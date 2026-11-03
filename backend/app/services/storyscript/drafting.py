"""draft_script and revise_scene.

Flow:
1. A deterministic blueprint (``plan_script``): word budget, scene slots with
   their beat, timing, word target, camera hint, shot kind, hook, re-hook and
   ending flags, and the per-episode variation (hook formula, situation and
   outcome archetypes) drawn from a seeded RNG.
2. The LLM writes the scenes into that blueprint as JSON (one call for short
   scripts; an outline plus parallel chunks for long-form).
3. Deterministic post-processing: TTS sanitizing, audio tag mapping, likeness
   clauses injected verbatim at the start of every visual prompt, style words
   stripped, sources checked against the user's facts, stats capped, timing
   estimated from word counts.
"""

from __future__ import annotations

import asyncio
import math
import os
import random
import re
import zlib
from dataclasses import dataclass, field
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from . import llm
from .errors import StoryScriptInputError
from .models import (
    Beat, CharacterBrief, DialogueLine, Fact, Scene, Script, SeriesBrief,
    ShotPlan, SourceRef, Stat, Template,
)
from .templates import get_template, max_length_for, rehook_times
from .text import (
    SAFE_AUDIO_TAGS, compose_visual_prompt, normalize_audio_tag, seconds_for_words,
    strip_style_words, tts_safe, word_budget, word_count,
)

SINGLE_CALL_MAX_SCENES = 16
CHUNK_SCENES = 12
CHUNK_CONCURRENCY = 3
CAMERAS = ("pov", "handheld", "establishing", "close_up", "over_the_shoulder", "medium", "wide", "insert")
ASPECTS = ("9:16", "16:9", "1:1", "4:5")

LANGUAGE_NAMES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian",
    "pt": "Portuguese", "nl": "Dutch", "sv": "Swedish", "no": "Norwegian", "da": "Danish",
    "fi": "Finnish", "pl": "Polish", "cs": "Czech", "ro": "Romanian", "hu": "Hungarian",
    "el": "Greek", "tr": "Turkish", "ru": "Russian", "uk": "Ukrainian", "ar": "Arabic",
    "he": "Hebrew", "hi": "Hindi", "bn": "Bengali", "ta": "Tamil", "te": "Telugu",
    "mr": "Marathi", "gu": "Gujarati", "kn": "Kannada", "ml": "Malayalam", "pa": "Punjabi",
    "ur": "Urdu", "id": "Indonesian", "ms": "Malay", "th": "Thai", "vi": "Vietnamese",
    "tl": "Filipino", "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "sw": "Swahili",
}


# --------------------------------------------------------------------------
# What the LLM returns (lenient; the post-processor enforces the real rules)
# --------------------------------------------------------------------------

class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


class LLMDialogue(_Loose):
    character_id: str
    text: str = Field(min_length=1)
    emotion: str | None = None


class LLMStat(_Loose):
    value: str
    label: str
    fact_id: str | None = None


class LLMSource(_Loose):
    fact_id: str
    claim: str = ""


class LLMScene(_Loose):
    slot: int
    narration: str = ""
    narration_emotion: str | None = None
    dialogue: list[LLMDialogue] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list)
    camera: str = "medium"
    kind: str | None = None
    direction: str = Field(min_length=3)
    on_screen_text: str | None = None
    stat: LLMStat | None = None
    sources: list[LLMSource] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class LLMHeader(_Loose):
    title: str = Field(min_length=1)
    logline: str = ""
    premise: str = Field(min_length=1)
    situation: str = ""
    outcome: str = Field(min_length=1)
    ending_line: str = ""
    vote_prompt: str | None = None
    outro_title: str = ""


class LLMDraft(LLMHeader):
    scenes: list[LLMScene]


class LLMOutlineItem(_Loose):
    slot: int
    summary: str = Field(min_length=1)


class LLMOutline(LLMHeader):
    outline: list[LLMOutlineItem]


class LLMChunk(_Loose):
    scenes: list[LLMScene]


class LLMRevision(_Loose):
    scene: LLMScene


# --------------------------------------------------------------------------
# Blueprint
# --------------------------------------------------------------------------

@dataclass
class Slot:
    number: int                      # 1-based, as shown to the LLM
    beat: Beat
    beats: list[Beat]
    start: float
    duration: float
    words: int
    camera: str
    kind: str
    images: int
    is_hook: bool = False
    is_rehook: bool = False
    is_last: bool = False
    silence_after: float = 0.0


@dataclass
class Plan:
    template: Template
    length_seconds: int
    aspect: str
    language: str
    seed: int
    wpm: int
    word_target: int
    word_min: int
    word_max: int
    outro_seconds: float
    hook_formula: str
    situation: str
    outcome: str
    slots: list[Slot] = field(default_factory=list)


OUTRO_SECONDS = 3.0   # silent outro card after a payoff ending (92 frames at 30 fps)


def _outro_seconds(template: Template, length_seconds: int) -> float:
    return OUTRO_SECONDS if template.ending == "payoff" else 0.0


def _speaking_seconds(template: Template, length_seconds: int, aspect: str) -> tuple[float, float]:
    """Seconds of voice and the outro length.

    The outro card plays after the voice (the story-telling project's 60 s =
    160 to 175 words), except at the platform cap, where it has to fit inside.
    """
    outro = _outro_seconds(template, length_seconds)
    if outro and length_seconds + outro > max_length_for(template, aspect):
        return max(5.0, length_seconds - outro), outro
    return float(length_seconds), outro


