"""Audio mix: voice, music and sfx placed on the timeline, music ducked under
voice, then loudness normalised (two-pass loudnorm, linear mode) and encoded
to AAC in its own file that the video encoder muxes with ``-c:a copy``.

Ducking uses a volume envelope computed from where voice actually plays
(voice tracks and clip audio with role voice, split at pauses found by
silencedetect) rather than sidechaincompress: it is deterministic, has no
pumping on breaths, and ramps down 0.25 s before speech and back up 0.6 s
after. Filters used exist in ffmpeg 4.4 and later: aresample, aformat, atrim,
asetpts, volume (eval=frame), afade, adelay, amix (normalize=0), apad,
silencedetect, loudnorm, anullsrc, acompressor.

With ``output.voice_lufs`` set, every voice and music input is measured once
(loudnorm analysis) and leveled before the mix: voice to a common target,
music a fixed distance below the voice while ducked, so a quiet take or a hot
music track no longer decides the balance (see level_items).
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from typing import Callable, Optional

from . import ffmpeg as ff
from .timeline import RenderError, Timeline

SR = 48000
DUCK_ATTACK = 0.25
DUCK_RELEASE = 0.6
DUCK_MIN_GAP = 1.2  # pauses shorter than this keep the music ducked
MAX_DUCK_SEGMENTS = 400


@dataclass
class Item:
    src: str
    start: float  # timeline seconds
    src_start: float
    length: float  # seconds played
    gain_db: float
    role: str
    fade_in: float
    fade_out: float
    loop: bool
    duck: bool
    duck_db: float


def track_end(tl_track, media_duration: float) -> float:
    """End time of a non-looping track on the timeline."""
    length = max(0.0, media_duration - tl_track.src_start)
    if getattr(tl_track, "duration", None):
        length = min(length, tl_track.duration)
    return tl_track.start + length


def plan_items(tl: Timeline, duration: float, media: dict[str, dict]) -> list[Item]:
    items: list[Item] = []
    for a in tl.audio:
        info = media.get(a.src)
        if info is None:
            raise RenderError(f"audio not found: {a.src}")
        if a.start >= duration:
            continue
        avail = max(0.0, info["duration"] - a.src_start)
        if a.loop:
            length = duration - a.start
        else:
            length = avail
        if a.duration:
            length = min(length, a.duration)
        length = min(length, duration - a.start)
        if length <= 0.01:
            continue
        items.append(Item(a.src, a.start, a.src_start, length, a.gain_db, a.role, a.fade_in, a.fade_out,
                          a.loop, a.duck_under_voice, a.duck_db))
    for c in tl.clips:
        if c.kind != "video" or c.video_audio_gain_db is None or not c.src or abs(c.speed - 1.0) > 1e-3:
            continue
        info = media.get(c.src)
        if not info or not info["has_audio"]:
            continue
        length = min(c.duration, duration - c.start)
        if not c.loop_video:
            length = min(length, max(0.0, info["duration"] - c.src_start))
        if length <= 0.01:
            continue
        items.append(Item(c.src, c.start, c.src_start, length, c.video_audio_gain_db, c.video_audio_role,
                          0.02, 0.05, c.loop_video, False, -11.0))
    return items


def _speech_spans(item: Item, workdir: str, nice: int, cancel) -> list[tuple[float, float]]:
    """Timeline spans where this voice item is audible."""
    log = os.path.join(workdir, f"silence_{abs(hash((item.src, item.start))) % 10**8}.log")
    args = [ff.ffmpeg_bin(), "-nostdin", "-hide_banner", "-v", "info"]
    if item.loop:
        args += ["-stream_loop", "-1"]
    args += ["-ss", f"{item.src_start:.3f}", "-t", f"{item.length:.3f}", *ff.input_guard(), "-i", item.src,
             "-af", "silencedetect=noise=-38dB:d=0.5", "-f", "null", "-"]
    try:
        text = ff.run(args, log_path=log, nice=nice, cancel=cancel, what="silencedetect")
    except RenderError:
        return [(item.start, item.start + item.length)]
    silences: list[tuple[float, float]] = []
    s_start = None
    for line in text.splitlines():
        m = re.search(r"silence_start: (-?[\d.]+)", line)
        if m:
            s_start = max(0.0, float(m.group(1)))
            continue
        m = re.search(r"silence_end: (-?[\d.]+)", line)
        if m and s_start is not None:
            silences.append((s_start, float(m.group(1))))
            s_start = None
    if s_start is not None:
        silences.append((s_start, item.length))
    spans = []
    cur = 0.0
    for a, b in silences:
        if a > cur:
            spans.append((cur, a))
        cur = max(cur, b)
    if cur < item.length:
        spans.append((cur, item.length))
    return [(item.start + a, item.start + b) for a, b in spans if b - a > 0.05]


def _merge(spans: list[tuple[float, float]], min_gap: float) -> list[tuple[float, float]]:
    spans = sorted(spans)
    out: list[list[float]] = []
    for a, b in spans:
        if out and a - out[-1][1] < min_gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _duck_expr(spans: list[tuple[float, float]], duck_db: float, offset: float) -> str:
    """volume expression in the music track's local time (t starts at 0 at
    the track's start; ``offset`` is the track's timeline start)."""
    g = 10 ** (duck_db / 20.0)
    terms = []
    for a, b in spans:
        a -= offset
        b -= offset
        up0 = a - DUCK_ATTACK
        down1 = b + DUCK_RELEASE
        terms.append(f"min(clip((t-{up0:.3f})/{DUCK_ATTACK},0,1),clip(({down1:.3f}-t)/{DUCK_RELEASE},0,1))")
    if not terms:
        return "1"
    return f"1-{1 - g:.5f}*min(1,{'+'.join(terms)})"


VOICE_GAIN_LIMIT = 12.0  # dB either way: a take further off is left for the final loudnorm
MUSIC_GAIN_RANGE = (-30.0, 12.0)
# Gentle voice bus compressor: about 2.5:1 above -21 dBFS, fast enough for
# syllables, slow enough not to pump on breaths.
VOICE_COMPRESSOR = "acompressor=threshold=0.089:ratio=2.5:attack=8:release=200:makeup=1"


def measure_loudness(src: str, workdir: str, nice: int = 10, cancel=None) -> Optional[float]:
    """Integrated loudness (LUFS) of a whole input, or None (silent, too
    short or unreadable)."""
    log = os.path.join(workdir, f"measure_{abs(hash(src)) % 10**8}.log")
    args = [ff.ffmpeg_bin(), "-nostdin", "-hide_banner", "-v", "info", *ff.input_guard(), "-i", src,
            "-af", "loudnorm=print_format=json", "-f", "null", "-"]
    try:
        text = ff.run(args, log_path=log, nice=nice, cancel=cancel, what="loudness of an input")
    except RenderError:
        return None
    data = _parse_loudnorm(text)
    value = (data or {}).get("input_i", float("-inf"))
    return value if math.isfinite(value) and value > -60 else None


def level_items(items: list[Item], voice_lufs: float, under_lu: float, ducking: bool,
                measured: dict[str, Optional[float]]) -> None:
    """Add each item's leveling gain to its gain_db (in place).

    Voice goes to ``voice_lufs``. Music sits ``under_lu`` below the voice
    while it is ducked under speech, so its open level is that plus the duck
    depth, but never closer than 2 LU to the voice; without voice it plays at
    the voice target. Sound effects keep their own gain."""
    has_voice = any(it.role == "voice" for it in items)
    for it in items:
        lufs = measured.get(it.src)
        if lufs is None or it.role == "sfx":
            continue
        if it.role == "voice":
            it.gain_db += max(-VOICE_GAIN_LIMIT, min(VOICE_GAIN_LIMIT, voice_lufs - lufs))
        elif it.role == "music":
            if not has_voice:
                target = voice_lufs
            elif ducking and it.duck:
                target = min(voice_lufs - 2.0, voice_lufs - under_lu + abs(it.duck_db))
            else:
                target = voice_lufs - under_lu
            low, high = MUSIC_GAIN_RANGE
            it.gain_db += max(low, min(high, target - lufs))


def build_graph(items: list[Item], duration: float, spans: list[tuple[float, float]],
                voice_bus: Optional[str] = None) -> tuple[list[str], str]:
    """Input args and filter_complex producing [mix] (stereo, 48 kHz, exact
    duration, not yet normalised). ``voice_bus`` is a filter run over the
    voice tracks mixed together before they meet music and effects."""
    inputs: list[str] = []
    chains: list[str] = []
    buses: dict[str, list[str]] = {"voice": [], "music": [], "sfx": []}
    for i, it in enumerate(items):
        if it.loop:
            inputs += ["-stream_loop", "-1"]
        if it.src_start > 0:
            inputs += ["-ss", f"{it.src_start:.3f}"]
        inputs += [*ff.input_guard(), "-i", it.src]
        f = [
            f"[{i}:a]aresample={SR}",
            "aformat=sample_fmts=fltp:channel_layouts=stereo",
            f"atrim=start=0:duration={it.length:.4f}",
            "asetpts=PTS-STARTPTS",
        ]
        if it.gain_db:
            f.append(f"volume={it.gain_db:.2f}dB")
        if it.fade_in > 0:
            f.append(f"afade=t=in:st=0:d={min(it.fade_in, it.length):.3f}")
        if it.fade_out > 0:
            d = min(it.fade_out, it.length)
            f.append(f"afade=t=out:st={max(0.0, it.length - d):.3f}:d={d:.3f}")
        if it.role == "music" and it.duck and spans:
            local = [(a, b) for a, b in spans if b > it.start and a < it.start + it.length]
            if local:
                f.append(f"volume='{_duck_expr(local, it.duck_db, it.start)}':eval=frame")
        ms = int(round(it.start * 1000))
        if ms > 0:
            f.append(f"adelay=delays={ms}:all=1")
        label = f"a{i}"
        chains.append(",".join(f) + f"[{label}]")
        buses.get(it.role, buses["sfx"]).append(label)
    if voice_bus and buses["voice"]:
        vin = "".join(f"[{l}]" for l in buses["voice"])
        mixed = (f"amix=inputs={len(buses['voice'])}:duration=longest:dropout_transition=0:normalize=0,"
                 if len(buses["voice"]) > 1 else "anull,")
        chains.append(f"{vin}{mixed}{voice_bus}[vbus]")
        buses["voice"] = ["vbus"]
    labels = [l for bus in ("voice", "music", "sfx") for l in buses[bus]]
    tail = f"apad=whole_dur={duration:.4f},atrim=start=0:duration={duration:.4f},asetpts=PTS-STARTPTS"
    if len(labels) == 1:
        chains.append(f"[{labels[0]}]{tail}[mix]")
    else:
        ins = "".join(f"[{l}]" for l in labels)
        chains.append(f"{ins}amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,{tail}[mix]")
    return inputs, ";".join(chains)


def render_audio(
    tl: Timeline,
    duration: float,
    media: dict[str, dict],
    workdir: str,
    out_path: str,
    *,
    nice: int = 10,
    cancel: Optional[Callable[[], bool]] = None,
    progress: Optional[Callable[[float], None]] = None,
) -> str:
    """Write the final AAC track (``out_path``, .m4a) and return its path."""
    o = tl.output
    items = plan_items(tl, duration, media)
    common = [ff.ffmpeg_bin(), "-nostdin", "-hide_banner", "-y"]
    enc = ["-c:a", "aac", "-b:a", o.audio_bitrate, "-ar", str(SR), "-ac", "2"]
    if not items:
        args = common + ["-f", "lavfi", "-t", f"{duration:.4f}", "-i", f"anullsrc=r={SR}:cl=stereo"] + enc + [out_path]
        ff.run(args, log_path=os.path.join(workdir, "audio_silent.log"), nice=nice, cancel=cancel, what="audio")
        return out_path

    # Where voice plays, for ducking.
    spans: list[tuple[float, float]] = []
    if any(it.role == "music" and it.duck for it in items):
        for it in items:
            if it.role == "voice":
                spans += _speech_spans(it, workdir, nice, cancel)
        gap = DUCK_MIN_GAP
        spans = _merge(spans, gap)
        while len(spans) > MAX_DUCK_SEGMENTS:
            gap *= 1.6
            spans = _merge(spans, gap)
    if o.voice_lufs is not None:
        # Each input measured once, however many times it is placed.
        measured: dict[str, Optional[float]] = {}
        for it in items:
            if it.role in ("voice", "music") and it.src not in measured:
                measured[it.src] = measure_loudness(it.src, workdir, nice, cancel)
        level_items(items, o.voice_lufs, o.music_under_voice_lu, bool(spans), measured)
    if progress:
        progress(0.3)

    inputs, graph = build_graph(items, duration, spans,
                                voice_bus=VOICE_COMPRESSOR if o.voice_compressor else None)
    target = f"I={o.loudness_lufs}:TP={o.true_peak}:LRA=11"
    # Pass 1: measure.
    log1 = os.path.join(workdir, "loudnorm_pass1.log")
    args1 = common + ["-v", "info"] + inputs + [
        "-filter_complex", graph + f";[mix]loudnorm={target}:print_format=json[out]",
        "-map", "[out]", "-f", "null", "-",
    ]
    text = ff.run(args1, log_path=log1, nice=nice, cancel=cancel, what="loudness measure")
    measured = _parse_loudnorm(text)
    if progress:
        progress(0.65)
    if measured is None or not math.isfinite(measured.get("input_i", float("-inf"))) or measured["input_i"] < -70:
        norm = "anull"  # silence or unmeasurable: leave as is
    else:
        norm = (
            f"loudnorm={target}:measured_I={measured['input_i']:.2f}:measured_TP={measured['input_tp']:.2f}"
            f":measured_LRA={measured['input_lra']:.2f}:measured_thresh={measured['input_thresh']:.2f}"
            f":offset={measured['target_offset']:.2f}:linear=true"
        )
    args2 = common + inputs + [
        "-filter_complex",
        graph + f";[mix]{norm},aresample={SR},atrim=start=0:duration={duration:.4f}[out]",
        "-map", "[out]",
    ] + enc + [out_path]
    ff.run(args2, log_path=os.path.join(workdir, "loudnorm_pass2.log"), nice=nice, cancel=cancel, what="audio mix")
    if progress:
        progress(1.0)
    return out_path


def _parse_loudnorm(text: str) -> Optional[dict]:
    idx = text.rfind("{")
    end = text.rfind("}")
    if idx < 0 or end < idx:
        return None
    try:
        data = json.loads(text[idx : end + 1])
    except ValueError:
        return None
    out = {}
    for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset"):
        try:
            out[k] = float(data.get(k))
        except (TypeError, ValueError):
            out[k] = float("-inf")
    return out
