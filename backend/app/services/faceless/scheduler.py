"""Scheduler entry points (registered in app/services/scheduler_service.py).

APScheduler runs them (steps, long-form script drafts, renders) on separate threads with
max_instances=1, so a long render never delays the polling of other steps, and at most one
tick of each kind runs at a time.
"""

import logging

from app.database import SessionLocal

logger = logging.getLogger(__name__)

TICK_SECONDS = 5
RENDER_TICK_SECONDS = 10
SCRIPT_TICK_SECONDS = 5


def release_orphaned_claims() -> None:
    """At startup, before the first tick: resume runs that were saving a result when the app
    last stopped. Renders and script drafts left running are picked up by their own ticks."""
    from .orchestrator import release_orphaned_claims as release

    db = SessionLocal()
    try:
        released = release(db)
        if released:
            logger.info(f"Resuming {released} Faceless run(s) that were saving a result when the app last stopped")
    except Exception as exc:
        db.rollback()
        logger.error(f"Could not release Faceless claims: {exc}")
    finally:
        db.close()


def run_tick() -> None:
    """Advance queued and running steps (fal submit, poll, store)."""
    from .orchestrator import tick

    db = SessionLocal()
    try:
        tick(db)
    except Exception as exc:
        logger.error(f"Faceless tick failed: {exc}")
    finally:
        db.close()


def run_script_tick() -> None:
    """Draft at most one queued long-form script (several LLM calls)."""
    from .script_job import script_tick

    db = SessionLocal()
    try:
        script_tick(db)
    except Exception as exc:
        logger.error(f"Faceless script tick failed: {exc}")
    finally:
        db.close()


def run_render_tick() -> None:
    """Claim and render at most one queued video (one render system wide)."""
    from .render_job import render_tick

    db = SessionLocal()
    try:
        render_tick(db)
    except Exception as exc:
        logger.error(f"Faceless render tick failed: {exc}")
    finally:
        db.close()
