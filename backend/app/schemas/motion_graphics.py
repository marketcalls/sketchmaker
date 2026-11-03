"""Request bodies for /api/motion-graphics (responses are plain dicts built
by app/services/motion_graphics/views.py)."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Aspect = Literal["9:16", "4:5", "1:1", "16:9"]


class _In(BaseModel):
    model_config = ConfigDict(extra="ignore")


class VoiceSettings(_In):
    enabled: bool = False
    # elevenlabs (Eleven v4) or sarvam (Bulbul v4, Indian voices and languages).
    provider: Optional[Literal["elevenlabs", "sarvam"]] = None
    voice_id: Optional[str] = Field(default=None, max_length=64)
    stability: float = Field(default=0.5, ge=0, le=1)
    similarity_boost: float = Field(default=0.75, ge=0, le=1)
    pace: Optional[float] = Field(default=None, ge=0.5, le=2.0)  # Sarvam only


class MusicSettings(_In):
    enabled: bool = False
    mood: Optional[str] = Field(default=None, max_length=40)


class AudioSettings(_In):
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    music: MusicSettings = Field(default_factory=MusicSettings)


class ProjectCreate(_In):
    template_id: str = Field(max_length=40)
    style_id: Optional[str] = Field(default=None, max_length=40)
    aspect: Optional[Aspect] = None
    title: Optional[str] = Field(default=None, max_length=200)
    apply_brand: bool = True
    sample_content: bool = True


class ProjectUpdate(_In):
    title: Optional[str] = Field(default=None, max_length=200)
    style_id: Optional[str] = Field(default=None, max_length=40)
    aspect: Optional[Aspect] = None
    variants: Optional[list[Aspect]] = Field(default=None, max_length=3)
    audio: Optional[AudioSettings] = None
    apply_brand: Optional[bool] = None
    expected_version: Optional[int] = None


class SpecSave(_In):
    spec: dict[str, Any]
    expected_version: Optional[int] = None


class DraftRequest(_In):
    brief: str = Field(min_length=3, max_length=4000)
    template_id: Optional[str] = Field(default=None, max_length=40)
    style_id: Optional[str] = Field(default=None, max_length=40)
    aspect: Optional[Aspect] = None
    length_seconds: Optional[int] = Field(default=None, ge=5, le=600)
    data_csv: Optional[str] = Field(default=None, max_length=200_000)
    voiceover: bool = False


class PreviewRequest(_In):
    scene_id: Optional[str] = Field(default=None, max_length=24)
    t: Optional[float] = Field(default=None, ge=0, le=900, allow_inf_nan=False)
    at: Optional[float] = Field(default=None, ge=0, le=900, allow_inf_nan=False)  # seconds into the scene
    aspect: Optional[Aspect] = None
    scale: float = Field(default=0.5, ge=0.25, le=1.0, allow_inf_nan=False)
    safe_zone_overlay: bool = False
    spec: Optional[dict[str, Any]] = None  # unsaved edits, previewed without saving


class MotionPreviewRequest(_In):
    """A short silent animated preview: one scene, or the whole video when
    scene_id is empty (capped in length)."""
    scene_id: Optional[str] = Field(default=None, max_length=24)
    aspect: Optional[Aspect] = None
    spec: Optional[dict[str, Any]] = None  # unsaved edits, previewed without saving


class DataParse(_In):
    csv: str = Field(max_length=200_000)
    kind: Optional[Literal["race", "series", "tickers", "versus"]] = None


class JobRequest(_In):
    kind: Literal["audio", "render"]
    idempotency_key: Optional[str] = Field(default=None, max_length=80)


class BrandKitUpdate(_In):
    name: Optional[str] = Field(default=None, max_length=80)
    palette: Optional[dict[str, Optional[str]]] = None
    fonts: Optional[dict[str, Optional[str]]] = None
    intensity: Optional[Literal["calm", "standard", "punchy"]] = None
    use_brand_background: Optional[bool] = None
    auto_apply: Optional[bool] = None
