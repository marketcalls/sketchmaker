"""Step runs: quote on start, advance in the scheduler, record what landed.

Lifecycle of a run (faceless_step_run):

  POST /steps/{step}  plan_step() builds the items and their estimate in USD; the run is
                      stored with one item per provider request and status "queued". An
                      idempotency key (header Idempotency-Key or body idempotency_key)
                      returns the existing run instead of starting another; one active
                      run per project and step.
  scheduler tick      every few seconds advance_one() reads each active run, polls its
                      submitted items on fal, settles finished ones and submits pending
                      ones (at most MAX_IN_FLIGHT_PER_RUN at once).
  finalize            when every item is terminal the run ends completed, partial, failed
                      or cancelled. Each item that lands is recorded in usage_log when it
                      lands; a failed one is not billed by fal, so nothing is recorded.

Item statuses: pending, submitted, done, failed, cancelled. Renders have no provider
request and run in render_job; queued script drafts run in script_job.

SQLite has one writer, so nothing here holds a write across a network call or ffmpeg.
Each write is: lock the row (apply_row_lock), re-check, apply, commit. Results are
downloaded and stored on disk first. A result is applied in a transaction of its own,
together with its usage row, so a landed result is never fetched or recorded twice and a
crash loses nothing that landed.

Settling. A finished item is settled only by whoever wins job_state.claim_job on its run,
which turns it "processing" (the API still shows "running"). One bad item must not fail
its neighbours, so errors while settling are judged per item with is_temporary_failure:

  temporary (network, key, fal outage, locked database)
      The item stays "submitted", the claim is released and the poller tries again after
      RETRY_SECONDS. fal keeps the result, so nothing paid for is lost, and a temporary error
      never ends an item by itself: a laptop asleep overnight, or a key being fixed, is not
      a failure. The way out of a provider that never comes back is the owner's: a cancelled
      run stops waiting after CANCEL_GIVES_UP_SECONDS out of reach.
      5xx answers are limited by job_state, since fal can answer one for a run that truly
      failed. The limit counts consecutive failures, per item and per phase, so answers
      scattered over a long poll never add up; the wait keeps it at the five minutes it was
      set for.
  a definite answer from fal (a 4xx, a content filter refusal, 5xx past that bound)
      The item fails at once: asking again will not change it.
  an unusable result (the bytes are not what they should be)
      Counted per item; after MAX_HANDLE_ERRORS the item fails.
  anything that breaks the claim itself (a failed commit)
      job_state.fail_claimed_job hands the whole run back, or fails it if it is permanent.

A finisher that fails (the last writes of a music or thumbnails run) rolls back whole. The
run stays open and a later tick tries again, with no provider call left to pay for.

Restarts. Request ids are committed as soon as fal returns them, so a restart keeps polling
what is in flight. release_orphaned_claims() hands back any run that was mid-settlement.
The one window left is a crash between fal accepting a request and that commit: the
request is then lost and is submitted again, at the cost of one extra provider request.

Quality checks: a still or clip item quoted with a check (qa_requested, its estimate folded
into the item's usd) gets item["qa"] = "pending" when its result is stored. A later tick
reads it with one vision call (app/services/quality_gate.py, its tokens logged by
litellm_client) and stores the verdict on the asset. The run finalizes only when no check
is pending. A failed check is a badge; nothing is regenerated.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
from datetime import datetime, timedelta
import io
import logging
import threading
import uuid

from fal_client.client import FalClientHTTPError
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.database import apply_row_lock
from app.models.content import Image
from app.models.faceless import FacelessCharacter, FacelessProject, FacelessStepRun
from app.services import job_state
from app.services.job_state import (
    PROCESSING_WINDOW, claim_job, fail_claimed_job, is_temporary_failure, lock_skip,
)
from app.services.pricing import USD_DECIMALS
from app.services.usage import record_usage

from . import activity, catalog, consent, media, pricing
from .errors import Blocked, Conflict, InvalidRequest, NotFound
from .scenes import scene_ids as ordered_scene_ids, words_from_timestamps

logger = logging.getLogger(__name__)

FEATURE = "faceless"
# What a run can be while it is unfinished. The API shows in_progress and processing as
# "running": they exist for job_state's claim (claim_job, fail_claimed_job).
ACTIVE = ("queued", "running", "in_progress", "processing")
CLAIMABLE = ("queued", "running", "in_progress")
TERMINAL_ITEMS = ("done", "failed", "cancelled")
MAX_HANDLE_ERRORS = 3
MAX_SUBMIT_ERRORS = 3
# Nothing has been paid for before a request is accepted, so a provider that stays
# unreachable for this long fails the item instead of leaving the run waiting.
SUBMIT_RETRY_SECONDS = 10 * 60
# The wait after a temporary failure. job_state's limit on 5xx retries was set for one
# attempt per 30-second poll, and this tick runs every 5 seconds.
RETRY_SECONDS = 30
# A cancelled run stops waiting for a request after the provider has been out of reach for
# this long. Long enough that a network blip does not lose a result that was paid for.
CANCEL_GIVES_UP_SECONDS = 10 * 60
# Vision calls per run per tick: each takes seconds, and the tick holds the thread.
QA_PER_TICK = 2

RUN_FAILED = "Something went wrong on our side while saving this step. Please try again."
RESULT_UNUSABLE = "We could not save the result of this step. Please try again."
PROVIDER_FAILED = "The AI service could not finish this step. Please try again."
SUBMIT_FAILED = "We could not start this step. Please try again."
NO_FAL_KEY = "Add your fal API key in Settings, under API keys."
NOT_COLLECTED = "Cancelled. The AI service could not be reached, so this result was not collected."


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


# ---------------------------------------------------------------------------
# API views
# ---------------------------------------------------------------------------

def item_view(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "kind": item.get("kind"),
        "scene_id": item.get("scene_id"),
        "index": item.get("index"),
        "status": item.get("status"),
        "usd": item.get("usd"),
        "error": item.get("error"),
        "code": item.get("code"),
        "qa": item.get("qa"),
        "qa_verdict": item.get("qa_verdict"),
    }


def _terminal_share(items: list[dict]) -> int:
    if not items:
        return 100
    return int(100 * sum(1 for i in items if i.get("status") in TERMINAL_ITEMS) / len(items))


def run_view(run: FacelessStepRun) -> dict:
    claimed = run.status in ("in_progress", "processing")
    return {
        "id": run.id,
        "project_id": run.project_id,
        "character_id": run.character_id,
        "step": run.step,
        "status": "running" if claimed else run.status,
        # A claim writes its own progress and time into these two columns.
        "progress": min(_terminal_share(run.items or []), 99) if claimed else int(run.progress or 0),
        "scene_ids": run.scene_ids or [],
        "options": run.options or {},
        "quote": run.quote or {},
        "estimated_usd": float(run.estimated_usd or 0),
        "usd_spent": round(float(run.usd_spent or 0), USD_DECIMALS),
        "cancel_requested": bool(run.cancel_requested),
        "error": run.error,
        "items": [item_view(i) for i in run.items or []],
        "idempotency_key": run.idempotency_key,
        "created_at": _iso(run.created_at),
        "started_at": _iso(run.started_at),
        "completed_at": None if run.status in ACTIVE else _iso(run.completed_at),
    }


# ---------------------------------------------------------------------------
# Starting a step (web request)
# ---------------------------------------------------------------------------

def _existing_for_key(db: Session, user_id: int, key: str | None) -> FacelessStepRun | None:
    if not key:
        return None
    return db.query(FacelessStepRun).filter(
        FacelessStepRun.user_id == user_id, FacelessStepRun.idempotency_key == key,
    ).first()


def _clean_key(key: str | None) -> str | None:
    key = (key or "").strip()
    if not key:
        return None
    if len(key) > 80:
        raise InvalidRequest("Idempotency key must be at most 80 characters.")
    return key


def check_expected(plan: dict, expected_usd) -> None:
    """The client confirmed a quote; refuse to start at a different estimate.

    The plan is rebuilt at confirm time, so assets, prices or the script may have changed
    since the dialog showed its quote."""
    if expected_usd is None:
        return
    try:
        expected = round(float(expected_usd), USD_DECIMALS)
    except (TypeError, ValueError):
        raise InvalidRequest("expected_usd must be a number.")
    if abs(expected - float(plan["usd"])) > 10 ** -USD_DECIMALS / 2:
        raise Conflict(
            f"The estimate changed from ${expected:g} to ${float(plan['usd']):g}. Review the new quote.",
            code="quote_changed", extra={"quote": pricing.quote_view(plan)},
        )


def lock_project(db: Session, project_id: int) -> FacelessProject:
    """The project row under the write lock, until commit.

    Serialises step starts, deletes and script drafts on one project: two concurrent POST
    /steps for the same step cannot both pass the "already running" check."""
    locked = apply_row_lock(db.query(FacelessProject).filter(FacelessProject.id == project_id)).first()
    if locked is None:
        raise NotFound("Project not found.")
    return locked


# Projects with a script being drafted inside a web request. The LLM call holds no row, so
# this is what stops a double click paying for two drafts, and a step starting underneath
# one. The app is one process, so a set is enough, and it dies with the process.
_inline_drafts: set[int] = set()
_inline_drafts_lock = threading.Lock()


def _drafting_conflict(run_id: int | None = None) -> Conflict:
    return Conflict("A new script is being drafted for this project. Wait for it to finish.",
                    code="script_active", extra={"run_id": run_id} if run_id else None)


@contextmanager
def inline_draft(project_id: int):
    """Hold the project's one inline draft, or answer that one is already running. Take it
    before checking for active runs, so a step that started first is seen."""
    with _inline_drafts_lock:
        if project_id in _inline_drafts:
            raise _drafting_conflict()
        _inline_drafts.add(project_id)
    try:
        yield
    finally:
        with _inline_drafts_lock:
            _inline_drafts.discard(project_id)


# What a script change can do to a step's results on their way. Items land by scene id and
# carry their own plan, so:
#   a scene's text or shot   safe. A picture lands on the scene it was asked for, as if the
#                            edit came just after it. A voice clip keeps the hash of the old
#                            text, so it shows as not current and the render skips it.
#   scene ids or their order refused (require_same_scenes): results would land on a scene
#                            that is gone or now means another one, and the timing they were
#                            planned on no longer holds.
#   a whole new script       refused (require_no_running_steps), even with the same ids: s1 of
#                            another draft is another scene, and ids cannot tell.
# All of these roll back before refusing, so a caller holding the write lock lets it go.

def _running_steps(db: Session, project_id: int) -> list[int]:
    """Active runs with results on their way, so every one but a script draft. A step cannot
    start during a draft, or a draft during a step, so the two never overlap."""
    return [run_id for (run_id,) in db.query(FacelessStepRun.id).filter(
        FacelessStepRun.project_id == project_id, FacelessStepRun.status.in_(ACTIVE),
        FacelessStepRun.step != "script").all()]


def require_no_running_steps(db: Session, project_id: int, doing: str) -> None:
    running = _running_steps(db, project_id)
    if running:
        db.rollback()
        raise Conflict(f"A step is running for this project. Wait for it to finish, or cancel it, before {doing}.",
                       code="steps_active", extra={"run_ids": running})


def require_same_scenes(db: Session, project: FacelessProject, script: dict) -> None:
    """An edited script may land during a step if it has the same scenes in the same order."""
    if ordered_scene_ids(script) == ordered_scene_ids(project.script):
        return
    running = _running_steps(db, project.id)
    if running:
        db.rollback()
        raise Conflict("A step is running, so scenes cannot be added, removed or moved yet. Wait for it to finish, "
                       "or cancel it. A scene's text and shot can be changed now.",
                       code="steps_active", extra={"run_ids": running})


def require_no_active_run(db: Session, project_id: int) -> None:
    """Before a new draft: no step, and no other draft in the queue."""
    require_no_running_steps(db, project_id, "drafting a new script")
    drafting = db.query(FacelessStepRun.id).filter(
        FacelessStepRun.project_id == project_id, FacelessStepRun.status.in_(ACTIVE)).first()
    if drafting is not None:
        run_id = drafting[0]
        db.rollback()
        raise _drafting_conflict(run_id)


def require_idle(db: Session, project_id: int) -> None:
    """Before a queued draft: as above, and no inline draft either."""
    require_no_active_run(db, project_id)
    if project_id in _inline_drafts:
        db.rollback()
        raise _drafting_conflict()


def _key_reused() -> Conflict:
    return Conflict("This idempotency key was already used for a different request.", code="key_reused")


def start_step(db: Session, user_id: int, project: FacelessProject, step: str, scene_ids: list | None,
               options: dict | None, idempotency_key: str | None,
               expected_usd: float | None = None) -> tuple[FacelessStepRun, bool]:
    """Plan and queue a step. Returns (run, created)."""
    key = _clean_key(idempotency_key)
    existing = _existing_for_key(db, user_id, key)
    if existing is not None:
        if existing.project_id != project.id or existing.step != step:
            raise _key_reused()
        return existing, False
    try:
        project = lock_project(db, project.id)
        existing = _existing_for_key(db, user_id, key)  # a twin request may have won the lock
        if existing is not None:
            db.rollback()
            if existing.project_id != project.id or existing.step != step:
                raise _key_reused()
            return existing, False
        if project.id in _inline_drafts:
            raise _drafting_conflict()
        if (project.compliance or {}).get("blocked"):
            raise Blocked("The script has a blocking compliance flag. Edit the script to resolve it first.",
                          code="compliance_block", extra={"flags": (project.compliance or {}).get("flags")})

        active = db.query(FacelessStepRun).filter(
            FacelessStepRun.project_id == project.id, FacelessStepRun.status.in_(ACTIVE),
        ).all()
        same = next((r for r in active if r.step == step), None)
        if same is not None:
            raise Conflict(f"A {step} run is already in progress for this project.", code="step_active",
                           extra={"run_id": same.id})
        drafting = next((r for r in active if r.step == "script"), None)
        if drafting is not None:
            raise Conflict("A new script is being drafted for this project. Wait for it to finish.",
                           code="script_active", extra={"run_id": drafting.id})
        if step == "render" and active:
            raise Conflict("Wait for the running steps to finish before rendering.", code="steps_active",
                           extra={"run_ids": [r.id for r in active]})
        rendering = next((r for r in active if r.step == "render"), None)
        if rendering is not None:
            # A new still or clip would replace (and delete) files the queued render is
            # about to read.
            raise Conflict("A render is queued or running for this project. Wait for it to finish.",
                           code="render_active", extra={"run_id": rendering.id})

        ctx = pricing.build_ctx(db, project)
        plan = pricing.plan_step(ctx, step, scene_ids, options)
        used = [ctx.char_by_id[str(cid)] for cid in plan["characters"] if str(cid) in ctx.char_by_id]
        consent.require_can_generate(used)
        if not plan["items"]:
            raise Conflict("Nothing to do: every selected scene already has a current result. "
                           "Pass scene_ids or options.regenerate to make new ones.", code="nothing_to_do")
        check_expected(plan, expected_usd)

        activity.check_rate(db, user_id, "step_run", catalog.STEP_RUNS_PER_HOUR, label="steps")
        return _create_run(db, user_id, project, None, step, plan, scene_ids, options, key)
    except Exception:
        db.rollback()
        raise


def start_sheet(db: Session, user_id: int, char: FacelessCharacter, options: dict | None,
                idempotency_key: str | None, expected_usd: float | None = None) -> tuple[FacelessStepRun, bool]:
    key = _clean_key(idempotency_key)
    existing = _existing_for_key(db, user_id, key)
    if existing is not None:
        if existing.character_id != char.id or existing.step != "sheet":
            raise _key_reused()
        return existing, False
    try:
        char = apply_row_lock(db.query(FacelessCharacter).filter(FacelessCharacter.id == char.id)).first()
        if char is None:
            raise NotFound("Character not found.")
        existing = _existing_for_key(db, user_id, key)
        if existing is not None:
            db.rollback()
            if existing.character_id != char.id or existing.step != "sheet":
                raise _key_reused()
            return existing, False
        consent.require_can_generate([char])
        plan = pricing.plan_sheet(char, options)
        active = db.query(FacelessStepRun).filter(
            FacelessStepRun.character_id == char.id, FacelessStepRun.status.in_(ACTIVE),
        ).first()
        if active is not None:
            raise Conflict("A sheet is already being made for this character.", code="step_active",
                           extra={"run_id": active.id})
        check_expected(plan, expected_usd)
        activity.check_rate(db, user_id, "step_run", catalog.STEP_RUNS_PER_HOUR, label="steps")
        return _create_run(db, user_id, None, char, "sheet", plan, None, options, key)
    except Exception:
        db.rollback()
        raise


def _create_run(db: Session, user_id: int, project: FacelessProject | None, char: FacelessCharacter | None,
                step: str, plan: dict, scene_ids, options, key: str | None) -> tuple[FacelessStepRun, bool]:
    """Store the run under the caller's lock, and commit."""
    key = key or f"auto-{uuid.uuid4().hex}"
    items = [{**item, "status": "pending", "request_id": None, "error": None} for item in plan["items"]]
    estimated = float(plan["usd"])
    try:
        run = FacelessStepRun(
            user_id=user_id,
            project_id=project.id if project else None,
            character_id=char.id if char else None,
            step=step,
            status="queued",
            idempotency_key=key,
            scene_ids=plan["scene_ids"] or ([str(s) for s in scene_ids] if scene_ids else []),
            options=dict(options or {}),
            quote=pricing.quote_view(plan),
            items=items,
            progress=0,
            estimated_usd=estimated,
            usd_spent=0.0,
        )
        db.add(run)
        db.flush()
        if project is not None and project.status in ("draft", "scripted"):
            project.status = "producing"
        activity.log_activity(db, user_id, "step_run", project_id=run.project_id, character_id=run.character_id,
                              step=step, run_id=run.id, estimated_usd=estimated)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_for_key(db, user_id, key)
        if existing is not None:
            return existing, False
        raise
    db.refresh(run)
    logger.info(f"Faceless {step} run {run.id} queued: {len(items)} item(s), estimated ${estimated:g}")
    return run, True


