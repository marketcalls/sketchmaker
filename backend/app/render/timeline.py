"""Timeline model for the shared render engine.

This is the contract between the render engine and its callers (/faceless,
/motion-graphics). See docs/STUDIO_ARCHITECTURE.md section 1.

Conventions
-----------
* All times are seconds (floats). Frames are derived from ``fps`` (default 30)
  and every start and end is rounded to the nearest frame.
* Sizes and offsets in styles (``size``, ``x``, ``y``, ``max_width``, ``width``,
  ``stroke`` and so on) are in baseline pixels for a 1080 px wide frame and are
  scaled by ``width / 1080`` at render time. A ``max_width`` or ``width`` of
  1.0 or less is read as a fraction of the usable (safe area) width instead.
* Colors are CSS style hex strings: ``#RGB``, ``#RRGGBB`` or ``#RRGGBBAA``,
  or ``rgba(r,g,b,a)``.
* Every source is a local file path. The engine never fetches URLs.

Fields documented in the architecture doc are kept with their exact names.
Everything else here is an optional addition with a safe default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, Optional, TypedDict, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Shared literals
# ---------------------------------------------------------------------------

EasingName = Literal["linear", "ease_out", "ease_in_out", "bezier_out"]

AnimType = Literal[
    "none",
    "fade",
    "slide_up",
    "slide_down",
    "slide_left",
    "slide_right",
    "scale_in",
    "pop",
    "typewriter",
    "word_pop",
    "mask_reveal",
]

Anchor = Literal[
    "top",
    "center",
    "bottom",
    "top_left",
    "top_right",
    "bottom_left",
    "bottom_right",
    "left",
    "right",
]

Align = Literal["left", "center", "right"]

#: 22 frames at 30 fps, the crossfade length of the story-telling grammar.
DEFAULT_TRANSITION = 22 / 30


class _Model(BaseModel):
    # Unknown keys are ignored so older stored timelines keep loading.
    model_config = ConfigDict(extra="ignore")


# ---------------------------------------------------------------------------
# Animation and style
# ---------------------------------------------------------------------------


class Anim(_Model):
    """An enter or exit animation.

    For ``enter`` the animation starts ``delay`` seconds after the overlay
    starts. For ``exit`` it finishes ``delay`` seconds before the overlay ends
    (so ``delay`` there is a hold at the end, invisible).

    ``word_pop`` and ``typewriter`` reveal text overlays word by word or
    character by character; ``stagger`` is the time between units (default:
    the units are spread across ``duration``). On kinds without text they
    fall back to a fade. ``mask_reveal`` wipes the element in from the left.
    """

    type: AnimType = "fade"
    duration: float = Field(default=0.5, ge=0)
    easing: EasingName = "bezier_out"
    # Additions
    delay: float = Field(default=0.0, ge=0)
    distance: Optional[float] = None  # slide distance in baseline px (default 40)
    stagger: Optional[float] = Field(default=None, ge=0)


class TextStyle(_Model):
    """Style for an overlay. Every field is optional; ``None`` means the
    kind's default (which follows the story-telling grammar)."""

    font: Optional[str] = None  # family name, see app.render.fonts.FAMILIES
    weight: Optional[int] = None  # 100 to 900
    size: Optional[float] = None  # baseline px
    color: Optional[str] = None
    accent: Optional[str] = None  # falls back to Timeline.accent
    stroke: Optional[float] = None  # outline width in baseline px, outside the glyph
    shadow: Optional[bool] = None
    align: Optional[Align] = None
    max_width: Optional[float] = None  # baseline px, or a fraction when <= 1
    # Additions
    stroke_color: str = "#000000"
    shadow_color: str = "rgba(0,0,0,0.75)"
    line_height: Optional[float] = None  # multiple of the font size
    letter_spacing: Optional[float] = None  # baseline px
    uppercase: Optional[bool] = None
    background: Optional[str] = None  # box color behind text kinds
    max_lines: Optional[int] = Field(default=None, ge=1)


# ---------------------------------------------------------------------------
# Visual base track
# ---------------------------------------------------------------------------


