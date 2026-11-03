"""Audio analysis and sound design for motion graphics (no librosa, no numpy).

* amplitudes(path): per video frame RMS (30 fps), normalised to the 95th
  percentile, for audiogram waveforms. Computed server side from the decoded
  audio (ffmpeg to 11025 Hz mono 16 bit PCM).
* beats(path): a light energy-flux beat tracker: log energy onset strength
  per 23 ms hop, autocorrelation over 70 to 180 BPM, best phase. The result
  carries a confidence; beat sync is skipped when it is not reliable.
* sfx_paths(): whoosh, hit and riser effects synthesized once with ffmpeg
  lavfi (no third-party samples, so no licensing questions) and cached.
"""

from __future__ import annotations

import logging
import math
import os
import subprocess
from array import array
from typing import Optional

from app.render import ffmpeg as ff
from app.utils.security import scrubbed_env

from .gfx.bg import cache_root

logger = logging.getLogger(__name__)

RATE = 11025
HOP = 256

# Input guard for every file ffmpeg opens here: only plain audio demuxers and
# the local file protocol, so a crafted upload can never be probed as a
# playlist (HLS, concat) that pulls in other local files or URLs.
FORMAT_WHITELIST = "mp3,wav,mov,ogg,flac,aac"
INPUT_GUARD = ("-protocol_whitelist", "file", "-format_whitelist", FORMAT_WHITELIST)


