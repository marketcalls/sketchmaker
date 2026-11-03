"""Subtitle generation routes - Add subtitles to videos."""

import uuid
import math
import hmac
import hashlib
import logging
import os
import re
import tempfile
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, UploadFile, File
from fastapi.concurrency import run_in_threadpool

from app.dependencies import CurrentUser, DbSession
from app.models.content import Video, SubtitleJob
from app.schemas.subtitle import (
    SubtitleUploadResponse,
    CreateSubtitleRequest,
    SubtitleJobResponse,
    SubtitleStatusResponse,
    SubtitleVideoResponse,
    SubtitleResultResponse,
    SubtitleGalleryResponse,
)
from app.clients.fal_client import (
    SUBTITLE_MODEL,
    submit_subtitle_generation,
    get_subtitle_generation_status,
    get_subtitle_generation_result,
    download_and_save_video,
    subtitle_actual_usd,
    subtitle_usd,
)
from app.services.job_state import (
    CLAIMABLE_STATUSES,
    claim_job,
    JOB_HANDED_BACK,
    fail_claimed_job,
    lock_job,
)
from app.services.storage_service import UnsafeMediaPath, read_local_media
from app.services.usage import record_usage
from app.config import settings
from app.utils.security import scrubbed_env

logger = logging.getLogger(__name__)

router = APIRouter()

def probe_video_duration(file_path: str) -> float | None:
    """Video duration in seconds using ffprobe, or None if it cannot be read."""
    import subprocess
    import json

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                # The upload is user-controlled and ffprobe sniffs the real
                # format: an HLS playlist posing as .mp4 would otherwise make
                # it fetch arbitrary http:// URLs from inside the server.
                "-protocol_whitelist", "file",
                file_path
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=scrubbed_env(),
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            duration = float(data.get("format", {}).get("duration", 0))
            if duration > 0:
                return duration
    except Exception as e:
        logger.warning(f"ffprobe failed: {e}")

    return None


def get_video_duration(file_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    duration = probe_video_duration(file_path)
    if duration is None:
        logger.warning("ffprobe could not read the duration, falling back to default duration")
        # Fallback: return a default duration estimate
        return 30.0  # Assume 30 seconds if can't determine
    return duration


# The cost is per minute of video, and FAL is paid for the whole video as soon
# as the job is submitted. The duration therefore has to be known at submit,
# not discovered on completion. The upload endpoint already measures it on the
# local file; it is carried to /generate in the stored filename, signed:
# subtitle_src_<uuid>-d<centiseconds>-<signature>.
_SIGNED_SOURCE = re.compile(
    r"subtitle_src_([0-9a-f]{32})-d(\d{1,9})-([0-9a-f]{16})\.(?:mp4|webm|mov)$"
)
MAX_SUBTITLE_SOURCE_BYTES = 500 * 1024 * 1024
# An unsigned source (an external URL) is downloaded into memory to be
# measured, so it gets a lower cap than an upload, which is streamed to disk.
MAX_UNSIGNED_SOURCE_BYTES = 100 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024


async def spool_upload_to_disk(upload: UploadFile, max_bytes: int, suffix: str) -> tuple[str, int]:
    """Copy an upload to a temp file in 1 MB chunks; returns (path, size).

    Raises 413 as soon as the size passes `max_bytes`. The temp file is
    removed on every failure; on success the caller owns it and must delete it.
    """
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="subtitle_upload_")
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Video file too large. Maximum size is {max_bytes // (1024 * 1024)}MB",
                    )
                await run_in_threadpool(out.write, chunk)
        return path, size
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def _duration_signature(user_id: int, token: str, centis: int) -> str:
    message = f"subtitle-duration:{user_id}:{token}:{centis}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()[:16]


def signed_source_filename(user_id: int, duration_seconds: float, ext: str) -> str:
    token = uuid.uuid4().hex
    centis = int(math.ceil(duration_seconds * 100))
    return f"subtitle_src_{token}-d{centis}-{_duration_signature(user_id, token, centis)}{ext}"


def duration_from_signed_url(url: str, user_id: int) -> float | None:
    """The duration measured at upload, if ``url`` is this user's signed upload."""
    from urllib.parse import urlparse

    name = (urlparse(url or "").path or "").rsplit("/", 1)[-1]
    match = _SIGNED_SOURCE.search(name)
    if not match:
        return None
    token, centis, signature = match.group(1), int(match.group(2)), match.group(3)
    if not hmac.compare_digest(signature, _duration_signature(user_id, token, centis)):
        return None
    return centis / 100.0


