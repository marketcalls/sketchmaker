"""Add text: exact typography on a generated image (services/text_overlay.py).

No provider call. The result is a NEW gallery image in the owner's images/
folder; the original is kept. Rendering is Pillow only, run off the event loop.

  GET  /config      {max_layers, max_text_chars, roles, fonts, palette, positions,
                     formats: {fmt: {destination, view_width, min_px, min_size, safe_zone}}}
  POST /preview     {image_id, spec} -> {image (PNG data URL, at most 960 px), boxes: [{x0, y0,
                     x1, y1}] (fractions), warnings: [{layer, kind, message}], width, height, format}
  POST /render      {image_id, spec} -> {image: ImageResponse, warnings}. Stores the image.

spec = {font, layers: [{role, text, weight, size (per cent of the width), color, uppercase,
        align, x, y (block centre, fractions), max_width, line_height, backdrop none|scrim|box,
        backdrop_color, backdrop_opacity, stroke, stroke_color, shadow}]}
"""

from __future__ import annotations

import base64
import logging
import threading
import uuid
from collections import OrderedDict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.dependencies import CurrentUser, DbSession
from app.models.content import Image
from app.schemas.image import ImageResponse
from app.services import text_overlay
from app.utils.media_labels import is_vector_filename

logger = logging.getLogger(__name__)

router = APIRouter()

ART_STYLE = "text_overlay"
MODEL = "sketchmaker/text-overlay"
MAX_SOURCE_BYTES = 40 * 1024 * 1024

# Decoded sources for previews, per worker: an edit session previews the
# same image many times. Small (a few downscaled images).
_CACHE: "OrderedDict[tuple[int, int, str], tuple]" = OrderedDict()
_CACHE_SIZE = 4
_cache_lock = threading.Lock()


class OverlayIn(BaseModel):
    image_id: int = Field(ge=1)
    spec: text_overlay.Spec


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _owned_image(db, user_id: int, image_id: int) -> Image:
    image = db.query(Image).filter(Image.id == image_id, Image.user_id == user_id).first()
    if image is None:
        raise _error(status.HTTP_404_NOT_FOUND, "That image was not found in your gallery.")
    if is_vector_filename(image.filename):
        raise _error(status.HTTP_400_BAD_REQUEST, "Add text works on pictures, not vector logos.")
    return image


async def _source(image: Image) -> tuple[bytes, object]:
    """(bytes, decoded RGB image) of a gallery image, from storage."""
    from app.services.storage_service import storage_service

    data = await storage_service.get_file_bytes(image.filename, "images", user_id=image.user_id)
    if not data:
        raise _error(status.HTTP_404_NOT_FOUND, "The image file is missing. It may have been deleted.")
    if len(data) > MAX_SOURCE_BYTES:
        raise _error(status.HTTP_400_BAD_REQUEST, "This image is too large to add text to.")
    try:
        decoded = await run_in_threadpool(text_overlay.open_image, data)
    except text_overlay.TextOverlayError as exc:
        raise _error(status.HTTP_400_BAD_REQUEST, str(exc))
    return data, decoded


async def _preview_source(image: Image):
    """(full width, full height, image for previews) with a small cache."""
    key = (image.user_id, image.id, image.filename)
    with _cache_lock:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
            return hit
    _data, decoded = await _source(image)
    W, H = decoded.size
    scale = min(1.0, text_overlay.PREVIEW_LONG_SIDE / max(W, H))
    if scale < 1.0:
        from PIL import Image as PILImage

        decoded = decoded.resize((max(1, round(W * scale)), max(1, round(H * scale))), PILImage.Resampling.LANCZOS)
    entry = (W, H, decoded)
    with _cache_lock:
        _CACHE[key] = entry
        while len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)
    return entry


def _source_format(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "JPEG"
    return "PNG"


@router.get("/config")
async def get_config(current_user: CurrentUser):
    return text_overlay.config()


@router.post("/preview")
async def preview(body: OverlayIn, current_user: CurrentUser, db: DbSession):
    """Stores nothing."""
    image = _owned_image(db, current_user.id, body.image_id)
    W, H, small = await _preview_source(image)

    try:
        png, boxes, warnings = await run_in_threadpool(text_overlay.preview, small, body.spec, (W, H))
    except text_overlay.TextOverlayError as exc:
        raise _error(status.HTTP_400_BAD_REQUEST, str(exc))
    except Exception:
        logger.exception(f"Text overlay preview failed for image {image.id}")
        raise _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "The preview could not be drawn. Please try again.")
    return {
        "image": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
        "boxes": boxes,
        "warnings": warnings,
        "width": W,
        "height": H,
        "format": text_overlay.format_of(W, H),
    }


@router.post("/render")
async def render(body: OverlayIn, current_user: CurrentUser, db: DbSession):
    """Draw the card at full size and store it as a new gallery image."""
    from app.services.storage_service import storage_service

    parent = _owned_image(db, current_user.id, body.image_id)
    data, decoded = await _source(parent)
    try:
        content, ext, content_type, warnings = await run_in_threadpool(
            text_overlay.render, decoded, body.spec, source_format=_source_format(data))
    except text_overlay.TextOverlayError as exc:
        raise _error(status.HTTP_400_BAD_REQUEST, str(exc))
    except Exception:
        logger.exception(f"Text overlay render failed for image {parent.id}")
        raise _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "The text could not be added. Please try again.")
    del data

    filename = f"text_{uuid.uuid4().hex}{ext}"
    try:
        # images/{user_id}/: removed with the gallery row when the user deletes it.
        await storage_service.upload_file(file_data=content, filename=filename, storage_type="images",
                                          content_type=content_type, user_id=current_user.id)
    except Exception:
        logger.exception(f"Text overlay image for user {current_user.id} could not be stored")
        raise _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "The image could not be saved. Please try again.")

    headline = text_overlay.headline_of(body.spec)
    prompt = f"Text: {headline}" + (f" | {parent.prompt}" if parent.prompt else "")
    row = Image(
        filename=filename,
        prompt=prompt[:2000],
        magic_prompt=parent.magic_prompt,
        art_style=ART_STYLE,
        width=decoded.width,
        height=decoded.height,
        model=MODEL,
        seed=parent.seed,
        rendering="text_overlay",
        aspect_ratio=parent.aspect_ratio,
        user_id=current_user.id,
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Text overlay gallery row could not be saved")
        try:
            await storage_service.delete_file(filename, "images", user_id=current_user.id)
        except Exception:
            logger.warning(f"Could not remove the unsaved text overlay file {filename}")
        raise _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "The image could not be saved. Please try again.")
    db.refresh(row)
    return {"image": ImageResponse.from_orm_with_urls(row).model_dump(mode="json"), "warnings": warnings}