class Clip(_Model):
    """One item of the visual base track.

    A clip is visible from ``start`` to ``start + duration``. With a
    ``transition_in`` other than ``cut`` the clip fades in over the first
    ``transition_duration`` seconds of its own window while the previous clip
    keeps playing, fully opaque, underneath it (no brightness dip). Clips are
    usually laid back to back; a gap shows ``Timeline.background``.
    """

    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    kind: Literal["image", "video", "color", "gradient"]
    src: Optional[str] = None
    color: Optional[str] = None
    gradient: Optional[Union[str, list[str]]] = None  # list of colors, or "a,b,c"
    fit: Literal["cover", "contain"] = "cover"
    # "ken_burns" (addition) alternates push_in and pull_out by clip index,
    # exactly like the story-telling ImageLayer.
    motion: Literal["none", "push_in", "pull_out", "pan_left", "pan_right", "ken_burns"] = "none"
    transition_in: Literal["cut", "crossfade", "dip_black"] = "cut"
    transition_duration: float = Field(default=DEFAULT_TRANSITION, ge=0)
    video_audio_gain_db: Optional[float] = None  # None: the clip's own audio is muted
    # Additions
    gradient_angle: float = 180.0  # CSS degrees: 180 is top to bottom
    zoom_from: Optional[float] = None  # override the motion's start scale
    zoom_to: Optional[float] = None  # override the motion's end scale
    drift_px: Optional[float] = None  # horizontal drift, baseline px (default 14)
    motion_direction: Optional[Literal[1, -1]] = None  # None: alternate by clip index
    focus_x: float = Field(default=0.5, ge=0, le=1)  # crop focal point for cover
    focus_y: float = Field(default=0.5, ge=0, le=1)
    src_start: float = Field(default=0.0, ge=0)  # video: seconds into the source
    loop_video: bool = False  # video shorter than the clip: loop (else hold last frame)
    # A video shorter than its clip without loop_video: "freeze" holds the
    # last frame; "push_in" holds it under a slow push-in (about 2.5 per cent
    # a second) so the picture never stops moving.
    hold: Literal["freeze", "push_in"] = "freeze"
    # Playback speed of a video (0.5 to 2); below 1 a slight slow motion that
    # stretches a clip a little short of its slot. Picture only: the clip's
    # own audio is not used when speed is not 1.
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    video_audio_role: Literal["voice", "sfx"] = "voice"  # voice ducks music
    # Colour grade (Timeline.grade, image and video clips only): False keeps
    # this clip ungraded. match_ref is a local image (the scene's approved
    # environment plate) the clip is colour matched to when grade.match is on.
    grade: bool = True
    match_ref: Optional[str] = None


# ---------------------------------------------------------------------------
# Overlays
# ---------------------------------------------------------------------------


class _OverlayBase(_Model):
    start: float = Field(default=0.0, ge=0)
    duration: float = Field(gt=0)
    enter: Optional[Anim] = None  # None: the kind's default
    exit: Optional[Anim] = None  # None: the kind's default
    z: int = 0
    anchor: Optional[Anchor] = None  # None: the kind's default
    safe_area: bool = True
    style: TextStyle = Field(default_factory=TextStyle)
    # Additions
    x: float = 0.0  # offset from the anchor position, baseline px
    y: float = 0.0
    opacity: float = Field(default=1.0, ge=0, le=1)


class TitleCardOverlay(_OverlayBase):
    kind: Literal["title_card"] = "title_card"
    title: str
    subtitle: Optional[str] = None
    eyebrow: Optional[str] = None
    narrow: bool = False  # a stat card shares the frame: keep clear of it


class StatCardOverlay(_OverlayBase):
    kind: Literal["stat_card"] = "stat_card"
    value: str
    label: Optional[str] = None


class LowerThirdOverlay(_OverlayBase):
    kind: Literal["lower_third"] = "lower_third"
    title: str
    subtitle: Optional[str] = None


class TextOverlay(_OverlayBase):
    kind: Literal["text"] = "text"
    text: str