def cancel_run(db: Session, run: FacelessStepRun) -> FacelessStepRun:
    """Ask the scheduler to stop a run. Pending items are cancelled; requests already with
    the provider finish and are kept (the provider has been paid). A render is stopped."""
    if run.status in ACTIVE:
        db.query(FacelessStepRun).filter(
            FacelessStepRun.id == run.id, FacelessStepRun.status.in_(ACTIVE)).update(
            {FacelessStepRun.cancel_requested: True}, synchronize_session=False,
        )
        db.commit()
        db.refresh(run)
    return run


# ---------------------------------------------------------------------------
# Scheduler: advancing runs
# ---------------------------------------------------------------------------

class RunCtx:
    """One tick's view of a run. The run's fields are copied out, because its row is
    re-read under the lock each time it is written.

    The project and character are locked lazily and kept until the next commit: a second
    read with populate_existing would overwrite changes not yet flushed.
    """

    def __init__(self, db: Session, run: FacelessStepRun):
        self.db = db
        self.run_id = run.id
        self.user_id = run.user_id
        self.project_id = run.project_id
        self.character_id = run.character_id
        self.step = run.step
        self.quote = run.quote or {}
        self.cancel_requested = bool(run.cancel_requested)
        self.closed = False  # the run reached a final status this tick
        self.written: list[dict] = []     # stored this attempt, not landed yet
        self._replaced: list[dict] = []   # superseded files, to delete once the change commits
        self._project = None
        self._character = None

    def project(self) -> FacelessProject:
        if self._project is None:
            self._project = apply_row_lock(
                self.db.query(FacelessProject).filter(FacelessProject.id == self.project_id)).first()
            if self._project is None:
                raise RuntimeError("The project was deleted")
        return self._project

    def character(self) -> FacelessCharacter:
        if self._character is None:
            self._character = apply_row_lock(
                self.db.query(FacelessCharacter).filter(FacelessCharacter.id == self.character_id)).first()
            if self._character is None:
                raise RuntimeError("The character was deleted")
        return self._character

    def lock_run(self) -> FacelessStepRun | None:
        return apply_row_lock(self.db.query(FacelessStepRun).filter(FacelessStepRun.id == self.run_id)).first()

    def replaced(self, asset: dict | None) -> None:
        if asset:
            self._replaced.append(asset)

    def commit(self) -> None:
        self.db.commit()
        self._project = self._character = None
        self.written.clear()
        replaced, self._replaced = self._replaced, []
        _delete_files(replaced, self.user_id)

    def rollback(self) -> None:
        """Undo the open transaction, and remove the files of what did not land."""
        self.db.rollback()
        self._project = self._character = None
        self._replaced = []
        written, self.written = self.written, []
        _delete_files(written, self.user_id)


