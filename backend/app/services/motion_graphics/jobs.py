"""Jobs: quote on start, advance in the scheduler, record what landed.

Lifecycle (mg_job):

  POST /jobs          plan_job() builds the items and their estimate in USD; the
                      job is stored with its items and status "queued". An
                      idempotency key returns the existing job instead of starting
                      another; one active job per project.
  tick (5 s)          the scheduler reads each queued or running job, submits
                      pending fal items (voice, music, images), polls submitted
                      ones and downloads results with no write held. Only then does
                      it take the write lock, re-check the job and apply. Each fal
                      or Sarvam item that lands is recorded in usage_log (a failed
                      one is not billed). When every fal item is terminal: if
                      anything failed the render items are skipped and the job
                      ends partial or failed; otherwise a render job moves to
                      "render_queued".
  render tick (10 s)  takes the system-wide render slot (render_queue.py), claims
                      the oldest render_queued job and renders ONE pending aspect,
                      then releases the slot; the next tick renders the next
                      aspect. A render left "rendering" by a dead process is
                      requeued once, then failed.

Item statuses: pending, submitted, rendering, done, failed, cancelled.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.database import apply_row_lock
from app.models.motion_graphics import MGJob, MGProject
from app.services.job_state import lock_skip
from app.services.usage import record_usage

from . import activity, media, pricing
from . import project as proj
from .errors import Conflict, InvalidRequest

logger = logging.getLogger(__name__)

VIDEO_TYPE = "motion_graphics"
VIDEO_MODEL = "motion-graphics-studio"
ACTIVE = ("queued", "running", "render_queued", "rendering")
FAL_KINDS = ("voice", "music", "image")
MAX_POLL_ERRORS = 4
RENDER_MAX_ATTEMPTS = 2
JOBS_PER_HOUR = 30
FAL_TIMEOUT = timedelta(minutes=30)


class RenderProblem(RuntimeError):
    """A render failure whose message is written for the user (shown on the
    job). Any other exception is logged and shown as a generic failure, so
    internal paths and tool output never reach the client."""


def set_json(obj, attr: str, value) -> None:
    setattr(obj, attr, value)
    flag_modified(obj, attr)


def _iso(v):
    return v.isoformat() if v else None


def job_view(job: MGJob) -> dict:
    return {
        "id": job.id, "project_id": job.project_id, "kind": job.kind, "status": job.status,
        "progress": int(job.progress or 0), "quote": job.quote or {}, "estimated_usd": float(job.estimated_usd or 0),
        "cancel_requested": bool(job.cancel_requested),
        "error": job.error, "idempotency_key": job.idempotency_key,
        "items": [{"id": i.get("id"), "kind": i.get("kind"), "status": i.get("status"), "label": i.get("label"),
                   "aspect": i.get("aspect"), "estimated_usd": i.get("estimated_usd"), "error": i.get("error"),
                   "video_id": (i.get("result") or {}).get("video_id")} for i in job.items or []],
        "created_at": _iso(job.created_at), "started_at": _iso(job.started_at), "completed_at": _iso(job.completed_at),
    }


# ---------------------------------------------------------------------------
# Starting a job (web worker)
# ---------------------------------------------------------------------------

def start_job(db: Session, user_id: int, project: MGProject, kind: str, key: str | None):
    key = (key or "").strip() or None
    if key and len(key) > 80:
        raise InvalidRequest("Idempotency key must be at most 80 characters.")
    if key:
        existing = db.query(MGJob).filter(MGJob.user_id == user_id, MGJob.idempotency_key == key).first()
        if existing is not None:
            if existing.project_id != project.id or existing.kind != kind:
                raise Conflict("This idempotency key was already used for a different request.", code="key_reused")
            return existing, False
    active = db.query(MGJob).filter(MGJob.project_id == project.id, MGJob.status.in_(ACTIVE)).first()
    if active is not None:
        raise Conflict("A job is already running for this project.", code="job_active", extra={"job_id": active.id})
    activity.check_rate(db, user_id, "job", JOBS_PER_HOUR, label="jobs")
    plan = pricing.plan_job(db, project, kind)
    key = key or f"auto-{uuid.uuid4().hex}"
    items = []
    for it in plan["items"]:
        items.append({**it, "id": uuid.uuid4().hex[:10], "status": "pending", "request_id": None, "error": None,
                      "errors": 0})
    estimated = float(plan["estimated_usd"])
    try:
        # The one-active-job rule is re-checked here under the write lock: two
        # requests for the same project serialise on it, and the second sees the
        # first's committed job.
        locked = apply_row_lock(db.query(MGProject).filter(MGProject.id == project.id)).first()
        if locked is None:
            raise InvalidRequest("The project was deleted.")
        dup = db.query(MGJob).filter(MGJob.user_id == user_id, MGJob.idempotency_key == key).first()
        if dup is not None:
            # Same key raced in from a double click or a retry: answer with the
            # job that exists.
            db.rollback()
            if dup.project_id != project.id or dup.kind != kind:
                raise Conflict("This idempotency key was already used for a different request.", code="key_reused")
            return dup, False
        running = db.query(MGJob).filter(MGJob.project_id == project.id, MGJob.status.in_(ACTIVE)).first()
        if running is not None:
            raise Conflict("A job is already running for this project.", code="job_active",
                           extra={"job_id": running.id})
        job = MGJob(user_id=user_id, project_id=project.id, kind=kind, status="queued", idempotency_key=key,
                    options={}, quote=pricing.quote_view(plan), items=items, progress=0, estimated_usd=estimated)
        db.add(job)
        db.flush()
        if kind == "render":
            locked.status = "producing"
        activity.log_activity(db, user_id, "job", project_id=project.id, job_id=job.id, job_kind=kind,
                              estimated_usd=estimated)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(MGJob).filter(MGJob.user_id == user_id, MGJob.idempotency_key == key).first()
        if existing is not None:
            return existing, False
        raise
    except Exception:
        db.rollback()
        raise
    db.refresh(job)
    logger.info(f"Motion graphics {kind} job {job.id} queued: {len(items)} item(s), estimated ${estimated:g}")
    return job, True


def cancel_job(db: Session, job: MGJob) -> MGJob:
    locked = apply_row_lock(db.query(MGJob).filter(MGJob.id == job.id).populate_existing()).first()
    if locked.status in ACTIVE:
        locked.cancel_requested = True
        db.commit()
    db.refresh(locked)
    return locked


# ---------------------------------------------------------------------------
# Closing
# ---------------------------------------------------------------------------

def _finish(db: Session, job: MGJob, items: list[dict]) -> None:
    done = [i for i in items if i["status"] == "done"]
    if job.cancel_requested and len(done) < len(items):
        job.status = "cancelled"
    elif len(done) == len(items):
        job.status = "completed"
    elif done:
        job.status = "partial"
    else:
        job.status = "failed"
    failed = [i for i in items if i["status"] in ("failed", "cancelled")]
    if failed and not job.error:
        job.error = next((i.get("error") for i in failed if i.get("error")), None) or (
            "Cancelled" if job.cancel_requested else "Some steps failed")
    job.progress = 100
    job.completed_at = datetime.utcnow()
    project = db.query(MGProject).filter(MGProject.id == job.project_id).first()
    if project is not None and job.kind == "render":
        project.status = "rendered" if (project.outputs or {}) else "draft"


# ---------------------------------------------------------------------------
# fal items (scheduler)
# ---------------------------------------------------------------------------

def tick(db: Session) -> int:
    ids = [j.id for j in db.query(MGJob.id).filter(MGJob.status.in_(("queued", "running"))).order_by(MGJob.id).limit(20)]
    for jid in ids:
        try:
            advance(db, jid)
        except Exception as exc:
            db.rollback()
            logger.exception(f"Motion graphics job {jid} tick failed: {exc}")
    return len(ids)


def advance(db: Session, job_id: int) -> None:
    job = lock_skip(db.query(MGJob).filter(MGJob.id == job_id, MGJob.status.in_(("queued", "running")))
                    ).populate_existing().first()
    if job is None:
        db.rollback()
        return
    items = [dict(i) for i in job.items or []]
    now = datetime.utcnow()
    user_id = job.user_id
    if job.cancel_requested:
        for i in items:
            if i["status"] == "pending":
                i["status"] = "cancelled"
                i["error"] = "Cancelled"
    from app.services.faceless import media as fl_media

    trash = []
    fetched = []  # (item, stored result) downloaded this tick, applied to the project below
    # Nothing is written and no lock is held in this loop: it talks to the providers.
    for i in items:
        if i["kind"] not in FAL_KINDS:
            continue
        if i.get("provider") == "sarvam":
            # Not on fal: synthesised here in one go (a second or so per scene).
            if i["status"] == "pending" and not job.cancel_requested:
                try:
                    fetched.append((i, fetch_sarvam_voice(db, job, i)))
                except Exception as exc:
                    i["errors"] = int(i.get("errors") or 0) + 1
                    logger.warning(f"Motion graphics job {job.id}: Sarvam voice failed: {exc}")
                    if i["errors"] >= SARVAM_MAX_ERRORS:
                        i["status"] = "failed"
                        i["error"] = "The Sarvam voice could not be generated."
            continue
        if i["status"] == "pending":
            try:
                i["request_id"] = fl_media.fal_submit(db, i["endpoint"], i["arguments"])
                i["status"] = "submitted"
                i["submitted_at"] = now.isoformat()
            except Exception as exc:
                i["errors"] = int(i.get("errors") or 0) + 1
                logger.warning(f"Motion graphics job {job.id}: submit {i['kind']} failed: {exc}")
                if i["errors"] >= MAX_POLL_ERRORS:
                    i["status"] = "failed"
                    i["error"] = f"The provider rejected the {i['kind']} request."
        elif i["status"] == "submitted":
            try:
                st = fl_media.fal_status(db, i["endpoint"], i["request_id"])
                if st == "completed":
                    result = fl_media.fal_result(db, i["endpoint"], i["request_id"])
                    fetched.append((i, fetch_result(job, i, result)))
                elif datetime.fromisoformat(i.get("submitted_at") or now.isoformat()) < now - FAL_TIMEOUT:
                    i["status"] = "failed"
                    i["error"] = f"The {i['kind']} request timed out."
            except Exception as exc:
                i["errors"] = int(i.get("errors") or 0) + 1
                logger.warning(f"Motion graphics job {job.id}: {i['kind']} poll or store failed: {exc}")
                if i["errors"] >= MAX_POLL_ERRORS:
                    i["status"] = "failed"
                    i["error"] = f"The {i['kind']} step failed at the provider."
    # Downloads and analysis are done; only now take the write lock (web requests
    # such as autosave wait on it), re-check the job, apply, and commit below.
    job = apply_row_lock(db.query(MGJob).filter(MGJob.id == job_id)).first()
    if job is None or job.status not in ("queued", "running"):
        # Closed while the providers were talking: this tick's results are dropped.
        db.rollback()
        _discard([(f["stored"], user_id) for _, f in fetched])
        return
    if job.status == "queued":
        job.status = "running"
        job.started_at = job.started_at or now
    if fetched:
        if apply_results(db, job, fetched, trash):
            for i, f in fetched:
                i["status"] = "done"
                i["result"] = {"file": f["stored"]["file"]}
        else:
            for i, f in fetched:
                i["status"] = "failed"
                i["error"] = "The project was deleted."
                trash.append((f["stored"], job.user_id))
    fal = [i for i in items if i["kind"] in FAL_KINDS]
    renders = [i for i in items if i["kind"] == "render"]
    terminal = all(i["status"] in ("done", "failed", "cancelled") for i in fal)
    done_n = sum(1 for i in fal if i["status"] == "done")
    job.progress = int(60 * done_n / max(1, len(fal))) if renders else int(100 * done_n / max(1, len(fal)))
    if terminal:
        bad = [i for i in fal if i["status"] in ("failed", "cancelled")]
        if bad or job.cancel_requested:
            for r in renders:
                if r["status"] == "pending":
                    r["status"] = "cancelled"
                    r["error"] = "Skipped because an earlier step failed." if bad else "Cancelled"
            _finish(db, job, items)
        elif renders:
            job.status = "render_queued"
        else:
            _finish(db, job, items)
    set_json(job, "items", items)
    job.heartbeat_at = now
    db.commit()
    for asset, uid in trash:
        try:
            media.run_async(media.delete_stored(asset, uid))
        except Exception:
            pass


def _first_file(result: dict, key: str) -> dict:
    value = (result or {}).get(key)
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, dict) or not value.get("url"):
        raise ValueError(f"The provider returned no {key}")
    return value


def _download_store(file: dict, *, user_id: int, prefix: str, default_ext: str, max_bytes: int):
    from app.services.faceless import media as fl_media

    content = media.run_async(fl_media.download(file["url"], max_bytes))
    ext = fl_media.ext_from_result(file, default_ext)
    stored = media.run_async(media.store_bytes(content, user_id=user_id, storage="uploads", prefix=prefix, ext=ext,
                                               content_type=fl_media.content_type_for(ext)))
    return content, stored, ext


def _analyze_bytes(content: bytes, ext: str) -> dict:
    from .audio import analyze

    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as fh:
            fh.write(content)
            path = fh.name
        return analyze(path)
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def fetch_result(job: MGJob, item: dict, result: dict) -> dict:
    """Download, store and analyse a provider result (no project lock held).
    Returns {key, entry, stored} for apply_results()."""
    from app.services.faceless.scenes import words_from_timestamps

    user_id = job.user_id
    if item["kind"] == "voice":
        content, stored, ext = _download_store(_first_file(result, "audio"), user_id=user_id, prefix="mg_voice",
                                               default_ext=".mp3", max_bytes=80 * 1024 * 1024)
        info = _analyze_bytes(content, ext)
        words = words_from_timestamps(result.get("timestamps"), item.get("text") or "", info["duration"])
        entry = {"file": stored["file"], "storage": stored["storage"], "duration": info["duration"], "words": words,
                 "hash": item.get("hash"), "chars": item.get("chars"), "voice_id": item.get("voice"),
                 "amps": info.get("amps"), "job_id": job.id, "created_at": datetime.utcnow().isoformat(),
                 "ai_generated": True}
        key = "voice"
    elif item["kind"] == "music":
        content, stored, ext = _download_store(_first_file(result, "audio"), user_id=user_id, prefix="mg_music",
                                               default_ext=".mp3", max_bytes=80 * 1024 * 1024)
        info = _analyze_bytes(content, ext)
        beats = {k: info.get(k) for k in ("bpm", "beats", "confidence", "reliable")}
        entry = {"file": stored["file"], "storage": stored["storage"], "duration": info["duration"],
                 "requested": item.get("seconds"), "hash": item.get("hash"), "mood": item.get("mood"), "beats": beats,
                 "job_id": job.id, "created_at": datetime.utcnow().isoformat(),
                 # Generation receipt (rights record): what, with which provider, for whom, when.
                 "rights": {"provider": "ElevenLabs Music via fal.ai", "endpoint": item.get("endpoint"),
                            "request_id": item.get("request_id"), "prompt": item["arguments"].get("prompt"),
                            "length_ms": item["arguments"].get("music_length_ms"), "instrumental": True,
                            "user_id": user_id, "generated_at": datetime.utcnow().isoformat(), "ai_generated": True,
                            "note": "AI-generated music made for this account. Keep this receipt with the video."}}
        key = "music"
    else:  # image
        content, stored, ext = _download_store(_first_file(result, "images"), user_id=user_id, prefix="mg_ai",
                                               default_ext=".png", max_bytes=40 * 1024 * 1024)
        from PIL import Image as PILImage
        import io

        with PILImage.open(io.BytesIO(content)) as im:
            w, h = im.size
        entry = media.upload_entry(stored, kind="image", name="AI image", width=w, height=h, ai_generated=True,
                                   prompt=item.get("prompt"), job_id=job.id)
        key = "image"
    return {"key": key, "entry": entry, "stored": stored}


SARVAM_MAX_ERRORS = 3


def fetch_sarvam_voice(db: Session, job: MGJob, item: dict) -> dict:
    """Synthesise a Sarvam voiceover scene by scene, join and store it, with
    word times placed from the audio's own pauses (sarvam_voice.py). Returns
    the same {key, entry, stored} as fetch_result."""
    from app.services import sarvam_tts
    from app.services.assets import sarvam_key

    from .sarvam_voice import join

    key = sarvam_key(db)
    if not key:
        raise RuntimeError("no Sarvam key")
    parts = [p for p in item.get("parts") or [] if p.strip()]
    clips = [media.run_async(sarvam_tts.synthesize(key, sarvam_tts.arguments(text, item["voice"], item.get("pace"))))
             for text in parts]
    content, words, duration = join(clips, parts)
    stored = media.run_async(media.store_bytes(content, user_id=job.user_id, storage="uploads", prefix="mg_voice",
                                               ext=".mp3", content_type="audio/mpeg"))
    info = _analyze_bytes(content, ".mp3")
    entry = {"file": stored["file"], "storage": stored["storage"], "duration": info.get("duration") or duration,
             "words": words, "hash": item.get("hash"), "chars": item.get("chars"), "voice_id": item.get("voice"),
             "provider": "sarvam", "word_times": "estimated", "amps": info.get("amps"), "job_id": job.id,
             "created_at": datetime.utcnow().isoformat(), "ai_generated": True}
    return {"key": "voice", "entry": entry, "stored": stored}


def apply_results(db: Session, job: MGJob, fetched: list, trash: list) -> bool:
    """Write fetched results into the project under the write lock (a short
    critical section: nothing here touches the network), and record their spending
    in the same transaction. False when the project is gone."""
    db.flush()
    project = apply_row_lock(db.query(MGProject).filter(MGProject.id == job.project_id)).first()
    if project is None:
        return False
    assets = dict(project.assets or {})
    spec = dict(project.spec or {})
    spec_changed = False
    by_step = dict(project.usd_by_step or {})
    for item, f in fetched:
        usd = float(item.get("estimated_usd") or 0)
        record_usage(db, feature=VIDEO_TYPE, usd=usd, model=item.get("endpoint"), units=item.get("units"),
                     unit=item.get("unit"), job_type=VIDEO_TYPE, job_id=job.id,
                     detail={"project_id": job.project_id, "kind": item["kind"], "job_kind": job.kind})
        by_step[job.kind] = round(float(by_step.get(job.kind) or 0) + usd, 4)
        key, entry = f["key"], f["entry"]
        if key in ("voice", "music"):
            old = assets.get(key)
            assets[key] = entry
            if old and old.get("file"):
                trash.append((old, job.user_id))
        else:
            uploads = dict(assets.get("uploads") or {})
            uploads[entry["id"]] = entry
            assets["uploads"] = uploads
            scenes = [dict(s) for s in spec.get("scenes") or []]
            for s in scenes:
                if s.get("id") == item.get("scene_id"):
                    slots = dict(s.get("slots") or {})
                    slots[item.get("slot") or "image"] = {"upload_id": entry["id"], "ai": True}
                    s["slots"] = slots
            spec["scenes"] = scenes
            spec_changed = True
    if spec_changed:
        set_json(project, "spec", spec)
        project.spec_version = int(project.spec_version or 1) + 1
    set_json(project, "assets", assets)
    set_json(project, "usd_by_step", by_step)
    return True


# ---------------------------------------------------------------------------
# Renders (scheduler, one at a time system wide)
# ---------------------------------------------------------------------------

def work_root() -> str | None:
    """Disk-backed scratch space (XDG_CACHE_HOME, set in app/config.py); None falls
    back to temp."""
    base = os.environ.get("XDG_CACHE_HOME")
    if not base:
        return None
    root = os.path.join(base, "motion-graphics-render")
    try:
        os.makedirs(root, exist_ok=True)
        return root if os.access(root, os.W_OK) else None
    except OSError:
        return None


def _sweep_workdirs() -> None:
    root = work_root() or tempfile.gettempdir()
    try:
        names = [n for n in os.listdir(root) if n.startswith("mg_render_")]
    except OSError:
        return
    for n in names:
        shutil.rmtree(os.path.join(root, n), ignore_errors=True)


def render_tick(db: Session) -> int | None:
    """Claim and render at most one aspect of one job under the shared slot."""
    from app.services.render_queue import render_slot

    with render_slot("motion_graphics") as acquired:
        if not acquired:
            return None
        _sweep_workdirs()
        # Holding the slot proves an item still "rendering" is orphaned.
        orphans = lock_skip(db.query(MGJob).filter(MGJob.status == "rendering")).populate_existing().all()
        for job in orphans:
            items = [dict(i) for i in job.items or []]
            for i in items:
                if i["kind"] == "render" and i["status"] == "rendering":
                    if int(job.attempts or 0) >= RENDER_MAX_ATTEMPTS:
                        i["status"] = "failed"
                        i["error"] = "The render stopped responding."
                    else:
                        logger.warning(f"Motion graphics render job {job.id} was orphaned; requeued")
                        i["status"] = "pending"
            set_json(job, "items", items)
            job.status = "render_queued"
        db.commit()
        job = lock_skip(db.query(MGJob).filter(MGJob.status == "render_queued").order_by(MGJob.created_at)).first()
        if job is None:
            db.rollback()
            return None
        items = [dict(i) for i in job.items or []]
        if job.cancel_requested:
            for i in items:
                if i["kind"] == "render" and i["status"] == "pending":
                    i["status"] = "cancelled"
                    i["error"] = "Cancelled"
            set_json(job, "items", items)
            _finish(db, job, items)
            db.commit()
            return None
        pending = [i for i in items if i["kind"] == "render" and i["status"] == "pending"]
        if not pending:
            _finish(db, job, items)
            set_json(job, "items", items)
            db.commit()
            return None
        target = pending[0]
        target["status"] = "rendering"
        job.status = "rendering"
        job.attempts = int(job.attempts or 0) + 1
        job.heartbeat_at = datetime.utcnow()
        set_json(job, "items", items)
        db.commit()
        render_item(db, job.id, target["id"])
        return job.id


def _update_item(db: Session, job_id: int, item_id: str, **fields) -> tuple[MGJob, list[dict], dict]:
    job = apply_row_lock(db.query(MGJob).filter(MGJob.id == job_id).populate_existing()).first()
    items = [dict(i) for i in job.items or []]
    it = next(i for i in items if i["id"] == item_id)
    it["_was"] = it.get("status")
    it.update(fields)
    return job, items, it


def _closed_meanwhile(it: dict) -> bool:
    """True when someone else (a force close) settled this item while the render
    ran, so the result is dropped."""
    return it.pop("_was", "rendering") != "rendering"


def is_stuck(job: MGJob, now: datetime, after: timedelta) -> bool:
    if job.status not in ACTIVE:
        return False
    last = job.heartbeat_at or job.started_at or job.created_at
    return bool(last and now - last > after)


def force_close(db: Session, job_id: int, reason: str, stuck_after: timedelta) -> str:
    """Close an active job the scheduler stopped advancing: every unfinished item
    is cancelled.

    A job "rendering" is worked on without a row lock, so the render slot is
    taken first: holding it proves no render process is still on it (and
    keeps render_tick's orphan sweep out). Returns "closed", "busy" (a render
    holds the slot), "moving" (it progressed since it was listed) or "gone"
    (ended, or the scheduler holds the row)."""
    from contextlib import ExitStack

    from app.services.render_queue import render_slot

    status = db.query(MGJob.status).filter(MGJob.id == job_id).scalar()
    db.rollback()
    with ExitStack() as stack:
        holds_slot = False
        if status == "rendering":
            holds_slot = stack.enter_context(render_slot("force-close"))
            if not holds_slot:
                return "busy"
        job = lock_skip(db.query(MGJob).filter(MGJob.id == job_id, MGJob.status.in_(ACTIVE))).populate_existing().first()
        if job is None:
            db.rollback()
            return "gone"
        if not is_stuck(job, datetime.utcnow(), stuck_after) or (job.status == "rendering" and not holds_slot):
            db.rollback()
            return "moving"
        job.cancel_requested = True
        items = [dict(i) for i in job.items or []]
        for i in items:
            if i.get("status") not in ("done", "failed", "cancelled"):
                i["status"] = "cancelled"
                i["error"] = reason[:200]
        set_json(job, "items", items)
        _finish(db, job, items)
        job.error = job.error or reason[:300]
        db.commit()
    logger.info(f"Motion graphics job {job_id} force closed: {reason}")
    return "closed"


def render_item(db: Session, job_id: int, item_id: str) -> None:
    from app.models.content import Video
    from app.render import RenderCancelled, render_timeline

    from . import build as mg_build
    from .audio import sfx_paths

    job = db.query(MGJob).filter(MGJob.id == job_id).first()
    item = next(i for i in job.items if i["id"] == item_id)
    aspect = item["aspect"]
    project = db.query(MGProject).filter(MGProject.id == job.project_id).first()
    renders = [i for i in job.items if i["kind"] == "render"]
    index = [i["id"] for i in renders].index(item_id)
    base_p = 60 if any(i["kind"] in FAL_KINDS for i in job.items) else 0
    workdir = tempfile.mkdtemp(prefix=f"mg_render_{job_id}_", dir=work_root())
    state = {"last": 0.0, "checked": 0.0, "cancel": False}
    written: list = []  # stored files to remove if the render does not land

    def check_cancel() -> bool:
        flag = db.query(MGJob.cancel_requested).filter(MGJob.id == job_id).scalar()
        db.rollback()
        return bool(flag)

    def progress(f: float) -> None:
        now = time.monotonic()
        if now - state["last"] < 2.0 and f < 1.0:
            return
        state["last"] = now
        try:
            span = (100 - base_p) / max(1, len(renders))
            db.query(MGJob).filter(MGJob.id == job_id).update(
                {MGJob.progress: int(base_p + span * (index + max(0.0, min(1.0, f)) * 0.97)),
                 MGJob.heartbeat_at: datetime.utcnow()}, synchronize_session=False)
            db.commit()
            state["cancel"] = check_cancel()
        except Exception:
            db.rollback()

    def cancelled() -> bool:
        now = time.monotonic()
        if now - state["checked"] >= 2.0:
            state["checked"] = now
            try:
                state["cancel"] = check_cancel()
            except Exception:
                db.rollback()
        return state["cancel"]

    try:
        if project is None:
            raise RenderProblem("The project was deleted")
        spec = proj.spec_of(project)
        src = os.path.join(workdir, "src")
        os.makedirs(src, exist_ok=True)
        files, logo = media.local_files(project, spec, folder=src)
        assets = project.assets or {}
        paths = {}
        if spec.template_id == "audiogram":
            ca = proj.clip_audio_info(project, spec)
            if ca and ca.get("file"):
                paths["clip"] = media.local_copy(ca, project.user_id, src)
                if not paths["clip"]:
                    raise RenderProblem("The audio file is missing")
        elif proj.voice_needed(project, spec):
            if not proj.voice_current(project, spec):
                raise RenderProblem("The voiceover is out of date; render again to regenerate it")
            paths["voice"] = media.local_copy(assets["voice"], project.user_id, src)
            if not paths["voice"]:
                raise RenderProblem("The stored voiceover file is missing")
        if proj.music_needed(project) and (assets.get("music") or {}).get("file"):
            paths["music"] = media.local_copy(assets["music"], project.user_id, src)
            if not paths["music"]:
                raise RenderProblem("The stored music file is missing")
        kw = proj.build_kwargs(project, spec, files=files, logo_path=logo, paths=paths)
        if spec.template_id == "audiogram" and paths.get("clip"):
            kw["clip_audio"]["path"] = paths["clip"]
        tl, plan = mg_build.build(spec, aspect=aspect, sfx=sfx_paths() if spec.options.sfx else None, **kw)
        # Hard bound on render time: the quote checked the estimated length,
        # but a measured voiceover can run longer than the estimate.
        top = proj.MAX_SECONDS.get(project.aspect, 180) * 1.1 + 5
        if float(plan["total"]) > top:
            raise RenderProblem(f"The video would run {plan['total']:.0f} s, over the {top:.0f} s limit; "
                               "shorten the voiceover or the scenes")
        out_path = os.path.join(workdir, f"out_{uuid.uuid4().hex}.mp4")
        result = render_timeline(tl, out_path, workdir=os.path.join(workdir, "engine"), progress=progress,
                                 cancel=cancelled)
        with open(result.path, "rb") as fh:
            content = fh.read()
        from app.services.faceless import media as fl_media

        thumb = fl_media.video_thumbnail(result.path, at_seconds=min(2.5, max(0.2, result.duration * 0.4)))
        stored = media.run_async(media.store_bytes(content, user_id=project.user_id, storage="videos", prefix="mg",
                                                   ext=".mp4", content_type="video/mp4"))
        written.append((stored, project.user_id))
        thumb_stored = None
        if thumb:
            thumb_stored = media.run_async(media.store_bytes(thumb, user_id=project.user_id, storage="thumbnails",
                                                             prefix="mg_thumb", ext=".jpg", content_type="image/jpeg"))
            written.append((thumb_stored, project.user_id))
        job, items, it = _update_item(db, job_id, item_id, status="done")
        if _closed_meanwhile(it):
            # Force closed while rendering: drop it.
            db.rollback()
            _discard(written)
            logger.warning(f"Motion graphics job {job_id}: {aspect} finished after the job was closed; discarded")
            return
        project = apply_row_lock(db.query(MGProject).filter(MGProject.id == job.project_id).populate_existing()).first()
        if project is None:
            raise RenderProblem("The project was deleted during the render")
        transcript = " ".join(w["text"] for w in ((project.assets or {}).get("voice") or {}).get("words") or [])
        video = Video(filename=stored["file"], thumbnail_filename=thumb_stored["file"] if thumb_stored else None,
                      prompt=(project.title or "")[:2000], transcript=transcript[:20000] or None,
                      video_type=VIDEO_TYPE, has_subtitles=1 if plan.get("captions") else 0,
                      duration_seconds=round(float(result.duration), 3), width=result.width, height=result.height,
                      fps=30, model=VIDEO_MODEL, file_size_bytes=int(result.size_bytes), user_id=project.user_id)
        db.add(video)
        db.flush()
        it["result"] = {"video_id": video.id}
        outputs = dict(project.outputs or {})
        outputs[aspect] = {"video_id": video.id, "duration": video.duration_seconds, "width": video.width,
                           "height": video.height, "job_id": job.id, "rendered_at": datetime.utcnow().isoformat(),
                           "spec_version": project.spec_version}
        set_json(project, "outputs", outputs)
        project.status = "rendered"
        set_json(job, "items", items)
        remaining = [i for i in items if i["kind"] == "render" and i["status"] == "pending"]
        if remaining:
            job.status = "render_queued"
            job.attempts = 0
        else:
            _finish(db, job, items)
        activity.log_activity(db, job.user_id, "render", project_id=project.id, job_id=job.id, video_id=video.id,
                              aspect=aspect)
        db.commit()
        written.clear()  # landed: the gallery row owns the files now
        logger.info(f"Motion graphics job {job_id} rendered {aspect}: video {video.id}, {result.duration:.1f}s")
        if not remaining:
            _notify(db, job.user_id, "completed", video.id)
    except RenderCancelled:
        db.rollback()
        _discard(written)
        job, items, it = _update_item(db, job_id, item_id, status="cancelled", error="Cancelled")
        if _closed_meanwhile(it):
            db.rollback()
            return
        for i in items:
            if i["kind"] == "render" and i["status"] == "pending":
                i["status"] = "cancelled"
        set_json(job, "items", items)
        _finish(db, job, items)
        db.commit()
    except Exception as exc:
        db.rollback()
        _discard(written)
        logger.exception(f"Motion graphics render {job_id}/{aspect} failed: {exc}")
        shown = str(exc)[:300] if isinstance(exc, RenderProblem) else "something went wrong on our side. Please render again"
        job, items, it = _update_item(db, job_id, item_id, status="failed",
                                      error=f"The {aspect} render failed: {shown}")
        if _closed_meanwhile(it):
            db.rollback()
            return
        set_json(job, "items", items)
        remaining = [i for i in items if i["kind"] == "render" and i["status"] == "pending"]
        if remaining:
            job.status = "render_queued"
            job.attempts = 0
        else:
            _finish(db, job, items)
        db.commit()
        if not remaining:
            _notify(db, job.user_id, "failed", None, f"The {aspect} render failed: {shown}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _discard(written: list) -> None:
    for asset, uid in written:
        try:
            media.run_async(media.delete_stored(asset, uid))
        except Exception:
            pass
    written.clear()


def _notify(db: Session, user_id: int, status: str, video_id, error: str | None = None) -> None:
    try:
        from app.services.alert_service import send_job_completion_notification

        send_job_completion_notification(db=db, user_id=user_id, job_type="video", status=status,
                                         result_id=video_id, error_message=error)
    except Exception as exc:
        db.rollback()
        logger.warning(f"Motion graphics notification failed: {exc}")
