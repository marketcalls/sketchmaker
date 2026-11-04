"""Handoff from a Story Room thread to a Faceless Studio project.

No LLM call and no provider call: the shot list becomes a storyscript Script directly, so
the user lands on a scripted project and the handoff costs nothing. It all runs under the
caller's write lock, which is safe only because of that. Each shot is one Scene:

- voiceover becomes the narration, dialogue lines keep their speaker (the
  saved character's id) and delivery (as the Eleven v4 emotion tag word);
- shot kind "clip" for a shot with camera motion or B-roll, "still" otherwise;
- the storyscript camera is the nearest match of shot size and move;
- visual_prompt is the likeness clauses of the characters in frame, then the
  environment, then the action (the Faceless style is added at generation);
- on_screen_text is kept; scene timing comes from the shot durations.

Unsaved characters are saved to faceless_character first (fictional only).
The script is saved through the same validation and version path as
PUT /api/faceless/projects/{id}/script (scripts.validate_script and
scripts.apply_script), which also runs the compliance and originality checks.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.models.faceless import FacelessProject
from app.services.faceless import catalog, consent, grade, scripts
from app.services.faceless.errors import InvalidRequest

from . import library
from .models import CastEntry, Shot, StoryDoc

logger = logging.getLogger(__name__)

MAX_PROJECTS = 500   # same cap as POST /api/faceless/projects

# Template picked when the user does not choose one, by format, first fit wins.
DEFAULT_TEMPLATES = {
    "story": ("micro_drama", "what_if", "reel", "original_horror", "explainer"),
    "ad": ("reel", "what_if", "micro_drama", "explainer", "business_story"),
}

_CAMERA_FOR_TYPE = {
    "establishing": "establishing", "aerial": "establishing", "wide": "wide", "tracking": "wide",
    "medium": "medium", "two_shot": "medium", "close_up": "close_up", "extreme_close_up": "close_up",
    "insert": "insert", "cutaway": "insert", "over_the_shoulder": "over_the_shoulder", "pov": "pov",
}
_MOTION_FOR_CAMERA = {
    "static": "none", "dolly_in": "push_in", "zoom": "push_in", "tilt": "push_in", "crane": "pull_out",
    "dolly_out": "pull_out", "rack_focus": "push_in", "handheld": "push_in",
}
# The director's camera as the clip prompt's one move (storyscript CameraMove).
_MOVE_FOR_CAMERA = {
    "static": "static", "tilt": "tilt_up", "dolly_in": "push_in", "dolly_out": "pull_out",
    "tracking": "tracking", "handheld": "handheld", "crane": "crane_up", "orbit": "orbit",
    "whip_pan": "whip_pan", "zoom": "push_in", "rack_focus": "rack_focus",
}
# Story Room transitions as Faceless scene transitions. Cuts are hard unless
# the director asked for a dissolve or a fade; J and L cuts keep their sound
# offsets. Smash cuts land on a hit, whip pans on a whoosh.
_TRANSITION = {
    "cut": "cut", "jump_cut": "cut", "match_cut": "cut", "smash_cut": "cut", "cross_cut": "cut",
    "whip_pan": "cut", "dissolve": "crossfade", "fade_in": "dip_black", "fade_out": "dip_black",
    "j_cut": "j_cut", "l_cut": "l_cut",
}
_SFX = {"smash_cut": "hit", "whip_pan": "whoosh"}
_REGISTERS = ("cinematic", "ugc", "documentary", "animated")


def _get(obj, key: str, default=None):
    """A field of a pydantic model or dict; the Story Room document gains
    fields (products, props, keyframes, register) over time."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _clean_spoken(text: str) -> str:
    """TTS-safe text: no stage directions in brackets or asterisks."""
    text = re.sub(r"\[[^\]]*\]|\*[^*]*\*", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _emotion(delivery: str) -> str | None:
    """The first word of the delivery note that is an Eleven v4 audio tag
    (or a known alias), else None: an unknown tag would be read aloud."""
    from app.services.storyscript.text import normalize_audio_tag

    for word in re.findall(r"[A-Za-z]+", delivery or "")[:6]:
        tag = normalize_audio_tag(word)
        if tag:
            return tag
    return None


def _products(doc: StoryDoc) -> dict[str, dict]:
    """Approved products by key: name, photo and what must not change."""
    out = {}
    for p in _get(doc, "products", None) or []:
        key, url = _get(p, "key", ""), _get(p, "image_url", None)
        if key and url and _get(p, "image_approved", False):
            out[key] = {"key": key, "name": (_get(p, "name", "") or "product")[:120], "image_url": url,
                        "must_keep": [str(m)[:200] for m in (_get(p, "must_keep", None) or [])][:8]}
    return out


def _template_for(doc: StoryDoc, template_id: str | None) -> dict:
    if template_id:
        tpl = scripts.require_template(template_id)
        if doc.aspect not in (tpl.get("aspects") or []):
            raise InvalidRequest(f"This template does not support the {doc.aspect} format. "
                                 "Pick another template or change the story's aspect.", code="invalid_length")
        return tpl
    candidates = DEFAULT_TEMPLATES.get(doc.format, DEFAULT_TEMPLATES["story"])
    fallback = None
    for tid in candidates:
        tpl = scripts.template(tid)
        if not tpl or doc.aspect not in (tpl.get("aspects") or []):
            continue
        rng = tpl.get("length") or {}
        if int(rng.get("min_seconds") or 0) <= doc.target_seconds <= int(rng.get("max_seconds") or 900):
            return tpl
        fallback = fallback or tpl
    if fallback:
        return fallback
    raise InvalidRequest("No Faceless Studio template fits this story. Pick a template and try again.",
                         code="unknown_template")


def _length(doc: StoryDoc, tpl: dict) -> int:
    rng = tpl.get("length") or {}
    low = max(catalog.MIN_LENGTH_SECONDS, int(rng.get("min_seconds") or catalog.MIN_LENGTH_SECONDS))
    high = min(catalog.MAX_LENGTH_SECONDS.get(doc.aspect, 180), int(rng.get("max_seconds") or 900))
    return max(low, min(high, int(doc.target_seconds)))


def _beat_at(tpl: dict, fraction: float) -> tuple[str, str]:
    beats = tpl.get("beats") or []
    for beat in beats:
        if float(beat.get("start", 0)) <= fraction < float(beat.get("end", 1)):
            return beat["id"], beat.get("name") or ""
    if beats:
        return beats[-1]["id"], beats[-1].get("name") or ""
    return "main", ""


def save_unsaved_cast(db: Session, user_id: int, doc: StoryDoc) -> list[CastEntry]:
    """Save every character without a (still existing) library entry. No commit."""
    saved = []
    for entry in doc.characters:
        if entry.ref_id and library.owned_character(db, user_id, entry.ref_id) is not None:
            continue
        entry.ref_id = library.save_character(db, user_id, entry).id
        saved.append(entry)
    return saved


def _camera(shot: Shot) -> str:
    if shot.camera == "handheld":
        return "handheld"
    return _CAMERA_FOR_TYPE.get(shot.type, "medium")


def _motion(shot: Shot, index: int) -> str:
    if shot.camera in ("pan", "whip_pan", "tracking", "orbit"):
        return "pan_left" if index % 2 else "pan_right"
    return _MOTION_FOR_CAMERA.get(shot.camera, "push_in")


def build_script(db: Session, user_id: int, doc: StoryDoc, tpl: dict, length: int) -> tuple[dict, list[int]]:
    """(Script as JSON, cast ids) for a document whose characters are saved."""
    chars = {}
    for entry in doc.characters:
        char = library.owned_character(db, user_id, entry.ref_id)
        if char is not None:
            chars[entry.key] = char
    clauses = {key: library.character_clause(char) for key, char in chars.items()}

    # The six characters seen or heard most are the project cast.
    appearances = {key: 0 for key in chars}
    for scene in doc.scenes:
        for shot in scene.shots:
            for key in set(shot.characters) | {d.character_key for d in shot.dialogue}:
                if key in appearances:
                    appearances[key] += 1
    order = sorted(appearances, key=lambda k: (-appearances[k], k))
    cast_ids = [chars[k].id for k in order][:catalog.MAX_CAST]

    shots = [(scene, shot) for scene in doc.scenes for shot in scene.shots]
    total = sum(shot.duration_seconds for _, shot in shots) or float(length)
    wpm = int(((tpl.get("voice") or {}).get("wpm")) or 165)
    look = ", ".join(p for p in (doc.look.visual_style, doc.look.lighting, doc.look.palette) if p)
    register = _get(doc.look, "register", "")
    register = register.lower() if isinstance(register, str) else ""
    products = _products(doc)
    scenes = []
    start = 0.0
    words = 0
    for index, (scene, shot) in enumerate(shots):
        env = doc.env(scene.environment_key)
        env_text = ", ".join(p for p in ((env.name, env.description, env.time_of_day) if env else (scene.heading,)) if p)
        in_frame = [k for k in shot.characters if k in chars]
        clause_text = "; ".join(clauses[k] for k in in_frame)
        in_shot = [products[k] for k in (_get(shot, "props", None) or []) if k in products]
        product_text = "; ".join(
            f"{p['name']}" + (f", keeping {', '.join(p['must_keep'])}" if p["must_keep"] else "") for p in in_shot)
        framing = str(_get(shot, "frame_position", "") or "").strip()
        visual = ". ".join(p.strip().rstrip(".") for p in (clause_text, product_text, env_text, shot.action,
                                                            f"Framing: {framing}" if framing else "")
                           if p and p.strip())
        hero = bool(in_shot) and not in_frame
        keyframe = _get(shot, "keyframe_url", None) if _get(shot, "keyframe_approved", False) else None
        dialogue = []
        for line in shot.dialogue:
            text = _clean_spoken(line.line)
            if not text:
                continue
            speaker = chars.get(line.character_key)
            cast_entry = doc.cast(line.character_key)
            dialogue.append({
                "character_id": str(speaker.id) if speaker else "",
                "character": (cast_entry.name if cast_entry else "Narrator")[:120],
                "text": text[:catalog.MAX_LINE_CHARS],
                "emotion": _emotion(line.delivery),
            })
        narration = _clean_spoken(shot.voiceover)[:catalog.MAX_NARRATION_CHARS]
        # A hero product shot is always a clip: it opens on the product photo.
        moving = shot.b_roll or shot.camera != "static" or hero
        seconds = float(shot.duration_seconds)
        if shot.camera == "pan":
            move = "pan_left" if index % 2 else "pan_right"
        else:
            move = _MOVE_FOR_CAMERA.get(shot.camera, "static")
        beat_id, beat_name = _beat_at(tpl, start / total if total else 0.0)
        scene_words = len(narration.split()) + sum(len(d["text"].split()) for d in dialogue)
        words += scene_words
        scenes.append({
            "id": f"s{index + 1}",
            "index": index,
            "beat": beat_id,
            "beat_name": beat_name,
            "start": round(start, 2),
            "duration": round(seconds, 2),
            "narration": narration,
            "dialogue": dialogue,
            "shot": {
                "kind": "clip" if moving else "still",
                "camera": _camera(shot),
                "characters": [str(chars[k].id) for k in in_frame],
                "direction": (shot.action or scene.summary or "")[:catalog.MAX_PROMPT_CHARS],
                "visual_prompt": visual[:catalog.MAX_PROMPT_CHARS],
                "images": 1,
                "clip_seconds": (max(float(catalog.CLIP_MIN_SECONDS), min(float(catalog.CLIP_MAX_SECONDS), seconds))
                                 if moving else None),
                "motion": _motion(shot, index),
                "camera_move": move,
                "end_state": str(_get(shot, "end_state", "") or "")[:catalog.MAX_ON_SCREEN_TEXT],
                "hero_product": hero,
                "keyframe_url": keyframe or "",
            },
            "on_screen_text": shot.on_screen_text[:catalog.MAX_ON_SCREEN_TEXT] or None,
            "is_hook": index == 0,
            "word_target": scene_words,
            "transition_in": _TRANSITION.get(shot.transition_in, "cut"),
            "sfx": _SFX.get(shot.transition_in) if index > 0 else None,
            "products": in_shot[:3],
            "notes": f"Story Room shot {shot.id} ({scene.heading or scene.id}); "
                     f"{shot.type}, {shot.camera}, {shot.transition_in}"
                     + (f"; sound: {shot.sound}" if shot.sound else ""),
        })
        start += seconds

    script = {
        "template_id": tpl["id"],
        "title": (doc.title or "Untitled")[:200],
        "logline": doc.logline,
        "premise": doc.synopsis or doc.logline,
        "language": doc.language or "en",
        "aspect": doc.aspect,
        "length_seconds": length,
        "estimated_seconds": round(start, 2),
        "wpm": wpm,
        "word_budget": int(length * wpm / 60),
        "word_count": words,
        "ending": tpl.get("ending") or "payoff",
        "outro_title": " ".join((doc.title or "").split()[:5]),
        "look_register": register if register in _REGISTERS else "",
        "scenes": scenes,
        "cast_ids": [str(i) for i in cast_ids],
        "cast_clauses": {str(chars[k].id): clauses[k] for k in chars},
        "cast_names": {str(chars[k].id): chars[k].name for k in chars},
        "dramatization_label": tpl.get("dramatization_label"),
        "visual_style": look or tpl.get("visual_style") or "",
        "caption_preset": tpl.get("caption_preset") or "bold_pop",
        "music": tpl.get("music"),
        "warnings": [],
        "model": "story_room",
    }
    if doc.format == "ad":
        # The brand beat: the CTA is the end card's title, the offer under
        # it; the piece runs exactly the placement length (the target).
        ad = doc.ad
        cta = (_get(ad, "cta", "") or "").strip() if ad else ""
        script.update({
            "format": "ad",
            "ad": {"cta": cta[:120], "offer": ((_get(ad, "offer", "") or "").strip())[:200] if ad else "",
                   "brand": ((_get(ad, "brand", "") or "").strip())[:120] if ad else ""},
            "exact_seconds": float(doc.target_seconds),
            "outro_title": cta[:120] or script["outro_title"],
        })
    return script, cast_ids


def handoff(db: Session, user_id: int, doc: StoryDoc, template_id: str | None) -> FacelessProject:
    """Create a scripted Faceless project from ``doc``. Commits nothing; the
    caller commits (the cast saves, the project and its first script version
    land together)."""
    if not doc.shot_count():
        raise InvalidRequest("The story has no shots yet. Ask the director for a shot list first.")
    count = db.query(FacelessProject).filter(FacelessProject.user_id == user_id).count()
    if count >= MAX_PROJECTS:
        raise InvalidRequest(f"You can keep at most {MAX_PROJECTS} Faceless projects. Delete some first.")
    tpl = _template_for(doc, template_id)
    length = _length(doc, tpl)
    save_unsaved_cast(db, user_id, doc)
    raw, cast_ids = build_script(db, user_id, doc, tpl, length)
    script = scripts.dump(scripts.validate_script(raw))
    chars = consent.load_cast(db, user_id, cast_ids)
    idea = "\n\n".join(p for p in (doc.logline, doc.synopsis, doc.treatment) if p)[:8000] or doc.title
    project = FacelessProject(
        user_id=user_id, title=(doc.title or "Untitled")[:200], idea=idea, template_id=tpl["id"],
        aspect=doc.aspect, length_seconds=length, language=(doc.language or "en")[:10],
        caption_preset=tpl.get("caption_preset") or "bold_pop", music_mood="template", cast_ids=cast_ids,
        facts=[], settings=grade.handoff_settings(db, user_id, doc), status="draft", scene_assets={}, usd_by_step={},
    )
    db.add(project)
    db.flush()
    scripts.apply_script(db, project, script, "draft", chars)
    return project