def _delete_files(assets: list[dict], user_id: int) -> None:
    for asset in assets:
        try:
            media.run_async(media.delete_stored(asset, user_id))
        except Exception as exc:
            logger.warning(f"Could not delete faceless asset {asset.get('file')}: {type(exc).__name__}")


def release_orphaned_claims(db: Session) -> int:
    """Hand back every run that was mid-settlement. For startup only: there is one process,
    so a claim that survived a restart belongs to a worker that no longer exists. Whatever
    landed is already committed, and the rest is fetched from fal again."""
    released = (
        db.query(FacelessStepRun)
        .filter(FacelessStepRun.status == "processing")
        .update({"status": "in_progress", "completed_at": None}, synchronize_session=False)
    )
    db.commit()
    return released


def _release_stale_claims(db: Session) -> None:
    """A claim outlives its tick only if the worker thread died without a restart."""
    stale = FacelessStepRun.completed_at < datetime.utcnow() - PROCESSING_WINDOW
    query = db.query(FacelessStepRun).filter(FacelessStepRun.status == "processing", stale)
    if query.first() is None:
        return
    query.update({"status": "in_progress", "completed_at": None}, synchronize_session=False)
    db.commit()


def tick(db: Session) -> int:
    """Advance every active non-render run once. Returns how many were looked at."""
    _release_stale_claims(db)
    ids = [
        rid for (rid,) in db.query(FacelessStepRun.id)
        .filter(FacelessStepRun.status.in_(CLAIMABLE), FacelessStepRun.step.notin_(("render", "script")))
        # Least recently advanced first (never advanced before all others),
        # so with more than 50 active runs every run still gets its turn.
        .order_by(FacelessStepRun.heartbeat_at.isnot(None), FacelessStepRun.heartbeat_at,
                  FacelessStepRun.created_at)
        .limit(50)
        .all()
    ]
    db.rollback()
    for rid in ids:
        advance_one(db, rid)
    return len(ids)


