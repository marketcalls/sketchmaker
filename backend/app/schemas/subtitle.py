"""Subtitle generation Pydantic schemas."""

from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator


# Valid color names for FAL auto-subtitle API
VALID_COLORS = Literal[
    "white", "black", "red", "green", "blue", "yellow",
    "orange", "purple", "pink", "brown", "gray", "cyan", "magenta"
]


# =============================================================================
# Video Upload Schemas
# =============================================================================

class SubtitleUploadResponse(BaseModel):
    """Response when uploading a video for subtitles."""

    url: str = Field(..., description="URL of the uploaded video")
    filename: str
    duration_seconds: float = Field(..., description="Duration of the video in seconds")
    estimated_usd: float = Field(..., description="Estimated cost of subtitle generation, in USD")
    file_size_bytes: int
    message: str = Field(default="Video uploaded successfully")


# =============================================================================
# Subtitle Generation Schemas
# =============================================================================

class CreateSubtitleRequest(BaseModel):
    """Request to generate subtitles for a video."""

    video_url: str = Field(
        ...,
        description="URL of the video to add subtitles to"
    )
    font_color: str = Field(
        default="white",
        description="Subtitle text color (white, black, red, green, blue, yellow, orange, purple, pink, brown, gray, cyan, magenta)"
    )
    stroke_color: str = Field(
        default="black",
        description="Text stroke/outline color"
    )
    highlight_color: Optional[str] = Field(
        default=None,
        description="Word highlight animation color (optional)"
    )
    background_color: Optional[str] = Field(
        default=None,
        description="Subtitle background color (optional)"
    )
    position: str = Field(
        default="bottom",
        description="Subtitle position: 'top', 'center', 'bottom'"
    )
    font_size: int = Field(
        default=100,
        ge=20,
        le=200,
        description="Subtitle font size in pixels"
    )
    font_name: str = Field(
        default="Montserrat",
        description="Font family for subtitles"
    )
    font_weight: str = Field(
        default="bold",
        description="Font weight: 'normal' or 'bold'"
    )
    stroke_width: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Width of text stroke in pixels"
    )
    y_offset: int = Field(
        default=75,
        ge=0,
        le=200,
        description="Vertical offset from position in pixels"
    )
    words_per_subtitle: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of words per subtitle chunk"
    )
    enable_animation: bool = Field(
        default=True,
        description="Enable word-by-word highlight animation"
    )
    language: str = Field(
        default="en",
        description="Language code for transcription (en, es, fr, etc.)"
    )

    @field_validator("font_color", "stroke_color")
    @classmethod
    def validate_required_color(cls, v: str) -> str:
        valid = {"white", "black", "red", "green", "blue", "yellow",
                 "orange", "purple", "pink", "brown", "gray", "cyan", "magenta"}
        if v not in valid:
            raise ValueError(f"Color must be one of: {', '.join(sorted(valid))}")
        return v

    @field_validator("highlight_color", "background_color")
    @classmethod
    def validate_optional_color(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        valid = {"white", "black", "red", "green", "blue", "yellow",
                 "orange", "purple", "pink", "brown", "gray", "cyan", "magenta"}
        if v not in valid:
            raise ValueError(f"Color must be one of: {', '.join(sorted(valid))}")
        return v

    @field_validator("position")
    @classmethod
    def validate_position(cls, v: str) -> str:
        valid = {"top", "center", "bottom"}
        if v not in valid:
            raise ValueError(f"Position must be one of: {', '.join(valid)}")
        return v

    @field_validator("font_weight")
    @classmethod
    def validate_font_weight(cls, v: str) -> str:
        valid = {"normal", "bold"}
        if v not in valid:
            raise ValueError(f"Font weight must be one of: {', '.join(valid)}")
        return v


class SubtitleJobResponse(BaseModel):
    """Response when submitting a subtitle generation job."""

    job_id: str = Field(..., description="Unique job identifier for polling")
    status: str = Field(default="pending", description="Initial job status")
    message: str = Field(default="Subtitle generation job submitted successfully")
    estimated_usd: float = Field(..., description="Estimated cost of this job, in USD")


class SubtitleStatusResponse(BaseModel):
    """Response for subtitle job status polling."""

    job_id: str
    status: str = Field(..., description="pending, in_progress, processing, ready, completed, failed")
    progress: int = Field(default=0, ge=0, le=100)
    logs: Optional[List[str]] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None


class SubtitleVideoResponse(BaseModel):
    """Schema for subtitled video response."""

    id: int
    filename: str
    thumbnail_url: Optional[str] = None
    url: str
    video_type: str = "subtitle"
    transcript: Optional[str] = None  # The generated subtitle text
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[int] = None
    file_size_bytes: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_urls(cls, video) -> "SubtitleVideoResponse":
        """Create SubtitleVideoResponse from Video ORM object."""
        return cls(
            id=video.id,
            filename=video.filename,
            thumbnail_url=video.get_thumbnail_url(),
            url=video.get_url(),
            video_type=video.video_type or "subtitle",
            transcript=video.transcript,
            duration_seconds=video.duration_seconds,
            width=video.width,
            height=video.height,
            fps=video.fps,
            file_size_bytes=video.file_size_bytes,
            created_at=video.created_at,
        )


class SubtitleResultResponse(BaseModel):
    """Response for completed subtitle job result."""

    job_id: str
    status: str
    video: SubtitleVideoResponse
    estimated_usd: float
    transcript: str = Field(..., description="The full transcript/subtitle text")
    completed_at: Optional[datetime] = None


class SubtitleGalleryResponse(BaseModel):
    """Schema for subtitled videos gallery response."""

    videos: List[SubtitleVideoResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
