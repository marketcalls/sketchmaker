"""The in-process scheduler: fal job polls, the stuck-job sweep, quality checks, the
Motion Graphics and Faceless Studio ticks and the nightly backup.

Runs in one process (uvicorn --workers 1), started from the app's lifespan. fal is
polled rather than called back: each poll finishes jobs whose page was closed. No
network call runs under a held write: a tick reads, commits, calls fal, then locks,
re-checks, applies and commits.
"""

import logging
import asyncio
import sys
import time
from datetime import datetime
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.database import SessionLocal
from app.services.job_state import (
    CLAIMABLE_STATUSES,
    NO_IMAGES_ERROR,
    claim_job,
    fail_claimed_job,
    is_temporary_failure,
    lock_job,
    update_job_if,
)
from app.services.usage import record_usage

logger = logging.getLogger(__name__)

# One thread for each tick that can run at once; a slow tick must not delay the rest.
TICK_THREADS = 15
JOB_POLL_SECONDS = 30
QUALITY_TICK_SECONDS = 10
STUCK_SWEEP_MINUTES = 10
# UTC. A backup that misses this (the machine was asleep) still runs within the
# misfire grace time.
BACKUP_HOUR = 3


def _fail_job(db, model, job_id: int, claimed: bool, error: str) -> bool:
    """Fail a job whose processing raised. True if this call failed it.

    A job this processor claimed goes from "processing" to failed, never
    staying stuck there. An unclaimed job is failed only while it is still
    claimable, so a job another worker claimed meanwhile is left alone.
    Called from an except block: when fal's answer was a content filter
    refusal, the job stores that sentence instead of ``error``.
    """
    from app.clients.fal_client import job_failure_error

    exc = sys.exc_info()[1]
    error = job_failure_error(exc, error)
    if claimed:
        return fail_claimed_job(db, model, job_id, error)
    db.rollback()
    if is_temporary_failure(model, job_id, exc):
        return False
    return update_job_if(
        db, model, job_id, CLAIMABLE_STATUSES,
        {"status": "failed", "error": error, "completed_at": datetime.utcnow()},
    )


def _images_usd(job, stored: int) -> float:
    """An image job's estimate for the images actually stored, never more. A model that
    returns fewer images than asked for is recorded only for what arrived."""
    requested = max(int(job.num_images or 1), 1)
    delivered = max(min(int(stored or 0), requested), 0)
    return round(float(job.estimated_usd or 0) * delivered / requested, 4)


