"""Shared video render engine (ffmpeg plus Pillow, no network access).

Public API (docs/STUDIO_ARCHITECTURE.md section 1)::

    render_timeline(timeline, out_path, *, workdir, progress=None, cancel=None)
        -> RenderResult(path, duration, width, height, size_bytes)
    preview_frame(timeline, t) -> bytes        # PNG
    measure_media(path) -> {duration, width, height, has_audio}

``timeline`` may be a :class:`Timeline` or a plain dict (validated here).
``progress`` is called with a float from 0 to 1. ``cancel`` is a callable
returning True to stop; it is polled between segments and every few frames,
and a cancelled render raises :class:`RenderCancelled` after removing its
workdir contents. All other failures raise :class:`RenderError`.

The heavy modules are imported lazily so that importing this package (for
the models only) stays cheap in web workers.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Union

from .timeline import (
    Anim,
    AudioTrack,
    CaptionTrack,
    CaptionWord,
    Clip,
    Grade,
    MediaInfo,
    OutputSpec,
    Overlay,
    RenderCancelled,
    RenderError,
    RenderResult,
    TextStyle,
    Timeline,
)

ProgressFn = Callable[[float], None]
CancelFn = Callable[[], bool]


def _coerce(timeline: Union[Timeline, dict[str, Any]]) -> Timeline:
    if isinstance(timeline, Timeline):
        return timeline
    return Timeline.model_validate(timeline)


def render_timeline(
    timeline: Union[Timeline, dict[str, Any]],
    out_path: str,
    *,
    workdir: str,
    progress: Optional[ProgressFn] = None,
    cancel: Optional[CancelFn] = None,
) -> RenderResult:
    """Render ``timeline`` to an H.264/AAC MP4 at ``out_path``.

    ``workdir`` is a scratch directory owned by this call (created if
    missing); everything the render writes there is removed when it returns,
    whether it succeeded, failed or was cancelled. Blocking; run it in the
    scheduler process, one render at a time.
    """
    from .engine import render_timeline as _impl

    return _impl(_coerce(timeline), out_path, workdir=workdir, progress=progress, cancel=cancel)


def preview_frame(timeline: Union[Timeline, dict[str, Any]], t: float) -> bytes:
    """Render the single frame at ``t`` seconds as PNG bytes (same drawing
    code as the full render, no encode)."""
    from .engine import preview_frame as _impl

    return _impl(_coerce(timeline), t)


def measure_media(path: str) -> MediaInfo:
    """Probe a local media file with ffprobe."""
    from .ffmpeg import measure_media as _impl

    return _impl(path)


__all__ = [
    "Anim",
    "AudioTrack",
    "CaptionTrack",
    "CaptionWord",
    "Clip",
    "Grade",
    "MediaInfo",
    "OutputSpec",
    "Overlay",
    "RenderCancelled",
    "RenderError",
    "RenderResult",
    "TextStyle",
    "Timeline",
    "measure_media",
    "preview_frame",
    "render_timeline",
]
