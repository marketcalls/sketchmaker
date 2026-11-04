"""Provider and file plumbing shared by Faceless Studio, Motion Graphics, My Assets, Story
Room and characters.

fal is used through submit, status and result only (never the blocking
subscribe), from scheduler threads. Results are downloaded through
app/services/url_fetch.py and stored with StorageService under the user's
folders. Uploads are decoded and probed from their own bytes; the client never
supplies a URL that is later sent to a provider: every URL sent to fal is rebuilt
from a stored filename.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import subprocess
import tempfile
import uuid
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.utils.security import scrubbed_env

from . import catalog
from .errors import InvalidRequest

logger = logging.getLogger(__name__)

RESULT_IMAGE_MAX_BYTES = 40 * 1024 * 1024
RESULT_VIDEO_MAX_BYTES = 500 * 1024 * 1024
RESULT_AUDIO_MAX_BYTES = 80 * 1024 * 1024


def set_json(obj, attr: str, value) -> None:
    """Assign a JSON column and mark it changed."""
    setattr(obj, attr, value)
    flag_modified(obj, attr)


def image_size(content: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image as PILImage

        with PILImage.open(io.BytesIO(content)) as img:
            return img.size
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# fal (submit, poll, result)
# ---------------------------------------------------------------------------

def fal_submit(db: Session, endpoint: str, arguments: dict) -> str:
    """Queue a request on fal and return its request id. Own files in ``arguments`` go
    up to fal storage first. Blocking: scheduler threads only."""
    from app.services.fal_inputs import resolve_fal_inputs
    from app.services.fal_keys import get_sync_client

    handler = get_sync_client(db).submit(endpoint, arguments=resolve_fal_inputs(arguments))
    return handler.request_id


def fal_status(db: Session, endpoint: str, request_id: str) -> str:
    """queued | running | completed. Raises on transport errors (retried by the caller)."""
    from app.services.fal_keys import get_sync_client

    status = get_sync_client(db).status(endpoint, request_id, with_logs=False)
    name = type(status).__name__.lower()
    attr = str(getattr(status, "status", "") or "").lower()
    if "complete" in name or "complete" in attr:
        return "completed"
    if "progress" in name or "progress" in attr:
        return "running"
    return "queued"


def fal_result(db: Session, endpoint: str, request_id: str) -> dict:
    """The result of a completed request. Raises when fal reports a failure."""
    from app.services.fal_keys import get_sync_client

    return get_sync_client(db).result(endpoint, request_id)


async def download(url: str, max_bytes: int) -> bytes:
    """Provider output through the SSRF-safe fetcher."""
    from app.services.url_fetch import afetch_bytes

    return await afetch_bytes(url, max_bytes=max_bytes, timeout=300)


def run_async(coro):
    """Run a coroutine from the scheduler's worker thread."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

async def store_bytes(content: bytes, *, user_id: int, storage: str, prefix: str, ext: str,
                      content_type: str) -> dict:
    """Save bytes under the user's folder; returns {file, storage, url, bytes}."""
    from app.services.storage_service import storage_service

    ext = ext if ext.startswith(".") else f".{ext}"
    filename = f"{prefix}_{uuid.uuid4().hex}{ext}"
    url = await storage_service.upload_file(
        file_data=content, filename=filename, storage_type=storage,
        content_type=content_type, user_id=user_id,
    )
    return {"file": filename, "storage": storage, "url": url, "bytes": len(content)}


def public_url(asset: dict, user_id: int) -> str:
    """URL of a stored asset, rebuilt from its filename (never taken from a client).

    Never for a private asset (real person character media): those have no
    public URL, see owner_url and provider_ref."""
    from app.services.storage_service import storage_service

    if is_private(asset):
        raise ValueError("A private asset has no public URL")
    return storage_service.get_public_url(asset["file"], asset["storage"], user_id=user_id)


async def read_bytes(asset: dict, user_id: int) -> bytes | None:
    from app.services.storage_service import storage_service

    if is_private(asset):
        return await asyncio.get_running_loop().run_in_executor(None, _private_read, asset["file"], user_id)
    return await storage_service.get_file_bytes(asset["file"], asset["storage"], user_id=user_id)


