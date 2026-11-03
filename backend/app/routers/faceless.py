"""Characters and catalogues (/api/faceless). Story Room's Cast tab and the character
editor use these. The Faceless project pipeline is deferred.

Errors: every error here is JSON {"detail": "<message>", "code": "<code>", ...extra}.
Codes: consent_required (403, extra: characters), rate_limited (429), invalid_input,
too_large, unknown_voice (400), llm_not_configured (503), invalid_llm_output and
llm_call_failed (502).

Catalogues
  GET  /templates          {templates: [storyscript.Template], styles: [{id, label, prompt}]}
  GET  /voices             {voices: [{id, gender, accent, tone}], default_narrator}
  GET  /music-moods        {moods: [{id, label, positive, negative}]}
  GET  /caption-styles     {styles: [{id, label, description}]}
  GET  /config             {aspects, limits, consent: {version, text, relationships}}

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

  Character = {id, name, kind, role, personality, notes, style_notes, species, catchphrase,
               consent: {status: not_required|missing|outdated|valid|revoked, attested_at,
               text_version, relationship, revoked_at, current_version}, bible, media:
               [{id, kind: image|video, role: reference|sheet|source_video|frame, url, width,
               height, duration, source_id, usable_as_reference, created_at}], voice_id,
               voice_settings, safety_flags, can_generate, block_reason, is_archived,
               created_at, updated_at}
"""

import logging
import os

from fastapi import APIRouter, File, Form, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse

from app.database import apply_row_lock
from app.dependencies import CurrentUser, DbSession
from app.middleware.rate_limiter import limiter
from app.models.faceless import FacelessCharacter
from app.schemas.faceless import CharacterCreate, CharacterUpdate, ConsentIn
from app.services.faceless import activity, catalog, consent, media, views
from app.services.faceless.errors import Blocked, InvalidRequest, NotFound, Unavailable, UpstreamError

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


async def _delete_files(entries: list[dict], user_id: int) -> None:
    for entry in entries:
        await media.delete_stored(entry, user_id)


async def _read_upload(file: UploadFile) -> bytes:
    content = await file.read(catalog.VIDEO_UPLOAD_MAX_BYTES + 1)
    if not content:
        raise InvalidRequest("The file is empty.")
    if len(content) > catalog.VIDEO_UPLOAD_MAX_BYTES:
        raise InvalidRequest("File too large. Images up to 25 MB, videos up to 100 MB.", code="too_large")
    return content


async def _describe(db, char: FacelessCharacter, image_urls: list[str]) -> dict:
    """The character bible from the script engine, with its errors as sentences."""
    from app.services import storyscript as ss

    try:
        bible = await ss.describe_character(db, name=char.name, image_urls=image_urls, notes=char.notes or None,
                                            user_id=char.user_id)
    except ss.LLMNotConfigured as exc:
        logger.error(f"Script engine is not configured: {exc}")
        raise Unavailable("The AI writer is not available right now. Please try again later.",
                          code="llm_not_configured")
    except ss.InvalidLLMOutput as exc:
        logger.warning(f"Script engine returned an invalid result: {exc} ({exc.last_error})")
        raise UpstreamError("The AI writer returned an invalid result. Please try again.",
                            code="invalid_llm_output")
    except ss.LLMCallFailed as exc:
        logger.warning(f"Script engine call failed: {exc}", exc_info=True)
        raise UpstreamError("The AI writer could not be reached. Please try again.", code="llm_call_failed")
    except ss.StoryScriptInputError as exc:
        raise InvalidRequest(str(exc), code="invalid_input")
    return bible.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Catalogues
# ---------------------------------------------------------------------------