async def resolve_source_duration(url: str, user_id: int) -> float | None:
    """Duration of the video FAL will be asked to subtitle, or None if unknown.

    A signed upload carries its own measurement. Another of our own files is
    measured where it is. Anything else (an external URL) is downloaded through
    the SSRF-safe fetcher and measured locally, the same way the upload is.
    """
    duration = duration_from_signed_url(url, user_id)
    if duration is not None:
        return duration

    try:
        local = read_local_media(url)
    except UnsafeMediaPath:
        logger.warning("Subtitle source path was refused", exc_info=True)
        return None
    if local is not None:
        return await run_in_threadpool(probe_video_duration, str(local))

    from app.services.url_fetch import afetch_bytes

    try:
        content = await afetch_bytes(url, max_bytes=MAX_UNSIGNED_SOURCE_BYTES, timeout=180.0)
    except Exception as e:
        logger.warning(f"Could not fetch subtitle source to measure it: {e}")
        return None

    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".video", delete=False) as tmp:
            tmp.write(content)
            path = tmp.name
        del content
        return await run_in_threadpool(probe_video_duration, path)
    finally:
        if path:
            try:
                os.unlink(path)
            except Exception:
                pass


@router.post("/upload", response_model=SubtitleUploadResponse)
async def upload_video_for_subtitles(
    current_user: CurrentUser,
    db: DbSession,
    video: UploadFile = File(...),
):
    """Upload a video for subtitle generation.

    Returns the URL and the estimated cost based on video duration.
    Maximum file size: 500MB
    Supported formats: MP4, WebM, MOV
    """
    from app.services.storage_service import storage_service

    # Validate content type before reading anything
    allowed_types = {"video/mp4", "video/webm", "video/quicktime"}
    if video.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported video format. Allowed: MP4, WebM, MOV",
        )

    # Determine file extension
    ext_map = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}
    ext = ext_map.get(video.content_type, ".mp4")

    # Up to 500 MB: streamed to a temp file in chunks (never held in a
    # worker's memory), measured there and uploaded from there.
    path, file_size = await spool_upload_to_disk(video, MAX_SUBTITLE_SOURCE_BYTES, ext)
    try:
        measured = await run_in_threadpool(probe_video_duration, path)
        duration_seconds = measured if measured is not None else 30.0  # default estimate

        estimated_usd = subtitle_usd(duration_seconds)

        # Generate unique filename. Only a real measurement is signed into it; a
        # file ffprobe could not read is measured again at /generate.
        if measured is not None:
            filename = signed_source_filename(current_user.id, measured, ext)
        else:
            filename = f"subtitle_src_{uuid.uuid4()}{ext}"

        url = await storage_service.upload_file_from_path(
            path,
            filename=filename,
            storage_type="uploads",
            content_type=video.content_type,
            user_id=current_user.id,
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    logger.info(f"Video uploaded for subtitles: {filename} ({file_size / 1024 / 1024:.2f} MB, {duration_seconds:.1f}s)")

    return SubtitleUploadResponse(
        url=url,
        filename=filename,
        duration_seconds=duration_seconds,
        estimated_usd=estimated_usd,
        file_size_bytes=file_size,
        message=f"Video uploaded successfully. Duration: {duration_seconds:.1f}s",
    )


@router.post("/generate", response_model=SubtitleJobResponse)
async def generate_subtitles_endpoint(
    body: CreateSubtitleRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Submit async subtitle generation job.

    Returns a job_id immediately. Poll /subtitle/status/{job_id} for progress,
    then fetch results from /subtitle/result/{job_id} when complete.

    Priced per minute of video (rounded up).
    """
    # The estimate is per minute of the real video, so it is measured first.
    duration_seconds = await resolve_source_duration(body.video_url, current_user.id)
    if duration_seconds is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read the length of this video. Upload it again or try a different file.",
        )
    estimated_usd = subtitle_usd(duration_seconds)

    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Submit to FAL. Blocking network calls: off the event loop.
        result = await run_in_threadpool(
            submit_subtitle_generation,
            video_url=body.video_url,
            db=db,
            font_color=body.font_color,
            stroke_color=body.stroke_color,
            highlight_color=body.highlight_color,
            background_color=body.background_color,
            position=body.position,
            font_size=body.font_size,
            font_name=body.font_name,
            font_weight=body.font_weight,
            stroke_width=body.stroke_width,
            y_offset=body.y_offset,
            words_per_subtitle=body.words_per_subtitle,
            enable_animation=body.enable_animation,
            language=body.language,
        )

        # Create job record
        job = SubtitleJob(
            job_id=job_id,
            request_id=result["request_id"],
            user_id=current_user.id,
            source_video_url=body.video_url,
            video_duration_seconds=duration_seconds,
            subtitle_color=body.font_color,
            subtitle_bg_color=body.stroke_color,
            subtitle_position=body.position,
            subtitle_font_size=body.font_size,
            font_family=body.font_name,
            status="pending",
            estimated_usd=estimated_usd,
        )
        db.add(job)
        db.commit()

        logger.info(f"Subtitle generation job submitted: {job_id}")

        return SubtitleJobResponse(
            job_id=job_id,
            status="pending",
            message="Subtitle generation job submitted. Poll /subtitle/status/{job_id} for progress.",
            estimated_usd=estimated_usd,
        )

    except ValueError as e:
        logger.warning(f"Subtitle generation request rejected: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This subtitle request could not be accepted. Check the video and subtitle style and try again.",
        )
    except Exception as e:
        logger.error(f"Subtitle generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="We could not start adding subtitles right now. Please try again in a moment.",
        )


@router.get("/status/{job_id}", response_model=SubtitleStatusResponse)
async def get_subtitle_job_status(
    job_id: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get status of a subtitle generation job."""
    job = db.query(SubtitleJob).filter(
        SubtitleJob.job_id == job_id,
        SubtitleJob.user_id == current_user.id,
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # Return cached status if truly completed
    if job.status == "completed" and job.result and job.result.get("video_id"):
        return SubtitleStatusResponse(
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
        return SubtitleStatusResponse(
            job_id=job.job_id,
            status="failed",
            progress=0,
            logs=job.logs.split("\n") if job.logs else None,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
        )

    # If processing, return current status
    if job.status == "processing":
        return SubtitleStatusResponse(
            job_id=job.job_id,
            status="processing",
            progress=job.progress or 75,
            logs=job.logs.split("\n") if job.logs else None,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
        )

    # Poll FAL for current status
    try:
        fal_status = await run_in_threadpool(get_subtitle_generation_status, job.request_id, db)

        # Re-read under the row lock: the job may have been claimed while fal
        # answered, and a stale write would make it claimable again.
        job = lock_job(db, SubtitleJob, job.id)
        if job.status not in CLAIMABLE_STATUSES:
            db.rollback()
            fal_status = {"status": job.status, "logs": fal_status.get("logs")}
        elif fal_status.get("completed"):
            if job.status == "pending":
                job.status = "in_progress"
            job.progress = 90
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
        if fal_status.get("completed"):
            response_status = "ready"
            response_progress = 95
        else:
            response_status = job.status
            response_progress = job.progress or 0

        return SubtitleStatusResponse(
            job_id=job.job_id,
            status=response_status,
            progress=response_progress,
            logs=fal_status.get("logs"),
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
        )

    except Exception as e:
        logger.error(f"Failed to get subtitle job status: {e}", exc_info=True)
        return SubtitleStatusResponse(
            job_id=job.job_id,
            status=job.status,
            progress=job.progress or 0,
            error="We could not check this job just now. It is still running, so please check again in a moment.",
            created_at=job.created_at,
            started_at=job.started_at,
        )


@router.get("/result/{job_id}", response_model=SubtitleResultResponse)
async def get_subtitle_job_result(
    job_id: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get result of a completed subtitle generation job.

    Downloads the video from FAL, saves it locally, creates a Video record
    and records what it cost.
    """
    # No row lock: it would be held across the fal calls below. The job is
    # claimed atomically (claim_job) once fal reports it finished.
    job = db.query(SubtitleJob).filter(
        SubtitleJob.job_id == job_id,
        SubtitleJob.user_id == current_user.id,
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
            return SubtitleResultResponse(
                job_id=job.job_id,
                status="completed",
                video=SubtitleVideoResponse.from_orm_with_urls(video),
                estimated_usd=job.estimated_usd or 0,
                transcript=video.transcript or "",
                completed_at=job.completed_at,
            )

    # GUARD 2: If job is being processed, don't interfere
    if job.status == "processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is currently being processed. Please try again in a few seconds.",
        )

    if job.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=job.error or "Subtitle generation failed",
        )

    # Check if job is complete with FAL
    fal_status = await run_in_threadpool(get_subtitle_generation_status, job.request_id, db)
    if not fal_status.get("completed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job not complete. Current status: {fal_status.get('status', 'unknown')}",
        )

    # Claim the job: only one caller (this endpoint or the scheduler) may
    # download and store it.
    if not claim_job(db, SubtitleJob, job.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is currently being processed. Please try again in a few seconds.",
        )
    db.refresh(job)

    try:
        # Fetch result from FAL
        fal_result = await run_in_threadpool(get_subtitle_generation_result, job.request_id, db)

        # Download and save video
        video_data = await download_and_save_video(fal_result, user_id=job.user_id)

        # Extract transcript from FAL result if available
        transcript = fal_result.get("transcript", "")
        if not transcript and fal_result.get("subtitles"):
            # Build transcript from subtitles array
            subtitles = fal_result.get("subtitles", [])
            transcript = " ".join([s.get("text", "") for s in subtitles])

        # GUARD 3: Re-check job hasn't been processed while downloading
        db.refresh(job)
        if job.result and job.result.get("video_id"):
            video = db.query(Video).filter(Video.id == job.result["video_id"]).first()
            if video:
                return SubtitleResultResponse(
                    job_id=job.job_id,
                    status="completed",
                    video=SubtitleVideoResponse.from_orm_with_urls(video),
                    estimated_usd=job.estimated_usd or 0,
                    transcript=video.transcript or "",
                    completed_at=job.completed_at,
                )

        # Recorded on the video's duration, capped at the estimate
        duration_seconds = video_data.get("duration_seconds")
        usd = subtitle_actual_usd(duration_seconds, job.estimated_usd)

        # Update job with actual video duration if known
        if duration_seconds:
            job.video_duration_seconds = duration_seconds

        # Save video to database with subtitle-specific fields
        video = Video(
            filename=video_data["filename"],
            thumbnail_filename=video_data.get("thumbnail_filename"),
            video_type="subtitle",
            transcript=transcript,
            has_subtitles=1,
            duration_seconds=duration_seconds,
            width=video_data.get("width"),
            height=video_data.get("height"),
            fps=video_data.get("fps"),
            file_size_bytes=video_data.get("file_size_bytes"),
            model=SUBTITLE_MODEL,
            user_id=current_user.id,
        )
        db.add(video)
        db.flush()

        record_usage(
            db,
            feature="subtitle",
            usd=usd,
            model=SUBTITLE_MODEL,
            job_type="subtitle",
            job_id=job.job_id,
            detail={
                "video_id": video.id,
                "duration_seconds": duration_seconds,
                "source": "result_endpoint",
            },
        )

        # Update job
        job.status = "completed"
        job.progress = 100
        job.estimated_usd = usd
        job.completed_at = datetime.utcnow()
        job.result = {"video_id": video.id, "transcript": transcript}

        db.commit()

        logger.info(f"Subtitle generation completed: {job_id}")

        return SubtitleResultResponse(
            job_id=job.job_id,
            status="completed",
            video=SubtitleVideoResponse.from_orm_with_urls(video),
            estimated_usd=usd,
            transcript=transcript,
            completed_at=job.completed_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Subtitle processing failed: {e}", exc_info=True)
        message = "We could not save the subtitled video. Please try again."
        failed = fail_claimed_job(db, SubtitleJob, job.id, message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=message if failed else JOB_HANDED_BACK,
        )


@router.get("/gallery", response_model=SubtitleGalleryResponse)
async def get_subtitle_gallery(
    current_user: CurrentUser,
    db: DbSession,
    page: int = 1,
    page_size: int = 20,
):
    """Get user's subtitled videos.

    Returns paginated list of subtitle videos (video_type='subtitle').
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20
    if page_size > 100:
        page_size = 100

    # Count total subtitle videos for user
    total = db.query(Video).filter(
        Video.user_id == current_user.id,
        Video.video_type == "subtitle",
    ).count()

    total_pages = math.ceil(total / page_size) if total > 0 else 1
    offset = (page - 1) * page_size

    # Get paginated videos
    videos = db.query(Video).filter(
        Video.user_id == current_user.id,
        Video.video_type == "subtitle",
    ).order_by(Video.created_at.desc()).offset(offset).limit(page_size).all()

    return SubtitleGalleryResponse(
        videos=[SubtitleVideoResponse.from_orm_with_urls(v) for v in videos],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.delete("/{video_id}")
async def delete_subtitle_video(
    video_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Delete a subtitled video and its stored files."""
    from app.services.storage_service import storage_service

    video = db.query(Video).filter(
        Video.id == video_id,
        Video.user_id == current_user.id,
        Video.video_type == "subtitle",
    ).first()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subtitle video not found",
        )

    filename, thumbnail = video.filename, video.thumbnail_filename

    # Database first, then storage (best effort)
    db.delete(video)
    db.commit()

    try:
        await storage_service.delete_file(filename, "videos", user_id=current_user.id)
        if thumbnail:
            await storage_service.delete_file(thumbnail, "thumbnails", user_id=current_user.id)
    except Exception as e:
        logger.warning(f"Failed to delete subtitle video files: {e}")

    return {"status": "ok", "message": "Subtitle video deleted"}


@router.get("/{video_id}/download")
async def download_subtitle_video(
    video_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get download URL for a subtitled video."""
    video = db.query(Video).filter(
        Video.id == video_id,
        Video.user_id == current_user.id,
        Video.video_type == "subtitle",
    ).first()

    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subtitle video not found",
        )

    return {
        "download_url": video.get_url(),
        "filename": video.filename,
    }
