"""ffmpeg and ffprobe subprocess helpers (lowered priority, cancellable)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from typing import Callable, Optional, Sequence

from app.utils.security import scrubbed_env

from .timeline import MediaInfo, RenderCancelled, RenderError

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}

# Input options for every media file the engine opens (input_guard()): only
# plain local files, and only real media containers, so a source that is
# secretly an HLS playlist, a concat list or another indirection format can
# neither make ffmpeg read other paths nor reach the network.
LOCAL_ONLY = ["-protocol_whitelist", "file"]
MEDIA_FORMATS = ",".join([
    "mov", "mp4", "m4a", "3gp", "3g2", "mj2",        # the mov demuxer and its aliases
    "matroska", "webm", "mp3", "wav", "aac", "ogg", "flac",
    "image2", "png_pipe", "jpeg_pipe", "webp_pipe",
])
_FORMAT_WHITELIST_OK: Optional[bool] = None


def format_whitelist_supported() -> bool:
    """Whether this ffmpeg build knows -format_whitelist (FFmpeg 3.x and
    later). Checked once per process; older builds keep the protocol guard."""
    global _FORMAT_WHITELIST_OK
    if _FORMAT_WHITELIST_OK is None:
        try:
            out = subprocess.run([ffprobe_bin(), "-v", "error", "-format_whitelist", "mov", "-version"],
                                 capture_output=True, timeout=20, env=scrubbed_env())
            _FORMAT_WHITELIST_OK = out.returncode == 0
        except Exception:
            _FORMAT_WHITELIST_OK = False
    return _FORMAT_WHITELIST_OK


def input_guard() -> list[str]:
    """Options to put before ``-i <file>`` (and before a probed path)."""
    if format_whitelist_supported():
        return [*LOCAL_ONLY, "-format_whitelist", MEDIA_FORMATS]
    return list(LOCAL_ONLY)


def ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RenderError("ffmpeg is not installed or not on PATH")
    return path


def ffprobe_bin() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise RenderError("ffprobe is not installed or not on PATH")
    return path


def _popen_kwargs(nice: int) -> dict:
    kw: dict = {"env": scrubbed_env()}
    if sys.platform == "win32":
        # BELOW_NORMAL_PRIORITY_CLASS
        kw["creationflags"] = 0x00004000 if nice > 0 else 0
    elif nice > 0:
        def _lower() -> None:  # runs in the child before exec
            try:
                os.nice(nice)
            except OSError:
                pass

        kw["preexec_fn"] = _lower
    return kw


def popen(
    args: Sequence[str],
    *,
    nice: int = 10,
    stdin=None,
    stdout=None,
    stderr=None,
    bufsize: int = -1,
) -> subprocess.Popen:
    return subprocess.Popen(
        list(args),
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        bufsize=bufsize,
        **_popen_kwargs(nice),
    )


def kill(proc: Optional[subprocess.Popen]) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def _tail(path: str, limit: int = 1500) -> str:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - limit))
            return fh.read().decode("utf-8", "replace").strip()
    except OSError:
        return ""


def run(
    args: Sequence[str],
    *,
    log_path: str,
    nice: int = 10,
    cancel: Optional[Callable[[], bool]] = None,
    timeout: Optional[float] = None,
    what: str = "ffmpeg",
) -> str:
    """Run a command to completion, polling ``cancel``. stderr goes to
    ``log_path`` (never a pipe, so a chatty ffmpeg cannot deadlock). Returns
    the stderr text (bounded) for callers that parse it."""
    with open(log_path, "wb") as log:
        proc = popen(args, nice=nice, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log)
        started = time.monotonic()
        try:
            while True:
                try:
                    proc.wait(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if cancel is not None and cancel():
                    kill(proc)
                    raise RenderCancelled("render cancelled")
                if timeout is not None and time.monotonic() - started > timeout:
                    kill(proc)
                    raise RenderError(f"{what} timed out")
        except BaseException:
            kill(proc)
            raise
    if proc.returncode != 0:
        raise RenderError(f"{what} failed ({proc.returncode}): {_tail(log_path)}")
    try:
        with open(log_path, "rb") as fh:
            data = fh.read(4_000_000)
        return data.decode("utf-8", "replace")
    except OSError:
        return ""


def measure_media(path: str) -> MediaInfo:
    """duration (s, 0 for still images), width, height, has_audio."""
    if not path or not os.path.isfile(path):
        raise RenderError(f"media not found: {path}")
    args = [
        ffprobe_bin(),
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,width,height,duration,nb_frames",
        "-of",
        "json",
        *input_guard(),
        path,
    ]
    try:
        out = subprocess.run(args, capture_output=True, timeout=60, **_popen_kwargs(5))
    except subprocess.TimeoutExpired as exc:
        raise RenderError(f"ffprobe timed out on {path}") from exc
    if out.returncode != 0:
        raise RenderError(f"ffprobe failed on {path}: {out.stderr.decode('utf-8', 'replace')[-500:]}")
    try:
        data = json.loads(out.stdout.decode("utf-8", "replace") or "{}")
    except ValueError as exc:
        raise RenderError(f"ffprobe returned bad JSON for {path}") from exc
    streams = data.get("streams") or []
    width = height = 0
    has_audio = False
    has_video = False
    for st in streams:
        kind = st.get("codec_type")
        if kind == "video" and not has_video:
            has_video = True
            width = int(st.get("width") or 0)
            height = int(st.get("height") or 0)
        elif kind == "audio":
            has_audio = True
    duration = 0.0
    try:
        duration = float((data.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    if os.path.splitext(path)[1].lower() in IMAGE_EXTS:
        duration = 0.0
    return {"duration": duration, "width": width, "height": height, "has_audio": has_audio}
