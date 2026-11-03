"""Motion Graphics Studio API (/api/motion-graphics).

Errors are JSON {"detail", "code", ...extra} (the Faceless handler in main.py):
job_active (409, extra: job_id), version_conflict (409), rate_limited (429),
invalid_spec / invalid_input / unsupported_file / too_large / too_long /
nothing_to_do (400), llm_not_configured (503), invalid_llm_output and
llm_call_failed (502).

Catalog
  GET  /catalog                 templates (slots, limits, scene types), styles, aspects, safe zones,
                                intensities, fonts, voices, music moods, prices (estimated USD), limits
  GET  /voices                  {voices, default}
  GET  /music-moods             {moods}
  GET  /templates/{id}/preview.png?style=&aspect=&scene=&scale=   still of the sample (free, cached)

Brand kit (one per user)
  GET  /brand-kit   PUT /brand-kit   POST /brand-kit/logo (multipart file)   DELETE /brand-kit/logo

Projects
  GET  /projects?page=&page_size=            {projects, total}
  POST /projects                             ProjectCreate -> Project (sample content, brand auto-apply)
  POST /projects/draft                       DraftRequest -> Project (new project from a brief, AI, free)
  GET  /projects/{id}                        Project (spec, validation, plan, outputs, jobs, compliance)
  PUT  /projects/{id}                        ProjectUpdate -> Project (style, aspect, variants, audio, brand)
  DELETE /projects/{id}                      {deleted: true} (409 while a job runs; videos stay in the gallery)
  PUT  /projects/{id}/spec                   SpecSave -> Project (validated; expected_version optional)
  POST /projects/{id}/draft                  DraftRequest -> Project (AI rewrite of the spec, free, rate limited)
  POST /projects/{id}/preview                PreviewRequest -> image/png (free; unsaved spec allowed)
  POST /projects/{id}/motion-preview         MotionPreviewRequest -> image/webp (free; a silent animated scene)
  POST /data/parse                           DataParse -> {table, view}
  POST /projects/{id}/uploads                multipart file (image up to 15 MB, audio up to 40 MB / 180 s)
  DELETE /projects/{id}/uploads/{upload_id}
  GET  /projects/{id}/quote?kind=audio|render  Quote {kind, estimated_usd, breakdown, notes, seconds, warnings}
  POST /projects/{id}/jobs                   JobRequest {kind, idempotency_key}
                                             (or header Idempotency-Key) -> 202 Job.
  GET  /projects/{id}/jobs   GET /jobs/{id}   POST /jobs/{id}/cancel

Heavy work never runs here: jobs are advanced and rendered by the scheduler;
previews are single frames rendered in a thread pool.
"""

import io
import logging
import threading
from collections import OrderedDict
from typing import Optional

from fastapi import APIRouter, File, Header, Query, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.database import apply_row_lock
from app.dependencies import CurrentUser, DbSession
from app.middleware.rate_limiter import limiter
from app.models.motion_graphics import MGBrandKit, MGJob, MGProject
from app.schemas.motion_graphics import (
    BrandKitUpdate, DataParse, DraftRequest, JobRequest, MotionPreviewRequest, PreviewRequest, ProjectCreate,
    ProjectUpdate, SpecSave,
)
from app.services import pricing as cp
from app.services.faceless import catalog as fl_catalog
from app.services.motion_graphics import activity, jobs, media, pricing, views
from app.services.motion_graphics import project as proj
from app.services.motion_graphics.design import (
    ASPECTS, BRAND_FONTS, INTENSITIES, SAFE_ZONE_PRESETS, SAFE_ZONES, STYLES, style_catalog,
)
from app.services.motion_graphics.errors import Conflict, InvalidRequest, NotFound, Unavailable, UpstreamError
from app.services.motion_graphics.spec import TEMPLATES, Spec, catalog, default_spec, normalize

logger = logging.getLogger(__name__)

router = APIRouter()

POST_LIMIT = "30/minute"
PREVIEW_LIMIT = "120/minute"
DRAFTS_PER_HOUR = 20
UPLOADS_PER_HOUR = 40
MAX_PROJECTS = 200

# One preview (build plus frame) at a time: previews share the machine with the
# scheduler's render.
_preview_gate = threading.BoundedSemaphore(1)
PREVIEW_WAIT_SECONDS = 15
# Preview scales are snapped to these steps so canvas sizes (and the cached
# background plates keyed by them) stay a small, fixed set.
PREVIEW_SCALES = (0.25, 0.35, 0.5, 0.75, 1.0)
THUMB_CACHE_MAX_BYTES = 32 * 1024 * 1024
_thumb_cache: "OrderedDict[tuple, bytes]" = OrderedDict()
_thumb_bytes = {"total": 0}
_thumb_lock = threading.Lock()


