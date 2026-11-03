"""My Jobs: every generation job (images and videos) in one list, with cancel."""

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.dependencies import CurrentUser, DbSession
from app.models.content import GenerationJob, VideoGenerationJob, StoryGenerationJob, SubtitleJob, LipSyncJob, Image, Video
from app.services.job_state import CLAIMABLE_STATUSES, JOB_MODELS, update_job_if

logger = logging.getLogger(__name__)

router = APIRouter()


class UnifiedJobResponse(BaseModel):
    """Unified job response for both image and video jobs."""
    job_id: str
    job_type: str  # "image" or "video"
    status: str
    progress: int
    prompt: Optional[str] = None
    error: Optional[str] = None
    thumbnail_url: Optional[str] = None
    result_id: Optional[int] = None  # image_id or video_id
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class JobsListResponse(BaseModel):
    """Response for jobs list."""
    jobs: List[UnifiedJobResponse]
    total: int
    pending_count: int
    in_progress_count: int


class CancelJobResponse(BaseModel):
    success: bool
    message: str
    job_id: str
    new_status: str


@router.get("", response_model=JobsListResponse)
def get_all_jobs(
    current_user: CurrentUser,
    db: DbSession,
    status: Optional[str] = Query(None, description="Filter by status: pending, in_progress, completed, failed"),
    job_type: Optional[str] = Query(None, description="Filter by type: image, video, story, subtitle, lipsync"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    days: int = Query(7, ge=1, le=30, description="Show jobs from last N days"),
):
    """Get all generation jobs for the current user.

    Returns a unified list of image and video generation jobs with status,
    progress, and result information.
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    jobs = []

    # Query image generation jobs
    if job_type is None or job_type == "image":
        image_query = db.query(GenerationJob).filter(
            GenerationJob.user_id == current_user.id,
            GenerationJob.created_at >= cutoff_date,
        )
        if status:
            # Handle "pending" filter to include both pending and in_progress
            if status == "pending":
                image_query = image_query.filter(
                    GenerationJob.status.in_(["pending", "in_progress"])
                )
            else:
                image_query = image_query.filter(GenerationJob.status == status)

        for job in image_query.all():
            thumbnail_url = None
            result_id = None
            if job.result and job.result.get("image_ids"):
                result_id = job.result["image_ids"][0]
                image = db.query(Image).filter(Image.id == result_id).first()
                if image:
                    thumbnail_url = image.get_url()

            jobs.append(UnifiedJobResponse(
                job_id=job.job_id,
                job_type="image",
                status=job.status,
                progress=job.progress or 0,
                prompt=job.prompt[:100] + "..." if job.prompt and len(job.prompt) > 100 else job.prompt,
                error=job.error,
                thumbnail_url=thumbnail_url,
                result_id=result_id,
                created_at=job.created_at,
                started_at=job.started_at,
                completed_at=job.completed_at,
            ))

    # Query video generation jobs
    if job_type is None or job_type == "video":
        video_query = db.query(VideoGenerationJob).filter(
            VideoGenerationJob.user_id == current_user.id,
            VideoGenerationJob.created_at >= cutoff_date,
        )
        if status:
            if status == "pending":
                video_query = video_query.filter(
                    VideoGenerationJob.status.in_(["pending", "in_progress"])
                )
            else:
                video_query = video_query.filter(VideoGenerationJob.status == status)

        for job in video_query.all():
            thumbnail_url = None
            result_id = None
            if job.result and job.result.get("video_id"):
                result_id = job.result["video_id"]
                video = db.query(Video).filter(Video.id == result_id).first()
                if video:
                    thumbnail_url = video.get_thumbnail_url()

            jobs.append(UnifiedJobResponse(
                job_id=job.job_id,
                job_type="video",
                status=job.status,
                progress=job.progress or 0,
                prompt=job.prompt[:100] + "..." if job.prompt and len(job.prompt) > 100 else job.prompt,
                error=job.error,
                thumbnail_url=thumbnail_url,
                result_id=result_id,
                created_at=job.created_at,
                started_at=job.started_at,
                completed_at=job.completed_at,
            ))

    # Query story generation jobs
    if job_type is None or job_type == "story":
        story_query = db.query(StoryGenerationJob).filter(
            StoryGenerationJob.user_id == current_user.id,
            StoryGenerationJob.created_at >= cutoff_date,
        )
        if status:
            if status == "pending":
                story_query = story_query.filter(
                    StoryGenerationJob.status.in_(["pending", "in_progress", "processing"])
                )
            else:
                story_query = story_query.filter(StoryGenerationJob.status == status)

        for job in story_query.all():
            thumbnail_url = None
            result_id = None
            if job.result and job.result.get("video_id"):
                result_id = job.result["video_id"]
                video = db.query(Video).filter(Video.id == result_id).first()
                if video:
                    thumbnail_url = video.get_thumbnail_url()

            jobs.append(UnifiedJobResponse(
                job_id=job.job_id,
                job_type="story",
                status=job.status if job.status != "processing" else "in_progress",
                progress=job.progress or 0,
                prompt=job.prompt[:100] + "..." if job.prompt and len(job.prompt) > 100 else job.prompt,
                error=job.error,
                thumbnail_url=thumbnail_url,
                result_id=result_id,
                created_at=job.created_at,
                started_at=job.started_at,
                completed_at=job.completed_at,
            ))

    # Query subtitle generation jobs
    if job_type is None or job_type == "subtitle":
        subtitle_query = db.query(SubtitleJob).filter(
            SubtitleJob.user_id == current_user.id,
            SubtitleJob.created_at >= cutoff_date,
        )
        if status:
            if status == "pending":
                subtitle_query = subtitle_query.filter(
                    SubtitleJob.status.in_(["pending", "in_progress", "processing"])
                )
            else:
                subtitle_query = subtitle_query.filter(SubtitleJob.status == status)

        for job in subtitle_query.all():
            thumbnail_url = None
            result_id = None
            if job.result and job.result.get("video_id"):
                result_id = job.result["video_id"]
                video = db.query(Video).filter(Video.id == result_id).first()
                if video:
                    thumbnail_url = video.get_thumbnail_url()

            jobs.append(UnifiedJobResponse(
                job_id=job.job_id,
                job_type="subtitle",
                status=job.status if job.status != "processing" else "in_progress",
                progress=job.progress or 0,
                prompt=None,  # Subtitles don't have prompts
                error=job.error,
                thumbnail_url=thumbnail_url,
                result_id=result_id,
                created_at=job.created_at,
                started_at=job.started_at,
                completed_at=job.completed_at,
            ))

    # Query lip sync jobs
    if job_type is None or job_type == "lipsync":
        lipsync_query = db.query(LipSyncJob).filter(
            LipSyncJob.user_id == current_user.id,
            LipSyncJob.created_at >= cutoff_date,
        )
        if status:
            if status == "pending":
                lipsync_query = lipsync_query.filter(
                    LipSyncJob.status.in_(["pending", "in_progress", "processing"])
                )
            else:
                lipsync_query = lipsync_query.filter(LipSyncJob.status == status)

        for job in lipsync_query.all():
            thumbnail_url = None
            result_id = None
            if job.result and job.result.get("video_id"):
                result_id = job.result["video_id"]
                video = db.query(Video).filter(Video.id == result_id).first()
                if video:
                    thumbnail_url = video.get_thumbnail_url()

            seconds = job.audio_duration_seconds
            jobs.append(UnifiedJobResponse(
                job_id=job.job_id,
                job_type="lipsync",
                status=job.status if job.status != "processing" else "in_progress",
                progress=job.progress or 0,
                prompt=f"{seconds:.1f}s audio, {job.resolution}" if seconds else job.resolution,
                error=job.error,
                thumbnail_url=thumbnail_url,
                result_id=result_id,
                created_at=job.created_at,
                started_at=job.started_at,
                completed_at=job.completed_at,
            ))

    # Sort by created_at descending (most recent first)
    jobs.sort(key=lambda x: x.created_at, reverse=True)

    # Calculate counts before pagination
    pending_count = sum(1 for j in jobs if j.status == "pending")
    in_progress_count = sum(1 for j in jobs if j.status == "in_progress")
    total = len(jobs)

    # Apply pagination
    paginated_jobs = jobs[offset:offset + limit]

    return JobsListResponse(
        jobs=paginated_jobs,
        total=total,
        pending_count=pending_count,
        in_progress_count=in_progress_count,
    )


@router.post("/{job_id}/cancel", response_model=CancelJobResponse)
def cancel_job(job_id: str, current_user: CurrentUser, db: DbSession):
    """Stop tracking a pending or in-progress job and mark it failed.

    A job already claimed ("processing") is downloading its result, so it is left to
    finish. update_job_if checks the status in the UPDATE itself, so a cancel cannot
    overwrite a claim the scheduler made a moment earlier.
    """
    for model in JOB_MODELS:
        job = db.query(model).filter(model.job_id == job_id, model.user_id == current_user.id).first()
        if job is None:
            continue
        cancelled = update_job_if(
            db, model, job.id, CLAIMABLE_STATUSES,
            {"status": "failed", "error": "Cancelled.", "completed_at": datetime.utcnow()},
        )
        if not cancelled:
            raise HTTPException(status_code=409, detail="This job has already finished or is finishing.")
        logger.info(f"Cancelled job {job_id}")
        return CancelJobResponse(success=True, message="Job cancelled", job_id=job_id, new_status="failed")
    raise HTTPException(status_code=404, detail="Job not found")