async def delete_stored(asset: dict, user_id: int) -> None:
    from app.services.storage_service import storage_service

    try:
        if is_private(asset):
            await asyncio.get_running_loop().run_in_executor(None, _private_delete, asset["file"], user_id)
            return
        await storage_service.delete_file(asset["file"], asset["storage"], user_id=user_id)
    except Exception as exc:
        logger.warning(f"Could not delete faceless asset {asset.get('file')}: {exc}")


def local_path(asset: dict, user_id: int) -> str:
    """Where a stored asset is on disk."""
    from app.services.storage_service import storage_service

    if is_private(asset):
        return private_local_path(asset["file"], user_id)
    return storage_service.get_local_path(asset["file"], asset["storage"], user_id=user_id)


# ---------------------------------------------------------------------------
# Private storage (real person character media)
# ---------------------------------------------------------------------------
#
# Photos, source videos, extracted frames and reference sheets of a
# real_person character are never served at /static. They live under
# private_root(), outside static/; fal gets its own copy in fal storage at submit
# time, and the owner sees them through GET /characters/{id}/media/{media_id}/file.
#
# Step items store a placeholder (PRIVATE_REF + filename) instead of a URL in
# their fal arguments, so no provider link is persisted in the database;
# resolve_provider_refs() swaps in a fresh one just before submit.

PRIVATE_STORAGE = "private"
PRIVATE_REF = "faceless-private://"


def is_private(asset: dict | None) -> bool:
    return bool(asset) and asset.get("storage") == PRIVATE_STORAGE


def private_root() -> str:
    from app.config import settings

    return str(settings.private_media_dir)


def _check_private_name(filename: str) -> None:
    from app.services.storage_service import _safe_name

    _safe_name(filename)
    if "/" in filename:
        raise ValueError(f"Unsafe private filename: {filename!r}")


def private_local_path(filename: str, user_id: int) -> str:
    _check_private_name(filename)
    return os.path.join(private_root(), str(int(user_id)), filename)


def _private_write(content: bytes, filename: str, user_id: int, content_type: str) -> None:
    path = private_local_path(filename, user_id)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)


def _private_read(filename: str, user_id: int) -> bytes | None:
    path = private_local_path(filename, user_id)
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            return fh.read()
    return None


def _private_delete(filename: str, user_id: int) -> None:
    path = private_local_path(filename, user_id)
    if os.path.isfile(path):
        os.unlink(path)


async def store_private(content: bytes, *, user_id: int, prefix: str, ext: str, content_type: str) -> dict:
    """Save bytes privately; returns {file, storage: "private", bytes}."""
    ext = ext if ext.startswith(".") else f".{ext}"
    filename = f"{prefix}_{uuid.uuid4().hex}{ext}"
    await asyncio.get_running_loop().run_in_executor(None, _private_write, content, filename, user_id,
                                                     content_type)
    return {"file": filename, "storage": PRIVATE_STORAGE, "bytes": len(content)}


async def store_character_bytes(char, content: bytes, *, prefix: str, ext: str, content_type: str) -> dict:
    """Character media: private for a real person, public uploads otherwise."""
    if getattr(char, "kind", None) == "real_person":
        return await store_private(content, user_id=char.user_id, prefix=prefix, ext=ext,
                                   content_type=content_type)
    return await store_bytes(content, user_id=char.user_id, storage="uploads", prefix=prefix, ext=ext,
                             content_type=content_type)


def owner_url(asset: dict, user_id: int, char_id: int) -> str | None:
    """URL the owner's browser loads: the /static path, or the owner-checked route."""
    if not is_private(asset):
        return public_url(asset, user_id)
    return f"/api/faceless/characters/{int(char_id)}/media/{asset.get('id')}/file"


def provider_ref(asset: dict, user_id: int) -> str:
    """What a step plan stores where fal needs this asset's URL."""
    if is_private(asset):
        _check_private_name(asset["file"])
        return PRIVATE_REF + asset["file"]
    return public_url(asset, user_id)


def _provider_url(filename: str, user_id: int) -> str:
    # fal cannot reach this machine's disk, so the file goes to fal's own storage.
    from app.services.fal_inputs import PRIVATE_MEDIA_PREFIX, resolve_fal_inputs

    _check_private_name(filename)
    return resolve_fal_inputs(f"{PRIVATE_MEDIA_PREFIX}{int(user_id)}/{filename}")


