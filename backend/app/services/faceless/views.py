"""Response shapes for /api/faceless (documented in app/routers/faceless.py)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.content import Image, Video
from app.models.faceless import FacelessCharacter, FacelessProject, FacelessSeries, FacelessStepRun

from . import catalog, consent, media
from .orchestrator import ACTIVE, run_view
from .pricing import build_ctx
from .scenes import scene_by_id, shot_kind, total_seconds


def _iso(value):
    return value.isoformat() if value else None


def media_view(entry: dict, char: FacelessCharacter) -> dict:
    """One stored character file. Real person media is private: its URL is the
    owner-only file route, never a /static path."""
    return {
        "id": entry.get("id"),
        "kind": entry.get("kind"),
        "role": entry.get("role"),
        "url": media.owner_url(entry, char.user_id, char.id),
        "private": media.is_private(entry),
        "width": entry.get("width"),
        "height": entry.get("height"),
        "duration": entry.get("duration"),
        "source_id": entry.get("source_id"),
        "usable_as_reference": entry.get("usable_as_reference", True),
        "created_at": entry.get("created_at"),
    }


def character_view(char: FacelessCharacter) -> dict:
    reason = consent.generation_block_reason(char)
    return {
        "id": char.id,
        "name": char.name,
        "kind": char.kind,
        "role": char.role,
        "personality": char.personality,
        "notes": char.notes,
        "style_notes": char.style_notes,
        "species": char.species,
        "catchphrase": char.catchphrase,
        "consent": {
            "status": consent.consent_status(char),
            "attested_at": _iso(char.consent_attested_at),
            "text_version": char.consent_text_version,
            "relationship": char.consent_relationship,
            "revoked_at": _iso(char.consent_revoked_at),
            "current_version": catalog.CONSENT_TEXT_VERSION,
        },
        "bible": char.bible,
        "media": [media_view(m, char) for m in char.media or []],
        "voice_id": char.voice_id,
        "voice_settings": char.voice_settings,
        "safety_flags": char.safety_flags or [],
        "can_generate": reason is None,
        "block_reason": reason,
        "is_archived": bool(char.is_archived),
        "created_at": _iso(char.created_at),
        "updated_at": _iso(char.updated_at),
    }


def series_view(series: FacelessSeries, project_count: int | None = None) -> dict:
    return {
        "id": series.id,
        "title": series.title,
        "logline": series.logline,
        "template_id": series.template_id,
        "style": series.style,
        "tone": series.tone,
        "cast_ids": series.cast_ids or [],
        "world_notes": series.world_notes,
        "rules": series.rules or [],
        "episode_memory": series.episode_memory or [],
        "project_count": project_count,
        "created_at": _iso(series.created_at),
        "updated_at": _iso(series.updated_at),
    }


def _first_still_url(project: FacelessProject) -> str | None:
    assets = project.scene_assets or {}
    for scene in (project.script or {}).get("scenes") or []:
        for still in (assets.get(str(scene.get("id"))) or {}).get("stills") or []:
            if still and still.get("file") and still.get("storage"):
                try:
                    return media.public_url(still, project.user_id)
                except Exception:
                    return None
    return None


def summary_thumbnails(db: Session, projects: list[FacelessProject]) -> dict[int, str | None]:
    """A card image per project: the chosen thumbnail, else the rendered
    video's thumbnail, else the first thumbnail, else the first storyboard
    still. Two queries for the whole page."""
    image_ids, video_ids = set(), set()
    for p in projects:
        for th in p.thumbnails or []:
            if th.get("image_id"):
                image_ids.add(th["image_id"])
        if p.output_video_id:
            video_ids.add(p.output_video_id)
    images = {i.id: i for i in db.query(Image).filter(Image.id.in_(image_ids)).all()} if image_ids else {}
    videos = {v.id: v for v in db.query(Video).filter(Video.id.in_(video_ids)).all()} if video_ids else {}

    def thumb_url(p: FacelessProject, th: dict) -> str | None:
        image = images.get(th.get("image_id"))
        if image is not None and image.user_id == p.user_id:
            return image.get_url()
        if th.get("file"):
            return media.public_url({"file": th["file"], "storage": "images"}, p.user_id)
        return None

    out: dict[int, str | None] = {}
    for p in projects:
        thumbs = [th for th in p.thumbnails or [] if th]
        chosen = (p.settings or {}).get("selected_thumbnail")
        picked = next((th for k, th in enumerate(thumbs) if (th.get("index", k)) == chosen), None)
        url = thumb_url(p, picked) if picked else None
        video = videos.get(p.output_video_id)
        if not url and video is not None and video.user_id == p.user_id:
            url = video.get_thumbnail_url()
        if not url and thumbs:
            url = thumb_url(p, thumbs[0])
        out[p.id] = url or _first_still_url(p)
    return out


def project_summary(project: FacelessProject, thumbnail_url: str | None = None) -> dict:
    return {
        "id": project.id,
        "title": project.title,
        "template_id": project.template_id,
        "series_id": project.series_id,
        "aspect": project.aspect,
        "length_seconds": project.length_seconds,
        "status": project.status,
        "script_version": project.script_version,
        "scene_count": len((project.script or {}).get("scenes") or []),
        "output_video_id": project.output_video_id,
        "usd_by_step": project.usd_by_step or {},
        "thumbnail_url": thumbnail_url,
        "created_at": _iso(project.created_at),
        "updated_at": _iso(project.updated_at),
    }


def _asset_url(entry: dict | None, user_id: int) -> str | None:
    return media.public_url(entry, user_id) if entry and entry.get("file") else None


def project_view(db: Session, project: FacelessProject) -> dict:
    from app.services.quality_gate import view as quality_view

    ctx = build_ctx(db, project)
    uid = project.user_id
    scenes = []
    for t in ctx.timing:
        scene = scene_by_id(ctx.script, t["scene_id"]) or {}
        a = ctx.assets(t["scene_id"])
        stored = {int(v.get("index", -1)): v for v in a.get("voice") or []}
        voice = []
        for line in t["lines"]:
            clip = stored.get(line["index"])
            current = bool(clip and clip.get("hash") == line["hash"])
            voice.append({
                "index": line["index"], "speaker": line["speaker"], "character_id": line["character_id"],
                "voice": line["voice"], "text": line["text"], "current": current,
                "url": _asset_url(clip, uid) if clip else None,
                "duration": clip.get("duration") if clip else None,
                "words": clip.get("words") if current else None,
                # The free take check (pace, long pauses): a hint, never a re-run.
                "warning": ((clip.get("check") or {}).get("warning") if current else None),
                "wpm": ((clip.get("check") or {}).get("wpm") if current else None),
            })
        um = a.get("user_media")
        scenes.append({
            "scene_id": t["scene_id"],
            "shot": shot_kind(scene),
            "start": t["start"],
            "duration": t["duration"],
            "measured": t["measured"],
            "stills": [
                {"url": _asset_url(s, uid), "model": s.get("model"), "seed": s.get("seed"),
                 "width": s.get("width"), "height": s.get("height"), "created_at": s.get("created_at"),
                 "quality": quality_view(s.get("quality"))}
                if s else None for s in a.get("stills") or []
            ],
            "clips": [
                {"url": _asset_url(c, uid), "model": c.get("model"), "mode": c.get("mode"),
                 "resolution": c.get("resolution"), "duration": c.get("duration"), "created_at": c.get("created_at"),
                 "quality": quality_view(c.get("quality"))}
                if c else None for c in a.get("clips") or []
            ],
            "user_media": {"url": _asset_url(um, uid), "kind": um.get("kind"), "duration": um.get("duration"),
                           "width": um.get("width"), "height": um.get("height")} if um else None,
            "voice": voice,
        })
    music = project.music or {}
    render = dict(project.render or {})
    video = db.query(Video).filter(Video.id == project.output_video_id).first() if project.output_video_id else None
    if video is not None and video.user_id == uid:
        render.update({"video_id": video.id, "url": video.get_url(), "thumbnail_url": video.get_thumbnail_url()})
    elif project.output_video_id:
        render["deleted"] = True
    thumbs = []
    for th in project.thumbnails or []:
        image = None
        if th.get("image_id"):
            image = db.query(Image).filter(Image.id == th.get("image_id"), Image.user_id == uid).first()
        thumbs.append({"index": th.get("index"), "image_id": th.get("image_id"), "text": th.get("text"),
                       "url": image.get_url() if image else media.public_url(
                           {"file": th["file"], "storage": "images"}, uid),
                       "raw_url": media.public_url({"file": th["raw_file"], "storage": "images"}, uid)
                       if th.get("raw_file") else None})
    runs = db.query(FacelessStepRun).filter(
        FacelessStepRun.project_id == project.id, FacelessStepRun.status.in_(ACTIVE)).all()
    return {
        **project_summary(project, summary_thumbnails(db, [project]).get(project.id)),
        "idea": project.idea,
        "language": project.language,
        "style": project.style,
        "narrator_voice": ctx.narrator_voice,
        "voice_settings": ctx.narrator_settings,
        "caption_preset": project.caption_preset,
        "music_mood": project.music_mood,
        "cast_ids": project.cast_ids or [],
        "facts": project.facts or [],
        "settings": project.settings or {},
        "selected_thumbnail": (project.settings or {}).get("selected_thumbnail"),
        "disclosure_checks": (project.settings or {}).get("disclosure_checks") or [],
        "script": project.script,
        "scenes": scenes,
        "total_seconds": round(total_seconds(ctx.timing) + (ctx.outro if ctx.timing else 0), 3),
        "timing_measured": bool(ctx.timing) and all(t["measured"] for t in ctx.timing),
        "music": {
            "tracks": [{"url": _asset_url({**tr, "storage": tr.get("storage", "uploads")}, uid),
                        "duration": tr.get("duration"), "start": tr.get("start")} for tr in music.get("tracks") or []],
            "mood": music.get("mood"),
            "instrumental": music.get("instrumental"),
            "rights": music.get("rights"),
        } if music else None,
        "render": render or None,
        "packaging": project.packaging,
        "thumbnails": thumbs,
        "compliance": project.compliance,
        "originality": project.originality,
        "active_runs": [run_view(r) for r in runs],
    }
