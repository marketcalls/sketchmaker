"""Script helpers: scenes, voice lines, timing and word timings.

The script is storyscript.Script stored as JSON on the project. Audio drives
timing, as in the story-telling pipeline: once a scene's voice lines exist,
the scene lasts exactly as long as its clips plus short pauses; before that
the length is estimated from the word count at 165 words per minute.
"""

from __future__ import annotations

import hashlib
import json
import re

from app.services.storyscript.text import limit_audio_tags

from . import catalog

_TAG = re.compile(r"\[[^\]]*\]")
_SPACE = re.compile(r"\s+")


def scenes_of(script: dict | None) -> list[dict]:
    return list((script or {}).get("scenes") or [])


def scene_ids(script: dict | None) -> list[str]:
    return [str(s.get("id")) for s in scenes_of(script) if s.get("id") is not None]


def scene_by_id(script: dict | None, scene_id: str) -> dict | None:
    for scene in scenes_of(script):
        if str(scene.get("id")) == str(scene_id):
            return scene
    return None


def strip_tags(text: str) -> str:
    return _SPACE.sub(" ", _TAG.sub(" ", text or "")).strip()


def digest(*parts) -> str:
    raw = json.dumps(parts, sort_keys=True, default=str).encode()
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:16]


def shot_of(scene: dict) -> dict:
    return dict(scene.get("shot") or {})


def shot_kind(scene: dict) -> str:
    return shot_of(scene).get("kind") or "still"


def scene_characters(scene: dict) -> list[str]:
    """Character ids in frame (as strings)."""
    return [str(c) for c in (shot_of(scene).get("characters") or [])]


# ---------------------------------------------------------------------------
# Voice lines
# ---------------------------------------------------------------------------

def voice_lines(scene: dict, narrator_voice: str, narrator_settings: dict,
                characters: dict[str, dict]) -> list[dict]:
    """The clips one scene needs: its narration, then each dialogue line.

    ``characters`` maps character id (string) to {voice_id, voice_settings,
    name}. A line by a character without a voice uses the narrator voice.
    Each line carries the exact text sent to Eleven v4 (tags included, which
    is what fal bills) and a hash so a changed line is regenerated.
    """
    lines: list[dict] = []
    narration = (scene.get("narration") or "").strip()
    if narration:
        emotion = scene.get("narration_emotion")
        narration = limit_audio_tags(narration, emotion)
        text = f"[{emotion}] {narration}" if emotion else narration
        lines.append({
            "speaker": "narrator",
            "character_id": None,
            "voice": narrator_voice,
            "settings": dict(narrator_settings),
            "text": text,
        })
    for line in scene.get("dialogue") or []:
        spoken = (line.get("text") or "").strip()
        if not spoken:
            continue
        emotion = line.get("emotion")
        spoken = limit_audio_tags(spoken, emotion)
        text = f"[{emotion}] {spoken}" if emotion else spoken
        cid = str(line.get("character_id") or "")
        char = characters.get(cid) or {}
        lines.append({
            "speaker": line.get("character") or char.get("name") or "character",
            "character_id": cid or None,
            "voice": char.get("voice_id") or narrator_voice,
            "settings": dict(char.get("voice_settings") or narrator_settings),
            "text": text,
        })
    for i, line in enumerate(lines):
        line["index"] = i
        line["hash"] = digest(line["voice"], line["text"], line["settings"])
    return lines


def tts_characters(text: str) -> int:
    """Characters fal bills for one request (the text as sent)."""
    return len(text or "")


def estimate_seconds(text: str) -> float:
    words = len(strip_tags(text).split())
    return words / catalog.ESTIMATE_WPM * 60.0


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------

def voice_is_current(assets: dict, lines: list[dict]) -> bool:
    """Every line of the scene has a clip generated from its current text."""
    stored = {int(v.get("index", -1)): v for v in (assets or {}).get("voice") or []}
    if not lines:
        return False
    for line in lines:
        clip = stored.get(line["index"])
        if not clip or clip.get("hash") != line["hash"] or not clip.get("duration"):
            return False
    return True


