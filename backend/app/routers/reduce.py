"""Image Reduce/Resize - Utility for resizing and converting images.

Allows users to:
- Resize images by percentage or exact pixels
- Convert between formats (PNG, JPG, WebP)
- Adjust quality/compression
- Set DPI/resolution
- Batch process multiple images
- Choose background color for transparent images

Runs on this machine, with no provider cost.
"""

import io
import base64
import logging
import uuid
import zipfile
from typing import List, Literal
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from PIL import Image as PILImage

from app.dependencies import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()

# Raster formats a browser can hand us. Anything else is refused before Pillow
# picks a decoder: EPS in particular is decoded by shelling out to Ghostscript.
ALLOWED_INPUT_FORMATS = ["PNG", "JPEG", "WEBP", "GIF", "BMP", "TIFF", "ICO"]

# Both ends are capped. Pillow's own bomb guard only warns below ~179M pixels,
# and the resize target is user supplied (10000% or 100000x100000), so either
# side could ask a worker for gigabytes.
MAX_INPUT_PIXELS = 50_000_000
MAX_OUTPUT_PIXELS = 50_000_000


class ImageToProcess(BaseModel):
    """Single image data for processing."""
    data_url: str = Field(..., description="Base64 data URL of the image")
    filename: str = Field(..., description="Original filename")


class ReduceRequest(BaseModel):
    """Request schema for image reduction/resizing."""
    images: List[ImageToProcess] = Field(..., description="Images to process")

    # Resize options
    resize_mode: Literal["percent", "pixels"] = Field(default="percent", description="Resize by percent or exact pixels")
    width: int = Field(default=70, description="Width value (percent or pixels based on mode)")
    height: int = Field(default=70, description="Height value (percent or pixels based on mode)")
    maintain_aspect_ratio: bool = Field(default=True, description="Lock aspect ratio when resizing")

    # Output options
    output_format: Literal["jpg", "png", "webp"] = Field(default="jpg", description="Output image format")
    quality: int = Field(default=90, ge=1, le=100, description="Output quality (1-100)")
    dpi: int = Field(default=72, ge=1, le=600, description="Output DPI/resolution")

    # Background for transparent images
    background_color: Literal["white", "black", "transparent"] = Field(
        default="white",
        description="Background color for transparent images when converting to JPG"
    )


class ProcessedImage(BaseModel):
    """Single processed image result."""
    filename: str
    data_url: str
    original_size: int  # bytes
    new_size: int  # bytes
    original_dimensions: str  # "WxH"
    new_dimensions: str  # "WxH"
    format: str
    reduction_percent: float


class ReduceResponse(BaseModel):
    """Response schema for image reduction."""
    images: List[ProcessedImage]
    total_original_size: int
    total_new_size: int
    total_reduction_percent: float


def decode_data_url(data_url: str) -> tuple[bytes, str]:
    """Decode a base64 data URL to bytes and mime type."""
    try:
        # Format: data:image/png;base64,<data>
        header, data = data_url.split(",", 1)
        mime_type = header.split(":")[1].split(";")[0]
        image_bytes = base64.b64decode(data)
        return image_bytes, mime_type
    except Exception as e:
        raise ValueError(f"Invalid data URL format: {e}")


def encode_to_data_url(image_bytes: bytes, format: str) -> str:
    """Encode bytes to a base64 data URL."""
    mime_map = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }
    mime_type = mime_map.get(format.lower(), "image/jpeg")
    b64_data = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{b64_data}"


