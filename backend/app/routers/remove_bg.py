"""Background Removal - Remove backgrounds from images using FAL's Bria model.

Allows users to upload images and remove their backgrounds.
Returns PNG images with transparent backgrounds.
Supports batch processing of multiple images.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.dependencies import CurrentUser, DbSession
from app.models.content import Image
from app.schemas.image import ImageResponse
from app.clients.fal_client import remove_background
from app.services.pricing import REMOVE_BG_KEY, usd_for
from app.services.usage import record_usage

logger = logging.getLogger(__name__)

router = APIRouter()

# Images per request; each one is a fal call made while the request waits.
MAX_BATCH_IMAGES = 20

BRIA_MODEL = "fal-ai/bria/background/remove"


class RemoveBgRequest(BaseModel):
    """Request schema for background removal."""
    image_url: Optional[str] = Field(default=None, description="Base64 data URL of single image (legacy)")
    image_urls: Optional[List[str]] = Field(default=None, description="Base64 data URLs for batch processing")


class RemoveBgImageResult(BaseModel):
    """Single image result."""
    url: str
    gallery_id: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None


class RemoveBgResponse(BaseModel):
    """Response schema for background removal."""
    image_url: Optional[str] = None  # Legacy single image
    images: Optional[List[RemoveBgImageResult]] = None  # Batch results
    gallery_id: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    estimated_usd: float


@router.post("/generate", response_model=RemoveBgResponse)
async def remove_bg(
    body: RemoveBgRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Remove background from images using FAL's Bria model.

    Upload one or more images to remove their backgrounds.
    Returns PNG images with transparent backgrounds.
    Supports batch processing of multiple images.
    """
    # Determine images to process
    images_to_process = []
    if body.image_urls:
        images_to_process = body.image_urls
    elif body.image_url:
        images_to_process = [body.image_url]

    if not images_to_process:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No images provided. Please upload at least one image.",
        )
    # Each image is a sequential fal call inside this request.
    if len(images_to_process) > MAX_BATCH_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Up to {MAX_BATCH_IMAGES} images per batch.",
        )

    num_images = len(images_to_process)

    try:
        # Every fal call first, then the rows in one short write: nothing holds the
        # database write lock while fal works. As before, one failed image fails the
        # whole batch and no rows are saved.
        outputs = []
        for image_url in images_to_process:
            # Remove background using Bria model
            outputs.append(await remove_background(
                image_url=image_url,
                db=db,
                user_id=current_user.id,
            ))

        # Save to database/gallery
        rows = []
        for result in outputs:
            db_image = Image(
                filename=result["filename"],
                prompt="Background removal",
                art_style="remove_bg",
                width=result.get("width"),
                height=result.get("height"),
                model=BRIA_MODEL,
                user_id=current_user.id,
            )
            db.add(db_image)
            rows.append(db_image)
        db.flush()  # Get the IDs without committing

        results = [
            RemoveBgImageResult(
                url=result["url"],
                gallery_id=row.id,
                width=result.get("width"),
                height=result.get("height"),
            )
            for result, row in zip(outputs, rows)
        ]

        estimated_usd = round(usd_for(REMOVE_BG_KEY) * num_images, 4)
        record_usage(
            db,
            feature="remove_bg",
            usd=estimated_usd,
            model=BRIA_MODEL,
            units=num_images,
            unit="image",
        )
        db.commit()

        # Return response (compatible with both single and batch)
        if len(results) == 1:
            return RemoveBgResponse(
                image_url=results[0].url,
                images=results,
                gallery_id=results[0].gallery_id,
                width=results[0].width,
                height=results[0].height,
                estimated_usd=estimated_usd,
            )
        else:
            return RemoveBgResponse(
                images=results,
                estimated_usd=estimated_usd,
            )

    except ValueError:
        logger.exception(f"Background removal failed for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="We could not remove the background. Check the image and try again.",
        )
    except Exception:
        logger.exception(f"Background removal failed for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="We could not remove the background right now. Please try again in a moment.",
        )


@router.get("/history")
async def get_remove_bg_history(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = 20,
):
    """Get user's background removal history."""
    images = (
        db.query(Image)
        .filter(
            Image.user_id == current_user.id,
            Image.art_style == "remove_bg",
        )
        .order_by(Image.created_at.desc())
        .limit(limit)
        .all()
    )

    return [ImageResponse.from_orm_with_urls(img) for img in images]