def advance_one(db: Session, run_id: int) -> None:
    """One tick of one run. Provider calls happen between the commits, never inside one."""
    run = lock_skip(
        db.query(FacelessStepRun).filter(FacelessStepRun.id == run_id, FacelessStepRun.status.in_(CLAIMABLE))
    ).populate_existing().first()
    if run is None:
        db.rollback()
        return
    rc = RunCtx(db, run)
    items = copy.deepcopy(run.items or [])
    # attempts counts finishers that failed (_finish_later): those wait between tries.
    waiting = bool(run.attempts) and _seconds_since(run.heartbeat_at) < RETRY_SECONDS
    db.rollback()
    if waiting:
        return
    claimed = False
    try:
        _stop_pending_items(rc, items)
        _run_quality_checks(rc, items)
        finished = _poll(rc, items)
        if finished:
            if not claim_job(db, FacelessStepRun, run_id, from_states=CLAIMABLE):
                return  # someone else is settling this run
            claimed = True
            _settle(rc, items, finished)
        _save(rc, items)
        claimed = False
        if not rc.closed and _submit(rc, items):
            _save(rc, items)
    except Exception as exc:
        logger.exception(f"Faceless run {run_id}: tick failed: {exc}")
        if not claimed:
            rc.rollback()
        elif fail_claimed_job(db, FacelessStepRun, run_id, RUN_FAILED):
            rc.rollback()
            _close_after_failure(rc)
        else:
            rc.rollback()


def _close_after_failure(rc: RunCtx) -> None:
    """The run failed for good: close the items that were still open."""
    try:
        run = rc.lock_run()
        items = copy.deepcopy(run.items or [])
        for item in items:
            if item.get("status") not in TERMINAL_ITEMS:
                _fail(item, RUN_FAILED)
        media.set_json(run, "items", items)
        run.progress = 100
        rc.commit()
    except Exception as exc:
        rc.rollback()
        logger.warning(f"Faceless run {rc.run_id}: items not closed: {type(exc).__name__}")


def _stop_pending_items(rc: RunCtx, items: list[dict]) -> None:
    """Cancelled, or a character can no longer be used: nothing more goes to the provider.
    Requests already with the provider finish."""
    if rc.cancel_requested:
        for item in items:
            if item["status"] == "pending":
                item["status"] = "cancelled"
                item["error"] = "Cancelled"
            if item.get("qa") == "pending":
                item["qa"] = "skipped"
    if not any(i["status"] == "pending" for i in items):
        return
    blocked = _blocked_characters(rc)
    if blocked:
        for item in items:
            if item["status"] == "pending":
                item["status"] = "cancelled"
                item["error"] = blocked[:500]
                item["code"] = "consent_required"


def _blocked_characters(rc: RunCtx) -> str | None:
    """Why the run may no longer send anything to the provider, or None.

    The characters a run started with are in its quote. Each is re-read: one that was
    deleted, archived or had its consent revoked since blocks every item not yet
    submitted."""
    ids = []
    for cid in rc.quote.get("characters") or []:
        try:
            ids.append(int(cid))
        except (TypeError, ValueError):
            continue
    if rc.character_id and rc.character_id not in ids:
        ids.append(int(rc.character_id))
    if not ids:
        return None
    rows = {c.id: c for c in rc.db.query(FacelessCharacter).filter(
        FacelessCharacter.id.in_(ids), FacelessCharacter.user_id == rc.user_id).all()}
    reasons = []
    for cid in ids:
        char = rows.get(cid)
        if char is None:
            reasons.append("A character in this step was deleted.")
            continue
        reason = consent.generation_block_reason(char)
        if reason:
            reasons.append(reason)
    if not reasons:
        return None
    return " ".join(reasons) + " The remaining items were cancelled."


def _fail(item: dict, message: str) -> None:
    item["status"] = "failed"
    item["error"] = (message or "Failed")[:500]
    item["completed_at"] = datetime.utcnow().isoformat()


def _bump(item: dict, field: str) -> int:
    item[field] = int(item.get(field) or 0) + 1
    return item[field]


def _age_seconds(item: dict, now: datetime) -> float:
    return (now - datetime.fromisoformat(item.get("submitted_at") or now.isoformat())).total_seconds()


def _seconds_since(value: datetime | None) -> float:
    return (datetime.utcnow() - value).total_seconds() if value else float("inf")


_PHASES = {"poll": 0, "result": 1, "fetch": 2, "submit": 3}


def _retry_key(rc: RunCtx, item: dict, phase: str) -> int:
    """job_state counts 5xx answers per job. Counted per item and per phase here: one outage
    must not fail a run with many items early, and a status check that failed says nothing
    about fetching a result."""
    digits = "".join(c for c in str(item.get("id")) if c.isdigit())
    return (rc.run_id * 10_000 + int(digits or 0)) * 10 + _PHASES[phase]


def _is_temporary(rc: RunCtx, item: dict, exc: Exception, phase: str) -> bool:
    return is_temporary_failure(FacelessStepRun, _retry_key(rc, item, phase), exc)


def _answered(rc: RunCtx, item: dict, phase: str) -> None:
    """This phase got a good answer, so its count of failures starts again: the limit is on
    failures in a row, not on how many a long poll collects."""
    job_state._server_errors.pop((FacelessStepRun.__name__, _retry_key(rc, item, phase)), None)


def _retry_later(rc: RunCtx, item: dict) -> None:
    """After a temporary failure. It never ends the item by itself, however old the item is.
    Only the owner's cancel does, and only once the provider has stayed out of reach."""
    now = datetime.utcnow()
    item["retry_at"] = (now + timedelta(seconds=RETRY_SECONDS)).isoformat()
    since = item.setdefault("unreachable_since", now.isoformat())
    if rc.cancel_requested and (now - datetime.fromisoformat(since)).total_seconds() > CANCEL_GIVES_UP_SECONDS:
        item["status"] = "cancelled"
        item["error"] = NOT_COLLECTED


def _waiting_to_retry(item: dict) -> bool:
    retry_at = item.get("retry_at")
    return bool(retry_at) and datetime.fromisoformat(retry_at) > datetime.utcnow()


def _poll(rc: RunCtx, items: list[dict]) -> list[dict]:
    """Status of every submitted item (network, no write). Returns the finished ones."""
    finished = []
    for item in items:
        if item["status"] != "submitted" or _waiting_to_retry(item):
            continue
        try:
            state = media.fal_status(rc.db, item["endpoint"], item["request_id"])
        except Exception as exc:
            if _is_temporary(rc, item, exc, "poll"):
                logger.warning(f"Faceless run {rc.run_id} item {item.get('id')}: status check will retry "
                               f"({type(exc).__name__})")
                _retry_later(rc, item)
            elif _bump(item, "poll_errors") >= catalog.MAX_POLL_ERRORS:
                logger.warning(f"Faceless run {rc.run_id} item {item.get('id')}: status checks failed: {exc}")
                _fail(item, "We could not reach the AI service for this step. Please try again.")
            continue
        _answered(rc, item, "poll")
        item.pop("poll_errors", None)
        item["state"] = state
        if state == "completed":
            finished.append(item)
            continue
        item.pop("unreachable_since", None)
        if _age_seconds(item, datetime.utcnow()) > catalog.ITEM_TIMEOUT_SECONDS:
            # Checked only on a good answer: fal says this is still not done. A machine
            # that was asleep past the timeout must look at the result first.
            _fail(item, "The AI service took too long on this step. Please try again.")
    return finished