class QuoteOverlay(_OverlayBase):
    kind: Literal["quote"] = "quote"
    text: str
    author: Optional[str] = None


class ListOverlay(_OverlayBase):
    kind: Literal["list"] = "list"
    items: list[str]
    title: Optional[str] = None
    numbered: bool = True
    item_stagger: float = 0.35  # seconds between items appearing


class CounterOverlay(_OverlayBase):
    kind: Literal["counter"] = "counter"
    to_value: float
    from_value: float = 0.0
    decimals: int = Field(default=0, ge=0, le=6)
    prefix: str = ""
    suffix: str = ""
    label: Optional[str] = None
    separator: str = ","
    compact: bool = False  # 1.2M style instead of 1,200,000
    count_duration: Optional[float] = None  # default: 60 percent of duration, max 2.5 s
    count_easing: EasingName = "ease_out"


class ChartOverlay(_OverlayBase):
    kind: Literal["chart"] = "chart"
    chart_type: Literal["bar", "line", "pie"] = "bar"
    labels: list[str] = Field(default_factory=list)
    values: list[float]
    title: Optional[str] = None
    colors: Optional[list[str]] = None
    value_prefix: str = ""
    value_suffix: str = ""
    decimals: int = Field(default=0, ge=0, le=6)
    show_values: bool = True
    build_duration: float = Field(default=1.4, ge=0)  # animated build length
    width: Optional[float] = None  # baseline px or fraction of usable width
    height: Optional[float] = None  # baseline px


class ProgressOverlay(_OverlayBase):
    kind: Literal["progress"] = "progress"
    from_value: float = Field(default=0.0, ge=0, le=1)
    to_value: float = Field(default=1.0, ge=0, le=1)
    thickness: float = 10.0  # baseline px
    color: Optional[str] = None  # default accent
    track_color: str = "rgba(255,255,255,0.18)"
    label: Optional[str] = None


class ShapeOverlay(_OverlayBase):
    kind: Literal["shape"] = "shape"
    shape: Literal["rect", "rounded_rect", "circle", "line"] = "rect"
    width: float = 200.0  # baseline px, or fraction of usable width when <= 1
    height: float = 200.0  # baseline px
    fill: Optional[str] = None  # default accent
    stroke_color: Optional[str] = None
    stroke_width: float = 0.0
    radius: float = 24.0


class ImageOverlayOverlay(_OverlayBase):
    kind: Literal["image_overlay"] = "image_overlay"
    src: str
    width: float = 0.6  # baseline px, or fraction of usable width when <= 1
    height: Optional[float] = None  # None: keep aspect
    radius: float = 24.0
    border: Optional[str] = None
    border_width: float = 0.0
    shadow: bool = True


class LogoOverlay(_OverlayBase):
    kind: Literal["logo"] = "logo"
    src: str
    width: float = 150.0  # baseline px


class OutroCardOverlay(_OverlayBase):
    kind: Literal["outro_card"] = "outro_card"
    title: str
    subtitle: Optional[str] = None
    scrim_opacity: float = Field(default=0.62, ge=0, le=1)
    fade_out: float = 22 / 30  # whole frame fades to the background at the end


class ScrimOverlay(_OverlayBase):
    """Linear gradient over the whole frame. ``stops`` are (position, color),
    position 0 at the bottom and 1 at the top. None: the story scrim."""

    kind: Literal["scrim"] = "scrim"
    stops: Optional[list[tuple[float, str]]] = None


class VignetteOverlay(_OverlayBase):
    kind: Literal["vignette"] = "vignette"
    inner: float = Field(default=0.48, ge=0, le=1)  # transparent up to this radius
    strength: float = Field(default=0.45, ge=0, le=1)  # black alpha at the corners


Overlay = Annotated[
    Union[
        TitleCardOverlay,
        StatCardOverlay,
        LowerThirdOverlay,
        TextOverlay,
        QuoteOverlay,
        ListOverlay,
        CounterOverlay,
        ChartOverlay,
        ProgressOverlay,
        ShapeOverlay,
        ImageOverlayOverlay,
        LogoOverlay,
        OutroCardOverlay,
        ScrimOverlay,
        VignetteOverlay,
    ],
    Field(discriminator="kind"),
]