def resolve_provider_refs(arguments, user_id: int, db: Session | None = None):
    """A copy of ``arguments`` with every private placeholder replaced by a
    fresh provider URL. Raises if a referenced private file is gone."""

    def walk(value):
        if isinstance(value, str) and value.startswith(PRIVATE_REF):
            return _provider_url(value[len(PRIVATE_REF):], user_id)
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        return value

    return walk(arguments)


async def vision_data_urls(assets: list[dict], user_id: int, max_side: int = 1024) -> list[str]:
    """Stored images as downscaled JPEG data URLs for a vision model. Read
    from storage directly, so private media never needs a link (the LLM path
    cannot fetch this server's /static)."""
    import base64
    import io

    from PIL import Image as PILImage

    out = []
    for asset in assets:
        try:
            content = await read_bytes(asset, user_id)
            if not content:
                continue
            with PILImage.open(io.BytesIO(content)) as im:
                im = im.convert("RGB")
                im.thumbnail((max_side, max_side))
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=88)
            out.append("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii"))
        except Exception as exc:
            logger.warning(f"Could not prepare {asset.get('file')} for the vision model: {type(exc).__name__}")
    return out


def has_private_refs(arguments) -> bool:
    if isinstance(arguments, str):
        return arguments.startswith(PRIVATE_REF)
    if isinstance(arguments, list):
        return any(has_private_refs(v) for v in arguments)
    if isinstance(arguments, dict):
        return any(has_private_refs(v) for v in arguments.values())
    return False


async def store_file(path: str, *, user_id: int, storage: str, prefix: str, ext: str, content_type: str) -> dict:
    """Like store_bytes for a large local file (a rendered video), streamed
    from disk instead of read into memory."""
    from app.services.storage_service import storage_service

    ext = ext if ext.startswith(".") else f".{ext}"
    filename = f"{prefix}_{uuid.uuid4().hex}{ext}"
    size = os.path.getsize(path)
    url = await storage_service.upload_file_from_path(path, filename, storage, content_type, user_id=user_id)
    return {"file": filename, "storage": storage, "url": url, "bytes": size}


# ---------------------------------------------------------------------------
# Provider results: check what came back before storing or probing it
# ---------------------------------------------------------------------------

def check_result_kind(content: bytes, kind: str) -> None:
    """Refuse a provider result whose bytes are not the expected media type,
    so ffprobe and ffmpeg only ever see an image, an MP4/MOV/WebM video or a
    plain audio file (never a playlist or a concat list that could make
    ffmpeg open other files)."""
    head = (content or b"")[:16]
    ok = False
    if kind == "image":
        ok = head[:8] == b"\x89PNG\r\n\x1a\n" or head[:3] == b"\xff\xd8\xff" or \
            (head[:4] == b"RIFF" and head[8:12] == b"WEBP")
    elif kind == "video":
        ok = head[4:8] == b"ftyp" or head[:4] == b"\x1a\x45\xdf\xa3"
    elif kind == "audio":
        ok = head[:3] == b"ID3" or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0) or \
            (head[:4] == b"RIFF" and head[8:12] == b"WAVE") or head[4:8] == b"ftyp" or head[:4] == b"OggS" or \
            head[:4] == b"fLaC"
    if not ok:
        raise ValueError(f"The provider returned something that is not a valid {kind} file")


def content_type_for(ext: str) -> str:
    return {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
        ".avif": "image/avif", ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
        ".m4v": "video/x-m4v", ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4",
    }.get(ext.lower(), "application/octet-stream")


def ext_from_result(file: dict | None, default: str) -> str:
    content_type = ((file or {}).get("content_type") or "").lower()
    url = ((file or {}).get("url") or "").lower().split("?", 1)[0]
    for needle, ext in (("png", ".png"), ("jpeg", ".jpg"), ("jpg", ".jpg"), ("webp", ".webp"),
                        ("mp4", ".mp4"), ("mpeg", ".mp3"), ("mp3", ".mp3"), ("wav", ".wav")):
        if needle in content_type or url.endswith(f".{needle}"):
            return ext
    return default


# ---------------------------------------------------------------------------
# ffmpeg and ffprobe
# ---------------------------------------------------------------------------