def _settle(rc: RunCtx, items: list[dict], finished: list[dict]) -> None:
    """Fetch and land each finished item. The caller holds the claim. Stops at the first
    temporary failure: the next item would almost certainly hit it too."""
    from app.clients.fal_client import job_failure_error

    for item in finished:
        phase = "result"
        try:
            result = media.fal_result(rc.db, item["endpoint"], item["request_id"])
            _answered(rc, item, phase)
            phase = "fetch"
            landed = FETCHERS[item["kind"]](rc, item, result)
            _land(rc, items, item, landed)
            _answered(rc, item, phase)
        except Exception as exc:
            rc.rollback()
            if _is_temporary(rc, item, exc, phase):
                logger.warning(f"Faceless run {rc.run_id} item {item.get('id')}: result kept at the provider, "
                               f"will retry ({type(exc).__name__})")
                _retry_later(rc, item)
                return
            logger.warning(f"Faceless run {rc.run_id} item {item.get('id')}: storing the result failed: {exc}")
            if isinstance(exc, FalClientHTTPError):
                _fail(item, job_failure_error(exc, PROVIDER_FAILED))
            elif _bump(item, "handle_errors") >= MAX_HANDLE_ERRORS:
                _fail(item, RESULT_UNUSABLE)


def _provider_usd(item: dict) -> float:
    """What the provider is estimated to have billed this item, without its quality check
    (an LLM call that litellm_client logs)."""
    usd = item.get("usd_actual")
    if usd is None:
        usd = float(item.get("usd") or 0) - float(item.get("qa_usd") or 0)
    return round(float(usd), USD_DECIMALS)


def _add_spent(rc: RunCtx, run: FacelessStepRun, usd: float) -> None:
    if usd <= 0:
        return
    run.usd_spent = round(float(run.usd_spent or 0) + usd, USD_DECIMALS)
    if rc.project_id:
        project = rc.project()
        by_step = dict(project.usd_by_step or {})
        by_step[rc.step] = round(float(by_step.get(rc.step) or 0) + usd, USD_DECIMALS)
        media.set_json(project, "usd_by_step", by_step)


def _land(rc: RunCtx, items: list[dict], item: dict, landed: dict) -> None:
    """Apply one fetched result, with its usage row, in one short transaction."""
    run = rc.lock_run()
    if run is None or run.status != "processing":
        raise RuntimeError("The claim on this run was lost")
    done = copy.deepcopy(item)
    APPLIERS[item["kind"]](rc, done, landed)
    done["status"] = "done"
    done["completed_at"] = datetime.utcnow().isoformat()
    usd = _provider_usd(done)
    record_usage(rc.db, feature=FEATURE, usd=usd, model=done.get("model") or done.get("endpoint"),
                 units=done.get("units"), unit=done.get("unit"), job_type=FEATURE, job_id=rc.run_id,
                 detail={"step": rc.step, "item": done.get("id"), "scene_id": done.get("scene_id"),
                         "project_id": rc.project_id, "character_id": rc.character_id})
    _add_spent(rc, run, usd)
    media.set_json(run, "items", [done if i is item else i for i in items])
    run.heartbeat_at = datetime.utcnow()
    rc.commit()
    item.clear()
    item.update(done)


def _save(rc: RunCtx, items: list[dict]) -> None:
    """Write the items and close the run when it is done, releasing any claim."""
    run = rc.lock_run()
    if run is None or run.status not in ACTIVE:
        # Closed while the providers were talking: this tick's results are dropped.
        rc.rollback()
        rc.closed = True
        return
    now = datetime.utcnow()
    if run.status != "running":
        run.status = "running"
        run.started_at = run.started_at or now
        run.completed_at = None
    checking = any(i.get("qa") == "pending" for i in items)
    run.progress = _terminal_share(items)
    if checking:
        run.progress = min(run.progress, 99)
    run.heartbeat_at = now
    media.set_json(run, "items", copy.deepcopy(items))
    if all(i["status"] in TERMINAL_ITEMS for i in items) and not checking:
        try:
            _finalize(rc, run, items)
        except OperationalError:
            raise  # a locked database: nothing changed, and the caller hands the run back
        except Exception as exc:
            logger.exception(f"Faceless {rc.step} run {rc.run_id} could not be finished: {exc}")
            _finish_later(rc, items)
            return
        rc.closed = True
    rc.commit()


def _finish_later(rc: RunCtx, items: list[dict]) -> None:
    """A finisher failed, and what it did is rolled back whole. Every provider request has
    already been paid for and stored, so later ticks try again with nothing left to pay. A
    cancelled run stops trying: it ends failed, and its files go when the project does."""
    rc.rollback()
    rc.closed = True
    run = rc.lock_run()
    if run is None:
        rc.rollback()
        return
    now = datetime.utcnow()
    media.set_json(run, "items", copy.deepcopy(items))
    run.attempts = int(run.attempts or 0) + 1
    run.heartbeat_at = now
    if run.cancel_requested:
        run.status = "failed"
        run.error = RESULT_UNUSABLE
        run.progress = 100
        run.completed_at = now
    else:
        run.status = "running"
        run.progress = 99
        run.completed_at = None
    rc.commit()


def _cancel_requested_now(rc: RunCtx) -> bool:
    flag = rc.db.query(FacelessStepRun.cancel_requested).filter(FacelessStepRun.id == rc.run_id).scalar()
    rc.db.rollback()
    return bool(flag)


def _submit(rc: RunCtx, items: list[dict]) -> bool:
    """Send pending items to fal, up to the in-flight limit. True when anything changed.
    Each request id is committed as soon as fal returns it, so a restart keeps polling it."""
    changed = False
    in_flight = sum(1 for i in items if i["status"] == "submitted")
    for item in items:
        if in_flight >= catalog.MAX_IN_FLIGHT_PER_RUN:
            break
        if item["status"] != "pending":
            continue
        # A tick can run for minutes. Asked each time, with a plain read that holds no write.
        rc.cancel_requested = rc.cancel_requested or _cancel_requested_now(rc)
        _stop_pending_items(rc, items)
        if item["status"] != "pending":
            changed = True
            continue
        if item.get("chain_from") is not None and not _chain_start(rc, item, items):
            continue  # waits for the part it continues from
        changed = True
        try:
            arguments = item["arguments"]
            if media.has_private_refs(arguments):
                # Private character media goes up to fal now, and its fal URL is never stored.
                arguments = media.resolve_provider_refs(arguments, rc.user_id, rc.db)
            item["request_id"] = media.fal_submit(rc.db, item["endpoint"], arguments)
        except Exception as exc:
            if _submit_failed(rc, item, exc):
                break
            continue
        _answered(rc, item, "submit")
        item["status"] = "submitted"
        item["submitted_at"] = datetime.utcnow().isoformat()
        in_flight += 1
        try:
            _save(rc, items)
        except OperationalError as exc:
            # The request is paid for: keep going, and the save at the end of the tick has
            # another try at writing its id.
            rc.db.rollback()
            logger.warning(f"Faceless run {rc.run_id} item {item.get('id')}: request id not saved yet: {exc}")
    return changed


def _submit_failed(rc: RunCtx, item: dict, exc: Exception) -> bool:
    """True when the provider is out of reach for now, so the other items can wait too."""
    from app.clients.fal_client import is_content_policy_error, job_failure_error
    from app.services.fal_keys import FAL_KEY_REJECTED, FalKeyMissing, is_fal_auth_error

    logger.warning(f"Faceless run {rc.run_id} item {item.get('id')}: submit failed: {exc}")
    if isinstance(exc, FalKeyMissing):
        _fail(item, NO_FAL_KEY)
        return False
    if _is_temporary(rc, item, exc, "submit"):
        now = datetime.utcnow()
        since = item.setdefault("first_submit_error_at", now.isoformat())
        if (now - datetime.fromisoformat(since)).total_seconds() > SUBMIT_RETRY_SECONDS:
            _fail(item, FAL_KEY_REJECTED if is_fal_auth_error(exc) else SUBMIT_FAILED)
        return True
    if is_content_policy_error(exc) or _bump(item, "submit_errors") >= MAX_SUBMIT_ERRORS:
        _fail(item, job_failure_error(exc, SUBMIT_FAILED))
    return False


