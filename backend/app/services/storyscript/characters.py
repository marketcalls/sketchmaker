"""describe_character: a CharacterBible from reference images or notes.

With a vision-capable default model the images are analyzed (downloaded
through url_fetch and sent inline). Otherwise, or when the vision call fails,
the bible is built from the user's notes by the text model, and without any
LLM configured it is assembled deterministically from the notes.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, ConfigDict, Field

from . import llm, policy
from .errors import InvalidLLMOutput, LLMCallFailed, LLMNotConfigured, StoryScriptInputError
from .models import CharacterBible, SafetyFlag
from .text import strip_style_words

logger = logging.getLogger(__name__)


class _LLMFlag(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: str
    confidence: float = 0.5
    note: str = ""


class LLMBible(BaseModel):
    model_config = ConfigDict(extra="ignore")
    canonical_description: str = Field(min_length=10)
    outfit: str = ""
    distinguishing_features: list[str] = Field(default_factory=list)
    likeness_clause: str = Field(min_length=10)
    style_notes: str = ""
    age_range: str = ""
    species: str = "human"
    safety_flags: list[_LLMFlag] = Field(default_factory=list)


SYSTEM = """You write character bibles for an AI image pipeline that must draw the same character identically in every frame. Describe only what is visible in the images or stated in the notes. Never guess or name the identity of a real person.

