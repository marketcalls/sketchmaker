"""The activity log and the database-backed hourly caps (runaway-spend guards)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.motion_graphics import MGActivity

from .errors import RateLimited


def log_activity(db: Session, user_id: int, kind: str, *, project_id: int | None = None, **detail) -> None:
    db.add(MGActivity(user_id=user_id, project_id=project_id, kind=kind, detail=detail or None))


def check_rate(db: Session, user_id: int, kind: str, limit: int, window_seconds: int = 3600,
               label: str = "requests") -> None:
    since = datetime.utcnow() - timedelta(seconds=window_seconds)
    count = db.query(MGActivity).filter(MGActivity.user_id == user_id, MGActivity.kind == kind,
                                        MGActivity.created_at >= since).count()
    if count >= limit:
        raise RateLimited(f"Limit reached: {limit} {label} per {max(1, window_seconds // 60)} minutes. "
                          "Please try again later.", code="rate_limited")
