"""Video generation routes with motion control."""

import io
import os
import re
import hmac
import math
import uuid
import hashlib
import logging
import tempfile
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, UploadFile, File, Header
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.dependencies import CurrentUser, DbSession
from app.models.content import Video, VideoGenerationJob
from app.schemas.video import (
    RecastGenerateRequest,
    VideoGenerateRequest,
    VideoResponse,
    VideoJobSubmitResponse,
    VideoJobStatusResponse,
    VideoJobResultResponse,
    VideoGalleryResponse,
    VideoUploadResponse,
    VideoFaceUploadResponse,
)
from app.clients.fal_client import (
    MOTION_CONTROL_TIERS,
    submit_video_generation,
    get_video_generation_status,
    get_video_generation_result,
    download_and_save_video,
    motion_control_endpoint,
    motion_job_tier,
    build_recast_arguments,
    submit_recast,
    story_output_seconds,
    is_content_policy_error,
    job_error_code,
    CONTENT_FILTER_CODE,
    CONTENT_FILTER_ERROR,
)
from app.services.pricing import (
    MOTION_CONTROL_MAX_SECONDS,
    RECAST_MAX_SECONDS,
    RECAST_MIN_SECONDS,
    RECAST_TIER_BY_RESOLUTION,
    motion_control_actual_usd,
    motion_control_reserved_seconds,
    motion_control_usd,
)
from app.services.job_state import (
    CLAIMABLE_STATUSES,
    claim_job,
    JOB_HANDED_BACK,
    fail_claimed_job,
    lock_job,
)
from app.services.usage import record_usage
from app.config import settings
from app.utils.security import scrubbed_env

logger = logging.getLogger(__name__)

router = APIRouter()


# Motion Control is priced per second of output at the chosen tier's price
# (pricing.MOTION_CONTROL_KEYS), and the output follows the reference video. fal is paid as soon as the job
# is submitted, so the length has to be known then. The upload endpoint
# measures it and carries it to /generate in the stored filename, signed:
# motion_ref_<uuid>-d<centiseconds>-<signature>.
# A reference without a signed length is estimated at the orientation's maximum.
_SIGNED_MOTION_REF = re.compile(
    r"motion_ref_([0-9a-f]{32})-d(\d{1,9})-([0-9a-f]{16})\.(?:mp4|webm|mov|m4v)$"
)

# Face images for V3 face lock: motion_face_<uuid>-<signature>.<ext>, signed for
# the uploading user. /generate accepts only these and rebuilds the public URL
# from storage, so fal is only sent a face this user uploaded and we checked.
_SIGNED_FACE = re.compile(r"^motion_face_([0-9a-f]{32})-([0-9a-f]{16})\.(?:png|jpg|webp|avif)$")

# fal's limits for the inputs (schemas of all three motion-control endpoints).
# Character image: 340 to 3850 px a side, aspect 0.4 to 2.5, at most 10 MB.
# Reference video: 340 to 3850 px a side, 3 to 30.05 s, at most 100 MB.
# Face element: at least 300x300 px, aspect 0.4 to 2.5 (fal allows 50 MB;
# 20 MB is plenty for one face).
CHARACTER_UPLOAD_MAX_BYTES = 25 * 1024 * 1024  # accepted, then fitted to fal's limits
CHARACTER_FAL_MAX_BYTES = 10 * 1024 * 1024
CHARACTER_MIN_SIDE = 340
CHARACTER_MAX_SIDE = 3850
CHARACTER_FIT_SIDE = 3840  # a larger image is scaled down to this
FACE_MAX_BYTES = 20 * 1024 * 1024
FACE_MIN_SIDE = 300
ASPECT_MIN = 0.4
ASPECT_MAX = 2.5
REFERENCE_MIN_SECONDS = 3.0
REFERENCE_SIDE_LIMITS = (340, 3850)
# Applied inward: a measured length must sit inside the provider's range by
# this margin, never on its edge. Our ffprobe reading and the provider's can
# differ by a few hundredths, and an input a hair over a cap fails the whole
# run (a 30.08 s clip against a 30 s limit is refused).
DURATION_SLACK_SECONDS = 0.05


def _seconds_text(seconds: float) -> str:
    """A length for messages; two decimals so 29.97 and 30.02 read apart."""
    return f"{seconds:.2f}".rstrip("0").rstrip(".")

# Still formats accepted for the character and face images (Pillow format name
# to stored extension and content type). GIF is refused on purpose, see
# inspect_still_image.
STILL_FORMATS = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
    "AVIF": (".avif", "image/avif"),
}
STILL_FORMATS_TEXT = "JPG, PNG, WebP or AVIF"
VIDEO_FORMATS_TEXT = "MP4, MOV, WebM or M4V"


def _motion_duration_signature(user_id: int, token: str, centis: int) -> str:
    message = f"motion-duration:{user_id}:{token}:{centis}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()[:16]


def signed_motion_filename(user_id: int, duration_seconds: float, ext: str) -> str:
    token = uuid.uuid4().hex
    centis = int(math.ceil(duration_seconds * 100))
    return f"motion_ref_{token}-d{centis}-{_motion_duration_signature(user_id, token, centis)}{ext}"


def motion_duration_from_url(url: str, user_id: int) -> float | None:
    """The length measured at upload, if ``url`` is this user's signed upload."""
    from urllib.parse import urlparse

    name = (urlparse(url or "").path or "").rsplit("/", 1)[-1]
    match = _SIGNED_MOTION_REF.search(name)
    if not match:
        return None
    token, centis, signature = match.group(1), int(match.group(2)), match.group(3)
    if not hmac.compare_digest(signature, _motion_duration_signature(user_id, token, centis)):
        return None
    return centis / 100.0


def _face_signature(user_id: int, token: str) -> str:
    message = f"motion-face:{user_id}:{token}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()[:16]


def signed_face_filename(user_id: int, ext: str) -> str:
    token = uuid.uuid4().hex
    return f"motion_face_{token}-{_face_signature(user_id, token)}{ext}"


