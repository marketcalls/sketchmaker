"""Quotes for jobs, in estimated USD. Every amount comes from app/services/pricing.py.

A job is a list of items:

  voice   Eleven v4 TTS of the whole voiceover (one request, word timestamps),
          priced per 1,000 characters, only when the stored voice is not
          current (text, voice and settings hash).
  music   ElevenLabs Music for the planned length, per started minute, only
          when the stored track is not current (mood, long enough).
  image   AI images for listicle items that have a prompt and no image.
  render  one per output aspect (primary plus variants). Runs on this machine, so
          its price is $0.

``kind`` "audio" quotes voice and music only (to listen before rendering);
"render" quotes everything the render needs.
"""

from __future__ import annotations

import math
import random

from sqlalchemy.orm import Session

from app.services import pricing as cp
from app.services.faceless import catalog as fl_catalog

from . import project as proj
from .errors import InvalidRequest
from .spec import TEMPLATES, validate

T2I_MODEL = fl_catalog.DEFAULT_T2I_MODEL
IMAGE_RESOLUTION = "1k"
MUSIC_MAX_SECONDS = 600


def _music_prompt(mood_id: str) -> str:
    mood = next((m for m in fl_catalog.MUSIC_MOODS if m["id"] == mood_id), None)
    styles = ", ".join((mood or {}).get("positive") or ["modern documentary underscore"])
    return (f"Instrumental background music for a short motion graphics video: {styles}. "
            "Steady tempo around 110 BPM with a clear pulse, clean mix, no vocals, no lyrics, "
            "no named artists, loopable ending.")


def image_jobs(project, spec) -> list[dict]:
    out = []
    uploads = (project.assets or {}).get("uploads") or {}
    for sc in spec.scenes:
        if sc.type != "item":
            continue
        prompt = str(sc.slots.get("image_prompt") or "").strip()
        ref = sc.slots.get("image")
        uid = ref.get("upload_id") if isinstance(ref, dict) else None
        if prompt and not (uid and uid in uploads):
            out.append({"scene_id": sc.id, "slot": "image", "prompt": prompt[:900]})
    return out


def _sarvam_voice_item(db: Session, project, spec, v: dict, text: str) -> dict:
    """A Sarvam Bulbul v4 voiceover: one request per scene (Sarvam returns no
    word timestamps; scene clips keep the scene boundaries exact), estimated per
    character sent at the Sarvam voice price. jobs.py synthesises it directly
    (Sarvam is not on fal)."""
    from app.services import sarvam_tts
    from app.services.assets import sarvam_key

    from . import build as mg_build
    from .sarvam_voice import split_part

    if not sarvam_key(db):
        raise InvalidRequest("Sarvam voices are not available right now. Choose an ElevenLabs voice.",
                             code="voice_unavailable")
    rules = mg_build._rules(spec)
    parts = []
    for _sid, written in mg_build.vo_parts(spec):
        # Eleven v4 audio tags like [excited] would be read aloud by Sarvam.
        spoken = " ".join(mg_build._TAG.sub(" ", mg_build.spoken_form(written, rules)[0]).split())
        if spoken:
            parts += split_part(spoken, sarvam_tts.MAX_CHARS)
    chars = sum(len(x) for x in parts)
    return {
        "kind": "voice", "provider": "sarvam", "endpoint": f"sarvam/{sarvam_tts.MODEL}", "key": cp.SARVAM_BULBUL_KEY,
        "unit": "1k characters", "units": round(chars / 1000, 3),
        "estimated_usd": cp.tts_usd(chars, cp.SARVAM_BULBUL_KEY), "label": "Sarvam Bulbul v4 voiceover",
        "chars": chars, "hash": proj.voice_hash(project, spec), "voice": v["voice_id"], "text": text,
        "parts": parts, "pace": float(v.get("pace") or 1.0), "arguments": {},
    }


