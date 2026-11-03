"""Render orchestration.

Pipeline for render_timeline:

1. Validate sources and probe media (ffprobe), work out the duration.
2. Audio: mix, duck, two-pass loudnorm, encode AAC to the workdir.
3. Video: a single Python compositor loop produces every frame (base track
   from base.py, overlays from overlays.py, captions from captions.py) and
   streams raw RGB into one libx264 encoder process (``-threads 2``, lowered
   priority), which also muxes the AAC with ``-c:a copy`` and writes a
   faststart MP4. Memory stays bounded: one or two decoded frames per active
   clip, a handful of cached sprites, and the OS pipe buffer.
4. Verify the output with ffprobe, move it into place atomically, remove the
   workdir contents.

Cancellation is polled between stages, at every clip boundary and every 15
frames; progress is reported from 0 to 1 (audio is the first 8 percent).
"""

from __future__ import annotations

import io
import logging
import math
import os
import shutil
import subprocess
import tempfile
import time
from typing import Callable, Optional

from PIL import Image

from . import ffmpeg as ff
from .audio import render_audio, track_end
from .base import BaseTrack, plan_clips
from .captions import CaptionRenderer
from .layout import build_layout
from .overlays import apply_ops, build_renderers
from .timeline import RenderCancelled, RenderError, RenderResult, Timeline

log = logging.getLogger(__name__)

AUDIO_SHARE = 0.08
CHECK_EVERY = 15


# ---------------------------------------------------------------------------
# Planning helpers
# ---------------------------------------------------------------------------


def _probe_all(tl: Timeline) -> dict[str, dict]:
    media: dict[str, dict] = {}
    for a in tl.audio:
        if a.src not in media:
            media[a.src] = dict(ff.measure_media(a.src))
            if media[a.src]["duration"] <= 0:
                raise RenderError(f"audio has no duration: {a.src}")
    for c in tl.clips:
        if c.kind == "video" and c.src and c.src not in media:
            media[c.src] = dict(ff.measure_media(c.src))
        elif c.kind == "image" and c.src and not os.path.isfile(c.src):
            raise RenderError(f"image not found: {c.src}")
    for ov in tl.overlays:
        src = getattr(ov, "src", None)
        if src and not os.path.isfile(src):
            raise RenderError(f"overlay image not found: {src}")
    return media


def compute_duration(tl: Timeline, media: Optional[dict[str, dict]] = None) -> float:
    """Explicit duration, else the end of the last clip or of the audio that
    defines length (voice and sfx; music and looping tracks only when
    trim_to_timeline is False)."""
    if tl.duration:
        return tl.duration
    end = 0.0
    for c in tl.clips:
        end = max(end, c.start + c.duration)
    for a in tl.audio:
        if a.loop or (a.role == "music" and a.trim_to_timeline):
            continue
        d = (media or {}).get(a.src, {}).get("duration")
        if d is None:
            try:
                d = ff.measure_media(a.src)["duration"]
            except RenderError:
                continue
        end = max(end, track_end(a, d))
    if end <= 0:
        for ov in tl.overlays:
            end = max(end, ov.start + ov.duration)
    if end <= 0:
        raise RenderError("timeline is empty: no clips, audio or overlays")
    return end


class Compositor:
    """Draws complete frames. Shared by render_timeline and preview_frame."""

    def __init__(self, tl: Timeline, *, preview: bool = False, nice: int = 10, log_path: Optional[str] = None,
                 grade_dir: Optional[str] = None):
        self.tl = tl
        self.layout = build_layout(tl)
        self.base = BaseTrack(tl, nice=nice, log_path=log_path, preview=preview, grade_dir=grade_dir)
        self.renderers = build_renderers(tl, self.layout)
        self.captions = CaptionRenderer(tl.captions, self.layout, tl) if tl.captions else None
        cz = tl.captions.z if tl.captions else 1000
        self.below = [r for r in self.renderers if r.ov.z < cz]
        self.above = [r for r in self.renderers if r.ov.z >= cz]

    def frame(self, k: int) -> Image.Image:
        t = k / self.tl.fps
        img = self.base.frame(k)
        ops = []
        for r in self.below:
            ops.extend(r.ops(t))
        if self.captions is not None:
            ops.extend(self.captions.ops(t))
        for r in self.above:
            ops.extend(r.ops(t))
        if ops:
            img = apply_ops(img, ops)
        return img

    def close(self) -> None:
        self.base.close()


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def preview_frame(tl: Timeline, t: float) -> bytes:
    for c in tl.clips:
        if c.kind == "image" and c.src and not os.path.isfile(c.src):
            raise RenderError(f"image not found: {c.src}")
    try:
        duration = compute_duration(tl)
    except RenderError:
        duration = max(t, 0.0) + 1.0
    n = max(1, int(round(duration * tl.fps)))
    k = max(0, min(n - 1, int(round(t * tl.fps))))
    comp = Compositor(tl, preview=True, nice=5)
    try:
        img = comp.frame(k)
    finally:
        comp.close()
    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=3)
    return buf.getvalue()