def probe_file(path: str) -> dict:
    """{duration, width, height, has_audio, has_video} of a local media file."""
    try:
        from app.render import measure_media  # the render engine's probe, when built

        info = measure_media(path)
        if isinstance(info, dict) and info.get("duration") is not None:
            info.setdefault("has_video", bool(info.get("width")))
            return info
    except Exception:
        pass
    from app.render.ffmpeg import input_guard

    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams",
         *input_guard(), path],
        capture_output=True, text=True, timeout=60, env=scrubbed_env(),
    )
    if result.returncode != 0:
        return {"duration": None, "width": None, "height": None, "has_audio": False, "has_video": False}
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    try:
        duration = float((data.get("format") or {}).get("duration") or 0) or None
    except (TypeError, ValueError):
        duration = None
    return {
        "duration": duration,
        "width": video.get("width") if video else None,
        "height": video.get("height") if video else None,
        "has_audio": audio is not None,
        "has_video": video is not None,
    }


def probe_bytes(content: bytes, ext: str) -> dict:
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            path = tmp.name
        return probe_file(path)
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def extract_frames(content: bytes, ext: str, duration: float | None, count: int,
                   positions: list[float] | None = None) -> list[bytes]:
    """``count`` JPEG frames spread over a video (skipping the first and last
    10%), or one frame at each of ``positions`` (fractions of the length)."""
    from app.render.ffmpeg import input_guard

    frames: list[bytes] = []
    with tempfile.TemporaryDirectory(prefix="faceless_frames_") as workdir:
        src = os.path.join(workdir, f"src{ext}")
        with open(src, "wb") as fh:
            fh.write(content)
        seconds = float(duration or 0) or 1.0
        fractions = list(positions) if positions else [0.1 + 0.8 * (i + 0.5) / count for i in range(count)]
        for i, fraction in enumerate(fractions):
            # A seek past the last frame returns nothing: stay 0.2 s inside.
            t = min(seconds * min(max(float(fraction), 0.0), 1.0), max(0.0, seconds - 0.2))
            out = os.path.join(workdir, f"f{i}.jpg")
            result = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", *input_guard(), "-ss", f"{t:.3f}",
                 "-i", src, "-frames:v", "1", "-q:v", "2", out],
                capture_output=True, timeout=60, env=scrubbed_env(),
            )
            if result.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
                with open(out, "rb") as fh:
                    frames.append(fh.read())
    return frames


def last_frame(content: bytes, ext: str) -> bytes | None:
    """The last frame of a video as JPEG (the first frame of the next part
    when a clip family takes no end frame)."""
    from app.render.ffmpeg import input_guard

    with tempfile.TemporaryDirectory(prefix="faceless_last_") as workdir:
        src = os.path.join(workdir, f"src{ext}")
        out = os.path.join(workdir, "last.jpg")
        with open(src, "wb") as fh:
            fh.write(content)
        result = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", *input_guard(), "-sseof", "-0.5", "-i", src,
             "-update", "1", "-q:v", "2", out],
            capture_output=True, timeout=60, env=scrubbed_env(),
        )
        if result.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
            with open(out, "rb") as fh:
                return fh.read()
    return None


def voice_take_check(content: bytes, ext: str, duration: float, words: int) -> dict:
    """Free sanity check of one voice take: pace in words per minute and the
    longest pause (silencedetect). ``warning`` is a sentence for the user, or
    None. The take is only flagged; re-voicing is the user's choice."""
    from app.render.ffmpeg import input_guard

    low, high = catalog.VOICE_WPM_RANGE
    out: dict = {"wpm": None, "longest_pause": 0.0, "warning": None}
    if duration > 0 and words >= catalog.VOICE_CHECK_MIN_WORDS:
        out["wpm"] = round(words / (duration / 60.0))
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            path = tmp.name
        result = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "info", *input_guard(), "-i", path,
             "-af", f"silencedetect=noise=-40dB:d={catalog.VOICE_MAX_PAUSE_SECONDS}", "-f", "null", "-"],
            capture_output=True, text=True, timeout=60, env=scrubbed_env(),
        )
        pauses = [float(m) for m in re.findall(r"silence_duration: ([\d.]+)", result.stderr or "")]
        out["longest_pause"] = round(max(pauses), 2) if pauses else 0.0
    except Exception as exc:
        logger.warning(f"Voice take check could not run: {exc}")
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
    reasons = []
    if out["wpm"] is not None and not low <= out["wpm"] <= high:
        reasons.append(f"it runs at {out['wpm']} words a minute ({'slow' if out['wpm'] < low else 'rushed'})")
    if out["longest_pause"] > catalog.VOICE_MAX_PAUSE_SECONDS:
        reasons.append(f"it has a pause of {out['longest_pause']:.1f} seconds")
    if reasons:
        out["warning"] = "This take may sound off: " + " and ".join(reasons) + ". Listen, and voice it again if needed."
    return out