def signed_face_from_url(url: str, user_id: int) -> str | None:
    """The stored filename if ``url`` is this user's signed face upload."""
    from urllib.parse import urlparse

    try:
        name = (urlparse(url or "").path or "").rsplit("/", 1)[-1]
    except Exception:
        return None
    match = _SIGNED_FACE.match(name)
    if not match:
        return None
    if not hmac.compare_digest(match.group(2), _face_signature(user_id, match.group(1))):
        return None
    return name


def inspect_still_image(content: bytes, *, min_side: int, label: str) -> dict:
    """Decode an uploaded still from its own bytes (the declared type is
    ignored). Returns format, ext, content_type, width and height; raises
    ValueError with a message fit for the user.

    GIF is refused although fal lists it: an animated GIF has no single frame
    to animate (fal would pick one for us), its 256-colour palette dithers the
    face and clothing the model copies, and every source of a GIF can save a
    PNG or JPG instead.
    """
    from PIL import Image, UnidentifiedImageError

    if not content:
        raise ValueError(f"The {label} file is empty.")
    try:
        with Image.open(io.BytesIO(content)) as img:
            fmt = (img.format or "").upper()
            width, height = img.size
            img.verify()
    except (UnidentifiedImageError, Image.DecompressionBombError):
        raise ValueError(f"The {label} is not a readable image. Upload a {STILL_FORMATS_TEXT} file.")
    except Exception:
        raise ValueError(f"The {label} could not be read. Upload a {STILL_FORMATS_TEXT} file.")

    if fmt == "GIF":
        raise ValueError(
            f"GIF is not supported for the {label}. Save the frame you want as PNG or JPG and upload that."
        )
    if fmt not in STILL_FORMATS:
        raise ValueError(f"Unsupported image format. Upload a {STILL_FORMATS_TEXT} file.")
    if not width or not height:
        raise ValueError(f"The {label} has no size.")
    if min(width, height) < min_side:
        raise ValueError(
            f"The {label} is {width}x{height}. It needs to be at least {min_side}x{min_side} pixels."
        )
    ratio = width / height
    if ratio < ASPECT_MIN or ratio > ASPECT_MAX:
        raise ValueError(
            f"The {label} is {width}x{height} (aspect ratio {ratio:.2f}). It needs an aspect ratio "
            f"between {ASPECT_MIN} and {ASPECT_MAX} (from tall 2:5 to wide 5:2). Crop it and upload again."
        )
    ext, content_type = STILL_FORMATS[fmt]
    return {"format": fmt, "ext": ext, "content_type": content_type, "width": width, "height": height}


def prepare_character_image(content: bytes) -> dict:
    """Validate the character image and fit it to fal's limits.

    An image over 3850 px a side (a 12 MP phone photo is 4032x3024) or over
    10 MB is scaled to fit 3840 px and re-encoded (JPEG, or WebP when it has
    transparency) instead of being refused by fal after the upload. Returns the
    inspect_still_image fields plus ``content`` (the bytes to store).
    """
    from PIL import Image, ImageOps

    info = inspect_still_image(content, min_side=CHARACTER_MIN_SIDE, label="character image")
    if max(info["width"], info["height"]) <= CHARACTER_MAX_SIDE and len(content) <= CHARACTER_FAL_MAX_BYTES:
        return {**info, "content": content}

    try:
        with Image.open(io.BytesIO(content)) as img:
            img = ImageOps.exif_transpose(img)
            has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)
            img = img.convert("RGBA" if has_alpha else "RGB")
            img.thumbnail((CHARACTER_FIT_SIDE, CHARACTER_FIT_SIDE), Image.LANCZOS)
            for quality in (92, 85, 75):
                buf = io.BytesIO()
                if has_alpha:
                    img.save(buf, format="WEBP", quality=quality)
                else:
                    img.save(buf, format="JPEG", quality=quality, optimize=True)
                data = buf.getvalue()
                if len(data) <= CHARACTER_FAL_MAX_BYTES:
                    break
            else:
                data = None
            width, height = img.size
    except ValueError:
        # Callers show a ValueError's text to the user; Pillow's is technical.
        logger.warning("Character image resize failed", exc_info=True)
        raise ValueError("The character image could not be resized. Save it as JPG or PNG and upload it again.")
    if data is None:
        raise ValueError("The character image is too large even after resizing. Upload a smaller image.")
    ext, content_type = (".webp", "image/webp") if has_alpha else (".jpg", "image/jpeg")
    return {
        "format": "WEBP" if has_alpha else "JPEG",
        "ext": ext,
        "content_type": content_type,
        "width": width,
        "height": height,
        "content": data,
    }


