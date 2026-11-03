"""Story (text / image / reference / keyframes to video) generation Pydantic schemas."""

import re
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator


# Video model families for Stories. Durations, resolutions and aspect ratios
# depend on the family and mode, so they are validated against
# STORY_VIDEO_MODELS in app/clients/fal_client.py (400 on a mismatch).
VALID_VIDEO_MODELS = ("h3-max", "seedance-2.5", "kling-v4", "flux-3-max", "omni-flash")

# Valid color names for subtitles (FAL auto-subtitle API)
VALID_SUBTITLE_COLORS = Literal[
    "white", "black", "red", "green", "blue", "yellow",
    "orange", "purple", "pink", "brown", "gray", "cyan", "magenta"
]


# =============================================================================
# Prompt Enhancement Schemas
# =============================================================================

class EnhancePromptRequest(BaseModel):
    """Request to enhance a story prompt using LLM."""

    # As long as the clip maker's prompt box (STORY_PROMPT_MAX_CHARS in
    # frontend api/story.ts), so any prompt it holds can be enhanced.
    topic: str = Field(
        ...,
        min_length=1,
        max_length=2500,
        description="The topic/idea for the video story"
    )
    style: Optional[str] = Field(
        default=None,
        description="Optional style hint (e.g., 'cinematic', 'meme', 'vlog', 'advertisement')"
    )
    content_type: Optional[str] = Field(
        default=None,
        description="Content type: 'reel', 'story', 'ad', 'meme', 'vlog', 'narration'"
    )
    video_model: Optional[str] = Field(
        default=None,
        description="Video model family the prompt is for: 'h3-max' (default), 'seedance-2.5', 'kling-v4', 'flux-3-max', 'omni-flash'"
    )
    # The clip the prompt is for: the enhancer writes the whole shot for
    # text-to-video, only motion and camera over supplied frames, and binds
    # reference tags to what each supplies.
    mode: Optional[Literal["text-to-video", "image-to-video", "reference-to-video", "keyframes"]] = Field(
        default=None,
        description="Generation mode the prompt is for (default text-to-video)"
    )
    duration: Optional[str] = Field(
        default=None,
        max_length=8,
        description="Clip length in seconds as a string, or 'auto'"
    )
    aspect_ratio: Optional[str] = Field(default=None, max_length=12)
    frames: Optional[Literal["start", "end", "both"]] = Field(
        default=None,
        description="image-to-video: which frames were supplied"
    )
    reference_tags: Optional[List[str]] = Field(
        default=None,
        max_length=30,
        description="reference-to-video: how the prompt names each upload, in order (e.g. 'Image 1', '@Video1')"
    )
    generate_audio: Optional[bool] = Field(
        default=None,
        description="Whether the clip will have generated sound (families with an audio switch)"
    )

    @field_validator("reference_tags")
    @classmethod
    def check_reference_tags(cls, v):
        if v is None:
            return v
        pattern = re.compile(r"^[@<]?[A-Za-z]{1,10}[ _]?(REF_)?\d{1,2}>?$")
        for tag in v:
            if not isinstance(tag, str) or not pattern.match(tag):
                raise ValueError("Reference names must look like Image 1, @Image1 or <IMAGE_REF_0>")
        return v


class EnhancePromptResponse(BaseModel):
    """Response with original and enhanced prompts."""

    original_prompt: str
    enhanced_prompt: str
    estimated_usd: float = 0.0


# =============================================================================
# Story Generation Schemas
# =============================================================================

class StoryKeyframe(BaseModel):
    """One keyframe image pinned to a time in the video (FLUX 3 Max keyframes mode)."""

    image_url: str = Field(..., min_length=1, description="Hosted keyframe image URL")
    time_seconds: Optional[float] = Field(
        default=None,
        ge=0,
        description="Where the keyframe sits in the video, in seconds. The first keyframe defaults to 0."
    )


