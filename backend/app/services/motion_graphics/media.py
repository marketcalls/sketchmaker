"""Files for motion graphics: uploads, the brand logo, local copies.

Stored files live under the user's storage folders (StorageService). The render
engine never reads the network: previews and renders first copy what they need
into a local cache (keyed by filename) or into the render's work directory.
Provider results are downloaded through the SSRF-safe fetcher (faceless media
helpers are reused for fal and storage plumbing).
"""

from __future__ import annotations

import io
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from app.services.faceless import media as fl_media

from .audio import analyze
from .errors import InvalidRequest
from .gfx.bg import cache_root, prune_dir, touch

logger = logging.getLogger(__name__)

IMAGE_MAX_BYTES = 15 * 1024 * 1024
AUDIO_MAX_BYTES = 40 * 1024 * 1024
AUDIO_MAX_SECONDS = 180.0
MAX_UPLOADS_PER_PROJECT = 40

run_async = fl_media.run_async
store_bytes = fl_media.store_bytes
read_bytes = fl_media.read_bytes
delete_stored = fl_media.delete_stored


def public_url(asset: dict, user_id: int) -> Optional[str]:
    try:
        return fl_media.public_url(asset, user_id)
    except Exception:
        return None


def sniff(content: bytes) -> str:
    head = content[:16]
    if head[:8] == b"\x89PNG\r\n\x1a\n" or head[:3] == b"\xff\xd8\xff" or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
        return "image"
    if head[:3] == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2") or \
            (head[:4] == b"RIFF" and head[8:12] == b"WAVE") or head[4:8] == b"ftyp" or head[:4] == b"OggS" or \
            head[:4] == b"fLaC":
        return "audio"
    raise InvalidRequest("Unsupported file. Upload a PNG, JPG or WebP image, or an MP3, WAV, M4A or OGG audio file.",
                         code="unsupported_file")


def prepare_image(content: bytes) -> dict:
    """Decoded, size-checked image re-encoded as PNG or JPEG (drops metadata)."""
    from PIL import Image, ImageOps

    if len(content) > IMAGE_MAX_BYTES:
        raise InvalidRequest("Image too large. Upload up to 15 MB.", code="too_large")
    try:
        with Image.open(io.BytesIO(content)) as im:
            # Check the header size before anything decodes the pixels
            # (exif_transpose loads the full image): a small file can declare
            # a decompression bomb.
            if im.width * im.height > 40_000_000:
                raise InvalidRequest("Image dimensions are too large.", code="too_large")
            if im.format not in ("PNG", "JPEG", "MPO", "WEBP"):
                raise InvalidRequest("Upload a PNG, JPG or WebP image.", code="unsupported_file")
            im = ImageOps.exif_transpose(im)
            im.thumbnail((3000, 3000))
            has_alpha = im.mode in ("RGBA", "LA", "P")
            out = io.BytesIO()
            if has_alpha:
                im.convert("RGBA").save(out, format="PNG", optimize=True)
                ext, ctype = ".png", "image/png"
            else:
                im.convert("RGB").save(out, format="JPEG", quality=90)
                ext, ctype = ".jpg", "image/jpeg"
            return {"content": out.getvalue(), "ext": ext, "content_type": ctype, "width": im.width,
                    "height": im.height}
    except InvalidRequest:
        raise
    except Exception:
        raise InvalidRequest("The image could not be read.", code="bad_image")


def prepare_audio(content: bytes) -> dict:
    if len(content) > AUDIO_MAX_BYTES:
        raise InvalidRequest("Audio too large. Upload up to 40 MB.", code="too_large")
    import tempfile

    ext = ".mp3"
    head = content[:12]
    if head[:4] == b"RIFF":
        ext = ".wav"
    elif head[4:8] == b"ftyp":
        ext = ".m4a"
    elif head[:4] == b"OggS":
        ext = ".ogg"
    elif head[:4] == b"fLaC":
        ext = ".flac"
    from .audio import transcode_upload

    path = out = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as fh:
            fh.write(content)
            path = fh.name
        out = path + ".clean.m4a"
        try:
            # Decoding stops one second past the limit: a long (or lying)
            # file never costs more than that, and is reported as too long.
            transcode_upload(path, out, AUDIO_MAX_SECONDS + 1.0)
            info = analyze(out, max_seconds=AUDIO_MAX_SECONDS + 1.0)
            with open(out, "rb") as fh:
                clean = fh.read()
        except Exception:
            raise InvalidRequest("The audio could not be decoded.", code="bad_audio")
    finally:
        for p in (path, out):
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass
    if info["duration"] < 1.0:
        raise InvalidRequest("The audio is shorter than one second.", code="bad_audio")
    if info["duration"] > AUDIO_MAX_SECONDS + 0.5:
        raise InvalidRequest(f"The audio is longer than {AUDIO_MAX_SECONDS:.0f} s; upload at most "
                             f"{AUDIO_MAX_SECONDS:.0f} s.", code="too_long")
    return {"content": clean, "ext": ".m4a", "content_type": "audio/mp4", "duration": info["duration"],
            "amps": info["amps"]}


def upload_entry(stored: dict, *, kind: str, name: str = "", **extra) -> dict:
    return {"id": uuid.uuid4().hex[:12], "kind": kind, "file": stored["file"], "storage": stored["storage"],
            "name": (name or "")[:120], "created_at": datetime.utcnow().isoformat(), **extra}


def local_copy(asset: dict, user_id: int, folder: Optional[str] = None) -> Optional[str]:
    """A local path for a stored asset (cached for web previews)."""
    if not asset or not asset.get("file"):
        return None
    base = folder or os.path.join(cache_root("motion-graphics-assets"), str(int(user_id)))
    os.makedirs(base, exist_ok=True)
    name = os.path.basename(asset["file"])
    path = os.path.join(base, name)
    if os.path.isfile(path) and os.path.getsize(path) > 0:
        if folder is None:
            touch(path)
        return path
    try:
        content = run_async(read_bytes(asset, user_id))
    except Exception as exc:
        logger.warning(f"Motion graphics asset {name} unavailable: {exc}")
        return None
    if not content:
        return None
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "wb") as fh:
        fh.write(content)
    os.replace(tmp, path)
    if folder is None:
        _prune_cache()
    return path


CACHE_MAX_AGE_SECONDS = 3 * 24 * 3600
CACHE_MAX_BYTES = 2 * 1024 * 1024 * 1024


def _prune_cache() -> None:
    """Drop preview copies not used for 3 days, and the least recently used
    beyond 2 GB (at most every 10 minutes per process)."""
    prune_dir(cache_root("motion-graphics-assets"), max_bytes=CACHE_MAX_BYTES, max_age=CACHE_MAX_AGE_SECONDS)


def local_files(project, spec, *, folder: Optional[str] = None) -> tuple[dict, Optional[str]]:
    """({upload id: local path} for images the spec references, logo path)."""
    from .project import image_refs

    uploads = (project.assets or {}).get("uploads") or {}
    files = {}
    for uid in set(image_refs(spec)):
        up = uploads.get(uid)
        if up and up.get("kind") == "image":
            p = local_copy(up, project.user_id, folder)
            if p:
                files[uid] = p
    logo = None
    brand = project.brand or {}
    if brand.get("logo"):
        logo = local_copy(brand["logo"], project.user_id, folder)
    return files, logo
