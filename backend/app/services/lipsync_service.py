"""Lip Sync: a portrait image and an audio track to a talking video.

fal endpoint minimax/h3-max/lip-sync/image-to-video (async: submit, then poll
status and fetch the result, like Motion Control and Stories).

Pricing (app/services/pricing.py) is per second of output, and the output is
exactly as long as the audio. fal is paid as soon as the job is submitted, so
the length has to be known then: the upload endpoint measures the audio with
ffprobe and signs the measured length into the stored filename. The job is
estimated on that length and recorded on the real output length, never above
the estimate.

Both uploads are signed for the uploading user. /generate accepts only signed
filenames and rebuilds their public URLs from storage itself, so fal is only
ever sent files this user uploaded through these endpoints.
"""

import asyncio
import hashlib
import hmac
import io
import logging
import math
import re
import uuid
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.config import settings
from app.models.content import LipSyncJob, Video
from app.services.pricing import lipsync_actual_usd
from app.services.usage import record_usage

logger = logging.getLogger(__name__)

LIPSYNC_MODEL = "minimax/h3-max/lip-sync/image-to-video"

# fal's resolution enum is upper case ("768P"); the app and the price keys use
# lower case.
FAL_RESOLUTIONS = {"480p": "480P", "768p": "768P", "1080p": "1080P", "2k": "2K"}

# Portrait image limits. fal rejects an aspect ratio outside 0.4 to 2.5.
IMAGE_MAX_BYTES = 10 * 1024 * 1024
IMAGE_FORMATS = {
    "PNG": (".png", "image/png"),
    "JPEG": (".jpg", "image/jpeg"),
    "WEBP": (".webp", "image/webp"),
}
ASPECT_MIN = 0.4
ASPECT_MAX = 2.5

# Audio limits. fal needs at least 5 seconds and accepts up to 15 minutes, but
# every second is billed (and 1.2x over 15 seconds), so this release caps the
# audio at 2 minutes to bound what a single job can cost. Raise it here; the
# page reads the same number from LIPSYNC_MAX_SECONDS in pricingStore.ts.
AUDIO_MAX_BYTES = 25 * 1024 * 1024
AUDIO_MIN_SECONDS = 5.0
AUDIO_MAX_SECONDS = 120.0

# Stored names: lipsync_img_<uuid>-<sig>.<ext> and
# lipsync_aud_<uuid>-d<centiseconds>-<sig>.<ext>, signed for the user.
_SIGNED_IMAGE = re.compile(r"^lipsync_img_([0-9a-f]{32})-([0-9a-f]{16})\.(png|jpg|webp)$")
_SIGNED_AUDIO = re.compile(
    r"^lipsync_aud_([0-9a-f]{32})-d(\d{1,9})-([0-9a-f]{16})\.(mp3|wav|m4a|aac|ogg)$"
)


# -----------------------------------------------------------------------------
# Signed upload names
# -----------------------------------------------------------------------------

def _signature(kind: str, user_id: int, token: str, centis: int = 0) -> str:
    message = f"lipsync-{kind}:{user_id}:{token}:{centis}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()[:16]


def signed_image_filename(user_id: int, ext: str) -> str:
    token = uuid.uuid4().hex
    return f"lipsync_img_{token}-{_signature('image', user_id, token)}{ext}"


def signed_audio_filename(user_id: int, duration_seconds: float, ext: str) -> str:
    token = uuid.uuid4().hex
    centis = int(math.ceil(round(duration_seconds * 100, 6)))
    return f"lipsync_aud_{token}-d{centis}-{_signature('audio', user_id, token, centis)}{ext}"


def _filename_from_url(url: str) -> str:
    try:
        return (urlparse(url or "").path or "").rsplit("/", 1)[-1]
    except Exception:
        return ""


def signed_image_from_url(url: str, user_id: int) -> str | None:
    """The stored filename if ``url`` is this user's signed image upload."""
    name = _filename_from_url(url)
    match = _SIGNED_IMAGE.match(name)
    if not match:
        return None
    if not hmac.compare_digest(match.group(2), _signature("image", user_id, match.group(1))):
        return None
    return name


