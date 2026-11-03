"""Edit a kept image with an instruction, as a new image.

The Generate page offers this under each result: the user describes a change
and Ideogram V4.5 makes it in its precise mode, which copies back every pixel
the edit did not need to change. Each edit is a new gallery image, so edits
chain for any number of turns and any earlier version can be edited again.

The source is always one of the user's own images, looked up by id; the
browser never sends an image URL.
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.dependencies import CurrentUser, DbSession
from app.models.content import Image
from app.schemas.image import ImageResponse
from app.services.pricing import edit_usd
from app.services.quality_gate import fix_resolution
from app.services.usage import record_usage

logger = logging.getLogger(__name__)

router = APIRouter()

EDIT_MODEL = "ideogram/v4.5/edit"

KEEP = "Change only what this asks for and keep everything else in the picture exactly as it is."


class _EditFailed(Exception):
    """An edit that produced nothing."""


class ImageEditRequest(BaseModel):
    instruction: str = Field(min_length=2, max_length=1000)


def edit_prompt(instruction: str) -> str:
    text = " ".join(instruction.split()).rstrip(".")
    return f"{text}. {KEEP}"


def _edit(db, image_url: str, prompt: str) -> dict:
    """One synchronous Ideogram edit in its precise mode (run in a thread)."""
    from app.clients.fal_client import build_edit_arguments, fal_subscribe

    # The model keeps the source size, so no ratio or resolution is sent.
    arguments = build_edit_arguments(EDIT_MODEL, prompt, [image_url], aspect_ratio="auto", num_images=1)
    arguments["edit_precision"] = "high"
    return fal_subscribe(EDIT_MODEL, arguments, db)


@router.post("/{image_id}", response_model=ImageResponse)
async def edit_image(image_id: int, body: ImageEditRequest, current_user: CurrentUser, db: DbSession):
    """Make the described change to one of the user's images and keep the
    result as a new image."""
    from app.clients.fal_client import (
        CONTENT_FILTER_ERROR, _image_dimensions, drop_safety_flagged, edit_output_extension, is_content_policy_error,
    )
    from app.services.storage_service import storage_service
    from app.services.url_fetch import afetch_bytes

    image = db.query(Image).filter(Image.id == image_id, Image.user_id == current_user.id).first()
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    if (image.filename or "").lower().endswith(".svg"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Vector logos cannot be edited here. Edit them in Logo Studio.")

    resolution = fix_resolution(image.width, image.height)
    estimated_usd = edit_usd(EDIT_MODEL, resolution)
    prompt = edit_prompt(body.instruction)
    source_url = image.get_url()

    try:
        result = await run_in_threadpool(_edit, db, source_url, prompt)
        result, _blocked = drop_safety_flagged(result or {})
        images = result.get("images") or []
        if not images:
            raise _EditFailed()
        first = images[0] if isinstance(images[0], dict) else {"url": images[0]}
        data = await afetch_bytes(first.get("url") or "")
        ext = edit_output_extension(first, "png")
        filename = f"edit_{uuid.uuid4()}.{ext}"
        await storage_service.upload_file(
            file_data=data, filename=filename, storage_type="images",
            content_type="image/jpeg" if ext == "jpg" else f"image/{ext}", user_id=current_user.id,
        )
        width, height = _image_dimensions(first, data)
        edited = Image(
            filename=filename,
            prompt=" ".join(body.instruction.split()),
            magic_prompt=prompt,
            art_style=image.art_style,
            width=width,
            height=height,
            model=EDIT_MODEL,
            seed=result.get("seed"),
            rendering="Edit",
            aspect_ratio=image.aspect_ratio,
            user_id=current_user.id,
        )
        db.add(edited)
        record_usage(
            db, feature="image_edit", usd=estimated_usd, model=EDIT_MODEL, units=1, unit="image",
            detail={"image_id": image.id, "resolution": resolution, "prompt": body.instruction[:200]},
        )
        db.commit()
        db.refresh(edited)
        return ImageResponse.from_orm_with_urls(edited)
    except _EditFailed:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="The edit came back empty. Please try again.")
    except Exception as exc:
        logger.exception(f"Edit of image {image_id} failed for user {current_user.id}")
        if is_content_policy_error(exc):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=CONTENT_FILTER_ERROR)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="We could not edit this image right now. Please try again in a moment.",
        )
