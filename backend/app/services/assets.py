"""My Assets: a user's reusable images, logos, videos and audio.

Uploads are recognised from their own bytes (the declared type and the file
name are ignored), measured (pixel size, or length with ffprobe) and stored
as asset_<uuid>.<ext> in the user's folders: images and logos under
images/{user_id}/, videos and audio under videos/{user_id}/. Deleting an asset
deletes its file.

Voices are generated with ElevenLabs (Eleven v4 through fal,
elevenlabs/tts/eleven-v4, ELEVEN_V4_KEY) or Sarvam (Bulbul v4 for Indian
languages, app/services/sarvam_tts.py, SARVAM_BULBUL_KEY), priced per
character sent and saved as audio assets. The fal call blocks one threadpool
thread for a few seconds, like the logo and image generators; Sarvam is an
async HTTP call. The event loop keeps serving either way.

Tools take an asset by id and check it against their own limits at use time
(Lip Sync in app/routers/lipsync.py, Motion Control in app/routers/video.py),
always for the asset's owner, so a URL from the client is never trusted.
"""

from __future__ import annotations

import io
import logging
import re
import time
import unicodedata
import uuid
from datetime import datetime

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.config import settings
from app.database import apply_row_lock
from app.models.asset import UserAsset

logger = logging.getLogger(__name__)

KINDS = ("image", "logo", "video", "audio")
# StorageService type each kind is stored under.
STORAGE_FOR_KIND = {"image": "images", "logo": "images", "video": "videos", "audio": "videos"}

IMAGE_MAX_BYTES = 25 * 1024 * 1024
LOGO_MAX_BYTES = 5 * 1024 * 1024
AUDIO_MAX_BYTES = 25 * 1024 * 1024
VIDEO_MAX_BYTES = settings.MAX_VIDEO_UPLOAD_SIZE_MB * 1024 * 1024
UPLOAD_MAX_BYTES = max(IMAGE_MAX_BYTES, AUDIO_MAX_BYTES, VIDEO_MAX_BYTES)
AUDIO_MAX_SECONDS = 30 * 60
VIDEO_MAX_SECONDS = 10 * 60
MAX_ASSETS_PER_USER = 2000
NAME_MAX = 120

RASTER_FORMATS = {
    "PNG": (".png", "image/png"),
    "JPEG": (".jpg", "image/jpeg"),
    "WEBP": (".webp", "image/webp"),
}

# Voice generation (Eleven v4 stock voices, the Faceless Studio catalogue).
VOICE_MAX_CHARS = 2500
VOICE_MIN_CHARS = 2
# The page waits 240 s for the whole request (api/assets.ts generateVoice):
# fal gets 120 s, the download 30 s.
VOICE_TIMEOUT_SECONDS = 120
VOICE_FETCH_TIMEOUT_SECONDS = 30
VOICE_RESULT_MAX_BYTES = 25 * 1024 * 1024


class AssetError(ValueError):
    """An upload or request the user has to fix; the message is shown as is."""


class AssetNotFound(LookupError):
    pass


# ---------------------------------------------------------------------------
# Names and URLs
# ---------------------------------------------------------------------------

def clean_name(raw: str | None, fallback: str) -> str:
    """A display name: no path, no extension, no control characters."""
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    if "." in name:
        stem, _, ext = name.rpartition(".")
        if stem and len(ext) <= 5:
            name = stem
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    name = re.sub(r"\s+", " ", name).strip()
    return name[:NAME_MAX] or fallback


def url_of(asset: UserAsset) -> str:
    from app.services.storage_service import storage_service

    return storage_service.get_public_url(asset.filename, asset.storage_type, user_id=asset.user_id)


