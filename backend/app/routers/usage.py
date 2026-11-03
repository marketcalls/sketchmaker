"""The Usage page: estimated spending, and fal's live prices to compare it with.

fal and Sarvam spending comes from usage_log, LLM spending from llm_usage. Every
figure is an estimate from a built-in table, not a provider's invoice.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import Float, Integer, String, case, cast, func, literal, null, select, union_all

from app.dependencies import CurrentUser, DbSession
from app.models.llm_usage import LLMUsage
from app.models.usage_log import UsageLog
from app.services.fal_cost_service import fetch_single_model_pricing, get_available_models
from app.services.fal_keys import load_fal_key

router = APIRouter()

# Which provider a usage_log row was spent at.
_MEDIA_KIND = case((func.lower(UsageLog.model).like("%sarvam%"), "sarvam"), else_="fal")


@router.get("/summary")
def get_summary(_user: CurrentUser, db: DbSession, days: int = Query(30, ge=1, le=3650)):
    """Totals by kind (fal, sarvam, llm) and by feature over the last ``days``."""
    since = datetime.utcnow() - timedelta(days=days)
    by_kind = {
        "fal": {"usd": 0.0, "count": 0},
        "sarvam": {"usd": 0.0, "count": 0},
        "llm": {"usd": 0.0, "count": 0, "input_tokens": 0, "output_tokens": 0, "unpriced_calls": 0},
    }
    by_feature = []

    media_rows = (
        db.query(_MEDIA_KIND, UsageLog.feature, func.count(UsageLog.id), func.coalesce(func.sum(UsageLog.usd), 0.0))
        .filter(UsageLog.created_at >= since)
        .group_by(_MEDIA_KIND, UsageLog.feature)
        .all()
    )
    for kind, feature, count, usd in media_rows:
        by_kind[kind]["usd"] += float(usd)
        by_kind[kind]["count"] += count
        by_feature.append({"kind": kind, "feature": feature, "count": count, "usd": round(float(usd), 4)})

    llm_rows = (
        db.query(
            LLMUsage.feature,
            func.count(LLMUsage.id),
            func.coalesce(func.sum(LLMUsage.input_tokens), 0),
            func.coalesce(func.sum(LLMUsage.output_tokens), 0),
            func.sum(LLMUsage.estimated_usd),
            func.count(LLMUsage.estimated_usd),
        )
        .filter(LLMUsage.created_at >= since)
        .group_by(LLMUsage.feature)
        .all()
    )
    llm = by_kind["llm"]
    for feature, count, input_tokens, output_tokens, usd, priced in llm_rows:
        llm["usd"] += float(usd or 0)
        llm["count"] += count
        llm["input_tokens"] += int(input_tokens)
        llm["output_tokens"] += int(output_tokens)
        llm["unpriced_calls"] += count - priced
        by_feature.append({
            "kind": "llm",
            "feature": feature,
            "count": count,
            # null when no call for this feature has a known price
            "usd": round(float(usd), 4) if usd is not None else None,
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "unpriced_calls": count - priced,
        })

    for totals in by_kind.values():
        totals["usd"] = round(totals["usd"], 4)
    by_feature.sort(key=lambda row: row["usd"] or 0, reverse=True)
    return {
        "days": days,
        "total_usd": round(sum(totals["usd"] for totals in by_kind.values()), 4),
        "by_kind": by_kind,
        "by_feature": by_feature,
    }


@router.get("/log")
def get_log(
    _user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Spending newest first, fal and Sarvam rows merged with LLM calls."""
    media = select(
        UsageLog.id.label("id"),
        _MEDIA_KIND.label("kind"),
        UsageLog.created_at.label("created_at"),
        UsageLog.feature.label("feature"),
        UsageLog.model.label("model"),
        UsageLog.usd.label("usd"),
        UsageLog.units.label("units"),
        UsageLog.unit.label("unit"),
        UsageLog.job_type.label("job_type"),
        UsageLog.job_id.label("job_id"),
        cast(null(), Integer).label("input_tokens"),
        cast(null(), Integer).label("output_tokens"),
    )
    llm = select(
        LLMUsage.id.label("id"),
        literal("llm").label("kind"),
        LLMUsage.created_at.label("created_at"),
        LLMUsage.feature.label("feature"),
        LLMUsage.model.label("model"),
        LLMUsage.estimated_usd.label("usd"),
        cast(null(), Float).label("units"),
        cast(null(), String).label("unit"),
        cast(null(), String).label("job_type"),
        cast(null(), String).label("job_id"),
        LLMUsage.input_tokens.label("input_tokens"),
        LLMUsage.output_tokens.label("output_tokens"),
    )
    rows = union_all(media, llm).subquery()

    total = db.execute(select(func.count()).select_from(rows)).scalar() or 0
    result = db.execute(
        select(rows)
        .order_by(rows.c.created_at.desc(), rows.c.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).mappings().all()
    return {
        "entries": [
            {**row, "created_at": row["created_at"].isoformat() if row["created_at"] else None}
            for row in result
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/fal-models")
def get_fal_models(_user: CurrentUser):
    return get_available_models()


@router.get("/fal-pricing/{model_id:path}")
async def get_fal_pricing(model_id: str, _user: CurrentUser):
    """fal's live price for one model. One at a time because fal rate limits this."""
    api_key = await asyncio.to_thread(load_fal_key)
    return await fetch_single_model_pricing(api_key, model_id)
