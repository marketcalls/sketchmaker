"""Spec to Timeline: scene timing, transitions, audio, captions, overlays.

Timing
  Each scene gets a content duration from its template (text hold rules,
  number of periods, milestones and so on) or the user's override. With a
  voiceover the single TTS file is cut into per-scene segments at word
  boundaries and every scene is at least as long as its segment plus a short
  lead and tail, so text follows the voice (VO first). Without a voiceover
  and with reliable beats in the music, scene boundaries snap to the nearest
  beat within +/- 150 ms. Transitions overlap the boundary symmetrically, so
  the total length is the sum of the scene durations.

Audio
  Voice segments (role voice), music (ducked under voice by the engine,
  looped when shorter than the video), procedural whooshes before each
  moving transition and hits or risers from scene cues. The engine mixes,
  ducks and loudness normalises to -14 LUFS.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any, Optional

from .design import CAPTION_PLATFORM, FPS, Frame, Look, make_frame, make_look, mix, snap
from .gfx import MGTimeline
from .gfx.bg import base_clips
from .kit import Kit
from .spec import TEMPLATES, Spec, clamp_numbers, normalize
from .templates import BuildCtx, SceneOut, builder_for, duration

VO_LEAD = 0.25
VO_TAIL = 0.35
QUOTE_LEAD = 0.12


# ---------------------------------------------------------------------------
# Voiceover text and segmentation
# ---------------------------------------------------------------------------

def vo_parts(spec: Spec) -> list[tuple[str, str]]:
    """[(scene_id, text)] in order, for scenes that are spoken."""
    tpl = TEMPLATES.get(spec.template_id)
    out = []
    for sc in spec.scenes:
        st = tpl.scene_type(sc.type) if tpl else None
        text = (sc.voiceover or "").strip()
        if not text and spec.template_id == "kinetic_quote" and sc.type in ("hook", "line", "payoff"):
            text = str(sc.slots.get("text") or "").strip()
        if not text and spec.template_id == "audiogram" and sc.type == "clip" and not sc.slots.get("audio"):
            text = str(sc.slots.get("script") or "").strip()
        if text and (st is None or st.voiceover or sc.type == "clip"):
            out.append((sc.id, text))
    return out


_TAG = re.compile(r"\[[^\]]*\]")
_EDGE = re.compile(r"^[^\w&+]+|[^\w&+]+$", re.U)


def _tokens(text: str) -> list[str]:
    return [t for t in _TAG.sub(" ", text).split() if any(ch.isalnum() for ch in t)]


def _rules(spec: Optional[Spec]) -> dict[str, str]:
    return {p.written.strip().lower(): p.spoken.strip() for p in (spec.pronunciations if spec else [])
            if p.written.strip() and p.spoken.strip()}


def spoken_form(text: str, rules: dict[str, str]) -> tuple[str, list[int]]:
    """(text as the voice should read it, spoken token count per written token).

    A written token whose core (without surrounding punctuation) matches a
    pronunciation is replaced, keeping its punctuation: "API," becomes
    "A P I," and counts 3. Counts let the TTS word timings be folded back
    onto the written words for captions and kinetic text."""
    if not rules:
        return text, [1] * len(_tokens(text))
    out, counts = [], []
    for tok in _TAG.sub(" ", text).split():
        if not any(ch.isalnum() for ch in tok):
            out.append(tok)
            continue
        core = _EDGE.sub("", tok)
        say = rules.get(core.lower())
        if say and core:
            spoken = tok.replace(core, say, 1)
            counts.append(max(1, len(_tokens(spoken))))
            out.append(spoken)
        else:
            counts.append(1)
            out.append(tok)
    return " ".join(out), counts


def vo_text(spec: Spec) -> str:
    """The text sent to TTS: scene parts joined with paragraph breaks, with
    the project's pronunciations applied."""
    rules = _rules(spec)
    return "\n\n".join(spoken_form(t, rules)[0] for _, t in vo_parts(spec))