OVERLAY_KINDS = (
    "title_card",
    "stat_card",
    "lower_third",
    "text",
    "quote",
    "list",
    "counter",
    "chart",
    "progress",
    "shape",
    "image_overlay",
    "logo",
    "outro_card",
    "scrim",
    "vignette",
)


# ---------------------------------------------------------------------------
# Captions
# ---------------------------------------------------------------------------


class CaptionWord(_Model):
    text: str
    start: float
    end: float
    speaker: Optional[str] = None


CaptionPreset = Literal["bold_pop", "karaoke_box", "minimal_lower", "serif_story", "none"]
CAPTION_PRESETS: tuple[str, ...] = ("bold_pop", "karaoke_box", "minimal_lower", "serif_story", "none")


class CaptionTrack(_Model):
    """Word-synced captions. Words are grouped (default 3 per group in a
    vertical frame, 4 square, 6 landscape) and a group never crosses a speaker
    change, a pause over 0.35 s or the end of a sentence."""

    words: list[CaptionWord] = Field(default_factory=list)
    preset: CaptionPreset = "bold_pop"
    words_per_group: Optional[int] = Field(default=None, ge=1, le=12)
    highlight: str = "#FFD166"
    position: Literal["lower", "middle", "upper"] = "lower"
    # "ads": the paid placement safe zone of a vertical ad (top 14 per cent,
    # bottom 35 per cent, 6 per cent left and 13 per cent right kept clear).
    platform_safe_zone: Literal["shorts", "tiktok", "reels", "youtube", "ads"] = "shorts"
    # Additions
    font: Optional[str] = None
    size: Optional[float] = None  # baseline px
    color: Optional[str] = None
    uppercase: Optional[bool] = None  # None: preset default
    max_lines: int = Field(default=2, ge=1, le=3)
    z: int = 1000  # captions draw above overlays with a lower z


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------


class AudioTrack(_Model):
    src: str
    start: float = Field(default=0.0, ge=0)
    gain_db: float = 0.0
    role: Literal["voice", "music", "sfx"] = "voice"
    fade_in: float = Field(default=0.0, ge=0)
    fade_out: float = Field(default=0.0, ge=0)
    loop: bool = False
    trim_to_timeline: bool = True
    duck_under_voice: bool = False  # music ducks under voice
    # Additions
    src_start: float = Field(default=0.0, ge=0)  # seconds into the source
    duration: Optional[float] = Field(default=None, gt=0)  # cap the played length
    duck_db: float = Field(default=-14.0, le=0)  # attenuation while voice plays (12 to 18 dB reads as "under")


# ---------------------------------------------------------------------------
# Output and timeline
# ---------------------------------------------------------------------------


class OutputSpec(_Model):
    loudness_lufs: float = Field(default=-14.0, ge=-40, le=-5)
    crf: int = Field(default=20, ge=0, le=51)
    preset: Literal[
        "ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"
    ] = "veryfast"
    # Additions
    audio_bitrate: str = "192k"
    true_peak: float = -1.5
    threads: int = Field(default=2, ge=1, le=16)
    nice: int = Field(default=10, ge=0, le=19)
    # Leveling before the mix (None: tracks are mixed as they are). Every
    # voice input is measured once and brought to voice_lufs; music sits
    # music_under_voice_lu below the voice while ducked under it; gain_db is
    # then a trim on top. voice_compressor adds a gentle compressor on the
    # voice bus. The final two-pass loudnorm to loudness_lufs is unchanged.
    voice_lufs: Optional[float] = Field(default=None, ge=-30, le=-8)
    music_under_voice_lu: float = Field(default=16.0, ge=6, le=30)
    voice_compressor: bool = False