Fields:
- canonical_description: two to four sentences: species, apparent age range, build, skin tone, face shape, eyes, hair color, length and style, facial hair, and anything else that defines the look.
- outfit: the signature outfit with colors and materials.
- distinguishing_features: three to six short items that make the character recognizable (a scar, freckles, a hat, glasses, a color accent).
- likeness_clause: one paragraph of forty to eighty words, present tense, starting with the character's name, that an image model can read before any scene: species, apparent age range, build, skin tone, face, eyes, hair, distinguishing features and signature outfit with colors. No art style words (realistic, cartoon, 3D, anime, painting), no camera words, no emotions, no actions, no background, nothing written.
- style_notes: the visual style the references are in (photo, 3D, cartoon, painted), for the operator, not for prompts.
- age_range: for example "late twenties" or "about eight".
- species: human, or the animal or creature.
- safety_flags: a list of {kind, confidence 0 to 1, note} using these kinds only:
  real_person (the images look like photographs of a real human),
  possible_minor (the character could be under eighteen),
  public_figure (resembles a well known public figure; do not name them),
  copyrighted_character (a recognizable character from film, TV, games or comics),
  brand_logo (logos or brand marks are visible),
  sensitive_content (nudity, weapons, gore or similar).
  Include a flag only when it applies."""

_FLAG_KINDS = {"real_person", "possible_minor", "public_figure", "copyrighted_character",
               "brand_logo", "sensitive_content"}
_AGE_WORDS = ("one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
              "fifteen|sixteen|seventeen")
_MINOR_HINT = re.compile(
    r"\b(child|children|kid|kids|toddler|baby|infant|teen|teenage|teenager|preteen|tween|schoolboy|"
    r"schoolgirl|schoolchild|little (?:boy|girl)|young (?:boy|girl)|"
    r"(?:[1-9]|1[0-7]|" + _AGE_WORDS + r")[ -]?(?:years?|yrs?)[ -]?old|"
    r"aged? (?:[1-9]|1[0-7]|" + _AGE_WORDS + r"))\b",
    re.I)


def _clean_clause(name: str, clause: str) -> str:
    c = " ".join((clause or "").split())
    c = strip_style_words(c)
    if name and not c.lower().startswith(name.lower()):
        c = f"{name}, {c[0].lower() + c[1:] if c else ''}".strip(", ")
    words = c.split()
    if len(words) > 110:
        c = " ".join(words[:110]).rstrip(",;") + "."
    if c and c[-1] not in ".!?":
        c += "."
    return c


def _heuristic_flags(name: str, text: str) -> list[SafetyFlag]:
    flags: list[SafetyFlag] = []
    if _MINOR_HINT.search(text or ""):
        flags.append(SafetyFlag(kind="possible_minor", confidence=0.6, note="The notes describe a child or teen."))
    hits = policy.find("copyright", f"{name} {text}")
    if hits:
        flags.append(SafetyFlag(kind="copyrighted_character", confidence=0.7,
                                note="Name or notes match a copyrighted character: " + ", ".join(hits)))
    pub = policy.find("public", f"{name} {text}")
    if pub:
        flags.append(SafetyFlag(kind="public_figure", confidence=0.6,
                                note="Name or notes match a public figure."))
    return flags


def _merge_flags(a: list[SafetyFlag], b: list[SafetyFlag]) -> list[SafetyFlag]:
    best: dict[str, SafetyFlag] = {}
    for f in a + b:
        if f.kind not in best or f.confidence > best[f.kind].confidence:
            best[f.kind] = f
    return sorted(best.values(), key=lambda f: -f.confidence)


def _from_llm(name: str, raw: LLMBible, source: str, model: str | None, notes: str) -> CharacterBible:
    flags = []
    for f in raw.safety_flags:
        if f.kind in _FLAG_KINDS:
            flags.append(SafetyFlag(kind=f.kind, confidence=max(0.0, min(1.0, float(f.confidence))),
                                    note=f.note[:300]))
    flags = _merge_flags(flags, _heuristic_flags(name, notes + " " + raw.canonical_description))
    return CharacterBible(
        name=name,
        canonical_description=" ".join(raw.canonical_description.split()),
        outfit=raw.outfit.strip(),
        distinguishing_features=[x.strip() for x in raw.distinguishing_features if x.strip()][:8],
        likeness_clause=_clean_clause(name, raw.likeness_clause),
        style_notes=raw.style_notes.strip(),
        age_range=raw.age_range.strip(),
        species=(raw.species or "human").strip().lower() or "human",
        safety_flags=flags,
        source=source,
        model=model,
    )


def _from_notes_only(name: str, notes: str | None) -> CharacterBible:
    text = " ".join((notes or "").split())
    if text:
        clause = _clean_clause(name, text)
        return CharacterBible(name=name, canonical_description=text, likeness_clause=clause,
                              safety_flags=_heuristic_flags(name, text), source="notes")
    return CharacterBible(
        name=name, canonical_description=f"{name}. No description yet.",
        likeness_clause=f"{name}.", source="name_only",
        safety_flags=_heuristic_flags(name, ""),
    )


async def describe_character(db, *, name, image_urls, notes=None,
                             user_id: int | None = None) -> CharacterBible:
    """Build a CharacterBible for a cast member.

    ``image_urls`` are https URLs (or data: URLs) of two to four reference
    images, ideally from different angles. ``notes`` is the user's own
    description, used alone when the model cannot see images.
    """
    name = " ".join(str(name or "").split())
    if not name:
        raise StoryScriptInputError("name is required")
    urls = [u for u in (image_urls or []) if isinstance(u, str) and u.strip()]
    notes_text = " ".join(str(notes or "").split())[:3000]

    try:
        choice = llm.resolve_model(db)
    except LLMNotConfigured:
        choice = None

    if choice is not None and choice.supports_vision and urls:
        images = await llm.load_images_as_data_urls(urls)
        if images:
            prompt = (f"CHARACTER NAME: {name}\n"
                      f"USER NOTES: {notes_text or 'none'}\n"
                      f"There are {len(images)} reference images of the same character. "
                      f"Where the images and notes disagree, trust the images for appearance.")
            try:
                raw, used = await llm.complete_json(
                    db, system=SYSTEM, prompt=prompt, schema=LLMBible, feature="storyscript_character",
                    temperature=0.3, user_id=user_id, choice=choice, images=images, max_tokens=2048,
                )
                return _from_llm(name, raw, "vision", used.label, notes_text)
            except (InvalidLLMOutput, LLMCallFailed) as exc:
                logger.warning(f"storyscript: vision bible failed, falling back to notes: {type(exc).__name__}")

    if choice is not None and notes_text:
        prompt = (f"CHARACTER NAME: {name}\nUSER NOTES: {notes_text}\n"
                  "No images are available. Build the bible from the notes only; do not invent features "
                  "the notes do not support, but you may make the wording precise.")
        try:
            raw, used = await llm.complete_json(
                db, system=SYSTEM, prompt=prompt, schema=LLMBible, feature="storyscript_character",
                temperature=0.3, user_id=user_id, choice=choice, max_tokens=2048,
            )
            return _from_llm(name, raw, "notes", used.label, notes_text)
        except (InvalidLLMOutput, LLMCallFailed, LLMNotConfigured) as exc:
            logger.warning(f"storyscript: notes bible failed, using the notes verbatim: {type(exc).__name__}")

    return _from_notes_only(name, notes_text)
