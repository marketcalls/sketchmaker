"""Lip Sync routes: a portrait image and an audio track to a talking video.

Priced per second of output (the audio length) by resolution, with fal's 1.2x
multiplier over 15 seconds (app/services/pricing.py).
The flow mirrors Motion Control: upload, submit, poll /status, fetch /result;
the scheduler finishes jobs whose page was closed. See
app/services/lipsync_service.py for the signed uploads. The portrait and the
audio can instead come from My Assets by id (app/services/assets.py), which
also holds voices generated with ElevenLabs.
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.dependencies import CurrentUser, DbSession
from app.models.content import LipSyncJob, Video
from app.routers.video import _probe_upload_duration
from app.schemas.lipsync import (
    LipSyncAudioUploadResponse,
    LipSyncGenerateRequest,
    LipSyncImageUploadResponse,
    LipSyncJobSubmitResponse,
)
from app.schemas.video import (
    VideoGalleryResponse,
    VideoJobResultResponse,
    VideoJobStatusResponse,
    VideoResponse,
)
from app.services import assets as asset_service
from app.services import lipsync_service as ls
from app.services.pricing import (
    LIPSYNC_RESOLUTIONS,
    lipsync_seconds,
    lipsync_usd,
)
from app.services.job_state import (
    CLAIMABLE_STATUSES,
    claim_job,
    JOB_HANDED_BACK,
    fail_claimed_job,
    lock_job,
)
from app.services import quality_gate

logger = logging.getLogger(__name__)

router = APIRouter()


def _portrait_url(db, body: LipSyncGenerateRequest, user_id: int) -> str:
    """The portrait's URL, rebuilt from storage: a signed upload from this page
    or one of the user's image assets that fits fal's limits. Raises ValueError."""
    if body.image_asset_id is not None:
        try:
            asset = asset_service.owned(db, user_id, body.image_asset_id, ("image", "logo"))
        except asset_service.AssetNotFound:
            raise ValueError("That portrait is no longer in My Assets. Pick another one.")
        if asset.content_type not in ("image/png", "image/jpeg", "image/webp"):
            raise ValueError("Lip Sync needs a PNG, JPEG or WebP portrait. SVG logos cannot be animated.")
        if (asset.file_size_bytes or 0) > ls.IMAGE_MAX_BYTES:
            raise ValueError("That image is larger than 10 MB, the Lip Sync limit. Pick a smaller one.")
        if asset.width and asset.height:
            ratio = asset.width / asset.height
            if ratio < ls.ASPECT_MIN or ratio > ls.ASPECT_MAX:
                raise ValueError(
                    f"That image is {asset.width}x{asset.height} (aspect ratio {ratio:.2f}). Lip Sync needs an "
                    f"aspect ratio between {ls.ASPECT_MIN} and {ls.ASPECT_MAX}. Crop it and upload it again."
                )
        return asset_service.url_of(asset)
    image_name = ls.signed_image_from_url(body.image_url or "", user_id)
    if not image_name:
        raise ValueError("The portrait must be uploaded on this page or picked from My Assets. Add it again.")
    return ls.upload_url(image_name, user_id)


LIPSYNC_AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac", ".ogg")


def _audio_source(db, body: LipSyncGenerateRequest, user_id: int) -> tuple[str, float]:
    """(URL, measured seconds) of the audio: a signed upload from this page or
    one of the user's audio assets (uploaded or generated voices). Raises ValueError."""
    if body.audio_asset_id is not None:
        try:
            asset = asset_service.owned(db, user_id, body.audio_asset_id, ("audio",))
        except asset_service.AssetNotFound:
            raise ValueError("That audio is no longer in My Assets. Pick another one.")
        if asset_service.extension(asset) not in LIPSYNC_AUDIO_EXTENSIONS:
            raise ValueError("Lip Sync needs MP3, WAV, M4A, AAC or OGG audio.")
        if (asset.file_size_bytes or 0) > ls.AUDIO_MAX_BYTES:
            raise ValueError("That audio file is larger than 25 MB, the Lip Sync limit.")
        return asset_service.url_of(asset), float(asset.duration_seconds or 0)
    audio = ls.signed_audio_from_url(body.audio_url or "", user_id)
    if not audio:
        raise ValueError("The audio must be uploaded on this page, generated or picked from My Assets. Add it again.")
    audio_name, audio_seconds = audio
    return ls.upload_url(audio_name, user_id), audio_seconds


