"""Image generation routes."""

import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from app.dependencies import CurrentUser, DbSession
from app.models.content import Image, GenerationJob
from app.clients.litellm_client import LLM_KEY_REJECTED, is_llm_auth_error
from app.services.fal_keys import FAL_KEY_REJECTED, FalKeyMissing, is_fal_auth_error
from app.models.api import APIProvider, AIModel, APISettings
from app.schemas.image import (
    GeneratePromptRequest,
    GeneratePromptResponse,
    GenerateImageRequest,
    ImageResponse,
    GenerateJobSubmitResponse,
    GenerateJobStatusResponse,
    GenerateJobResultResponse,
)
from app.clients.litellm_client import generate_prompt_for_image
from app.clients.fal_client import (
    validate_model,
    max_images_for,
    submit_image_generation,
    get_generation_status,
    get_generation_result,
    download_and_save_images,
    drop_safety_flagged,
    safety_blocked_notice,
    SAFETY_BLOCKED_ALL,
)
from app.services.image_prompt_profiles import PURPOSES, has_quoted_text
from app.services.job_state import (
    CLAIMABLE_STATUSES,
    NO_IMAGES_ERROR,
    claim_job,
    JOB_HANDED_BACK,
    fail_claimed_job,
    lock_job,
)
from app.services.pricing import image_usd
from app.services.usage import record_usage
from app.services import quality_gate

logger = logging.getLogger(__name__)

# Resolutions /generate accepts; each has a price per model.
IMAGE_RESOLUTIONS = ("1k", "2k", "4k")

router = APIRouter()