def decode_mono(path: str, rate: int = RATE, max_seconds: float = 900.0) -> array:
    args = [ff.ffmpeg_bin(), "-nostdin", "-v", "error", *INPUT_GUARD, "-i", path, "-t", f"{max_seconds:.2f}",
            "-vn", "-ac", "1", "-ar", str(rate), "-f", "s16le", "pipe:1"]
    out = subprocess.run(args, capture_output=True, timeout=180, env=scrubbed_env())
    if out.returncode != 0:
        raise ValueError(f"could not decode audio: {out.stderr[-300:]!r}")
    data = array("h")
    data.frombytes(out.stdout[: len(out.stdout) // 2 * 2])
    return data


def transcode_upload(src: str, dst: str, max_seconds: float) -> None:
    """Re-encode an uploaded audio file to AAC in MP4 (first audio stream
    only, no metadata, cover art or other streams), at most ``max_seconds``
    long. What is stored and later rendered is always our own encoder's
    output, never the uploaded container."""
    args = [ff.ffmpeg_bin(), "-nostdin", "-v", "error", "-y", *INPUT_GUARD, "-i", src, "-t", f"{max_seconds:.2f}",
            "-map", "0:a:0", "-vn", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1", "-ac", "2",
            "-ar", "44100", "-c:a", "aac", "-b:a", "160k", "-threads", "1", "-movflags", "+faststart", "-f", "mp4",
            dst]
    out = subprocess.run(args, capture_output=True, timeout=180, env=scrubbed_env())
    if out.returncode != 0 or not os.path.isfile(dst) or os.path.getsize(dst) == 0:
        raise ValueError(f"could not transcode audio: {out.stderr[-300:]!r}")


def amplitudes(samples: array, fps: int = 30, rate: int = RATE) -> list[float]:
    win = max(1, int(rate / fps))
    vals = []
    for i in range(0, len(samples), win):
        chunk = samples[i:i + win]
        if not chunk:
            break
        vals.append(math.sqrt(sum(v * v for v in chunk) / len(chunk)))
    if not vals:
        return []
    ref = sorted(vals)[int(len(vals) * 0.95) - 1 if len(vals) > 1 else 0] or 1.0
    out = []
    prev = 0.0
    for v in vals:
        a = min(1.0, v / ref)
        prev = a if a > prev else prev * 0.6 + a * 0.4  # quick attack, soft release
        out.append(round(prev, 3))
    return out


def beats(samples: array, rate: int = RATE) -> dict:
    n = len(samples) // HOP
    if n < 64:
        return {"bpm": None, "beats": [], "confidence": 0.0, "reliable": False}
    hop_s = HOP / rate
    le = []
    for k in range(n):
        chunk = samples[k * HOP:k * HOP + 2 * HOP]
        e = sum(v * v for v in chunk) / max(1, len(chunk))
        le.append(math.log(1e-3 + e))
    onset = [0.0] + [max(0.0, le[k] - le[k - 1]) for k in range(1, n)]
    w = max(3, int(0.5 / hop_s))
    smooth = []
    acc = 0.0
    for k in range(n):
        acc += onset[k]
        if k >= w:
            acc -= onset[k - w]
        smooth.append(acc / min(k + 1, w))
    o = [max(0.0, onset[k] - smooth[k]) for k in range(n)]
    lags = range(max(2, int(60 / 180 / hop_s)), int(60 / 70 / hop_s) + 1)
    ac = {}
    for L in lags:
        ac[L] = sum(o[k] * o[k - L] for k in range(L, n)) / (n - L)
    if not ac:
        return {"bpm": None, "beats": [], "confidence": 0.0, "reliable": False}
    best = max(ac, key=ac.get)
    mean = sum(ac.values()) / len(ac) or 1e-9
    conf = ac[best] / mean
    bpm = 60.0 / (best * hop_s)
    if bpm < 85 and best // 2 in ac and ac[best // 2] > 0.6 * ac[best]:
        best //= 2
        bpm = 60.0 / (best * hop_s)
    phase = max(range(best), key=lambda ph: sum(max(o[j - 1] if j > 0 else 0, o[j], o[j + 1] if j + 1 < n else 0)
                                                for j in range(ph, n, best)))
    beat_times = [round(j * hop_s, 3) for j in range(phase, n, best)]
    reliable = conf >= 1.35 and len(beat_times) >= 8
    return {"bpm": round(bpm, 1), "beats": beat_times, "confidence": round(conf, 2), "reliable": reliable}


def analyze(path: str, max_seconds: float = 900.0) -> dict:
    """{duration, amps, bpm, beats, confidence, reliable}."""
    samples = decode_mono(path, max_seconds=max_seconds)
    duration = len(samples) / RATE
    out = {"duration": round(duration, 3), "amps": amplitudes(samples)}
    try:
        out.update(beats(samples))
    except Exception as exc:  # beat sync is optional
        logger.warning(f"Beat estimate failed: {exc}")
        out.update({"bpm": None, "beats": [], "confidence": 0.0, "reliable": False})
    return out


def snap_to_beats(boundaries: list[float], beat_times: list[float], window: float = 0.15) -> list[float]:
    """Move each boundary to the nearest beat within +/- window seconds."""
    if not beat_times:
        return boundaries
    out = []
    j = 0
    for b in boundaries:
        while j + 1 < len(beat_times) and beat_times[j + 1] <= b:
            j += 1
        cands = [beat_times[j]] + ([beat_times[j + 1]] if j + 1 < len(beat_times) else [])
        near = min(cands, key=lambda x: abs(x - b))
        out.append(near if abs(near - b) <= window else b)
    return out


# ---------------------------------------------------------------------------
# Procedural sound effects
# ---------------------------------------------------------------------------

_SFX = {
    "whoosh": ("anoisesrc=d=0.55:c=pink:a=0.55:r=44100,bandpass=f=1600:width_type=q:w=0.8,"
               "afade=t=in:st=0:d=0.33:curve=qsin,afade=t=out:st=0.33:d=0.22:curve=exp,volume=2.2"),
    "hit": ("sine=f=56:d=0.7:r=44100,afade=t=out:st=0.01:d=0.69:curve=exp,volume=3.2[a];"
            "anoisesrc=d=0.05:c=white:a=0.5:r=44100,highpass=f=2500,afade=t=out:st=0:d=0.05[b];"
            "[a][b]amix=inputs=2:normalize=0"),
    "riser": ("aevalsrc='0.35*sin(2*PI*(180*t+700*t*t))':d=0.65:s=44100,"
              "afade=t=in:st=0:d=0.6:curve=exp,afade=t=out:st=0.6:d=0.05"),
    # A soft UI tick (switches flipping on, rows landing).
    "click": ("sine=f=1900:d=0.05:r=44100,afade=t=out:st=0:d=0.05:curve=exp,volume=0.8[a];"
              "anoisesrc=d=0.02:c=white:a=0.3:r=44100,highpass=f=4000[b];[a][b]amix=inputs=2:normalize=0"),
}


def sfx_paths() -> dict[str, str]:
    folder = cache_root("motion-graphics-sfx")
    out = {}
    for name, graph in _SFX.items():
        path = os.path.join(folder, f"{name}_v1.wav")
        if not os.path.isfile(path):
            tmp = f"{path}.{os.getpid()}.tmp.wav"
            args = [ff.ffmpeg_bin(), "-nostdin", "-v", "error", "-y", "-filter_complex",
                    graph + ",aformat=sample_rates=44100:channel_layouts=stereo", "-c:a", "pcm_s16le", tmp]
            res = subprocess.run(args, capture_output=True, timeout=60, env=scrubbed_env())
            if res.returncode != 0 or not os.path.isfile(tmp):
                logger.warning(f"SFX {name} could not be generated: {res.stderr[-200:]!r}")
                continue
            os.replace(tmp, path)
        out[name] = path
    return out


def audio_duration(path: str) -> Optional[float]:
    try:
        return float(ff.measure_media(path)["duration"])
    except Exception:
        return None