def _chain_start(rc: RunCtx, item: dict, items: list[dict]) -> bool:
    """Ready to submit a clip part that starts on the previous part's last frame (a video
    family without an end frame, see pricing._plan_clips).

    Waits while the previous part runs. Once it is stored, its last frame is extracted with
    ffmpeg, stored as a generation input and becomes this part's first frame; if the
    previous part failed or the frame cannot be read, the part keeps its storyboard still
    (already in its arguments)."""
    from app.clients.fal_client import STORY_VIDEO_MODELS

    prev = next((i for i in items if i.get("kind") == "clip" and i.get("scene_id") == item.get("scene_id")
                 and i.get("index") == item.get("chain_from")), None)
    if prev is not None and prev["status"] in ("pending", "submitted"):
        return False
    item["chain_from"] = None
    stored = (prev or {}).get("result") or {}
    if not prev or prev["status"] != "done" or not stored.get("file"):
        return True
    try:
        content = media.run_async(media.read_bytes(
            {"file": stored["file"], "storage": stored.get("storage") or "videos"}, rc.user_id))
        frame = media.last_frame(content, ".mp4") if content else None
        if frame:
            saved = media.run_async(media.store_bytes(frame, user_id=rc.user_id, storage="uploads",
                                                      prefix="fl_chain", ext=".jpg", content_type="image/jpeg"))
            field = STORY_VIDEO_MODELS[catalog.H3_FAMILY].get("start_field") or "image_url"
            item["arguments"] = {**item["arguments"], field: saved["url"]}
            item["chained_frame"] = saved["file"]
    except Exception as exc:
        logger.warning(f"Faceless run {rc.run_id} item {item.get('id')}: last frame not extracted: {exc}")
    return True


def _finalize(rc: RunCtx, run: FacelessStepRun, items: list[dict]) -> None:
    """Close the run, inside the caller's transaction. A finisher that raises takes the whole
    transaction with it (see _save)."""
    done = sum(1 for i in items if i["status"] == "done")
    if done == len(items):
        run.status = "completed"
    elif done == 0:
        run.status = "cancelled" if run.cancel_requested else "failed"
    else:
        run.status = "partial"
    errors = [i.get("error") for i in items if i["status"] == "failed" and i.get("error")]
    errors += [i.get("error") for i in items if i["status"] == "cancelled" and i.get("code") == "consent_required"]
    run.error = errors[0] if errors and run.status in ("failed", "partial") else None
    run.completed_at = datetime.utcnow()
    run.progress = 100
    finisher = FINALIZERS.get(rc.step) if done else None
    if finisher:
        finisher(rc, items)
    logger.info(f"Faceless {rc.step} run {rc.run_id} {run.status}: {done}/{len(items)} done, "
                f"${float(run.usd_spent or 0):g} estimated spent")


# ---------------------------------------------------------------------------
# Quality checks of stored stills and clips
# ---------------------------------------------------------------------------

async def _reference_bytes(rc: RunCtx, refs: list[dict]) -> list[tuple[str, bytes]]:
    """The approved references of an item: each character's first reference image (sheet
    first) and product photos, all read from disk."""
    from app.services.storage_service import read_local_media

    from .pricing import _ROLE_ORDER

    out: list[tuple[str, bytes]] = []
    for ref in refs or []:
        try:
            if ref.get("character_id") is not None:
                char = rc.db.query(FacelessCharacter).filter(
                    FacelessCharacter.id == int(ref["character_id"]),
                    FacelessCharacter.user_id == rc.user_id).first()
                entries = sorted(
                    (m for m in (char.media if char else None) or []
                     if m.get("kind") == "image" and m.get("role") in _ROLE_ORDER
                     and m.get("usable_as_reference", True)),
                    key=lambda m: (_ROLE_ORDER[m["role"]], m.get("created_at") or ""))
                blob = await media.read_bytes(entries[0], rc.user_id) if entries else None
            elif ref.get("url"):
                path = read_local_media(ref["url"])
                blob = path.read_bytes() if path else None
            else:
                blob = None
        except Exception as exc:
            logger.warning(f"Faceless run {rc.run_id}: a check reference could not be read: {type(exc).__name__}")
            blob = None
        if blob:
            out.append((str(ref.get("label") or "the subject"), blob))
    return out


async def _check_item(rc: RunCtx, item: dict) -> dict:
    from app.services import quality_gate

    stored = item.get("result") or {}
    storage = stored.get("storage") or ("videos" if item.get("kind") == "clip" else "images")
    blob = await media.read_bytes({"file": stored.get("file"), "storage": storage}, rc.user_id)
    if not blob:
        return quality_gate.nothing_to_check(item.get("kind") or "still", quality_gate.UNVERIFIED_FAILED)
    refs = await _reference_bytes(rc, item.get("qa_refs") or [])
    if item.get("kind") == "clip":
        frames = media.extract_frames(blob, ".mp4", stored.get("duration") or item.get("seconds"), 3,
                                      positions=[0.02, 0.5, 0.97])
        if not frames:
            return quality_gate.nothing_to_check("clip", quality_gate.UNVERIFIED_FAILED)
        return await quality_gate.check_clip(frames, scene_text=item.get("qa_scene") or "", references=refs,
                                             user_id=rc.user_id)
    return await quality_gate.check_still(blob, scene_text=item.get("qa_scene") or "",
                                          cast=item.get("qa_cast") or [], references=refs,
                                          aspect=item.get("qa_aspect"), user_id=rc.user_id)


def _store_verdict(rc: RunCtx, item: dict, verdict: dict) -> None:
    """Put the verdict on the asset the item stored, if it is still there."""
    project = rc.project()
    assets = _scene_assets(project)
    field = "clips" if item.get("kind") == "clip" else "stills"
    entries = (assets.get(item["scene_id"]) or {}).get(field) or []
    index = int(item.get("index") or 0)
    entry = entries[index] if index < len(entries) else None
    if not entry or entry.get("file") != (item.get("result") or {}).get("file"):
        return  # replaced since; the newer asset has its own check
    entry["quality"] = verdict
    media.set_json(project, "scene_assets", assets)


def _run_quality_checks(rc: RunCtx, items: list[dict]) -> None:
    """Check up to QA_PER_TICK stored items. The vision calls run with no write held; each
    verdict is then stored in a short transaction."""
    from app.services import quality_gate

    due = [i for i in items if i.get("status") == "done" and i.get("qa") == "pending"][:QA_PER_TICK]
    if due and _blocked_characters(rc):
        # Consent revoked or a character deleted: their references go nowhere any more.
        for item in items:
            if item.get("qa") == "pending":
                item["qa"] = "skipped"
        return
    for item in due:
        try:
            verdict = media.run_async(_check_item(rc, item))
        except Exception as exc:
            logger.warning(f"Faceless run {rc.run_id} item {item.get('id')}: quality check failed: {exc}")
            verdict = quality_gate.nothing_to_check(item.get("kind") or "still", quality_gate.UNVERIFIED_FAILED)
        usd = 0.0 if verdict.get("verdict") == quality_gate.UNVERIFIED else float(item.get("qa_usd") or 0)
        verdict["estimated_usd"] = usd
        item["qa"] = "done"
        item["qa_verdict"] = verdict.get("verdict")
        try:
            run = rc.lock_run()
            _store_verdict(rc, item, verdict)
            _add_spent(rc, run, usd)
            media.set_json(run, "items", copy.deepcopy(items))
            rc.commit()
        except Exception as exc:
            rc.rollback()
            logger.warning(f"Faceless run {rc.run_id} item {item.get('id')}: verdict not stored: {exc}")


# ---------------------------------------------------------------------------
# Results. Fetchers download and store with no write held; appliers run under the lock
# and change rows. A fetcher adds what it stored to rc.written, so a failure removes it.
# ---------------------------------------------------------------------------