class JobScheduler:
    """The app's background ticks."""

    def __init__(self):
        self.scheduler = BackgroundScheduler(
            timezone="UTC",
            executors={"default": ThreadPoolExecutor(TICK_THREADS)},
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 3600,
            },
        )

    def start(self):
        """Start the scheduler and add every tick."""
        if not self.scheduler.running:
            self.scheduler.start()
            self.schedule_job_processor()
            self.schedule_backup_job()
            logger.info("Scheduler started")

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    def schedule_backup_job(self):
        """Nightly database backup (app/services/backup_service.py)."""
        from app.services.backup_service import run_scheduled_backup

        self.scheduler.add_job(
            func=run_scheduled_backup,
            trigger=CronTrigger(hour=BACKUP_HOUR, minute=0),
            id="nightly_backup",
            replace_existing=True,
        )
        logger.info(f"Scheduled nightly backup ({BACKUP_HOUR:02d}:00 UTC)")

    def schedule_job_processor(self):
        """Add the job polls, the stuck-job sweep, the quality checks and the Motion
        Graphics and Faceless Studio ticks."""
        from app.services.faceless import scheduler as fl_scheduler
        from app.services.motion_graphics import scheduler as mg_scheduler
        from app.services.quality_gate import run_image_tick

        fl_scheduler.release_orphaned_claims()
        for job_id, func, seconds in (
            ("generation_job_processor", self._process_pending_jobs, JOB_POLL_SECONDS),
            ("video_job_processor", self._process_pending_video_jobs, JOB_POLL_SECONDS),
            ("story_job_processor", self._process_pending_story_jobs, JOB_POLL_SECONDS),
            ("subtitle_job_processor", self._process_pending_subtitle_jobs, JOB_POLL_SECONDS),
            ("lipsync_job_processor", self._process_pending_lipsync_jobs, JOB_POLL_SECONDS),
            # Fail fal jobs that never came back (status checks that fail
            # transiently do not fail a job, so something must end them).
            ("stuck_fal_job_sweeper", self._expire_stuck_fal_jobs, STUCK_SWEEP_MINUTES * 60),
            # Opted-in quality checks of stored images (/generate, the explainer):
            # one vision call each, stored, never a regeneration.
            ("quality_check_processor", run_image_tick, QUALITY_TICK_SECONDS),
            # Motion Graphics Studio: advance paid jobs (fal voice, music and
            # images) and render one aspect at a time under the shared render
            # slot (app/services/render_queue.py).
            ("motion_graphics_job_processor", mg_scheduler.run_tick, mg_scheduler.TICK_SECONDS),
            ("motion_graphics_render_processor", mg_scheduler.run_render_tick, mg_scheduler.RENDER_TICK_SECONDS),
            # Faceless Studio: step runs (fal submit, poll, store), long-form script
            # drafts, and one render at a time under the same slot.
            ("faceless_step_processor", fl_scheduler.run_tick, fl_scheduler.TICK_SECONDS),
            ("faceless_script_processor", fl_scheduler.run_script_tick, fl_scheduler.SCRIPT_TICK_SECONDS),
            ("faceless_render_processor", fl_scheduler.run_render_tick, fl_scheduler.RENDER_TICK_SECONDS),
        ):
            self.scheduler.add_job(
                func=func,
                trigger=IntervalTrigger(seconds=seconds),
                id=job_id,
                replace_existing=True,
            )
            logger.info(f"Scheduled {job_id} (every {seconds} s)")

    def _expire_stuck_fal_jobs(self):
        """Fail fal jobs older than the in-flight window."""
        from app.services.job_state import expire_stuck_fal_jobs

        db = SessionLocal()
        try:
            expired = expire_stuck_fal_jobs(db)
            if expired:
                logger.warning(f"Expired {expired} stuck fal job(s)")
        except Exception as e:
            db.rollback()
            logger.error(f"Stuck fal job sweep failed: {e}")
        finally:
            db.close()

    def _process_pending_lipsync_jobs(self):
        """Poll fal for unfinished lip sync jobs and finish completed ones
        (same flow as the Motion Control processor; see lipsync_service)."""
        from app.services.lipsync_service import process_pending_lipsync_jobs

        db = SessionLocal()
        try:
            process_pending_lipsync_jobs(db)
        except Exception as e:
            logger.error(f"Error in lip sync job processor: {e}")
        finally:
            db.close()

    def _process_pending_jobs(self):
        """Check for pending/in_progress generation jobs and process completed ones."""
        from app.models.content import GenerationJob, Image
        from app.clients.fal_client import (
            SAFETY_BLOCKED_ALL, download_and_save_images, drop_safety_flagged, get_generation_result,
            get_generation_status,
        )
        from app.services.alert_service import send_job_completion_notification
        from app.services.quality_gate import pending_from_job

        db = SessionLocal()
        try:
            # Find all pending/in_progress jobs (exclude 'processing' to prevent race conditions)
            # No row locks here: one SKIP LOCKED select used to lock every job
            # and the first commit released them all. Each job is claimed on
            # its own (claim_job) before it is downloaded and stored, and
            # status writes re-read the row under its lock (lock_job).
            jobs = db.query(GenerationJob).filter(
                GenerationJob.status.in_(["pending", "in_progress"])
            ).all()

            if not jobs:
                return

            logger.info(f"Processing {len(jobs)} pending generation jobs")

            for job in jobs:
                claimed = False
                try:
                    # IDEMPOTENCY CHECK: Skip if job already has valid image results
                    if job.result and job.result.get("image_ids"):
                        # Verify at least one image exists
                        first_image = db.query(Image).filter(
                            Image.id == job.result["image_ids"][0]
                        ).first()
                        if first_image:
                            logger.info(f"Job {job.job_id} already has images {job.result['image_ids']}, marking as completed")
                            job.status = "completed"
                            job.progress = 100
                            if not job.completed_at:
                                job.completed_at = datetime.utcnow()
                            db.commit()
                            continue

                    # Check status with FAL
                    fal_status = get_generation_status(job.model, job.request_id, db)

                    if fal_status.get("completed"):
                        logger.info(f"Job {job.job_id} completed, processing result")

                        # Claim the job: only one caller (this processor or a result
                        # endpoint) may download and store it.
                        if not claim_job(db, GenerationJob, job.id):
                            logger.info(f"Image job {job.job_id} was claimed elsewhere, skipping")
                            continue
                        claimed = True
                        db.refresh(job)

                        # Fetch result from FAL
                        fal_result = get_generation_result(job.model, job.request_id, db)
                        # Images the provider's safety filter blanked are not stored.
                        fal_result, blocked = drop_safety_flagged(fal_result)

                        # Download and save images (run async in sync context, organized by user folder)
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            downloaded_images = loop.run_until_complete(
                                download_and_save_images(fal_result, job.seed, user_id=job.user_id)
                            )
                        finally:
                            loop.close()

                        # Save images to database
                        image_ids = []

                        for img_data in downloaded_images:
                            # GUARD: Check if image with same filename already exists
                            existing_image = db.query(Image).filter(
                                Image.filename == img_data["filename"]
                            ).first()
                            if existing_image:
                                logger.warning(f"Scheduler: Image {img_data['filename']} already exists, using existing")
                                image_ids.append(existing_image.id)
                                continue

                            if job.original_prompt:
                                stored_prompt = job.original_prompt
                                magic_prompt = job.prompt
                            else:
                                stored_prompt = job.prompt
                                magic_prompt = None

                            image = Image(
                                filename=img_data["filename"],
                                prompt=stored_prompt,
                                magic_prompt=magic_prompt,
                                art_style=job.art_style,
                                width=img_data.get("width"),
                                height=img_data.get("height"),
                                model=job.model,
                                seed=img_data.get("seed"),
                                rendering="Default",
                                aspect_ratio=job.aspect_ratio,
                                guidance_scale=job.guidance_scale,
                                inference_steps=job.inference_steps,
                                user_id=job.user_id,
                                quality=pending_from_job(job),
                            )
                            db.add(image)
                            db.flush()
                            image_ids.append(image.id)

                        if not image_ids:
                            # Nothing arrived, so nothing is recorded.
                            job.status = "failed"
                            job.progress = 0
                            job.completed_at = datetime.utcnow()
                            job.error = SAFETY_BLOCKED_ALL if blocked else NO_IMAGES_ERROR
                            db.commit()
                            logger.warning(f"Job {job.job_id} returned no images ({blocked} blocked by the safety filter)")
                            try:
                                send_job_completion_notification(
                                    db=db,
                                    user_id=job.user_id,
                                    job_type="image",
                                    status="failed",
                                    error_message=job.error,
                                )
                            except Exception as ne:
                                logger.error(f"Failed to send failure notification for job {job.job_id}: {ne}")
                            continue

                        # Recorded for the images actually stored
                        usd = _images_usd(job, len(image_ids))
                        record_usage(
                            db,
                            feature="images",
                            usd=usd,
                            model=job.model,
                            units=len(image_ids),
                            unit="image",
                            job_type="image",
                            job_id=job.job_id,
                            detail={
                                "num_images": job.num_images,
                                "safety_blocked": blocked,
                                "source": "scheduler",
                            },
                        )

                        # Update job as completed
                        job.status = "completed"
                        job.progress = 100
                        job.estimated_usd = usd
                        job.completed_at = datetime.utcnow()
                        # The result endpoint shows the safety notice from this.
                        job.result = {"image_ids": image_ids, **({"safety_blocked": blocked} if blocked else {})}

                        db.commit()
                        logger.info(f"Job {job.job_id} processed, {len(image_ids)} images saved")

                        # Send completion notification
                        try:
                            send_job_completion_notification(
                                db=db,
                                user_id=job.user_id,
                                job_type="image",
                                status="completed",
                                result_id=image_ids[0] if image_ids else None,
                            )
                        except Exception as e:
                            logger.error(f"Failed to send notification for job {job.job_id}: {e}")

                    elif fal_status.get("in_progress"):
                        job = lock_job(db, GenerationJob, job.id)
                        if job is None or job.status not in CLAIMABLE_STATUSES:
                            db.rollback()
                            continue
                        # Update job status. Always commit: lock_job took the write
                        # lock, and the next job's fal call must not run under it.
                        if job.status != "in_progress":
                            job.status = "in_progress"
                            job.started_at = datetime.utcnow()
                        db.commit()

                    elif fal_status.get("status") == "error":
                        job = lock_job(db, GenerationJob, job.id)
                        if job is None or job.status not in CLAIMABLE_STATUSES:
                            db.rollback()
                            continue
                        job.status = "failed"
                        job.error = fal_status.get("error", "Unknown error")
                        db.commit()
                        logger.error(f"Job {job.job_id} failed: {job.error}")

                        # Send failure notification
                        try:
                            send_job_completion_notification(
                                db=db,
                                user_id=job.user_id,
                                job_type="image",
                                status="failed",
                                error_message=job.error,
                            )
                        except Exception as ne:
                            logger.error(f"Failed to send failure notification for job {job.job_id}: {ne}")

                except Exception as e:
                    # A failed flush leaves the session unusable, and job.job_id below would raise.
                    db.rollback()
                    logger.error(f"Error processing job {job.job_id}: {e}", exc_info=True)
                    # Shown to the user; the technical detail is in the log above.
                    if not _fail_job(db, GenerationJob, job.id, claimed, "We could not finish this image. Please try generating it again."):
                        continue

                    # Send failure notification
                    try:
                        send_job_completion_notification(
                            db=db,
                            user_id=job.user_id,
                            job_type="image",
                            status="failed",
                            error_message=job.error,
                        )
                    except Exception as ne:
                        logger.error(f"Failed to send failure notification for job {job.job_id}: {ne}")

        except Exception as e:
            logger.error(f"Error in job processor: {e}")
        finally:
            db.close()

    def _process_pending_video_jobs(self):
        """Check for pending/in_progress video generation jobs and process completed ones."""
        from app.models.content import VideoGenerationJob, Video
        from app.clients.fal_client import (
            get_video_generation_status,
            get_video_generation_result,
            download_and_save_video,
            motion_control_endpoint,
            motion_job_tier,
            story_output_seconds,
        )
        from app.services.pricing import motion_control_actual_usd
        from app.services.alert_service import send_job_completion_notification

        db = SessionLocal()
        try:
            # Find all pending/in_progress video jobs (exclude 'processing' to prevent race conditions)
            # No row locks here: one SKIP LOCKED select used to lock every job
            # and the first commit released them all. Each job is claimed on
            # its own (claim_job) before it is downloaded and stored, and
            # status writes re-read the row under its lock (lock_job).
            jobs = db.query(VideoGenerationJob).filter(
                VideoGenerationJob.status.in_(["pending", "in_progress"])
            ).all()

            if not jobs:
                return

            logger.info(f"Processing {len(jobs)} pending video generation jobs")

            for job in jobs:
                claimed = False
                try:
                    # IDEMPOTENCY CHECK: Skip if job already has a valid video result
                    if job.result and job.result.get("video_id"):
                        existing_video = db.query(Video).filter(
                            Video.id == job.result["video_id"]
                        ).first()
                        if existing_video:
                            logger.info(f"Video job {job.job_id} already has video {job.result['video_id']}, marking as completed")
                            job.status = "completed"
                            job.progress = 100
                            if not job.completed_at:
                                job.completed_at = datetime.utcnow()
                            db.commit()
                            continue

                    # Check status with FAL, on the endpoint the job was
                    # submitted to (NULL model: v2.6, rows from before tiers)
                    fal_status = get_video_generation_status(job.request_id, db, job.model)

                    if fal_status.get("completed"):
                        logger.info(f"Video job {job.job_id} completed, processing result")

                        # Claim the job: only one caller (this processor or a result
                        # endpoint) may download and store it.
                        if not claim_job(db, VideoGenerationJob, job.id):
                            logger.info(f"Video job {job.job_id} was claimed elsewhere, skipping")
                            continue
                        claimed = True
                        db.refresh(job)

                        # Fetch result from FAL
                        fal_result = get_video_generation_result(job.request_id, db, job.model)

                        # Download and save video (run async in sync context, organized by user folder)
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            video_data = loop.run_until_complete(
                                download_and_save_video(fal_result, user_id=job.user_id)
                            )
                        finally:
                            loop.close()

                        # GUARD: Double-check no video was created while we were downloading
                        existing_video_check = db.query(Video).filter(
                            Video.filename == video_data["filename"]
                        ).first()
                        if existing_video_check:
                            logger.warning(f"Video {video_data['filename']} already exists, skipping duplicate")
                            job.status = "completed"
                            job.progress = 100
                            job.result = {"video_id": existing_video_check.id}
                            job.completed_at = datetime.utcnow()
                            db.commit()
                            continue

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
                            user_id=job.user_id,
                        )
                        db.add(video)
                        db.flush()

                        # Recorded on the real output length, never above the
                        # estimate (app/services/pricing.py).
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
                                "video_id": video.id,
                                "duration_seconds": video_data.get("duration_seconds"),
                                "source": "scheduler",
                            },
                        )

                        # Update job as completed
                        job.status = "completed"
                        job.progress = 100
                        job.estimated_usd = usd
                        job.completed_at = datetime.utcnow()
                        job.result = {
                            "video_id": video.id,
                            "filename": video_data["filename"],
                            "url": video_data["url"],
                            "thumbnail_url": video_data.get("thumbnail_url"),
                        }

                        db.commit()
                        logger.info(f"Video job {job.job_id} processed, video {video.id} saved")

                        # Send completion notification
                        try:
                            send_job_completion_notification(
                                db=db,
                                user_id=job.user_id,
                                job_type="video",
                                status="completed",
                                result_id=video.id,
                            )
                        except Exception as e:
                            logger.error(f"Failed to send notification for video job {job.job_id}: {e}")

                    elif fal_status.get("in_progress"):
                        job = lock_job(db, VideoGenerationJob, job.id)
                        if job is None or job.status not in CLAIMABLE_STATUSES:
                            db.rollback()
                            continue
                        # Update job status
                        if job.status != "in_progress":
                            job.status = "in_progress"
                            job.started_at = datetime.utcnow()
                        # Update progress if available
                        if fal_status.get("progress"):
                            job.progress = fal_status.get("progress")
                        db.commit()

                    elif fal_status.get("status") == "error":
                        job = lock_job(db, VideoGenerationJob, job.id)
                        if job is None or job.status not in CLAIMABLE_STATUSES:
                            db.rollback()
                            continue
                        job.status = "failed"
                        job.error = fal_status.get("error", "Unknown error")
                        db.commit()
                        logger.error(f"Video job {job.job_id} failed: {job.error}")

                        # Send failure notification
                        try:
                            send_job_completion_notification(
                                db=db,
                                user_id=job.user_id,
                                job_type="video",
                                status="failed",
                                error_message=job.error,
                            )
                        except Exception as ne:
                            logger.error(f"Failed to send failure notification for video job {job.job_id}: {ne}")

                except Exception as e:
                    # A failed flush leaves the session unusable, and job.job_id below would raise.
                    db.rollback()
                    logger.error(f"Error processing video job {job.job_id}: {e}", exc_info=True)
                    # Shown to the user; the technical detail is in the log above.
                    if not _fail_job(db, VideoGenerationJob, job.id, claimed, "We could not finish this video. Please try generating it again."):
                        continue

                    # Send failure notification
                    try:
                        send_job_completion_notification(
                            db=db,
                            user_id=job.user_id,
                            job_type="video",
                            status="failed",
                            error_message=job.error,
                        )
                    except Exception as ne:
                        logger.error(f"Failed to send failure notification for video job {job.job_id}: {ne}")

        except Exception as e:
            logger.error(f"Error in video job processor: {e}")
        finally:
            db.close()


    def _process_pending_story_jobs(self):
        """Check for pending/in_progress story generation jobs and process completed ones."""
        from app.models.content import StoryGenerationJob, Video
        from app.clients.fal_client import get_story_generation_status, get_story_generation_result, download_and_save_video, story_model_for_job
        from app.clients.fal_client import SUBTITLE_MODEL, story_family_for_endpoint, story_actual_usd, subtitle_usd
        from app.clients.fal_client import submit_subtitle_generation, get_subtitle_generation_status, get_subtitle_generation_result
        from app.services.storage_service import storage_service
        from app.services.alert_service import send_job_completion_notification

        db = SessionLocal()
        try:
            # Find all pending/in_progress story jobs (exclude 'processing' to prevent race conditions)
            # No row locks here: one SKIP LOCKED select used to lock every job
            # and the first commit released them all. Each job is claimed on
            # its own (claim_job) before it is downloaded and stored, and
            # status writes re-read the row under its lock (lock_job).
            jobs = db.query(StoryGenerationJob).filter(
                StoryGenerationJob.status.in_(["pending", "in_progress"])
            ).all()

            if not jobs:
                return

            logger.info(f"Processing {len(jobs)} pending story generation jobs")

            for job in jobs:
                claimed = False
                try:
                    # IDEMPOTENCY CHECK: Skip if job already has a valid video result
                    if job.result and job.result.get("video_id"):
                        existing_video = db.query(Video).filter(
                            Video.id == job.result["video_id"]
                        ).first()
                        if existing_video:
                            logger.info(f"Story job {job.job_id} already has video {job.result['video_id']}, marking as completed")
                            job.status = "completed"
                            job.progress = 100
                            if not job.completed_at:
                                job.completed_at = datetime.utcnow()
                            db.commit()
                            continue

                    # Check status with FAL
                    fal_status = get_story_generation_status(job.request_id, db, model=story_model_for_job(job))

                    if fal_status.get("completed"):
                        logger.info(f"Story job {job.job_id} completed, processing result")

                        # Claim the job: only one caller (this processor or a result
                        # endpoint) may download and store it.
                        if not claim_job(db, StoryGenerationJob, job.id):
                            logger.info(f"Story job {job.job_id} was claimed elsewhere, skipping")
                            continue
                        claimed = True
                        db.refresh(job)

                        # Fetch result from FAL
                        fal_result = get_story_generation_result(job.request_id, db, model=story_model_for_job(job))

                        # Download and save video (run async in sync context)
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            video_data = loop.run_until_complete(
                                download_and_save_video(fal_result, user_id=job.user_id)
                            )
                        finally:
                            loop.close()

                        # Price on the generated clip, before subtitles replace it:
                        # fixed lengths keep the estimate, "auto" follows the real
                        # length.
                        usd, billed_seconds = story_actual_usd(
                            job, fal_result, video_data.get("duration_seconds")
                        )

                        # STAGE 2: Add subtitles if enabled
                        subtitles_added_successfully = False
                        if job.add_subtitles:
                            logger.info(f"Story job {job.job_id}: Adding subtitles (stage 2)")
                            job.progress = 80
                            db.commit()

                            try:
                                # fal's own copy of the clip: it needs no upload.
                                video_url = fal_result["video"]["url"]

                                # Build subtitle options from job settings
                                bg_color = getattr(job, 'subtitle_background_color', 'none') or 'none'
                                background_color = None if bg_color in ('none', 'transparent') else bg_color

                                # Submit subtitle generation job
                                subtitle_result = submit_subtitle_generation(
                                    video_url=video_url,
                                    db=db,
                                    font_color=getattr(job, 'subtitle_font_color', 'white') or 'white',
                                    stroke_color=getattr(job, 'subtitle_stroke_color', 'black') or 'black',
                                    highlight_color=getattr(job, 'subtitle_highlight_color', 'purple') or 'purple',
                                    background_color=background_color,
                                    position=getattr(job, 'subtitle_position', 'bottom') or 'bottom',
                                    font_size=getattr(job, 'subtitle_font_size', 100) or 100,
                                    font_name=getattr(job, 'subtitle_font_name', 'Montserrat') or 'Montserrat',
                                    font_weight=getattr(job, 'subtitle_font_weight', 'bold') or 'bold',
                                    stroke_width=getattr(job, 'subtitle_stroke_width', 3) or 3,
                                    y_offset=getattr(job, 'subtitle_y_offset', 75) or 75,
                                    words_per_subtitle=getattr(job, 'subtitle_words_per_subtitle', 3) or 3,
                                    enable_animation=bool(getattr(job, 'subtitle_enable_animation', 1)),
                                    language=getattr(job, 'subtitle_language', 'en') or 'en',
                                )

                                subtitle_request_id = subtitle_result.get("request_id")
                                if not subtitle_request_id:
                                    raise ValueError("No subtitle request_id received from FAL")

                                # Poll for subtitle completion (max 5 minutes)
                                max_subtitle_attempts = 60
                                for attempt in range(max_subtitle_attempts):
                                    time.sleep(5)  # 5 second intervals
                                    subtitle_status = get_subtitle_generation_status(subtitle_request_id, db)

                                    if subtitle_status.get("completed"):
                                        # Get subtitle result and download
                                        subtitle_fal_result = get_subtitle_generation_result(subtitle_request_id, db)

                                        loop2 = asyncio.new_event_loop()
                                        asyncio.set_event_loop(loop2)
                                        try:
                                            subtitled_video_data = loop2.run_until_complete(
                                                download_and_save_video(subtitle_fal_result, user_id=job.user_id)
                                            )
                                        finally:
                                            loop2.close()

                                        # Store original filename for deletion
                                        original_filename = video_data["filename"]
                                        original_thumbnail = video_data.get("thumbnail_filename")

                                        # Use subtitled video data
                                        video_data = subtitled_video_data
                                        subtitles_added_successfully = True
                                        logger.info(f"Story job {job.job_id}: Subtitles added successfully")

                                        # Delete original video file
                                        try:
                                            loop3 = asyncio.new_event_loop()
                                            asyncio.set_event_loop(loop3)
                                            try:
                                                loop3.run_until_complete(
                                                    storage_service.delete_file(original_filename, "videos", user_id=job.user_id)
                                                )
                                                if original_thumbnail:
                                                    loop3.run_until_complete(
                                                        storage_service.delete_file(original_thumbnail, "thumbnails", user_id=job.user_id)
                                                    )
                                            finally:
                                                loop3.close()
                                        except Exception as del_err:
                                            logger.warning(f"Failed to delete original video: {del_err}")

                                        break

                                    elif subtitle_status.get("status") == "error":
                                        raise ValueError(f"Subtitle generation failed: {subtitle_status.get('error', 'Unknown error')}")

                                else:
                                    raise TimeoutError("Subtitle generation timed out after 5 minutes")

                            except Exception as subtitle_error:
                                logger.error(f"Story job {job.job_id}: Subtitle generation failed: {subtitle_error}")
                                # Continue with the original video (without subtitles)
                                # subtitles_added_successfully remains False

                        # GUARD: Double-check no video was created while we were downloading
                        existing_video_check = db.query(Video).filter(
                            Video.filename == video_data["filename"]
                        ).first()
                        if existing_video_check:
                            logger.warning(f"Story video {video_data['filename']} already exists, skipping duplicate")
                            job.status = "completed"
                            job.progress = 100
                            job.result = {"video_id": existing_video_check.id}
                            job.completed_at = datetime.utcnow()
                            db.commit()
                            continue

                        # Save video to database with story-specific fields
                        video = Video(
                            filename=video_data["filename"],
                            thumbnail_filename=video_data.get("thumbnail_filename"),
                            prompt=job.prompt,
                            original_prompt=job.original_prompt,
                            video_type="story",
                            has_subtitles=1 if subtitles_added_successfully else 0,
                            duration_seconds=video_data.get("duration_seconds"),
                            width=video_data.get("width"),
                            height=video_data.get("height"),
                            fps=video_data.get("fps"),
                            model=story_model_for_job(job),
                            seed=job.seed,
                            file_size_bytes=video_data.get("file_size_bytes"),
                            user_id=job.user_id,
                        )
                        db.add(video)
                        db.flush()

                        record_usage(
                            db,
                            feature="story",
                            usd=usd,
                            model=story_model_for_job(job),
                            units=billed_seconds,
                            unit="second",
                            job_type="story",
                            job_id=job.job_id,
                            detail={
                                "video_model": story_family_for_endpoint(story_model_for_job(job)),
                                "resolution": job.resolution,
                                "reference_tokens": fal_result.get("reference_tokens") if isinstance(fal_result, dict) else None,
                                "video_id": video.id,
                                "has_subtitles": subtitles_added_successfully,
                                "source": "scheduler",
                            },
                        )
                        if subtitles_added_successfully:
                            # Stage 2 is a fal job of its own.
                            record_usage(
                                db,
                                feature="subtitle",
                                usd=subtitle_usd(video_data.get("duration_seconds")),
                                model=SUBTITLE_MODEL,
                                job_type="story",
                                job_id=job.job_id,
                                detail={"source": "scheduler"},
                            )

                        # Update job as completed
                        job.status = "completed"
                        job.progress = 100
                        job.estimated_usd = usd
                        job.completed_at = datetime.utcnow()
                        job.result = {"video_id": video.id}

                        db.commit()
                        logger.info(f"Story job {job.job_id} processed, video {video.id} saved")

                        # Send completion notification
                        try:
                            send_job_completion_notification(
                                db=db,
                                user_id=job.user_id,
                                job_type="story",
                                status="completed",
                                result_id=video.id,
                            )
                        except Exception as e:
                            logger.error(f"Failed to send notification for story job {job.job_id}: {e}")

                    elif fal_status.get("in_progress"):
                        job = lock_job(db, StoryGenerationJob, job.id)
                        if job is None or job.status not in CLAIMABLE_STATUSES:
                            db.rollback()
                            continue
                        if job.status != "in_progress":
                            job.status = "in_progress"
                            job.started_at = datetime.utcnow()
                        db.commit()

                    elif fal_status.get("status") == "error":
                        job = lock_job(db, StoryGenerationJob, job.id)
                        if job is None or job.status not in CLAIMABLE_STATUSES:
                            db.rollback()
                            continue
                        job.status = "failed"
                        job.error = fal_status.get("error", "Unknown error")
                        db.commit()
                        logger.error(f"Story job {job.job_id} failed: {job.error}")

                        try:
                            send_job_completion_notification(
                                db=db,
                                user_id=job.user_id,
                                job_type="story",
                                status="failed",
                                error_message=job.error,
                            )
                        except Exception as ne:
                            logger.error(f"Failed to send failure notification for story job {job.job_id}: {ne}")

                except Exception as e:
                    # A failed flush leaves the session unusable, and job.job_id below would raise.
                    db.rollback()
                    logger.error(f"Error processing story job {job.job_id}: {e}", exc_info=True)
                    # Shown to the user; the technical detail is in the log above.
                    if not _fail_job(db, StoryGenerationJob, job.id, claimed, "We could not finish this video. Please try generating it again."):
                        continue

        except Exception as e:
            logger.error(f"Error in story job processor: {e}")
        finally:
            db.close()

    def _process_pending_subtitle_jobs(self):
        """Check for pending/in_progress subtitle generation jobs and process completed ones."""
        from app.models.content import SubtitleJob, Video
        from app.clients.fal_client import (
            SUBTITLE_MODEL,
            download_and_save_video,
            get_subtitle_generation_result,
            get_subtitle_generation_status,
            subtitle_actual_usd,
        )
        from app.services.alert_service import send_job_completion_notification

        db = SessionLocal()
        try:
            # Find all pending/in_progress subtitle jobs
            # No row locks here: one SKIP LOCKED select used to lock every job
            # and the first commit released them all. Each job is claimed on
            # its own (claim_job) before it is downloaded and stored, and
            # status writes re-read the row under its lock (lock_job).
            jobs = db.query(SubtitleJob).filter(
                SubtitleJob.status.in_(["pending", "in_progress"])
            ).all()

            if not jobs:
                return

            logger.info(f"Processing {len(jobs)} pending subtitle generation jobs")

            for job in jobs:
                claimed = False
                try:
                    # IDEMPOTENCY CHECK: Skip if job already has a valid video result
                    if job.result and job.result.get("video_id"):
                        existing_video = db.query(Video).filter(
                            Video.id == job.result["video_id"]
                        ).first()
                        if existing_video:
                            logger.info(f"Subtitle job {job.job_id} already has video {job.result['video_id']}, marking as completed")
                            job.status = "completed"
                            job.progress = 100
                            if not job.completed_at:
                                job.completed_at = datetime.utcnow()
                            db.commit()
                            continue

                    # Check status with FAL
                    fal_status = get_subtitle_generation_status(job.request_id, db)

                    if fal_status.get("completed"):
                        logger.info(f"Subtitle job {job.job_id} completed, processing result")

                        # Claim the job: only one caller (this processor or a result
                        # endpoint) may download and store it.
                        if not claim_job(db, SubtitleJob, job.id):
                            logger.info(f"Subtitle job {job.job_id} was claimed elsewhere, skipping")
                            continue
                        claimed = True
                        db.refresh(job)

                        # Fetch result from FAL
                        fal_result = get_subtitle_generation_result(job.request_id, db)

                        # Download and save video
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            video_data = loop.run_until_complete(
                                download_and_save_video(fal_result, user_id=job.user_id)
                            )
                        finally:
                            loop.close()

                        # Extract transcript
                        transcript = fal_result.get("transcript", "")
                        if not transcript and fal_result.get("subtitles"):
                            subtitles = fal_result.get("subtitles", [])
                            transcript = " ".join([s.get("text", "") for s in subtitles])

                        # GUARD: Double-check no video was created while we were downloading
                        existing_video_check = db.query(Video).filter(
                            Video.filename == video_data["filename"]
                        ).first()
                        if existing_video_check:
                            logger.warning(f"Subtitle video {video_data['filename']} already exists, skipping duplicate")
                            job.status = "completed"
                            job.progress = 100
                            job.result = {"video_id": existing_video_check.id, "transcript": transcript}
                            job.completed_at = datetime.utcnow()
                            db.commit()
                            continue

                        # Recorded on the actual duration, never above the estimate
                        duration_seconds = video_data.get("duration_seconds")
                        if duration_seconds:
                            job.video_duration_seconds = duration_seconds
                        usd = subtitle_actual_usd(duration_seconds, job.estimated_usd)

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
                            model=SUBTITLE_MODEL,
                            file_size_bytes=video_data.get("file_size_bytes"),
                            user_id=job.user_id,
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
                                "source": "scheduler",
                            },
                        )

                        # Update job as completed
                        job.status = "completed"
                        job.progress = 100
                        job.estimated_usd = usd
                        job.completed_at = datetime.utcnow()
                        job.result = {"video_id": video.id, "transcript": transcript}

                        db.commit()
                        logger.info(f"Subtitle job {job.job_id} processed, video {video.id} saved")

                        # Send completion notification
                        try:
                            send_job_completion_notification(
                                db=db,
                                user_id=job.user_id,
                                job_type="subtitle",
                                status="completed",
                                result_id=video.id,
                            )
                        except Exception as e:
                            logger.error(f"Failed to send notification for subtitle job {job.job_id}: {e}")

                    elif fal_status.get("in_progress"):
                        job = lock_job(db, SubtitleJob, job.id)
                        if job is None or job.status not in CLAIMABLE_STATUSES:
                            db.rollback()
                            continue
                        if job.status != "in_progress":
                            job.status = "in_progress"
                            job.started_at = datetime.utcnow()
                        db.commit()

                    elif fal_status.get("status") == "error":
                        job = lock_job(db, SubtitleJob, job.id)
                        if job is None or job.status not in CLAIMABLE_STATUSES:
                            db.rollback()
                            continue
                        job.status = "failed"
                        job.error = fal_status.get("error", "Unknown error")
                        db.commit()
                        logger.error(f"Subtitle job {job.job_id} failed: {job.error}")

                        try:
                            send_job_completion_notification(
                                db=db,
                                user_id=job.user_id,
                                job_type="subtitle",
                                status="failed",
                                error_message=job.error,
                            )
                        except Exception as ne:
                            logger.error(f"Failed to send failure notification for subtitle job {job.job_id}: {ne}")

                except Exception as e:
                    # A failed flush leaves the session unusable, and job.job_id below would raise.
                    db.rollback()
                    logger.error(f"Error processing subtitle job {job.job_id}: {e}", exc_info=True)
                    # Shown to the user; the technical detail is in the log above.
                    if not _fail_job(db, SubtitleJob, job.id, claimed, "We could not finish adding subtitles. Please try again."):
                        continue

        except Exception as e:
            logger.error(f"Error in subtitle job processor: {e}")
        finally:
            db.close()


job_scheduler = JobScheduler()
