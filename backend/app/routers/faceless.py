"""Faceless Studio API (/api/faceless): cast, series, projects, quotes and steps.

Errors: every Faceless error is JSON {"detail": "<message>", "code": "<code>",
...extra}. Codes: consent_required (403, extra: characters), compliance_block (403,
extra: flags), rate_limited (429), nothing_to_do / step_active / steps_active /
script_active / render_active / key_reused / script_changed / quote_changed (409, extra:
run_id, run_ids or quote), still_required / visual_required (400, extra: scene_ids),
unknown_template, unknown_scene, unknown_step, unknown_voice, invalid_script, invalid_input,
invalid_length, too_large (400), llm_not_configured (503), invalid_llm_output and
llm_call_failed (502), not_implemented (501). A queued script draft that fails carries
the same code on its StepRun item (items[0].code).

Catalogues
  GET  /templates          {templates: [storyscript.Template], styles: [{id, label, prompt}]}
  GET  /voices             {voices: [{id, gender, accent, tone}], default_narrator}
  GET  /music-moods        {moods: [{id, label, positive, negative}]}
  GET  /caption-styles     {styles: [{id, label, description}]}
  GET  /config             {aspects, limits, models, consent: {version, text, relationships},
                            prices: {key: USD per unit}, steps, grade_looks: [{id, label, description}]}

Characters (cast library)
  GET    /characters?include_archived=false      {characters: [Character]}
  POST   /characters                   CharacterCreate -> Character. kind real_person requires
                                       consent {accepted: true, text_version, relationship}
  GET    /characters/{id}              Character
  PUT    /characters/{id}              CharacterUpdate -> Character (consent re-attests,
                                       revoke_consent: true revokes)
  DELETE /characters/{id}              {deleted: true}
  POST   /characters/{id}/consent      ConsentIn -> Character
  POST   /characters/{id}/consent/revoke          -> Character
  POST   /characters/{id}/media        multipart "file" (PNG/JPG/WebP/AVIF up to 25 MB, or
                                       MP4/MOV/WebM up to 100 MB and 60 s), optional form
                                       field role=reference -> Character. A video adds 3
                                       extracted frames as references; a 2 to 15 s video is
                                       also an H3 Max reference video.
  GET    /characters/{id}/media/{media_id}/file   the owner's own copy of one file
  DELETE /characters/{id}/media/{media_id}        -> Character
  POST   /characters/{id}/bible        20 per hour -> Character (bible and safety flags)
  GET    /characters/{id}/sheet/quote  Quote
  POST   /characters/{id}/sheet        SheetRequest -> StepRun (one 16:9 reference sheet)

  Character = {id, name, kind, role, personality, notes, style_notes, species, catchphrase,
               consent: {status: not_required|missing|outdated|valid|revoked, attested_at,
               text_version, relationship, revoked_at, current_version}, bible, media:
               [{id, kind: image|video, role: reference|sheet|source_video|frame, url, width,
               height, duration, source_id, usable_as_reference, created_at}], voice_id,
               voice_settings, safety_flags, can_generate, block_reason, is_archived,
               created_at, updated_at}

Series
  GET    /series                       {series: [Series]}
  POST   /series                       SeriesCreate -> Series
  GET    /series/{id}                  Series plus projects: [ProjectSummary]
  PUT    /series/{id}                  SeriesUpdate -> Series
  DELETE /series/{id}                  {deleted: true} (projects stay, detached)

Projects
  GET    /projects?series_id=&page=&page_size=   {projects: [ProjectSummary], total, page, page_size}
  POST   /projects                     ProjectCreate -> Project (length 15 to 180 s, up to
                                       900 s for 16:9; at most 6 characters)
  GET    /projects/{id}                Project
  PUT    /projects/{id}                ProjectUpdate -> Project
  DELETE /projects/{id}                {deleted: true} (409 while a step is running)
  POST   /projects/{id}/script         ScriptDraftRequest {idea?, background?, idempotency_key?}.
                                       20 drafts per hour. Short formats: 200 Project (drafted
                                       inline). Long-form (over 90 s or a long-form template) or
                                       background: true: 202 StepRun with step "script", drafted
                                       by the scheduler; poll GET /runs/{id}, then GET
                                       /projects/{id}. Either way a new version is saved and the
                                       compliance and originality checks run. Other steps answer
                                       409 script_active while a draft is running.
  PUT    /projects/{id}/script         ScriptSave {script} -> Project (new version, checks re-run)
  GET    /projects/{id}/script/versions          {versions: [{version, source, created_at, title}], current}
  GET    /projects/{id}/script/versions/{v}      {version, source, created_at, script}
  POST   /projects/{id}/script/versions/{v}/restore -> Project
  POST   /projects/{id}/scenes/{scene_id}/revise SceneRevise {instruction} -> Project
  POST   /projects/{id}/scenes/{scene_id}/media  multipart "file" (image, or video up to
                                       180 s) -> Project. Used instead of a generated still.
  DELETE /projects/{id}/scenes/{scene_id}/media  -> Project
  GET    /projects/{id}/quote?step=storyboard|clips|voice|music|render|thumbnails
                                       &scene_ids=s1,s2&options=<JSON object>   Quote
  POST   /projects/{id}/quote          QuoteRequest {step, scene_ids, options} -> Quote
  POST   /projects/{id}/steps/{step}   StepRequest {scene_ids?, options?, idempotency_key?,
                                       expected_usd?} (or header Idempotency-Key) -> 202 StepRun.
                                       A repeated key returns the same run (200). expected_usd,
                                       when sent, answers 409 quote_changed if the estimate moved.
  GET    /projects/{id}/runs           {runs: [StepRun]} newest first
  GET    /runs/{run_id}                StepRun
  POST   /runs/{run_id}/cancel         StepRun (pending items are cancelled; a render stops)
  GET    /projects/{id}/originality    OriginalityReport plus script_version (re-checked on demand)
  GET    /projects/{id}/compliance     {flags, blocked, checked_at, script_version}
  POST   /projects/{id}/package        PackageRequest {thumbnails?, texts?, options?,
                                       idempotency_key?, expected_usd?} -> {packaging, run:
                                       StepRun|null}. Metadata is an LLM call (20 per hour);
                                       thumbnails are the thumbnails step.
  GET    /projects/{id}/log            {events: [{kind, detail, created_at}]} production log

Step options (all optional):
  storyboard  t2i_model, edit_model, resolution 1k|2k, regenerate, quality_check
  clips       resolution 480p|768p|1080p, mode image|reference, max_clips_per_scene 1..4,
              regenerate, quality_check
  voice       regenerate, lines
  music       mood, instrumental (default true), regenerate
  render      resolution 1080p|720p, captions (preset id or "none"), music (bool), music_gain_db
  thumbnails  t2i_model, edit_model, texts [3 headlines]

Quote = {step, usd, breakdown: [{label, key, unit, units, unit_usd, usd, count}],
         assumptions: [str], scene_ids, characters}. Every amount is an estimate in USD.
StepRun = {id, project_id, character_id, step, status: queued|running|completed|partial|
           failed|cancelled, progress 0..100, scene_ids, options, quote, estimated_usd (the
           quote total), usd_spent (what landed so far), cancel_requested, error, items: [{id,
           kind, scene_id, index, status: pending|submitted|done|failed|cancelled, usd, error,
           code, qa, qa_verdict}], idempotency_key, created_at, started_at, completed_at}
Project = ProjectSummary plus {idea, language, style, narrator_voice, voice_settings,
           caption_preset, music_mood, cast_ids, facts, settings, script, scenes: [{scene_id,
           shot, start, duration, measured, stills: [{url, model, seed, width, height}],
           clips: [{url, model, mode, resolution, duration}], user_media: {url, kind,
           duration}, voice: [{index, speaker, character_id, voice, text, current, url,
           duration, words: [{text, start, end}]}]}], total_seconds, timing_measured,
           music: {tracks: [{url, duration, start}], mood, instrumental, rights}, render:
           {video_id, url, thumbnail_url, duration, width, height, rendered_at}, packaging,
           thumbnails: [{index, image_id, url, raw_url, text}], compliance, originality,
           active_runs: [StepRun]}
ProjectSummary = {id, title, template_id, series_id, aspect, length_seconds, status:
           draft|scripted|producing|rendered, script_version, scene_count, output_video_id,
           usd_by_step, thumbnail_url, created_at, updated_at}

Long work never runs here: steps are queued and the scheduler advances them (fal submit and
poll) and renders one video at a time.

Every route that writes is a plain def. Those run on the thread pool, so waiting for the
SQLite write lock (up to busy_timeout), ffmpeg or an LLM call never freezes the event loop.
While a step runs (orchestrator.require_same_scenes has why): a scene's text and shot can
still be edited, by a save or a revision. A save that adds, removes, moves or renames scenes
answers 409 steps_active, and so do a new draft and a restored version, which replace every
scene. A second draft answers 409 script_active.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, Form, Header, Request, Response, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func

from app.database import apply_row_lock
from app.dependencies import CurrentUser, DbSession
from app.middleware.rate_limiter import limiter
from app.models.content import Image, Video
from app.models.faceless import (
    FacelessActivity, FacelessCharacter, FacelessProject, FacelessScriptVersion, FacelessSeries, FacelessStepRun,
)
from app.schemas.faceless import CharacterCreate, CharacterUpdate, ConsentIn
from app.services import pricing as cp
from app.services.faceless import activity, catalog, consent, media, orchestrator, pricing, script_job, scripts, views
from app.services.faceless.errors import Blocked, Conflict, InvalidRequest, NotFound
from app.services.faceless.render_job import VIDEO_TYPE
from app.services.faceless.scenes import scene_by_id
from app.services.faceless.schemas import (
    PackageRequest, ProjectCreate, ProjectUpdate, QuoteRequest, SceneRevise, ScriptDraftRequest, ScriptSave,
    SeriesCreate, SeriesUpdate, SheetRequest, StepRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()

POST_LIMIT = "30/minute"
UPLOAD_LIMIT = "20/minute"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _character(db, user, char_id: int) -> FacelessCharacter:
    char = db.query(FacelessCharacter).filter(
        FacelessCharacter.id == char_id, FacelessCharacter.user_id == user.id).first()
    if char is None:
        raise NotFound("Character not found.")
    return char


def _take_private_media(char: FacelessCharacter) -> list[dict]:
    """Detach every stored file of a real person character (on consent
    revocation). The caller commits, then deletes the returned files."""
    if char.kind != "real_person":
        return []
    removed = list(char.media or [])
    if removed:
        media.set_json(char, "media", [])
    return removed


def _delete_files(entries: list[dict], user_id: int) -> None:
    for entry in entries:
        media.run_async(media.delete_stored(entry, user_id))


def _series(db, user, series_id: int) -> FacelessSeries:
    series = db.query(FacelessSeries).filter(
        FacelessSeries.id == series_id, FacelessSeries.user_id == user.id).first()
    if series is None:
        raise NotFound("Series not found.")
    return series


def _project(db, user, project_id: int, lock: bool = False) -> FacelessProject:
    query = db.query(FacelessProject).filter(
        FacelessProject.id == project_id, FacelessProject.user_id == user.id)
    project = (apply_row_lock(query) if lock else query).first()
    if project is None:
        raise NotFound("Project not found.")
    return project


def _run(db, user, run_id: int) -> FacelessStepRun:
    run = db.query(FacelessStepRun).filter(
        FacelessStepRun.id == run_id, FacelessStepRun.user_id == user.id).first()
    if run is None:
        raise NotFound("Run not found.")
    return run


def _check_length(aspect: str, length: int, tpl: dict | None = None) -> None:
    low, top = catalog.MIN_LENGTH_SECONDS, catalog.MAX_LENGTH_SECONDS[aspect]
    rng = (tpl or {}).get("length") or {}
    low = max(low, int(rng.get("min_seconds") or low))
    top = min(top, int(rng.get("max_seconds") or top))
    if low > top:
        raise InvalidRequest(f"This template does not support {aspect}.", code="invalid_length")
    if length < low or length > top:
        raise InvalidRequest(f"Length for this template at {aspect} must be {low} to {top} seconds.",
                             code="invalid_length")


def _check_choices(data: dict) -> None:
    if data.get("narrator_voice") and data["narrator_voice"] not in catalog.VOICE_IDS:
        raise InvalidRequest("Unknown narrator voice.", code="unknown_voice")
    if data.get("caption_preset") and data["caption_preset"] not in catalog.CAPTION_STYLE_IDS:
        raise InvalidRequest("Unknown caption style.", code="unknown_caption_style")
    if data.get("music_mood") and data["music_mood"] not in catalog.MUSIC_MOOD_IDS:
        raise InvalidRequest("Unknown music mood.", code="unknown_mood")
    if data.get("style") and data["style"] not in catalog.STYLE_PROMPTS:
        raise InvalidRequest("Unknown visual style.", code="unknown_style")
    settings = data.get("settings") or {}
    if settings.get("t2i_model") and settings["t2i_model"] not in pricing.t2i_models():
        raise InvalidRequest("Unknown text to image model.")
    if settings.get("edit_model") and settings["edit_model"] not in pricing.edit_models():
        raise InvalidRequest("Unknown edit model.")


def _parse_options(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except ValueError:
        raise InvalidRequest("options must be a JSON object.")
    if not isinstance(value, dict):
        raise InvalidRequest("options must be a JSON object.")
    return value


def _take_project_outputs(db, project: FacelessProject) -> list[dict]:
    """Delete (without committing) the gallery rows a project produced: every render (Video)
    and thumbnail (Image), from earlier runs too, and return their stored files plus the raw
    thumbnail backgrounds and the frames made to chain clip parts. A row already deleted from
    the gallery is skipped."""
    video_ids = {project.output_video_id, (project.render or {}).get("video_id")}
    image_ids = {th.get("image_id") for th in project.thumbnails or [] if th}
    raw_files = {th.get("raw_file") for th in project.thumbnails or [] if th}
    files = []
    runs = db.query(FacelessStepRun.step, FacelessStepRun.items).filter(
        FacelessStepRun.project_id == project.id).all()
    for run in runs:
        for item in run.items or []:
            result = (item or {}).get("result") or {}
            if run.step == "render":
                video_ids.add(result.get("video_id"))
            elif run.step == "thumbnails":
                image_ids.add(result.get("image_id"))
                raw_files.add(result.get("raw_file"))
            elif run.step == "music" and result.get("file"):
                # Also tracks that never reached project.music, if its finisher failed.
                files.append({"file": result["file"], "storage": result.get("storage") or "uploads"})
            elif (item or {}).get("chained_frame"):
                files.append({"file": item["chained_frame"], "storage": "uploads"})
    files += [{"file": f, "storage": "images"} for f in raw_files if f]
    video_ids = [int(i) for i in video_ids if isinstance(i, int)]
    image_ids = [int(i) for i in image_ids if isinstance(i, int)]
    if video_ids:
        for video in db.query(Video).filter(Video.id.in_(video_ids), Video.user_id == project.user_id,
                                            Video.video_type == VIDEO_TYPE).all():
            files.append({"file": video.filename, "storage": "videos"})
            if video.thumbnail_filename:
                files.append({"file": video.thumbnail_filename, "storage": "thumbnails"})
            db.delete(video)
    if image_ids:
        for image in db.query(Image).filter(Image.id.in_(image_ids), Image.user_id == project.user_id,
                                            Image.art_style == "faceless_thumbnail").all():
            files.append({"file": image.filename, "storage": "images"})
            db.delete(image)
    return files


def _read_upload(file: UploadFile) -> bytes:
    content = file.file.read(catalog.VIDEO_UPLOAD_MAX_BYTES + 1)
    if not content:
        raise InvalidRequest("The file is empty.")
    if len(content) > catalog.VIDEO_UPLOAD_MAX_BYTES:
        raise InvalidRequest("File too large. Images up to 25 MB, videos up to 100 MB.", code="too_large")
    return content


# ---------------------------------------------------------------------------
# Catalogues
# ---------------------------------------------------------------------------

@router.get("/templates")
async def list_templates(current_user: CurrentUser):
    return {"templates": scripts.templates(), "styles": catalog.STYLES}


@router.get("/voices")
async def list_voices(current_user: CurrentUser):
    return {"voices": catalog.VOICES, "default_narrator": catalog.DEFAULT_NARRATOR_VOICE}


@router.get("/music-moods")
async def list_music_moods(current_user: CurrentUser):
    return {"moods": catalog.MUSIC_MOODS}


@router.get("/caption-styles")
async def list_caption_styles(current_user: CurrentUser):
    return {"styles": catalog.CAPTION_STYLES}


@router.get("/config")
async def get_config(current_user: CurrentUser):
    table = cp.cost_table()
    keys = [cp.ELEVEN_V4_KEY, cp.ELEVEN_MUSIC_KEY, cp.RENDER_MINUTE_KEY,
            "video:h3-max:reference-1k-tokens"]
    keys += [cp.video_key(catalog.H3_FAMILY, r) for r in catalog.CLIP_RESOLUTIONS]
    for m in pricing.t2i_models():
        keys += [cp.image_key(m, r) for r in catalog.STILL_RESOLUTIONS]
    for m in pricing.edit_models():
        keys += [cp.edit_key(m, r) for r in catalog.STILL_RESOLUTIONS]
    return {
        "aspects": list(catalog.ASPECTS),
        "limits": {
            "min_length_seconds": catalog.MIN_LENGTH_SECONDS,
            "max_length_seconds": catalog.MAX_LENGTH_SECONDS,
            "max_scenes": catalog.MAX_SCENES,
            "max_cast": catalog.MAX_CAST,
            "max_character_media": catalog.MAX_CHARACTER_MEDIA,
            "image_upload_max_bytes": catalog.IMAGE_UPLOAD_MAX_BYTES,
            "video_upload_max_bytes": catalog.VIDEO_UPLOAD_MAX_BYTES,
            "character_video_max_seconds": catalog.CHARACTER_VIDEO_MAX_SECONDS,
            "scene_video_max_seconds": catalog.SCENE_VIDEO_MAX_SECONDS,
            "drafts_per_hour": catalog.DRAFTS_PER_HOUR,
        },
        "models": {
            "t2i": pricing.t2i_models(), "edit": pricing.edit_models(),
            "default_t2i": catalog.DEFAULT_T2I_MODEL, "default_edit": catalog.DEFAULT_EDIT_MODEL,
            "still_resolutions": list(catalog.STILL_RESOLUTIONS),
            "clip_resolutions": list(catalog.CLIP_RESOLUTIONS), "default_clip_resolution": catalog.DEFAULT_CLIP_RESOLUTION,
            "clip_modes": list(catalog.CLIP_MODES), "render_resolutions": list(catalog.RENDER_RESOLUTIONS),
        },
        "consent": {"version": catalog.CONSENT_TEXT_VERSION, "text": catalog.CONSENT_TEXT,
                    "relationships": list(catalog.CONSENT_RELATIONSHIPS)},
        "prices": {k: table[k] for k in keys if k in table},
        "steps": list(catalog.STEPS),
        "grade_looks": _grade_looks(),
    }


def _grade_looks() -> list[dict]:
    from app.render.grade import looks_catalog

    return looks_catalog()


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------

@router.get("/characters")
async def list_characters(current_user: CurrentUser, db: DbSession, include_archived: bool = False):
    query = db.query(FacelessCharacter).filter(FacelessCharacter.user_id == current_user.id)
    if not include_archived:
        query = query.filter(FacelessCharacter.is_archived == False)  # noqa: E712
    return {"characters": [views.character_view(c) for c in query.order_by(FacelessCharacter.created_at.desc())]}


@router.post("/characters", status_code=status.HTTP_201_CREATED)
@limiter.limit(POST_LIMIT)
def create_character(request: Request, body: CharacterCreate, current_user: CurrentUser, db: DbSession):
    if body.voice_id and body.voice_id not in catalog.VOICE_IDS:
        raise InvalidRequest("Unknown voice.", code="unknown_voice")
    count = db.query(FacelessCharacter).filter(FacelessCharacter.user_id == current_user.id).count()
    if count >= 200:
        raise InvalidRequest("You can keep at most 200 characters. Delete some first.")
    char = FacelessCharacter(
        user_id=current_user.id, name=body.name.strip(), kind=body.kind, role=body.role,
        personality=body.personality, notes=body.notes, style_notes=body.style_notes,
        species=body.species or "human", catchphrase=body.catchphrase, voice_id=body.voice_id,
        voice_settings=body.voice_settings.model_dump() if body.voice_settings else None,
        media=[], safety_flags=[],
    )
    if body.kind == "real_person":
        if body.consent is None:
            raise InvalidRequest("A character based on a real person needs the likeness consent.",
                                 code="consent_required")
        consent.attest(char, accepted=body.consent.accepted, text_version=body.consent.text_version,
                       relationship=body.consent.relationship)
    db.add(char)
    db.flush()
    if char.consent_attested_at:
        activity.log_activity(db, current_user.id, "consent_attested", character_id=char.id,
                              text_version=char.consent_text_version, relationship=char.consent_relationship)
    db.commit()
    db.refresh(char)
    return views.character_view(char)


@router.get("/characters/{char_id}")
async def get_character(char_id: int, current_user: CurrentUser, db: DbSession):
    return views.character_view(_character(db, current_user, char_id))


@router.put("/characters/{char_id}")
@limiter.limit(POST_LIMIT)
def update_character(request: Request, char_id: int, body: CharacterUpdate, current_user: CurrentUser,
                           db: DbSession):
    char = _character(db, current_user, char_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("voice_id") and data["voice_id"] not in catalog.VOICE_IDS:
        raise InvalidRequest("Unknown voice.", code="unknown_voice")
    for field in ("name", "role", "personality", "notes", "style_notes", "species", "catchphrase", "voice_id",
                  "is_archived"):
        if field in data:
            setattr(char, field, data[field])
    if "voice_settings" in data:
        char.voice_settings = data["voice_settings"]
    if "bible" in data:
        bible = data["bible"]
        if bible is not None:
            try:
                from app.services.storyscript import CharacterBible

                bible = CharacterBible.model_validate({**(char.bible or {}), **bible}).model_dump(mode="json")
            except Exception as exc:
                logger.warning(f"Character {char.id} bible failed validation: {exc}")
                raise InvalidRequest("The character details could not be saved because some of them are missing "
                                     "or too long. Check them and try again.")
        char.bible = bible
    if body.consent is not None:
        if char.kind != "real_person":
            raise InvalidRequest("Only real person characters take a consent attestation.")
        consent.attest(char, accepted=body.consent.accepted, text_version=body.consent.text_version,
                       relationship=body.consent.relationship)
        activity.log_activity(db, current_user.id, "consent_attested", character_id=char.id,
                              text_version=char.consent_text_version, relationship=char.consent_relationship)
    purged: list[dict] = []
    if body.revoke_consent:
        consent.revoke(char)
        purged = _take_private_media(char)
        activity.log_activity(db, current_user.id, "consent_revoked", character_id=char.id,
                              files_deleted=len(purged))
    db.commit()
    _delete_files(purged, current_user.id)
    db.refresh(char)
    return views.character_view(char)


@router.post("/characters/{char_id}/consent")
@limiter.limit(POST_LIMIT)
def attest_consent(request: Request, char_id: int, body: ConsentIn, current_user: CurrentUser,
                         db: DbSession):
    char = _character(db, current_user, char_id)
    if char.kind != "real_person":
        raise InvalidRequest("Only real person characters take a consent attestation.")
    consent.attest(char, accepted=body.accepted, text_version=body.text_version, relationship=body.relationship)
    activity.log_activity(db, current_user.id, "consent_attested", character_id=char.id,
                          text_version=char.consent_text_version, relationship=char.consent_relationship)
    db.commit()
    db.refresh(char)
    return views.character_view(char)


@router.post("/characters/{char_id}/consent/revoke")
@limiter.limit(POST_LIMIT)
def revoke_consent(request: Request, char_id: int, current_user: CurrentUser, db: DbSession):
    char = _character(db, current_user, char_id)
    consent.revoke(char)
    # Revoking consent erases the person's photos, videos, frames and sheets:
    # nothing of their likeness stays stored for later generation.
    purged = _take_private_media(char)
    activity.log_activity(db, current_user.id, "consent_revoked", character_id=char.id, files_deleted=len(purged))
    db.commit()
    _delete_files(purged, current_user.id)
    db.refresh(char)
    return views.character_view(char)


@router.delete("/characters/{char_id}")
def delete_character(char_id: int, current_user: CurrentUser, db: DbSession):
    char = _character(db, current_user, char_id)
    active = db.query(FacelessStepRun).filter(
        FacelessStepRun.character_id == char.id, FacelessStepRun.status.in_(orchestrator.ACTIVE)).first()
    if active:
        raise Conflict("A sheet is being made for this character. Try again when it finishes.",
                       code="step_active", extra={"run_id": active.id})
    files = list(char.media or [])
    activity.log_activity(db, current_user.id, "character_deleted", character_id=char.id)
    db.delete(char)
    db.commit()
    _delete_files(files, current_user.id)
    return {"deleted": True}


@router.post("/characters/{char_id}/media")
@limiter.limit(UPLOAD_LIMIT)
def upload_character_media(request: Request, char_id: int, current_user: CurrentUser, db: DbSession,
                                 file: UploadFile = File(...), role: str = Form("reference")):
    char = _character(db, current_user, char_id)
    consent.require_can_upload(char)
    if len(char.media or []) >= catalog.MAX_CHARACTER_MEDIA:
        raise InvalidRequest(f"A character can have at most {catalog.MAX_CHARACTER_MEDIA} media files.")
    if role not in ("reference",):
        role = "reference"
    content = _read_upload(file)
    kind = media.sniff_kind(content)
    new_entries = []
    # A real person's media is stored privately (never served at /static); a
    # fictional character's in the uploads folder.
    try:
        if kind == "image":
            if len(content) > catalog.IMAGE_UPLOAD_MAX_BYTES:
                raise InvalidRequest("Image too large. Upload up to 25 MB.", code="too_large")
            info = media.prepare_image(content)
            stored = media.run_async(media.store_character_bytes(char, info["content"], prefix="fl_char", ext=info["ext"],
                                                                 content_type=info["content_type"]))
            new_entries.append(media.media_entry(stored, kind="image", role=role, width=info["width"],
                                                 height=info["height"]))
        else:
            info = media.prepare_video(content, catalog.CHARACTER_VIDEO_MAX_SECONDS)
            stored = media.run_async(media.store_character_bytes(char, content, prefix="fl_charvid", ext=info["ext"],
                                                                 content_type=info["content_type"]))
            usable = catalog.REFERENCE_VIDEO_MIN_SECONDS <= info["duration"] <= catalog.REFERENCE_VIDEO_MAX_SECONDS
            video_entry = media.media_entry(stored, kind="video", role="source_video", width=info["width"],
                                            height=info["height"], duration=info["duration"],
                                            usable_as_reference=usable)
            new_entries.append(video_entry)
            frames = media.extract_frames(content, info["ext"], info["duration"], catalog.FRAMES_PER_CHARACTER_VIDEO)
            room = catalog.MAX_CHARACTER_MEDIA - len(char.media or []) - 1
            for frame in frames[: max(0, room)]:
                fstored = media.run_async(media.store_character_bytes(char, frame, prefix="fl_charframe", ext=".jpg",
                                                                      content_type="image/jpeg"))
                w, h = media.image_size(frame)
                new_entries.append(media.media_entry(fstored, kind="image", role="frame", width=w, height=h,
                                                     source_id=video_entry["id"]))
    except Exception:
        _delete_files(new_entries, current_user.id)
        raise
    char = apply_row_lock(db.query(FacelessCharacter).filter(FacelessCharacter.id == char.id)).first()
    # Re-checked under the lock: consent may have been revoked, or the media
    # limit reached by a parallel upload, while this file was processed.
    if char is None or consent.consent_status(char) in ("missing", "outdated", "revoked"):
        db.rollback()
        _delete_files(new_entries, current_user.id)
        raise Blocked("Consent for this character changed during the upload. Nothing was stored.",
                      code="consent_required")
    if len(char.media or []) + 1 > catalog.MAX_CHARACTER_MEDIA:
        db.rollback()
        _delete_files(new_entries, current_user.id)
        raise InvalidRequest(f"A character can have at most {catalog.MAX_CHARACTER_MEDIA} media files.")
    media.set_json(char, "media", list(char.media or []) + new_entries)
    activity.log_activity(db, current_user.id, "character_media", character_id=char.id, media_kind=kind,
                          files=len(new_entries))
    db.commit()
    db.refresh(char)
    return views.character_view(char)


@router.get("/characters/{char_id}/media/{media_id}/file")
async def character_media_file(char_id: int, media_id: str, current_user: CurrentUser, db: DbSession):
    """The owner's own copy of one character file. Private (real person) media
    is only ever reachable here; this route checks the owner on every request."""
    char = _character(db, current_user, char_id)
    entry = next((m for m in char.media or [] if m.get("id") == media_id), None)
    if entry is None:
        raise NotFound("Media not found.")
    if not media.is_private(entry):
        return RedirectResponse(media.public_url(entry, current_user.id), status_code=302)
    content = await media.read_bytes(entry, current_user.id)
    if content is None:
        raise NotFound("The file is missing.")
    ctype = media.content_type_for(os.path.splitext(entry["file"])[1])
    if not ctype.startswith(("image/", "video/")):
        ctype = "application/octet-stream"
    return Response(content=content, media_type=ctype, headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline", "Content-Security-Policy": "default-src 'none'; sandbox",
    })


@router.delete("/characters/{char_id}/media/{media_id}")
def delete_character_media(char_id: int, media_id: str, current_user: CurrentUser, db: DbSession):
    char = _character(db, current_user, char_id)
    entries = list(char.media or [])
    removed = [m for m in entries if m.get("id") == media_id or m.get("source_id") == media_id]
    if not any(m.get("id") == media_id for m in entries):
        raise NotFound("Media not found.")
    media.set_json(char, "media", [m for m in entries if m not in removed])
    db.commit()
    _delete_files(removed, current_user.id)
    db.refresh(char)
    return views.character_view(char)


@router.post("/characters/{char_id}/bible")
@limiter.limit(POST_LIMIT)
def make_bible(request: Request, char_id: int, current_user: CurrentUser, db: DbSession):
    char = _character(db, current_user, char_id)
    if char.kind == "real_person":
        consent.require_can_upload(char)
    activity.check_rate(db, current_user.id, "bible", catalog.BIBLES_PER_HOUR, label="character bibles")
    images = [m for m in char.media or [] if m.get("kind") == "image"][:4]
    # The bytes go to the vision model as downscaled data URLs, so private
    # (real person) photos never need a link here.
    urls = media.run_async(media.vision_data_urls(images, current_user.id))
    activity.log_activity(db, current_user.id, "bible", character_id=char.id)
    db.commit()
    bible = media.run_async(scripts.describe(db, char, urls))
    char = _character(db, current_user, char_id)
    char.bible = bible
    char.safety_flags = list((bible or {}).get("safety_flags") or [])
    if consent.possible_minor(char) and char.kind == "real_person":
        activity.log_activity(db, current_user.id, "blocked_possible_minor", character_id=char.id)
    db.commit()
    db.refresh(char)
    return views.character_view(char)


@router.get("/characters/{char_id}/sheet/quote")
def quote_sheet(char_id: int, current_user: CurrentUser, db: DbSession, options: Optional[str] = None):
    char = _character(db, current_user, char_id)
    return pricing.quote_view(pricing.plan_sheet(char, _parse_options(options)))


@router.post("/characters/{char_id}/sheet", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(POST_LIMIT)
def make_sheet(request: Request, response: Response, char_id: int, body: SheetRequest,
               current_user: CurrentUser, db: DbSession,
               idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")):
    char = _character(db, current_user, char_id)
    run, created = orchestrator.start_sheet(db, current_user.id, char, body.options,
                                            body.idempotency_key or idempotency_key, body.expected_usd)
    if not created:
        response.status_code = status.HTTP_200_OK
    return orchestrator.run_view(run)


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------

def _series_counts(db, user_id: int) -> dict:
    rows = db.query(FacelessProject.series_id, func.count(FacelessProject.id)).filter(
        FacelessProject.user_id == user_id, FacelessProject.series_id.isnot(None)
    ).group_by(FacelessProject.series_id).all()
    return {sid: n for sid, n in rows}


@router.get("/series")
def list_series(current_user: CurrentUser, db: DbSession):
    counts = _series_counts(db, current_user.id)
    rows = db.query(FacelessSeries).filter(FacelessSeries.user_id == current_user.id) \
        .order_by(FacelessSeries.created_at.desc()).all()
    return {"series": [views.series_view(s, counts.get(s.id, 0)) for s in rows]}


@router.post("/series", status_code=status.HTTP_201_CREATED)
@limiter.limit(POST_LIMIT)
def create_series(request: Request, body: SeriesCreate, current_user: CurrentUser, db: DbSession):
    consent.load_cast(db, current_user.id, body.cast_ids)
    if body.template_id:
        scripts.require_template(body.template_id)
    if body.style and body.style not in catalog.STYLE_PROMPTS:
        raise InvalidRequest("Unknown visual style.", code="unknown_style")
    series = FacelessSeries(
        user_id=current_user.id, title=body.title.strip(), logline=body.logline, template_id=body.template_id,
        style=body.style, tone=body.tone, cast_ids=list(body.cast_ids), world_notes=body.world_notes,
        rules=[r[:300] for r in body.rules][:30], episode_memory=[],
    )
    db.add(series)
    db.commit()
    db.refresh(series)
    return views.series_view(series, 0)


@router.get("/series/{series_id}")
def get_series(series_id: int, current_user: CurrentUser, db: DbSession):
    series = _series(db, current_user, series_id)
    projects = db.query(FacelessProject).filter(
        FacelessProject.user_id == current_user.id, FacelessProject.series_id == series.id
    ).order_by(FacelessProject.created_at.desc()).all()
    thumbs = views.summary_thumbnails(db, projects)
    return {**views.series_view(series, len(projects)),
            "projects": [views.project_summary(p, thumbs.get(p.id)) for p in projects]}


def _memory_entry(entry: dict) -> dict:
    """One episode summary as the client may edit it: known keys, bounded text
    (it is fed back into every later draft of the series)."""
    out = {}
    if isinstance(entry.get("project_id"), int):
        out["project_id"] = entry["project_id"]
    for key, limit in (("title", 200), ("premise", 1000), ("outcome", 1000), ("situation", 500)):
        value = entry.get(key)
        if isinstance(value, str):
            out[key] = value[:limit]
    return out


@router.put("/series/{series_id}")
@limiter.limit(POST_LIMIT)
def update_series(request: Request, series_id: int, body: SeriesUpdate, current_user: CurrentUser, db: DbSession):
    series = _series(db, current_user, series_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("cast_ids") is not None:
        consent.load_cast(db, current_user.id, data["cast_ids"])
    if data.get("template_id"):
        scripts.require_template(data["template_id"])
    if data.get("style") and data["style"] not in catalog.STYLE_PROMPTS:
        raise InvalidRequest("Unknown visual style.", code="unknown_style")
    for field, value in data.items():
        if field == "rules" and value is not None:
            value = [r[:300] for r in value][:30]
        if field == "episode_memory" and value is not None:
            value = [_memory_entry(m) for m in value[-scripts.MAX_EPISODE_MEMORY:] if isinstance(m, dict)]
        setattr(series, field, value)
    db.commit()
    db.refresh(series)
    return views.series_view(series, _series_counts(db, current_user.id).get(series.id, 0))


@router.delete("/series/{series_id}")
def delete_series(series_id: int, current_user: CurrentUser, db: DbSession):
    series = _series(db, current_user, series_id)
    db.query(FacelessProject).filter(FacelessProject.series_id == series.id).update(
        {FacelessProject.series_id: None}, synchronize_session=False)
    db.delete(series)
    db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@router.get("/projects")
def list_projects(current_user: CurrentUser, db: DbSession, series_id: Optional[int] = None,
                  page: int = 1, page_size: int = 20):
    page = max(1, page)
    page_size = min(max(1, page_size), 50)
    query = db.query(FacelessProject).filter(FacelessProject.user_id == current_user.id)
    if series_id is not None:
        query = query.filter(FacelessProject.series_id == series_id)
    total = query.count()
    rows = query.order_by(FacelessProject.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    thumbs = views.summary_thumbnails(db, rows)
    return {"projects": [views.project_summary(p, thumbs.get(p.id)) for p in rows], "total": total, "page": page,
            "page_size": page_size}


@router.post("/projects", status_code=status.HTTP_201_CREATED)
@limiter.limit(POST_LIMIT)
def create_project(request: Request, body: ProjectCreate, current_user: CurrentUser, db: DbSession):
    tpl = scripts.require_template(body.template_id)
    data = body.model_dump()
    _check_choices(data)
    series = _series(db, current_user, body.series_id) if body.series_id else None
    cast_ids = list(body.cast_ids) or ([int(i) for i in series.cast_ids or []] if series else [])
    consent.load_cast(db, current_user.id, cast_ids)
    aspect = body.aspect or tpl.get("default_aspect") or "9:16"
    length = body.length_seconds or int((tpl.get("length") or {}).get("default_seconds") or 60)
    _check_length(aspect, length, tpl)
    count = db.query(FacelessProject).filter(FacelessProject.user_id == current_user.id).count()
    if count >= 500:
        raise InvalidRequest("You can keep at most 500 projects. Delete some first.")
    project = FacelessProject(
        user_id=current_user.id, series_id=series.id if series else None,
        title=(body.title or "Untitled").strip()[:200] or "Untitled", idea=body.idea,
        template_id=body.template_id, aspect=aspect, length_seconds=length, language=body.language,
        style=body.style or (series.style if series else None), narrator_voice=body.narrator_voice,
        voice_settings=body.voice_settings.model_dump() if body.voice_settings else None,
        caption_preset=body.caption_preset or tpl.get("caption_preset") or "bold_pop",
        music_mood=body.music_mood or "template", cast_ids=cast_ids,
        facts=[f.model_dump() for f in body.facts],
        settings=body.settings.model_dump(exclude_none=True) if body.settings else {},
        status="draft", scene_assets={}, usd_by_step={},
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return views.project_view(db, project)


@router.get("/projects/{project_id}")
def get_project(project_id: int, current_user: CurrentUser, db: DbSession):
    return views.project_view(db, _project(db, current_user, project_id))


@router.put("/projects/{project_id}")
@limiter.limit(POST_LIMIT)
def update_project(request: Request, project_id: int, body: ProjectUpdate, current_user: CurrentUser, db: DbSession):
    project = _project(db, current_user, project_id)
    data = body.model_dump(exclude_unset=True)
    _check_choices(data)
    tpl = scripts.require_template(data.get("template_id") or project.template_id)
    if "series_id" in data and data["series_id"] is not None:
        _series(db, current_user, data["series_id"])
    if data.get("cast_ids") is not None:
        consent.load_cast(db, current_user.id, data["cast_ids"])
    aspect = data.get("aspect") or project.aspect
    length = data.get("length_seconds") or project.length_seconds
    if "aspect" in data or "length_seconds" in data or "template_id" in data:
        _check_length(aspect, length, tpl)
    project = _project(db, current_user, project_id, lock=True)
    for field in ("title", "idea", "template_id", "series_id", "aspect", "length_seconds", "language", "style",
                  "narrator_voice", "caption_preset", "music_mood", "cast_ids"):
        if field in data:
            setattr(project, field, data[field])
    if "voice_settings" in data:
        project.voice_settings = data["voice_settings"]
    if "facts" in data:
        project.facts = data["facts"] or []
    if "settings" in data:
        merged = dict(project.settings or {})
        merged.update({k: v for k, v in (data["settings"] or {}).items() if v is not None})
        media.set_json(project, "settings", merged)
    db.commit()
    db.refresh(project)
    return views.project_view(db, project)


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, current_user: CurrentUser, db: DbSession):
    # Locked so a concurrent step start (which locks the project too) cannot queue a run
    # that this delete then removes.
    project = _project(db, current_user, project_id, lock=True)
    active = db.query(FacelessStepRun).filter(
        FacelessStepRun.project_id == project.id, FacelessStepRun.status.in_(orchestrator.ACTIVE)).first()
    if active:
        run_id = active.id
        db.rollback()
        raise Conflict("A step is running for this project. Cancel it or wait for it to finish.",
                       code="step_active", extra={"run_id": run_id})
    files = []
    for assets in (project.scene_assets or {}).values():
        files += [x for x in (assets.get("stills") or []) + (assets.get("clips") or []) + (assets.get("voice") or []) if x]
        if assets.get("user_media"):
            files.append(assets["user_media"])
    files += (project.music or {}).get("tracks") or []
    # Renders and thumbnails ("its stills, clips, audio and renders" in the
    # confirmation), collected before the step runs that list them go.
    files += _take_project_outputs(db, project)
    series = db.query(FacelessSeries).filter(FacelessSeries.id == project.series_id).first() \
        if project.series_id else None
    if series is not None:
        series.episode_memory = [m for m in series.episode_memory or [] if m.get("project_id") != project.id]
    db.query(FacelessScriptVersion).filter(FacelessScriptVersion.project_id == project.id).delete(
        synchronize_session=False)
    db.query(FacelessStepRun).filter(FacelessStepRun.project_id == project.id).delete(synchronize_session=False)
    db.delete(project)
    db.commit()
    _delete_files(files, current_user.id)
    return {"deleted": True}


# --- Script -----------------------------------------------------------------

def _checks_and_memory(db, project: FacelessProject) -> None:
    chars = pricing.build_ctx(db, project).chars
    scripts.run_checks(db, project, chars)
    if project.series_id:
        series = db.query(FacelessSeries).filter(FacelessSeries.id == project.series_id).first()
        scripts.remember_episode(series, project)


def _queue_draft(db, user, project: FacelessProject, body: ScriptDraftRequest, key: str | None,
                 response: Response) -> dict:
    """A draft for the scheduler: under the project lock, so a double click and a step that
    is starting are both seen."""
    project_id, created = project.id, False
    try:
        orchestrator.lock_project(db, project_id)
        existing = db.query(FacelessStepRun).filter(
            FacelessStepRun.user_id == user.id, FacelessStepRun.idempotency_key == key).first() if key else None
        if existing is None:
            orchestrator.require_idle(db, project_id)
            activity.check_rate(db, user.id, "draft", catalog.DRAFTS_PER_HOUR, label="script drafts")
        run, created = script_job.start_script_run(db, user.id, project, body.idea, key)
        if created:
            activity.log_activity(db, user.id, "draft", project_id=project_id, run_id=run.id)
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    response.status_code = status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK
    return orchestrator.run_view(run)


def _draft_now(db, user, project: FacelessProject, body: ScriptDraftRequest) -> dict:
    """A draft inside this request. Holds one inline draft per project, and no write during
    the LLM call."""
    project_id = project.id
    with orchestrator.inline_draft(project_id):
        try:
            project = _project(db, user, project_id, lock=True)
            orchestrator.require_no_active_run(db, project_id)
            activity.check_rate(db, user.id, "draft", catalog.DRAFTS_PER_HOUR, label="script drafts")
            if body.idea is not None:
                project.idea = body.idea
            activity.log_activity(db, user.id, "draft", project_id=project_id)
            db.commit()
            chars = consent.load_cast(db, user.id, project.cast_ids)
            series = db.query(FacelessSeries).filter(FacelessSeries.id == project.series_id).first() \
                if project.series_id else None
            script = media.run_async(scripts.draft(db, project, chars, series))
            project = _project(db, user, project_id, lock=True)
            orchestrator.require_no_active_run(db, project_id)
            scripts.apply_script(db, project, script, "draft", chars)
            db.commit()
        except Exception:
            db.rollback()
            raise
    db.refresh(project)
    return views.project_view(db, project)


@router.post("/projects/{project_id}/script")
@limiter.limit("10/minute")
def draft_script(request: Request, response: Response, project_id: int, body: ScriptDraftRequest,
                 current_user: CurrentUser, db: DbSession,
                 idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")):
    """Draft a new script version. Short formats are drafted inline (200, Project).
    Long-form projects (over 90 s or a long-form template), or background: true, are queued
    for the scheduler (202, StepRun with step "script"): poll GET /runs/{id}, then GET
    /projects/{id}. 409 while another draft or any step is running: a new script replaces
    every scene."""
    project = _project(db, current_user, project_id)
    tpl = scripts.require_template(project.template_id)
    if body.background or scripts.is_long_form(project, tpl):
        return _queue_draft(db, current_user, project, body, body.idempotency_key or idempotency_key, response)
    return _draft_now(db, current_user, project, body)


@router.put("/projects/{project_id}/script")
@limiter.limit(POST_LIMIT)
def save_script(request: Request, project_id: int, body: ScriptSave, current_user: CurrentUser, db: DbSession):
    project = _project(db, current_user, project_id)
    script = scripts.dump(scripts.validate_script(body.script))
    scripts.check_script_limits(script)
    chars = pricing.build_ctx(db, project).chars
    project = _project(db, current_user, project_id, lock=True)
    orchestrator.require_same_scenes(db, project, script)
    scripts.apply_script(db, project, script, "edit", chars)
    db.commit()
    db.refresh(project)
    return views.project_view(db, project)


@router.get("/projects/{project_id}/script/versions")
def list_versions(project_id: int, current_user: CurrentUser, db: DbSession):
    project = _project(db, current_user, project_id)
    rows = db.query(FacelessScriptVersion).filter(FacelessScriptVersion.project_id == project.id) \
        .order_by(FacelessScriptVersion.version.desc()).all()
    return {"versions": [{"version": r.version, "source": r.source, "created_at": r.created_at.isoformat(),
                          "title": (r.script or {}).get("title")} for r in rows],
            "current": project.script_version}


@router.get("/projects/{project_id}/script/versions/{version}")
def get_version(project_id: int, version: int, current_user: CurrentUser, db: DbSession):
    project = _project(db, current_user, project_id)
    row = db.query(FacelessScriptVersion).filter(
        FacelessScriptVersion.project_id == project.id, FacelessScriptVersion.version == version).first()
    if row is None:
        raise NotFound("Version not found.")
    return {"version": row.version, "source": row.source, "created_at": row.created_at.isoformat(),
            "script": row.script}


@router.post("/projects/{project_id}/script/versions/{version}/restore")
@limiter.limit(POST_LIMIT)
def restore_version(request: Request, project_id: int, version: int, current_user: CurrentUser, db: DbSession):
    project = _project(db, current_user, project_id)
    row = db.query(FacelessScriptVersion).filter(
        FacelessScriptVersion.project_id == project.id, FacelessScriptVersion.version == version).first()
    if row is None:
        raise NotFound("Version not found.")
    script = row.script
    project = _project(db, current_user, project_id, lock=True)
    orchestrator.require_no_running_steps(db, project_id, "restoring a version")
    scripts.save_version(db, project, script, "restore")
    db.flush()
    _checks_and_memory(db, project)
    db.commit()
    db.refresh(project)
    return views.project_view(db, project)


def _save_revision(db, user, project_id: int, scene_id: str, scene: dict, base_version: int) -> dict:
    project = _project(db, user, project_id)
    if project.script_version != base_version:
        raise Conflict("The script changed while the scene was being revised. Try again.", code="script_changed")
    new_script = dict(project.script)
    new_script["scenes"] = [
        {**scene, "id": scene_id} if str(s.get("id")) == str(scene_id) else s for s in new_script.get("scenes") or []
    ]
    new_script = scripts.dump(scripts.validate_script(new_script))
    project = _project(db, user, project_id, lock=True)
    if project.script_version != base_version:
        db.rollback()
        raise Conflict("The script changed while the scene was being revised. Try again.", code="script_changed")
    scripts.save_version(db, project, new_script, "revise")
    db.flush()
    _checks_and_memory(db, project)
    db.commit()
    db.refresh(project)
    return views.project_view(db, project)


@router.post("/projects/{project_id}/scenes/{scene_id}/revise")
@limiter.limit("20/minute")
def revise_scene(request: Request, project_id: int, scene_id: str, body: SceneRevise,
                 current_user: CurrentUser, db: DbSession):
    project = _project(db, current_user, project_id)
    if not project.script or scene_by_id(project.script, scene_id) is None:
        raise NotFound("Scene not found.")
    activity.check_rate(db, current_user.id, "revise", catalog.REVISIONS_PER_HOUR, label="scene revisions")
    activity.log_activity(db, current_user.id, "revise", project_id=project.id, scene_id=scene_id)
    db.commit()
    base_version = project.script_version
    chars = pricing.build_ctx(db, project).chars
    scene = media.run_async(scripts.revise(db, project.script, scene_id, body.instruction, chars, current_user.id))
    return _save_revision(db, current_user, project_id, scene_id, scene, base_version)


# --- Bring your own media ---------------------------------------------------

@router.post("/projects/{project_id}/scenes/{scene_id}/media")
@limiter.limit(UPLOAD_LIMIT)
def upload_scene_media(request: Request, project_id: int, scene_id: str, current_user: CurrentUser,
                       db: DbSession, file: UploadFile = File(...)):
    project = _project(db, current_user, project_id)
    if not project.script or scene_by_id(project.script, scene_id) is None:
        raise NotFound("Scene not found.")
    content = _read_upload(file)
    kind = media.sniff_kind(content)
    if kind == "image":
        if len(content) > catalog.IMAGE_UPLOAD_MAX_BYTES:
            raise InvalidRequest("Image too large. Upload up to 25 MB.", code="too_large")
        info = media.prepare_image(content)
        stored = media.run_async(media.store_bytes(info["content"], user_id=current_user.id, storage="uploads",
                                                   prefix="fl_scene", ext=info["ext"], content_type=info["content_type"]))
        entry = media.media_entry(stored, kind="image", role="user_media", width=info["width"],
                                  height=info["height"])
    else:
        info = media.prepare_video(content, catalog.SCENE_VIDEO_MAX_SECONDS)
        stored = media.run_async(media.store_bytes(content, user_id=current_user.id, storage="uploads", prefix="fl_scenevid",
                                                   ext=info["ext"], content_type=info["content_type"]))
        entry = media.media_entry(stored, kind="video", role="user_media", width=info["width"],
                                  height=info["height"], duration=info["duration"])
    project = _project(db, current_user, project_id, lock=True)
    assets = dict(project.scene_assets or {})
    scene = dict(assets.get(str(scene_id)) or {})
    old = scene.get("user_media")
    scene["user_media"] = entry
    assets[str(scene_id)] = scene
    media.set_json(project, "scene_assets", assets)
    activity.log_activity(db, current_user.id, "scene_media", project_id=project.id, scene_id=scene_id, media_kind=kind)
    db.commit()
    if old:
        _delete_files([old], current_user.id)
    db.refresh(project)
    return views.project_view(db, project)


@router.delete("/projects/{project_id}/scenes/{scene_id}/media")
def delete_scene_media(project_id: int, scene_id: str, current_user: CurrentUser, db: DbSession):
    project = _project(db, current_user, project_id, lock=True)
    assets = dict(project.scene_assets or {})
    scene = dict(assets.get(str(scene_id)) or {})
    old = scene.pop("user_media", None)
    if old is None:
        db.rollback()
        raise NotFound("This scene has no uploaded media.")
    assets[str(scene_id)] = scene
    media.set_json(project, "scene_assets", assets)
    db.commit()
    _delete_files([old], current_user.id)
    db.refresh(project)
    return views.project_view(db, project)


# --- Quotes and steps -------------------------------------------------------

def _quote(db, project, step: str, scene_ids, options) -> dict:
    ctx = pricing.build_ctx(db, project)
    return pricing.quote_view(pricing.plan_step(ctx, step, scene_ids, options))


@router.get("/projects/{project_id}/quote")
def get_quote(project_id: int, step: str, current_user: CurrentUser, db: DbSession,
              scene_ids: Optional[str] = None, options: Optional[str] = None):
    project = _project(db, current_user, project_id)
    ids = [s.strip() for s in scene_ids.split(",") if s.strip()] if scene_ids else None
    return _quote(db, project, step, ids, _parse_options(options))


@router.post("/projects/{project_id}/quote")
def post_quote(project_id: int, body: QuoteRequest, current_user: CurrentUser, db: DbSession):
    project = _project(db, current_user, project_id)
    return _quote(db, project, body.step, body.scene_ids, body.options or {})


@router.post("/projects/{project_id}/steps/{step}", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(POST_LIMIT)
def start_step(request: Request, response: Response, project_id: int, step: str, body: StepRequest,
               current_user: CurrentUser, db: DbSession,
               idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")):
    if step not in catalog.STEPS:
        raise InvalidRequest(f"Unknown step '{step}'. Steps: {', '.join(catalog.STEPS)}.", code="unknown_step")
    project = _project(db, current_user, project_id)
    run, created = orchestrator.start_step(db, current_user.id, project, step, body.scene_ids, body.options,
                                           body.idempotency_key or idempotency_key, body.expected_usd)
    if not created:
        response.status_code = status.HTTP_200_OK
    return orchestrator.run_view(run)


@router.get("/projects/{project_id}/runs")
def list_runs(project_id: int, current_user: CurrentUser, db: DbSession, limit: int = 50):
    project = _project(db, current_user, project_id)
    rows = db.query(FacelessStepRun).filter(FacelessStepRun.project_id == project.id) \
        .order_by(FacelessStepRun.created_at.desc()).limit(min(max(1, limit), 200)).all()
    return {"runs": [orchestrator.run_view(r) for r in rows]}


@router.get("/runs/{run_id}")
def get_run(run_id: int, current_user: CurrentUser, db: DbSession):
    return orchestrator.run_view(_run(db, current_user, run_id))


@router.post("/runs/{run_id}/cancel")
@limiter.limit(POST_LIMIT)
def cancel_run(request: Request, run_id: int, current_user: CurrentUser, db: DbSession):
    run = _run(db, current_user, run_id)
    return orchestrator.run_view(orchestrator.cancel_run(db, run))


# --- Reports and packaging --------------------------------------------------

def _fresh_report(db, user, project_id: int, field: str, refresh: bool) -> dict:
    project = _project(db, user, project_id)
    if not project.script:
        raise InvalidRequest("Draft a script first.", code="no_script")
    report = getattr(project, field) or {}
    if refresh or report.get("script_version") != project.script_version:
        project = _project(db, user, project_id, lock=True)
        _checks_and_memory(db, project)
        db.commit()
        report = getattr(project, field) or {}
    return report


@router.get("/projects/{project_id}/originality")
def get_originality(project_id: int, current_user: CurrentUser, db: DbSession, refresh: bool = False):
    return _fresh_report(db, current_user, project_id, "originality", refresh)


@router.get("/projects/{project_id}/compliance")
def get_compliance(project_id: int, current_user: CurrentUser, db: DbSession, refresh: bool = False):
    return _fresh_report(db, current_user, project_id, "compliance", refresh)


def _save_packaging(db, user, project_id: int, packaging: dict) -> tuple[dict, FacelessProject]:
    project = _project(db, user, project_id, lock=True)
    packaging = {**(packaging or {}), "script_version": project.script_version,
                 "created_at": datetime.utcnow().isoformat()}
    media.set_json(project, "packaging", packaging)
    db.commit()
    return packaging, project


@router.post("/projects/{project_id}/package")
@limiter.limit("10/minute")
def make_package(request: Request, project_id: int, body: PackageRequest, current_user: CurrentUser,
                 db: DbSession, idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")):
    project = _project(db, current_user, project_id)
    if not project.script:
        raise InvalidRequest("Draft a script first.", code="no_script")
    options = dict(body.options or {})
    if body.texts:
        options["texts"] = body.texts
    if body.thumbnails and body.expected_usd is not None:
        # Checked before the LLM call, so a refused request costs nothing.
        plan = pricing.plan_step(pricing.build_ctx(db, project), "thumbnails", None, options)
        orchestrator.check_expected(plan, body.expected_usd)
    activity.check_rate(db, current_user.id, "package", catalog.PACKAGES_PER_HOUR, label="packaging requests")
    activity.log_activity(db, current_user.id, "package", project_id=project.id)
    db.commit()
    chars = pricing.build_ctx(db, project).chars
    made = media.run_async(scripts.make_package(db, project.script, project.aspect, chars, current_user.id))
    packaging, project = _save_packaging(db, current_user, project_id, made)
    run = None
    if body.thumbnails:
        run, _created = orchestrator.start_step(db, current_user.id, project, "thumbnails", None, options,
                                                body.idempotency_key or idempotency_key, body.expected_usd)
    return {"packaging": packaging, "run": orchestrator.run_view(run) if run else None}


@router.get("/projects/{project_id}/log")
def get_log(project_id: int, current_user: CurrentUser, db: DbSession):
    project = _project(db, current_user, project_id)
    rows = db.query(FacelessActivity).filter(
        FacelessActivity.user_id == current_user.id, FacelessActivity.project_id == project.id
    ).order_by(FacelessActivity.created_at).limit(1000).all()
    return {"events": [{"kind": r.kind, "detail": r.detail, "created_at": r.created_at.isoformat()} for r in rows]}