def _snap_scale(scale: float, steps: tuple = PREVIEW_SCALES) -> float:
    return min(steps, key=lambda s: abs(s - float(scale)))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project(db, user, project_id: int, lock: bool = False) -> MGProject:
    q = db.query(MGProject).filter(MGProject.id == project_id, MGProject.user_id == user.id)
    p = (apply_row_lock(q.populate_existing()) if lock else q).first()
    if p is None:
        raise NotFound("Project not found.")
    return p


def _job(db, user, job_id: int) -> MGJob:
    j = db.query(MGJob).filter(MGJob.id == job_id, MGJob.user_id == user.id).first()
    if j is None:
        raise NotFound("Job not found.")
    return j


def _plan(p: MGProject) -> Optional[dict]:
    try:
        from app.services.motion_graphics import build as mg_build

        spec = proj.spec_of(p)
        kw = proj.build_kwargs(p, spec)
        kw.update(files={}, logo_path=None)
        _, plan = mg_build.build(spec, aspect=p.aspect, scale=0.25, preview=True, **kw)
        return plan
    except Exception as exc:
        logger.warning(f"Motion graphics plan for project {p.id} failed: {exc}")
        return None


async def _view(db, p: MGProject) -> dict:
    plan = await run_in_threadpool(_plan, p)
    return views.project_view(db, p, plan)


def _set_json(obj, attr, value):
    jobs.set_json(obj, attr, value)


def _brand_kit(db, user_id: int) -> Optional[MGBrandKit]:
    return db.query(MGBrandKit).filter(MGBrandKit.user_id == user_id).first()


def _logo_in_use(db, user_id: int, filename: str) -> bool:
    """Whether a stored logo file is still the kit's logo or in a project's
    brand snapshot (snapshots share the kit's file rather than copying it)."""
    kit = _brand_kit(db, user_id)
    if kit is not None and (kit.logo or {}).get("file") == filename:
        return True
    rows = db.query(MGProject.brand).filter(MGProject.user_id == user_id).all()
    return any(((r.brand or {}).get("logo") or {}).get("file") == filename for r in rows)


def _parse_spec(raw: dict, template_id: str) -> Spec:
    try:
        spec = Spec.model_validate({**raw, "template_id": template_id})
    except Exception as exc:
        logger.warning(f"Motion graphics storyboard failed validation: {exc}")
        raise InvalidRequest("The storyboard could not be saved because some of it is missing or too long. "
                             "Check each scene and try again.", code="invalid_spec")
    return normalize(spec)


def _llm_error(exc: Exception):
    from app.services.storyscript.errors import InvalidLLMOutput, LLMCallFailed, LLMNotConfigured

    if isinstance(exc, LLMNotConfigured):
        return Unavailable("The AI writer needs a language model key. Add one in Settings, under API keys.",
                           code="llm_not_configured")
    if isinstance(exc, InvalidLLMOutput):
        return UpstreamError("The AI writer did not return a usable storyboard. Try again or rephrase the brief.",
                             code="invalid_llm_output")
    if isinstance(exc, LLMCallFailed):
        return UpstreamError("The AI writer is unavailable right now. Try again shortly.", code="llm_call_failed")
    return None


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

@router.get("/catalog")
async def get_catalog(current_user: CurrentUser):
    return {
        "templates": catalog(), "styles": style_catalog(), "aspects": list(ASPECTS),
        "safe_zones": {a: {k: {"top": v[0], "bottom": v[1], "left": v[2], "right": v[3]} for k, v in z.items()}
                       for a, z in SAFE_ZONES.items()},
        "safe_zone_presets": list(SAFE_ZONE_PRESETS),
        "intensities": [{"id": i.id, "label": i.label} for i in INTENSITIES.values()],
        "fonts": list(BRAND_FONTS), "voices": fl_catalog.VOICES, "default_voice": proj.DEFAULT_VOICE,
        "music_moods": [m for m in fl_catalog.MUSIC_MOODS if m["id"] != "template"],
        "prices": proj.price_table(),
        "price_units": {cp.ELEVEN_V4_KEY: "1,000 characters", cp.ELEVEN_MUSIC_KEY: "started minute",
                        cp.RENDER_MINUTE_KEY: "started output minute per aspect"},
        "limits": {"max_seconds": proj.MAX_SECONDS, "image_max_bytes": media.IMAGE_MAX_BYTES,
                   "audio_max_bytes": media.AUDIO_MAX_BYTES, "audio_max_seconds": media.AUDIO_MAX_SECONDS,
                   "drafts_per_hour": DRAFTS_PER_HOUR},
    }