def _allocate(beats: list[Beat], n: int) -> list[list[Beat]]:
    """Beats for each of n slots, in order."""
    if n >= len(beats):
        raw = [n * (b.end - b.start) for b in beats]
        counts = [max(1, int(math.floor(r))) for r in raw]
        while sum(counts) < n:
            i = max(range(len(beats)), key=lambda k: raw[k] - counts[k])
            counts[i] += 1
        while sum(counts) > n:
            cands = [k for k in range(len(beats)) if counts[k] > 1]
            i = min(cands, key=lambda k: raw[k] - counts[k])
            counts[i] -= 1
        out: list[list[Beat]] = []
        for b, c in zip(beats, counts):
            out.extend([[b]] * c)
        return out
    groups: list[list[Beat]] = [[] for _ in range(n)]
    for b in beats:
        mid = (b.start + b.end) / 2
        groups[min(n - 1, int(mid * n))].append(b)
    for i, g in enumerate(groups):
        if not g:
            center = (i + 0.5) / n
            groups[i] = [next(b for b in beats if b.start <= center <= b.end)]
    return groups


def _camera_plan(rng: random.Random, n: int, template: Template) -> list[str]:
    energetic = ["pov", "handheld", "close_up"]
    if template.shorts:
        first = rng.choice(energetic)
        pool = ["pov", "handheld", "close_up", "over_the_shoulder", "medium", "wide", "insert"]
        weights = [3, 3, 3, 2, 2, 1, 1]
    else:
        first = rng.choice(["establishing", "close_up", "pov"])
        pool = ["establishing", "wide", "medium", "close_up", "over_the_shoulder", "insert", "pov", "handheld"]
        weights = [2, 2, 3, 3, 2, 2, 1, 1]
    out = [first]
    for _ in range(1, n):
        while True:
            c = rng.choices(pool, weights=weights)[0]
            if c != out[-1]:
                break
        out.append(c)
    return out


def _seed_for(series: SeriesBrief | None, seed: int | None) -> int:
    if seed is not None:
        return int(seed)
    if series is not None and (series.id or series.title):
        key = f"{series.id or series.title}:{series.episode_number}"
        return zlib.crc32(key.encode("utf-8"))
    return int.from_bytes(os.urandom(4), "big")


def _pick_fresh(rng: random.Random, pool: list[str], used: Iterable[str]) -> str:
    if not pool:
        return ""
    used_l = {u.strip().lower() for u in used if u}
    fresh = [p for p in pool if p.lower() not in used_l]
    return rng.choice(fresh or pool)


def plan_script(template: Template, *, length_seconds: int, aspect: str, language: str = "en",
                seed: int = 0, series: SeriesBrief | None = None) -> Plan:
    """The deterministic skeleton every draft is written into."""
    rng = random.Random(seed)
    speaking, outro = _speaking_seconds(template, length_seconds, aspect)
    budget = word_budget(speaking, template.voice.wpm, template.words_per_scene,
                         template.shots_per_minute)
    n = budget.scenes
    slot_seconds = speaking / n
    groups = _allocate(template.beats, n)
    cameras = _camera_plan(rng, n, template)

    prev = series.previous_episodes if series else []
    used_situations = [e.situation or "" for e in prev] + (series.avoid if series else [])
    used_outcomes = [e.outcome for e in prev]
    plan = Plan(
        template=template, length_seconds=length_seconds, aspect=aspect, language=language,
        seed=seed, wpm=template.voice.wpm, word_target=budget.target,
        word_min=budget.minimum, word_max=budget.maximum, outro_seconds=outro,
        hook_formula=rng.choice(template.hook_formulas) if template.hook_formulas else "",
        situation=_pick_fresh(rng, template.situations, used_situations),
        outcome=_pick_fresh(rng, template.outcomes, used_outcomes),
    )

    # Word targets: spread the budget evenly (cumulative rounding, exact total).
    marks = [int(round(budget.target * k / n)) for k in range(n + 1)]
    for i in range(n):
        beats = groups[i]
        is_last_of_beat = i == n - 1 or groups[i + 1][0].id != beats[-1].id
        plan.slots.append(Slot(
            number=i + 1, beat=beats[0], beats=beats, start=round(i * slot_seconds, 2),
            duration=round(slot_seconds, 2), words=marks[i + 1] - marks[i], camera=cameras[i],
            kind="still", images=budget.images_per_scene, is_hook=(i == 0), is_last=(i == n - 1),
            silence_after=beats[-1].silence_after if is_last_of_beat else 0.0,
        ))

    # Re-hooks at the template's schedule (never the hook or the last scene).
    for t in rehook_times(template, length_seconds):
        for s in plan.slots[1:-1]:
            if s.start + s.duration / 2 >= t:
                s.is_rehook = True
                break

    # Clips: the hook first, then re-hooks and the ending, then seeded picks.
    n_clips = int(round(n * template.clip_share))
    if n_clips:
        order = [plan.slots[0]] + [s for s in plan.slots if s.is_rehook] + [plan.slots[-1]]
        rest = [s for s in plan.slots if s not in order]
        rng.shuffle(rest)
        chosen: list[Slot] = []
        for s in order + rest:
            if s not in chosen:
                chosen.append(s)
            if len(chosen) >= n_clips:
                break
        for s in chosen:
            s.kind = "clip"
            s.images = 1
    return plan


