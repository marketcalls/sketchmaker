"""API views for motion graphics projects, brand kits and compliance."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.content import Video
from app.models.motion_graphics import MGBrandKit, MGJob, MGProject

from . import media
from . import project as proj
from .jobs import ACTIVE, job_view
from .spec import TEMPLATES, validate


def _iso(v):
    return v.isoformat() if v else None


def upload_view(up: dict, user_id: int) -> dict:
    out = {k: up.get(k) for k in ("id", "kind", "name", "width", "height", "duration", "created_at", "ai_generated",
                                  "prompt")}
    out["url"] = media.public_url(up, user_id)
    return out


def project_summary(p: MGProject, db: Optional[Session] = None) -> dict:
    thumb = None
    outputs = p.outputs or {}
    first = outputs.get(p.aspect) or next(iter(outputs.values()), None)
    if first and db is not None:
        v = db.query(Video).filter(Video.id == first.get("video_id"), Video.user_id == p.user_id).first()
        thumb = v.get_thumbnail_url() if v else None
    return {"id": p.id, "title": p.title, "template_id": p.template_id, "style_id": p.style_id, "aspect": p.aspect,
            "variants": p.variants or [], "status": p.status, "spec_version": p.spec_version,
            "outputs": sorted(outputs), "thumbnail_url": thumb, "usd_by_step": p.usd_by_step or {},
            "created_at": _iso(p.created_at), "updated_at": _iso(p.updated_at)}


def project_view(db: Session, p: MGProject, plan: Optional[dict] = None) -> dict:
    spec = proj.spec_of(p)
    report = validate(spec, aspect=p.aspect)
    assets = p.assets or {}
    uploads = [upload_view(u, p.user_id) for u in (assets.get("uploads") or {}).values()]
    voice = assets.get("voice") or {}
    music = assets.get("music") or {}
    outputs = {}
    for aspect, o in (p.outputs or {}).items():
        v = db.query(Video).filter(Video.id == o.get("video_id"), Video.user_id == p.user_id).first()
        if v is None:
            continue
        outputs[aspect] = {**o, "url": v.get_url(), "download_url": v.get_direct_url(),
                           "thumbnail_url": v.get_thumbnail_url(),
                           "stale": int(o.get("spec_version") or 0) != int(p.spec_version or 0)}
    jobs = db.query(MGJob).filter(MGJob.project_id == p.id).order_by(MGJob.created_at.desc()).limit(5).all()
    audio = proj.audio_settings(p)
    return {
        **project_summary(p, db),
        "brief": p.brief, "spec": spec.model_dump(), "validation": report, "brand": brand_snapshot_view(p),
        "audio": audio, "uploads": uploads,
        "voice": {"current": proj.voice_current(p, spec), "needed": proj.voice_needed(p, spec),
                  "duration": voice.get("duration"), "voice_id": voice.get("voice_id"),
                  "url": media.public_url(voice, p.user_id) if voice.get("file") else None,
                  "chars": len(proj.voice_text(p, spec))},
        "music": {"current": bool(music.get("file")) and music.get("hash") == proj.music_hash(p),
                  "duration": music.get("duration"), "mood": music.get("mood"),
                  "url": media.public_url(music, p.user_id) if music.get("file") else None,
                  "beats": {k: (music.get("beats") or {}).get(k) for k in ("bpm", "reliable", "confidence")},
                  "rights": music.get("rights")},
        "plan": plan, "outputs": outputs,
        "jobs": [job_view(j) for j in jobs],
        "active_job": next((job_view(j) for j in jobs if j.status in ACTIVE), None),
        "compliance": compliance(p, spec),
    }


def brand_snapshot_view(p: MGProject) -> Optional[dict]:
    b = p.brand
    if not b:
        return None
    out = {k: b.get(k) for k in ("name", "palette", "fonts", "intensity", "use_brand_background")}
    out["logo_url"] = media.public_url(b["logo"], p.user_id) if b.get("logo") else None
    return out


def brand_kit_view(kit: Optional[MGBrandKit], user_id: int) -> dict:
    if kit is None:
        return {"exists": False, "name": None, "palette": {}, "fonts": {}, "intensity": "standard",
                "use_brand_background": False, "auto_apply": True, "logo_url": None}
    return {"exists": True, "name": kit.name, "palette": kit.palette or {}, "fonts": kit.fonts or {},
            "intensity": kit.intensity or "standard", "use_brand_background": bool(kit.use_brand_background),
            "auto_apply": bool(kit.auto_apply),
            "logo_url": media.public_url(kit.logo, user_id) if kit.logo else None}


def brand_snapshot(kit: Optional[MGBrandKit]) -> Optional[dict]:
    if kit is None:
        return None
    return {"name": kit.name, "logo": kit.logo, "palette": kit.palette or {}, "fonts": kit.fonts or {},
            "intensity": kit.intensity or "standard", "use_brand_background": bool(kit.use_brand_background)}


def compliance(p: MGProject, spec) -> list[dict]:
    """Checklist shown next to the render button: {id, level, title, detail}."""
    tpl = TEMPLATES.get(spec.template_id)
    out = []
    if tpl and tpl.requires_source:
        ok = bool((spec.source or "").strip())
        out.append({"id": "source", "level": "ok" if ok else "error", "title": "Source card",
                    "detail": "Data videos always end with a source card and show a source line on data scenes."
                    if ok else "Add the source of your numbers; it is required for data videos."})
    if tpl and tpl.requires_disclaimer:
        out.append({"id": "disclaimer", "level": "ok", "title": "Finance disclaimer",
                    "detail": "A disclaimer card (at least 2 seconds) is always included in market recaps."})
    pp = spec.options.paid_partnership
    out.append({"id": "paid_partnership", "level": "ok" if pp.enabled else "info", "title": "Paid partnership label",
                "detail": f"Shown for the whole video: Paid partnership with {pp.brand}." if pp.enabled else
                "If a brand paid for this video, turn on the paid partnership label (FTC and platform rules) and "
                "say it in the voiceover too."})
    audio = proj.audio_settings(p)
    if audio["voice"]["enabled"] or spec.template_id == "audiogram":
        out.append({"id": "ai_disclosure", "level": "info", "title": "AI voice",
                    "detail": "The narrator is an AI voice. Plain motion graphics with an AI narrator do not "
                    "usually need a platform AI label, but you can add an on-screen 'AI-generated voice' tag; "
                    "label it on YouTube or TikTok if it could pass for a real person."})
    if audio["music"]["enabled"]:
        out.append({"id": "music", "level": "ok", "title": "Music rights",
                    "detail": "Music is generated by ElevenLabs Music for this account; a generation receipt is "
                    "stored with the project. Trending commercial songs are never used."})
    out.append({"id": "fonts", "level": "ok", "title": "Fonts",
                "detail": "Only the bundled SIL Open Font License fonts are used, which allow video and server "
                "rendering. Custom font uploads are not offered in this release."})
    return out
