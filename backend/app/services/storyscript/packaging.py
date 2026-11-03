"""package: titles, description, tags, chapters, thumbnails, disclosure.

Deterministic parts (always): chapters from scene timing, the sources
section, the disclosure line and per-platform advice, and the likeness clause
at the front of each thumbnail prompt. The LLM writes the creative parts
(titles from the template's formulas, the description's first line, tags,
chapter names, thumbnail ideas); if it is not configured or fails, a
deterministic fallback fills them so packaging never blocks a project.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from pydantic import BaseModel, ConfigDict, Field

from . import llm, policy
from .drafting import LANGUAGE_NAMES, _as_model, normalize_cast
from .errors import InvalidLLMOutput, LLMCallFailed, LLMNotConfigured, StoryScriptInputError
from .models import Chapter, Packaging, Script, Template, ThumbnailPrompt
from .templates import get_template
from .text import compose_visual_prompt, strip_style_words

logger = logging.getLogger(__name__)

MIN_CHAPTER_SECONDS = 10.0
TITLE_MAX = 100
TAGS_MAX_CHARS = 450


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


class LLMThumb(_Loose):
    direction: str = Field(min_length=5)
    text: str = Field(min_length=2)


class LLMPackage(_Loose):
    titles: list[str] = Field(min_length=3)
    first_line: str = Field(min_length=10)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    chapter_titles: list[str] = Field(default_factory=list)
    thumbnails: list[LLMThumb] = Field(min_length=3)


SYSTEM = """You package faceless videos for YouTube Shorts, TikTok, Reels and YouTube long-form. Write titles that create curiosity without lying, a description whose first line works as the preview, search tags, chapter names and thumbnail ideas.

