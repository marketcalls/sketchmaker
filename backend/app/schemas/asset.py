"""My Assets schemas."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


AssetKind = Literal["image", "logo", "video", "audio"]


class AssetResponse(BaseModel):
    id: int
    kind: AssetKind
    name: str
    url: str
    content_type: Optional[str] = None
    file_size_bytes: int
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    source: str = "upload"
    voice: Optional[str] = None
    voice_provider: Optional[str] = None
    text: Optional[str] = None
    created_at: datetime


class AssetListResponse(BaseModel):
    assets: list[AssetResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AssetRenameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class VoiceGenerateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    voice: str = Field(..., max_length=64)
    provider: Literal["elevenlabs", "sarvam"] = "elevenlabs"
    # ElevenLabs only.
    stability: Optional[float] = Field(default=None, ge=0, le=1)
    # Sarvam only: speaking speed.
    pace: Optional[float] = Field(default=None, ge=0.5, le=2.0)
    name: Optional[str] = Field(default=None, max_length=200)


class VoiceGenerateResponse(BaseModel):
    asset: AssetResponse
    estimated_usd: float


class VoiceLanguage(BaseModel):
    id: str
    code: str
    label: str


class VoiceOption(BaseModel):
    id: str
    label: str
    language: Optional[str] = None
    description: Optional[str] = None
    gender: Optional[Literal["female", "male", "neutral"]] = None


class VoiceSampleResponse(BaseModel):
    url: str


class VoiceProvider(BaseModel):
    id: Literal["elevenlabs", "sarvam"]
    label: str
    model: str
    description: str
    price_key: str
    max_characters: int
    default_voice: str
    default_language: Optional[str] = None
    languages: list[VoiceLanguage]
    voices: list[VoiceOption]


class VoiceCatalogResponse(BaseModel):
    providers: list[VoiceProvider]