def sniff_reference_video(content: bytes) -> tuple[str, str]:
    """(extension, content type) of a motion reference from its own bytes;
    raises ValueError unless it is MP4, MOV, M4V or WebM.

    GIF is refused although fal lists it: it has no audio (so "Keep original
    audio" would do nothing), its low frame rate and dithered palette make
    pose tracking worse, the page cannot preview or measure it, and any GIF
    converts to MP4 in one step.
    """
    head = content[:64]
    if head[:6] in (b"GIF87a", b"GIF89a"):
        raise ValueError(
            f"GIF is not supported for the motion reference. Convert it to MP4 and upload that ({VIDEO_FORMATS_TEXT})."
        )
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand == b"qt  ":
            return ".mov", "video/quicktime"
        if brand.startswith(b"M4V"):
            return ".m4v", "video/x-m4v"
        if brand.startswith((b"M4A", b"M4B", b"M4P")):
            raise ValueError(f"That is an audio file. Upload a video ({VIDEO_FORMATS_TEXT}).")
        return ".mp4", "video/mp4"
    if len(head) >= 8 and head[4:8] in (b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot"):
        return ".mov", "video/quicktime"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        if b"webm" in content[:4096]:
            return ".webm", "video/webm"
        raise ValueError(f"MKV is not supported. Upload {VIDEO_FORMATS_TEXT}.")
    raise ValueError(f"Unsupported video format. Upload {VIDEO_FORMATS_TEXT}.")


def _probe_upload_duration(content: bytes, ext: str) -> float | None:
    """Length of an uploaded media file in seconds (ffprobe), or None if
    unreadable. Lip Sync measures its audio with this."""
    from app.routers.subtitle import probe_video_duration

    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            path = tmp.name
        return probe_video_duration(path)
    finally:
        if path:
            try:
                os.unlink(path)
            except Exception:
                pass


def _probe_reference(content: bytes, ext: str) -> dict | None:
    """ffprobe an uploaded reference: {"duration", "width", "height",
    "has_video"}, or None when ffprobe is missing or cannot read it."""
    import json
    import subprocess

    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            path = tmp.name
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams",
                # The upload is user-controlled and ffprobe sniffs the real
                # format: a playlist posing as .mp4 must not make it fetch URLs.
                "-protocol_whitelist", "file",
                path,
            ],
            capture_output=True, text=True, timeout=30, env=scrubbed_env(),
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout or "{}")
        duration = float((data.get("format") or {}).get("duration") or 0) or None
        video = next((st for st in data.get("streams", []) if st.get("codec_type") == "video"), None)
        return {
            "duration": duration,
            "width": video.get("width") if video else None,
            "height": video.get("height") if video else None,
            "has_video": video is not None,
        }
    except Exception as e:
        logger.warning(f"ffprobe of motion reference failed: {e}")
        return None
    finally:
        if path:
            try:
                os.unlink(path)
            except Exception:
                pass


def check_reference_probe(probe: dict) -> None:
    """Refuse a reference fal would refuse; raises ValueError with a message
    fit for the user. The orientation is chosen later, so the upload allows the
    largest cap and /generate checks the chosen one."""
    if not probe.get("has_video"):
        raise ValueError(f"The file has no video track. Upload a video ({VIDEO_FORMATS_TEXT}).")
    seconds = probe.get("duration")
    longest = max(MOTION_CONTROL_MAX_SECONDS.values())
    if seconds is not None:
        if seconds < REFERENCE_MIN_SECONDS + DURATION_SLACK_SECONDS:
            raise ValueError(
                f"The reference video is {_seconds_text(seconds)} seconds long. It needs to be longer than "
                f"{REFERENCE_MIN_SECONDS:g} seconds."
            )
        if seconds > longest - DURATION_SLACK_SECONDS:
            raise ValueError(
                f"The reference video is {_seconds_text(seconds)} seconds long. Motion Control accepts clips shorter "
                f"than {longest} seconds (Match the video), or {MOTION_CONTROL_MAX_SECONDS['image']} seconds with "
                "Match the image. Trim it and upload again."
            )
    low, high = REFERENCE_SIDE_LIMITS
    width, height = probe.get("width"), probe.get("height")
    if width and height and (min(width, height) < low or max(width, height) > high):
        raise ValueError(
            f"The reference video is {width}x{height}. Each side must be between {low} and {high} pixels."
        )


def _asset_still_problem(asset, *, min_side: int, max_bytes: int, label: str) -> str | None:
    """Why an image asset cannot be sent to Kling as is, or None."""
    if asset.content_type not in {ct for _ext, ct in STILL_FORMATS.values()}:
        return f"The {label} must be a JPG, PNG or WebP image. SVG logos cannot be used."
    width, height = asset.width or 0, asset.height or 0
    if not width or not height:
        return f"The size of that {label} is unknown. Upload it again."
    if min(width, height) < min_side:
        return f"The {label} is {width}x{height}. It needs to be at least {min_side}x{min_side} pixels."
    ratio = width / height
    if ratio < ASPECT_MIN or ratio > ASPECT_MAX:
        return (
            f"The {label} is {width}x{height} (aspect ratio {ratio:.2f}). It needs an aspect ratio between "
            f"{ASPECT_MIN} and {ASPECT_MAX} (from tall 2:5 to wide 5:2). Crop it and upload it again."
        )
    if (asset.file_size_bytes or 0) > max_bytes:
        return f"The {label} is larger than {max_bytes // (1024 * 1024)} MB."
    return None


def _face_asset_url(db, user_id: int, asset_id: int) -> str:
    from app.services import assets as asset_service

    try:
        asset = asset_service.owned(db, user_id, asset_id, ("image", "logo"))
    except asset_service.AssetNotFound:
        raise ValueError("That face image is no longer in My Assets. Pick another one.")
    problem = _asset_still_problem(asset, min_side=FACE_MIN_SIDE, max_bytes=FACE_MAX_BYTES, label="face image")
    if problem:
        raise ValueError(problem)
    return asset_service.url_of(asset)


def _reference_asset(db, user_id: int, asset_id: int) -> tuple[str, float | None]:
    """(URL, measured seconds) of a reference video from My Assets."""
    from app.services import assets as asset_service

    try:
        asset = asset_service.owned(db, user_id, asset_id, ("video",))
    except asset_service.AssetNotFound:
        raise ValueError("That video is no longer in My Assets. Pick another one.")
    if (asset.file_size_bytes or 0) > settings.MAX_VIDEO_UPLOAD_SIZE_MB * 1024 * 1024:
        raise ValueError(f"The reference video is larger than {settings.MAX_VIDEO_UPLOAD_SIZE_MB} MB.")
    check_reference_probe({
        "has_video": True,
        "duration": asset.duration_seconds,
        "width": asset.width,
        "height": asset.height,
    })
    return asset_service.url_of(asset), asset.duration_seconds