Rules:
- Three titles, each following one of the given title formulas (fill its placeholders), under 70 characters, no emoji, no hashtags, no clickbait that the video does not pay off.
- first_line: one sentence under 150 characters that makes a viewer want to watch; never a summary of the ending.
- description: two to four short sentences after the first line; no links, no hashtags, no sources (the studio adds them).
- tags: eight to fifteen search phrases, lower case.
- chapter_titles: one short title per chapter listed, in order, two to five words each.
- thumbnails: three ideas featuring the main character. "direction" is for an image model: the character's expression and pose, one prop or setting element, strong contrast, an uncluttered background with clear empty space for text. Name the character only; never describe their looks. No art style words and nothing written in the image. "text" is two to four words the studio will overlay later.
- Write titles, first_line, description and thumbnail text in the requested language. Write direction in English."""


def _ts(seconds: float) -> str:
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def build_chapters(script: Script, template: Template | None, aspect: str) -> list[Chapter]:
    """Chapters from beat boundaries, for long-form only (16:9 and at least 3 minutes).

    YouTube needs the first chapter at 0:00, at least three chapters and each
    at least ten seconds long; anything shorter merges into its neighbor.
    """
    total = script.estimated_seconds or (script.scenes[-1].start + script.scenes[-1].duration if script.scenes else 0)
    if aspect != "16:9" or total < 180 or not script.scenes:
        return []
    groups: list[tuple[float, str]] = []
    prev_beat = None
    for sc in script.scenes:
        if sc.beat != prev_beat:
            groups.append((sc.start, sc.beat_name or sc.beat))
            prev_beat = sc.beat
    # A chapter shorter than the minimum folds into the one before it.
    merged: list[list] = []
    for start, name in groups:
        if merged and start - merged[-1][0] < MIN_CHAPTER_SECONDS:
            continue
        merged.append([start, name])
    if len(merged) >= 2 and total - merged[-1][0] < MIN_CHAPTER_SECONDS:
        merged.pop()
    if merged:
        merged[0][0] = 0.0
    if len(merged) < 3:
        return []
    return [Chapter(start=round(s, 2), timestamp=_ts(s), title=n) for s, n in merged]


def _main_character(script: Script) -> list[str]:
    counts: Counter[str] = Counter()
    for sc in script.scenes:
        counts.update(sc.shot.characters)
        counts.update(d.character_id for d in sc.dialogue)
    if counts:
        return [counts.most_common(1)[0][0]]
    return script.cast_ids[:1]


def _sources_section(script: Script) -> str | None:
    if not script.fact_mode or not script.facts:
        return None
    cited = {src.fact_id for sc in script.scenes for src in sc.sources}
    if sc_stats := {sc.stat.fact_id for sc in script.scenes if sc.stat and sc.stat.fact_id}:
        cited |= sc_stats
    facts = [f for f in script.facts if f.id in cited] or script.facts
    lines = ["Sources:"]
    for f in facts:
        bits = [f.text]
        if f.source:
            bits.append(f.source)
        if f.date:
            bits.append(f.date)
        lines.append("- " + " | ".join(bits))
    return "\n".join(lines)


def _fill_formula(formula: str, script: Script, character: str) -> str:
    topic = script.title or (script.premise.split(".")[0] if script.premise else "this story")
    values = {
        "character": character or topic, "subject": character or topic, "topic": topic,
        "episode": str(script.episode_number or 1), "number": str(max(3, min(10, len(script.scenes)))),
    }

    def rep(m: re.Match) -> str:
        return values.get(m.group(1), topic)

    out = re.sub(r"\{(\w+)\}", rep, formula)
    return out[:TITLE_MAX]


def _clean_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    total = 0
    for t in tags:
        t = re.sub(r"[#<>\"]", "", (t or "").strip().lower())
        t = " ".join(t.split())[:60]
        if not t or t in out:
            continue
        if total + len(t) + 1 > TAGS_MAX_CHARS:
            break
        out.append(t)
        total += len(t) + 1
    return out


def _thumb_text(text: str) -> str:
    words = re.sub(r"[^\w\s'?!]", "", text or "").split()
    return " ".join(words[:4]) if len(words) >= 2 else " ".join(words + ["now"])[:40]


def _thumb_prompt(script: Script, chars: list[str], direction: str, aspect: str) -> str:
    space = "leave clear empty space in the top third" if aspect in ("9:16", "4:5") else \
        "leave clear empty space on one side"
    clauses = [script.cast_clauses.get(c, script.cast_names.get(c, c)) for c in chars]
    d = strip_style_words(direction)
    return compose_visual_prompt(clauses, f"{d}, {space}" if d else space)


def _fallback(script: Script, template: Template | None, character: str) -> LLMPackage:
    formulas = (template.title_formulas if template else []) or ["{topic}", "{topic}, explained", "The story of {topic}"]
    titles = [_fill_formula(f, script, character) for f in formulas[:3]]
    while len(titles) < 3:
        titles.append(script.title[:TITLE_MAX] or "Untitled")
    first = script.logline or script.premise or script.title
    hook = script.scenes[0].narration if script.scenes else ""
    first_line = (hook.split(". ")[0].rstrip(".") + ".") if hook else first
    who = character or "the hero"
    thumbs = [
        LLMThumb(direction=f"close up of {who} with a shocked expression, dramatic rim light", text="Wait for it"),
        LLMThumb(direction=f"{who} pointing at a key object from the story, high contrast", text="Nobody expected this"),
        LLMThumb(direction=f"{who} in a tense moment from the story, strong backlight", text="Watch till the end"),
    ]
    tags = (template.tags if template else []) + [w for w in re.findall(r"[a-z]{4,}", script.title.lower())][:6]
    return LLMPackage(titles=titles, first_line=first_line[:150], description=script.logline or script.premise,
                      tags=tags, chapter_titles=[], thumbnails=thumbs)


async def package(db, *, script, aspect, cast=None, user_id: int | None = None) -> Packaging:
    """Titles, description, tags, chapters, thumbnail prompts and disclosure advice.

    ``aspect`` is the export being packaged (a 16:9 long-form gets chapters; a
    vertical cut gets vertical thumbnail composition). ``cast`` (optional)
    lets the disclosure advice see real-person characters.
    """
    s = _as_model(Script, script)
    cast_l = normalize_cast(cast) if cast else []
    if aspect not in ("9:16", "16:9", "1:1", "4:5"):
        raise StoryScriptInputError("aspect must be 9:16, 16:9, 1:1 or 4:5")
    try:
        tpl: Template | None = get_template(s.template_id)
    except KeyError:
        tpl = None
    main = _main_character(s)
    main_name = s.cast_names.get(main[0], "") if main else ""
    chapters = build_chapters(s, tpl, aspect)

    lang = LANGUAGE_NAMES.get(s.language, s.language)
    spoken = " ".join(sc.narration for sc in s.scenes[:6])
    prompt = "\n".join([
        f"LANGUAGE: {lang}",
        f"TEMPLATE: {tpl.name if tpl else s.template_id}. Title formulas: " +
        (" | ".join(tpl.title_formulas) if tpl and tpl.title_formulas else "free") + ".",
        f"Description guidance: {tpl.description_formula}" if tpl and tpl.description_formula else "",
        f"WORKING TITLE: {s.title}",
        f"LOGLINE: {s.logline}",
        f"PREMISE: {s.premise}",
        f"MAIN CHARACTER: {main_name or 'none (use the most striking object or place instead)'}",
        f"EPISODE: {s.episode_number}" if s.episode_number else "",
        f"VOTE PROMPT: {s.vote_prompt}" if s.vote_prompt else "",
        f"OPENING NARRATION: {spoken[:1200]}",
        f"CHAPTERS ({len(chapters)}): " + "; ".join(f"{c.timestamp} {c.title}" for c in chapters)
        if chapters else "CHAPTERS: none, return an empty chapter_titles list.",
    ])

    model_label = None
    try:
        raw, choice = await llm.complete_json(
            db, system=SYSTEM, prompt=prompt, schema=LLMPackage, feature="storyscript_package",
            temperature=0.8, user_id=user_id, max_tokens=3000,
        )
        model_label = choice.label
    except (LLMNotConfigured, InvalidLLMOutput, LLMCallFailed) as exc:
        logger.warning(f"storyscript: packaging LLM unavailable, using templates: {type(exc).__name__}")
        raw = _fallback(s, tpl, main_name)

    titles = [" ".join(t.split())[:TITLE_MAX] for t in raw.titles if t.strip()][:3]
    if len(titles) < 3:
        titles += _fallback(s, tpl, main_name).titles[: 3 - len(titles)]
    if chapters and len(raw.chapter_titles) == len(chapters):
        for c, t in zip(chapters, raw.chapter_titles):
            if t.strip():
                c.title = " ".join(t.split())[:60]

    first_line = " ".join(raw.first_line.split())[:150]
    sources = _sources_section(s)
    disclosure = policy.disclosure_line(s, tpl, cast_l)
    tags = _clean_tags(list(raw.tags) + (tpl.tags if tpl else []))
    hashtags = ["#" + re.sub(r"[^a-z0-9]", "", t) for t in tags[:3] if re.sub(r"[^a-z0-9]", "", t)]

    body = [first_line]
    if raw.description.strip():
        body.append(" ".join(raw.description.split()))
    if s.vote_prompt:
        body.append(s.vote_prompt)
    if chapters:
        body.append("Chapters:\n" + "\n".join(f"{c.timestamp} {c.title}" for c in chapters))
    if sources:
        body.append(sources)
    body.append(disclosure)
    if hashtags:
        body.append(" ".join(hashtags))
    description = "\n\n".join(body)

    thumbs = [
        ThumbnailPrompt(prompt=_thumb_prompt(s, main, t.direction, aspect), text=_thumb_text(t.text),
                        characters=list(main))
        for t in raw.thumbnails[:3]
    ]
    out = Packaging(
        titles=titles, description=description, first_line=first_line, sources_section=sources,
        disclosure_line=disclosure, tags=tags, hashtags=hashtags, chapters=chapters,
        thumbnail_prompts=thumbs, disclosure_advice=policy.disclosure_advice(s, tpl, cast_l),
    )
    if model_label is None:
        logger.info("storyscript: packaging used deterministic fallback")
    return out