@router.get("/voices")
async def list_voices(current_user: CurrentUser):
    return {"voices": fl_catalog.VOICES, "default": proj.DEFAULT_VOICE}


@router.get("/music-moods")
async def list_moods(current_user: CurrentUser):
    return {"moods": [m for m in fl_catalog.MUSIC_MOODS if m["id"] != "template"]}


def _template_png(tid: str, style: str, aspect: str, scene: int, scale: float) -> bytes:
    from app.render import preview_frame
    from app.services.motion_graphics.build import build, scene_still_time

    key = (tid, style, aspect, scene, scale)
    with _thumb_lock:
        if key in _thumb_cache:
            _thumb_cache.move_to_end(key)
            return _thumb_cache[key]
    if not _preview_gate.acquire(timeout=PREVIEW_WAIT_SECONDS):
        raise Unavailable("Previews are busy. Try again in a moment.", code="busy")
    try:
        spec = default_spec(tid, style_id=style, seed=11)
        tl, plan = build(spec, aspect=aspect, scale=scale, preview=True)
        scenes = plan["scenes"]
        s = scenes[max(0, min(len(scenes) - 1, scene))]
        png = preview_frame(tl, scene_still_time(plan, s["id"]))
    finally:
        _preview_gate.release()
    with _thumb_lock:
        if key not in _thumb_cache:
            _thumb_cache[key] = png
            _thumb_bytes["total"] += len(png)
        while _thumb_cache and (_thumb_bytes["total"] > THUMB_CACHE_MAX_BYTES or len(_thumb_cache) > 240):
            _, old = _thumb_cache.popitem(last=False)
            _thumb_bytes["total"] -= len(old)
    return png


@router.get("/templates/{template_id}/preview.png")
@limiter.limit(PREVIEW_LIMIT)
async def template_preview(request: Request, template_id: str, current_user: CurrentUser,
                           style: Optional[str] = None, aspect: Optional[str] = None,
                           scene: int = Query(0, ge=0, le=20), scale: float = Query(0.35, ge=0.2, le=0.6)):
    tpl = TEMPLATES.get(template_id)
    if tpl is None:
        raise NotFound("Unknown template.")
    style = style if style in STYLES else tpl.default_style
    aspect = aspect if aspect in tpl.aspects else tpl.default_aspect
    png = await run_in_threadpool(_template_png, template_id, style, aspect, scene,
                                  _snap_scale(scale, (0.2, 0.25, 0.35, 0.45, 0.6)))
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


# ---------------------------------------------------------------------------
# Brand kit
# ---------------------------------------------------------------------------

_HEX = __import__("re").compile(r"^#[0-9A-Fa-f]{6}$")


@router.get("/brand-kit")
async def get_brand_kit(current_user: CurrentUser, db: DbSession):
    return views.brand_kit_view(_brand_kit(db, current_user.id), current_user.id)


@router.put("/brand-kit")
@limiter.limit(POST_LIMIT)
async def put_brand_kit(request: Request, body: BrandKitUpdate, current_user: CurrentUser, db: DbSession):
    kit = _brand_kit(db, current_user.id)
    if kit is None:
        kit = MGBrandKit(user_id=current_user.id, intensity="standard")
        db.add(kit)
    if body.name is not None:
        kit.name = body.name.strip()[:80] or None
    if body.palette is not None:
        pal = {}
        for k in ("primary", "secondary", "background", "text"):
            v = (body.palette.get(k) or "").strip()
            if v:
                if not _HEX.match(v):
                    raise InvalidRequest(f"Palette {k} must be a hex color like #1A2B3C.", code="invalid_input")
                pal[k] = v.upper()
        _set_json(kit, "palette", pal)
    if body.fonts is not None:
        f = {}
        for k in ("display", "text"):
            v = body.fonts.get(k)
            if v:
                if v not in BRAND_FONTS:
                    raise InvalidRequest("Fonts must come from the bundled list.", code="invalid_input")
                f[k] = v
        _set_json(kit, "fonts", f)
    if body.intensity is not None:
        kit.intensity = body.intensity
    if body.use_brand_background is not None:
        kit.use_brand_background = body.use_brand_background
    if body.auto_apply is not None:
        kit.auto_apply = body.auto_apply
    db.commit()
    db.refresh(kit)
    return views.brand_kit_view(kit, current_user.id)