def segment_words(words: list[dict], parts: list[tuple[str, str]], duration: float,
                  rules: Optional[dict[str, str]] = None) -> dict:
    """{scene_id: {start, end, words: [...] (file seconds)}} by counting the
    spoken tokens of each part in order over the TTS word list. With
    pronunciations, the spoken words of one written token are merged back
    into that written token."""
    out = {}
    j = 0
    n = len(words)
    for k, (sid, text) in enumerate(parts):
        _spoken, counts = spoken_form(text, rules or {})
        cnt = sum(counts)
        seg = words[j:j + cnt] if cnt else []
        j += cnt
        if not seg:
            continue
        nxt = words[j]["start"] if j < n else duration
        start = max(0.0, float(seg[0]["start"]) - 0.06)
        end = min(duration, max(float(seg[-1]["end"]) + 0.08, min(float(nxt) - 0.02, float(seg[-1]["end"]) + 0.25)))
        if rules:
            written = _tokens(text)
            merged, at = [], 0
            for tok, c in zip(written, counts):
                group = seg[at:at + c]
                at += c
                if group:
                    merged.append({"text": tok, "start": group[0]["start"], "end": group[-1]["end"]})
            seg = merged or seg
        out[sid] = {"start": round(start, 3), "end": round(end, 3), "words": seg}
    return out


MAX_PAUSE = 0.3


def tighten(seg: dict, max_pause: float = MAX_PAUSE) -> dict:
    """Close long pauses inside one scene's narration.

    Gaps between words longer than ``max_pause`` lose their middle: the
    first half pause after the earlier word and the last half pause before
    the next word are kept, so breaths and word tails survive. Returns the
    segment with ``pieces`` [(src_start, src_end)] to play back to back,
    ``length`` (the tightened duration) and the words moved to match."""
    ws = seg["words"]
    cuts = []  # (cut_from, cut_to) in file seconds
    for a, b in zip(ws, ws[1:]):
        gap = float(b["start"]) - float(a["end"])
        if gap > max_pause + 0.04:
            cuts.append((float(a["end"]) + max_pause / 2, float(b["start"]) - max_pause / 2))
    if not cuts:
        return {**seg, "pieces": [(seg["start"], seg["end"])], "length": round(seg["end"] - seg["start"], 3)}

    def moved(t: float) -> float:
        removed = sum(min(t, c1) - c0 for c0, c1 in cuts if t > c0)
        return t - removed

    pieces, cur = [], seg["start"]
    for c0, c1 in cuts:
        pieces.append((round(cur, 3), round(c0, 3)))
        cur = c1
    pieces.append((round(cur, 3), seg["end"]))
    words = [{**w, "start": round(moved(float(w["start"])), 3), "end": round(moved(float(w["end"])), 3)} for w in ws]
    length = sum(e - s for s, e in pieces)
    return {**seg, "words": words, "pieces": pieces, "length": round(length, 3), "orig_start": seg["start"]}


def spread_words(text: str, duration: float, start: float = 0.0) -> list[dict]:
    """Approximate word timings: words spread over ``duration`` by length
    (used for uploaded audio with a transcript but no timestamps)."""
    toks = _tokens(text)
    if not toks or duration <= 0:
        return []
    weights = [len(t) + 2 for t in toks]
    total = float(sum(weights))
    out, t = [], start
    for tok, w in zip(toks, weights):
        d = duration * w / total
        out.append({"text": tok, "start": round(t, 3), "end": round(t + d * 0.92, 3)})
        t += d
    return out


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------

def _transition(look: Look, sc_type: str, index: int, override: Optional[str]) -> tuple[str, float]:
    st = look.style
    kind = override or st.transition
    if kind == "push":
        kind = look.rng(f"tr{index}").choice(("push_left", "push_left", "push_up"))
    if kind == "cut":
        return "cut", 0.0
    dur = snap(st.transition_seconds * look.intensity.time)
    if override == "fade":
        dur = snap(0.4 * look.intensity.time)
    return kind, max(dur, 2 / FPS)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def caption_frame(fr: Frame, aspect: str, preset: str) -> Frame:
    """Shrink the content rect so templates stay clear of the caption band."""
    from app.render import CaptionTrack, Timeline
    from app.render.layout import build_layout

    tl = Timeline(width=fr.W, height=fr.H, duration=1, captions=CaptionTrack(
        words=[{"text": "x", "start": 0, "end": 1}], preset=preset, platform_safe_zone=CAPTION_PLATFORM[aspect]))
    top = build_layout(tl).caption_top_estimate
    l, t, r, b = fr.safe
    return dataclasses.replace(fr, safe=(l, t, r, min(b, int(top - 30 * fr.u))))