# --------------------------------------------------------------------------
# Input normalization
# --------------------------------------------------------------------------

def _as_model(cls, value):
    if value is None or isinstance(value, cls):
        return value
    if isinstance(value, dict):
        return cls.model_validate(value)
    return cls.model_validate(value, from_attributes=True)


def normalize_cast(cast) -> list[CharacterBrief]:
    out: list[CharacterBrief] = []
    for c in cast or []:
        out.append(_as_model(CharacterBrief, c))
    ids = [c.id for c in out]
    if len(set(ids)) != len(ids):
        raise StoryScriptInputError("Cast members must have unique ids")
    return out


def normalize_facts(facts) -> list[Fact]:
    out: list[Fact] = []
    for i, f in enumerate(facts or [], 1):
        if isinstance(f, Fact):
            out.append(f)
        elif isinstance(f, str):
            if f.strip():
                out.append(Fact(id=f"f{i}", text=f.strip()))
        elif isinstance(f, dict):
            text = (f.get("text") or f.get("claim") or f.get("fact") or "").strip()
            if text:
                out.append(Fact(id=str(f.get("id") or f"f{i}"), text=text,
                                source=str(f.get("source") or f.get("url") or ""),
                                date=str(f.get("date") or "")))
        else:
            out.append(Fact.model_validate(f, from_attributes=True))
    return out


def normalize_language(language: str | None) -> str:
    lang = (language or "en").strip().lower()
    if not re.fullmatch(r"[a-z]{2}", lang):
        raise StoryScriptInputError(f"language must be an ISO 639-1 code, got {language!r}")
    return lang


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the head writer of a faceless video studio. Your scripts are read aloud by a text to speech voice over still images and short clips, so every word must sound natural spoken out loud. You write into a fixed blueprint of numbered slots and return JSON only.

WRITING RULES
1. Narration is conversational and spoken, not a caption. Plain, concrete words.
2. Spell every number as words in the narration language. Never use digits, hyphens, dashes, ampersands, slashes, brackets (except the audio tags of rule 14), emoji, bullets, hashtags or links in narration or dialogue.
3. Keep every sentence under 25 words and vary sentence length.
4. Slot one is the hook: its first sentence must land within three seconds and follow the hook instruction.
5. Each middle slot carries exactly one idea and follows its beat job.
6. A slot marked REHOOK opens with a short line that reopens curiosity: an open question, a stakes reminder or a promise of what is coming.
7. Respect each slot's word target closely; together they make the runtime.
8. The last slot delivers the ending described in ENDING.

VISUALS
9. "direction" is for an image model, in English, one or two sentences: subject, action, setting, light, mood. Name characters by name only; never describe their face, body or clothes, the studio adds that. No art style words (realistic, cinematic, anime, 3D, illustration, painting and the like). Nothing written in the picture: no text, letters, numbers, signs, logos, brands or watermarks.
10. Alternate frames that show characters with frames of places or objects. Favor POV, handheld and close up framing for energy; open a new place with an establishing shot.
11. "camera" is one of: pov, handheld, establishing, close_up, over_the_shoulder, medium, wide, insert. Each slot has a suggested camera; keep it unless the story needs another.
12. "characters" lists the cast ids visible in the frame, and only those.
13. "kind" is still or clip as given in the slot, or card for a slot that is only a title or quote on a plain background.

DIALOGUE AND TEXT
14. Dialogue lines use cast ids. Lines are short, under 15 words, and in character. "emotion" is optional and must be one of: {tags}. Narration or a line may carry one more of these tags in square brackets at the start of a later sentence, never mid sentence, so a line has at most two tags.
15. "on_screen_text" is optional, at most five words, and never repeats the narration word for word.
16. "stat" shows what the voice cannot say precisely, as exact digits on a card. At most one per slot and not in every slot. Leave it null when the template has no stat cards.

