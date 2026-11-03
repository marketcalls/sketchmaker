"""Scheduler entry points (registered in app/services/scheduler_service.py).

Both run only in the single scheduler process. APScheduler runs them on
separate threads with max_instances=1: provider polling never waits behind a
render, and renders share the system-wide slot with /faceless
(app/services/render_queue.py), so only one render runs at a time.
"""

import logging

from app.database import SessionLocal

logger = logging.getLogger(__name__)

TICK_SECONDS = 5
RENDER_TICK_SECONDS = 10


def run_tick() -> None:
    from .jobs import tick

    db = SessionLocal()
    try:
        tick(db)
    except Exception as exc:
        logger.error(f"Motion graphics tick failed: {exc}")
    finally:
        db.close()


def run_render_tick() -> None:
    from .jobs import render_tick

    db = SessionLocal()
    try:
        render_tick(db)
    except Exception as exc:
        logger.error(f"Motion graphics render tick failed: {exc}")
    finally:
        db.close()