def plan_timing(cx: BuildCtx, voice_segments: dict, beats: Optional[dict], use_beats: bool) -> list[float]:
    spec = cx.spec
    durs = []
    for i, sc in enumerate(spec.scenes):
        d = duration(cx, sc, i)
        seg = voice_segments.get(sc.id)
        if seg:
            lead = QUOTE_LEAD if spec.template_id == "kinetic_quote" else VO_LEAD
            spoken = seg.get("length", seg["end"] - seg["start"])
            d = max(d if not sc.duration else float(sc.duration), lead + spoken + VO_TAIL)
            if spec.template_id == "kinetic_quote" and not sc.duration:
                d = lead + spoken + (0.9 if sc.type == "payoff" else 0.35)
        durs.append(snap(d))
    if use_beats and beats and beats.get("reliable") and not voice_segments and len(durs) > 1:
        from .audio import snap_to_beats

        bounds = []
        acc = 0.0
        for d in durs[:-1]:
            acc += d
            bounds.append(acc)
        snapped = snap_to_beats(bounds, beats.get("beats") or [])
        prev = 0.0
        new = []
        for i, bnd in enumerate(snapped):
            st = cx.tpl.scene_type(spec.scenes[i].type)
            mn = st.min_seconds if st else 1.0
            d = bnd - prev
            if d < mn:
                d = durs[i]
                bnd = prev + d
            new.append(snap(d))
            prev = bnd
        new.append(durs[-1])
        durs = new
    return durs


def _series_header(spec: Spec, fr, look) -> dict:
    """The reel series header and progress bar: {band: height reserved at
    the top of the content area, elements: total seconds -> [elements]}.
    Placed at the top of the content area (below a paid partnership badge)."""
    ser, bar = spec.options.series, spec.options.progress_bar
    if not ser.enabled and not bar:
        return {"band": 0.0, "elements": lambda total: []}
    from .gfx import prim

    l, t, r, b = fr.content
    u = fr.u
    size = max(fr.type("meta") * 0.8, 22 * u)
    font = look.style.label_font or "Inter"
    y = t
    pp = spec.options.paid_partnership
    if pp.enabled and (pp.brand or "").strip():
        y += max(fr.type("meta") * 0.75, 26 * u) * 2.3
    p = look.p
    accent, muted = p.accent, p.muted
    els: list[dict] = []
    row_h = 0.0
    if ser.enabled:
        total_parts = max(ser.part, ser.total)
        part = f"PART {ser.part} OF {total_parts}"
        name = (ser.name or "").strip().upper()
        tr = 0.14
        x = l
        if name:
            els.append({"type": "badge", "text": name, "x": x, "y": y, "anchor": "top_left", "font": font,
                        "weight": 700, "size": size, "color": muted, "tracking": tr, "padx": 0, "pady": 0,
                        "anim": {"type": "fade", "t": 0.1, "dur": 0.3}, "z": 85})
            x += prim.measure(name, font, 700, size, tr * size) + size * 1.1
        els.append({"type": "badge", "text": part, "x": x, "y": y, "anchor": "top_left", "font": font,
                    "weight": 800, "size": size, "color": accent, "tracking": tr, "padx": 0, "pady": 0,
                    "anim": {"type": "fade", "t": 0.15, "dur": 0.3}, "z": 85})
        cap = prim.cap_height(font, 800, size)
        pw, ph, gap = 22 * u, 6 * u, 7 * u
        n = min(total_parts, 12)
        px = r - n * pw - (n - 1) * gap
        for j in range(n):
            done = j + 1 < ser.part
            col = accent if j + 1 == ser.part else mix(accent, p.bg, 0.55) if done else mix(muted, p.bg, 0.55)
            els.append({"type": "shape", "x": px + j * (pw + gap), "y": y + (cap - ph) / 2, "w": pw, "h": ph,
                        "color": col, "radius": ph / 2, "anim": {"type": "fade", "t": 0.2 + 0.04 * j, "dur": 0.25},
                        "t0": 0.2, "z": 85})
        row_h = cap
    bar_y = y + row_h + (18 * u if row_h else 0.0)
    bar_h = 6 * u if bar else 0.0
    band = (bar_y + bar_h) - t + 40 * u

    def elements(total: float) -> list[dict]:
        out = list(els)
        if bar:
            out.append({"type": "progress", "x": l, "y": bar_y, "w": r - l, "h": bar_h, "color": accent,
                        "track": mix(muted, p.bg, 0.7), "total": total, "z": 85})
        return out

    return {"band": band, "elements": elements}

