"""Gallery routes."""

import logging
import os
from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import desc

from app.dependencies import CurrentUser, DbSession
from app.models.content import Image
from app.schemas.image import ImageResponse, GalleryResponse
from app.schemas.common import MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=GalleryResponse)
async def get_gallery(
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    """Get user's image gallery."""
    # Get total count
    total = db.query(Image).filter(Image.user_id == current_user.id).count()

    # Get paginated images
    offset = (page - 1) * page_size
    images = (
        db.query(Image)
        .filter(Image.user_id == current_user.id)
        .order_by(desc(Image.created_at))
        .offset(offset)
        .limit(page_size)
        .all()
    )

    total_pages = (total + page_size - 1) // page_size

    return GalleryResponse(
        images=[ImageResponse.from_orm_with_urls(img) for img in images],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{image_id}", response_model=ImageResponse)
async def get_image(
    image_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get a single image."""
    image = db.query(Image).filter(
        Image.id == image_id,
        Image.user_id == current_user.id,
    ).first()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found",
        )

    return ImageResponse.from_orm_with_urls(image)


@router.delete("/{image_id}", response_model=MessageResponse)
async def delete_image(
    image_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Delete an image and its stored files."""
    from app.services.storage_service import storage_service

    image = db.query(Image).filter(
        Image.id == image_id,
        Image.user_id == current_user.id,
    ).first()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found",
        )

    filename, user_id = image.filename, image.user_id

    # Database first: a failed commit must not leave a row whose file is gone.
    db.delete(image)
    db.commit()

    # Then the stored files, best effort.
    base_name = os.path.splitext(filename)[0]
    for name in dict.fromkeys([filename, f"{base_name}.webp"]):
        try:
            await storage_service.delete_file(name, "images", user_id=user_id)
        except Exception as e:
            logger.warning(f"Could not delete image file {name}: {e}")

    return MessageResponse(message="Image deleted successfully")


@router.get("/{image_id}/download/{format}")
async def download_image(
    image_id: int,
    format: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Download an image in specified format.

    Vector originals (logos) are always served as SVG: there is no server-side
    rasterising, so a png/jpg/webp request for one returns the SVG under its
    real type and extension instead of a mislabelled file.
    """
    from fastapi.responses import Response
    from app.services.storage_service import storage_service

    if format not in ["png", "webp", "jpg", "jpeg", "svg"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format. Use: png, webp, jpg, jpeg, svg",
        )

    image = db.query(Image).filter(
        Image.id == image_id,
        Image.user_id == current_user.id,
    ).first()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found",
        )

    base_name = os.path.splitext(image.filename)[0]
    is_svg = image.filename.lower().endswith(".svg")

    if format == "svg" and not is_svg:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SVG download is only available for vector images such as logos",
        )

    if is_svg:
        file_bytes = await storage_service.get_file_bytes(image.filename, "images", user_id=image.user_id)
        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Image file not found",
            )
        return Response(
            content=file_bytes,
            media_type="image/svg+xml",
            headers={
                "Content-Disposition": f'attachment; filename="{base_name}.svg"',
                "X-Content-Type-Options": "nosniff",
                # Stored SVGs are sanitised; this keeps a directly opened one inert anyway.
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
            },
        )
    target_filename = f"{base_name}.{format}"

    # Try to get the file in requested format first
    file_bytes = await storage_service.get_file_bytes(target_filename, "images", user_id=image.user_id)

    # If requested format doesn't exist, try original
    if not file_bytes:
        file_bytes = await storage_service.get_file_bytes(image.filename, "images", user_id=image.user_id)
        # Use original format if fallback
        target_filename = image.filename

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image file not found",
        )

    # Determine media type
    media_type_map = {
        "png": "image/png",
        "webp": "image/webp",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
    }
    actual_ext = os.path.splitext(target_filename)[1].lstrip(".")
    media_type = media_type_map.get(actual_ext, f"image/{format}")

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{base_name}.{format}"',
        },
    )