def check_orientation_duration(orientation: str, seconds: float | None) -> None:
    """Refuse a measured reference outside what the orientation allows
    (unknown lengths pass; fal enforces its own limits on those)."""
    if seconds is None:
        return
    cap = MOTION_CONTROL_MAX_SECONDS.get(orientation)
    if cap is not None and seconds > cap - DURATION_SLACK_SECONDS:
        if orientation == "image":
            raise ValueError(
                f"The reference video is {_seconds_text(seconds)} seconds long. Match the image accepts clips "
                f"shorter than {cap} seconds: switch to Match the video (under "
                f"{MOTION_CONTROL_MAX_SECONDS['video']} seconds) or trim the clip."
            )
        raise ValueError(
            f"The reference video is {_seconds_text(seconds)} seconds long. Match the video accepts clips shorter "
            f"than {cap} seconds. Trim the clip."
        )
    if seconds < REFERENCE_MIN_SECONDS + DURATION_SLACK_SECONDS:
        raise ValueError(
            f"The reference video is {_seconds_text(seconds)} seconds long. It needs to be longer than "
            f"{REFERENCE_MIN_SECONDS:g} seconds."
        )


@router.post("/upload-image")
async def upload_source_image(
    current_user: CurrentUser,
    db: DbSession,
    image: UploadFile = File(...),
):
    """Upload the character image for Motion Control.

    FAL's Kling Video API requires hosted URLs for source images.
    JPG, PNG, WebP or AVIF up to 25 MB, at least 340 px a side, aspect ratio
    0.4 to 2.5. The bytes are decoded to check the real format; the declared
    type is ignored. An image over fal's 3850 px or 10 MB limits is scaled
    down to fit (prepare_character_image).
    """
    from app.services.storage_service import storage_service

    content = await image.read(CHARACTER_UPLOAD_MAX_BYTES + 1)
    if len(content) > CHARACTER_UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image file too large. Maximum size is 25 MB.",
        )
    try:
        info = await run_in_threadpool(prepare_character_image, content)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    data = info["content"]
    filename = f"src_{uuid.uuid4()}{info['ext']}"

    # Save to storage, in the user's folder
    url = await storage_service.upload_file(
        file_data=data,
        filename=filename,
        storage_type="uploads",
        content_type=info["content_type"],
        user_id=current_user.id,
    )

    logger.info(
        f"Source image uploaded: {filename} ({len(data) / 1024:.2f} KB, {info['width']}x{info['height']})"
    )

    return {
        "url": url,
        "filename": filename,
        "file_size_bytes": len(data),
        "width": info["width"],
        "height": info["height"],
        "message": "Image uploaded successfully",
    }


@router.post("/asset-image/{asset_id}")
async def use_asset_image(asset_id: int, current_user: CurrentUser, db: DbSession):
    """Use an image from My Assets as the character image.

    Answers like /upload-image. An image within fal's limits is used where it
    is; a larger one (a 12 MP phone photo) is fitted with
    prepare_character_image and stored as a separate upload, as /upload-image
    would.
    """
    from app.services import assets as asset_service
    from app.services.storage_service import storage_service

    try:
        asset = asset_service.owned(db, current_user.id, asset_id, ("image", "logo"))
    except asset_service.AssetNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    problem = _asset_still_problem(
        asset, min_side=CHARACTER_MIN_SIDE, max_bytes=CHARACTER_FAL_MAX_BYTES, label="character image"
    )
    if problem is None and max(asset.width or 0, asset.height or 0) <= CHARACTER_MAX_SIDE:
        return {
            "url": asset_service.url_of(asset),
            "filename": asset.filename,
            "file_size_bytes": int(asset.file_size_bytes or 0),
            "width": asset.width,
            "height": asset.height,
            "message": "Image ready",
        }

    content = await storage_service.get_file_bytes(asset.filename, asset.storage_type, user_id=asset.user_id)
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The image file is missing. Upload it again.")
    try:
        info = await run_in_threadpool(prepare_character_image, content)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    data = info["content"]
    filename = f"src_{uuid.uuid4()}{info['ext']}"
    url = await storage_service.upload_file(
        file_data=data,
        filename=filename,
        storage_type="uploads",
        content_type=info["content_type"],
        user_id=current_user.id,
    )
    logger.info(f"Character image fitted from asset {asset.id}: {filename} ({info['width']}x{info['height']})")
    return {
        "url": url,
        "filename": filename,
        "file_size_bytes": len(data),
        "width": info["width"],
        "height": info["height"],
        "message": "Image ready",
    }


@router.post("/upload-face", response_model=VideoFaceUploadResponse)
async def upload_face_image(
    current_user: CurrentUser,
    db: DbSession,
    image: UploadFile = File(...),
):
    """Upload a face for Kling V3 face lock (fal element @Element1).

    A clear, front-facing face: JPG, PNG, WebP or AVIF up to 20 MB, at least
    300x300 px, aspect ratio 0.4 to 2.5. Stored under a name signed for this
    user; /generate accepts only such names.
    """
    from app.services.storage_service import storage_service

    content = await image.read(FACE_MAX_BYTES + 1)
    if len(content) > FACE_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Face image too large. Maximum size is 20 MB.",
        )
    try:
        info = await run_in_threadpool(
            lambda: inspect_still_image(content, min_side=FACE_MIN_SIDE, label="face image")
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    filename = signed_face_filename(current_user.id, info["ext"])
    url = await storage_service.upload_file(
        file_data=content,
        filename=filename,
        storage_type="uploads",
        content_type=info["content_type"],
        user_id=current_user.id,
    )
    logger.info(f"Face image uploaded: {filename} ({len(content) / 1024:.1f} KB, {info['width']}x{info['height']})")

    return VideoFaceUploadResponse(
        url=url,
        filename=filename,
        file_size_bytes=len(content),
        width=info["width"],
        height=info["height"],
    )


@router.post("/upload", response_model=VideoUploadResponse)
async def upload_motion_video(
    current_user: CurrentUser,
    db: DbSession,
    video: UploadFile = File(...),
):
    """Upload a motion reference video.

    Returns a URL that can be used for video generation.
    Maximum file size: 100MB
    Supported formats: MP4, MOV, WebM, M4V, recognised from the bytes (the
    declared type is ignored). fal needs 3 to 30 seconds and 340 to 3850 px a
    side; the orientation's own cap (10 s for "image") is checked by /generate.
    """
    from app.services.storage_service import storage_service

    max_size = settings.MAX_VIDEO_UPLOAD_SIZE_MB * 1024 * 1024
    content = await video.read(max_size + 1)
    file_size = len(content)
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Video file too large. Maximum size is {settings.MAX_VIDEO_UPLOAD_SIZE_MB}MB",
        )

    try:
        ext, content_type = sniff_reference_video(content)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Measure the length for the per-second price. Only a real measurement is
    # signed into the filename; anything else is reserved at the maximum.
    probe = await run_in_threadpool(_probe_reference, content, ext)
    measured = None
    if probe is not None:
        try:
            check_reference_probe(probe)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        measured = probe.get("duration")
    if measured is not None:
        filename = signed_motion_filename(current_user.id, measured, ext)
    else:
        filename = f"upload_{uuid.uuid4()}{ext}"

    # Save to storage, in the user's folder
    url = await storage_service.upload_file(
        file_data=content,
        filename=filename,
        storage_type="uploads",
        content_type=content_type,
        user_id=current_user.id,
    )

    logger.info(f"Video uploaded: {filename} ({file_size / 1024 / 1024:.2f} MB)")

    return VideoUploadResponse(
        url=url,
        filename=filename,
        file_size_bytes=file_size,
        duration_seconds=measured,
        message="Video uploaded successfully",
    )