def signed_audio_from_url(url: str, user_id: int) -> tuple[str, float] | None:
    """(stored filename, measured seconds) if ``url`` is this user's signed audio upload."""
    name = _filename_from_url(url)
    match = _SIGNED_AUDIO.match(name)
    if not match:
        return None
    token, centis, signature = match.group(1), int(match.group(2)), match.group(3)
    if not hmac.compare_digest(signature, _signature("audio", user_id, token, centis)):
        return None
    return name, centis / 100.0


def upload_url(filename: str, user_id: int) -> str:
    """Public URL of one of this user's uploads, built by storage (not taken from the client)."""
    from app.services.storage_service import storage_service

    return storage_service.get_public_url(filename, "uploads", user_id=user_id)


# -----------------------------------------------------------------------------
# Upload validation
# -----------------------------------------------------------------------------

def inspect_image(content: bytes) -> dict:
    """Decode an uploaded portrait. Returns ext, content_type, width, height and
    aspect_ratio; raises ValueError with a message fit for the user."""
    from PIL import Image, UnidentifiedImageError

    if not content:
        raise ValueError("The image file is empty.")
    if len(content) > IMAGE_MAX_BYTES:
        raise ValueError("Image file too large. Maximum size is 10 MB.")
    try:
        with Image.open(io.BytesIO(content)) as img:
            fmt = (img.format or "").upper()
            width, height = img.size
            img.verify()
    except (UnidentifiedImageError, Image.DecompressionBombError):
        raise ValueError("The file is not a readable image. Upload a PNG, JPEG or WebP.")
    except Exception:
        raise ValueError("The image could not be read. Upload a PNG, JPEG or WebP.")

    if fmt not in IMAGE_FORMATS:
        raise ValueError("Unsupported image format. Upload a PNG, JPEG or WebP.")
    if not width or not height:
        raise ValueError("The image has no size.")
    ratio = width / height
    if ratio < ASPECT_MIN or ratio > ASPECT_MAX:
        raise ValueError(
            f"The image is {width}x{height} (aspect ratio {ratio:.2f}). Lip Sync needs an aspect "
            f"ratio between {ASPECT_MIN} and {ASPECT_MAX} (from tall 2:5 to wide 5:2). Crop it and upload again."
        )
    ext, content_type = IMAGE_FORMATS[fmt]
    return {
        "ext": ext,
        "content_type": content_type,
        "width": width,
        "height": height,
        "aspect_ratio": round(ratio, 4),
    }


def sniff_audio(content: bytes) -> tuple[str, str]:
    """(extension, content type) from the file's own bytes; raises ValueError
    unless it is MP3, WAV, M4A/AAC or Ogg."""
    head = content[:16]
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return ".wav", "audio/wav"
    if head[:4] == b"OggS":
        return ".ogg", "audio/ogg"
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return ".m4a", "audio/mp4"
    if head[:3] == b"ID3":
        return ".mp3", "audio/mpeg"
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        # Frame sync. ADTS (raw AAC) has layer bits 00; MPEG audio does not.
        if (head[1] & 0x06) == 0:
            return ".aac", "audio/aac"
        return ".mp3", "audio/mpeg"
    raise ValueError("Unsupported audio format. Upload MP3, WAV, M4A, AAC or OGG.")


def check_audio_length(seconds: float | None) -> float:
    """The measured length if Lip Sync accepts it; raises ValueError otherwise."""
    if seconds is None or seconds <= 0:
        raise ValueError("The audio length could not be read. Upload an MP3, WAV, M4A, AAC or OGG file.")
    if seconds < AUDIO_MIN_SECONDS:
        raise ValueError(
            f"The audio is {seconds:.1f} seconds long. Lip Sync needs at least {AUDIO_MIN_SECONDS:g} seconds."
        )
    if seconds > AUDIO_MAX_SECONDS:
        raise ValueError(
            f"The audio is {seconds:.1f} seconds long. Lip Sync accepts up to {AUDIO_MAX_SECONDS:g} seconds "
            f"({AUDIO_MAX_SECONDS / 60:g} minutes) for now. Trim it and upload again."
        )
    return seconds


# -----------------------------------------------------------------------------
# fal
# -----------------------------------------------------------------------------