@router.post("/brand-kit/logo")
@limiter.limit("20/minute")
async def upload_logo(request: Request, current_user: CurrentUser, db: DbSession, file: UploadFile = File(...)):
    content = await file.read(media.IMAGE_MAX_BYTES + 1)
    if not content:
        raise InvalidRequest("The file is empty.")
    if media.sniff(content) != "image":
        raise InvalidRequest("Upload the logo as a PNG, JPG or WebP image (transparent PNG works best).",
                             code="unsupported_file")
    info = await run_in_threadpool(media.prepare_image, content)
    stored = await media.store_bytes(info["content"], user_id=current_user.id, storage="uploads", prefix="mg_logo",
                                     ext=info["ext"], content_type=info["content_type"])
    kit = _brand_kit(db, current_user.id)
    if kit is None:
        kit = MGBrandKit(user_id=current_user.id, intensity="standard")
        db.add(kit)
    old = kit.logo
    _set_json(kit, "logo", {"file": stored["file"], "storage": stored["storage"], "width": info["width"],
                            "height": info["height"]})
    db.commit()
    db.refresh(kit)
    if old and old.get("file") and not _logo_in_use(db, current_user.id, old["file"]):
        await media.delete_stored(old, current_user.id)
    return views.brand_kit_view(kit, current_user.id)


@router.delete("/brand-kit/logo")
async def delete_logo(current_user: CurrentUser, db: DbSession):
    kit = _brand_kit(db, current_user.id)
    if kit is not None and kit.logo:
        old = kit.logo
        kit.logo = None
        db.commit()
        # Projects branded with this logo keep it in their snapshot.
        if old.get("file") and not _logo_in_use(db, current_user.id, old["file"]):
            await media.delete_stored(old, current_user.id)
    return views.brand_kit_view(kit, current_user.id)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@router.get("/projects")
async def list_projects(current_user: CurrentUser, db: DbSession, page: int = Query(1, ge=1),
                        page_size: int = Query(24, ge=1, le=100)):
    q = db.query(MGProject).filter(MGProject.user_id == current_user.id)
    total = q.count()
    rows = q.order_by(MGProject.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"projects": [views.project_summary(p, db) for p in rows], "total": total, "page": page,
            "page_size": page_size}


def _new_project(db, user_id: int, template_id: str, style_id: Optional[str], aspect: Optional[str],
                 title: Optional[str], apply_brand: bool, sample: bool) -> MGProject:
    tpl = TEMPLATES.get(template_id)
    if tpl is None:
        raise InvalidRequest("Unknown template.", code="unknown_template")
    if db.query(MGProject).filter(MGProject.user_id == user_id).count() >= MAX_PROJECTS:
        raise InvalidRequest(f"You can keep at most {MAX_PROJECTS} projects. Delete some first.")
    aspect = aspect if aspect in tpl.aspects else tpl.default_aspect
    spec = default_spec(template_id, style_id=style_id if style_id in STYLES else None, with_sample_data=sample)
    if not sample:
        spec.scenes = [s for s in spec.scenes if s.type in ("source_card", "disclaimer")]
    if title:
        spec.title = title[:120]
    kit = _brand_kit(db, user_id)
    brand = views.brand_snapshot(kit) if (apply_brand and kit is not None and kit.auto_apply) else None
    audio = {"voice": {"enabled": False, "voice_id": proj.DEFAULT_VOICE, "stability": 0.5, "similarity_boost": 0.75},
             "music": {"enabled": tpl.music_mood != "none", "mood": tpl.music_mood if tpl.music_mood != "none"
                       else "documentary"}}
    p = MGProject(user_id=user_id, title=spec.title, template_id=template_id, style_id=spec.style_id, aspect=aspect,
                  variants=[], spec=spec.model_dump(), spec_version=1, brand=brand, audio=audio,
                  assets={"uploads": {}}, outputs={}, status="draft", usd_by_step={})
    db.add(p)
    db.flush()
    return p


@router.post("/projects", status_code=status.HTTP_201_CREATED)
@limiter.limit(POST_LIMIT)
async def create_project(request: Request, body: ProjectCreate, current_user: CurrentUser, db: DbSession):
    p = _new_project(db, current_user.id, body.template_id, body.style_id, body.aspect, body.title, body.apply_brand,
                     body.sample_content)
    activity.log_activity(db, current_user.id, "project", project_id=p.id, template_id=p.template_id)
    db.commit()
    db.refresh(p)
    return await _view(db, p)


