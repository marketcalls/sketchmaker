"""State changes for fal jobs that several places can finish.

A job is polled by the scheduler and by the status and result routes, so the same
finished job can be picked up twice at once. claim_job makes exactly one of them the
settler: only the caller that gets True may download the result and store it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import errno
import logging
import sys

from fal_client.client import FalClientHTTPError
import httpx
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database import apply_row_lock
from app.models.content import GenerationJob, LipSyncJob, StoryGenerationJob, SubtitleJob, VideoGenerationJob
from app.services.fal_keys import FalKeyMissing
from app.services.url_fetch import HostLookupFailed

logger = logging.getLogger(__name__)

JOB_MODELS = (GenerationJob, VideoGenerationJob, StoryGenerationJob, SubtitleJob, LipSyncJob)

IN_FLIGHT_STATUSES = ("pending", "in_progress", "processing")
# States a finished fal job can be claimed from for download.
CLAIMABLE_STATUSES = ("pending", "in_progress")

# A job older than this is stuck rather than in flight.
IN_FLIGHT_WINDOW = timedelta(hours=6)
# A claim older than this goes back to the poller. Long enough for a large video on a slow
# link, because the original worker may still be running and would settle the job twice.
# Claims from a previous run are released at startup (release_orphaned_claims).
PROCESSING_WINDOW = timedelta(hours=3)
# fal can answer for good with a 5xx when the run itself failed, so these are counted.
# At one attempt per 30-second poll, this is about five minutes.
MAX_SERVER_ERROR_RETRIES = 10

NO_IMAGES_ERROR = "No images came back for this job. Please try generating again."
STUCK_JOB_ERROR = "The provider did not return a result in time."
JOB_HANDED_BACK = "We could not save this result yet. It will retry automatically, so check My Jobs in a minute."

_server_errors: dict[tuple[str, int], int] = {}


def is_temporary_failure(model, job_id: int, exc: BaseException | None) -> bool:
    """Whether retrying can still recover the result of this job.

    The provider has usually done the work and billed for it by now, so failing the job
    over a network drop, an outage or a key the owner has yet to fix would throw paid
    output away. Bounded by expire_stuck_fal_jobs for the uncounted cases, and by
    MAX_SERVER_ERROR_RETRIES for 5xx answers.
    """
    from app.clients.fal_client import is_content_policy_error

    if exc is None or is_content_policy_error(exc):
        return False
    if isinstance(exc, (FalKeyMissing, HostLookupFailed, httpx.TransportError, OperationalError,
                        TimeoutError, ConnectionError)):
        return True
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return True

    status = None
    if isinstance(exc, FalClientHTTPError):
        status = exc.status_code
    elif isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
    if status in (401, 403, 408, 425, 429):
        return True
    if status is not None and status >= 500:
        key = (model.__name__, job_id)
        count = _server_errors.get(key, 0) + 1
        if count > MAX_SERVER_ERROR_RETRIES:
            _server_errors.pop(key, None)
            return False
        _server_errors[key] = count
        return True
    return False


def update_job_if(db: Session, model, job_id: int, from_states, values: dict) -> bool:
    """Apply ``values`` to the job only while its status is one of ``from_states``, in
    one UPDATE, and commit. True when exactly one row changed.

    The WHERE clause is the check and the UPDATE takes the write lock, so two workers
    cannot both pass it. Commits so no lock is held across the provider calls that
    usually follow.
    """
    changed = (
        db.query(model)
        .filter(model.id == job_id, model.status.in_(tuple(from_states)))
        .update(values, synchronize_session=False)
    )
    db.commit()
    return changed == 1


def claim_job(db: Session, model, job_id: int, from_states=CLAIMABLE_STATUSES) -> bool:
    """Atomically move a finished job to "processing" before downloading it. Only the
    caller that gets True may settle the job. A claimed job that then fails must be
    moved to failed (fail_claimed_job), never left in "processing".
    """
    # completed_at holds the claim time while processing (it is overwritten when the
    # job finishes or fails), so the sweeper can tell a crashed claim from a live one.
    return update_job_if(
        db, model, job_id, from_states,
        {"status": "processing", "progress": 75, "completed_at": datetime.utcnow()},
    )


def fail_claimed_job(db: Session, model, job_id: int, error: str) -> bool:
    """Mark a job this caller claimed as failed after its processing broke. Called from an
    except block. True when the job is now failed.

    Rolls back first: the failure may have left half-written rows in the session, and
    none of them may be kept. A temporary failure hands the job back to the poller
    instead, and returns False.
    """
    db.rollback()
    exc = sys.exc_info()[1]
    if is_temporary_failure(model, job_id, exc):
        logger.warning(f"{model.__name__} {job_id}: temporary failure ({type(exc).__name__}), will retry")
        update_job_if(db, model, job_id, ("processing",), {"status": "in_progress", "completed_at": None})
        return False
    return update_job_if(
        db, model, job_id, ("processing",),
        {"status": "failed", "error": error, "completed_at": datetime.utcnow()},
    )


def release_orphaned_claims(db: Session) -> int:
    """Hand every claim back to the poller. For startup only: there is one process, so a
    claim that survived a restart belongs to a worker that no longer exists."""
    released = 0
    for model in JOB_MODELS:
        released += (
            db.query(model)
            .filter(model.status == "processing")
            .update({"status": "in_progress", "completed_at": None}, synchronize_session=False)
        )
    db.commit()
    return released


def lock_job(db: Session, model, job_id: int):
    """Re-read a job under the write lock, with fresh values.

    Status checks call fal first and write the answer afterwards; by then the
    scheduler or a result call may have claimed the job. Writing the stale status back
    would make a claimed job claimable again, so callers re-read here (after the
    provider call, never before it) and write only while the job is still in
    CLAIMABLE_STATUSES. The caller's commit releases the lock.
    """
    return apply_row_lock(db.query(model).filter(model.id == job_id)).first()


def lock_skip(query):
    """The query as is. APScheduler's max_instances=1 already serialises each tick,
    and SQLite has no row locks to skip."""
    return query


def expire_stuck_fal_jobs(db: Session) -> int:
    """Fail fal jobs still pending or in progress after IN_FLIGHT_WINDOW; returns how many.

    A status check that fails transiently leaves the job as it is, so a request fal
    lost would otherwise be polled forever. "processing" jobs are left alone while
    their claim is fresh: their result may be mid-download. A claim older than
    PROCESSING_WINDOW belongs to a worker that died (a restart, an OOM kill): nothing
    of it was committed, so the job goes back to "in_progress" and the poller claims
    and settles it again.
    """
    now = datetime.utcnow()
    stale_claim = now - PROCESSING_WINDOW
    cutoff = now - IN_FLIGHT_WINDOW
    expired = 0
    for model in JOB_MODELS:
        released = (
            db.query(model)
            .filter(model.status == "processing", model.completed_at.isnot(None), model.completed_at < stale_claim)
            .update({"status": "in_progress", "completed_at": None}, synchronize_session=False)
        )
        if released:
            logger.warning(f"Released {released} {model.__name__} row(s) stuck in processing")
        expired += (
            db.query(model)
            .filter(model.status.in_(CLAIMABLE_STATUSES), model.created_at < cutoff)
            .update(
                {"status": "failed", "error": STUCK_JOB_ERROR, "completed_at": now},
                synchronize_session=False,
            )
        )
        db.commit()
    return expired
