"""Quality checks: the price and availability, stored image verdicts, and
the fix of an image (app/services/quality_gate.py).

A fix is an instruction edit of the kept image on the fix model, priced by
its edit key and started by the user. Nothing here runs on its own.
"""

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.dependencies import CurrentUser, DbSession
from app.models.content import Image
from app.schemas.image import ImageResponse
from app.services import quality_gate as qg
from app.services.pricing import edit_usd
from app.services.usage import record_usage

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/config")
async def quality_config(current_user: CurrentUser, db: DbSession):
    """Whether checks can run, their price, the models /generate does not
    offer them on, and the model fixes are made with."""
    return {
        "available": qg.available(db),
        "estimated_usd": qg.price(),
        "skip_models": sorted(qg.SKIP_MODELS),
        "fix_model": qg.FIX_MODEL,
    }


def _owned_image(db, user_id: int, image_id: int) -> Image:
    image = db.query(Image).filter(Image.id == image_id, Image.user_id == user_id).first()
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return image


@router.get("/image/{image_id}")
async def image_quality(image_id: int, current_user: CurrentUser, db: DbSession):
    image = _owned_image(db, current_user.id, image_id)
    return {"image_id": image.id, "quality": qg.view(image.quality)}


class FixRequest(BaseModel):
    target: Literal["spelling", "defects"]


def _edit(db, image_url: str, prompt: str, resolution: str, aspect_ratio: str | None) -> dict:
    """One synchronous edit on the fix model (run in a thread)."""
    from app.clients.fal_client import build_edit_arguments, edit_max_images, fal_subscribe

    arguments = build_edit_arguments(
        qg.FIX_MODEL, prompt, [image_url], aspect_ratio=aspect_ratio or "auto", resolution=resolution.upper(),
        output_format="png", num_images=edit_max_images(qg.FIX_MODEL, 1),
    )
    return fal_subscribe(qg.FIX_MODEL, arguments, db)


@router.post("/image/{image_id}/fix", response_model=ImageResponse)
async def fix_image(image_id: int, body: FixRequest, current_user: CurrentUser, db: DbSession):
    """Fix what the check found on a kept image, as a new image: the failed
    spelling (each word spelled letter by letter) or the defects (their fix
    instructions), with "change nothing else"."""
    from app.clients.fal_client import (
        CONTENT_FILTER_ERROR, _image_dimensions, drop_safety_flagged, edit_output_extension, is_content_policy_error,
    )
    from app.services.storage_service import storage_service
    from app.services.url_fetch import afetch_bytes

    image = _owned_image(db, current_user.id, image_id)
    try:
        instruction = qg.fix_instruction(image.quality or {}, body.target)
    except qg.CheckError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    resolution = qg.fix_resolution(image.width, image.height)
    estimated_usd = edit_usd(qg.FIX_MODEL, resolution)
    source_url = image.get_url()

    try:
        result = await run_in_threadpool(_edit, db, source_url, instruction, resolution, image.aspect_ratio)
        result, _blocked = drop_safety_flagged(result or {})
        images = result.get("images") or []
        if not images:
            raise qg.CheckError("The fix came back empty. Please try again.")
        first = images[0] if isinstance(images[0], dict) else {"url": images[0]}
        data = await afetch_bytes(first.get("url") or "")
        ext = edit_output_extension(first, "png")
        filename = f"fix_{uuid.uuid4()}.{ext}"
        await storage_service.upload_file(
            file_data=data, filename=filename, storage_type="images",
            content_type="image/jpeg" if ext == "jpg" else f"image/{ext}", user_id=current_user.id,
        )
        width, height = _image_dimensions(first, data)
        fixed = Image(
            filename=filename,
            prompt=image.prompt,
            magic_prompt=instruction,
            art_style=image.art_style,
            width=width,
            height=height,
            model=qg.FIX_MODEL,
            aspect_ratio=image.aspect_ratio,
            user_id=current_user.id,
        )
        db.add(fixed)
        record_usage(
            db, feature="quality_fix", usd=estimated_usd, model=qg.FIX_MODEL, units=1, unit="image",
            detail={"image_id": image.id, "target": body.target, "resolution": resolution},
        )
        db.commit()
        db.refresh(fixed)
        return ImageResponse.from_orm_with_urls(fixed)
    except qg.CheckError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Quality fix of image {image_id} failed for user {current_user.id}")
        if is_content_policy_error(exc):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=CONTENT_FILTER_ERROR)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="We could not make this fix right now. Please try again in a moment.",
        )