def plan_job(db: Session, project, kind: str) -> dict:
    if kind not in ("audio", "render"):
        raise InvalidRequest("Unknown job kind. Use audio or render.", code="unknown_kind")
    spec = proj.spec_of(project)
    tpl = TEMPLATES[spec.template_id]
    report = validate(spec, aspect=project.aspect)
    if kind == "render" and not report["ok"]:
        raise InvalidRequest("Fix the storyboard before rendering: " + report["errors"][0]["message"],
                             code="invalid_spec", extra={"errors": report["errors"][:20]})
    items: list[dict] = []
    notes: list[str] = []
    audio = proj.audio_settings(project)
    if proj.voice_needed(project, spec) and not proj.voice_current(project, spec):
        text = proj.voice_text(project, spec)
        if len(text) > 5000:
            raise InvalidRequest("The voiceover is over 5,000 characters. Shorten it.", code="voice_too_long")
        chars = len(text)
        v = audio["voice"]
        if v["provider"] == "sarvam":
            items.append(_sarvam_voice_item(db, project, spec, v, text))
            notes.append(f"Voiceover: {chars} characters with the Sarvam voice {v['voice_id']} (Bulbul v4); scene "
                         "lengths follow the measured voice.")
        else:
            items.append({
                "kind": "voice", "endpoint": fl_catalog.TTS_ENDPOINT, "key": cp.ELEVEN_V4_KEY,
                "unit": "1k characters", "units": round(chars / 1000, 3), "estimated_usd": cp.tts_usd(chars),
                "label": "Eleven v4 voiceover", "chars": chars, "hash": proj.voice_hash(project, spec),
                "voice": v["voice_id"], "text": text,
                "arguments": {"text": text, "voice": v["voice_id"], "stability": float(v["stability"]),
                              "similarity_boost": float(v["similarity_boost"]), "output_format": "mp3_44100_128",
                              "apply_text_normalization": "auto", "timestamps": True},
            })
            notes.append(f"Voiceover: {chars} characters with {v['voice_id']}; scene lengths follow the measured "
                         "voice.")
    elif proj.voice_needed(project, spec):
        notes.append("Voiceover is current: not generated again.")
    total = proj.planned_total(project, spec)
    # A voice still to be generated may run longer than the estimate: price on 10 percent more.
    priced_total = total * (1.1 if any(i["kind"] == "voice" for i in items) else 1.0)
    if proj.music_needed(project):
        if not proj.music_current(project, priced_total):
            # A second of tail, but never into a further billed minute.
            length = min(MUSIC_MAX_SECONDS, math.ceil(priced_total + 1), max(60, cp.music_minutes(priced_total) * 60))
            mood = audio["music"]["mood"]
            items.append({
                "kind": "music", "endpoint": fl_catalog.MUSIC_ENDPOINT, "key": cp.ELEVEN_MUSIC_KEY, "unit": "minute",
                "units": cp.music_minutes(length), "estimated_usd": cp.music_usd(length),
                "label": "ElevenLabs Music", "seconds": length, "mood": mood, "hash": proj.music_hash(project),
                "arguments": {"prompt": _music_prompt(mood), "music_length_ms": int(length * 1000),
                              "force_instrumental": True, "output_format": "mp3_44100_128"},
            })
            notes.append(f"Music: one {length} s instrumental track ({mood}), billed per started minute.")
        else:
            notes.append("Music is current: not generated again.")
    if kind == "render":
        from app.clients.fal_client import build_generation_arguments

        for job in image_jobs(project, spec):
            asp = "9:16" if project.aspect == "9:16" else ("16:9" if project.aspect == "16:9" else "1:1")
            args = build_generation_arguments(job["prompt"] + ". No text, no logos, no watermarks.", T2I_MODEL,
                                              aspect_ratio=asp, resolution=IMAGE_RESOLUTION, num_images=1,
                                              seed=random.randint(1, 2_147_483_646))
            key = cp.image_key(T2I_MODEL, IMAGE_RESOLUTION)
            items.append({"kind": "image", "endpoint": T2I_MODEL, "key": key, "unit": "image", "units": 1,
                          "estimated_usd": cp.usd_for(key), "label": "AI image", "arguments": args, **job})
        aspects = proj.aspects_of(project)
        for a in aspects:
            if a not in tpl.aspects:
                raise InvalidRequest(f"{tpl.name} does not support {a}.", code="unsupported_aspect")
        top = proj.MAX_SECONDS.get(project.aspect, 180)
        if total > top + 0.5:
            raise InvalidRequest(f"This video would run {total:.0f} s; the limit for {project.aspect} is {top} s.",
                                 code="too_long")
        for a in aspects:
            items.append({"kind": "render", "endpoint": None, "key": cp.RENDER_MINUTE_KEY, "unit": "minute",
                          "units": cp.render_minutes(priced_total), "estimated_usd": cp.render_usd(priced_total),
                          "label": f"Render {a}", "aspect": a, "seconds": round(priced_total, 2)})
        notes.append(f"{len(aspects)} output(s): {', '.join(aspects)}, {total:.1f} s each, rendered on this machine.")
    if not items:
        raise InvalidRequest("Nothing to generate: the voice and music are current." if kind == "audio" else
                             "Nothing to render.", code="nothing_to_do")
    breakdown = []
    for it in items:
        breakdown.append({"label": it["label"], "key": it["key"], "unit": it["unit"], "units": it["units"],
                          "unit_usd": cp.usd_for(it["key"]), "estimated_usd": it["estimated_usd"],
                          "aspect": it.get("aspect")})
    usd_total = round(sum(float(i["estimated_usd"]) for i in items), 4)
    return {"kind": kind, "estimated_usd": usd_total, "items": items, "breakdown": breakdown, "notes": notes,
            "seconds": round(total, 2), "warnings": [w["message"] for w in report["warnings"]][:10]}


def quote_view(plan: dict) -> dict:
    return {k: plan[k] for k in ("kind", "estimated_usd", "breakdown", "notes", "seconds", "warnings")}