async def _run_draft(db, user, p: MGProject, body: DraftRequest) -> None:
    from app.services.motion_graphics.draft import draft_spec

    activity.check_rate(db, user.id, "draft", DRAFTS_PER_HOUR, label="AI drafts")
    activity.log_activity(db, user.id, "draft", project_id=p.id)
    db.commit()
    seed = int((p.spec or {}).get("seed") or 0) or None
    try:
        spec, info = await draft_spec(db, brief=body.brief, template_id=body.template_id or None,
                                      style_id=body.style_id or None, data_csv=body.data_csv,
                                      length_seconds=body.length_seconds, aspect=body.aspect or p.aspect, seed=seed,
                                      voiceover=body.voiceover, user_id=user.id)
    except Exception as exc:
        mapped = _llm_error(exc)
        if mapped is not None:
            logger.warning(f"Motion graphics draft for project {p.id} failed: {exc}")
            raise mapped
        raise
    p = _project(db, user, p.id, lock=True)
    tpl = TEMPLATES[spec.template_id]
    if spec.data is None and p.template_id == spec.template_id and (p.spec or {}).get("data"):
        from app.services.motion_graphics.spec import DataTable

        spec.data = DataTable.model_validate(p.spec["data"])
    p.template_id = spec.template_id
    p.style_id = spec.style_id
    p.title = spec.title
    p.brief = body.brief
    if body.aspect and body.aspect in tpl.aspects:
        p.aspect = body.aspect
    elif p.aspect not in tpl.aspects:
        p.aspect = tpl.default_aspect
    _set_json(p, "spec", spec.model_dump())
    p.spec_version = int(p.spec_version or 1) + 1
    audio = proj.audio_settings(p)
    if info.get("music_mood") in fl_catalog.MUSIC_MOOD_IDS and info["music_mood"] not in ("template",):
        audio["music"]["mood"] = info["music_mood"] if info["music_mood"] != "none" else audio["music"]["mood"]
        audio["music"]["enabled"] = info["music_mood"] != "none"
    if body.voiceover:
        audio["voice"]["enabled"] = True
    _set_json(p, "audio", audio)
    db.commit()


@router.post("/projects/draft", status_code=status.HTTP_201_CREATED)
@limiter.limit(POST_LIMIT)
async def create_from_brief(request: Request, body: DraftRequest, current_user: CurrentUser, db: DbSession):
    tid = body.template_id if body.template_id in TEMPLATES else "big_number"
    p = _new_project(db, current_user.id, tid, body.style_id, body.aspect, None, True, False)
    db.commit()
    try:
        await _run_draft(db, current_user, p, body)
    except Exception:
        db.rollback()
        gone = db.query(MGProject).filter(MGProject.id == p.id).first()
        if gone is not None:
            db.delete(gone)
            db.commit()
        raise
    p = _project(db, current_user, p.id)
    return await _view(db, p)


@router.post("/projects/{project_id}/draft")
@limiter.limit(POST_LIMIT)
async def draft_project(request: Request, project_id: int, body: DraftRequest, current_user: CurrentUser,
                        db: DbSession):
    p = _project(db, current_user, project_id)
    await _run_draft(db, current_user, p, body)
    p = _project(db, current_user, project_id)
    return await _view(db, p)


@router.get("/projects/{project_id}")
async def get_project(project_id: int, current_user: CurrentUser, db: DbSession):
    return await _view(db, _project(db, current_user, project_id))