def _encoder_args(tl: Timeline, audio_path: str, tmp_out: str, n_frames: int) -> list[str]:
    o = tl.output
    return [
        ff.ffmpeg_bin(), "-nostdin", "-hide_banner", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{tl.width}x{tl.height}", "-r", str(tl.fps),
        "-thread_queue_size", "64", "-i", "pipe:0",
        *ff.input_guard(), "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
        "-c:v", "libx264", "-preset", o.preset, "-crf", str(o.crf),
        "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
        "-g", str(tl.fps * 2), "-threads", str(o.threads), "-filter_threads", "1",
        "-c:a", "copy",
        "-frames:v", str(n_frames),
        "-movflags", "+faststart",
        "-f", "mp4", tmp_out,
    ]


def render_timeline(
    tl: Timeline,
    out_path: str,
    *,
    workdir: str,
    progress: Optional[Callable[[float], None]] = None,
    cancel: Optional[Callable[[], bool]] = None,
) -> RenderResult:
    started = time.monotonic()
    os.makedirs(workdir, exist_ok=True)
    job = tempfile.mkdtemp(prefix="render_", dir=workdir)
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    os.makedirs(out_dir, exist_ok=True)
    tmp_out = os.path.join(out_dir, f".{os.path.basename(out_path)}.{os.getpid()}.part.mp4")
    nice = tl.output.nice
    last_p = [-1.0]

    def report(p: float) -> None:
        if progress is None:
            return
        p = max(0.0, min(1.0, p))
        if p - last_p[0] >= 0.005 or p >= 1.0:
            last_p[0] = p
            try:
                progress(p)
            except Exception:  # a broken callback must not kill the render
                log.exception("render progress callback failed")

    def check() -> None:
        if cancel is not None and cancel():
            raise RenderCancelled("render cancelled")

    comp: Optional[Compositor] = None
    enc: Optional[subprocess.Popen] = None
    try:
        report(0.0)
        check()
        media = _probe_all(tl)
        duration = compute_duration(tl, media)
        n_frames = max(1, int(round(duration * tl.fps)))
        duration = n_frames / tl.fps
        # Audio
        audio_path = os.path.join(job, "audio.m4a")
        render_audio(tl, duration, media, job, audio_path, nice=nice, cancel=cancel,
                     progress=lambda p: report(AUDIO_SHARE * p))
        check()
        # Video
        comp = Compositor(tl, nice=nice, log_path=os.path.join(job, "decode.log"), grade_dir=job)
        boundaries = {p.start_f for p in plan_clips(tl)} | {p.end_f for p in plan_clips(tl)}
        enc_log = open(os.path.join(job, "encode.log"), "wb")
        try:
            enc = ff.popen(_encoder_args(tl, audio_path, tmp_out, n_frames), nice=nice,
                           stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=enc_log,
                           bufsize=tl.width * tl.height * 3)
        finally:
            enc_log.close()
        assert enc.stdin is not None
        for k in range(n_frames):
            if k % CHECK_EVERY == 0 or k in boundaries:
                check()
                comp.base.release_before(k)
                report(AUDIO_SHARE + (1.0 - AUDIO_SHARE - 0.02) * (k / n_frames))
            img = comp.frame(k)
            try:
                enc.stdin.write(img.tobytes())
            except (BrokenPipeError, OSError) as exc:
                enc.wait(timeout=10)
                raise RenderError(f"encoder stopped: {_tail(os.path.join(job, 'encode.log'))}") from exc
        enc.stdin.close()
        rc = enc.wait()
        if rc != 0:
            raise RenderError(f"encoder failed ({rc}): {_tail(os.path.join(job, 'encode.log'))}")
        enc = None
        comp.close()
        comp = None
        check()
        info = ff.measure_media(tmp_out)
        if info["width"] != tl.width or info["height"] != tl.height:
            raise RenderError("encoded output has unexpected dimensions")
        os.replace(tmp_out, out_path)
        size = os.path.getsize(out_path)
        report(1.0)
        log.info(
            "render done: %s %dx%d %.2fs in %.1fs (%.2fx realtime)",
            out_path, tl.width, tl.height, duration, time.monotonic() - started,
            (time.monotonic() - started) / max(0.01, duration),
        )
        return RenderResult(path=out_path, duration=round(info["duration"] or duration, 3),
                            width=tl.width, height=tl.height, size_bytes=size)
    except RenderError:
        raise
    except Exception as exc:  # unexpected: wrap so callers handle one type
        raise RenderError(f"render failed: {exc}") from exc
    finally:
        if enc is not None:
            try:
                if enc.stdin and not enc.stdin.closed:
                    enc.stdin.close()
            except OSError:
                pass
            ff.kill(enc)
        if comp is not None:
            comp.close()
        if os.path.exists(tmp_out):
            try:
                os.remove(tmp_out)
            except OSError:
                pass
        shutil.rmtree(job, ignore_errors=True)


def _tail(path: str) -> str:
    return ff._tail(path)
