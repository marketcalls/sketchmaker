"""Request bodies for /api/faceless. Responses are documented in app/routers/faceless.py."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class VoiceSettings(BaseModel):
    stability: float = Field(0.5, ge=0, le=1)
    similarity_boost: float = Field(0.75, ge=0, le=1)


class ConsentIn(BaseModel):
    """The real person likeness attestation (GET /config returns the text)."""

    accepted: bool
    text_version: str = Field(..., max_length=40)
    relationship: Literal["self", "with_permission"]


class CharacterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    kind: Literal["fictional", "real_person"] = "fictional"
    role: Optional[str] = Field(None, max_length=120)
    personality: Optional[str] = Field(None, max_length=2000)
    notes: Optional[str] = Field(None, max_length=4000)
    style_notes: Optional[str] = Field(None, max_length=2000)
    species: Optional[str] = Field("human", max_length=60)
    catchphrase: Optional[str] = Field(None, max_length=200)
    voice_id: Optional[str] = Field(None, max_length=60)
    voice_settings: Optional[VoiceSettings] = None
    consent: Optional[ConsentIn] = None


class CharacterUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    role: Optional[str] = Field(None, max_length=120)
    personality: Optional[str] = Field(None, max_length=2000)
    notes: Optional[str] = Field(None, max_length=4000)
    style_notes: Optional[str] = Field(None, max_length=2000)
    species: Optional[str] = Field(None, max_length=60)
    catchphrase: Optional[str] = Field(None, max_length=200)
    voice_id: Optional[str] = Field(None, max_length=60)
    voice_settings: Optional[VoiceSettings] = None
    bible: Optional[dict[str, Any]] = None
    is_archived: Optional[bool] = None
    consent: Optional[ConsentIn] = None
    revoke_consent: Optional[bool] = None
