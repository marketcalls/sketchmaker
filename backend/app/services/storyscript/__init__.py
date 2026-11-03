"""Script engine for /faceless and /motion-graphics.

Pure functions over the configured LLM (APISettings default provider and model
through app/clients/litellm_client.py). No database writes, apart from the
token usage row litellm_client records for every call.

Functions that call the LLM are ``async`` (await them from routers or from the
scheduler's event loop); the deterministic ones are plain functions.
"""

from .errors import (
    InvalidLLMOutput,
    LLMCallFailed,
    LLMNotConfigured,
    NotImplementedYet,
    StoryScriptError,
    StoryScriptInputError,
)
from .models import (
    Beat,
    CharacterBible,
    CharacterBrief,
    Chapter,
    ComplianceFlag,
    DialogueLine,
    EpisodeSummary,
    Fact,
    LengthRange,
    MotionSpec,
    MusicPlan,
    MusicSection,
    OriginalityMatch,
    OriginalityReport,
    Packaging,
    PlatformDisclosure,
    SafetyFlag,
    Scene,
    Script,
    SeriesBrief,
    ShotPlan,
    SourceRef,
    Stat,
    Template,
    ThumbnailPrompt,
    VoiceStyle,
)
from .templates import get_template, list_templates
from .drafting import draft_script, revise_scene
from .characters import describe_character
from .originality import originality_check
from .compliance import compliance_check
from .packaging import package
from .motion import motion_graphics_draft

__all__ = [
    "list_templates", "get_template", "draft_script", "revise_scene",
    "describe_character", "originality_check", "compliance_check", "package",
    "motion_graphics_draft",
    "Beat", "CharacterBible", "CharacterBrief", "Chapter", "ComplianceFlag",
    "DialogueLine", "EpisodeSummary", "Fact", "LengthRange", "MotionSpec",
    "MusicPlan", "MusicSection", "OriginalityMatch", "OriginalityReport",
    "Packaging", "PlatformDisclosure", "SafetyFlag", "Scene", "Script",
    "SeriesBrief", "ShotPlan", "SourceRef", "Stat", "Template",
    "ThumbnailPrompt", "VoiceStyle",
    "StoryScriptError", "StoryScriptInputError", "LLMNotConfigured",
    "InvalidLLMOutput", "LLMCallFailed", "NotImplementedYet",
]