def _status_response(job: LipSyncJob, status_value: str, progress: int, logs=None) -> VideoJobStatusResponse:
    return VideoJobStatusResponse(
        job_id=job.job_id,
        status=status_value,
        progress=progress,
        logs=logs if logs is not None else (job.logs.split("\n") if job.logs else None),
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
    )


def _completed_response(job: LipSyncJob, video: Video) -> VideoJobResultResponse:
    return VideoJobResultResponse(
        job_id=job.job_id,
        status="completed",
        video=VideoResponse.from_orm_with_urls(video),
        estimated_usd=job.estimated_usd or 0,
        completed_at=job.completed_at,
    )


@router.post("/upload-image", response_model=LipSyncImageUploadResponse)
async def upload_lipsync_image(
    current_user: CurrentUser,
    db: DbSession,
    image: UploadFile = File(...),
):
    """Upload the portrait to animate.

    PNG, JPEG or WebP up to 10 MB, aspect ratio between 0.4 and 2.5. The bytes
    are decoded to check the real format and size; the declared type is ignored.
    """
    from app.services.storage_service import storage_service

    content = await image.read(ls.IMAGE_MAX_BYTES + 1)
    if len(content) > ls.IMAGE_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image file too large. Maximum size is 10 MB.",
        )
    try:
        info = await run_in_threadpool(ls.inspect_image, content)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    filename = ls.signed_image_filename(current_user.id, info["ext"])
    url = await storage_service.upload_file(
        file_data=content,
        filename=filename,
        storage_type="uploads",
        content_type=info["content_type"],
        user_id=current_user.id,
    )
    logger.info(f"Lip sync image uploaded: {filename} ({len(content) / 1024:.1f} KB, {info['width']}x{info['height']})")

    return LipSyncImageUploadResponse(
        url=url,
        filename=filename,
        file_size_bytes=len(content),
        width=info["width"],
        height=info["height"],
        aspect_ratio=info["aspect_ratio"],
    )


@router.post("/upload-audio", response_model=LipSyncAudioUploadResponse)
async def upload_lipsync_audio(
    current_user: CurrentUser,
    db: DbSession,
    audio: UploadFile = File(...),
):
    """Upload the audio to lip sync to.

    MP3, WAV, M4A/AAC or OGG up to 25 MB, from 5 seconds to the release cap
    (lipsync_service.AUDIO_MAX_SECONDS). The length is measured with ffprobe
    and signed into the stored filename; the job is priced on it.
    """
    from app.services.storage_service import storage_service

    content = await audio.read(ls.AUDIO_MAX_BYTES + 1)
    if len(content) > ls.AUDIO_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio file too large. Maximum size is 25 MB.",
        )
    try:
        ext, content_type = ls.sniff_audio(content)
        measured = await run_in_threadpool(_probe_upload_duration, content, ext)
        seconds = ls.check_audio_length(measured)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    filename = ls.signed_audio_filename(current_user.id, seconds, ext)
    url = await storage_service.upload_file(
        file_data=content,
        filename=filename,
        storage_type="uploads",
        content_type=content_type,
        user_id=current_user.id,
    )
    signed = ls.signed_audio_from_url(filename, current_user.id)
    signed_seconds = signed[1] if signed else seconds
    logger.info(f"Lip sync audio uploaded: {filename} ({len(content) / 1024:.1f} KB, {signed_seconds:.2f}s)")

    return LipSyncAudioUploadResponse(
        url=url,
        filename=filename,
        file_size_bytes=len(content),
        duration_seconds=signed_seconds,
        billable_seconds=lipsync_seconds(signed_seconds),
    )