def video_thumbnail(path: str, at_seconds: float = 1.0) -> bytes | None:
    out = f"{path}.thumb.jpg"
    try:
        from app.render.ffmpeg import input_guard

        result = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", *input_guard(), "-ss", f"{at_seconds:.2f}",
             "-i", path, "-frames:v", "1", "-q:v", "3", out],
            capture_output=True, timeout=60, env=scrubbed_env(),
        )
        if result.returncode == 0 and os.path.exists(out):
            with open(out, "rb") as fh:
                return fh.read()
        return None
    finally:
        if os.path.exists(out):
            os.unlink(out)


# ---------------------------------------------------------------------------
# Uploads (character media and bring-your-own scene media)
# ---------------------------------------------------------------------------

def sniff_kind(content: bytes) -> str:
    """image | video, from the file's own bytes; InvalidRequest otherwise."""
    head = content[:16]
    if head[:8] == b"\x89PNG\r\n\x1a\n" or head[:3] == b"\xff\xd8\xff" or \
            (head[:4] == b"RIFF" and head[8:12] == b"WEBP") or head[4:12] in (b"ftypavif", b"ftypavis"):
        return "image"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        raise InvalidRequest("GIF is not supported. Upload a PNG, JPG or WebP image, or an MP4 video.")
    if len(head) >= 8 and head[4:8] == b"ftyp" or head[:4] == b"\x1a\x45\xdf\xa3" or \
            (len(head) >= 8 and head[4:8] in (b"moov", b"mdat", b"wide", b"free")):
        return "video"
    raise InvalidRequest("Unsupported file. Upload a PNG, JPG, WebP or AVIF image, or an MP4, MOV or WebM video.")


def prepare_image(content: bytes) -> dict:
    """Decoded, size-checked and fitted image: {content, ext, content_type, width, height}."""
    from app.routers.video import prepare_character_image

    try:
        return prepare_character_image(content)
    except ValueError as exc:
        raise InvalidRequest(str(exc).replace("character image", "image"))


def prepare_video(content: bytes, max_seconds: float) -> dict:
    """Checked video: {content, ext, content_type, duration, width, height, has_audio}."""
    from app.routers.video import sniff_reference_video

    try:
        ext, content_type = sniff_reference_video(content)
    except ValueError as exc:
        raise InvalidRequest(str(exc).replace("motion reference", "video"))
    info = probe_bytes(content, ext)
    if not info.get("has_video"):
        raise InvalidRequest("The file has no video track.")
    duration = info.get("duration")
    if not duration:
        raise InvalidRequest("The video length could not be read. Upload an MP4, MOV or WebM file.")
    if duration < catalog.VIDEO_MIN_SECONDS:
        raise InvalidRequest(f"The video is {duration:.1f} seconds long; it needs at least {catalog.VIDEO_MIN_SECONDS:g}.")
    if duration > max_seconds + 0.05:
        raise InvalidRequest(f"The video is {duration:.1f} seconds long. Upload at most {max_seconds:g} seconds.")
    return {"content": content, "ext": ext, "content_type": content_type, "duration": round(duration, 3),
            "width": info.get("width"), "height": info.get("height"), "has_audio": bool(info.get("has_audio"))}


def media_entry(stored: dict, *, kind: str, role: str, width=None, height=None, duration=None,
                source_id: str | None = None, usable_as_reference: bool = True) -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "role": role,
        "file": stored["file"],
        "storage": stored["storage"],
        "width": width,
        "height": height,
        "duration": duration,
        "source_id": source_id,
        "usable_as_reference": usable_as_reference,
        "created_at": datetime.utcnow().isoformat(),
    }
