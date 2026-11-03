"""Motion graphics voiceovers with Sarvam Bulbul v4 (Indian voices and languages).

Sarvam's text to speech returns audio only, with no word timestamps, while
motion graphics needs word times for captions, word-synced headlines and
pause tightening. So each scene's narration is its own request (scene
boundaries are then exact), the clips are joined into one voice file with a
short gap, and each scene's words are placed inside its clip:

* ffmpeg silencedetect finds the clip's speech runs (the pauses the voice
  actually made),
* the words are spread over the speech runs by length, and a word that
  would straddle a pause is moved wholly to the side holding most of it.

Word times are therefore close, not exact; ElevenLabs remains the choice
when frame-exact word sync matters.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile

from app.utils.security import scrubbed_env

GAP_SECONDS = 0.25
SILENCE_DB = -35
SILENCE_MIN = 0.12

_SIL_START = re.compile(r"silence_start: (-?[\d.]+)")
_SIL_END = re.compile(r"silence_end: (-?[\d.]+)")


def _ffmpeg() -> str:
    from app.render.ffmpeg import ffmpeg_bin

    return ffmpeg_bin()


def _duration(path: str) -> float:
    from app.services.faceless.media import probe_file

    return float(probe_file(path).get("duration") or 0.0)


def speech_runs(path: str, duration: float) -> list[tuple[float, float]]:
    """(start, end) of the stretches of a clip that are not silence."""
    proc = subprocess.run(
        [_ffmpeg(), "-nostdin", "-hide_banner", "-i", path, "-af",
         f"silencedetect=noise={SILENCE_DB}dB:d={SILENCE_MIN}", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120, env=scrubbed_env(),
    )
    log = proc.stderr or ""
    starts = [float(x) for x in _SIL_START.findall(log)]
    ends = [float(x) for x in _SIL_END.findall(log)]
    silences = []
    for k, s in enumerate(starts):
        e = ends[k] if k < len(ends) else duration
        silences.append((max(0.0, s), min(duration, e)))
    runs, cur = [], 0.0
    for s, e in silences:
        if s - cur > 0.04:
            runs.append((cur, s))
        cur = max(cur, e)
    if duration - cur > 0.04:
        runs.append((cur, duration))
    return runs or [(0.0, duration)]


PUNCT_END = (",", ".", "!", "?", ";", ":", "।", "॥")  # includes the Devanagari danda


def _spread(tokens: list[str], s: float, e: float) -> list[dict]:
    weights = [len(t) + 1.5 for t in tokens]
    wsum = sum(weights) or 1.0
    out, acc = [], 0.0
    for tok, w in zip(tokens, weights):
        a = s + (e - s) * acc / wsum
        acc += w
        b = s + (e - s) * acc / wsum
        out.append({"text": tok, "start": round(a, 3), "end": round(max(a + 0.05, b - 0.02), 3)})
    return out


def place_words(tokens: list[str], runs: list[tuple[float, float]]) -> list[dict]:
    """[{text, start, end}] in clip seconds: tokens split between the speech
    runs, each pause anchored to the nearest punctuation (where a voice
    pauses) when one is close, then spread by length inside each run."""
    if not tokens:
        return []
    if len(runs) == 1 or len(tokens) == 1:
        return _spread(tokens, runs[0][0], runs[-1][1])
    weights = [len(t) + 1.5 for t in tokens]
    wsum = sum(weights)
    cum = [0.0]
    for w in weights:
        cum.append(cum[-1] + w / wsum)  # cum[i]: share of the text before token i
    total = sum(e - s for s, e in runs)
    punct = {i + 1 for i, t in enumerate(tokens[:-1]) if t.endswith(PUNCT_END)}
    bounds, before, prev = [], 0.0, 0
    for s, e in runs[:-1]:
        before += e - s
        f = before / total
        free = [b for b in range(prev + 1, len(tokens)) if len(tokens) - b >= 1]
        if not free:
            break
        near_p = [b for b in free if b in punct and abs(cum[b] - f) <= 0.2]
        b = min(near_p or free, key=lambda x: abs(cum[x] - f))
        bounds.append(b)
        prev = b
    groups, start = [], 0
    for b in bounds:
        groups.append(tokens[start:b])
        start = b
    groups.append(tokens[start:])
    out = []
    for grp, (s, e) in zip(groups, runs[:len(groups) - 1] + [(runs[len(groups) - 1][0], runs[-1][1])]):
        out += _spread(grp, s, e)
    return out


def join(clips: list[bytes], texts: list[str]) -> tuple[bytes, list[dict], float]:
    """Join per-scene MP3 clips with a short gap. Returns (mp3 bytes, words in
    file seconds, duration)."""
    from .build import _tokens

    with tempfile.TemporaryDirectory(prefix="mg_sarvam_") as tmp:
        paths, words, offset = [], [], 0.0
        for k, (clip, text) in enumerate(zip(clips, texts)):
            path = os.path.join(tmp, f"p{k}.mp3")
            with open(path, "wb") as fh:
                fh.write(clip)
            dur = _duration(path)
            if dur <= 0:
                raise ValueError("A voice clip has no readable length")
            for w in place_words(_tokens(text), speech_runs(path, dur)):
                words.append({"text": w["text"], "start": round(w["start"] + offset, 3),
                              "end": round(w["end"] + offset, 3)})
            paths.append(path)
            offset += dur + GAP_SECONDS
        out = os.path.join(tmp, "voice.mp3")
        args = [_ffmpeg(), "-nostdin", "-hide_banner", "-y", "-v", "error"]
        for path in paths:
            args += ["-i", path]
        # Clips 0..n-1, then one short silence split into the n-1 gaps:
        # [a0][g0][a1][g1]...[a(n-1)] concatenated.
        n = len(paths)
        args += ["-f", "lavfi", "-t", f"{GAP_SECONDS}", "-i", "anullsrc=r=44100:cl=mono"]
        chain = "".join(f"[{k}:a]aresample=44100,aformat=channel_layouts=mono[a{k}];" for k in range(n))
        if n > 1:
            chain += f"[{n}:a]asplit={n - 1}" + "".join(f"[g{k}]" for k in range(n - 1)) + ";"
        seq = "".join(f"[a{k}]" + (f"[g{k}]" if k < n - 1 else "") for k in range(n))
        args += ["-filter_complex", f"{chain}{seq}concat=n={2 * n - 1}:v=0:a=1[out]", "-map", "[out]",
                 "-c:a", "libmp3lame", "-b:a", "128k", out]
        proc = subprocess.run(args, capture_output=True, text=True, timeout=300, env=scrubbed_env())
        if proc.returncode != 0:
            raise ValueError(f"Joining the voice clips failed: {(proc.stderr or '')[-300:]}")
        with open(out, "rb") as fh:
            data = fh.read()
        return data, words, _duration(out)


def split_part(text: str, limit: int) -> list[str]:
    """A scene's narration in pieces Sarvam accepts (sentence boundaries first)."""
    text = text.strip()
    if len(text) <= limit:
        return [text]
    pieces, cur = [], ""
    for sent in re.split(r"(?<=[.!?।])\s+", text):
        if len(cur) + len(sent) + 1 <= limit:
            cur = f"{cur} {sent}".strip()
            continue
        if cur:
            pieces.append(cur)
        while len(sent) > limit:
            cut = sent.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            pieces.append(sent[:cut].strip())
            sent = sent[cut:].strip()
        cur = sent
    if cur:
        pieces.append(cur)
    return pieces