@router.put("/projects/{project_id}")
@limiter.limit(POST_LIMIT)
async def update_project(request: Request, project_id: int, body: ProjectUpdate, current_user: CurrentUser,
                         db: DbSession):
    p = _project(db, current_user, project_id, lock=True)
    tpl = TEMPLATES[p.template_id]
    if body.expected_version is not None and body.expected_version != p.spec_version:
        raise Conflict("The project changed in another tab. Reload it.", code="version_conflict")
    spec = proj.spec_of(p)
    changed = False
    if body.title is not None:
        p.title = body.title.strip()[:200] or "Untitled"
        spec.title = p.title[:120]
        changed = True
    if body.style_id is not None:
        if body.style_id not in STYLES:
            raise InvalidRequest("Unknown style.", code="invalid_input")
        p.style_id = spec.style_id = body.style_id
        changed = True
    if body.aspect is not None:
        if body.aspect not in tpl.aspects:
            raise InvalidRequest(f"{tpl.name} does not support {body.aspect}.", code="invalid_input")
        p.aspect = body.aspect
    if body.variants is not None:
        bad = [a for a in body.variants if a not in tpl.aspects]
        if bad:
            raise InvalidRequest(f"{tpl.name} does not support {bad[0]}.", code="invalid_input")
        _set_json(p, "variants", [a for a in dict.fromkeys(body.variants) if a != p.aspect])
    if body.audio is not None:
        a = body.audio.model_dump(exclude_unset=True)  # partial: only what the client sent
        voice, music = a.get("voice") or {}, a.get("music") or {}
        provider = voice.get("provider") or proj.audio_settings(p)["voice"]["provider"]
        if provider == "sarvam":
            from app.services import sarvam_tts
            from app.services.assets import sarvam_key

            if voice.get("provider") == "sarvam" and not sarvam_key(db):
                raise InvalidRequest("Sarvam voices are not available right now.", code="invalid_input")
            if voice.get("voice_id") and voice["voice_id"] not in sarvam_tts.VOICE_IDS:
                raise InvalidRequest("Unknown voice.", code="invalid_input")
        elif voice.get("voice_id") and voice["voice_id"] not in fl_catalog.VOICE_IDS:
            raise InvalidRequest("Unknown voice.", code="invalid_input")
        if voice.get("provider") and not voice.get("voice_id") \
                and voice["provider"] != proj.audio_settings(p)["voice"]["provider"]:
            # Switching provider without a voice: that provider's default voice.
            from app.services import sarvam_tts

            voice["voice_id"] = sarvam_tts.DEFAULT_VOICE if voice["provider"] == "sarvam" else proj.DEFAULT_VOICE
        if music.get("mood") and music["mood"] not in fl_catalog.MUSIC_MOOD_IDS:
            raise InvalidRequest("Unknown music mood.", code="invalid_input")
        cur = proj.audio_settings(p)
        cur["voice"].update({k: v for k, v in voice.items() if v is not None})
        cur["music"].update({k: v for k, v in music.items() if v is not None})
        _set_json(p, "audio", cur)
    if body.apply_brand is not None:
        kit = _brand_kit(db, current_user.id)
        _set_json(p, "brand", views.brand_snapshot(kit) if body.apply_brand and kit else None)
        changed = True
    if changed:
        _set_json(p, "spec", spec.model_dump())
        p.spec_version = int(p.spec_version or 1) + 1
    db.commit()
    db.refresh(p)
    return await _view(db, p)


@router.put("/projects/{project_id}/spec")
@limiter.limit("90/minute")
async def save_spec(request: Request, project_id: int, body: SpecSave, current_user: CurrentUser, db: DbSession):
    p = _project(db, current_user, project_id, lock=True)
    if body.expected_version is not None and body.expected_version != p.spec_version:
        raise Conflict("The storyboard changed in another tab or was updated by a job. Reload it.",
                       code="version_conflict", extra={"version": p.spec_version})
    spec = _parse_spec(body.spec, p.template_id)
    if spec.style_id != p.style_id:
        p.style_id = spec.style_id
    p.title = spec.title or p.title
    _set_json(p, "spec", spec.model_dump())
    p.spec_version = int(p.spec_version or 1) + 1
    db.commit()
    db.refresh(p)
    return await _view(db, p)


@router.delete("/projects/{project_id}")
async def delete_project(project_id: int, current_user: CurrentUser, db: DbSession):
    p = _project(db, current_user, project_id, lock=True)
    if db.query(MGJob).filter(MGJob.project_id == p.id, MGJob.status.in_(jobs.ACTIVE)).first():
        raise Conflict("A job is running for this project. Cancel it first.", code="job_active")
    assets = p.assets or {}
    files = list((assets.get("uploads") or {}).values()) + [a for a in (assets.get("voice"), assets.get("music")) if a]
    logo = (p.brand or {}).get("logo") or {}
    # Rendered videos are not deleted: they are gallery rows that own their
    # files ("Rendered videos stay in your gallery"), deleted from there.
    db.query(MGJob).filter(MGJob.project_id == p.id).delete(synchronize_session=False)
    db.delete(p)
    db.commit()
    for f in files:
        if f.get("file"):
            await media.delete_stored(f, current_user.id)
    # The brand snapshot's logo is shared with the kit and other projects.
    if logo.get("file") and not _logo_in_use(db, current_user.id, logo["file"]):
        await media.delete_stored(logo, current_user.id)
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Preview, data, uploads
# ---------------------------------------------------------------------------

def _render_preview(p: MGProject, spec: Spec, body: PreviewRequest) -> bytes:
    from app.render import preview_frame
    from app.services.motion_graphics.build import build, scene_still_time

    aspect = body.aspect or p.aspect
    files, logo = media.local_files(p, spec)
    kw = proj.build_kwargs(p, spec, files=files, logo_path=logo)
    # The build lays out every scene's text and data, so it is inside the
    # gate together with the frame.
    if not _preview_gate.acquire(timeout=PREVIEW_WAIT_SECONDS):
        raise Unavailable("Previews are busy. Try again in a moment.", code="busy")
    try:
        tl, plan = build(spec, aspect=aspect, scale=_snap_scale(body.scale), preview=True,
                         safe_overlay=body.safe_zone_overlay, **kw)
        if body.t is not None:
            t = min(body.t, plan["total"] - 0.02)
        else:
            t = scene_still_time(plan, body.scene_id, body.at)
        return preview_frame(tl, max(0.0, t))
    finally:
        _preview_gate.release()