def build(spec: Spec, *, aspect: str, brand: Optional[dict] = None, files: Optional[dict] = None,
          logo_path: Optional[str] = None, voice: Optional[dict] = None, music: Optional[dict] = None,
          clip_audio: Optional[dict] = None, sfx: Optional[dict] = None, scale: float = 1.0,
          preview: bool = False, safe_overlay: bool = False) -> tuple[MGTimeline, dict]:
    """Build the timeline for one aspect.

    voice: {path, duration, words: [{text, start, end}] (file seconds)}
    music: {path, duration, beats: {reliable, beats}}
    clip_audio: {path, duration, amps, words} for audiograms (uploaded or TTS)
    """
    spec = clamp_numbers(normalize(spec.model_copy(deep=True)))
    tpl = TEMPLATES[spec.template_id]
    look = make_look(spec.style_id, brand, spec.seed, spec.options.intensity, logo_path)
    fr = make_frame(aspect, spec.options.safe_zone, scale)
    voice = voice or {}
    parts = vo_parts(spec)
    if spec.template_id == "audiogram":
        parts = [p for p in parts if not any(s.id == p[0] and s.type == "clip" for s in spec.scenes)]
    segs = segment_words(voice.get("words") or [], parts, float(voice.get("duration") or 0),
                         _rules(spec)) if voice.get("words") else {}
    if spec.options.tight_pauses:
        segs = {sid: tighten(seg) for sid, seg in segs.items()}
    captions_on = spec.options.captions if spec.options.captions is not None else tpl.captions_default
    has_words = bool(segs) and spec.template_id != "kinetic_quote"
    if captions_on and has_words:
        fr = caption_frame(fr, aspect, look.style.caption_preset)
    header = _series_header(spec, fr, look)
    if header["band"]:
        # Scenes lay out below the series header and progress bar.
        l_, t_, r_, b_ = fr.safe
        fr = dataclasses.replace(fr, safe=(l_, int(fr.content[1] + header["band"]), r_, b_))
    kit = Kit(fr, look)
    from .data import validate_table

    data_view = None
    if tpl.data_kind and spec.data and spec.data.rows:
        data_view = validate_table(tpl.data_kind, spec.data.model_dump(),
                                   **({"top_n": spec.data_options.top_n or 10} if tpl.data_kind == "race" else {}))
        if not data_view.get("ok") and tpl.data_kind != "versus":
            data_view = {**data_view}
    cx = BuildCtx(spec=spec, tpl=tpl, fr=fr, look=look, kit=kit, data=data_view, files=dict(files or {}), vo={},
                  audio={})
    # Audiogram clip audio
    clip_scene = next((s for s in spec.scenes if s.type == "clip"), None) if spec.template_id == "audiogram" else None
    if clip_scene is not None:
        clip_audio = dict(clip_audio or {})
        if not clip_audio.get("words"):
            text = str(clip_scene.slots.get("transcript") or clip_scene.slots.get("script") or "")
            dur = float(clip_audio.get("duration") or max(2.0, len(text.split()) / 2.6))
            clip_audio["words"] = spread_words(text, dur)
            clip_audio.setdefault("duration", dur)
        cx.audio = {"amps": clip_audio.get("amps"), "duration": clip_audio.get("duration")}
    durs = plan_timing(cx, segs, (music or {}).get("beats"), spec.options.beat_sync)
    starts = []
    acc = 0.0
    for d in durs:
        starts.append(round(acc, 4))
        acc += d
    total = round(acc, 4)
    cx.starts = {sc.id: s for sc, s in zip(spec.scenes, starts)}

    # Words per scene in content seconds, and global caption words.
    caption_words = []
    for sc, s0 in zip(spec.scenes, starts):
        seg = segs.get(sc.id)
        if not seg:
            continue
        lead = QUOTE_LEAD if spec.template_id == "kinetic_quote" else VO_LEAD
        local = [{"text": w["text"], "start": round(lead + float(w["start"]) - seg["start"], 3),
                  "end": round(lead + float(w["end"]) - seg["start"], 3)} for w in seg["words"]]
        cx.vo[sc.id] = local
        caption_words += [{"text": w["text"], "start": round(s0 + w["start"], 3), "end": round(s0 + w["end"], 3)}
                          for w in local]
    if clip_scene is not None and clip_audio and clip_audio.get("words"):
        cx.vo[clip_scene.id] = [{"text": w["text"], "start": round(float(w["start"]) + 0.2, 3),
                                 "end": round(float(w["end"]) + 0.2, 3)} for w in clip_audio["words"]]

    # Scenes. The kit sees each scene's spoken words so headlines can rise
    # word by word as they are said.
    outs: list[SceneOut] = []
    for i, (sc, d) in enumerate(zip(spec.scenes, durs)):
        fn = builder_for(spec.template_id, sc.type)
        kit.vo_words = cx.vo.get(sc.id)
        outs.append(fn(cx, sc, d, i) if fn else SceneOut([]))
    kit.vo_words = None
    trans = [("cut", 0.0)]
    for i in range(1, len(spec.scenes)):
        trans.append(_transition(look, spec.scenes[i].type, i, outs[i].transition))
    overlays: list[dict] = []
    sfx_cues: list[tuple[float, str]] = []
    n = len(spec.scenes)
    for i, (sc, out) in enumerate(zip(spec.scenes, outs)):
        kind_in, t_in = trans[i]
        kind_out, t_out = trans[i + 1] if i + 1 < n else ("cut", 0.0)
        lead_in = t_in / 2
        lead_out = t_out / 2
        exit_t = {"type": kind_out, "dur": t_out, "ease": "camera_strong"}
        enter_t = {"type": kind_in, "dur": t_in, "ease": "camera_strong"}
        if i == n - 1:
            fade = 0.3 if spec.options.loop else 0.5
            exit_t = {"type": "fade", "dur": fade, "ease": "exit"}
        start = starts[i] - lead_in
        dur = durs[i] + lead_in + lead_out
        content_start = 0.0 if kind_in in ("push_left", "push_up", "wipe") else lead_in
        overlays.append({"kind": "mg_scene", "start": round(max(0.0, start), 4), "duration": round(dur, 4),
                         "z": 10 + i, "params": {
                             "elements": out.elements, "lead_in": lead_in, "lead_out": lead_out,
                             "content_dur": durs[i], "content_start": content_start,
                             "enter": enter_t, "exit": exit_t, "camera": out.camera,
                         }})
        c0 = starts[i] - lead_in + content_start
        for t, kind in out.sfx:
            sfx_cues.append((c0 + t, kind))
        if i > 0 and kind_in != "cut":
            sfx_cues.append((starts[i] - 0.3, "whoosh"))

    # Global overlay: compliance badges, logo bug, safe-zone guides.
    glob: list[dict] = []
    l, t, r, b = fr.content
    u = fr.u
    size = max(fr.type("meta") * 0.75, 26 * u)
    pp = spec.options.paid_partnership
    if pp.enabled and (pp.brand or "").strip():
        glob.append({"type": "badge", "text": f"Paid partnership with {pp.brand.strip()}", "x": l, "y": t,
                     "anchor": "top_left", "font": "Inter", "weight": 700, "size": size, "color": "#FFFFFF",
                     "bg": "rgba(10,10,12,0.72)", "anim": {"type": "none"}, "z": 90})
    if spec.options.ai_label and (voice.get("words") or vo_parts(spec)):
        glob.append({"type": "badge", "text": "AI-generated voice", "x": r, "y": t, "anchor": "top_right",
                     "font": "Inter", "weight": 600, "size": size * 0.9, "color": "#FFFFFF",
                     "bg": "rgba(10,10,12,0.6)", "anim": {"type": "none"}, "z": 90})
    glob += header["elements"](total)
    if spec.options.logo_bug and logo_path:
        lw = 120 * u
        glob.append({"type": "logo", "src": logo_path, "x": r - lw, "y": b - lw * 0.5, "w": lw, "h": lw * 0.5,
                     "align": "right", "anim": {"type": "fade", "t": 0.5, "dur": 0.4}, "z": 80})
    if safe_overlay:
        sl, st_, sr, sb = fr.safe
        red = "rgba(255,60,60,0.22)"
        glob += [
            {"type": "shape", "x": 0, "y": 0, "w": fr.W, "h": max(1, st_), "color": red, "anim": {"type": "none"}, "z": 99},
            {"type": "shape", "x": 0, "y": sb, "w": fr.W, "h": max(1, fr.H - sb), "color": red, "anim": {"type": "none"}, "z": 99},
            {"type": "shape", "x": 0, "y": st_, "w": max(1, sl), "h": max(1, sb - st_), "color": red, "anim": {"type": "none"}, "z": 99},
            {"type": "shape", "x": sr, "y": st_, "w": max(1, fr.W - sr), "h": max(1, sb - st_), "color": red, "anim": {"type": "none"}, "z": 99},
            {"type": "shape", "shape": "frame", "x": sl, "y": st_, "w": sr - sl, "h": sb - st_, "stroke": 2 * u,
             "color": "rgba(255,60,60,0.9)", "anim": {"type": "none"}, "z": 99},
        ]
    if glob:
        overlays.append({"kind": "mg_scene", "start": 0.0, "duration": total, "z": 200,
                         "params": {"elements": glob, "content_dur": total}})

    # Audio
    audio: list[dict] = []
    if not preview:
        if voice.get("path"):
            for sc, s0 in zip(spec.scenes, starts):
                seg = segs.get(sc.id)
                if not seg:
                    continue
                lead = QUOTE_LEAD if spec.template_id == "kinetic_quote" else VO_LEAD
                at = s0 + lead
                pieces = seg.get("pieces") or [(seg["start"], seg["end"])]
                for pi, (p0, p1) in enumerate(pieces):
                    # Pieces join inside kept pause audio, so short fades are inaudible.
                    audio.append({"src": voice["path"], "start": round(at, 3), "src_start": p0,
                                  "duration": round(p1 - p0, 3), "role": "voice",
                                  "fade_in": 0.02 if pi == 0 else 0.012,
                                  "fade_out": 0.06 if pi == len(pieces) - 1 else 0.012})
                    at += p1 - p0
        if clip_scene is not None and clip_audio and clip_audio.get("path"):
            s0 = cx.starts[clip_scene.id]
            audio.append({"src": clip_audio["path"], "start": round(s0 + 0.2, 3), "role": "voice",
                          "duration": round(float(clip_audio.get("duration") or 1.0), 3)})
        spoken = any(a["role"] == "voice" for a in audio)
        if music and music.get("path"):
            mdur = float(music.get("duration") or 0)
            audio.append({"src": music["path"], "start": 0.0, "role": "music", "gain_db": -13.0 if spoken else -3.0,
                          "duck_under_voice": True, "duck_db": -8.0, "fade_in": 0.25,
                          "fade_out": 0.3 if spec.options.loop else 1.6, "loop": bool(mdur and mdur + 0.5 < total),
                          "duration": round(total, 3)})
        if spec.options.sfx and sfx:
            for t, kind in sorted(sfx_cues):
                if kind in sfx and 0 <= t < total - 0.1:
                    gain = {"whoosh": -9.0, "hit": -6.0, "riser": -12.0, "click": -13.0}.get(kind, -9.0)
                    audio.append({"src": sfx[kind], "start": round(max(0.0, t), 3), "role": "sfx",
                                  "gain_db": gain - (4.0 if spoken else 0.0)})

    tl: dict[str, Any] = {
        "width": fr.W, "height": fr.H, "fps": FPS, "duration": total, "background": look.p.bg,
        "accent": look.p.accent, "display_font": look.style.display_font, "text_font": look.style.text_font,
        "clips": base_clips(fr, look, total), "overlays": overlays, "audio": audio,
        "output": {"loudness_lufs": -14, "crf": 20, "preset": "veryfast", "threads": 2, "true_peak": -1.0},
    }
    if captions_on and has_words:
        tl["captions"] = {"words": caption_words, "preset": look.style.caption_preset, "highlight": look.p.accent,
                          "platform_safe_zone": CAPTION_PLATFORM[aspect], "font": look.style.caption_font,
                          "position": "lower"}
    plan = {
        "total": total, "aspect": aspect, "width": fr.W, "height": fr.H, "captions": bool(tl.get("captions")),
        "scenes": [{"id": sc.id, "type": sc.type, "start": s0, "duration": d,
                    "voiced": sc.id in segs} for sc, s0, d in zip(spec.scenes, starts, durs)],
        "transitions": [{"into": spec.scenes[i].id, "type": trans[i][0], "seconds": trans[i][1]}
                        for i in range(1, n)],
        "beat_synced": bool(spec.options.beat_sync and (music or {}).get("beats", {}).get("reliable") and not segs),
    }
    return MGTimeline.model_validate(tl), plan


def scene_still_time(plan: dict, scene_id: Optional[str], at: Optional[float] = None) -> float:
    """Time for a storyboard still: inside the scene once its animations settle."""
    for s in plan["scenes"]:
        if s["id"] == scene_id:
            if at is not None:
                return max(0.0, min(s["start"] + s["duration"] - 0.05, s["start"] + at))
            return s["start"] + min(s["duration"] * 0.78, max(1.4, s["duration"] - 0.6))
    return min(plan["total"] - 0.05, 1.5)