def build_lipsync_arguments(
    image_url: str,
    audio_url: str,
    resolution: str,
    enable_transcription: bool,
    seed: int | None = None,
) -> dict:
    """fal arguments for minimax/h3-max/lip-sync/image-to-video."""
    res = (resolution or "").lower()
    if res not in FAL_RESOLUTIONS:
        raise ValueError("Resolution must be 480p, 768p, 1080p or 2k")
    arguments = {
        "image_url": image_url,
        "audio_url": audio_url,
        "resolution": FAL_RESOLUTIONS[res],
        "enable_transcription": bool(enable_transcription),
        "enable_safety_checker": True,
    }
    if seed is not None:
        arguments["seed"] = int(seed)
    return arguments


def submit_lipsync_job(arguments: dict, db: Session) -> str:
    """Submit to fal's queue; returns the request id. Blocking network calls."""
    from app.clients.fal_client import fal_submit, validate_video_url

    for field in ("image_url", "audio_url"):
        ok, error = validate_video_url(arguments.get(field) or "")
        if not ok:
            raise ValueError(f"Invalid {field.replace('_', ' ')}: {error}")

    handler = fal_submit(LIPSYNC_MODEL, arguments, db)
    logger.info(f"Lip sync job submitted to fal: {handler.request_id}")
    return handler.request_id


def get_lipsync_status(request_id: str, db: Session) -> dict:
    # The story status parser is endpoint-agnostic.
    from app.clients.fal_client import get_story_generation_status

    return get_story_generation_status(request_id, db, model=LIPSYNC_MODEL)


def get_lipsync_result(request_id: str, db: Session) -> dict:
    from app.clients.fal_client import get_story_generation_result

    return get_story_generation_result(request_id, db, model=LIPSYNC_MODEL)


def output_seconds(fal_result: dict | None, probed_seconds: float | None = None) -> float | None:
    """Length of the result: fal's top-level duration, else video.duration,
    else the length probed from the downloaded file."""
    result = fal_result if isinstance(fal_result, dict) else {}
    candidates = [result.get("duration")]
    video = result.get("video")
    if isinstance(video, dict):
        candidates.append(video.get("duration"))
    candidates.append(probed_seconds)
    for value in candidates:
        try:
            seconds = float(value) if value else 0.0
        except (TypeError, ValueError):
            seconds = 0.0
        if seconds > 0:
            return seconds
    return None


# -----------------------------------------------------------------------------
# Finishing a job (result endpoint and scheduler)
# -----------------------------------------------------------------------------

async def finish_lipsync_job(db: Session, job: LipSyncJob, source: str) -> Video:
    """Download a finished job's video, save it, record its cost and complete the job.

    The caller has already claimed the job (job_state.claim_job), which
    keeps the other path (scheduler or result endpoint) away from it.
    """
    from app.clients.fal_client import download_and_save_video

    # Blocking network call: off the event loop.
    fal_result = await asyncio.to_thread(get_lipsync_result, job.request_id, db)
    video_data = await download_and_save_video(fal_result, user_id=job.user_id)

    # Another path may have finished it while we were downloading.
    db.refresh(job)
    if job.result and job.result.get("video_id"):
        existing = db.query(Video).filter(Video.id == job.result["video_id"]).first()
        if existing:
            logger.warning(f"Lip sync job {job.job_id} was finished elsewhere while downloading")
            return existing

    seed = fal_result.get("seed") if isinstance(fal_result, dict) else None
    video = Video(
        filename=video_data["filename"],
        thumbnail_filename=video_data.get("thumbnail_filename"),
        source_image_url=job.image_url,
        video_type="lipsync",
        duration_seconds=video_data.get("duration_seconds"),
        width=video_data.get("width"),
        height=video_data.get("height"),
        fps=video_data.get("fps"),
        model=job.model or LIPSYNC_MODEL,
        seed=seed if isinstance(seed, int) else None,
        file_size_bytes=video_data.get("file_size_bytes"),
        user_id=job.user_id,
    )
    db.add(video)
    db.flush()

    # The real output length, never above the estimate.
    usd, billed_seconds = lipsync_actual_usd(
        job.estimated_usd,
        job.resolution,
        output_seconds(fal_result, video_data.get("duration_seconds")),
    )
    record_usage(
        db,
        feature="lipsync",
        usd=usd,
        model=job.model or LIPSYNC_MODEL,
        units=billed_seconds,
        unit="second",
        job_type="lipsync",
        job_id=job.job_id,
        detail={
            "video_id": video.id,
            "resolution": job.resolution,
            "enable_transcription": bool(job.enable_transcription),
            "audio_duration_seconds": job.audio_duration_seconds,
            "duration_seconds": video_data.get("duration_seconds"),
            "source": source,
        },
    )

    job.status = "completed"
    job.progress = 100
    job.estimated_usd = usd
    job.completed_at = datetime.utcnow()
    job.result = {
        "video_id": video.id,
        "filename": video_data["filename"],
        "url": video_data.get("url"),
        "thumbnail_url": video_data.get("thumbnail_url"),
    }
    db.commit()
    logger.info(f"Lip sync job {job.job_id} completed via {source}: video {video.id}")
    return video