MOTION_PREVIEW_LIMIT = "20/minute"
MOTION_SCALE = 0.35
MOTION_SCENE_FPS, MOTION_VIDEO_FPS = 15, 10
MOTION_SCENE_MAX, MOTION_VIDEO_MAX = 10.0, 30.0


def _render_motion(p: MGProject, spec: Spec, body: MotionPreviewRequest) -> bytes:
    """Animated WebP of a scene (or the opening of the video): the same
    frames as the render at a small size, without audio. Pillow encodes it,
    so the web worker never runs ffmpeg; it shares the still preview gate."""

    from app.render.engine import Compositor
    from app.services.motion_graphics.build import build

    aspect = body.aspect or p.aspect
    files, logo = media.local_files(p, spec)
    kw = proj.build_kwargs(p, spec, files=files, logo_path=logo)
    if not _preview_gate.acquire(timeout=PREVIEW_WAIT_SECONDS):
        raise Unavailable("Previews are busy. Try again in a moment.", code="busy")
    try:
        tl, plan = build(spec, aspect=aspect, scale=MOTION_SCALE, preview=True, **kw)
        if body.scene_id:
            sc = next((s for s in plan["scenes"] if s["id"] == body.scene_id), None)
            if sc is None:
                raise InvalidRequest("That scene is not in the project.", code="invalid_input")
            t0, length, fps = float(sc["start"]), min(float(sc["duration"]), MOTION_SCENE_MAX), MOTION_SCENE_FPS
        else:
            t0, length, fps = 0.0, min(float(plan["total"]), MOTION_VIDEO_MAX), MOTION_VIDEO_FPS
        n = max(1, int(length * fps))
        last = max(0, int(plan["total"] * tl.fps) - 1)
        comp = Compositor(tl, preview=True, nice=5)
        try:
            frames = [comp.frame(min(last, int(round((t0 + j / fps) * tl.fps)))).convert("RGB") for j in range(n)]
        finally:
            comp.close()
        buf = io.BytesIO()
        frames[0].save(buf, "WEBP", save_all=True, append_images=frames[1:], duration=int(round(1000 / fps)),
                       loop=0, quality=70, method=2)
        return buf.getvalue()
    finally:
        _preview_gate.release()


@router.post("/projects/{project_id}/motion-preview")
@limiter.limit(MOTION_PREVIEW_LIMIT)
async def motion_preview(request: Request, project_id: int, body: MotionPreviewRequest, current_user: CurrentUser,
                         db: DbSession):
    p = _project(db, current_user, project_id)
    tpl = TEMPLATES[p.template_id]
    if body.aspect and body.aspect not in tpl.aspects:
        raise InvalidRequest(f"{tpl.name} does not support {body.aspect}.", code="invalid_input")
    spec = _parse_spec(body.spec, p.template_id) if body.spec else proj.spec_of(p)
    try:
        webp = await run_in_threadpool(_render_motion, p, spec, body)
    except (InvalidRequest, Unavailable):
        raise
    except Exception as exc:
        logger.exception(f"Motion graphics motion preview failed for project {p.id}: {exc}")
        raise InvalidRequest("The motion preview could not be drawn. Check the scene fields and try again.",
                             code="preview_failed")
    return Response(content=webp, media_type="image/webp", headers={"Cache-Control": "no-store"})


@router.post("/projects/{project_id}/preview")
@limiter.limit(PREVIEW_LIMIT)
async def preview(request: Request, project_id: int, body: PreviewRequest, current_user: CurrentUser, db: DbSession):
    p = _project(db, current_user, project_id)
    tpl = TEMPLATES[p.template_id]
    if body.aspect and body.aspect not in tpl.aspects:
        raise InvalidRequest(f"{tpl.name} does not support {body.aspect}.", code="invalid_input")
    spec = _parse_spec(body.spec, p.template_id) if body.spec else proj.spec_of(p)
    try:
        png = await run_in_threadpool(_render_preview, p, spec, body)
    except (InvalidRequest, Unavailable):
        raise
    except Exception as exc:
        logger.exception(f"Motion graphics preview failed for project {p.id}: {exc}")
        raise InvalidRequest("The preview could not be drawn. Check the scene fields and try again.",
                             code="preview_failed")
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/data/parse")
@limiter.limit("60/minute")
async def parse_data(request: Request, body: DataParse, current_user: CurrentUser):
    from app.services.motion_graphics.draft import data_report

    return data_report(body.kind, body.csv)