def _first_file(result: dict, key: str) -> dict:
    value = (result or {}).get(key)
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, dict) or not value.get("url"):
        raise ValueError(f"The provider returned no {key}")
    return value


def _store_result(rc: RunCtx, file: dict, *, storage: str, prefix: str, default_ext: str,
                  max_bytes: int, kind: str) -> tuple[bytes, dict]:
    content = media.run_async(media.download(file["url"], max_bytes))
    media.check_result_kind(content, kind)
    ext = media.ext_from_result(file, default_ext)
    stored = media.run_async(media.store_bytes(
        content, user_id=rc.user_id, storage=storage, prefix=prefix, ext=ext,
        content_type=media.content_type_for(ext),
    ))
    rc.written.append(stored)
    return content, stored


def _scene_assets(project: FacelessProject) -> dict:
    return copy.deepcopy(project.scene_assets or {})


def _put_at(values: list, index: int, value) -> tuple[list, object]:
    values = list(values or [])
    while len(values) <= index:
        values.append(None)
    old = values[index]
    values[index] = value
    return values, old


def _mark_for_check(item: dict, entry: dict) -> None:
    if item.get("qa_requested"):
        entry["quality"] = {"status": "pending", "request": {"estimated_usd": item.get("qa_usd")}}
        item["qa"] = "pending"


def fetch_still(rc: RunCtx, item: dict, result: dict) -> dict:
    file = _first_file(result, "images")
    content, stored = _store_result(rc, file, storage="images", prefix="fl_still", default_ext=".png",
                                    max_bytes=media.RESULT_IMAGE_MAX_BYTES, kind="image")
    width, height = media.image_size(content)
    return {"stored": stored, "width": width, "height": height,
            "seed": result.get("seed") if isinstance(result.get("seed"), int) else item.get("seed")}


def apply_still(rc: RunCtx, item: dict, landed: dict) -> None:
    stored = landed["stored"]
    project = rc.project()
    assets = _scene_assets(project)
    scene = assets.setdefault(item["scene_id"], {})
    entry = {
        "file": stored["file"], "storage": stored["storage"], "model": item.get("model"),
        "seed": landed["seed"], "prompt": (item.get("prompt") or "")[:2000], "prompt_hash": item.get("prompt_hash"),
        "width": landed["width"], "height": landed["height"], "run_id": rc.run_id,
        "created_at": datetime.utcnow().isoformat(),
    }
    _mark_for_check(item, entry)
    stills, old = _put_at(scene.get("stills"), int(item.get("index") or 0), entry)
    scene["stills"] = stills[: max(int(item.get("of") or 1), 1)]
    media.set_json(project, "scene_assets", assets)
    rc.replaced(old)
    item["result"] = {"file": stored["file"]}


def fetch_clip(rc: RunCtx, item: dict, result: dict) -> dict:
    from app.clients.fal_client import STORY_VIDEO_MODELS, story_reference_token_usd
    from app.services import pricing as cp

    file = _first_file(result, "video")
    content, stored = _store_result(rc, file, storage="videos", prefix="fl_clip", default_ext=".mp4",
                                    max_bytes=media.RESULT_VIDEO_MAX_BYTES, kind="video")
    info = media.probe_bytes(content, ".mp4")
    landed = {"stored": stored, "info": info}
    tokens = result.get("reference_tokens")
    if item.get("mode") == "reference" and isinstance(tokens, (int, float)) and not isinstance(tokens, bool):
        # Estimated at the worst case of reference tokens; recorded on what fal reports.
        included = STORY_VIDEO_MODELS[catalog.H3_FAMILY]["reference_tokens"]["included"]
        base = cp.usd_for(item["key"]) * int(item.get("seconds") or 0)
        actual = base + story_reference_token_usd(catalog.H3_FAMILY, max(0, tokens - included))
        landed["usd_actual"] = round(min(actual, float(item.get("usd") or 0) - float(item.get("qa_usd") or 0)),
                                     cp.USD_DECIMALS)
        landed["reference_tokens"] = tokens
    return landed


def apply_clip(rc: RunCtx, item: dict, landed: dict) -> None:
    stored, info = landed["stored"], landed["info"]
    if "usd_actual" in landed:
        item["usd_actual"] = landed["usd_actual"]
        item["reference_tokens"] = landed["reference_tokens"]
    project = rc.project()
    assets = _scene_assets(project)
    scene = assets.setdefault(item["scene_id"], {})
    entry = {
        "file": stored["file"], "storage": stored["storage"], "model": item.get("model"),
        "mode": item.get("mode"), "resolution": item.get("resolution"), "seconds": item.get("seconds"),
        "duration": info.get("duration") or item.get("seconds"), "width": info.get("width"),
        "height": info.get("height"), "seed": item.get("seed"), "run_id": rc.run_id,
        "created_at": datetime.utcnow().isoformat(),
    }
    _mark_for_check(item, entry)
    clips, old = _put_at(scene.get("clips"), int(item.get("index") or 0), entry)
    scene["clips"] = clips[: max(int(item.get("of") or 1), 1)]
    media.set_json(project, "scene_assets", assets)
    rc.replaced(old)
    item["result"] = {"file": stored["file"], "storage": stored["storage"], "duration": entry["duration"]}


def fetch_voice(rc: RunCtx, item: dict, result: dict) -> dict:
    file = _first_file(result, "audio")
    content, stored = _store_result(rc, file, storage="uploads", prefix="fl_voice", default_ext=".mp3",
                                    max_bytes=media.RESULT_AUDIO_MAX_BYTES, kind="audio")
    info = media.probe_bytes(content, ".mp3")
    duration = info.get("duration")
    if not duration:
        raise ValueError("The voice clip has no readable length")
    words = words_from_timestamps(result.get("timestamps"), item.get("text") or "", duration)
    check = media.voice_take_check(content, ".mp3", float(duration), len(words))
    return {"stored": stored, "duration": round(float(duration), 3), "words": words, "check": check}


def apply_voice(rc: RunCtx, item: dict, landed: dict) -> None:
    stored = landed["stored"]
    project = rc.project()
    assets = _scene_assets(project)
    scene = assets.setdefault(item["scene_id"], {})
    voices = [v for v in scene.get("voice") or [] if int(v.get("index", -1)) != int(item["index"])]
    old = next((v for v in scene.get("voice") or [] if int(v.get("index", -1)) == int(item["index"])), None)
    voices.append({
        "index": int(item["index"]), "hash": item.get("hash"), "file": stored["file"],
        "storage": stored["storage"], "duration": landed["duration"], "words": landed["words"],
        "voice": item.get("voice"), "speaker": item.get("speaker"), "character_id": item.get("character_id"),
        "chars": item.get("chars"), "run_id": rc.run_id, "created_at": datetime.utcnow().isoformat(),
        "check": landed["check"],
    })
    voices.sort(key=lambda v: int(v["index"]))
    scene["voice"] = voices
    media.set_json(project, "scene_assets", assets)
    rc.replaced(old)
    item["result"] = {"file": stored["file"], "duration": landed["duration"], "words": len(landed["words"])}


def fetch_music(rc: RunCtx, item: dict, result: dict) -> dict:
    file = _first_file(result, "audio")
    content, stored = _store_result(rc, file, storage="uploads", prefix="fl_music", default_ext=".mp3",
                                    max_bytes=media.RESULT_AUDIO_MAX_BYTES, kind="audio")
    info = media.probe_bytes(content, ".mp3")
    return {"stored": stored, "duration": round(float(info.get("duration") or item.get("seconds") or 0), 3)}


def apply_music(rc: RunCtx, item: dict, landed: dict) -> None:
    stored = landed["stored"]
    item["result"] = {"file": stored["file"], "storage": stored["storage"], "duration": landed["duration"]}