STORY
17. Every episode must be a new situation with a new outcome. Never repeat a previous episode's situation and outcome.
18. Never use real brand names, logos or copyrighted characters. Never present fiction as real events.
"""

FACT_RULES = """FACT MODE
19. Every factual claim must come from FACTS. Never invent names, dates, numbers, quotes or events.
20. For each claim, add a source entry with the fact id and the claim in a few words. Dates carry their source.
21. A stat must quote a number that appears in the cited fact, and set fact_id.
22. If FACTS does not cover something the beat needs, do not guess: write around it and add a question to "questions" that starts with "Question:" naming the missing fact."""

NO_FACTS_RULES = """FACT MODE WITHOUT FACTS
19. This template requires sourced facts and none were provided. Do not state any specific fact: no names of real people beyond the idea, no dates, numbers, quotes or events presented as true.
20. Write each slot so it frames the beat without claims, and put the facts the slot needs into "questions", each starting with "Question:". Leave "sources" and "stat" empty."""

FICTION_RULES = """FICTION
19. This is fiction or speculation. "sources" stays empty. Do not present invented events as real history or news."""


def _slot_line(s: Slot, template: Template) -> str:
    jobs = " then ".join(f"{b.name}: {b.job}" for b in s.beats)
    flags = []
    if s.is_hook:
        flags.append("HOOK")
    if s.is_rehook:
        flags.append("REHOOK")
    if s.is_last:
        flags.append("ENDING")
    if s.silence_after:
        flags.append(f"hold {s.silence_after:g} s of silence after")
    flag_txt = (" | " + ", ".join(flags)) if flags else ""
    return (f"slot {s.number} | {jobs} | about {s.duration:.1f} s | about {s.words} words | "
            f"camera {s.camera} | kind {s.kind}{flag_txt}")


def _ending_text(template: Template) -> str:
    if template.ending == "loop":
        return ("LOOP: the last sentence must lead straight back into the first sentence of slot one, "
                "so the video can replay seamlessly. " + template.ending_note)
    if template.ending == "cliffhanger_vote":
        return ("CLIFFHANGER WITH VOTE: stop on an unresolved choice between two options. Fill "
                "\"vote_prompt\" with a short line asking viewers to vote in the comments, naming both "
                "options. " + template.ending_note)
    return ("PAYOFF: land the payoff in the last slot. Fill \"outro_title\" with three to five words, "
            "a title not a sentence. " + template.ending_note)


def _cast_block(cast: list[CharacterBrief]) -> str:
    if not cast:
        return "CAST: none. Use no recurring characters; show places, objects and anonymous figures."
    lines = ["CAST (use these ids):"]
    for c in cast:
        bits = [f"id {c.id}", f"name {c.name}"]
        if c.role:
            bits.append(f"role {c.role}")
        if c.species and c.species != "human":
            bits.append(f"species {c.species}")
        if c.personality:
            bits.append(f"personality {c.personality}")
        if c.catchphrase:
            bits.append(f"catchphrase {c.catchphrase}")
        lines.append("- " + "; ".join(bits))
    return "\n".join(lines)


def _series_block(series: SeriesBrief | None) -> str:
    if not series:
        return "SERIES: standalone episode."
    lines = [f"SERIES: {series.title or 'untitled'}, episode {series.episode_number}."]
    if series.logline:
        lines.append(f"Logline: {series.logline}")
    if series.world:
        lines.append(f"World: {series.world}")
    if series.tone:
        lines.append(f"Tone: {series.tone}")
    for r in series.rules:
        lines.append(f"Continuity rule: {r}")
    if series.recurring_elements:
        lines.append("Recurring elements to keep: " + "; ".join(series.recurring_elements))
    if series.previous_episodes:
        lines.append("Previous episodes (do not repeat their situation and outcome):")
        for i, e in enumerate(series.previous_episodes[-12:], 1):
            lines.append(f"- {e.title or 'episode'}: premise {e.premise or 'n/a'}; outcome {e.outcome or 'n/a'}")
    if series.avoid:
        lines.append("Avoid: " + "; ".join(series.avoid))
    return "\n".join(lines)


def _facts_block(facts: list[Fact]) -> str:
    if not facts:
        return "FACTS: none provided."
    lines = ["FACTS (the only material you may claim):"]
    for f in facts:
        extra = []
        if f.date:
            extra.append(f"date {f.date}")
        if f.source:
            extra.append(f"source {f.source}")
        lines.append(f"- {f.id}: {f.text}" + (f" ({'; '.join(extra)})" if extra else ""))
    return "\n".join(lines)


def _mode_block(template: Template) -> str:
    if template.dialogue_mode == "narration":
        return ("VOICE: one narrator carries the story. Dialogue is rare: at most one short line in a slot, "
                "only from a cast member, and it counts toward the slot's words.")
    if template.dialogue_mode == "dialogue":
        return "VOICE: characters carry the story in dialogue. Narration stays empty unless a slot needs one line."
    return ("VOICE: characters carry the story in dialogue with a light narrator. Narration is zero to "
            "twelve words a slot; dialogue makes up the rest of the slot's words.")


def _system(template: Template, facts: list[Fact]) -> str:
    base = SYSTEM_PROMPT.replace("{tags}", ", ".join(SAFE_AUDIO_TAGS))
    if template.fact_mode:
        base += "\n" + (FACT_RULES if facts else NO_FACTS_RULES)
    else:
        base += "\n" + FICTION_RULES
    return base


def _brief(plan: Plan, idea: str, cast: list[CharacterBrief], series: SeriesBrief | None,
           facts: list[Fact], narrator_voice: str | None) -> str:
    t = plan.template
    lang = LANGUAGE_NAMES.get(plan.language, plan.language)
    parts = [
        f"TEMPLATE: {t.name}. {t.pitch}",
        f"IDEA: {idea.strip()}",
        f"LANGUAGE: write narration, dialogue, on screen text, title, logline and vote prompt in {lang} "
        f"(ISO {plan.language}). Write direction in English.",
        f"RUNTIME: {plan.length_seconds} seconds, aspect {plan.aspect}, voice at about {plan.wpm} words a "
        f"minute. Total spoken words about {plan.word_target} (between {plan.word_min} and {plan.word_max}), "
        f"across {len(plan.slots)} slots.",
        _mode_block(t),
        f"HOOK INSTRUCTION: {plan.hook_formula}",
        f"THIS EPISODE'S VARIATION (adapt to the idea; it keeps episodes from repeating): situation archetype "
        f"\"{plan.situation}\", outcome direction \"{plan.outcome}\".",
        "ENDING: " + _ending_text(t),
        "STAT CARDS: allowed." if t.stat_cards else "STAT CARDS: not used in this template; stat stays null.",
    ]
    if t.policy_notes:
        parts.append("POLICY: " + " ".join(t.policy_notes))
    parts.append(_cast_block(cast))
    parts.append(_series_block(series))
    if t.fact_mode:
        parts.append(_facts_block(facts))
    if narrator_voice:
        parts.append(f"NARRATOR VOICE: {narrator_voice}.")
    return "\n\n".join(parts)


# --------------------------------------------------------------------------
# Validation of LLM output (semantic; feeds the retry loop)
# --------------------------------------------------------------------------

def _scene_words(s: LLMScene) -> int:
    return word_count(s.narration) + sum(word_count(d.text) for d in s.dialogue)


def _validator(slots: list[Slot], template: Template, *, check_total: tuple[int, int] | None):
    expected = {s.number for s in slots}

    def check(obj) -> list[str]:
        problems: list[str] = []
        scenes = obj.scenes
        got = [s.slot for s in scenes]
        if sorted(got) != sorted(expected) or len(got) != len(set(got)):
            problems.append(f"scenes must cover slots {sorted(expected)} exactly once each, got {sorted(got)}")
        for s in scenes:
            if template.dialogue_mode == "narration" and not s.narration.strip():
                problems.append(f"slot {s.slot}: narration is empty")
            if not s.narration.strip() and not s.dialogue:
                problems.append(f"slot {s.slot}: needs narration or dialogue")
        if check_total and not problems:
            total = sum(_scene_words(s) for s in scenes)
            lo, hi = check_total
            if total < lo or total > hi:
                problems.append(f"total spoken words {total} is outside {lo} to {hi}; adjust slot lengths")
        return problems

    return check


def _outline_validator(slots: list[Slot]):
    expected = sorted(s.number for s in slots)

    def check(obj: LLMOutline) -> list[str]:
        got = sorted(o.slot for o in obj.outline)
        return [] if got == expected else [f"outline must cover slots {expected} exactly once each"]

    return check


# --------------------------------------------------------------------------
# Post-processing
# --------------------------------------------------------------------------

_DIGIT_CLAIM = re.compile(r"\d")


def _likeness_map(cast: list[CharacterBrief]) -> dict[str, str]:
    out = {}
    for c in cast:
        clause = c.clause()
        out[c.id] = clause or f"{c.name}, a {c.species or 'character'}"
    return out


def _resolve_char(ref: str, cast: list[CharacterBrief]) -> str | None:
    r = (ref or "").strip()
    for c in cast:
        if r == c.id:
            return c.id
    low = r.lower()
    for c in cast:
        if low == c.name.lower():
            return c.id
    return None


def _build_scene(raw: LLMScene, slot: Slot, *, plan: Plan, cast: list[CharacterBrief],
                 facts: dict[str, Fact], clauses: dict[str, str], warnings: list[str],
                 scene_id: str | None = None, keep_kind: str | None = None) -> Scene:
    t = plan.template
    lang = plan.language
    sid = scene_id or f"s{slot.number}"

    raw_narr = raw.narration or ""
    narration = tts_safe(raw_narr, lang, keep_tags=True)
    names = {c.id: c.name for c in cast}

    dialogue: list[DialogueLine] = []
    for d in raw.dialogue:
        cid = _resolve_char(d.character_id, cast)
        if cid is None:
            warnings.append(f"{sid}: dropped a line from unknown character {d.character_id!r}")
            continue
        text = tts_safe(d.text, lang, keep_tags=True)
        if text:
            dialogue.append(DialogueLine(character_id=cid, character=names[cid], text=text,
                                         emotion=normalize_audio_tag(d.emotion)))

    chars: list[str] = []
    for ref in raw.characters:
        cid = _resolve_char(ref, cast)
        if cid and cid not in chars:
            chars.append(cid)

    camera = raw.camera if raw.camera in CAMERAS else slot.camera
    kind = keep_kind or slot.kind
    if keep_kind is None and (raw.kind or "") == "card":
        kind = "card"
    direction = strip_style_words(raw.direction)
    visual_prompt = compose_visual_prompt([clauses[c] for c in chars], direction)

    stat = None
    if raw.stat and t.stat_cards and raw.stat.value.strip():
        stat = Stat(value=raw.stat.value.strip()[:24], label=raw.stat.label.strip()[:60],
                    fact_id=raw.stat.fact_id)
        if t.fact_mode:
            f = facts.get(stat.fact_id or "")
            digits = re.sub(r"[^\d]", "", stat.value)
            if not f or (digits and digits not in re.sub(r"[^\d]", "", f.text)):
                warnings.append(f"{sid}: removed a stat that does not match a provided fact")
                stat = None

    sources: list[SourceRef] = []
    for src in raw.sources:
        f = facts.get(src.fact_id)
        if not f:
            warnings.append(f"{sid}: removed a source citing unknown fact {src.fact_id!r}")
            continue
        sources.append(SourceRef(fact_id=f.id, claim=src.claim.strip(), source=f.source, date=f.date))

    questions = [q.strip() if q.strip().lower().startswith("question:") else f"Question: {q.strip()}"
                 for q in raw.questions if q and q.strip()]
    notes = ""
    if t.fact_mode and facts and not sources and _DIGIT_CLAIM.search(raw_narr):
        notes = "Contains a specific number without a cited fact. Check it or add a source."
        warnings.append(f"{sid}: {notes}")

    on_screen = (raw.on_screen_text or "").strip() or None
    if on_screen:
        on_screen = " ".join(on_screen.split()[:6])

    scene = Scene(
        id=sid, index=slot.number - 1, beat=slot.beat.id, beat_name=slot.beat.name,
        narration=narration, narration_emotion=normalize_audio_tag(raw.narration_emotion),
        dialogue=dialogue,
        shot=ShotPlan(kind=kind, camera=camera, characters=chars, direction=direction,
                      visual_prompt=visual_prompt, images=1 if kind != "still" else slot.images,
                      clip_seconds=(min(15.0, max(1.0, round(slot.duration, 1))) if kind == "clip" else None),
                      motion="push_in" if slot.number % 2 else "pull_out"),
        on_screen_text=on_screen, stat=stat, sources=sources, questions=questions,
        is_hook=slot.is_hook, is_rehook=slot.is_rehook,
        dramatization=bool(t.dramatization_label),
        silence_after=slot.silence_after, word_target=slot.words, notes=notes,
    )
    return scene


def _retime(scenes: list[Scene], wpm: int, min_scene: float = 2.0) -> float:
    """Estimated start and duration from spoken words; returns the total."""
    t = 0.0
    for s in scenes:
        words = s.spoken_words()
        gaps = 0.25 * max(0, len(s.dialogue) - 1) + (0.2 if s.dialogue and s.narration else 0.0)
        dur = max(min_scene, seconds_for_words(words, wpm) + gaps) + s.silence_after
        s.start = round(t, 2)
        s.duration = round(dur, 2)
        t += dur
    return round(t, 2)


def _cap_stats(scenes: list[Scene], warnings: list[str]) -> None:
    limit = max(1, len(scenes) // 3)
    with_stat = [s for s in scenes if s.stat]
    if len(with_stat) > limit:
        keep = sorted(with_stat, key=lambda s: (s.stat.fact_id is None, s.index))[:limit]
        for s in with_stat:
            if s not in keep:
                s.stat = None
        warnings.append(f"Kept {limit} stat cards; stats are for some scenes, not every scene.")


def _quality_warnings(script: Script, plan: Plan) -> None:
    w = script.warnings
    narrated = plan.template.words_per_scene is not None
    for s in script.scenes:
        n = s.spoken_words()
        if narrated and plan.template.dialogue_mode == "narration":
            if n < 20:
                w.append(f"{s.id}: {n} words; under twenty and the cut feels abrupt.")
            elif n > 35:
                w.append(f"{s.id}: {n} words; over thirty five and the images go stale.")
    if script.word_count < plan.word_min * 0.85 or script.word_count > plan.word_max * 1.15:
        w.append(f"Script has {script.word_count} words against a budget of {plan.word_target}.")
    run = 0
    for s in script.scenes:
        run = run + 1 if s.shot.characters else 0
        if run == 4:
            w.append(f"{s.id}: four character frames in a row; alternate with a place or object frame.")


# --------------------------------------------------------------------------
# LLM orchestration
# --------------------------------------------------------------------------

async def _draft_single(db, plan, system, brief, user_id) -> tuple[LLMHeader, list[LLMScene], str]:
    slots_txt = "\n".join(_slot_line(s, plan.template) for s in plan.slots)
    prompt = f"{brief}\n\nBLUEPRINT (write one scene per slot):\n{slots_txt}"
    lo = int(plan.word_min * 0.8)
    hi = int(math.ceil(plan.word_max * 1.25))
    obj, choice = await llm.complete_json(
        db, system=system, prompt=prompt, schema=LLMDraft, feature="storyscript_draft",
        validate=_validator(plan.slots, plan.template, check_total=(lo, hi)),
        temperature=0.85, user_id=user_id,
    )
    return obj, obj.scenes, choice.label


async def _draft_chunked(db, plan, system, brief, user_id) -> tuple[LLMHeader, list[LLMScene], str]:
    slots_txt = "\n".join(_slot_line(s, plan.template) for s in plan.slots)
    outline_prompt = (
        f"{brief}\n\nBLUEPRINT:\n{slots_txt}\n\nSTEP ONE OF TWO: return the header fields and an "
        f"\"outline\" with one entry per slot: the slot number and a one sentence summary of what "
        f"happens in it. Do not write the scenes yet."
    )
    outline, choice = await llm.complete_json(
        db, system=system, prompt=outline_prompt, schema=LLMOutline, feature="storyscript_outline",
        validate=_outline_validator(plan.slots), temperature=0.85, user_id=user_id,
    )
    summaries = {o.slot: o.summary for o in outline.outline}
    outline_txt = "\n".join(f"slot {k}: {summaries[k]}" for k in sorted(summaries))
    header_txt = (f"TITLE: {outline.title}\nPREMISE: {outline.premise}\nOUTCOME: {outline.outcome}\n"
                  f"ENDING LINE: {outline.ending_line}")

    chunks = [plan.slots[i:i + CHUNK_SCENES] for i in range(0, len(plan.slots), CHUNK_SCENES)]
    sem = asyncio.Semaphore(CHUNK_CONCURRENCY)

    async def write(chunk: list[Slot]) -> list[LLMScene]:
        lines = "\n".join(_slot_line(s, plan.template) for s in chunk)
        words = sum(s.words for s in chunk)
        before = chunk[0].number - 1
        after = chunk[-1].number + 1
        ctx = []
        if before in summaries:
            ctx.append(f"The slot before this part: {summaries[before]}")
        if after in summaries:
            ctx.append(f"The slot after this part: {summaries[after]}")
        prompt = (
            f"{brief}\n\n{header_txt}\n\nFULL OUTLINE:\n{outline_txt}\n\nSTEP TWO: write only these "
            f"slots, following the outline, about {words} spoken words in total. Return "
            f"{{\"scenes\": [...]}}.\n{lines}\n" + "\n".join(ctx)
        )
        async with sem:
            obj, _ = await llm.complete_json(
                db, system=system, prompt=prompt, schema=LLMChunk, feature="storyscript_draft",
                validate=_validator(chunk, plan.template,
                                    check_total=(int(words * 0.7), int(math.ceil(words * 1.35)))),
                temperature=0.8, user_id=user_id, choice=choice,
            )
        return obj.scenes

    parts = await asyncio.gather(*(write(c) for c in chunks))
    scenes = [s for part in parts for s in part]
    return outline, scenes, choice.label


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

async def draft_script(db, *, template_id, idea, length_seconds, aspect, cast, series,
                       facts=None, language="en", narrator_voice=None,
                       seed: int | None = None, user_id: int | None = None) -> Script:
    """Draft a full script for a template.

    ``cast`` is a list of CharacterBrief (or dicts or ORM rows with the same
    fields); ``series`` a SeriesBrief, dict or None; ``facts`` a list of
    strings, dicts ({text, source, date, id}) or Fact. ``seed`` makes the
    episode's variation reproducible; by default it derives from the series id
    and episode number, or is random for a standalone video.

    Raises StoryScriptInputError, LLMNotConfigured, LLMCallFailed or
    InvalidLLMOutput (after two retries with the validation error fed back).
    """
    try:
        template = get_template(template_id)
    except KeyError as exc:
        raise StoryScriptInputError(str(exc)) from exc
    if aspect not in ASPECTS:
        raise StoryScriptInputError(f"aspect must be one of {', '.join(ASPECTS)}")
    if not idea or not str(idea).strip():
        raise StoryScriptInputError("idea is required")
    idea = str(idea).strip()[:4000]
    try:
        length_seconds = int(round(float(length_seconds)))
    except (TypeError, ValueError) as exc:
        raise StoryScriptInputError("length_seconds must be a number") from exc
    max_len = max_length_for(template, aspect)
    if not template.length.min_seconds <= length_seconds <= max_len:
        raise StoryScriptInputError(
            f"{template.name} runs {template.length.min_seconds} to {max_len} seconds at {aspect}")
    language = normalize_language(language)
    cast_l = normalize_cast(cast)
    series_b = _as_model(SeriesBrief, series)
    facts_l = normalize_facts(facts)

    seed_v = _seed_for(series_b, seed)
    plan = plan_script(template, length_seconds=length_seconds, aspect=aspect,
                       language=language, seed=seed_v, series=series_b)
    system = _system(template, facts_l)
    brief = _brief(plan, idea, cast_l, series_b, facts_l, narrator_voice)

    if len(plan.slots) <= SINGLE_CALL_MAX_SCENES:
        header, raw_scenes, model_label = await _draft_single(db, plan, system, brief, user_id)
    else:
        header, raw_scenes, model_label = await _draft_chunked(db, plan, system, brief, user_id)

    warnings: list[str] = []
    if aspect not in template.aspects:
        warnings.append(f"{aspect} is not a recommended aspect for {template.name}.")
    clauses = _likeness_map(cast_l)
    for c in cast_l:
        if not c.clause():
            warnings.append(f"{c.name} has no likeness clause; describe the character for consistent images.")
    facts_by_id = {f.id: f for f in facts_l}
    by_slot = {s.slot: s for s in raw_scenes}
    scenes = [
        _build_scene(by_slot[slot.number], slot, plan=plan, cast=cast_l, facts=facts_by_id,
                     clauses=clauses, warnings=warnings)
        for slot in plan.slots
    ]
    _cap_stats(scenes, warnings)
    speaking = _retime(scenes, plan.wpm)

    script = Script(
        template_id=template.id,
        title=header.title.strip(),
        logline=header.logline.strip(), premise=header.premise.strip(),
        situation=header.situation.strip() or plan.situation, outcome=header.outcome.strip(),
        language=language, aspect=aspect, length_seconds=length_seconds,
        estimated_seconds=round(speaking + plan.outro_seconds, 2), wpm=plan.wpm,
        word_budget=plan.word_target, word_count=sum(s.spoken_words() for s in scenes),
        seed=seed_v, hook_formula=plan.hook_formula, ending=template.ending,
        ending_line=tts_safe(header.ending_line, language) if header.ending_line else "",
        vote_prompt=((header.vote_prompt or "").strip() or None) if template.ending == "cliffhanger_vote" else None,
        outro_title=" ".join((header.outro_title or "").split()[:5]),
        scenes=scenes, cast_ids=[c.id for c in cast_l],
        narrator_voice=narrator_voice or (template.voice.suggested_voices[0] if template.voice.suggested_voices else None),
        series_id=series_b.id if series_b else None,
        episode_number=series_b.episode_number if series_b else None,
        fact_mode=template.fact_mode, facts=facts_l,
        needs_facts=template.fact_mode and not facts_l,
        dramatization_label=template.dramatization_label,
        visual_style=template.visual_style, caption_preset=template.caption_preset,
        music=template.music.model_copy(deep=True),
        tts_text_normalization="auto" if language == "en" else "on",
        warnings=warnings, model=model_label,
        cast_clauses=clauses, cast_names={c.id: c.name for c in cast_l},
    )
    if template.ending == "cliffhanger_vote" and not script.vote_prompt:
        script.warnings.append("No vote prompt was written for the cliffhanger.")
    if script.needs_facts:
        script.warnings.append("Fact mode without facts: scenes hold questions, not claims. Add facts and redraft before voicing.")
    _quality_warnings(script, plan)
    return script


def _script_template(script: Script) -> Template:
    try:
        return get_template(script.template_id)
    except KeyError as exc:
        raise StoryScriptInputError(str(exc)) from exc


async def revise_scene(db, *, script, scene_id, instruction, cast=None,
                       user_id: int | None = None) -> Scene:
    """Rewrite one scene per an instruction, keeping continuity and timing.

    The scene keeps its id, index, beat, flags and word target; the neighbors'
    text is given to the model for continuity. Likeness clauses come from
    ``cast`` when given, otherwise from the clauses stored on the script.
    A ``user_media`` scene keeps its kind (the user's own media stays).
    """
    script = _as_model(Script, script)
    if not instruction or not str(instruction).strip():
        raise StoryScriptInputError("instruction is required")
    idx = next((i for i, s in enumerate(script.scenes) if s.id == scene_id), None)
    if idx is None:
        raise StoryScriptInputError(f"Unknown scene id {scene_id!r}")
    template = _script_template(script)
    scene = script.scenes[idx]
    cast_l = normalize_cast(cast) if cast else [
        CharacterBrief(id=cid, name=script.cast_names.get(cid, cid),
                       likeness_clause=script.cast_clauses.get(cid, ""))
        for cid in (script.cast_ids or list(script.cast_clauses))
    ]
    clauses = _likeness_map(cast_l)
    facts_by_id = {f.id: f for f in script.facts}

    target = scene.word_target or max(8, scene.spoken_words())
    slot = Slot(number=scene.index + 1, beat=next((b for b in template.beats if b.id == scene.beat), template.beats[0]),
                beats=[b for b in template.beats if b.id == scene.beat] or [template.beats[0]],
                start=scene.start, duration=scene.duration, words=target, camera=scene.shot.camera,
                kind=scene.shot.kind if scene.shot.kind in ("still", "clip", "card") else "still",
                images=scene.shot.images, is_hook=scene.is_hook, is_rehook=scene.is_rehook,
                is_last=(idx == len(script.scenes) - 1), silence_after=scene.silence_after)
    plan = Plan(template=template, length_seconds=script.length_seconds, aspect=script.aspect,
                language=script.language, seed=script.seed, wpm=script.wpm,
                word_target=script.word_budget, word_min=0, word_max=0, outro_seconds=0.0,
                hook_formula=script.hook_formula, situation=script.situation, outcome=script.outcome)

    def describe(s: Scene) -> str:
        lines = [f"narration: {s.narration}"] if s.narration else []
        lines += [f"{d.character} ({d.character_id}): {d.text}" for d in s.dialogue]
        lines.append(f"direction: {s.shot.direction}")
        return "\n".join(lines)

    ctx = [f"SCRIPT: {script.title}. Premise: {script.premise}. Outcome: {script.outcome}."]
    if idx > 0:
        ctx.append("PREVIOUS SCENE:\n" + describe(script.scenes[idx - 1]))
    ctx.append(f"CURRENT SCENE (slot {slot.number}):\n" + describe(scene))
    if idx + 1 < len(script.scenes):
        ctx.append("NEXT SCENE:\n" + describe(script.scenes[idx + 1]))
    lang = LANGUAGE_NAMES.get(script.language, script.language)
    prompt = "\n\n".join([
        f"TEMPLATE: {template.name}. {template.pitch}",
        f"LANGUAGE: {lang} for spoken text and on screen text; direction in English.",
        _mode_block(template),
        _cast_block(cast_l),
        _facts_block(script.facts) if template.fact_mode else "",
        *ctx,
        "SLOT TO REWRITE:\n" + _slot_line(slot, template),
        f"INSTRUCTION: {str(instruction).strip()[:2000]}",
        f"Rewrite only this scene. Keep it about {target} spoken words so the timing holds, keep its beat "
        f"job, and make it flow from the previous scene into the next one. Return {{\"scene\": {{...}}}} "
        f"with slot {slot.number}.",
    ])

    def check(obj: LLMRevision) -> list[str]:
        problems = []
        if obj.scene.slot != slot.number:
            problems.append(f"scene.slot must be {slot.number}")
        n = _scene_words(obj.scene)
        if template.dialogue_mode == "narration" and not obj.scene.narration.strip():
            problems.append("narration is empty")
        if n < max(3, int(target * 0.6)) or n > int(math.ceil(target * 1.5)) + 2:
            problems.append(f"spoken words {n} should be close to {target}")
        return problems

    obj, _ = await llm.complete_json(
        db, system=_system(template, script.facts), prompt=prompt, schema=LLMRevision,
        feature="storyscript_revise", validate=check, temperature=0.8, user_id=user_id,
    )
    warnings: list[str] = []
    keep = "user_media" if scene.shot.kind == "user_media" else None
    new = _build_scene(obj.scene, slot, plan=plan, cast=cast_l, facts=facts_by_id, clauses=clauses,
                       warnings=warnings, scene_id=scene.id, keep_kind=keep)
    new.index = scene.index
    new.dramatization = scene.dramatization
    if keep:
        new.shot.images = scene.shot.images
    _retime([new], script.wpm)
    new.start = scene.start
    if warnings:
        new.notes = (new.notes + " " + " ".join(warnings)).strip()
    return new