@router.post("/prompt", response_model=GeneratePromptResponse)
async def generate_prompt(
    request: GeneratePromptRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Generate an AI prompt from a topic."""
    # Get API settings
    api_settings = db.query(APISettings).first()
    if not api_settings or not api_settings.has_llm_key():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Magic Prompt needs a language model key. Add one in Settings, under API keys, or turn Magic Prompt off.",
        )

    # Get default provider and model or user's selection
    provider_id = current_user.selected_provider_id or api_settings.default_provider_id
    model_id = current_user.selected_model_id or api_settings.default_model_id

    if not provider_id or not model_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No AI provider configured",
        )

    provider = db.query(APIProvider).filter(APIProvider.id == provider_id).first()
    model = db.query(AIModel).filter(AIModel.id == model_id).first()

    if not provider or not model:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid provider or model",
        )

    try:
        # Convert advanced settings to dict if provided
        advanced_dict = None
        if request.advanced:
            advanced_dict = request.advanced.model_dump(exclude_none=True)
            # Handle nested camera settings
            if advanced_dict.get("camera"):
                camera = request.advanced.camera
                if camera:
                    advanced_dict["camera"] = camera.model_dump(exclude_none=True)

        prompt, settings_applied = await generate_prompt_for_image(
            topic=request.topic,
            model_name=model.name,
            provider_name=provider.name,
            db=db,
            art_style=request.style,
            advanced_settings=advanced_dict,
            target_model=request.model if request.model and validate_model(request.model) else None,
            aspect_ratio=request.aspect_ratio,
            lora=request.lora,
            purpose=request.purpose if request.purpose in PURPOSES else None,
            avoid=request.avoid,
            directions=request.directions if request.directions >= 2 else 0,
            # Rubric lines for the opt-in quality check, in the same call.
            with_checks=quality_gate.available(db),
        )

        directions = settings_applied.pop("directions", None) if settings_applied else None
        checks = settings_applied.pop("checks", None) if settings_applied else None
        return GeneratePromptResponse(
            prompt=prompt,
            enhanced=True,
            settings_applied=settings_applied if settings_applied else None,
            prompts=directions["prompts"] if directions else None,
            axis=(directions["axis"] or None) if directions else None,
            checks=quality_gate.clean_lines(checks) or None,
        )
    except Exception as e:
        logger.error(f"Prompt enhancement failed: {e}")
        if is_llm_auth_error(e):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=LLM_KEY_REJECTED)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The prompt could not be enhanced right now. Please try again.",
        )


# Ideogram's own Magic Prompt rewrites the wording it is asked to draw.
_KEEP_QUOTED_TEXT_MODELS = {"ideogram/v4.5"}


def _prompt_expansion(body: GenerateImageRequest) -> bool | None:
    """The provider's own prompt expansion: off for a Magic Prompt, which is
    already written for the model, and off on Ideogram when a raw prompt
    quotes words to appear in the image. None keeps the model's default."""
    if body.original_prompt:
        return False
    if body.model in _KEEP_QUOTED_TEXT_MODELS and has_quoted_text(body.prompt):
        return False
    return None


@router.post("/image", response_model=GenerateJobSubmitResponse)
async def generate_image_endpoint(
    body: GenerateImageRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Submit async image generation job.

    Returns a job_id immediately. Poll /generate/status/{job_id} for progress,
    then fetch results from /generate/result/{job_id} when complete.
    """
    # SECURITY: Validate model is in whitelist
    if not validate_model(body.model):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model '{body.model}' is not available",
        )

    # Priced per image by model and resolution (app/services/pricing.py). Models
    # that return one image per request are asked for one.
    resolution = (body.resolution or "1k").lower()
    if resolution not in IMAGE_RESOLUTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Resolution must be one of {', '.join(IMAGE_RESOLUTIONS)}",
        )
    num_images = max_images_for(body.model, body.num_images)
    try:
        estimated_usd = image_usd(body.model, resolution, num_images)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model '{body.model}' has no price configured",
        )

    # The opt-in quality check runs after the image is stored, in the scheduler.
    quality_request = None
    if body.quality_check:
        if body.model in quality_gate.SKIP_MODELS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The quality check is not offered on this model. Turn it off or pick another model.",
            )
        if not quality_gate.available(db):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The quality check is not available right now. Turn it off to generate without it.",
            )
        quality_request = {"lines": quality_gate.clean_lines(body.check_lines), "estimated_usd": quality_gate.price()}

    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Submit to fal's async queue. The scheduler and the routes below poll it.
        result = await run_in_threadpool(
            submit_image_generation,
            prompt=body.prompt,
            model=body.model,
            db=db,
            aspect_ratio=body.aspect_ratio,
            resolution=body.resolution,
            num_images=num_images,
            lora_url=body.lora_url,
            lora_scale=body.lora_scale,
            guidance_scale=body.guidance_scale,
            inference_steps=body.inference_steps,
            seed=body.seed,
            negative_prompt=body.negative_prompt,
            prompt_expansion=_prompt_expansion(body),
        )

        # Create job record in database
        job = GenerationJob(
            job_id=job_id,
            request_id=result["request_id"],
            user_id=current_user.id,
            prompt=body.prompt,
            original_prompt=body.original_prompt,
            model=body.model,
            art_style=body.art_style,
            aspect_ratio=body.aspect_ratio,
            resolution=body.resolution,
            num_images=num_images,
            guidance_scale=int(body.guidance_scale) if body.guidance_scale else None,
            inference_steps=body.inference_steps,
            seed=result.get("seed"),
            lora_url=body.lora_url,
            lora_scale=int(body.lora_scale) if body.lora_scale else None,
            quality_check=quality_request,
            status="pending",
            estimated_usd=estimated_usd,
        )
        db.add(job)
        db.commit()

        return GenerateJobSubmitResponse(
            job_id=job_id,
            status="pending",
            message="Job submitted successfully. Poll /generate/status/{job_id} for progress.",
        )

    except FalKeyMissing as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ValueError:
        logger.warning(f"Image generation request rejected for user {current_user.id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This request could not be accepted. Check the model and settings and try again.",
        )
    except Exception as exc:
        logger.exception(f"Image generation submit failed for user {current_user.id}")
        if is_fal_auth_error(exc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FAL_KEY_REJECTED)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="We could not start this generation right now. Please try again in a moment.",
        )


@router.get("/jobs/pending")
async def get_pending_jobs(
    current_user: CurrentUser,
    db: DbSession,
):
    """Get all pending/in_progress jobs for the current user."""
    jobs = db.query(GenerationJob).filter(
        GenerationJob.user_id == current_user.id,
        GenerationJob.status.in_(["pending", "in_progress"]),
    ).order_by(GenerationJob.created_at.desc()).all()

    return [
        {
            "job_id": job.job_id,
            "status": job.status,
            "progress": job.progress,
            "model": job.model,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        }
        for job in jobs
    ]


# Plain def: the status check below is a blocking call to fal, and FastAPI runs a def
# handler in its threadpool instead of stalling the event loop.
@router.get("/status/{job_id}", response_model=GenerateJobStatusResponse)
def get_job_status(
    job_id: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get status of an async generation job."""
    # Find job
    job = db.query(GenerationJob).filter(
        GenerationJob.job_id == job_id,
        GenerationJob.user_id == current_user.id,
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # If already completed or failed, return cached status
    if job.status in ["completed", "failed"]:
        return GenerateJobStatusResponse(
            job_id=job.job_id,
            status=job.status,
            progress=100 if job.status == "completed" else 0,
            logs=job.logs.split("\n") if job.logs else None,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
        )

    # Poll FAL for current status
    try:
        fal_status = get_generation_status(job.model, job.request_id, db)

        # Re-read under the row lock: the job may have been claimed while fal
        # answered, and a stale write would make it claimable again.
        job = lock_job(db, GenerationJob, job.id)
        if job.status not in CLAIMABLE_STATUSES:
            db.rollback()
            fal_status = {"status": job.status, "logs": fal_status.get("logs")}

        # Update job status - but DON'T mark as completed here!
        # The scheduler handles completion to ensure images are downloaded and saved.
        # This prevents a race condition where the job is marked complete but
        # the images aren't actually processed.
        if job.status not in CLAIMABLE_STATUSES:
            pass
        elif fal_status.get("completed"):
            # Keep as in_progress so scheduler will process it
            if job.status == "pending":
                job.status = "in_progress"
            job.progress = 90  # Show high progress to indicate almost done
        elif fal_status.get("in_progress"):
            job.status = "in_progress"
            job.progress = 50  # FAL doesn't provide exact progress
            if not job.started_at:
                job.started_at = datetime.utcnow()
        elif fal_status.get("status") == "error":
            job.status = "failed"
            job.error = fal_status.get("error")

        # Store logs
        if fal_status.get("logs"):
            job.logs = "\n".join(fal_status["logs"])

        db.commit()

        # Return the actual FAL status to frontend (even if DB status differs)
        response_status = "completed" if fal_status.get("completed") else job.status
        response_progress = 100 if fal_status.get("completed") else job.progress

        return GenerateJobStatusResponse(
            job_id=job.job_id,
            status=response_status,
            progress=response_progress,
            logs=fal_status.get("logs"),
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
        )

    except Exception:
        logger.exception(f"Status check failed for generation job {job.job_id}")
        return GenerateJobStatusResponse(
            job_id=job.job_id,
            status=job.status,
            progress=job.progress,
            error="We could not check this job just now. It is still running, so please check again in a moment.",
            created_at=job.created_at,
            started_at=job.started_at,
        )


def _result_notice(job: GenerationJob) -> str | None:
    """The safety-filter sentence for a finished job, from its stored result."""
    result = job.result or {}
    return safety_blocked_notice(int(result.get("safety_blocked") or 0), len(result.get("image_ids") or []))


def _stored_usd(job: GenerationJob, stored: int) -> float:
    """The job's estimate for the images actually stored, never more than the estimate."""
    asked = max(int(job.num_images or 1), 1)
    return round(float(job.estimated_usd or 0) * min(stored, asked) / asked, 4)


@router.get("/result/{job_id}", response_model=GenerateJobResultResponse)
async def get_job_result(
    job_id: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get result of a completed generation job.

    Downloads images from FAL, saves them locally, creates Image records and
    records what they cost.
    """
    # Find job
    job = db.query(GenerationJob).filter(
        GenerationJob.job_id == job_id,
        GenerationJob.user_id == current_user.id,
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # GUARD: If already processed (has result with images), return cached result
    if job.result and job.result.get("image_ids"):
        # Rebuild image responses from stored result
        images = []
        for img_id in job.result.get("image_ids", []):
            image = db.query(Image).filter(Image.id == img_id).first()
            if image:
                images.append(ImageResponse.from_orm_with_urls(image))

        # Ensure job is marked completed
        if job.status != "completed":
            job.status = "completed"
            job.progress = 100
            if not job.completed_at:
                job.completed_at = datetime.utcnow()
            db.commit()

        return GenerateJobResultResponse(
            job_id=job.job_id,
            status="completed",
            images=images,
            estimated_usd=job.estimated_usd or 0,
            completed_at=job.completed_at,
            notice=_result_notice(job),
        )

    if job.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=job.error or "Generation failed",
        )

    # Check if job is complete
    fal_status = await run_in_threadpool(get_generation_status, job.model, job.request_id, db)

    if not fal_status.get("completed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job not complete. Current status: {fal_status.get('status', 'unknown')}",
        )

    # Claim the job atomically: only one caller (this endpoint or the
    # scheduler) may download and store it.
    if not claim_job(db, GenerationJob, job.id):
        db.refresh(job)
        if job.result and job.result.get("image_ids"):
            images = [
                ImageResponse.from_orm_with_urls(image)
                for image in (db.query(Image).filter(Image.id == img_id).first()
                              for img_id in job.result.get("image_ids", []))
                if image
            ]
            return GenerateJobResultResponse(
                job_id=job.job_id,
                status="completed",
                images=images,
                estimated_usd=job.estimated_usd or 0,
                completed_at=job.completed_at,
                notice=_result_notice(job),
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is currently being processed. Please try again in a few seconds.",
        )
    db.refresh(job)

    try:
        # Fetch result from FAL
        fal_result = await run_in_threadpool(get_generation_result, job.model, job.request_id, db)
        # Images the provider's safety filter blanked are not stored.
        fal_result, blocked = drop_safety_flagged(fal_result)

        # Download and save images (organized by user folder)
        downloaded_images = await download_and_save_images(fal_result, job.seed, user_id=job.user_id)

        # Save images to database
        saved_images = []
        image_ids = []

        for img_data in downloaded_images:
            # GUARD: Check if image with same filename already exists
            existing_image = db.query(Image).filter(
                Image.filename == img_data["filename"]
            ).first()
            if existing_image:
                logger.warning(f"Image {img_data['filename']} already exists, using existing")
                saved_images.append(ImageResponse.from_orm_with_urls(existing_image))
                image_ids.append(existing_image.id)
                continue

            # Handle prompt storage
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
                user_id=current_user.id,
                quality=quality_gate.pending_from_job(job),
            )
            db.add(image)
            db.flush()

            saved_images.append(ImageResponse.from_orm_with_urls(image))
            image_ids.append(image.id)

        if not image_ids:
            # Nothing arrived.
            job.status = "failed"
            job.progress = 0
            job.completed_at = datetime.utcnow()
            job.error = SAFETY_BLOCKED_ALL if blocked else NO_IMAGES_ERROR
            db.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=job.error)

        # Record what the images actually stored cost
        usd = _stored_usd(job, len(image_ids))
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
                "images_stored": len(image_ids),
                "safety_blocked": blocked,
                "prompt": job.prompt[:200] if job.prompt else None,
                "source": "result_endpoint",
            },
        )

        # Update job as completed
        job.status = "completed"
        job.progress = 100
        job.estimated_usd = usd
        job.completed_at = datetime.utcnow()
        job.result = {"image_ids": image_ids, **({"safety_blocked": blocked} if blocked else {})}

        db.commit()

        return GenerateJobResultResponse(
            job_id=job.job_id,
            status="completed",
            images=saved_images,
            estimated_usd=usd,
            completed_at=job.completed_at,
            notice=_result_notice(job),
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Processing the result of generation job {job.job_id} failed")
        # Mark job as failed
        message = "We could not save the images from this job. Please try generating again."
        failed = fail_claimed_job(db, GenerationJob, job.id, message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=message if failed else JOB_HANDED_BACK,
        )


def _fit_exact(data: bytes, size: tuple[int, int]) -> bytes:
    """The image cropped from the centre to the size's ratio and resized to
    exactly that many pixels, as PNG."""
    from io import BytesIO
    from PIL import Image as PILImage, ImageOps

    with PILImage.open(BytesIO(data)) as src:
        src.load()
        fitted = ImageOps.fit(src.convert("RGB"), size, method=PILImage.Resampling.LANCZOS, centering=(0.5, 0.5))
    out = BytesIO()
    fitted.save(out, format="PNG", optimize=True)
    return out.getvalue()


@router.get("/export/{image_id}")
async def export_image(
    image_id: int,
    purpose: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """One of the user's images at a platform's exact pixels ("Use for" on
    /generate): a YouTube thumbnail at 1280x720, a LinkedIn image at
    1200x627. Cropped from the centre and resized with Pillow, as PNG. The
    stored image is not changed."""
    entry = PURPOSES.get(purpose)
    if not entry or not entry[2]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This export size is not available.")
    image = db.query(Image).filter(Image.id == image_id, Image.user_id == current_user.id).first()
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    from app.services.storage_service import storage_service

    data = await storage_service.get_file_bytes(image.filename, "images", user_id=image.user_id)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This image file could not be found.")
    try:
        png = await run_in_threadpool(_fit_exact, data, entry[2])
    except Exception:
        logger.exception(f"Export of image {image_id} for {purpose} failed")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="This image could not be resized. Please download the original instead.",
        )
    width, height = entry[2]
    return Response(
        content=png,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{purpose}-{image_id}-{width}x{height}.png"'},
    )
