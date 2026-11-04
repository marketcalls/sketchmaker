"""The activity log and the database-backed hourly caps.

log_activity is also the consent audit trail: attestations, revocations and character
deletions land here. check_rate counts the same rows to guard against runaway spend.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.faceless import FacelessActivity

from .errors import RateLimited


def log_activity(db: Session, user_id: int, kind: str, *, project_id: int | None = None,
                 character_id: int | None = None, **detail) -> None:
    """Append to the activity log. No commit."""
    db.add(FacelessActivity(
        user_id=user_id,
        project_id=project_id,
        character_id=character_id,
        kind=kind,
        detail=detail or None,
    ))


def check_rate(db: Session, user_id: int, kind: str, limit: int, window_seconds: int = 3600,
               label: str = "requests") -> None:
    """RateLimited when the user has logged ``limit`` events of ``kind`` in the window."""
    since = datetime.utcnow() - timedelta(seconds=window_seconds)
    count = (
        db.query(FacelessActivity)
        .filter(
            FacelessActivity.user_id == user_id,
            FacelessActivity.kind == kind,
            FacelessActivity.created_at >= since,
        )
        .count()
    )
    if count >= limit:
        minutes = max(1, window_seconds // 60)
        raise RateLimited(
            f"Limit reached: {limit} {label} per {minutes} minutes. Please try again later.",
            code="rate_limited",
        )
