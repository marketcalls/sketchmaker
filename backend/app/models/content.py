"""Content models: images, videos and the fal job tables."""

from datetime import datetime
import os

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Float
from sqlalchemy.orm import relationship

from app.database import AUTOINCREMENT, Base


class Image(Base):
    """Generated image storage."""

    __tablename__ = "image"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    prompt = Column(Text, nullable=False)
    magic_prompt = Column(Text)  # Enhanced/magic prompt from AI
    art_style = Column(String(100))
    width = Column(Integer)
    height = Column(Integer)
    model = Column(String(100))  # AI model used (e.g., fal-ai/flux/schnell)
    seed = Column(Integer)  # Generation seed for reproducibility
    rendering = Column(String(50), default="Default")  # Rendering style
    aspect_ratio = Column(String(20))  # e.g., "16:9", "1:1"
    guidance_scale = Column(Integer)  # Guidance scale used
    inference_steps = Column(Integer)  # Number of inference steps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey("api_provider.id"))
    model_id = Column(Integer, ForeignKey("ai_model.id"))
    # Quality check (app/services/quality_gate.py): the request while it
    # waits ({"status": "pending", "request": {...}}), then the stored verdict.
    # NULL when the user did not ask for one.
    quality = Column(JSON(none_as_null=True))

    # Relationships
    user = relationship("User", back_populates="images")

    def get_url(self, format: str = None) -> str:
        """Relative URL of the stored image: /static/images/{user_id}/{filename}.
        ``format`` swaps the extension."""
        from app.services.storage_service import storage_service

        if format is None:
            return storage_service.get_public_url(self.filename, "images", user_id=self.user_id)
        base_filename = os.path.splitext(self.filename)[0]
        return storage_service.get_public_url(f"{base_filename}.{format}", "images", user_id=self.user_id)


class GenerationJob(Base):
    """Async image generation job tracking."""

    __tablename__ = "generation_job"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID
    request_id = Column(String(100), unique=True, index=True)  # FAL request ID
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)

    # Request params
    prompt = Column(Text, nullable=False)
    original_prompt = Column(Text)  # Before AI enhancement
    model = Column(String(100), nullable=False)
    art_style = Column(String(100))
    aspect_ratio = Column(String(20))
    resolution = Column(String(10))
    num_images = Column(Integer, default=1)
    guidance_scale = Column(Integer)
    inference_steps = Column(Integer)
    seed = Column(Integer)
    lora_url = Column(String(500))
    lora_scale = Column(Integer)
    # The opt-in quality check ({"lines": [...], "texts": [...]}), copied onto
    # each stored image as a pending request (app/services/quality_gate.py).
    quality_check = Column(JSON(none_as_null=True))

    # Job status
    status = Column(String(20), default="pending")  # pending, in_progress, completed, failed
    progress = Column(Integer, default=0)  # 0-100
    logs = Column(Text)
    error = Column(Text)

    # Result - stored as JSON with image details
    result = Column(JSON)

    # What the job is expected to cost, from the built-in price table.
    estimated_usd = Column(Float, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Relationships
    user = relationship("User", backref="generation_jobs")


class Video(Base):
    """Generated video storage."""

    __tablename__ = "video"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    thumbnail_filename = Column(String(255))  # First frame or generated thumbnail
    source_image_url = Column(Text)  # URL of source image used
    motion_reference_url = Column(Text)  # URL of motion reference video
    character_orientation = Column(String(20), default="video")  # "video" or "image"
    prompt = Column(Text)  # Optional prompt used
    original_prompt = Column(Text)  # Original prompt before LLM enhancement
    transcript = Column(Text)  # For subtitled videos - the generated text
    video_type = Column(String(20), default="motion")  # "motion", "story", "subtitle", "lipsync"
    has_subtitles = Column(Integer, default=0)  # 0=no, 1=yes
    duration_seconds = Column(Float)  # Video duration
    width = Column(Integer)
    height = Column(Integer)
    fps = Column(Integer, default=30)
    model = Column(String(100), default="fal-ai/kling-video/v2.6/standard/motion-control")
    seed = Column(Integer)
    file_size_bytes = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)

    # Relationships
    user = relationship("User", back_populates="videos")

    def get_url(self) -> str:
        """Relative URL of the stored video. /static serves Range requests."""
        from app.services.storage_service import storage_service

        return storage_service.get_public_url(self.filename, "videos", user_id=self.user_id)

    def get_direct_url(self) -> str:
        """Direct file URL, the same as get_url."""
        from app.services.storage_service import storage_service
        return storage_service.get_public_url(self.filename, "videos", user_id=self.user_id)

    def get_thumbnail_url(self) -> str:
        """Relative URL of the thumbnail, or None."""
        from app.services.storage_service import storage_service

        if self.thumbnail_filename:
            return storage_service.get_public_url(self.thumbnail_filename, "thumbnails", user_id=self.user_id)
        return None