def process_single_image(
    image_data: ImageToProcess,
    resize_mode: str,
    width: int,
    height: int,
    maintain_aspect_ratio: bool,
    output_format: str,
    quality: int,
    dpi: int,
    background_color: str,
) -> ProcessedImage:
    """Process a single image with the given parameters."""

    # Decode the input image
    image_bytes, _ = decode_data_url(image_data.data_url)
    original_size = len(image_bytes)

    # Open with Pillow. open() only reads the header, so the size is checked
    # before any pixels are decoded.
    img = PILImage.open(io.BytesIO(image_bytes), formats=ALLOWED_INPUT_FORMATS)
    original_width, original_height = img.size
    if original_width * original_height > MAX_INPUT_PIXELS:
        raise ValueError(f"Image is too large ({original_width}x{original_height})")
    original_dimensions = f"{original_width}x{original_height}"

    # Calculate new dimensions
    if resize_mode == "percent":
        new_width = int(original_width * width / 100)
        new_height = int(original_height * height / 100)
    else:  # pixels
        if maintain_aspect_ratio:
            # Calculate based on the dimension that was changed
            aspect_ratio = original_width / original_height
            if width != original_width:
                new_width = width
                new_height = int(width / aspect_ratio)
            else:
                new_height = height
                new_width = int(height * aspect_ratio)
        else:
            new_width = width
            new_height = height

    # Ensure minimum dimensions
    new_width = max(1, new_width)
    new_height = max(1, new_height)
    if new_width * new_height > MAX_OUTPUT_PIXELS:
        raise ValueError(f"Requested size {new_width}x{new_height} is too large")

    # Resize the image using high-quality resampling
    if (new_width, new_height) != (original_width, original_height):
        img = img.resize((new_width, new_height), PILImage.Resampling.LANCZOS)

    new_dimensions = f"{new_width}x{new_height}"

    # Handle transparency for JPG format
    if output_format.lower() in ["jpg", "jpeg"]:
        if img.mode in ("RGBA", "LA", "P"):
            # Create background
            if background_color == "white":
                bg_color = (255, 255, 255)
            elif background_color == "black":
                bg_color = (0, 0, 0)
            else:
                bg_color = (255, 255, 255)  # Default to white for JPG

            # Convert to RGB with background
            background = PILImage.new("RGB", img.size, bg_color)
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

    # Handle PNG with transparency
    elif output_format.lower() == "png":
        if img.mode not in ("RGBA", "RGB", "L", "LA"):
            img = img.convert("RGBA")

    # Handle WebP
    elif output_format.lower() == "webp":
        if img.mode == "P":
            img = img.convert("RGBA")

    # Save to bytes
    output_buffer = io.BytesIO()

    save_kwargs = {
        "format": "JPEG" if output_format.lower() in ["jpg", "jpeg"] else output_format.upper(),
        "quality": quality,
    }

    # Add DPI info
    save_kwargs["dpi"] = (dpi, dpi)

    # Format-specific options
    if output_format.lower() in ["jpg", "jpeg"]:
        save_kwargs["optimize"] = True
    elif output_format.lower() == "png":
        save_kwargs["optimize"] = True
    elif output_format.lower() == "webp":
        save_kwargs["method"] = 6  # Best compression

    img.save(output_buffer, **save_kwargs)
    output_bytes = output_buffer.getvalue()
    new_size = len(output_bytes)

    # Calculate reduction
    reduction_percent = ((original_size - new_size) / original_size) * 100 if original_size > 0 else 0

    # Generate new filename
    original_name = image_data.filename.rsplit(".", 1)[0] if "." in image_data.filename else image_data.filename
    new_filename = f"{original_name}_reduced.{output_format.lower()}"

    # Encode to data URL
    data_url = encode_to_data_url(output_bytes, output_format)

    return ProcessedImage(
        filename=new_filename,
        data_url=data_url,
        original_size=original_size,
        new_size=new_size,
        original_dimensions=original_dimensions,
        new_dimensions=new_dimensions,
        format=output_format.upper(),
        reduction_percent=round(reduction_percent, 2),
    )


# Plain def rather than async: resizing is CPU-bound, and FastAPI runs a def
# handler in its threadpool instead of stalling the worker's event loop.
@router.post("/process", response_model=ReduceResponse)
def reduce_images(
    request: ReduceRequest,
    current_user: CurrentUser,
):
    """Resize and convert images.

    Supports batch processing of multiple images.
    """
    if not request.images:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No images provided",
        )

    if len(request.images) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 50 images allowed per batch",
        )

    processed_images = []
    total_original = 0
    total_new = 0

    for image_data in request.images:
        try:
            result = process_single_image(
                image_data=image_data,
                resize_mode=request.resize_mode,
                width=request.width,
                height=request.height,
                maintain_aspect_ratio=request.maintain_aspect_ratio,
                output_format=request.output_format,
                quality=request.quality,
                dpi=request.dpi,
                background_color=request.background_color,
            )
            processed_images.append(result)
            total_original += result.original_size
            total_new += result.new_size
        except Exception:
            logger.warning(f"Image reduce failed for {image_data.filename}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"We could not process {image_data.filename}. Make sure it is a valid image file and try again.",
            )

    total_reduction = ((total_original - total_new) / total_original) * 100 if total_original > 0 else 0

    return ReduceResponse(
        images=processed_images,
        total_original_size=total_original,
        total_new_size=total_new,
        total_reduction_percent=round(total_reduction, 2),
    )


@router.post("/download-zip")
def download_as_zip(
    request: ReduceRequest,
    current_user: CurrentUser,
):
    """Process images and return as a ZIP file."""
    if not request.images:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No images provided",
        )

    if len(request.images) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 50 images allowed per batch",
        )

    # Process all images
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for image_data in request.images:
            try:
                result = process_single_image(
                    image_data=image_data,
                    resize_mode=request.resize_mode,
                    width=request.width,
                    height=request.height,
                    maintain_aspect_ratio=request.maintain_aspect_ratio,
                    output_format=request.output_format,
                    quality=request.quality,
                    dpi=request.dpi,
                    background_color=request.background_color,
                )

                # Decode the data URL back to bytes
                image_bytes, _ = decode_data_url(result.data_url)
                zip_file.writestr(result.filename, image_bytes)

            except Exception:
                logger.warning(f"Image reduce failed for {image_data.filename}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"We could not process {image_data.filename}. Make sure it is a valid image file and try again.",
                )

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=reduced_images_{uuid.uuid4().hex[:8]}.zip"
        },
    )
