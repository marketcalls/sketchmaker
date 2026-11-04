"""Long-form script drafts as a step run executed by the scheduler.

A long-form draft is an outline call plus chunked scene calls (about six LLM calls for
a 12 minute script) and holds a web request far too long. POST /projects/{id}/script
therefore queues a "script" step run for long-form projects (see scripts.is_long_form);
a dedicated scheduler tick (scheduler.run_script_tick) drafts one script at a time, on
its own thread, so media steps and renders keep moving.

The run has no fal cost (its tokens are logged by litellm_client) and goes through the
same views as the other steps: queued, running, completed or failed, with the error
message and code on its single item. No write is held during the LLM calls.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import apply_row_lock
from app.models.faceless import FacelessProject, FacelessSeries, FacelessStepRun
from app.services.job_state import update_job_if

from . import consent, media, scripts
from .errors import Conflict, FacelessError
from .orchestrator import ACTIVE

logger = logging.getLogger(__name__)

STEP = "script"
# A draft interrupted by a restart runs once more, then fails.
MAX_ATTEMPTS = 2


def start_script_run(db: Session, user_id: int, project: FacelessProject, idea: str | None,
                     idempotency_key: str | None) -> tuple[FacelessStepRun, bool]:
    """Queue a draft. The caller has already applied the draft rate limit."""
    key = (idempotency_key or "").strip()[:80] or f"auto-{uuid.uuid4().hex}"
    existing = db.query(FacelessStepRun).filter(
        FacelessStepRun.user_id == user_id, FacelessStepRun.idempotency_key == key).first()
    if existing is not None:
        if existing.project_id != project.id or existing.step != STEP:
            raise Conflict("This idempotency key was already used for a different request.", code="key_reused")
        return existing, False
    active = db.query(FacelessStepRun).filter(
        FacelessStepRun.project_id == project.id, FacelessStepRun.step == STEP,
        FacelessStepRun.status.in_(ACTIVE)).first()
    if active is not None:
        raise Conflict("A script is already being drafted for this project.", code="step_active",
                       extra={"run_id": active.id})
    run = FacelessStepRun(
        user_id=user_id, project_id=project.id,
        step=STEP, status="queued", idempotency_key=key, scene_ids=[],
        options={"idea": idea} if idea is not None else {},
        quote={"step": STEP, "usd": 0.0, "breakdown": [],
               "assumptions": ["Script drafts use the language model set in Settings; its tokens are on the Usage page."],
               "scene_ids": [], "characters": []},
        items=[{"id": "i1", "kind": "script", "status": "pending", "usd": 0.0, "error": None}],
        progress=0, estimated_usd=0.0, usd_spent=0.0,
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(FacelessStepRun).filter(
            FacelessStepRun.user_id == user_id, FacelessStepRun.idempotency_key == key).first()
        if existing is not None:
            return existing, False
        raise
    db.refresh(run)
    return run, True


def _finish(run: FacelessStepRun, status: str, error: str | None = None, code: str | None = None,
            result: dict | None = None) -> None:
    item = dict((run.items or [{}])[0] or {})
    shown = {"completed": "done", "cancelled": "cancelled"}.get(status, "failed")
    item.update({"status": shown, "error": error, "code": code})
    if result:
        item["result"] = result
    media.set_json(run, "items", [item])
    run.status = status
    run.error = error
    run.progress = 100
    run.completed_at = datetime.utcnow()


def release_interrupted(db: Session) -> int:
    """Hand back drafts a stopped process left "running". Ticks do not overlap
    (max_instances=1), so a draft still running here has no worker: the LLM result it
    was waiting for is gone, so it is drafted again once, then failed."""
    orphaned = db.query(FacelessStepRun.id).filter(
        FacelessStepRun.step == STEP, FacelessStepRun.status == "running").first()
    if orphaned is None:
        return 0
    released = 0
    for run in apply_row_lock(db.query(FacelessStepRun).filter(
            FacelessStepRun.step == STEP, FacelessStepRun.status == "running")).all():
        if int(run.attempts or 0) >= MAX_ATTEMPTS:
            _finish(run, "failed", "The draft stopped responding. Please draft again.", "stalled")
        else:
            logger.warning(f"Faceless script run {run.id} was interrupted; drafting it again")
            run.status = "queued"
            released += 1
    db.commit()
    return released


def script_tick(db: Session) -> int | None:
    """Draft at most one queued script. Returns the run id, if any."""
    release_interrupted(db)
    run = db.query(FacelessStepRun).filter(
        FacelessStepRun.step == STEP, FacelessStepRun.status == "queued",
    ).order_by(FacelessStepRun.created_at).first()
    if run is None:
        db.rollback()
        return None
    now = datetime.utcnow()
    run_id = run.id
    if not update_job_if(db, FacelessStepRun, run_id, ("queued",), {
            "status": "running", "started_at": now, "heartbeat_at": now,
            "attempts": int(run.attempts or 0) + 1, "progress": 10}):
        return None
    execute(db, run_id)
    return run_id


def _fresh_run(db: Session, run_id: int) -> FacelessStepRun | None:
    return apply_row_lock(db.query(FacelessStepRun).filter(FacelessStepRun.id == run_id)).first()


def execute(db: Session, run_id: int) -> None:
    run = db.query(FacelessStepRun).filter(FacelessStepRun.id == run_id).first()
    project = db.query(FacelessProject).filter(FacelessProject.id == run.project_id).first() if run else None
    if run is None:
        return
    if project is None:
        run = _fresh_run(db, run_id)
        _finish(run, "failed", "The project was deleted.", "not_found")
        db.commit()
        return
    if run.cancel_requested:  # before the LLM call, which costs tokens
        run = _fresh_run(db, run_id)
        _finish(run, "cancelled", "Cancelled")
        db.commit()
        return
    try:
        if "idea" in (run.options or {}):
            project.idea = run.options["idea"]
            db.commit()
        chars = consent.load_cast(db, project.user_id, project.cast_ids)
        series = db.query(FacelessSeries).filter(FacelessSeries.id == project.series_id).first() \
            if project.series_id else None
        script = media.run_async(scripts.draft(db, project, chars, series))
        db.rollback()
        project = apply_row_lock(db.query(FacelessProject).filter(FacelessProject.id == run.project_id)).first()
        if project is None:
            raise FacelessError("The project was deleted during the draft.", code="not_found")
        run = _fresh_run(db, run_id)
        if run.cancel_requested:  # cancelled during the LLM call: no new version
            _finish(run, "cancelled", "Cancelled")
            db.commit()
            return
        version = scripts.apply_script(db, project, script, "draft", chars)
        _finish(run, "completed", result={"script_version": version, "scenes": len(script.get("scenes") or [])})
        db.commit()
        logger.info(f"Faceless script run {run_id} completed: project {project.id} v{version}")
    except FacelessError as exc:
        db.rollback()
        run = _fresh_run(db, run_id)
        _finish(run, "failed", exc.message, exc.code)
        db.commit()
        logger.warning(f"Faceless script run {run_id} failed: {exc.code}: {exc.message}")
    except Exception as exc:
        db.rollback()
        logger.exception(f"Faceless script run {run_id} failed: {exc}")
        run = _fresh_run(db, run_id)
        _finish(run, "failed", "The draft failed. Please try again.", "internal_error")
        db.commit()