def to_dict(asset: UserAsset) -> dict:
    extra = asset.extra if isinstance(asset.extra, dict) else {}
    return {
        "id": asset.id,
        "kind": asset.kind,
        "name": asset.name,
        "url": url_of(asset),
        "content_type": asset.content_type,
        "file_size_bytes": int(asset.file_size_bytes or 0),
        "width": asset.width,
        "height": asset.height,
        "duration_seconds": asset.duration_seconds,
        "source": asset.source or "upload",
        "voice": extra.get("voice_label") or extra.get("voice"),
        "voice_provider": extra.get("provider") or ("elevenlabs" if asset.source == "voice" else None),
        "text": extra.get("text"),
        "created_at": asset.created_at,
    }


def owned(db: Session, user_id: int, asset_id: int, kinds: tuple[str, ...] | None = None,
          lock: bool = False) -> UserAsset:
    """The user's asset, optionally of one of ``kinds``; AssetNotFound otherwise.

    ``lock`` holds the row until the caller's commit: tools lock the assets a
    new job reads, and delete locks before its in-use check, so an asset
    cannot be deleted between a job's check and its job row landing."""
    query = db.query(UserAsset).filter(UserAsset.id == int(asset_id), UserAsset.user_id == user_id)
    if kinds:
        query = query.filter(UserAsset.kind.in_(kinds))
    if lock:
        query = apply_row_lock(query)
    asset = query.first()
    if asset is None:
        raise AssetNotFound("Asset not found")
    return asset


def extension(asset: UserAsset) -> str:
    return "." + asset.filename.rsplit(".", 1)[-1].lower() if "." in asset.filename else ""


# ---------------------------------------------------------------------------
# Recognising and measuring uploads
# ---------------------------------------------------------------------------

def _looks_like_svg(content: bytes) -> bool:
    head = content[:1024].lstrip().lower()
    if head.startswith(b"\xef\xbb\xbf"):
        head = head[3:].lstrip()
    return head.startswith(b"<svg") or (head.startswith((b"<?xml", b"<!--", b"<!doctype svg")) and b"<svg" in head)