@router.post("/projects/{project_id}/uploads", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def upload(request: Request, project_id: int, current_user: CurrentUser, db: DbSession,
                 file: UploadFile = File(...)):
    p = _project(db, current_user, project_id)
    if len((p.assets or {}).get("uploads") or {}) >= media.MAX_UPLOADS_PER_PROJECT:
        raise InvalidRequest(f"A project can hold at most {media.MAX_UPLOADS_PER_PROJECT} uploads.", code="too_many")
    activity.check_rate(db, current_user.id, "upload", UPLOADS_PER_HOUR, label="uploads")
    content = await file.read(media.AUDIO_MAX_BYTES + 1)
    if not content:
        raise InvalidRequest("The file is empty.")
    kind = media.sniff(content)
    name = (file.filename or "")[:120]
    if kind == "image":
        info = await run_in_threadpool(media.prepare_image, content)
        stored = await media.store_bytes(info["content"], user_id=current_user.id, storage="uploads", prefix="mg_img",
                                         ext=info["ext"], content_type=info["content_type"])
        entry = media.upload_entry(stored, kind="image", name=name, width=info["width"], height=info["height"])
    else:
        info = await run_in_threadpool(media.prepare_audio, content)
        stored = await media.store_bytes(info["content"], user_id=current_user.id, storage="uploads", prefix="mg_aud",
                                         ext=info["ext"], content_type=info["content_type"])
        entry = media.upload_entry(stored, kind="audio", name=name, duration=info["duration"], amps=info["amps"])
    p = _project(db, current_user, project_id, lock=True)
    assets = dict(p.assets or {})
    ups = dict(assets.get("uploads") or {})
    if len(ups) >= media.MAX_UPLOADS_PER_PROJECT:  # re-checked under the lock (parallel uploads)
        db.rollback()
        await media.delete_stored(stored, current_user.id)
        raise InvalidRequest(f"A project can hold at most {media.MAX_UPLOADS_PER_PROJECT} uploads.", code="too_many")
    ups[entry["id"]] = entry
    assets["uploads"] = ups
    _set_json(p, "assets", assets)
    activity.log_activity(db, current_user.id, "upload", project_id=p.id, file_kind=kind)
    db.commit()
    return {"upload": views.upload_view(entry, current_user.id)}


@router.delete("/projects/{project_id}/uploads/{upload_id}")
async def delete_upload(project_id: int, upload_id: str, current_user: CurrentUser, db: DbSession):
    p = _project(db, current_user, project_id, lock=True)
    if db.query(MGJob).filter(MGJob.project_id == p.id, MGJob.status.in_(jobs.ACTIVE)).first():
        raise Conflict("A job is running for this project.", code="job_active")
    assets = dict(p.assets or {})
    ups = dict(assets.get("uploads") or {})
    entry = ups.pop(upload_id, None)
    if entry is None:
        raise NotFound("Upload not found.")
    assets["uploads"] = ups
    _set_json(p, "assets", assets)
    db.commit()
    await media.delete_stored(entry, current_user.id)
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Quotes and jobs
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/quote")
async def quote(project_id: int, current_user: CurrentUser, db: DbSession,
                kind: str = Query("render", pattern="^(audio|render)$")):
    p = _project(db, current_user, project_id)
    plan = await run_in_threadpool(pricing.plan_job, db, p, kind)
    return pricing.quote_view(plan)


@router.post("/projects/{project_id}/jobs", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(POST_LIMIT)
async def start_job(request: Request, response: Response, project_id: int, body: JobRequest, current_user: CurrentUser,
                    db: DbSession, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")):
    p = _project(db, current_user, project_id)
    job, created = await run_in_threadpool(jobs.start_job, db, current_user.id, p, body.kind,
                                           body.idempotency_key or idempotency_key)
    if not created:
        response.status_code = status.HTTP_200_OK
    return jobs.job_view(job)


@router.get("/projects/{project_id}/jobs")
async def list_jobs(project_id: int, current_user: CurrentUser, db: DbSession):
    p = _project(db, current_user, project_id)
    rows = db.query(MGJob).filter(MGJob.project_id == p.id).order_by(MGJob.created_at.desc()).limit(50).all()
    return {"jobs": [jobs.job_view(j) for j in rows]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: int, current_user: CurrentUser, db: DbSession):
    return jobs.job_view(_job(db, current_user, job_id))


@router.post("/jobs/{job_id}/cancel")
async def cancel(job_id: int, current_user: CurrentUser, db: DbSession):
    # The write lock may have to wait for another writer: wait in a worker thread,
    # not on the event loop.
    job = _job(db, current_user, job_id)
    return jobs.job_view(await run_in_threadpool(jobs.cancel_job, db, job))