#: House looks (app/render/grade.py LOOKS, LUTs in app/render/looks/).
GRADE_LOOKS: tuple[str, ...] = (
    "neutral", "warm_film", "teal_orange", "cool_clean", "soft_pastel", "mono_contrast", "golden_hour",
    "documentary_muted",
)
GradeLook = Literal[
    "neutral", "warm_film", "teal_orange", "cool_clean", "soft_pastel", "mono_contrast", "golden_hour",
    "documentary_muted",
]


class Grade(_Model):
    """A colour grade on the base track only (image and video clips; never
    overlays, captions or end cards). ``strength`` blends the look with the
    ungraded picture. ``match`` (off by default) first pulls each clip that
    has a ``match_ref`` toward that plate's colour, ``match_strength`` of
    the way, to reduce drift between generated clips of one scene."""

    look: GradeLook = "neutral"
    strength: float = Field(default=1.0, ge=0, le=1)
    match: bool = False
    match_strength: float = Field(default=0.5, ge=0, le=1)


class Timeline(_Model):
    width: int = Field(ge=64, le=4096)
    height: int = Field(ge=64, le=4096)
    fps: int = Field(default=30, ge=1, le=60)
    duration: Optional[float] = Field(default=None, gt=0)  # None: end of the last clip or audio
    background: str = "#04060A"
    clips: list[Clip] = Field(default_factory=list)
    overlays: list[Overlay] = Field(default_factory=list)
    captions: Optional[CaptionTrack] = None
    audio: list[AudioTrack] = Field(default_factory=list)
    output: OutputSpec = Field(default_factory=OutputSpec)
    grade: Optional[Grade] = None  # None: no colour grade
    # Additions: theme defaults used by every overlay kind
    accent: str = "#FFD166"
    display_font: str = "Bricolage Grotesque"
    text_font: str = "Poppins"

    @field_validator("width", "height")
    @classmethod
    def _even(cls, v: int) -> int:
        # yuv420p needs even dimensions
        return v + (v % 2)

    @model_validator(mode="after")
    def _check_sources(self) -> "Timeline":
        for i, c in enumerate(self.clips):
            if c.kind in ("image", "video") and not c.src:
                raise ValueError(f"clips[{i}]: kind {c.kind} needs src")
        return self

    # Convenience helpers used by the engine and handy for callers.
    @property
    def scale(self) -> float:
        """Layout scale, width / 1080."""
        return self.width / 1080.0

    @property
    def orientation(self) -> Literal["vertical", "square", "landscape"]:
        if self.height > self.width * 1.1:
            return "vertical"
        if self.width > self.height * 1.1:
            return "landscape"
        return "square"


# ---------------------------------------------------------------------------
# Results and errors
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderResult:
    path: str
    duration: float
    width: int
    height: int
    size_bytes: int


class MediaInfo(TypedDict):
    duration: float
    width: int
    height: int
    has_audio: bool


class RenderError(RuntimeError):
    """A render failed (bad input, missing file, ffmpeg error)."""


class RenderCancelled(RenderError):
    """The cancel callback returned True. The workdir has been cleaned up."""


__all__ = [
    "Anchor",
    "Anim",
    "AnimType",
    "AudioTrack",
    "CAPTION_PRESETS",
    "CaptionPreset",
    "CaptionTrack",
    "CaptionWord",
    "ChartOverlay",
    "Clip",
    "CounterOverlay",
    "DEFAULT_TRANSITION",
    "EasingName",
    "GRADE_LOOKS",
    "Grade",
    "GradeLook",
    "ImageOverlayOverlay",
    "ListOverlay",
    "LogoOverlay",
    "LowerThirdOverlay",
    "MediaInfo",
    "OVERLAY_KINDS",
    "OutputSpec",
    "OutroCardOverlay",
    "Overlay",
    "ProgressOverlay",
    "QuoteOverlay",
    "RenderCancelled",
    "RenderError",
    "RenderResult",
    "ScrimOverlay",
    "ShapeOverlay",
    "StatCardOverlay",
    "TextOverlay",
    "TextStyle",
    "Timeline",
    "TitleCardOverlay",
    "VignetteOverlay",
]