@router.post("/generate", response_model=LipSyncJobSubmitResponse)
async def generate_lipsync(
    body: LipSyncGenerateRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Submit an async lip sync job.

    Returns a job_id immediately. Poll /lip-sync/status/{job_id}, then fetch
    /lip-sync/result/{job_id} once the status is "ready" or "completed".
    Estimated on the measured audio length; the recorded cost follows the real
    output length and is never higher.
    """
    resolution = (body.resolution or "").lower()
    if resolution not in LIPSYNC_RESOLUTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resolution must be 480p, 768p, 1080p or 2k",
        )

    try:
        image_url = _portrait_url(db, body, current_user.id)
        audio_url, audio_seconds = _audio_source(db, body, current_user.id)
        ls.check_audio_length(audio_seconds)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    reserved_seconds = lipsync_seconds(audio_seconds)
    try:
        arguments = ls.build_lipsync_arguments(image_url, audio_url, resolution, body.enable_transcription)
        estimated_usd = lipsync_usd(resolution, reserved_seconds)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    face_check = None
    if body.face_check:
        face_check = await _face_check(db, body, current_user.id)

    job_id = str(uuid.uuid4())
    try:
        # Blocking network calls: off the event loop.
        request_id = await run_in_threadpool(ls.submit_lipsync_job, arguments, db)

        job = LipSyncJob(
            job_id=job_id,
            request_id=request_id,
            user_id=current_user.id,
            model=ls.LIPSYNC_MODEL,
            image_url=image_url,
            audio_url=audio_url,
            audio_duration_seconds=audio_seconds,
            resolution=resolution,
            enable_transcription=1 if body.enable_transcription else 0,
            status="pending",
            estimated_usd=estimated_usd,
        )
        db.add(job)
        db.commit()
    except ValueError:
        db.rollback()
        logger.warning(f"Lip sync submit rejected for user {current_user.id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The portrait or audio could not be sent for lip sync. Add them again and try once more.",
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Lip sync submit failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit the lip sync job. Please try again.",
        )

    logger.info(f"Lip sync job submitted: {job_id} ({reserved_seconds}s {resolution}, estimated ${estimated_usd:g})")
    return LipSyncJobSubmitResponse(
        job_id=job_id,
        status="pending",
        estimated_usd=estimated_usd,
        reserved_seconds=reserved_seconds,
        message="Lip sync job submitted. Poll /lip-sync/status/{job_id} for progress.",
        face_check=quality_gate.view(face_check),
    )


async def _portrait_bytes(db, body: LipSyncGenerateRequest, user_id: int) -> bytes | None:
    """The portrait's bytes, read from storage (never from a client URL)."""
    from app.services.storage_service import storage_service

    if body.image_asset_id is not None:
        asset = asset_service.owned(db, user_id, body.image_asset_id, ("image", "logo"))
        return await storage_service.get_file_bytes(asset.filename, asset.storage_type, user_id=user_id)
    name = ls.signed_image_from_url(body.image_url or "", user_id)
    return await storage_service.get_file_bytes(name, "uploads", user_id=user_id) if name else None


async def _face_check(db, body: LipSyncGenerateRequest, user_id: int) -> dict | None:
    """The pre-check before the lip sync is submitted: one vision read of the portrait.
    A fail refuses the lip sync; an unverified check lets it go ahead. The vision call
    is logged with the other LLM calls."""
    if not quality_gate.available(db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The face check is not available right now. Turn it off to make the video without it.",
        )
    try:
        blob = await _portrait_bytes(db, body, user_id)
    except Exception:
        logger.warning(f"Lip sync face check: the portrait could not be read for user {user_id}", exc_info=True)
        blob = None
    if not blob:
        return None
    verdict = await quality_gate.check_portrait(blob, user_id=user_id)
    if verdict.get("verdict") == quality_gate.FAIL:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{quality_gate.PORTRAIT_REFUSAL} The video was not made.",
        )
    return verdict


@router.get("/status/{job_id}", response_model=VideoJobStatusResponse)
async def get_lipsync_status(job_id: str, current_user: CurrentUser, db: DbSession):
    """Status of a lip sync job: pending, in_progress, processing, ready, completed or failed."""
    job = db.query(LipSyncJob).filter(
        LipSyncJob.job_id == job_id,
        LipSyncJob.user_id == current_user.id,
    ).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if job.status == "completed" and job.result and job.result.get("video_id"):
        return _status_response(job, "completed", 100)
    if job.status == "failed":
        return _status_response(job, "failed", 0)
    if job.status == "processing":
        return _status_response(job, "processing", job.progress or 75)

    try:
        fal_status = await run_in_threadpool(ls.get_lipsync_status, job.request_id, db)
        # Re-read under the row lock: the job may have been claimed while fal
        # answered, and a stale write would make it claimable again.
        job = lock_job(db, LipSyncJob, job.id)
        if job.status not in CLAIMABLE_STATUSES:
            db.rollback()
            fal_status = {"status": job.status, "logs": fal_status.get("logs")}
        elif fal_status.get("completed"):
            # Let the result endpoint or the scheduler do the processing.
            if job.status == "pending":
                job.status = "in_progress"
            job.progress = 90
            job.started_at = job.started_at or datetime.utcnow()
        elif fal_status.get("in_progress"):
            job.status = "in_progress"
            job.progress = max(job.progress or 0, 50)
            job.started_at = job.started_at or datetime.utcnow()
        elif fal_status.get("status") == "error":
            job.status = "failed"
            job.error = fal_status.get("error")
        if fal_status.get("logs"):
            job.logs = "\n".join(fal_status["logs"])
        db.commit()

        if fal_status.get("completed"):
            return _status_response(job, "ready", 95, logs=fal_status.get("logs"))
        return _status_response(job, job.status, job.progress or 0, logs=fal_status.get("logs"))
    except Exception as e:
        logger.error(f"Failed to get lip sync job status: {e}")
        return _status_response(job, job.status, job.progress or 0)