def _raster(content: bytes) -> dict | None:
    """{format, ext, content_type, width, height} for a PNG, JPEG or WebP; None
    when the bytes are not an image Pillow reads."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(content)) as img:
            fmt = (img.format or "").upper()
            width, height = img.size
            img.verify()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
        return None
    if fmt == "GIF":
        raise AssetError("GIF is not supported. Save it as PNG, JPG or WebP (or MP4 for an animation) and upload that.")
    if fmt not in RASTER_FORMATS:
        raise AssetError("Unsupported image format. Upload PNG, JPG or WebP.")
    if not width or not height:
        raise AssetError("The image has no size.")
    ext, content_type = RASTER_FORMATS[fmt]
    return {"format": fmt, "ext": ext, "content_type": content_type, "width": width, "height": height}


def _probe(content: bytes, ext: str) -> dict | None:
    from app.routers.video import _probe_reference

    return _probe_reference(content, ext)


def inspect_upload(content: bytes, requested: str | None) -> dict:
    """Recognise and measure an upload. Returns {kind, ext, content_type,
    data, width, height, duration}; raises AssetError with a message fit for
    the user. ``requested`` ("logo" for the logo tab) picks between image and
    logo for a still; otherwise the bytes decide."""
    from app.services.lipsync_service import sniff_audio

    if not content:
        raise AssetError("The file is empty.")
    if requested is not None and requested not in KINDS:
        raise AssetError("Unknown asset type.")

    # SVG: logos only, rebuilt from the allowlist before it is stored.
    if _looks_like_svg(content):
        from app.utils.svg_sanitize import SVGSanitizeError, sanitize_svg

        if len(content) > LOGO_MAX_BYTES:
            raise AssetError("SVG logos can be up to 5 MB.")
        try:
            svg = sanitize_svg(content, max_bytes=LOGO_MAX_BYTES)
        except SVGSanitizeError:
            raise AssetError("The SVG could not be read. Export it again as a plain SVG, or upload a PNG.")
        return {"kind": "logo", "ext": ".svg", "content_type": "image/svg+xml", "data": svg.data,
                "width": svg.width, "height": svg.height, "duration": None}

    still = _raster(content)
    if still is not None:
        kind = "logo" if requested == "logo" else "image"
        limit = LOGO_MAX_BYTES if kind == "logo" else IMAGE_MAX_BYTES
        if len(content) > limit:
            raise AssetError(f"{'Logos' if kind == 'logo' else 'Images'} can be up to {limit // (1024 * 1024)} MB.")
        return {"kind": kind, "ext": still["ext"], "content_type": still["content_type"], "data": content,
                "width": still["width"], "height": still["height"], "duration": None}

    if requested == "logo":
        raise AssetError("Upload a logo as SVG, PNG, JPG or WebP.")

    head = content[:16]
    is_mp4_family = len(head) >= 12 and head[4:8] == b"ftyp"
    audio_brand = is_mp4_family and head[8:12].startswith((b"M4A", b"M4B"))
    if not is_mp4_family or audio_brand:
        try:
            ext, content_type = sniff_audio(content)
        except ValueError:
            ext = None
        if ext is not None and head[:4] != b"\x1a\x45\xdf\xa3":
            return _audio(content, ext, content_type)

    from app.routers.video import VIDEO_FORMATS_TEXT, sniff_reference_video

    try:
        ext, content_type = sniff_reference_video(content)
    except ValueError:
        raise AssetError(f"Unsupported file. Upload an image (PNG, JPG, WebP, SVG logo), a video ({VIDEO_FORMATS_TEXT}) "
                         "or audio (MP3, WAV, M4A, AAC, OGG).")
    probe = _probe(content, ext)
    if probe is not None and not probe.get("has_video") and ext in (".mp4", ".m4v"):
        # An MP4 with only an audio track is audio.
        return _audio(content, ".m4a", "audio/mp4", probe)
    if len(content) > VIDEO_MAX_BYTES:
        raise AssetError(f"Videos can be up to {VIDEO_MAX_BYTES // (1024 * 1024)} MB.")
    if probe is None or not probe.get("has_video") or not probe.get("duration"):
        raise AssetError(f"The video could not be read. Upload {VIDEO_FORMATS_TEXT}.")
    if probe["duration"] > VIDEO_MAX_SECONDS + 0.5:
        raise AssetError(f"Videos can be up to {VIDEO_MAX_SECONDS // 60} minutes long.")
    return {"kind": "video", "ext": ext, "content_type": content_type, "data": content,
            "width": probe.get("width"), "height": probe.get("height"),
            "duration": round(float(probe["duration"]), 3)}


def _audio(content: bytes, ext: str, content_type: str, probe: dict | None = None) -> dict:
    if len(content) > AUDIO_MAX_BYTES:
        raise AssetError(f"Audio files can be up to {AUDIO_MAX_BYTES // (1024 * 1024)} MB.")
    probe = probe or _probe(content, ext)
    seconds = (probe or {}).get("duration")
    if not seconds:
        raise AssetError("The audio length could not be read. Upload MP3, WAV, M4A, AAC or OGG.")
    if seconds > AUDIO_MAX_SECONDS + 0.5:
        raise AssetError(f"Audio files can be up to {AUDIO_MAX_SECONDS // 60} minutes long.")
    return {"kind": "audio", "ext": ext, "content_type": content_type, "data": content,
            "width": None, "height": None, "duration": round(float(seconds), 3)}


# ---------------------------------------------------------------------------
# Creating and deleting
# ---------------------------------------------------------------------------

def check_room(db: Session, user_id: int) -> None:
    count = db.query(UserAsset).filter(UserAsset.user_id == user_id).count()
    if count >= MAX_ASSETS_PER_USER:
        raise AssetError(f"You have {MAX_ASSETS_PER_USER} assets, the most an account can keep. Delete some first.")


async def store(db: Session, user_id: int, info: dict, name: str, *, source: str = "upload",
                extra: dict | None = None, commit: bool = True) -> UserAsset:
    """Save measured bytes (from inspect_upload) as a new asset."""
    from app.services.storage_service import storage_service

    storage_type = STORAGE_FOR_KIND[info["kind"]]
    filename = f"asset_{uuid.uuid4().hex}{info['ext']}"
    data = info["data"]
    await storage_service.upload_file(
        file_data=data,
        filename=filename,
        storage_type=storage_type,
        content_type=info["content_type"],
        user_id=user_id,
    )
    asset = UserAsset(
        user_id=user_id,
        kind=info["kind"],
        name=name,
        filename=filename,
        storage_type=storage_type,
        content_type=info["content_type"],
        file_size_bytes=len(data),
        width=info.get("width"),
        height=info.get("height"),
        duration_seconds=info.get("duration"),
        source=source,
        extra=extra,
        created_at=datetime.utcnow(),
    )
    try:
        db.add(asset)
        if commit:
            db.commit()
            db.refresh(asset)
        else:
            db.flush()
    except Exception:
        db.rollback()
        await _delete_file(filename, storage_type, user_id)
        raise
    return asset


async def _delete_file(filename: str, storage_type: str, user_id: int) -> None:
    from app.services.storage_service import storage_service

    try:
        await storage_service.delete_file(filename, storage_type, user_id=user_id)
    except Exception as exc:
        logger.warning(f"Could not delete asset file {storage_type}/{user_id}/{filename}: {exc}")


RUNNING_JOB_STATES = ("pending", "in_progress", "processing")


def in_use(db: Session, asset: UserAsset) -> bool:
    """True when a lip sync or motion control job that has not finished reads
    this asset (fal fetches the inputs when the job starts)."""
    from sqlalchemy import or_

    from app.models.content import LipSyncJob, VideoGenerationJob

    url = url_of(asset)
    lipsync = db.query(LipSyncJob.id).filter(
        LipSyncJob.user_id == asset.user_id,
        LipSyncJob.status.in_(RUNNING_JOB_STATES),
        or_(LipSyncJob.image_url == url, LipSyncJob.audio_url == url),
    ).first()
    if lipsync:
        return True
    motion = db.query(VideoGenerationJob.id).filter(
        VideoGenerationJob.user_id == asset.user_id,
        VideoGenerationJob.status.in_(RUNNING_JOB_STATES),
        or_(
            VideoGenerationJob.source_image_url == url,
            VideoGenerationJob.motion_reference_url == url,
            VideoGenerationJob.face_image_url == url,
        ),
    ).first()
    if motion is not None:
        return True
    from app.clients.fal_client import RECAST_ENDPOINT

    recasts = db.query(VideoGenerationJob.options).filter(
        VideoGenerationJob.user_id == asset.user_id,
        VideoGenerationJob.status.in_(RUNNING_JOB_STATES),
        VideoGenerationJob.model == RECAST_ENDPOINT,
    ).all()
    return any(url in ((options or {}).get("reference_image_urls") or []) for (options,) in recasts)


async def delete(db: Session, asset: UserAsset) -> None:
    """Delete the row, then the file (best effort: a file left behind is logged)."""
    filename, storage_type, user_id = asset.filename, asset.storage_type, asset.user_id
    db.delete(asset)
    db.commit()
    await _delete_file(filename, storage_type, user_id)


# ---------------------------------------------------------------------------
# Voices: ElevenLabs (Eleven v4 through fal) and Sarvam (Bulbul v4)
# ---------------------------------------------------------------------------

VOICE_PROVIDERS = ("elevenlabs", "sarvam")


def sarvam_key(db: Session) -> str | None:
    from app.models.api import APISettings

    settings_row = db.query(APISettings).first()
    return settings_row.get_sarvam_key() if settings_row else None


def voice_catalog(db: Session) -> dict:
    """The voice providers a user can pick from: ElevenLabs always, Sarvam
    once its key is saved."""
    from app.services import sarvam_tts
    from app.services.pricing import ELEVEN_V4_KEY, SARVAM_BULBUL_KEY
    from app.services.faceless.catalog import DEFAULT_NARRATOR_VOICE, VOICES

    providers = [{
        "id": "elevenlabs",
        "label": "ElevenLabs",
        "model": "Eleven v4",
        "description": "Natural English and multilingual voices",
        "price_key": ELEVEN_V4_KEY,
        "max_characters": VOICE_MAX_CHARS,
        "default_voice": DEFAULT_NARRATOR_VOICE,
        "default_language": None,
        "languages": [],
        "voices": [
            {"id": v["id"], "label": v["id"], "language": None, "gender": v.get("gender"),
             "description": ", ".join(x for x in (v.get("accent"), v.get("tone")) if x)}
            for v in VOICES
        ],
    }]
    if sarvam_key(db):
        sarvam = sarvam_tts.catalog()
        providers.append({
            "id": "sarvam",
            "label": "Sarvam",
            "model": sarvam_tts.MODEL_LABEL,
            "description": "Indian accents and regional languages",
            "price_key": SARVAM_BULBUL_KEY,
            "max_characters": min(VOICE_MAX_CHARS, sarvam_tts.MAX_CHARS),
            "default_voice": sarvam_tts.DEFAULT_VOICE,
            "default_language": sarvam_tts.DEFAULT_LANGUAGE,
            "languages": sarvam["languages"],
            "voices": [{**v, "description": v["style"] or None} for v in sarvam["voices"]],
        })
    return {"providers": providers}


def _spoken(text: str) -> str:
    spoken = (text or "").strip()
    if len(spoken) < VOICE_MIN_CHARS:
        raise AssetError("Type what the voice should say.")
    if len(spoken) > VOICE_MAX_CHARS:
        raise AssetError(f"The text is {len(spoken)} characters. A voice can be up to {VOICE_MAX_CHARS} characters.")
    return spoken


def voice_arguments(text: str, voice: str, stability: float | None) -> dict:
    """fal arguments for Eleven v4."""
    from app.services.faceless import catalog

    if voice not in catalog.VOICE_IDS:
        raise AssetError("Unknown voice. Pick one from the list.")
    spoken = _spoken(text)
    value = catalog.DEFAULT_STABILITY if stability is None else float(stability)
    if not 0.0 <= value <= 1.0:
        raise AssetError("Stability must be between 0 and 1.")
    return {
        "text": spoken,
        "voice": voice,
        "stability": round(value, 2),
        "similarity_boost": catalog.DEFAULT_SIMILARITY,
        "apply_text_normalization": "auto",
        "output_format": "mp3_44100_128",
    }


def _run_tts(client, arguments: dict) -> dict:
    """Submit to fal and wait for the result (threadpool)."""
    from app.services.faceless.catalog import TTS_ENDPOINT

    handler = client.submit(TTS_ENDPOINT, arguments=arguments)
    deadline = time.monotonic() + VOICE_TIMEOUT_SECONDS
    while True:
        status = client.status(TTS_ENDPOINT, handler.request_id, with_logs=False)
        name = type(status).__name__.lower()
        if "complete" in name or "complete" in str(getattr(status, "status", "")).lower():
            break
        if time.monotonic() > deadline:
            raise TimeoutError(f"Voice request {handler.request_id} did not finish in {VOICE_TIMEOUT_SECONDS}s")
        time.sleep(1.0)
    return client.result(TTS_ENDPOINT, handler.request_id)


async def _elevenlabs_audio(client, arguments: dict) -> bytes:
    from app.services.url_fetch import afetch_bytes

    result = await run_in_threadpool(_run_tts, client, arguments)
    file = (result or {}).get("audio") if isinstance(result, dict) else None
    if isinstance(file, list):
        file = file[0] if file else None
    if not isinstance(file, dict) or not file.get("url"):
        raise VoiceGenerationError("The voice service returned no audio")
    return await afetch_bytes(file["url"], max_bytes=VOICE_RESULT_MAX_BYTES, timeout=VOICE_FETCH_TIMEOUT_SECONDS)


class VoiceGenerationError(RuntimeError):
    """The provider failed."""


def _voice_request(db: Session, provider: str, text: str, voice: str, stability: float | None,
                   pace: float | None) -> dict:
    """Everything provider specific about one voice: what to send, what it
    costs and how to label it. Raises AssetError before anything is sent."""
    from app.services import sarvam_tts
    from app.services.faceless.catalog import TTS_ENDPOINT
    from app.services.pricing import ELEVEN_V4_KEY, SARVAM_BULBUL_KEY

    if provider == "elevenlabs":
        arguments = voice_arguments(text, voice, stability)
        return {
            "text": arguments["text"], "arguments": arguments, "price_key": ELEVEN_V4_KEY,
            "model": TTS_ENDPOINT, "voice_label": voice, "language": None,
            "settings": {"stability": arguments["stability"]},
        }
    if provider == "sarvam":
        key = sarvam_key(db)
        if not key:
            raise AssetError("Sarvam voices are not available right now. Pick an ElevenLabs voice.")
        spoken = _spoken(text)
        if len(spoken) > sarvam_tts.MAX_CHARS:
            raise AssetError(f"Sarvam voices take up to {sarvam_tts.MAX_CHARS} characters.")
        try:
            body = sarvam_tts.arguments(spoken, voice, pace)
        except ValueError as exc:
            raise AssetError(str(exc))
        return {
            "text": spoken, "arguments": body, "api_key": key, "price_key": SARVAM_BULBUL_KEY,
            "model": f"sarvam/{sarvam_tts.MODEL}", "voice_label": sarvam_tts.voice_label(voice),
            "language": body["target_language_code"], "settings": {"pace": body["pace"]},
        }
    raise AssetError("Unknown voice provider.")


async def generate_voice(db: Session, user_id: int, *, text: str, voice: str,
                         stability: float | None, name: str | None, provider: str = "elevenlabs",
                         pace: float | None = None) -> tuple[UserAsset, float]:
    """Generate, store, record. Returns (asset, estimated USD). Raises AssetError for
    input problems and VoiceGenerationError when the provider fails."""
    from app.services import sarvam_tts
    from app.services.faceless import media
    from app.services.fal_keys import get_sync_client
    from app.services.pricing import tts_usd
    from app.services.usage import record_usage

    request = _voice_request(db, provider, text, voice, stability, pace)
    spoken = request["text"]
    characters = len(spoken)
    estimated_usd = tts_usd(characters, request["price_key"])
    check_room(db, user_id)
    words = spoken.split()
    label = clean_name(name, "") or f"{request['voice_label']}: {' '.join(words[:6])}{'...' if len(words) > 6 else ''}"
    label = label[:NAME_MAX]

    client = get_sync_client(db) if provider == "elevenlabs" else None
    try:
        if provider == "sarvam":
            content = await sarvam_tts.synthesize(request["api_key"], request["arguments"])
        else:
            content = await _elevenlabs_audio(client, request["arguments"])
        media.check_result_kind(content, "audio")
        info = await run_in_threadpool(_audio, content, ".mp3", "audio/mpeg")
    except (AssetError, VoiceGenerationError):
        raise
    except sarvam_tts.SarvamError as exc:
        raise VoiceGenerationError(str(exc)) from exc
    except Exception as exc:
        logger.warning(f"Voice generation failed ({provider}): {exc}")
        raise VoiceGenerationError("The voice could not be generated") from exc

    asset = await store(
        db, user_id, info, label, source="voice", commit=False,
        extra={"provider": provider, "voice": voice, "voice_label": request["voice_label"],
               "language": request["language"], "text": spoken, "characters": characters,
               "estimated_usd": estimated_usd, "model": request["model"], **request["settings"]},
    )
    record_usage(
        db,
        feature="voice",
        usd=estimated_usd,
        model=request["model"],
        units=characters,
        unit="character",
        detail={
            "provider": provider,
            "price_key": request["price_key"],
            "voice": voice,
            "language": request["language"],
            "duration_seconds": info.get("duration"),
            "asset_id": asset.id,
        },
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        await _delete_file(asset.filename, asset.storage_type, user_id)
        raise
    db.refresh(asset)
    return asset, estimated_usd
