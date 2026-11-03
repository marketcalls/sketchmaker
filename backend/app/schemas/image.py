"""Image generation Pydantic schemas."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CameraSettings(BaseModel):
    """Camera settings for prompt enhancement."""

    angle: Optional[str] = Field(
        default=None,
        description="Camera angle: eye level, low angle, high angle, bird's eye, worm's eye, dutch angle, over-the-shoulder"
    )
    distance: Optional[str] = Field(
        default=None,
        description="Shot distance: extreme close-up, close-up, medium close-up, medium shot, medium full, full shot, wide shot, extreme wide"
    )
    lens: Optional[str] = Field(
        default=None,
        description="Lens type: 24mm wide, 35mm, 50mm standard, 85mm portrait, 135mm, macro, fisheye, tilt-shift"
    )


class AdvancedPromptSettings(BaseModel):
    """Advanced settings for AI prompt enhancement."""

    style: Optional[str] = Field(
        default=None,
        description="Artistic style: photorealistic, digital art, oil painting, watercolor, anime, 3D render, vector, sketch, cinematic"
    )
    color_palette: Optional[List[str]] = Field(
        default=None,
        max_length=5,
        description="Up to 5 colors for the palette, e.g. ['warm amber', 'deep teal', 'cream white']"
    )
    lighting: Optional[str] = Field(
        default=None,
        description="Lighting: golden hour, blue hour, studio, Rembrandt, split, rim light, backlit, soft diffused, dramatic, neon"
    )
    mood: Optional[str] = Field(
        default=None,
        description="Emotional atmosphere: serene, dramatic, mysterious, joyful, melancholic, energetic, peaceful, romantic, tense, dreamy"
    )
    composition: Optional[str] = Field(
        default=None,
        description="Composition: rule of thirds, centered, symmetrical, dynamic diagonal, golden ratio, leading lines, frame within frame"
    )
    camera: Optional[CameraSettings] = Field(
        default=None,
        description="Camera settings for photography-style images"
    )
    time_of_day: Optional[str] = Field(
        default=None,
        description="Time: dawn, sunrise, morning, noon, afternoon, golden hour, sunset, dusk, blue hour, night, midnight"
    )
    weather: Optional[str] = Field(
        default=None,
        description="Weather/atmosphere: clear, cloudy, overcast, foggy, misty, rainy, snowy, stormy, sunny, hazy"
    )
    quality: Optional[str] = Field(
        default=None,
        description="Quality level: standard, high detail, ultra detailed, 4K, 8K, masterpiece, professional, award-winning"
    )


class GeneratePromptRequest(BaseModel):
    """Schema for generating a prompt."""

    topic: str = Field(..., min_length=1, max_length=32000, description="The main subject or idea for the image")
    style: Optional[str] = Field(default=None, description="Quick style preset (optional)")
    # What the prompt will be rendered with, so it is written for that model and frame.
    model: Optional[str] = Field(default=None, max_length=200, description="Image model the prompt is for")
    aspect_ratio: Optional[str] = Field(default=None, max_length=10, description="Frame the image renders into, e.g. 9:16")
    lora: bool = Field(default=False, description="A LoRA is loaded (Z-Image)")
    # What the image is for (image_prompt_profiles.PURPOSES), the negative
    # prompt to rewrite as positive wording, and Directions: 2 to 4 prompts
    # along one named axis instead of one prompt repeated.
    purpose: Optional[str] = Field(default=None, max_length=40, description="Use for: a PURPOSES id")
    avoid: Optional[str] = Field(default=None, max_length=500, description="What to keep out of the image")
    directions: int = Field(default=0, ge=0, le=4, description="Number of prompts along one axis (0: one prompt)")
    advanced: Optional[AdvancedPromptSettings] = Field(
        default=None,
        description="Advanced settings for fine-tuned prompt control"
    )


class GeneratePromptResponse(BaseModel):
    """Schema for prompt generation response."""

    prompt: str
    enhanced: bool = True
    settings_applied: Optional[Dict[str, Any]] = None
    # Directions only: every prompt (the first is also `prompt`) and the axis
    prompts: Optional[List[str]] = None
    axis: Optional[str] = None
    # Checkable rubric lines for an opted-in quality check (counts, left and
    # right, quoted text, attributes the user stated); none with Directions
    checks: Optional[List[str]] = None


class ImageSize(BaseModel):
    """Schema for image dimensions."""

    width: int = Field(default=1024, ge=256, le=4096)
    height: int = Field(default=1024, ge=256, le=4096)


class GenerateImageRequest(BaseModel):
    """Schema for generating an image."""

    prompt: str = Field(..., min_length=1, max_length=32000)
    original_prompt: Optional[str] = None  # Original prompt before AI enhancement
    model: str = Field(default="fal-ai/flux/schnell")
    art_style: Optional[str] = None
    # Unified aspect ratio - maps to model-specific params in fal_client
    aspect_ratio: str = Field(default="16:9")
    # Resolution quality for models that support it
    resolution: str = Field(default="1k")  # 1k, 2k, 4k
    num_images: int = Field(default=1, ge=1, le=4)
    lora_url: Optional[str] = Field(default=None, max_length=500)
    lora_scale: float = Field(default=1.0, ge=0.0, le=2.0)
    # Additional metadata fields with validation ranges to prevent cost abuse
    guidance_scale: Optional[float] = Field(default=None, ge=0.0, le=20.0)  # 0-20 range for prompt adherence control
    inference_steps: Optional[int] = Field(default=None, ge=1, le=50)  # Configurable 1-50 range
    rendering: Optional[str] = Field(default="Default")
    seed: Optional[int] = None  # If None, random seed will be generated
    negative_prompt: Optional[str] = None
    # For backwards compatibility
    image_size: Optional[ImageSize] = None
    # Opt-in quality check (run once each image is stored) and its rubric
    # lines from Magic Prompt
    quality_check: bool = False
    check_lines: Optional[List[str]] = Field(default=None, max_length=6)


class ImageResponse(BaseModel):
    """Schema for image response."""

    id: int
    filename: str
    prompt: str
    magic_prompt: Optional[str] = None
    art_style: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    model: Optional[str] = None
    seed: Optional[int] = None
    rendering: Optional[str] = None
    aspect_ratio: Optional[str] = None
    guidance_scale: Optional[float] = None
    inference_steps: Optional[int] = None
    created_at: datetime
    url: str
    thumbnail_url: Optional[str] = None
    # The quality check, when one was asked for (quality_gate.view)
    quality: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_urls(cls, image) -> "ImageResponse":
        from app.services.quality_gate import view as quality_view

        # Calculate aspect ratio
        aspect_ratio = None
        if image.width and image.height:
            gcd = cls._gcd(image.width, image.height)
            w_ratio = image.width // gcd
            h_ratio = image.height // gcd
            # Simplify common ratios
            if (w_ratio, h_ratio) in [(16, 9), (9, 16), (4, 3), (3, 4), (1, 1), (3, 2), (2, 3)]:
                aspect_ratio = f"{w_ratio}:{h_ratio}"
            else:
                aspect_ratio = image.aspect_ratio or f"{image.width}x{image.height}"

        return cls(
            id=image.id,
            filename=image.filename,
            prompt=image.prompt,
            magic_prompt=image.magic_prompt,
            art_style=image.art_style,
            width=image.width,
            height=image.height,
            model=image.model,
            seed=image.seed,
            rendering=image.rendering,
            aspect_ratio=aspect_ratio,
            guidance_scale=image.guidance_scale,
            inference_steps=image.inference_steps,
            created_at=image.created_at,
            url=image.get_url(),  # Use original file extension
            thumbnail_url=image.get_url(),  # Use original file extension
            quality=quality_view(getattr(image, "quality", None)),
        )

    @staticmethod
    def _gcd(a: int, b: int) -> int:
        """Calculate greatest common divisor."""
        while b:
            a, b = b, a % b
        return a


class GalleryResponse(BaseModel):
    """Schema for gallery response."""

    images: List[ImageResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ExplainerRequest(BaseModel):
    """Schema for explainer generation."""

    topic: str = Field(..., min_length=1, max_length=500)
    content_type: str = Field(default="concept")  # concept, infographic, flowchart, etc.
    style: Optional[str] = None
    additional_instructions: Optional[str] = None


class MagixRequest(BaseModel):
    """Schema for Magix image editing."""

    prompt: str = Field(..., min_length=1, max_length=1000)
    mode: str = Field(default="enhance")  # enhance, upscale, edit
    strength: float = Field(default=0.7, ge=0.0, le=1.0)


class VirtualRequest(BaseModel):
    """Schema for virtual try-on generation with an EDIT_MODEL_CONFIG model."""

    person_image: str = Field(..., description="Base64 or URL of the person image")
    dress_image: str = Field(..., description="Base64 or URL of the dress/garment image")
    prompt: Optional[str] = Field(default=None, max_length=1000, description="Optional custom instructions")
    mode: str = Field(
        default="natural",
        description="Try-on style: natural, professional, glamour, outdoor_day, evening, urban, nature, party, athletic, romantic"
    )
    aspect_ratio: str = Field(
        default="16:9",
        description="Output aspect ratio: 16:9, 9:16, 1:1, 4:5, 3:4, 4:3"
    )
    use_dress_background: bool = Field(default=False, description="Use background from dress image")
    num_images: int = Field(default=1, ge=1, le=4)
    model: str = Field(default="google/nano-banana-2.1/edit", max_length=100, description="Edit model (see EDIT_MODEL_CONFIG)")
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    seed: Optional[int] = Field(default=None, ge=0, le=2147483647, description="Random seed for reproducibility")


class VirtualResponse(BaseModel):
    """Schema for virtual try-on response."""

    images: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    estimated_usd: float


# =============================================================================
# Async Generation Schemas
# =============================================================================

class GenerateJobSubmitResponse(BaseModel):
    """Response when submitting an async generation job."""

    job_id: str = Field(..., description="Unique job identifier for polling")
    status: str = Field(default="pending", description="Initial job status")
    message: str = Field(default="Job submitted successfully")


class GenerateJobStatusResponse(BaseModel):
    """Response for job status polling."""

    job_id: str
    status: str = Field(..., description="pending, in_progress, completed, failed")
    progress: int = Field(default=0, ge=0, le=100)
    logs: Optional[List[str]] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None


class GenerateJobResultResponse(BaseModel):
    """Response for completed job result."""

    job_id: str
    status: str
    images: List[ImageResponse]
    estimated_usd: float
    completed_at: Optional[datetime] = None
    # A sentence for people when the safety filter blocked some images
    notice: Optional[str] = None