@router.get("/result/{job_id}", response_model=VideoJobResultResponse)
async def get_lipsync_result(job_id: str, current_user: CurrentUser, db: DbSession):
    """Result of a finished lip sync job; downloads and saves it on first call."""
    # No row lock: it would be held across the fal calls below. The job is
    # claimed atomically (claim_job) once fal reports it finished.
    job = db.query(LipSyncJob).filter(
        LipSyncJob.job_id == job_id,
        LipSyncJob.user_id == current_user.id,
    ).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if job.result and job.result.get("video_id"):
        video = db.query(Video).filter(Video.id == job.result["video_id"]).first()
        if video:
            return _completed_response(job, video)

    if job.status == "processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is currently being processed. Please try again in a few seconds.",
        )
    if job.status == "failed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=job.error or "Lip sync failed")

    fal_status = await run_in_threadpool(ls.get_lipsync_status, job.request_id, db)
    if not fal_status.get("completed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job not complete. Current status: {fal_status.get('status', 'unknown')}",
        )

    if not claim_job(db, LipSyncJob, job.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is currently being processed. Please try again in a few seconds.",
        )
    db.refresh(job)

    try:
        video = await ls.finish_lipsync_job(db, job, "result_endpoint")
        db.refresh(job)
        return _completed_response(job, video)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lip sync result processing failed: {e}", exc_info=True)
        from app.clients.fal_client import CONTENT_FILTER_ERROR, is_content_policy_error

        if is_content_policy_error(e):
            # A moderation refusal: nothing to save.
            fail_claimed_job(db, LipSyncJob, job.id, CONTENT_FILTER_ERROR)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=CONTENT_FILTER_ERROR)
        message = "We could not save this lip sync video. Please try again."
        failed = fail_claimed_job(db, LipSyncJob, job.id, message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=message if failed else JOB_HANDED_BACK,
        )


@router.get("/gallery", response_model=VideoGalleryResponse)
async def get_lipsync_gallery(
    current_user: CurrentUser,
    db: DbSession,
    page: int = 1,
    page_size: int = 12,
):
    """The user's lip sync videos, newest first. Delete and download use the
    shared /api/video/{id} endpoints."""
    page = max(1, page)
    page_size = min(max(1, page_size), 50)
    query = db.query(Video).filter(Video.user_id == current_user.id, Video.video_type == "lipsync")
    total = query.count()
    videos = query.order_by(Video.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return VideoGalleryResponse(
        videos=[VideoResponse.from_orm_with_urls(v) for v in videos],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
    )


@router.post("/job/{job_id}/retry")
async def retry_lipsync_job(job_id: str, current_user: CurrentUser, db: DbSession):
    """Reset a stuck or failed job so the scheduler polls fal for it again.

    Does not resubmit: the job keeps its fal request and estimate.
    """
    job = db.query(LipSyncJob).filter(
        LipSyncJob.job_id == job_id,
        LipSyncJob.user_id == current_user.id,
    ).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    job = lock_job(db, LipSyncJob, job.id)

    if job.result and job.result.get("video_id"):
        if db.query(Video).filter(Video.id == job.result["video_id"]).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The video for this job already exists.")

    is_stuck = job.status in ("completed", "in_progress") and not (job.result and job.result.get("video_id"))
    if not is_stuck and job.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only stuck or failed jobs can be retried.",
        )
    job.status = "in_progress"
    job.progress = 50
    job.error = None
    job.completed_at = None
    job.result = None
    db.commit()
    return {
        "message": "Job reset for reprocessing. The scheduler will pick it up within 30 seconds.",
        "job_id": job_id,
        "status": "in_progress",
    }
