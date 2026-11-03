"""Data models for the script engine.

Everything here is plain pydantic with no database coupling, so the /faceless
backend can store these as JSON columns (``model_dump(mode="json")``) and
rebuild them with ``Model.model_validate(data)``.

Times are seconds (floats). Beat timings on templates are fractions of the
runtime (0.0 to 1.0).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Aspect = Literal["9:16", "16:9", "1:1", "4:5"]
ShotKind = Literal["still", "clip", "user_media", "card"]
Camera = Literal[
    "pov", "handheld", "establishing", "close_up", "over_the_shoulder",
    "medium", "wide", "insert",
]
EndingStyle = Literal["loop", "cliffhanger_vote", "payoff"]
CaptionPreset = Literal["bold_pop", "karaoke_box", "minimal_lower", "serif_story", "none"]
Severity = Literal["block", "warn", "info"]
TemplateKind = Literal["format", "viral"]
DialogueMode = Literal["narration", "dialogue", "mixed"]
# How a scene's picture arrives (the render engine's transitions), plus J and
# L cuts: a hard cut with the scene's voice starting before its picture (J) or
# the previous scene's voice running over this picture (L).
SceneTransition = Literal["cut", "crossfade", "dip_black", "j_cut", "l_cut"]
# One camera move per clip, stated with its tempo first in the clip prompt.
CameraMove = Literal[
    "static", "push_in", "pull_out", "pan_left", "pan_right", "tilt_up", "tilt_down",
    "tracking", "handheld", "orbit", "crane_up", "whip_pan", "rack_focus",
]
SoundEffect = Literal["whoosh", "hit", "riser"]


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------

class Beat(BaseModel):
    """One structural beat. ``start`` and ``end`` are fractions of runtime."""

    id: str
    name: str
    start: float = Field(ge=0.0, le=1.0)
    end: float = Field(ge=0.0, le=1.0)
    job: str
    rehook: bool = False          # this beat opens with a re-hook line
    silence_after: float = 0.0    # seconds of held silence after the beat


class LengthRange(BaseModel):
    min_seconds: int = Field(ge=15, le=900)
    default_seconds: int = Field(ge=15, le=900)
    max_seconds: int = Field(ge=15, le=900)


class VoiceStyle(BaseModel):
    wpm: int = Field(ge=100, le=200)
    stability: float = Field(ge=0.0, le=1.0, default=0.5)
    similarity_boost: float = Field(ge=0.0, le=1.0, default=0.75)
    description: str = ""
    suggested_voices: list[str] = Field(default_factory=list)


class MusicSection(BaseModel):
    section_name: str
    fraction: float = Field(gt=0.0, le=1.0)     # share of the runtime
    positive_local_styles: list[str] = Field(default_factory=list)
    negative_local_styles: list[str] = Field(default_factory=list)


class MusicPlan(BaseModel):
    """Shape of an ElevenLabs Music composition plan.

    ``to_composition_plan(length_seconds)`` turns the fractions into the
    ``duration_ms`` values fal expects.
    """

    mood: str
    positive_global_styles: list[str] = Field(default_factory=list)
    negative_global_styles: list[str] = Field(default_factory=list)
    sections: list[MusicSection] = Field(default_factory=list)
    force_instrumental: bool = True
    gain_db: float = -18.0

    def to_composition_plan(self, length_seconds: float) -> dict[str, Any]:
        total_ms = int(round(max(3.0, min(600.0, length_seconds)) * 1000))
        sections = self.sections or [MusicSection(section_name="main", fraction=1.0)]
        weight = sum(s.fraction for s in sections) or 1.0
        out: list[dict[str, Any]] = []
        used = 0
        for i, s in enumerate(sections):
            if i == len(sections) - 1:
                ms = total_ms - used
            else:
                ms = int(round(total_ms * s.fraction / weight))
                used += ms
            out.append({
                "section_name": s.section_name,
                "duration_ms": max(3000, ms),
                "positive_local_styles": list(s.positive_local_styles),
                "negative_local_styles": list(s.negative_local_styles),
                "lines": [],
            })
        return {
            "positive_global_styles": list(self.positive_global_styles),
            "negative_global_styles": list(self.negative_global_styles),
            "sections": out,
        }


class Template(BaseModel):
    id: str
    name: str
    pitch: str
    niche: str
    kind: TemplateKind
    aspects: list[Aspect]
    default_aspect: Aspect
    length: LengthRange
    shorts: bool                      # vertical Shorts format, capped at 180 s
    beats: list[Beat]
    hook_formulas: list[str]
    rehook_seconds: list[float] = Field(default_factory=list)   # absolute times
    rehook_every_seconds: float | None = None                   # repeats after the list
    ending: EndingStyle
    ending_note: str = ""
    shots_per_minute: float = Field(gt=0)        # visual changes per minute
    words_per_scene: int | None = 28             # None: dialogue-led, scenes from shots
    dialogue_mode: DialogueMode = "narration"
    visual_style: str                            # house style appended to every image prompt
    realistic: bool = False                      # photoreal look (drives disclosure advice)
    voice: VoiceStyle
    music: MusicPlan
    caption_preset: CaptionPreset
    fact_mode: bool = False
    kids_safe: bool = False
    stat_cards: bool = False
    clip_share: float = Field(default=0.2, ge=0.0, le=1.0)   # share of scenes as H3 clips
    policy_notes: list[str] = Field(default_factory=list)
    title_formulas: list[str] = Field(default_factory=list)
    description_formula: str = ""
    tags: list[str] = Field(default_factory=list)
    situations: list[str] = Field(default_factory=list)      # variation pool (premise archetypes)
    outcomes: list[str] = Field(default_factory=list)        # variation pool (endings)
    dramatization_label: str | None = None
    transition: Literal["cut", "crossfade", "dip_black"] = "cut"   # between scenes, unless a scene says otherwise


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------

class SafetyFlag(BaseModel):
    kind: Literal[
        "real_person", "possible_minor", "public_figure", "copyrighted_character",
        "brand_logo", "sensitive_content",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    note: str = ""


class CharacterBible(BaseModel):
    name: str
    canonical_description: str
    outfit: str = ""
    distinguishing_features: list[str] = Field(default_factory=list)
    likeness_clause: str
    style_notes: str = ""
    age_range: str = ""
    species: str = "human"
    safety_flags: list[SafetyFlag] = Field(default_factory=list)
    source: Literal["vision", "notes", "name_only"] = "notes"
    model: str | None = None


class CharacterBrief(BaseModel):
    """A cast member as the script engine sees it."""

    id: str
    name: str
    role: str = ""                    # protagonist, rival, narrator, mascot...
    personality: str = ""
    likeness_clause: str = ""         # prepended verbatim to prompts with this character
    species: str = "human"
    voice_id: str | None = None
    catchphrase: str | None = None
    is_real_person: bool = False      # built from photos of a real person
    is_user_self: bool = False        # the real person is the account holder
    consent_attested: bool = False
    is_public_figure: bool = False
    is_minor: bool = False
    bible: CharacterBible | None = None

    @field_validator("id", mode="before")
    @classmethod
    def _id_str(cls, v: Any) -> str:
        return str(v)

    def clause(self) -> str:
        if self.likeness_clause.strip():
            return self.likeness_clause.strip()
        if self.bible and self.bible.likeness_clause.strip():
            return self.bible.likeness_clause.strip()
        return ""


class EpisodeSummary(BaseModel):
    title: str = ""
    premise: str = ""
    outcome: str = ""
    situation: str | None = None


class SeriesBrief(BaseModel):
    id: str | None = None
    title: str = ""
    logline: str = ""
    world: str = ""
    tone: str = ""
    rules: list[str] = Field(default_factory=list)          # continuity rules
    recurring_elements: list[str] = Field(default_factory=list)
    episode_number: int = 1
    previous_episodes: list[EpisodeSummary] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)

    @field_validator("id", mode="before")
    @classmethod
    def _id_str(cls, v: Any) -> str | None:
        return None if v is None else str(v)


class Fact(BaseModel):
    """A user-supplied fact. The only material a fact-mode script may claim."""

    id: str
    text: str
    source: str = ""                  # URL or citation as the user gave it
    date: str = ""                    # date of the event or publication


# --------------------------------------------------------------------------
# Script
# --------------------------------------------------------------------------

class DialogueLine(BaseModel):
    character_id: str
    character: str                    # display name
    text: str                         # TTS-safe line, no tags
    emotion: str | None = None        # Eleven v4 audio tag word, e.g. "whispering"

    def tts_text(self) -> str:
        """The string sent to Eleven v4 (tag in square brackets, then the line)."""
        return f"[{self.emotion}] {self.text}" if self.emotion else self.text


class ShotPlan(BaseModel):
    kind: ShotKind = "still"
    camera: Camera = "medium"
    characters: list[str] = Field(default_factory=list)   # character ids in frame
    direction: str = ""               # the scene direction without likeness clauses
    visual_prompt: str = ""           # likeness clauses verbatim, then direction (no style words)
    images: int = Field(default=1, ge=1, le=4)            # stills within the scene
    clip_seconds: float | None = None
    motion: Literal["none", "push_in", "pull_out", "pan_left", "pan_right"] = "push_in"
    camera_move: CameraMove | None = None   # None: follows ``motion``
    end_state: str = ""                     # what the frame shows when the clip ends
    hero_product: bool = False              # the product alone, animated from its own photo
    keyframe_url: str = ""                  # an approved first frame (Story Room), used by clips


class ProductRef(BaseModel):
    """A real product in the shot. Its approved photo is sent as a labelled
    reference and never redrawn from a description."""

    key: str = ""
    name: str = ""
    image_url: str = ""               # set by the Story Room handoff from the approved image
    must_keep: list[str] = Field(default_factory=list)


class AdCard(BaseModel):
    """End card of an ad: the call to action as the title, the offer under it."""

    cta: str = ""
    offer: str = ""
    brand: str = ""


class Stat(BaseModel):
    value: str                        # exact digits as shown on screen, e.g. "1,200"
    label: str
    fact_id: str | None = None


class SourceRef(BaseModel):
    fact_id: str
    claim: str = ""
    source: str = ""                  # copied from the Fact
    date: str = ""


class Scene(BaseModel):
    id: str                           # "s1", "s2"... stable across revisions
    index: int
    beat: str                         # Beat.id
    beat_name: str = ""
    start: float = 0.0                # estimated, from word counts
    duration: float = 0.0             # estimated, the voice clip sets the real value
    narration: str = ""               # TTS-safe
    narration_emotion: str | None = None
    dialogue: list[DialogueLine] = Field(default_factory=list)
    shot: ShotPlan = Field(default_factory=ShotPlan)
    on_screen_text: str | None = None
    stat: Stat | None = None
    sources: list[SourceRef] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)   # fact gaps the user must answer
    is_hook: bool = False
    is_rehook: bool = False
    dramatization: bool = False
    silence_after: float = 0.0
    word_target: int = 0
    notes: str = ""
    transition_in: SceneTransition | None = None   # None: the template's transition
    sfx: SoundEffect | None = None                 # sound under the transition into this scene
    products: list[ProductRef] = Field(default_factory=list)

    def spoken_words(self) -> int:
        n = len(self.narration.split())
        n += sum(len(d.text.split()) for d in self.dialogue)
        return n


class Script(BaseModel):
    template_id: str
    title: str = ""
    logline: str = ""
    premise: str = ""
    situation: str = ""
    outcome: str = ""
    language: str = "en"
    aspect: Aspect = "9:16"
    length_seconds: int
    estimated_seconds: float = 0.0
    wpm: int = 165
    word_budget: int = 0
    word_count: int = 0
    seed: int = 0
    hook_formula: str = ""
    ending: EndingStyle = "payoff"
    ending_line: str = ""
    vote_prompt: str | None = None
    outro_title: str = ""             # three to five words, shown on the outro card
    scenes: list[Scene] = Field(default_factory=list)
    cast_ids: list[str] = Field(default_factory=list)
    cast_clauses: dict[str, str] = Field(default_factory=dict)   # id -> likeness clause used
    cast_names: dict[str, str] = Field(default_factory=dict)     # id -> display name
    narrator_voice: str | None = None
    series_id: str | None = None
    episode_number: int | None = None
    fact_mode: bool = False
    facts: list[Fact] = Field(default_factory=list)
    needs_facts: bool = False         # fact mode without facts: questions, not claims
    dramatization_label: str | None = None
    visual_style: str = ""
    caption_preset: CaptionPreset = "bold_pop"
    music: MusicPlan | None = None
    tts_text_normalization: Literal["auto", "on", "off"] = "auto"
    # Ads (Story Room handoff): the end card, and the exact runtime of the
    # placement (6, 15 or 30 s, or the story's target) the render fits to.
    format: Literal["story", "ad"] = "story"
    ad: AdCard | None = None
    exact_seconds: float | None = Field(default=None, ge=3.0, le=600.0)
    look_register: str = ""           # cinematic | ugc | documentary | animated, or empty
    warnings: list[str] = Field(default_factory=list)
    model: str | None = None
    version: int = 1


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------

class OriginalityMatch(BaseModel):
    title: str = ""
    index: int                        # position in previous_scripts
    similarity: float                 # 0..1, weighted
    features: dict[str, float] = Field(default_factory=dict)


class OriginalityReport(BaseModel):
    score: int = Field(ge=0, le=100)  # 100 = fully original
    verdict: Literal["original", "similar", "repetitive"]
    same_situation_same_outcome: bool = False
    compared: int = 0
    closest: list[OriginalityMatch] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ComplianceFlag(BaseModel):
    code: str
    severity: Severity
    message: str
    advice: str = ""
    scene_id: str | None = None
    character_id: str | None = None
    platform: Literal["youtube", "tiktok", "instagram", "all"] | None = None


class Chapter(BaseModel):
    start: float
    timestamp: str                    # "0:00", "1:23", "1:02:03"
    title: str


class ThumbnailPrompt(BaseModel):
    prompt: str                       # image prompt, likeness clause first, no text
    text: str                         # 2 to 4 words, rendered later by the app
    characters: list[str] = Field(default_factory=list)


class PlatformDisclosure(BaseModel):
    platform: Literal["youtube", "tiktok", "instagram"]
    required: bool
    label: str
    reason: str


class Packaging(BaseModel):
    titles: list[str]
    description: str
    first_line: str
    sources_section: str | None = None
    disclosure_line: str
    tags: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    chapters: list[Chapter] = Field(default_factory=list)
    thumbnail_prompts: list[ThumbnailPrompt] = Field(default_factory=list)
    disclosure_advice: list[PlatformDisclosure] = Field(default_factory=list)


class MotionSpec(BaseModel):
    """Placeholder for /motion-graphics. The motion graphics agent owns the shape."""

    template_id: str
    aspect: Aspect
    length_seconds: int
    elements: list[dict[str, Any]] = Field(default_factory=list)
    data: dict[str, Any] | None = None