@router.get("/templates")
async def list_templates(current_user: CurrentUser):
    from app.services import storyscript as ss

    return {"templates": [t.model_dump(mode="json") for t in ss.list_templates()], "styles": catalog.STYLES}


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
    return {
        "aspects": list(catalog.ASPECTS),
        "limits": {
            "max_cast": catalog.MAX_CAST,
            "max_character_media": catalog.MAX_CHARACTER_MEDIA,
            "image_upload_max_bytes": catalog.IMAGE_UPLOAD_MAX_BYTES,
            "video_upload_max_bytes": catalog.VIDEO_UPLOAD_MAX_BYTES,
            "character_video_max_seconds": catalog.CHARACTER_VIDEO_MAX_SECONDS,
        },
        "consent": {"version": catalog.CONSENT_TEXT_VERSION, "text": catalog.CONSENT_TEXT,
                    "relationships": list(catalog.CONSENT_RELATIONSHIPS)},
    }


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
async def create_character(request: Request, body: CharacterCreate, current_user: CurrentUser, db: DbSession):
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
async def update_character(request: Request, char_id: int, body: CharacterUpdate, current_user: CurrentUser,
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
    await _delete_files(purged, current_user.id)
    db.refresh(char)
    return views.character_view(char)


@router.post("/characters/{char_id}/consent")
@limiter.limit(POST_LIMIT)
async def attest_consent(request: Request, char_id: int, body: ConsentIn, current_user: CurrentUser,
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
async def revoke_consent(request: Request, char_id: int, current_user: CurrentUser, db: DbSession):
    char = _character(db, current_user, char_id)
    consent.revoke(char)
    # Revoking consent erases the person's photos, videos, frames and sheets:
    # nothing of their likeness stays stored for later generation.
    purged = _take_private_media(char)
    activity.log_activity(db, current_user.id, "consent_revoked", character_id=char.id, files_deleted=len(purged))
    db.commit()
    await _delete_files(purged, current_user.id)
    db.refresh(char)
    return views.character_view(char)


@router.delete("/characters/{char_id}")
async def delete_character(char_id: int, current_user: CurrentUser, db: DbSession):
    char = _character(db, current_user, char_id)
    files = list(char.media or [])
    activity.log_activity(db, current_user.id, "character_deleted", character_id=char.id)
    db.delete(char)
    db.commit()
    for entry in files:
        await media.delete_stored(entry, current_user.id)
    return {"deleted": True}


@router.post("/characters/{char_id}/media")
@limiter.limit(UPLOAD_LIMIT)
async def upload_character_media(request: Request, char_id: int, current_user: CurrentUser, db: DbSession,
                                 file: UploadFile = File(...), role: str = Form("reference")):
    char = _character(db, current_user, char_id)
    consent.require_can_upload(char)
    if len(char.media or []) >= catalog.MAX_CHARACTER_MEDIA:
        raise InvalidRequest(f"A character can have at most {catalog.MAX_CHARACTER_MEDIA} media files.")
    if role not in ("reference",):
        role = "reference"
    content = await _read_upload(file)
    kind = media.sniff_kind(content)
    new_entries = []
    # A real person's media is stored privately (never served at /static); a
    # fictional character's in the uploads folder.
    try:
        if kind == "image":
            if len(content) > catalog.IMAGE_UPLOAD_MAX_BYTES:
                raise InvalidRequest("Image too large. Upload up to 25 MB.", code="too_large")
            info = await run_in_threadpool(media.prepare_image, content)
            stored = await media.store_character_bytes(char, info["content"], prefix="fl_char", ext=info["ext"],
                                                       content_type=info["content_type"])
            new_entries.append(media.media_entry(stored, kind="image", role=role, width=info["width"],
                                                 height=info["height"]))
        else:
            info = await run_in_threadpool(media.prepare_video, content, catalog.CHARACTER_VIDEO_MAX_SECONDS)
            stored = await media.store_character_bytes(char, content, prefix="fl_charvid", ext=info["ext"],
                                                       content_type=info["content_type"])
            usable = catalog.REFERENCE_VIDEO_MIN_SECONDS <= info["duration"] <= catalog.REFERENCE_VIDEO_MAX_SECONDS
            video_entry = media.media_entry(stored, kind="video", role="source_video", width=info["width"],
                                            height=info["height"], duration=info["duration"],
                                            usable_as_reference=usable)
            new_entries.append(video_entry)
            frames = await run_in_threadpool(media.extract_frames, content, info["ext"], info["duration"],
                                             catalog.FRAMES_PER_CHARACTER_VIDEO)
            room = catalog.MAX_CHARACTER_MEDIA - len(char.media or []) - 1
            for frame in frames[: max(0, room)]:
                fstored = await media.store_character_bytes(char, frame, prefix="fl_charframe", ext=".jpg",
                                                            content_type="image/jpeg")
                w, h = media.image_size(frame)
                new_entries.append(media.media_entry(fstored, kind="image", role="frame", width=w, height=h,
                                                     source_id=video_entry["id"]))
    except Exception:
        await _delete_files(new_entries, current_user.id)
        raise
    char = apply_row_lock(db.query(FacelessCharacter).filter(FacelessCharacter.id == char.id)).first()
    # Re-checked under the lock: consent may have been revoked, or the media
    # limit reached by a parallel upload, while this file was processed.
    if char is None or consent.consent_status(char) in ("missing", "outdated", "revoked"):
        db.rollback()
        await _delete_files(new_entries, current_user.id)
        raise Blocked("Consent for this character changed during the upload. Nothing was stored.",
                      code="consent_required")
    if len(char.media or []) + 1 > catalog.MAX_CHARACTER_MEDIA:
        db.rollback()
        await _delete_files(new_entries, current_user.id)
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
async def delete_character_media(char_id: int, media_id: str, current_user: CurrentUser, db: DbSession):
    char = _character(db, current_user, char_id)
    entries = list(char.media or [])
    removed = [m for m in entries if m.get("id") == media_id or m.get("source_id") == media_id]
    if not any(m.get("id") == media_id for m in entries):
        raise NotFound("Media not found.")
    media.set_json(char, "media", [m for m in entries if m not in removed])
    db.commit()
    for entry in removed:
        await media.delete_stored(entry, current_user.id)
    db.refresh(char)
    return views.character_view(char)


@router.post("/characters/{char_id}/bible")
@limiter.limit(POST_LIMIT)
async def make_bible(request: Request, char_id: int, current_user: CurrentUser, db: DbSession):
    char = _character(db, current_user, char_id)
    if char.kind == "real_person":
        consent.require_can_upload(char)
    activity.check_rate(db, current_user.id, "bible", catalog.BIBLES_PER_HOUR, label="character bibles")
    images = [m for m in char.media or [] if m.get("kind") == "image"][:4]
    # The bytes go to the vision model as downscaled data URLs, so private
    # (real person) photos never need a link here.
    urls = await media.vision_data_urls(images, current_user.id)
    activity.log_activity(db, current_user.id, "bible", character_id=char.id)
    db.commit()
    bible = await _describe(db, char, urls)
    char = _character(db, current_user, char_id)
    char.bible = bible
    char.safety_flags = list((bible or {}).get("safety_flags") or [])
    if consent.possible_minor(char) and char.kind == "real_person":
        activity.log_activity(db, current_user.id, "blocked_possible_minor", character_id=char.id)
    db.commit()
    db.refresh(char)
    return views.character_view(char)