class CreateStoryRequest(BaseModel):
    """Request to generate a story video (MiniMax H3 Max by default, Seedance 2.5, Kling v4, FLUX 3 Max or Gemini Omni Flash 1.1)."""

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="The prompt for video generation. Use @Image1, @Video1, @Audio1 to reference inputs in reference mode."
    )
    original_prompt: Optional[str] = Field(
        default=None,
        description="Original prompt before LLM enhancement"
    )
    video_model: str = Field(
        default="h3-max",
        description="Video model family: 'h3-max' (default), 'seedance-2.5', 'kling-v4', 'flux-3-max', 'omni-flash'"
    )
    mode: str = Field(
        default="text-to-video",
        description="Generation mode: 'text-to-video', 'image-to-video', and "
                    "'reference-to-video' (H3 Max, Seedance, Kling, Omni Flash) or 'keyframes' (FLUX 3 Max)"
    )

    # Image-to-video fields
    image_url: Optional[str] = Field(
        default=None,
        description="Start image URL for image-to-video mode (Kling v4 also takes it as an optional first frame in reference mode)"
    )
    end_image_url: Optional[str] = Field(
        default=None,
        description="End image URL for image-to-video mode (optional last frame; H3 Max accepts it without a start image)"
    )
    target_audio_url: Optional[str] = Field(
        default=None,
        description="H3 Max text and image modes: hosted audio (at least 2 s, max 15 MB) that becomes the clip's soundtrack"
    )

    # Reference-to-video fields
    image_urls: Optional[List[str]] = Field(
        default=None,
        description="Reference image URLs for reference-to-video mode (H3 Max and Seedance up to 9, Kling and Omni Flash up to 10)"
    )
    video_urls: Optional[List[str]] = Field(
        default=None,
        description="Reference video URLs for reference-to-video mode (H3 Max, Seedance and Omni Flash up to 3, Kling up to 5)"
    )
    audio_urls: Optional[List[str]] = Field(
        default=None,
        description="Reference audio URLs (up to 3) for H3 Max and Seedance reference-to-video mode"
    )

    # Keyframes fields (FLUX 3 Max)
    keyframes: Optional[List[StoryKeyframe]] = Field(
        default=None,
        description="Keyframe images with their times (1 to 10) for keyframes mode"
    )

    # Common settings. Left out, each family uses its own default (H3 Max:
    # 5 s, 768p, 16:9; Seedance: 'auto', '720p', 'auto').
    duration: Optional[str] = Field(
        default=None,
        description="Video duration in seconds as a string. H3 Max: '2'-'15'; Seedance: 'auto' or '4'-'15'; "
                    "Kling v4: '3'-'30'; FLUX 3 Max: '5'-'20'; Omni Flash: '3'-'10'"
    )
    resolution: Optional[str] = Field(
        default=None,
        description="Video resolution. H3 Max: '480p', '768p' or '1080p'; Seedance: '480p' or '720p'; Kling v4 and FLUX 3 Max: '720p' or '1080p'; Omni Flash: '360p', '720p', '1080p' or '4k'"
    )
    aspect_ratio: Optional[str] = Field(
        default=None,
        description="Aspect ratio; the accepted values depend on the model and mode"
    )
    generate_audio: bool = Field(
        default=True,
        description="Generate synchronized audio including sound effects, ambient sounds, and lip-synced speech"
    )
    seed: Optional[int] = Field(
        default=None,
        ge=0,
        le=2147483647,
        description="Seed for families that take one (H3 Max, FLUX 3 Max): a final render reuses its preview's seed. "
                    "Left out, a random seed is used."
    )

    # Subtitle settings (for optional second stage) - matches FAL auto-subtitle API
    add_subtitles: bool = Field(
        default=False,
        description="Whether to add subtitles after video generation"
    )
    subtitle_font_color: str = Field(
        default="white",
        description="Subtitle text color name"
    )
    subtitle_stroke_color: str = Field(
        default="black",
        description="Subtitle stroke/outline color name"
    )
    subtitle_highlight_color: str = Field(
        default="purple",
        description="Subtitle word highlight color (karaoke-style)"
    )
    subtitle_background_color: str = Field(
        default="none",
        description="Background color behind text ('none' for transparent)"
    )
    subtitle_position: str = Field(
        default="bottom",
        description="Subtitle position: 'top', 'center', 'bottom'"
    )
    subtitle_font_size: int = Field(
        default=100,
        ge=20,
        le=150,
        description="Subtitle font size in pixels"
    )
    subtitle_font_name: str = Field(
        default="Montserrat",
        description="Subtitle font family"
    )
    subtitle_font_weight: str = Field(
        default="bold",
        description="Font weight: 'normal', 'bold', 'black'"
    )
    subtitle_stroke_width: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Text stroke width in pixels"
    )
    subtitle_y_offset: int = Field(
        default=75,
        ge=-200,
        le=200,
        description="Vertical offset in pixels"
    )
    subtitle_words_per_subtitle: int = Field(
        default=3,
        ge=1,
        le=12,
        description="Words per subtitle segment"
    )
    subtitle_enable_animation: bool = Field(
        default=True,
        description="Enable animation effects for subtitles"
    )
    subtitle_language: str = Field(
        default="en",
        description="Language code for transcription"
    )

    @field_validator("duration", mode="before")
    @classmethod
    def coerce_duration(cls, v):
        # Accept 5 as well as "5"; the per-family check happens in the router.
        if isinstance(v, int) and not isinstance(v, bool):
            return str(v)
        return v

    @field_validator("subtitle_font_color", "subtitle_stroke_color")
    @classmethod
    def validate_subtitle_color(cls, v: str) -> str:
        valid = {"white", "black", "red", "green", "blue", "yellow",
                 "orange", "purple", "pink", "brown", "gray", "cyan", "magenta"}
        if v not in valid:
            raise ValueError(f"Color must be one of: {', '.join(sorted(valid))}")
        return v

    @field_validator("subtitle_highlight_color")
    @classmethod
    def validate_subtitle_highlight_color(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        valid = {"white", "black", "red", "green", "blue", "yellow",
                 "orange", "purple", "pink", "brown", "gray", "cyan", "magenta"}
        if v not in valid:
            raise ValueError(f"Color must be one of: {', '.join(sorted(valid))}")
        return v


class StoryJobResponse(BaseModel):
    """Response when submitting a story generation job."""

    job_id: str = Field(..., description="Unique job identifier for polling")
    status: str = Field(default="pending", description="Initial job status")
    message: str = Field(default="Story generation job submitted successfully")


class StoryStatusResponse(BaseModel):
    """Response for story job status polling."""

    job_id: str
    status: str = Field(..., description="pending, in_progress, processing, ready, completed, failed")
    progress: int = Field(default=0, ge=0, le=100)
    logs: Optional[List[str]] = None
    error: Optional[str] = None
    # Stable code for a known kind of failure: "content_filter" when the
    # provider's content filter blocked the clip (fal_client.job_error_code).
    error_code: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None


class StoryVideoResponse(BaseModel):
    """Schema for story video response."""

    id: int
    filename: str
    thumbnail_url: Optional[str] = None
    url: str
    prompt: str
    original_prompt: Optional[str] = None
    video_type: str = "story"
    has_subtitles: int = 0
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
    def from_orm_with_urls(cls, video) -> "StoryVideoResponse":
        """Create StoryVideoResponse from Video ORM object."""
        return cls(
            id=video.id,
            filename=video.filename,
            thumbnail_url=video.get_thumbnail_url(),
            url=video.get_url(),
            prompt=video.prompt or "",
            original_prompt=video.original_prompt,
            video_type=video.video_type or "story",
            has_subtitles=video.has_subtitles or 0,
            duration_seconds=video.duration_seconds,
            width=video.width,
            height=video.height,
            fps=video.fps,
            model=video.model,
            seed=video.seed,
            file_size_bytes=video.file_size_bytes,
            created_at=video.created_at,
        )


class StoryResultResponse(BaseModel):
    """Response for completed story job result."""

    job_id: str
    status: str
    video: StoryVideoResponse
    estimated_usd: float
    completed_at: Optional[datetime] = None


class StoryGalleryResponse(BaseModel):
    """Schema for story gallery response."""

    videos: List[StoryVideoResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