def process_pending_lipsync_jobs(db: Session) -> None:
    """Scheduler pass: poll fal for every unfinished job and finish completed ones.

    Mirrors the Motion Control processor in scheduler_service. Runs only in the
    single scheduler process.
    """
    from app.services.alert_service import send_job_completion_notification
    from app.services.job_state import (
        CLAIMABLE_STATUSES, claim_job, fail_claimed_job, is_temporary_failure, lock_job, update_job_if,
    )

    # No row locks here: one SKIP LOCKED select used to lock every job and the
    # first commit released them all. Each job is claimed on its own before
    # it is downloaded and stored, and status writes re-read under the lock.
    jobs = (
        db.query(LipSyncJob)
        .filter(LipSyncJob.status.in_(CLAIMABLE_STATUSES))
        .all()
    )
    if not jobs:
        return
    logger.info(f"Processing {len(jobs)} pending lip sync jobs")

    def notify(job, status, result_id=None, error=None):
        try:
            send_job_completion_notification(
                db=db, user_id=job.user_id, job_type="video", status=status,
                result_id=result_id, error_message=error,
            )
        except Exception as ne:
            logger.error(f"Failed to send notification for lip sync job {job.job_id}: {ne}")

    for job in jobs:
        claimed = False
        try:
            if job.result and job.result.get("video_id"):
                if db.query(Video).filter(Video.id == job.result["video_id"]).first():
                    job.status = "completed"
                    job.progress = 100
                    job.completed_at = job.completed_at or datetime.utcnow()
                    db.commit()
                    continue

            fal_status = get_lipsync_status(job.request_id, db)

            if fal_status.get("completed"):
                if not claim_job(db, LipSyncJob, job.id):
                    logger.info(f"Lip sync job {job.job_id} was claimed elsewhere, skipping")
                    continue
                claimed = True
                db.refresh(job)

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    video = loop.run_until_complete(finish_lipsync_job(db, job, "scheduler"))
                finally:
                    loop.close()
                notify(job, "completed", result_id=video.id)

            elif fal_status.get("in_progress"):
                job = lock_job(db, LipSyncJob, job.id)
                if job is None or job.status not in CLAIMABLE_STATUSES:
                    db.rollback()
                    continue
                if job.status != "in_progress":
                    job.status = "in_progress"
                    job.started_at = datetime.utcnow()
                job.progress = max(job.progress or 0, 50)
                db.commit()

            elif fal_status.get("status") == "error":
                job = lock_job(db, LipSyncJob, job.id)
                if job is None or job.status not in CLAIMABLE_STATUSES:
                    db.rollback()
                    continue
                job.status = "failed"
                job.error = fal_status.get("error", "Unknown error")
                db.commit()
                logger.error(f"Lip sync job {job.job_id} failed: {job.error}")
                notify(job, "failed", error=job.error)

        except Exception as e:
            # A failed flush leaves the session unusable, and job.job_id below would raise.
            db.rollback()
            logger.error(f"Error processing lip sync job {job.job_id}: {e}", exc_info=True)
            # Shown to the user; the technical detail is in the log above.
            from app.clients.fal_client import job_failure_error

            error = job_failure_error(e, "We could not finish this lip sync video. Please try again.")
            if claimed:
                failed = fail_claimed_job(db, LipSyncJob, job.id, error)
            else:
                db.rollback()
                failed = not is_temporary_failure(LipSyncJob, job.id, e) and update_job_if(
                    db, LipSyncJob, job.id, CLAIMABLE_STATUSES,
                    {"status": "failed", "error": error, "completed_at": datetime.utcnow()},
                )
            if failed:
                notify(job, "failed", error=error)