def scene_duration(scene: dict, assets: dict, lines: list[dict]) -> tuple[float, bool]:
    """(seconds, measured). Measured when every voice clip exists."""
    silence = float(scene.get("silence_after") or 0)
    if lines and voice_is_current(assets, lines):
        stored = {int(v["index"]): v for v in assets.get("voice") or []}
        total = sum(float(stored[line["index"]]["duration"]) for line in lines)
        total += catalog.LINE_PAUSE_SECONDS * (len(lines) - 1) + catalog.SCENE_TAIL_SECONDS + silence
        return round(max(catalog.MIN_SCENE_SECONDS, total), 3), True
    if lines:
        total = sum(estimate_seconds(line["text"]) for line in lines)
        total += catalog.LINE_PAUSE_SECONDS * (len(lines) - 1) + catalog.SCENE_TAIL_SECONDS + silence
        return round(max(catalog.MIN_SCENE_SECONDS, total), 3), False
    planned = float(scene.get("duration") or 0) or float(shot_of(scene).get("clip_seconds") or 0)
    return round(max(catalog.MIN_SCENE_SECONDS, planned or 3.0) + silence, 3), False


def plan_timing(script: dict, scene_assets: dict, narrator_voice: str, narrator_settings: dict,
                characters: dict[str, dict]) -> list[dict]:
    """Start, duration and voice lines for every scene in order."""
    out = []
    t = 0.0
    for scene in scenes_of(script):
        sid = str(scene.get("id"))
        lines = voice_lines(scene, narrator_voice, narrator_settings, characters)
        duration, measured = scene_duration(scene, (scene_assets or {}).get(sid) or {}, lines)
        silence = float(scene.get("silence_after") or 0)
        # The part of the scene that is speech: an ad fit never cuts into it.
        speech = max(0.0, duration - catalog.SCENE_TAIL_SECONDS - silence) if lines else 0.0
        out.append({"scene_id": sid, "start": round(t, 3), "duration": duration, "measured": measured,
                    "lines": lines, "speech": round(speech, 3)})
        t += duration
    return out


def total_seconds(timing: list[dict]) -> float:
    return round(sum(s["duration"] for s in timing), 3)


def is_ad(script: dict | None) -> bool:
    """An ad with an exact placement length (Story Room handoff)."""
    s = script or {}
    return s.get("format") == "ad" and float(s.get("exact_seconds") or 0) > 0


def fit_to_length(timing: list[dict], total: float, end_card: float = catalog.AD_END_CARD_SECONDS,
                  min_end_card: float = catalog.AD_END_CARD_MIN_SECONDS) -> tuple[list[dict], float]:
    """(timing, end card seconds) so scenes plus end card last exactly ``total``.

    Too long: each scene gives up its slack (tail pauses, held picture) in
    proportion, never its speech, then the end card shrinks to its minimum;
    if narration alone is still longer the piece runs over and the render
    quote says so. Too short: every scene is held longer in proportion (the
    render keeps the picture moving). Starts are recomputed."""
    timing = [dict(t) for t in timing]
    if not timing:
        return timing, end_card
    body = sum(t["duration"] for t in timing)
    target = total - end_card
    if body > target + 1e-3:
        floors = [max(catalog.AD_MIN_SCENE_SECONDS, float(t.get("speech") or 0)) for t in timing]
        slack = [max(0.0, t["duration"] - f) for t, f in zip(timing, floors)]
        need, avail = body - target, sum(slack)
        keep = 1.0 - min(1.0, need / avail) if avail > 0 else 0.0
        for t, f, s in zip(timing, floors, slack):
            t["duration"] = round(min(t["duration"], f + s * keep), 3)
        over = sum(t["duration"] for t in timing) - target
        if over > 1e-3:
            end_card = max(min_end_card, end_card - over)
    elif body < target - 1e-3:
        scale = target / body if body > 0 else 1.0
        for t in timing:
            t["duration"] = round(t["duration"] * scale, 3)
    # Rounding: the last scene absorbs the remainder so the sum is exact.
    rest = round(total - end_card - sum(t["duration"] for t in timing), 3)
    if abs(rest) < 0.05:
        timing[-1]["duration"] = round(max(0.1, timing[-1]["duration"] + rest), 3)
    start = 0.0
    for t in timing:
        t["start"] = round(start, 3)
        start += t["duration"]
    return timing, round(end_card, 3)


