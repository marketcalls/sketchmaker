"""Recording what fal and Sarvam work cost.

record_usage is for fal and Sarvam spending only. LLM calls are logged by
litellm_client into llm_usage and must not also call it, or they are counted twice.
Call it on success only: fal does not bill failures.
"""

from __future__ import annotations

import json
import logging
import math

from sqlalchemy.orm import Session

from app.models.usage_log import UsageLog

logger = logging.getLogger(__name__)


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _json_safe(detail):
    """Something that cannot fail at the caller's commit."""
    if detail is None:
        return None
    return json.loads(json.dumps(detail, default=str))


def record_usage(
    db: Session,
    *,
    feature: str,
    usd: float,
    model: str | None = None,
    units: float | None = None,
    unit: str | None = None,
    job_type: str | None = None,
    job_id: str | int | None = None,
    detail: dict | None = None,
) -> None:
    """Add a UsageLog row to the session. Does not commit: it lands with the job's own
    status change. Never raises: a gap in a report is better than a lost result, so
    anything odd in the values is cleaned here rather than failing at commit.
    """
    try:
        db.add(UsageLog(
            feature=str(feature)[:50],
            usd=_number(usd) or 0.0,
            model=str(model)[:200] if model else None,
            units=_number(units),
            unit=str(unit)[:30] if unit else None,
            job_type=str(job_type)[:30] if job_type else None,
            job_id=str(job_id)[:64] if job_id is not None else None,
            detail=_json_safe(detail),
        ))
    except Exception:
        logger.exception("Could not record usage")
