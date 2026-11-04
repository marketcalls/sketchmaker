"""Request bodies of the Faceless Studio pipeline: series, projects, scripts and steps.
Character bodies live in app/schemas/faceless.py. Responses are documented in
app/routers/faceless.py."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.render.timeline import GradeLook
from app.schemas.faceless import VoiceSettings

Aspect = Literal["9:16", "16:9", "1:1", "4:5"]


class SeriesCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    logline: Optional[str] = Field(None, max_length=2000)
    template_id: Optional[str] = Field(None, max_length=60)
    style: Optional[str] = Field(None, max_length=60)
    tone: Optional[str] = Field(None, max_length=200)
    cast_ids: list[int] = Field(default_factory=list)
    world_notes: Optional[str] = Field(None, max_length=8000)
    rules: list[str] = Field(default_factory=list)


class SeriesUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    logline: Optional[str] = Field(None, max_length=2000)
    template_id: Optional[str] = Field(None, max_length=60)
    style: Optional[str] = Field(None, max_length=60)
    tone: Optional[str] = Field(None, max_length=200)
    cast_ids: Optional[list[int]] = None
    world_notes: Optional[str] = Field(None, max_length=8000)
    rules: Optional[list[str]] = None
    episode_memory: Optional[list[dict[str, Any]]] = None


class FactIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    source: str = Field("", max_length=1000)
    date: str = Field("", max_length=40)


class ProjectSettings(BaseModel):
    t2i_model: Optional[str] = None
    edit_model: Optional[str] = None
    still_resolution: Optional[Literal["1k", "2k"]] = None
    clip_resolution: Optional[Literal["480p", "768p", "1080p"]] = None
    clip_mode: Optional[Literal["image", "reference"]] = None
    render_resolution: Optional[Literal["1080p", "720p"]] = None
    # Captions: the active word's color and where the caption block sits
    # (render_job.build_timeline); None keeps the render defaults.
    caption_highlight: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    caption_position: Optional[Literal["lower", "middle", "upper"]] = None
    # Packaging choices kept with the project: the chosen thumbnail (its
    # index in project.thumbnails) and the ticked disclosure checklist items
    # ("platform:label" keys).
    selected_thumbnail: Optional[int] = Field(None, ge=0, le=20)
    # Ads: a My Assets logo or image (by id, checked against the owner at
    # render time) drawn on the end card; 0 removes it.
    ad_logo_asset_id: Optional[int] = Field(None, ge=0)
    # Colour grade of the render (services/faceless/grade.py): a house look,
    # its strength, and colour matching to approved environment plates.
    grade_look: Optional[GradeLook] = None
    grade_strength: Optional[float] = Field(None, ge=0, le=1)
    grade_match: Optional[bool] = None
    disclosure_checks: Optional[list[str]] = Field(None, max_length=30)

    @field_validator("disclosure_checks")
    @classmethod
    def _short_keys(cls, value):
        if value is None:
            return value
        if any(len(v) > 200 for v in value):
            raise ValueError("Each disclosure key must be at most 200 characters")
        return list(dict.fromkeys(value))


class ProjectCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    idea: Optional[str] = Field(None, max_length=8000)
    template_id: str = Field(..., max_length=60)
    series_id: Optional[int] = None
    aspect: Optional[Aspect] = None
    length_seconds: Optional[int] = Field(None, ge=15, le=900)
    language: str = Field("en", min_length=2, max_length=10)
    style: Optional[str] = Field(None, max_length=60)
    narrator_voice: Optional[str] = Field(None, max_length=60)
    voice_settings: Optional[VoiceSettings] = None
    caption_preset: Optional[str] = Field(None, max_length=30)
    music_mood: Optional[str] = Field(None, max_length=40)
    cast_ids: list[int] = Field(default_factory=list)
    facts: list[FactIn] = Field(default_factory=list, max_length=60)
    settings: Optional[ProjectSettings] = None


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    idea: Optional[str] = Field(None, max_length=8000)
    template_id: Optional[str] = Field(None, max_length=60)
    series_id: Optional[int] = None
    aspect: Optional[Aspect] = None
    length_seconds: Optional[int] = Field(None, ge=15, le=900)
    language: Optional[str] = Field(None, min_length=2, max_length=10)
    style: Optional[str] = Field(None, max_length=60)
    narrator_voice: Optional[str] = Field(None, max_length=60)
    voice_settings: Optional[VoiceSettings] = None
    caption_preset: Optional[str] = Field(None, max_length=30)
    music_mood: Optional[str] = Field(None, max_length=40)
    cast_ids: Optional[list[int]] = None
    facts: Optional[list[FactIn]] = Field(None, max_length=60)
    settings: Optional[ProjectSettings] = None


class ScriptDraftRequest(BaseModel):
    """Optional overrides for this draft; the project's fields are used otherwise.

    background forces a queued draft (long-form projects are always queued)."""

    idea: Optional[str] = Field(None, max_length=8000)
    background: bool = False
    idempotency_key: Optional[str] = Field(None, max_length=80)


class ScriptSave(BaseModel):
    script: dict[str, Any]


class SceneRevise(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=2000)


class StepRequest(BaseModel):
    scene_ids: Optional[list[str]] = Field(None, max_length=120)
    options: Optional[dict[str, Any]] = None
    idempotency_key: Optional[str] = Field(None, max_length=80)
    # The total of the quote the user confirmed. When given, the step is
    # refused (409 quote_changed, with the new quote) unless the fresh plan
    # costs exactly this, so what starts is always what was shown.
    expected_usd: Optional[float] = Field(None, ge=0, allow_inf_nan=False)


class QuoteRequest(BaseModel):
    step: str
    scene_ids: Optional[list[str]] = Field(None, max_length=120)
    options: Optional[dict[str, Any]] = None


class SheetRequest(BaseModel):
    options: Optional[dict[str, Any]] = None
    idempotency_key: Optional[str] = Field(None, max_length=80)
    expected_usd: Optional[float] = Field(None, ge=0, allow_inf_nan=False)


class PackageRequest(BaseModel):
    thumbnails: bool = False
    texts: Optional[list[str]] = Field(None, max_length=3)
    options: Optional[dict[str, Any]] = None
    idempotency_key: Optional[str] = Field(None, max_length=80)
    expected_usd: Optional[float] = Field(None, ge=0, allow_inf_nan=False)