@router.post("/generate", response_model=VideoJobSubmitResponse)
async def generate_video_endpoint(
    body: VideoGenerateRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Submit async video generation job with motion control.

    Returns a job_id immediately. Poll /video/status/{job_id} for progress,
    then fetch results from /video/result/{job_id} when complete.

    """
    if body.character_orientation not in ("video", "image"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="character_orientation must be 'video' or 'image'",
        )

    tier = body.model_tier
    tier_cfg = MOTION_CONTROL_TIERS[tier]

    # Face lock (fal element @Element1): Kling V3 only, and only when the
    # orientation follows the reference video. Only this user's signed upload
    # is accepted; its URL is rebuilt from storage, not taken from the client.
    face_image_url = None
    if body.face_image_url or body.face_asset_id is not None:
        if not tier_cfg["supports_elements"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Face lock needs a Kling V3 model. {tier_cfg['label']} does not support it: "
                    "choose V3 Standard or V3 Pro, or remove the face image."
                ),
            )
        if body.character_orientation != "video":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Face lock only works with the 'Match the video' orientation. Switch the "
                    "orientation to video, or remove the face image."
                ),
            )
        if body.face_asset_id is not None:
            try:
                face_image_url = _face_asset_url(db, current_user.id, body.face_asset_id)
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        else:
            face_name = signed_face_from_url(body.face_image_url, current_user.id)
            if not face_name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The face image must be uploaded on this page or picked from My Assets. Add it again.",
                )
            from app.services.storage_service import storage_service

            face_image_url = storage_service.get_public_url(face_name, "uploads", user_id=current_user.id)

    # Priced per second of output at the tier's price (app/services/pricing.py).
    # Estimated on the reference video's measured length, or the orientation's
    # maximum when it is not known; recorded on the real output length.
    try:
        if body.motion_reference_asset_id is not None:
            motion_reference_url, probed = _reference_asset(db, current_user.id, body.motion_reference_asset_id)
        elif body.motion_reference:
            motion_reference_url = body.motion_reference
            probed = motion_duration_from_url(body.motion_reference, current_user.id)
        else:
            raise ValueError("Add a motion reference video.")
        check_orientation_duration(body.character_orientation, probed)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    reserved_seconds = motion_control_reserved_seconds(body.character_orientation, probed)
    estimated_usd = motion_control_usd(reserved_seconds, tier)

    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Submit to FAL. Blocking network calls: off the event loop.
        result = await run_in_threadpool(
            submit_video_generation,
            source_image_url=body.source_image,
            motion_reference_url=motion_reference_url,
            db=db,
            character_orientation=body.character_orientation,
            tier=tier,
            prompt=body.prompt,
            keep_original_sound=body.keep_original_sound,
            face_image_url=face_image_url,
        )

        # Create job record
        job = VideoGenerationJob(
            job_id=job_id,
            request_id=result["request_id"],
            user_id=current_user.id,
            source_image_url=body.source_image,
            motion_reference_url=motion_reference_url,
            face_image_url=face_image_url,
            character_orientation=body.character_orientation,
            prompt=(body.prompt or "").strip() or None,
            model=result["model"],
            status="pending",
            estimated_usd=estimated_usd,
        )
        db.add(job)
        db.commit()

        logger.info(f"Video generation job submitted: {job_id} ({tier_cfg['label']}, {reserved_seconds}s reserved)")

        return VideoJobSubmitResponse(
            job_id=job_id,
            status="pending",
            message="Video generation job submitted. Poll /video/status/{job_id} for progress.",
        )

    except ValueError as e:
        # The request was validated above: what is left is a rejected file URL
        # or the provider.
        logger.error(f"Video generation submit rejected: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The image or motion video could not be used. Upload them again and retry.",
        )
    except Exception as e:
        logger.error(f"Video generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="We could not start this video right now. Please try again in a moment.",
        )



def _recast_video(db, user_id: int, body: RecastGenerateRequest) -> tuple[str, float]:
    """(URL, measured seconds) of the source video: this user's signed upload
    or a video from My Assets. Raises ValueError with a message fit for the user."""
    from app.services.storage_service import storage_service

    if body.video_asset_id is not None:
        url, seconds = _reference_asset(db, user_id, body.video_asset_id)
    elif body.video_url:
        seconds = motion_duration_from_url(body.video_url, user_id)
        if seconds is None:
            raise ValueError("Upload the source video on this page or pick it from My Assets.")
        from urllib.parse import urlparse

        name = (urlparse(body.video_url).path or "").rsplit("/", 1)[-1]
        url = storage_service.get_public_url(name, "uploads", user_id=user_id)
    else:
        raise ValueError("Add the source video.")
    if not seconds:
        raise ValueError("The length of that video is unknown. Upload it again.")
    if seconds < RECAST_MIN_SECONDS + DURATION_SLACK_SECONDS:
        raise ValueError(
            f"The video is {_seconds_text(seconds)} seconds long. Multi-character recast needs a clip longer than "
            f"{RECAST_MIN_SECONDS:g} seconds."
        )
    if seconds > RECAST_MAX_SECONDS - DURATION_SLACK_SECONDS:
        raise ValueError(
            f"The video is {_seconds_text(seconds)} seconds long. Multi-character recast accepts clips shorter than "
            f"{RECAST_MAX_SECONDS:g} seconds. Trim it and upload again."
        )
    return url, float(seconds)


def _recast_reference_urls(db, user_id: int, body: RecastGenerateRequest) -> list[str]:
    """Public URLs of the reference photos, in order, each this user's signed
    face upload or image asset. Raises ValueError."""
    from app.services.storage_service import storage_service

    urls = []
    for i, ref in enumerate(body.references, start=1):
        if ref.asset_id is not None:
            try:
                urls.append(_face_asset_url(db, user_id, ref.asset_id))
            except ValueError as e:
                raise ValueError(f"Photo {i}: {e}")
            continue
        name = signed_face_from_url(ref.image_url or "", user_id)
        if not name:
            raise ValueError(f"Photo {i} must be uploaded on this page or picked from My Assets. Add it again.")
        urls.append(storage_service.get_public_url(name, "uploads", user_id=user_id))
    if len(set(urls)) != len(urls):
        raise ValueError("The same photo is used twice. Use one photo per person.")
    return urls


@router.post("/recast", response_model=VideoJobSubmitResponse)
async def generate_recast(
    body: RecastGenerateRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Multi-character motion transfer with MiniMax H3 Max Recast.

    Up to four people in a 5 to 15 second source video are replaced by one
    reference photo each, keeping the motion and the source sound. Runs as a
    Motion Control job: poll /video/status/{job_id}, then fetch
    /video/result/{job_id}. Estimated on the measured video length at the
    resolution's price and recorded on the real output length, never higher.
    """
    tier = RECAST_TIER_BY_RESOLUTION[body.resolution]
    try:
        video_url, seconds = _recast_video(db, current_user.id, body)
        reference_urls = _recast_reference_urls(db, current_user.id, body)
        arguments = build_recast_arguments(
            video_url, reference_urls, body.resolution, prompt=body.prompt, enhance_realism=body.enhance_realism,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    reserved_seconds = int(min(RECAST_MAX_SECONDS, max(1, math.ceil(round(seconds, 1)))))
    estimated_usd = motion_control_usd(reserved_seconds, tier)

    job_id = str(uuid.uuid4())
    try:
        # Blocking network calls: off the event loop.
        result = await run_in_threadpool(submit_recast, arguments, db)
        job = VideoGenerationJob(
            job_id=job_id,
            request_id=result["request_id"],
            user_id=current_user.id,
            source_image_url=reference_urls[0],
            motion_reference_url=video_url,
            character_orientation="video",
            prompt=(body.prompt or "").strip() or None,
            model=result["model"],
            status="pending",
            estimated_usd=estimated_usd,
            options={
                "tier": tier,
                "resolution": body.resolution,
                "reference_image_urls": reference_urls,
                "enhance_realism": bool(body.enhance_realism),
                "video_seconds": round(seconds, 2),
            },
        )
        db.add(job)
        db.commit()
    except ValueError as e:
        db.rollback()
        logger.error(f"Recast submit rejected: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The video or photos could not be used. Upload them again and retry.",
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Recast submit failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit the recast. Please try again.",
        )

    logger.info(f"Recast job submitted: {job_id} ({len(reference_urls)} people, {reserved_seconds}s {body.resolution}, "
                f"estimated ${estimated_usd:g})")
    return VideoJobSubmitResponse(
        job_id=job_id,
        status="pending",
        message="Recast submitted. Poll /video/status/{job_id} for progress.",
    )

@router.get("/status/{job_id}", response_model=VideoJobStatusResponse)
async def get_video_job_status(
    job_id: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get status of a video generation job."""
    job = db.query(VideoGenerationJob).filter(
        VideoGenerationJob.job_id == job_id,
        VideoGenerationJob.user_id == current_user.id,
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # Return cached status if truly completed (has video result)
    if job.status == "completed" and job.result and job.result.get("video_id"):
        return VideoJobStatusResponse(
            job_id=job.job_id,
            status="completed",
            progress=100,
            logs=job.logs.split("\n") if job.logs else None,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
        )

    # Return failed status
    if job.status == "failed":
        return VideoJobStatusResponse(
            job_id=job.job_id,
            status="failed",
            progress=0,
            logs=job.logs.split("\n") if job.logs else None,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
        )

    # If processing, don't poll FAL - just return current status
    if job.status == "processing":
        return VideoJobStatusResponse(
            job_id=job.job_id,
            status="processing",
            progress=job.progress or 75,
            logs=job.logs.split("\n") if job.logs else None,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
        )

    # Poll FAL for current status, on the endpoint the job was submitted to
    try:
        fal_status = await run_in_threadpool(get_video_generation_status, job.request_id, db, job.model)

        # Re-read under the row lock: the scheduler or the result endpoint may
        # have claimed the job while fal answered, and a stale write would
        # make it claimable again.
        job = lock_job(db, VideoGenerationJob, job.id)
        if job.status not in CLAIMABLE_STATUSES:
            db.rollback()
            fal_status = {"status": job.status, "logs": fal_status.get("logs")}
        elif fal_status.get("completed"):
            # FAL is done - mark as in_progress with high progress
            # Let scheduler or result endpoint do the actual processing
            if job.status == "pending":
                job.status = "in_progress"
            job.progress = 90  # High progress indicates FAL is done
            if not job.started_at:
                job.started_at = datetime.utcnow()
        elif fal_status.get("in_progress"):
            job.status = "in_progress"
            job.progress = 50
            if not job.started_at:
                job.started_at = datetime.utcnow()
        elif fal_status.get("status") == "error":
            job.status = "failed"
            job.error = fal_status.get("error")

        # Store logs
        if fal_status.get("logs"):
            job.logs = "\n".join(fal_status["logs"])

        db.commit()

        # Return status - use "ready" when FAL is complete but video not yet processed
        # This tells the frontend it can call the result endpoint
        if fal_status.get("completed"):
            response_status = "ready"  # Changed from "completed" to "ready"
            response_progress = 95
        else:
            response_status = job.status
            response_progress = job.progress or 0

        return VideoJobStatusResponse(
            job_id=job.job_id,
            status=response_status,
            progress=response_progress,
            logs=fal_status.get("logs"),
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
        )

    except Exception as e:
        logger.error(f"Failed to get video job status: {e}", exc_info=True)
        return VideoJobStatusResponse(
            job_id=job.job_id,
            status=job.status,
            progress=job.progress or 0,
            error="We could not check this video just now. It is still running, so please check again in a moment.",
            created_at=job.created_at,
            started_at=job.started_at,
        )


@router.get("/result/{job_id}", response_model=VideoJobResultResponse)
async def get_video_job_result(
    job_id: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get result of a completed video generation job.

    Downloads the video from FAL, saves it locally, creates a Video record
    and records what it cost.
    """
    # No row lock here: it would be held across the fal calls below. The job
    # is claimed atomically (claim_job) once fal reports it finished.
    job = db.query(VideoGenerationJob).filter(
        VideoGenerationJob.job_id == job_id,
        VideoGenerationJob.user_id == current_user.id,
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # GUARD 1: Return cached result if already processed
    if job.result and job.result.get("video_id"):
        video_id = job.result.get("video_id")
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            return VideoJobResultResponse(
                job_id=job.job_id,
                status="completed",
                video=VideoResponse.from_orm_with_urls(video),
                estimated_usd=job.estimated_usd or 0,
                completed_at=job.completed_at,
            )

    # GUARD 2: If job is being processed by scheduler, don't interfere
    if job.status == "processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is currently being processed. Please try again in a few seconds.",
        )

    if job.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=job.error or "Video generation failed",
        )

    # Check if job is complete with FAL (on the job's own endpoint)
    fal_status = await run_in_threadpool(get_video_generation_status, job.request_id, db, job.model)
    if not fal_status.get("completed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job not complete. Current status: {fal_status.get('status', 'unknown')}",
        )

    # Claim the job: only one caller (this endpoint or the scheduler) may
    # download and store it.
    if not claim_job(db, VideoGenerationJob, job.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is currently being processed. Please try again in a few seconds.",
        )
    db.refresh(job)

    try:
        # Fetch result from FAL
        fal_result = await run_in_threadpool(get_video_generation_result, job.request_id, db, job.model)

        # Download and save video (organized by user folder)
        video_data = await download_and_save_video(fal_result, user_id=job.user_id)

        # GUARD 3: Re-check job hasn't been processed while we were downloading
        db.refresh(job)
        if job.result and job.result.get("video_id"):
            logger.warning(f"Video job {job_id} was processed by another request while downloading")
            video = db.query(Video).filter(Video.id == job.result["video_id"]).first()
            if video:
                return VideoJobResultResponse(
                    job_id=job.job_id,
                    status="completed",
                    video=VideoResponse.from_orm_with_urls(video),
                    estimated_usd=job.estimated_usd or 0,
                    completed_at=job.completed_at,
                )

        # Save video to database
        video = Video(
            filename=video_data["filename"],
            thumbnail_filename=video_data.get("thumbnail_filename"),
            source_image_url=job.source_image_url,
            motion_reference_url=job.motion_reference_url,
            character_orientation=job.character_orientation,
            prompt=job.prompt,
            duration_seconds=video_data.get("duration_seconds"),
            width=video_data.get("width"),
            height=video_data.get("height"),
            fps=video_data.get("fps"),
            model=motion_control_endpoint(job.model),
            file_size_bytes=video_data.get("file_size_bytes"),
            user_id=current_user.id,
        )
        db.add(video)
        db.flush()

        # Recorded on the real output length at the job's tier, never above
        # the estimate
        usd, billed_seconds = motion_control_actual_usd(
            job.estimated_usd,
            story_output_seconds(fal_result, video_data.get("duration_seconds")),
            motion_job_tier(job),
        )
        record_usage(
            db,
            feature="video",
            usd=usd,
            model=motion_control_endpoint(job.model),
            units=billed_seconds,
            unit="second",
            job_type="video",
            job_id=job.job_id,
            detail={
                "character_orientation": job.character_orientation,
                "duration_seconds": video_data.get("duration_seconds"),
                "source": "result_endpoint",
            },
        )

        # Update job
        job.status = "completed"
        job.progress = 100
        job.estimated_usd = usd
        job.completed_at = datetime.utcnow()
        job.result = {"video_id": video.id}

        db.commit()

        logger.info(f"Video generation completed via result endpoint: {job_id}")

        return VideoJobResultResponse(
            job_id=job.job_id,
            status="completed",
            video=VideoResponse.from_orm_with_urls(video),
            estimated_usd=usd,
            completed_at=job.completed_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Video processing failed: {e}", exc_info=True)
        if is_content_policy_error(e):
            # A moderation refusal: nothing to save.
            fail_claimed_job(db, VideoGenerationJob, job.id, CONTENT_FILTER_ERROR)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=CONTENT_FILTER_ERROR)
        message = "We could not save this video. Please try generating it again."
        failed = fail_claimed_job(db, VideoGenerationJob, job.id, message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=message if failed else JOB_HANDED_BACK,
        )


@router.get("/gallery", response_model=VideoGalleryResponse)
async def get_video_gallery(
    current_user: CurrentUser,
    db: DbSession,
    page: int = 1,
    page_size: int = 20,
):
    """Get user's video gallery."""
    query = db.query(Video).filter(Video.user_id == current_user.id)
    total = query.count()

    videos = query.order_by(Video.created_at.desc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()

    return VideoGalleryResponse(
        videos=[VideoResponse.from_orm_with_urls(v) for v in videos],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
    )


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get a specific video."""
    video = db.query(Video).filter(
        Video.id == video_id,
        Video.user_id == current_user.id,
    ).first()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    return VideoResponse.from_orm_with_urls(video)


@router.delete("/{video_id}")
async def delete_video(
    video_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Delete a video (any type, including lip sync, faceless and motion
    graphics renders) and its stored files."""
    from app.services.storage_service import storage_service

    video = db.query(Video).filter(
        Video.id == video_id,
        Video.user_id == current_user.id,
    ).first()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    files = [(video.filename, "videos")]
    if video.thumbnail_filename:
        files.append((video.thumbnail_filename, "thumbnails"))
    user_id = video.user_id

    # Database first: a failed commit must not leave a row whose file is gone.
    db.delete(video)
    db.commit()

    # Then storage, best effort.
    for name, storage_type in files:
        try:
            await storage_service.delete_file(name, storage_type, user_id=user_id)
        except Exception as e:
            logger.warning(f"Could not delete {storage_type} file {name}: {e}")

    logger.info(f"Video deleted: {video_id}")

    return {"message": "Video deleted successfully"}


@router.get("/{video_id}/download")
async def download_video(
    video_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Download a video file."""
    from fastapi.responses import Response
    from app.services.storage_service import storage_service

    video = db.query(Video).filter(
        Video.id == video_id,
        Video.user_id == current_user.id,
    ).first()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    file_bytes = await storage_service.get_file_bytes(video.filename, "videos", user_id=video.user_id)

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file not found",
        )

    return Response(
        content=file_bytes,
        media_type="video/mp4",
        headers={
            "Content-Disposition": f'attachment; filename="{video.filename}"',
        }
    )


@router.post("/job/{job_id}/retry")
async def retry_video_job(
    job_id: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retry a stuck or failed video job.

    Resets the job status to 'in_progress' so the scheduler can reprocess it.
    Only works for jobs that are truly stuck (no video in gallery) or failed.
    """
    job = db.query(VideoGenerationJob).filter(
        VideoGenerationJob.job_id == job_id,
        VideoGenerationJob.user_id == current_user.id,
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    job = lock_job(db, VideoGenerationJob, job.id)

    # Check if video already exists for this job
    if job.result and job.result.get("video_id"):
        existing_video = db.query(Video).filter(
            Video.id == job.result["video_id"]
        ).first()
        if existing_video:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Video already exists for this job (video_id={existing_video.id}). No retry needed.",
            )

    # Check if job is stuck (completed/in_progress but no result) or failed
    is_stuck = job.status in ["completed", "in_progress"] and (not job.result or not job.result.get("video_id"))
    is_failed = job.status == "failed"

    if not is_stuck and not is_failed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is not stuck or failed. Only stuck/failed jobs can be retried.",
        )

    # The provider refused this request; fetching it again gives the same answer.
    if is_failed and job_error_code(job.error) == CONTENT_FILTER_CODE:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=CONTENT_FILTER_ERROR)

    # Reset job for reprocessing - clear result to ensure clean state
    job.status = "in_progress"
    job.progress = 50
    job.error = None
    job.completed_at = None
    job.result = None  # Clear result to ensure clean reprocessing

    db.commit()
    logger.info(f"Video job {job_id} reset for reprocessing")

    return {
        "message": "Job reset for reprocessing. The scheduler will process it within 30 seconds.",
        "job_id": job_id,
        "status": "in_progress",
    }


def parse_range_header(header: str | None, file_size: int) -> tuple[int, int] | None:
    """The inclusive byte range a Range header asks for, or None for the whole file.

    A header that is malformed, reversed or asks for several ranges is ignored, as
    RFC 9110 allows. A well-formed range that falls outside the file raises 416.
    """
    match = re.fullmatch(r"bytes=(\d{0,19})-(\d{0,19})", (header or "").strip())
    if not match or not (match.group(1) or match.group(2)):
        return None
    first, last = match.group(1), match.group(2)
    if first and last and int(last) < int(first):
        return None

    if first:
        start = int(first)
        end = min(int(last), file_size - 1) if last else file_size - 1
    else:
        # A suffix: the last N bytes.
        start = max(file_size - int(last), 0)
        end = file_size - 1
    if start >= file_size or end < start:
        raise HTTPException(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            detail="That range is outside the file.",
            headers={"Content-Range": f"bytes */{file_size}"},
        )
    return start, end


@router.get("/{video_id}/stream")
async def stream_video(
    video_id: int,
    current_user: CurrentUser,
    db: DbSession,
    range: str = Header(None),
):
    """Stream a video file with range request support for smooth playback."""
    from app.services.storage_service import storage_service

    # Owner only. Ids are sequential, so an open endpoint would hand anyone the
    # storage URL of every private video by counting upwards.
    video = db.query(Video).filter(
        Video.id == video_id,
        Video.user_id == current_user.id,
    ).first()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    filepath = storage_service.get_local_path(video.filename, "videos", user_id=video.user_id)

    if not os.path.exists(filepath):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file not found",
        )

    file_size = os.path.getsize(filepath)
    byte_range = parse_range_header(range, file_size)
    start, end = byte_range if byte_range else (0, file_size - 1)
    content_length = end - start + 1

    # Generator for streaming chunks
    def iterfile():
        with open(filepath, "rb") as f:
            f.seek(start)
            remaining = content_length
            chunk_size = 1024 * 1024  # 1MB chunks
            while remaining > 0:
                chunk = f.read(min(chunk_size, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
    }
    if byte_range:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    return StreamingResponse(
        iterfile(),
        status_code=206 if byte_range else 200,
        headers=headers,
        media_type="video/mp4",
    )
