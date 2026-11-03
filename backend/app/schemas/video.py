"""Video generation Pydantic schemas for motion control."""

from datetime import datetime
from typing import Literal, Optional, List
from pydantic import BaseModel, Field


class VideoGenerateRequest(BaseModel):
    """Schema for video generation with motion control."""

    source_image: str = Field(
        ...,
        description="Base64 data URL or URL of the source image to animate"
    )
    motion_reference: Optional[str] = Field(
        default=None,
        description="URL of the motion reference video (must be a hosted URL, not base64)"
    )
    motion_reference_asset_id: Optional[int] = Field(
        default=None,
        description="A video from My Assets, instead of motion_reference",
    )
    character_orientation: str = Field(
        default="video",
        description=(
            "'video' matches the reference video (complex full-body motion, up to 30 s); "
            "'image' matches the source image (camera-movement-led shots, up to 10 s)"
        ),
    )
    model_tier: Literal["v3-standard", "v3-pro", "v2.6"] = Field(
        default="v3-standard",
        description="Kling tier: 'v3-standard' (default), 'v3-pro' (highest quality) or 'v2.6' (budget)",
    )
    prompt: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Optional scene description. With a face image, @Element1 refers to the face.",
    )
    keep_original_sound: bool = Field(
        default=True,
        description="Carry the reference video's speech, singing or ambient sound into the output",
    )
    face_image_url: Optional[str] = Field(
        default=None,
        description=(
            "Optional face for identity preservation, uploaded with /video/upload-face. "
            "Kling V3 tiers with character_orientation 'video' only."
        ),
    )
    face_asset_id: Optional[int] = Field(
        default=None,
        description="A face image from My Assets, instead of face_image_url",
    )


class RecastReference(BaseModel):
    """One person's photo: uploaded with /video/upload-face, or from My Assets."""

    image_url: Optional[str] = Field(default=None, max_length=2048)
    asset_id: Optional[int] = None


class RecastGenerateRequest(BaseModel):
    """Multi-character motion transfer (MiniMax H3 Max Recast): the people in
    the source video are replaced by the reference photos, left to right
    unless the prompt says otherwise (#Image1 is the first photo)."""

    video_url: Optional[str] = Field(default=None, max_length=2048, description="URL returned by /video/upload")
    video_asset_id: Optional[int] = Field(default=None, description="A video from My Assets, instead of video_url")
    references: List[RecastReference] = Field(..., min_length=1, max_length=4)
    resolution: Literal["768p", "1080p"] = "1080p"
    prompt: Optional[str] = Field(default=None, max_length=2000)
    enhance_realism: bool = True


class VideoFaceUploadResponse(BaseModel):
    """Response when uploading a face image for Motion Control face lock."""

    url: str
    filename: str
    file_size_bytes: int
    width: int
    height: int
    message: str = Field(default="Face image uploaded successfully")


class VideoResponse(BaseModel):
    """Schema for video response."""

    id: int
    filename: str
    thumbnail_url: Optional[str] = None
    url: str
    source_image_url: Optional[str] = None
    motion_reference_url: Optional[str] = None
    character_orientation: Optional[str] = None
    prompt: Optional[str] = None
    video_type: Optional[str] = None  # motion, story, subtitle, lipsync
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[int] = None
    model: Optional[str] = None
    seed: Optional[int] = None
    file_size_bytes: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_urls(cls, video) -> "VideoResponse":
        """Create VideoResponse from Video ORM object."""
        return cls(
            id=video.id,
            filename=video.filename,
            thumbnail_url=video.get_thumbnail_url(),
            url=video.get_url(),
            source_image_url=video.source_image_url,
            motion_reference_url=video.motion_reference_url,
            character_orientation=video.character_orientation,
            prompt=video.prompt,
            video_type=video.video_type,
            duration_seconds=video.duration_seconds,
            width=video.width,
            height=video.height,
            fps=video.fps,
            model=video.model,
            seed=video.seed,
            file_size_bytes=video.file_size_bytes,
            created_at=video.created_at,
        )


# =============================================================================
# Async Video Generation Schemas
# =============================================================================

class VideoJobSubmitResponse(BaseModel):
    """Response when submitting a video generation job."""

    job_id: str = Field(..., description="Unique job identifier for polling")
    status: str = Field(default="pending", description="Initial job status")
    message: str = Field(default="Video generation job submitted successfully")


class VideoJobStatusResponse(BaseModel):
    """Response for video job status polling."""

    job_id: str
    status: str = Field(..., description="pending, in_progress, completed, failed")
    progress: int = Field(default=0, ge=0, le=100)
    logs: Optional[List[str]] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None


class VideoJobResultResponse(BaseModel):
    """Response for completed video job result."""

    job_id: str
    status: str
    video: VideoResponse
    estimated_usd: float
    completed_at: Optional[datetime] = None


# =============================================================================
# Video Gallery Schemas
# =============================================================================

class VideoGalleryResponse(BaseModel):
    """Schema for video gallery response."""

    videos: List[VideoResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class VideoUploadResponse(BaseModel):
    """Response when uploading a motion reference video."""

    url: str = Field(..., description="URL of the uploaded video")
    filename: str
    file_size_bytes: int
    duration_seconds: Optional[float] = Field(
        default=None,
        description="Measured length in seconds, or null if it could not be read",
    )
    message: str = Field(default="Video uploaded successfully")