class VideoGenerationJob(Base):
    """Async video generation job tracking."""

    __tablename__ = "video_generation_job"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID
    request_id = Column(String(100), unique=True, index=True)  # FAL request ID
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)

    # Request params
    source_image_url = Column(Text, nullable=False)
    motion_reference_url = Column(Text, nullable=False)
    # Kling V3 face lock image, when one was sent (My Assets refuses to delete it meanwhile).
    face_image_url = Column(Text, nullable=True)
    # Model options beyond the Kling columns. H3 Max Recast: {"tier",
    # "resolution", "reference_image_urls", "enhance_realism"}; "tier" selects the
    # price (pricing.RECAST_KEYS).
    options = Column(JSON, nullable=True)
    character_orientation = Column(String(20), default="video")
    prompt = Column(Text)
    # The fal endpoint the job was submitted to (fal_client.MOTION_CONTROL_TIERS),
    # so it is polled and priced on that tier.
    model = Column(String(100), nullable=True)

    # Job status
    status = Column(String(20), default="pending")  # pending, in_progress, completed, failed
    progress = Column(Integer, default=0)  # 0-100
    logs = Column(Text)
    error = Column(Text)

    # Result - stored as JSON with video details
    result = Column(JSON)

    # What the job is expected to cost, from the built-in price table.
    estimated_usd = Column(Float, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Relationships
    user = relationship("User", backref="video_generation_jobs")


class StoryGenerationJob(Base):
    """Async story (text-to-video) generation job tracking."""

    __tablename__ = "story_generation_job"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID
    request_id = Column(String(100), unique=True, index=True)  # FAL request ID
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)

    # Input parameters
    prompt = Column(Text, nullable=False)
    original_prompt = Column(Text)  # Before LLM enhancement
    enhanced_prompt = Column(Text)  # After LLM enhancement
    mode = Column(String(30), default="text-to-video")  # text-to-video, image-to-video, reference-to-video
    model = Column(String(100))  # FAL endpoint the job was submitted to
    image_url = Column(Text)  # Source image URL for image-to-video mode
    duration_seconds = Column(Integer, default=0)  # 0 = auto, 4-15 = seconds
    resolution = Column(String(10), default="720p")  # 480p or 720p
    aspect_ratio = Column(String(10), default="auto")  # auto, 21:9, 16:9, 4:3, 1:1, 3:4, 9:16

    # Generation options
    seed = Column(Integer)  # Generation seed for reproducibility

    # Subtitle options - matches FAL auto-subtitle API
    add_subtitles = Column(Integer, default=0)  # 0=no, 1=yes
    subtitle_font_color = Column(String(20), default="white")
    subtitle_stroke_color = Column(String(20), default="black")
    subtitle_highlight_color = Column(String(20), default="purple")
    subtitle_background_color = Column(String(20), default="none")
    subtitle_position = Column(String(20), default="bottom")
    subtitle_font_size = Column(Integer, default=100)
    subtitle_font_name = Column(String(50), default="Montserrat")
    subtitle_font_weight = Column(String(20), default="bold")
    subtitle_stroke_width = Column(Integer, default=3)
    subtitle_y_offset = Column(Integer, default=75)
    subtitle_words_per_subtitle = Column(Integer, default=3)
    subtitle_enable_animation = Column(Integer, default=1)  # 0=no, 1=yes
    subtitle_language = Column(String(10), default="en")

    # Job status
    status = Column(String(20), default="pending")  # pending, in_progress, processing, completed, failed
    progress = Column(Integer, default=0)  # 0-100
    logs = Column(Text)
    error = Column(Text)

    # What the job is expected to cost, from the built-in price table.
    estimated_usd = Column(Float, default=0)

    # Result - stored as JSON with video details
    result = Column(JSON)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Relationships
    user = relationship("User", backref="story_generation_jobs")


class LipSyncJob(Base):
    """Async lip sync (portrait image plus audio to video) job tracking.

    A table of its own rather than a mode of VideoGenerationJob: that table
    requires a motion reference and every path reading it (status, result,
    retry, scheduler) polls the Motion Control endpoint.
    """

    __tablename__ = "lipsync_job"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID
    request_id = Column(String(100), unique=True, index=True)  # FAL request ID
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)

    # Input
    model = Column(String(100))  # FAL endpoint the job was submitted to
    image_url = Column(Text, nullable=False)
    audio_url = Column(Text, nullable=False)
    audio_duration_seconds = Column(Float)  # measured at upload (ffprobe)
    resolution = Column(String(10), default="768p")  # 480p, 768p, 1080p, 2k
    enable_transcription = Column(Integer, default=0)  # 0=no, 1=yes

    # Job status
    status = Column(String(20), default="pending")  # pending, in_progress, processing, completed, failed
    progress = Column(Integer, default=0)  # 0-100
    logs = Column(Text)
    error = Column(Text)

    # Result - stored as JSON with video details
    result = Column(JSON)

    # What the job is expected to cost, from the built-in price table.
    estimated_usd = Column(Float, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Relationships
    user = relationship("User", backref="lipsync_jobs")


class SubtitleJob(Base):
    """Async subtitle generation job tracking."""

    __tablename__ = "subtitle_job"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID
    request_id = Column(String(100), unique=True, index=True)  # FAL request ID
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)

    # Input
    source_video_url = Column(Text, nullable=False)
    video_duration_seconds = Column(Float)

    # Subtitle options
    subtitle_color = Column(String(20), default="#FFFFFF")
    subtitle_bg_color = Column(String(20), default="#000000")
    subtitle_position = Column(String(20), default="bottom")
    subtitle_font_size = Column(Integer, default=24)
    font_family = Column(String(50), default="Arial")

    # Job status
    status = Column(String(20), default="pending")  # pending, in_progress, processing, completed, failed
    progress = Column(Integer, default=0)  # 0-100
    logs = Column(Text)
    error = Column(Text)

    # What the job is expected to cost, from the built-in price table.
    estimated_usd = Column(Float, default=0)

    # Result - stored as JSON with video details and transcript
    result = Column(JSON)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Relationships
    user = relationship("User", backref="subtitle_jobs")
