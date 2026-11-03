"""Project state helpers shared by the router, pricing, previews and renders.

* audio settings with defaults (voice and music choices),
* content hashes that decide whether a stored voice or music track is
  still current (so a re-render never regenerates unchanged audio),
* the inputs build() needs (voice words, music beats, audiogram audio,
  uploaded files), from stored assets,
* the planned length used for quotes.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from app.services import pricing as cp
from app.services.faceless import catalog as fl_catalog

from . import build as mg_build
from .spec import TEMPLATES, Spec, normalize

MAX_SECONDS = {"9:16": 180, "4:5": 180, "1:1": 180, "16:9": 600}
WORDS_PER_SECOND = 2.6
DEFAULT_VOICE = "Daniel"


def digest(*parts) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode(), usedforsecurity=False).hexdigest()[:16]


def spec_of(project) -> Spec:
    return normalize(Spec.model_validate(project.spec or {"template_id": project.template_id}))


def audio_settings(project) -> dict:
    a = dict(project.audio or {})
    tpl = TEMPLATES.get(project.template_id)
    voice = {"enabled": False, "provider": "elevenlabs", "voice_id": DEFAULT_VOICE, "stability": 0.5,
             "similarity_boost": 0.75, "pace": 1.0, **(a.get("voice") or {})}
    if voice["provider"] == "sarvam":
        from app.services import sarvam_tts

        if voice["voice_id"] not in sarvam_tts.VOICE_IDS:
            voice["voice_id"] = sarvam_tts.DEFAULT_VOICE
    else:
        voice["provider"] = "elevenlabs"
        if voice["voice_id"] not in fl_catalog.VOICE_IDS:
            voice["voice_id"] = DEFAULT_VOICE
    mood = (tpl.music_mood if tpl else "documentary")
    music = {"enabled": False, "mood": mood if mood != "none" else "documentary", **(a.get("music") or {})}
    if music["mood"] not in fl_catalog.MUSIC_MOOD_IDS or music["mood"] in ("template",):
        music["mood"] = "documentary"
    return {"voice": voice, "music": music}


def voice_text(project, spec: Optional[Spec] = None) -> str:
    spec = spec or spec_of(project)
    if spec.template_id == "audiogram" and audiogram_upload(project, spec):
        return ""
    return mg_build.vo_text(spec)


def voice_hash(project, spec: Optional[Spec] = None) -> str:
    v = audio_settings(project)["voice"]
    if v["provider"] == "sarvam":
        return digest("sarvam", v["voice_id"], round(float(v.get("pace") or 1.0), 2), voice_text(project, spec))
    return digest(v["voice_id"], round(float(v["stability"]), 2), round(float(v["similarity_boost"]), 2),
                  voice_text(project, spec))


def voice_needed(project, spec: Optional[Spec] = None) -> bool:
    spec = spec or spec_of(project)
    text = voice_text(project, spec)
    if not text:
        return False
    enabled = audio_settings(project)["voice"]["enabled"] or (
        spec.template_id == "audiogram" and not audiogram_upload(project, spec))
    return bool(enabled)


def voice_current(project, spec: Optional[Spec] = None) -> bool:
    cur = (project.assets or {}).get("voice") or {}
    return bool(cur.get("file")) and cur.get("hash") == voice_hash(project, spec)


def music_hash(project) -> str:
    return digest(audio_settings(project)["music"]["mood"])


def music_needed(project) -> bool:
    m = audio_settings(project)["music"]
    return bool(m["enabled"]) and m["mood"] != "none"


def music_current(project, total: float) -> bool:
    cur = (project.assets or {}).get("music") or {}
    return bool(cur.get("file")) and cur.get("hash") == music_hash(project) and \
        float(cur.get("duration") or 0) + 0.5 >= min(total, float(cur.get("requested") or total))


def audiogram_upload(project, spec: Spec) -> Optional[dict]:
    if spec.template_id != "audiogram":
        return None
    clip = next((s for s in spec.scenes if s.type == "clip"), None)
    ref = (clip.slots.get("audio") if clip else None) or None
    uid = ref.get("upload_id") if isinstance(ref, dict) else ref
    up = ((project.assets or {}).get("uploads") or {}).get(uid) if uid else None
    return up if up and up.get("kind") == "audio" else None


def image_refs(spec: Spec) -> list[str]:
    """Upload ids referenced anywhere in the spec."""
    out = []

    def walk(v):
        if isinstance(v, dict):
            if v.get("upload_id"):
                out.append(str(v["upload_id"]))
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    for sc in spec.scenes:
        walk(sc.slots)
    return out


def estimated_voice(project, spec: Spec) -> Optional[dict]:
    """Stored voice when current; otherwise an estimate from the text (for
    quotes and storyboard timing before the voice exists)."""
    if not voice_needed(project, spec):
        return None
    cur = (project.assets or {}).get("voice") or {}
    if cur.get("file") and cur.get("hash") == voice_hash(project, spec):
        return {"duration": cur.get("duration"), "words": cur.get("words") or []}
    parts = mg_build.vo_parts(spec)
    words, t = [], 0.2
    for _, text in parts:
        for w in mg_build._tokens(text):
            d = max(0.18, (len(w) + 2) / (WORDS_PER_SECOND * 6.5))
            words.append({"text": w, "start": round(t, 3), "end": round(t + d * 0.9, 3)})
            t += d
        t += 0.45
    return {"duration": round(t, 3), "words": words, "estimated": True}


def clip_audio_info(project, spec: Spec) -> Optional[dict]:
    """Audiogram audio: the uploaded file, else the TTS voice."""
    if spec.template_id != "audiogram":
        return None
    up = audiogram_upload(project, spec)
    if up:
        return {"duration": up.get("duration"), "amps": up.get("amps"), "file": up.get("file"),
                "storage": up.get("storage")}
    v = estimated_voice(project, spec)
    cur = (project.assets or {}).get("voice") or {}
    if v and not v.get("estimated"):
        return {"duration": cur.get("duration"), "amps": cur.get("amps"), "words": cur.get("words"),
                "file": cur.get("file"), "storage": cur.get("storage")}
    if v:
        return {"duration": v["duration"], "words": v["words"]}
    return None


def build_kwargs(project, spec: Spec, *, files: Optional[dict] = None, logo_path: Optional[str] = None,
                 paths: Optional[dict] = None) -> dict:
    """Arguments for build.build() from stored assets. ``paths`` maps
    {voice, music, clip} to local files during a render."""
    paths = paths or {}
    assets = project.assets or {}
    kw = {"brand": project.brand or None, "files": files or {}, "logo_path": logo_path}
    if spec.template_id == "audiogram":
        ca = clip_audio_info(project, spec)
        if ca:
            kw["clip_audio"] = {**ca, "path": paths.get("clip")}
    else:
        v = estimated_voice(project, spec)
        if v:
            kw["voice"] = {**v, "path": paths.get("voice")}
    m = assets.get("music") or {}
    if music_needed(project) and m.get("file") and m.get("hash") == music_hash(project):
        kw["music"] = {"duration": m.get("duration"), "beats": m.get("beats") or {}, "path": paths.get("music")}
    return kw


def planned_total(project, spec: Optional[Spec] = None, aspect: Optional[str] = None) -> float:
    spec = spec or spec_of(project)
    kw = build_kwargs(project, spec)
    kw["files"] = {}
    kw["logo_path"] = None
    _, plan = mg_build.build(spec, aspect=aspect or project.aspect, scale=0.25, preview=True, **kw)
    return float(plan["total"])


def aspects_of(project) -> list[str]:
    tpl = TEMPLATES.get(project.template_id)
    out = [project.aspect]
    for a in project.variants or []:
        if a not in out and (tpl is None or a in tpl.aspects):
            out.append(a)
    return out


def price_table() -> dict:
    table = cp.cost_table()
    return {k: table[k] for k in (cp.ELEVEN_V4_KEY, cp.ELEVEN_MUSIC_KEY, cp.RENDER_MINUTE_KEY) if k in table}
