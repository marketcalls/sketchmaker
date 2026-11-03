"""Lip Sync (portrait image plus audio to video) schemas."""

from typing import Optional
from pydantic import BaseModel, Field


class LipSyncGenerateRequest(BaseModel):
    """Submit a lip sync job. The portrait and the audio each come from this
    user's uploads on the page (the URL) or from My Assets (the asset id)."""

    image_url: Optional[str] = Field(default=None, max_length=2048, description="URL returned by /lip-sync/upload-image")
    audio_url: Optional[str] = Field(default=None, max_length=2048, description="URL returned by /lip-sync/upload-audio")
    image_asset_id: Optional[int] = Field(default=None, description="An image from My Assets, instead of image_url")
    audio_asset_id: Optional[int] = Field(default=None, description="Audio from My Assets, instead of audio_url")
    resolution: str = Field(default="768p", description="480p, 768p, 1080p or 2k")
    enable_transcription: bool = Field(
        default=False,
        description="Transcribe the audio to guide the lip synchronization",
    )
    face_check: bool = Field(
        default=False,
        description="Check the portrait for one large, frontal, unoccluded face first (one vision "
                    "call); a failed check refuses the lip sync",
    )


class LipSyncImageUploadResponse(BaseModel):
    url: str
    filename: str
    file_size_bytes: int
    width: int
    height: int
    aspect_ratio: float = Field(..., description="width / height")
    message: str = "Image uploaded successfully"


class LipSyncAudioUploadResponse(BaseModel):
    url: str
    filename: str
    file_size_bytes: int
    duration_seconds: float = Field(..., description="Length measured by the server")
    billable_seconds: int = Field(..., description="Whole seconds the video is priced on")
    message: str = "Audio uploaded successfully"


class LipSyncJobSubmitResponse(BaseModel):
    job_id: str
    status: str = "pending"
    estimated_usd: float
    reserved_seconds: int
    message: str = "Lip sync job submitted"
    # The face check's verdict when one was asked for (quality_gate.view)
    face_check: Optional[dict] = None