def finish_music(rc: RunCtx, items: list[dict]) -> None:
    done = [i for i in items if i["status"] == "done" and i.get("result")]
    if not done:
        return
    project = rc.project()
    old = project.music or {}
    tracks = [{
        "index": i["index"], "file": i["result"]["file"], "storage": i["result"]["storage"],
        "duration": i["result"]["duration"], "start": i.get("start", 0.0),
    } for i in sorted(done, key=lambda i: i["index"])]
    media.set_json(project, "music", {
        "tracks": tracks,
        "mood": done[0].get("mood"),
        "plan_hash": done[0].get("plan_hash"),
        "instrumental": done[0].get("instrumental", True),
        "run_id": rc.run_id,
        # Rights record: what was generated, with what, for whom and when.
        "rights": {
            "provider": "ElevenLabs Music via fal.ai",
            "endpoint": catalog.MUSIC_ENDPOINT,
            "request_ids": [i.get("request_id") for i in done],
            "composition_plans": [i["arguments"].get("composition_plan") for i in done],
            "generated_at": datetime.utcnow().isoformat(),
            "user_id": rc.user_id,
            "ai_generated": True,
            "note": "AI-generated music made for this account. YouTube asks creators to disclose "
                    "realistic synthetic content; keep this record with the video.",
        },
    })
    for track in old.get("tracks") or []:
        rc.replaced(track)


def fetch_thumbnail(rc: RunCtx, item: dict, result: dict) -> dict:
    file = _first_file(result, "images")
    content = media.run_async(media.download(file["url"], media.RESULT_IMAGE_MAX_BYTES))
    media.check_result_kind(content, "image")
    composed = draw_headline(content, item.get("text") or "")
    ext = media.ext_from_result(file, ".png")
    raw = media.run_async(media.store_bytes(content, user_id=rc.user_id, storage="images", prefix="fl_thumbraw",
                                            ext=ext, content_type=media.content_type_for(ext)))
    rc.written.append(raw)
    final = media.run_async(media.store_bytes(composed, user_id=rc.user_id, storage="images", prefix="fl_thumb",
                                              ext=".png", content_type="image/png"))
    rc.written.append(final)
    width, height = media.image_size(composed)
    return {"raw": raw, "final": final, "width": width, "height": height}


def apply_thumbnail(rc: RunCtx, item: dict, landed: dict) -> None:
    project = rc.project()
    image = Image(
        filename=landed["final"]["file"],
        prompt=(item.get("prompt") or project.title or "Thumbnail")[:4000],
        art_style="faceless_thumbnail",
        width=landed["width"], height=landed["height"],
        model=item.get("model"),
        aspect_ratio=project.aspect,
        user_id=rc.user_id,
    )
    rc.db.add(image)
    rc.db.flush()
    item["result"] = {"image_id": image.id, "file": landed["final"]["file"], "raw_file": landed["raw"]["file"],
                      "text": item.get("text") or ""}


def finish_thumbnails(rc: RunCtx, items: list[dict]) -> None:
    done = [i for i in items if i["status"] == "done" and i.get("result")]
    if not done:
        return
    project = rc.project()
    media.set_json(project, "thumbnails", [{
        "index": i["index"], "image_id": i["result"]["image_id"], "file": i["result"]["file"],
        "raw_file": i["result"]["raw_file"], "text": i["result"]["text"], "run_id": rc.run_id,
    } for i in sorted(done, key=lambda i: i["index"])])


def _consent_gone(char: FacelessCharacter) -> bool:
    return consent.consent_status(char) in ("revoked", "missing", "outdated")


def fetch_sheet(rc: RunCtx, item: dict, result: dict) -> dict:
    char = rc.db.query(FacelessCharacter).filter(FacelessCharacter.id == rc.character_id).first()
    if char is None:
        raise RuntimeError("The character was deleted")
    if _consent_gone(char):
        return {}  # revoked while fal was working: the result is not kept
    file = _first_file(result, "images")
    content = media.run_async(media.download(file["url"], media.RESULT_IMAGE_MAX_BYTES))
    media.check_result_kind(content, "image")
    ext = media.ext_from_result(file, ".png")
    # A real person's sheet is private like the photos it was made from.
    stored = media.run_async(media.store_character_bytes(
        char, content, prefix="fl_sheet", ext=ext, content_type=media.content_type_for(ext)))
    rc.written.append(stored)
    width, height = media.image_size(content)
    return {"stored": stored, "width": width, "height": height}


def apply_sheet(rc: RunCtx, item: dict, landed: dict) -> None:
    if not landed:
        item["result"] = {"discarded": "consent revoked"}
        return
    char = rc.character()
    stored = landed["stored"]
    if _consent_gone(char):
        rc.replaced(stored)
        item["result"] = {"discarded": "consent revoked"}
        return
    entries = list(char.media or [])
    entries.append(media.media_entry(stored, kind="image", role="sheet", width=landed["width"],
                                     height=landed["height"]))
    media.set_json(char, "media", entries)
    item["result"] = {"file": stored["file"]}


FETCHERS = {
    "still": fetch_still,
    "clip": fetch_clip,
    "voice": fetch_voice,
    "music": fetch_music,
    "thumbnail": fetch_thumbnail,
    "sheet": fetch_sheet,
}

APPLIERS = {
    "still": apply_still,
    "clip": apply_clip,
    "voice": apply_voice,
    "music": apply_music,
    "thumbnail": apply_thumbnail,
    "sheet": apply_sheet,
}

FINALIZERS = {
    "music": finish_music,
    "thumbnails": finish_thumbnails,
}


# ---------------------------------------------------------------------------
# Thumbnail headline (drawn by the app, not by the image model)
# ---------------------------------------------------------------------------

def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_headline(content: bytes, text: str, accent: str = "#FFD166") -> bytes:
    """The image with a bold headline in its clean area, as PNG."""
    from PIL import Image as PILImage, ImageDraw

    from app.render.fonts import font_for

    with PILImage.open(io.BytesIO(content)) as src:
        img = src.convert("RGB")
    text = " ".join((text or "").split()).upper()
    if not text:
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()
    w, h = img.size
    landscape = w >= h
    box_w = int(w * (0.42 if landscape else 0.86))
    x0 = int(w * 0.05)
    y0 = int(h * (0.12 if landscape else 0.08))
    max_h = int(h * (0.76 if landscape else 0.3))

    overlay = PILImage.new("RGBA", img.size, (0, 0, 0, 0))
    shade = ImageDraw.Draw(overlay)
    steps = 24
    span = int(w * 0.55) if landscape else int(h * 0.42)
    for k in range(steps):
        alpha = int(150 * (1 - k / steps))
        if landscape:
            shade.rectangle([k * span // steps, 0, (k + 1) * span // steps, h], fill=(4, 6, 10, alpha))
        else:
            shade.rectangle([0, k * span // steps, w, (k + 1) * span // steps], fill=(4, 6, 10, alpha))
    img = PILImage.alpha_composite(img.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(img)

    size = int(h * (0.2 if landscape else 0.1))
    while True:
        font = font_for("Anton", 400, size, text)
        lines = _wrap(draw, text, font, box_w)
        line_h = int(size * 1.08)
        if (len(lines) <= 3 and line_h * len(lines) <= max_h) or size <= 24:
            break
        size = int(size * 0.9)
    stroke = max(2, size // 14)
    y = y0
    for n, line in enumerate(lines):
        fill = accent if n == len(lines) - 1 and len(lines) > 1 else "#FFFFFF"
        draw.text((x0, y), line, font=font, fill=fill, stroke_width=stroke, stroke_fill="#000000")
        y += line_h
    out = io.BytesIO()
    img.convert("RGB").save(out, format="PNG")
    return out.getvalue()
