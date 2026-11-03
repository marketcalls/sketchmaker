"""One render at a time across the whole system (/faceless and /motion-graphics).

Every caller of app.render.render_timeline (both studios, on scheduler threads) takes
the single render slot first:

    from app.services.render_queue import render_slot

    with render_slot("faceless") as acquired:
        if not acquired:
            return          # another render is running; try on the next tick
        ... claim a queued render and call render_timeline ...

The app is one process, so a thread lock is the slot, and it dies with the process.
The slot never blocks: a caller that does not get it skips this tick.
"""

from __future__ import annotations

from contextlib import contextmanager
import logging
import threading

logger = logging.getLogger(__name__)

_slot = threading.Lock()


@contextmanager
def render_slot(owner: str = ""):
    """Yield True when this caller holds the render slot, else False."""
    acquired = _slot.acquire(blocking=False)
    if acquired:
        logger.debug(f"Render slot taken by {owner or 'a caller'}")
    try:
        yield acquired
    finally:
        if acquired:
            _slot.release()


def render_slot_busy() -> bool:
    """True when a render holds the slot (for status pages; racy by nature)."""
    return _slot.locked()