# ---------------------------------------------------------------------------
# Word timings
# ---------------------------------------------------------------------------

def _flatten_timestamps(timestamps) -> tuple[list[str], list[float], list[float]] | list[dict]:
    """Character arrays from Eleven v4 timestamps, or a list of word dicts."""
    chunks = timestamps
    if isinstance(chunks, dict):
        chunks = [chunks]
    if not isinstance(chunks, list):
        return [], [], []
    if chunks and all(isinstance(c, dict) and ("word" in c or "text" in c) and "start" in c for c in chunks):
        return [
            {"text": str(c.get("word") or c.get("text") or ""), "start": float(c.get("start") or 0),
             "end": float(c.get("end") or c.get("start") or 0)}
            for c in chunks
        ]
    chars: list[str] = []
    starts: list[float] = []
    ends: list[float] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        cs = chunk.get("characters") or []
        ss = chunk.get("character_start_times_seconds") or []
        es = chunk.get("character_end_times_seconds") or []
        n = min(len(cs), len(ss), len(es))
        chars.extend(str(c) for c in cs[:n])
        starts.extend(float(s) for s in ss[:n])
        ends.extend(float(e) for e in es[:n])
    return chars, starts, ends


def _is_punct(text: str) -> bool:
    return bool(text) and not any(ch.isalnum() for ch in text)


def words_from_timestamps(timestamps, text: str, duration: float | None = None) -> list[dict]:
    """Word timings [{text, start, end}] with [audio tags] removed.

    Falls back to spreading the words over ``duration`` by length when the
    provider returned no usable timestamps.
    """
    flat = _flatten_timestamps(timestamps)
    words: list[dict] = []
    if isinstance(flat, list):
        for w in flat:
            clean = strip_tags(w["text"])
            if clean:
                words.append({"text": clean, "start": round(w["start"], 3), "end": round(w["end"], 3)})
    else:
        chars, starts, ends = flat
        cur, ws, we = "", 0.0, 0.0
        in_tag = False

        def flush():
            nonlocal cur
            if cur:
                if _is_punct(cur) and words:
                    words[-1]["text"] += cur
                    words[-1]["end"] = round(max(words[-1]["end"], we), 3)
                elif not _is_punct(cur):
                    words.append({"text": cur, "start": round(ws, 3), "end": round(we, 3)})
            cur = ""

        for ch, s, e in zip(chars, starts, ends):
            if ch == "[":
                flush()
                in_tag = True
                continue
            if in_tag:
                if ch == "]":
                    in_tag = False
                continue
            if ch.isspace():
                flush()
                continue
            if not cur:
                ws = s
            cur += ch
            we = e
        flush()

    if words:
        return words
    return spread_words(strip_tags(text), duration or estimate_seconds(text))


def spread_words(text: str, duration: float) -> list[dict]:
    """Even word timings weighted by word length (no provider timestamps)."""
    tokens = [t for t in (text or "").split() if t]
    if not tokens or duration <= 0:
        return []
    weights = [max(1, len(t)) for t in tokens]
    total = float(sum(weights))
    out, t = [], 0.0
    for token, w in zip(tokens, weights):
        span = duration * w / total
        out.append({"text": token, "start": round(t, 3), "end": round(t + span, 3)})
        t += span
    return out
