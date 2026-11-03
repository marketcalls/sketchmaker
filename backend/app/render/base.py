"""The visual base track: clips, Ken Burns motion and transitions.

Each clip becomes a frame source. Stills (image, color, gradient) are
prepared once as a "plate" large enough for the strongest zoom, and every
frame is a sub-pixel accurate window of the plate resampled to the output
size (``Image.resize`` with a float ``box``), so slow pushes and drifts are
smooth with no integer stepping. Videos are decoded by an ffmpeg subprocess
that already scales and crops to the output size and streams raw RGB frames
(bounded memory: one frame at a time).

Transitions (story-telling grammar, brightness dip fixed): the incoming clip
fades in over the first ``transition_duration`` of its window while the
outgoing clip keeps playing fully opaque underneath, i.e. a straight
``Image.blend``. ``dip_black`` fades the outgoing clip to black over the first
half and the incoming clip up from black over the second half.

The colour grade (``Timeline.grade``, grade.py) is part of the base track:
an image clip's plate is graded once when it is built, a video clip is
graded by ``lut3d`` at the end of its decode filter. Colour and gradient
clips, and everything drawn later (overlays, captions, end cards), are not.
"""

from __future__ import annotations

import math
import os
import subprocess
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from . import ffmpeg as ff
from .colors import parse_color
from .draw import linear_gradient_rgb, parse_gradient
from .easing import perceptual
from .grade import Grader, apply_to_image, filter_path
from .timeline import Clip, RenderError, Timeline

# Ken Burns numbers from the story-telling ImageLayer.
KB_LOW = 1.02
KB_HIGH = 1.12
KB_DRIFT = 14.0  # baseline px, from -drift to +drift
PAN_ZOOM = 1.10


@dataclass
class ClipPlan:
    index: int
    clip: Clip
    start_f: int
    end_f: int  # exclusive
    trans_f: int  # transition frames at the start (0 for cut)
    last_needed_f: int  # last frame this clip is drawn (incl. under the next transition)
    z0: float = 1.0
    z1: float = 1.0
    tx0: float = 0.0
    tx1: float = 0.0


def _motion_params(c: Clip, index: int, scale: float, width: int) -> tuple[float, float, float, float]:
    """(zoom_start, zoom_end, drift_start_px, drift_end_px)."""
    direction = c.motion_direction if c.motion_direction is not None else (1 if index % 2 == 0 else -1)
    drift = (c.drift_px if c.drift_px is not None else KB_DRIFT) * scale
    m = c.motion
    if m == "ken_burns":
        m = "push_in" if index % 2 == 0 else "pull_out"
        if c.motion_direction is None:
            direction = 1 if m == "push_in" else -1
    if m == "push_in":
        z0, z1 = KB_LOW, KB_HIGH
        t0, t1 = -drift * direction, drift * direction
    elif m == "pull_out":
        z0, z1 = KB_HIGH, KB_LOW
        t0, t1 = -drift * direction, drift * direction
    elif m in ("pan_left", "pan_right"):
        z0 = z1 = PAN_ZOOM
        travel = (PAN_ZOOM - 1.0) * width / 2.0 * 0.85
        t0, t1 = (travel, -travel) if m == "pan_left" else (-travel, travel)
    else:
        z0 = z1 = 1.0
        t0 = t1 = 0.0
    if c.zoom_from is not None:
        z0 = c.zoom_from
    if c.zoom_to is not None:
        z1 = c.zoom_to
    return z0, z1, t0, t1


def plan_clips(tl: Timeline) -> list[ClipPlan]:
    fps = tl.fps
    plans: list[ClipPlan] = []
    for i, c in enumerate(tl.clips):
        s = int(round(c.start * fps))
        e = max(s + 1, int(round((c.start + c.duration) * fps)))
        tf = 0 if c.transition_in == "cut" else max(0, min(e - s, int(round(c.transition_duration * fps))))
        z0, z1, t0, t1 = _motion_params(c, i, tl.width / 1080.0, tl.width)
        plans.append(ClipPlan(i, c, s, e, tf, e - 1, z0, z1, t0, t1))
    # A clip stays alive under the next clip's transition when they touch.
    for i, p in enumerate(plans):
        for q in plans[i + 1 :]:
            if q.trans_f > 0 and abs(q.start_f - p.end_f) <= 1 and q.start_f >= p.start_f:
                p.last_needed_f = max(p.last_needed_f, q.start_f + q.trans_f - 1)
    return plans


# ---------------------------------------------------------------------------
# Frame sources
# ---------------------------------------------------------------------------


class Source:
    def frame(self, k: int) -> Image.Image:  # RGB, output size
        raise NotImplementedError

    def close(self) -> None:
        pass


def _load_image(path: str) -> Image.Image:
    if not os.path.isfile(path):
        raise RenderError(f"image not found: {path}")
    try:
        im = Image.open(path)
        im = ImageOps.exif_transpose(im)
        im.draft("RGB", (8000, 8000))
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
            bg.alpha_composite(im)
            im = bg
        return im.convert("RGB")
    except RenderError:
        raise
    except Exception as exc:  # PIL raises many types
        raise RenderError(f"cannot read image {path}: {exc}") from exc


def _contain_plate(img: Image.Image, w: int, h: int, background) -> Image.Image:
    """Image fitted inside w x h over a blurred, darkened cover version."""
    cover = ImageOps.fit(img, (max(1, w // 8), max(1, h // 8)), Image.Resampling.BILINEAR)
    cover = cover.filter(ImageFilter.GaussianBlur(6)).resize((w, h), Image.Resampling.BILINEAR)
    cover = ImageEnhance.Brightness(cover).enhance(0.55)
    fitted = ImageOps.contain(img, (w, h), Image.Resampling.LANCZOS)
    cover.paste(fitted, ((w - fitted.width) // 2, (h - fitted.height) // 2))
    return cover


class StillSource(Source):
    """Image, color or gradient with optional Ken Burns motion."""

    def __init__(self, tl: Timeline, plan: ClipPlan, grader: Optional[Grader] = None):
        self.W, self.H = tl.width, tl.height
        self.plan = plan
        c = plan.clip
        dur = max(1, plan.end_f - plan.start_f)
        self.dur = dur
        # Zoom range over every frame this clip is drawn (extrapolated past its end).
        ext = (plan.last_needed_f - plan.start_f) / dur
        zs = [self._zoom(0.0), self._zoom(ext), plan.z0, plan.z1]
        self.zmax = max(1.0, max(zs))
        self.static = plan.z0 == plan.z1 and plan.tx0 == plan.tx1
        if c.kind == "image":
            img = _load_image(c.src or "")
            if c.fit == "contain":
                pw, ph = int(math.ceil(self.W * self.zmax)), int(math.ceil(self.H * self.zmax))
                self.plate = _contain_plate(img, pw, ph, tl.background)
                self.focus = (0.5, 0.5)
            else:
                s0 = max(self.W / img.width, self.H / img.height) * self.zmax
                pw = max(int(math.ceil(img.width * s0)), int(math.ceil(self.W * self.zmax)))
                ph = max(int(math.ceil(img.height * s0)), int(math.ceil(self.H * self.zmax)))
                self.plate = img.resize((pw, ph), Image.Resampling.LANCZOS, reducing_gap=3.0)
                self.focus = (c.focus_x, c.focus_y)
            img.close()
            if grader is not None:
                self.plate = apply_to_image(self.plate, grader.table(plan.index, c))
        elif c.kind == "gradient":
            cols = parse_gradient(c.gradient) or [parse_color(c.color or tl.background)]
            pw, ph = int(math.ceil(self.W * self.zmax)), int(math.ceil(self.H * self.zmax))
            self.plate = linear_gradient_rgb((pw, ph), cols, c.gradient_angle)
            self.focus = (0.5, 0.5)
        else:
            col = parse_color(c.color or tl.background, (0, 0, 0, 255))
            self.plate = Image.new("RGB", (self.W, self.H), col[:3])
            self.static = True
            self.zmax = 1.0
            self.focus = (0.5, 0.5)
        self._static_frame: Optional[Image.Image] = None

    def _zoom(self, p: float) -> float:
        return perceptual(self.plan.z0, self.plan.z1, p)

    def frame(self, k: int) -> Image.Image:
        if self.static and self._static_frame is not None:
            return self._static_frame.copy()
        p = (k - self.plan.start_f) / self.dur
        z = self._zoom(p) if not self.static else self.plan.z0
        tx = self.plan.tx0 + (self.plan.tx1 - self.plan.tx0) * p
        out = self._window(z, tx)
        if self.static:
            self._static_frame = out
            return out.copy()
        return out

    def _window(self, z: float, tx: float) -> Image.Image:
        pw, ph = self.plate.size
        if self.plate.size == (self.W, self.H) and z == 1.0 and tx == 0.0:
            return self.plate.copy()
        # Plate pixels per output pixel at this zoom.
        k = self.zmax / max(z, 1e-6)
        # The plate was sized for the cover scale at zmax: plate px per output px is
        # (plate scale / output scale); for cover plates that is zmax / z.
        base = min(pw / (self.W * self.zmax), ph / (self.H * self.zmax))
        k *= base
        ww, wh = self.W * k, self.H * k
        fx, fy = self.focus
        cx = fx * pw - tx * k
        cy = fy * ph
        x0 = min(max(0.0, cx - ww / 2.0), pw - ww)
        y0 = min(max(0.0, cy - wh / 2.0), ph - wh)
        x0, y0 = max(0.0, x0), max(0.0, y0)
        box = (x0, y0, min(pw, x0 + ww), min(ph, y0 + wh))
        return self.plate.resize((self.W, self.H), Image.Resampling.BILINEAR, box=box)

    def close(self) -> None:
        self.plate = None  # type: ignore[assignment]
        self._static_frame = None


HOLD_ZOOM_PER_SECOND = 0.025  # push-in on a held last frame
HOLD_ZOOM_MAX = 1.12


def video_filter(tl: Timeline, c: Clip, lut: Optional[str] = None) -> str:
    """Decode filter for a video clip at the output size, ending in rgb24;
    ``lut`` is the clip's grade (a .cube file), applied last."""
    W, H, fps = tl.width, tl.height, tl.fps
    speed = f"setpts=PTS/{c.speed:.4f}," if abs(c.speed - 1.0) > 1e-3 else ""
    if c.fit == "contain":
        chain = (
            f"split=2[vbg][vfg];"
            f"[vbg]scale={max(2, W // 8)}:{max(2, H // 8)}:force_original_aspect_ratio=increase,"
            f"crop={max(2, W // 8)}:{max(2, H // 8)},boxblur=6:2,scale={W}:{H},eq=brightness=-0.18[vb];"
            f"[vfg]scale={W}:{H}:force_original_aspect_ratio=decrease[vf];"
            f"[vb][vf]overlay=(W-w)/2:(H-h)/2"
        )
    else:
        chain = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    grade = f",lut3d=file={filter_path(lut)}:interp=tetrahedral" if lut else ""
    return f"{speed}fps={fps},{chain},setsar=1,format=rgb24{grade}"


class VideoSource(Source):
    """Sequential reader of an ffmpeg decode pipe (raw rgb24 at output size)."""

    def __init__(self, tl: Timeline, plan: ClipPlan, *, nice: int = 10, log_path: Optional[str] = None,
                 lut: Optional[str] = None):
        self.tl = tl
        self.plan = plan
        self.W, self.H = tl.width, tl.height
        c = plan.clip
        if not c.src or not os.path.isfile(c.src):
            raise RenderError(f"video not found: {c.src}")
        self.needed = plan.last_needed_f - plan.start_f + 1
        self.frame_bytes = self.W * self.H * 3
        self.pos = -1
        self.last: Optional[Image.Image] = None
        self.proc: Optional[subprocess.Popen] = None
        self.log_path = log_path
        self.nice = nice
        self.lut = lut  # the clip's grade LUT file, or None
        self.motion =plan.z0 != 1.0 or plan.z1 != 1.0 or plan.tx0 != plan.tx1
        # First clip-local frame past the end of the source, when the last
        # frame is held under a push-in instead of frozen.
        self.hold_from: Optional[int] = None
        if c.hold == "push_in" and not c.loop_video:
            try:
                dur = float(ff.measure_media(c.src)["duration"] or 0)
            except RenderError:
                dur = 0.0
            if dur > 0:
                avail = int(math.floor(max(0.0, dur - c.src_start) / c.speed * tl.fps)) - 1
                if 0 < avail < self.needed:
                    self.hold_from = avail

    def _start(self) -> None:
        c = self.plan.clip
        hold = self.needed / self.tl.fps + 1.0
        vf = video_filter(self.tl, c, self.lut)
        if c.fit == "contain":
            graph = f"[0:v]{vf},tpad=stop_mode=clone:stop_duration={hold:.3f}[out]"
        else:
            graph = f"[0:v]{vf},tpad=stop_mode=clone:stop_duration={hold:.3f}[out]"
        args = [ff.ffmpeg_bin(), "-nostdin", "-v", "error"]
        if c.loop_video:
            args += ["-stream_loop", "-1"]
        if c.src_start > 0:
            args += ["-ss", f"{c.src_start:.3f}"]
        args += [
            *ff.input_guard(),
            "-i",
            c.src,
            "-filter_complex",
            graph,
            "-map",
            "[out]",
            "-an",
            "-frames:v",
            str(self.needed),
            "-threads",
            "1",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
        log = open(self.log_path, "ab") if self.log_path else subprocess.DEVNULL
        try:
            self.proc = ff.popen(args, nice=self.nice, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log, bufsize=self.frame_bytes)
        finally:
            if self.log_path:
                log.close()  # the child keeps its own handle

    def _read(self) -> Optional[Image.Image]:
        assert self.proc is not None and self.proc.stdout is not None
        buf = bytearray(self.frame_bytes)
        view = memoryview(buf)
        got = 0
        while got < self.frame_bytes:
            n = self.proc.stdout.readinto(view[got:])
            if not n:
                break
            got += n
        if got < self.frame_bytes:
            return None
        return Image.frombuffer("RGB", (self.W, self.H), bytes(buf), "raw", "RGB", 0, 1)

    def frame(self, k: int) -> Image.Image:
        idx = k - self.plan.start_f
        if self.proc is None:
            self._start()
        while self.pos < idx:
            img = self._read()
            self.pos += 1
            if img is None:
                if self.last is None:
                    self.last = Image.new("RGB", (self.W, self.H), (0, 0, 0))
                break
            self.last = img
        out = self.last.copy() if self.last is not None else Image.new("RGB", (self.W, self.H))
        return self._apply_motion(out, idx)

    def _hold_zoom(self, idx: int) -> float:
        if self.hold_from is None or idx <= self.hold_from:
            return 1.0
        held = (idx - self.hold_from) / self.tl.fps
        # Eased in over the first half second so the move does not jolt.
        ramp = min(1.0, held / 0.5)
        return min(HOLD_ZOOM_MAX, 1.0 + HOLD_ZOOM_PER_SECOND * held * (0.5 + 0.5 * ramp))

    def _apply_motion(self, img: Image.Image, idx: int) -> Image.Image:
        hz = self._hold_zoom(idx)
        if not self.motion and hz == 1.0:
            return img
        p = idx / max(1, self.plan.end_f - self.plan.start_f)
        z = max(1.0, perceptual(self.plan.z0, self.plan.z1, p)) * hz
        tx = self.plan.tx0 + (self.plan.tx1 - self.plan.tx0) * p
        ww, wh = self.W / z, self.H / z
        x0 = min(max(0.0, (self.W - ww) / 2 - tx / z), self.W - ww)
        y0 = (self.H - wh) / 2
        return img.resize((self.W, self.H), Image.Resampling.BILINEAR, box=(x0, y0, x0 + ww, y0 + wh))

    def single(self, t_in_clip: float) -> Image.Image:
        """One frame at ``t_in_clip`` seconds into the clip (preview)."""
        c = self.plan.clip
        info = ff.measure_media(c.src or "")
        src_t = c.src_start + max(0.0, t_in_clip)
        if info["duration"] > 0:
            if c.loop_video:
                src_t = src_t % info["duration"]
            else:
                src_t = min(src_t, max(0.0, info["duration"] - 0.05))
        args = [
            ff.ffmpeg_bin(), "-nostdin", "-v", "error", "-ss", f"{src_t:.3f}", *ff.input_guard(), "-i", c.src,
            "-filter_complex", f"[0:v]{video_filter(self.tl, c, self.lut)}[out]", "-map", "[out]",
            "-frames:v", "1", "-f", "rawvideo", "pipe:1",
        ]
        out = subprocess.run(args, capture_output=True, timeout=60, **ff._popen_kwargs(5))
        if out.returncode != 0 or len(out.stdout) < self.frame_bytes:
            img = Image.new("RGB", (self.W, self.H), (0, 0, 0))
        else:
            img = Image.frombuffer("RGB", (self.W, self.H), out.stdout[: self.frame_bytes], "raw", "RGB", 0, 1)
        idx = int(round(t_in_clip * self.tl.fps))
        return self._apply_motion(img.copy(), idx)

    def close(self) -> None:
        if self.proc is not None:
            try:
                if self.proc.stdout:
                    self.proc.stdout.close()
            except OSError:
                pass
            ff.kill(self.proc)
            self.proc = None
        self.last = None


# ---------------------------------------------------------------------------
# Base track
# ---------------------------------------------------------------------------


class BaseTrack:
    """Produces the base RGB frame for frame index k (k must not decrease
    during a render; preview mode allows random access)."""

    def __init__(self, tl: Timeline, *, nice: int = 10, log_path: Optional[str] = None, preview: bool = False,
                 grade_dir: Optional[str] = None):
        self.tl = tl
        self.plans = plan_clips(tl)
        # grade_dir holds the LUT files written for graded video clips (None:
        # a temporary directory, removed by close()).
        self.grader = Grader(tl, grade_dir, nice)
        self.sources: dict[int, Source] = {}
        self.nice = nice
        self.log_path = log_path
        self.preview = preview
        bg = parse_color(tl.background, (4, 6, 10, 255))
        self.bg = Image.new("RGB", (tl.width, tl.height), bg[:3])
        self.black = Image.new("RGB", (tl.width, tl.height), (0, 0, 0))

    def _source(self, plan: ClipPlan) -> Source:
        src = self.sources.get(plan.index)
        if src is None:
            if plan.clip.kind == "video":
                src = VideoSource(self.tl, plan, nice=self.nice, log_path=self.log_path,
                                  lut=self.grader.lut_file(plan.index, plan.clip))
            else:
                src = StillSource(self.tl, plan, self.grader)
            self.sources[plan.index] = src
        return src

    def _clip_frame(self, plan: ClipPlan, k: int) -> Image.Image:
        src = self._source(plan)
        if self.preview and isinstance(src, VideoSource):
            return src.single((k - plan.start_f) / self.tl.fps)
        return src.frame(k)

    def release_before(self, k: int) -> None:
        """Close sources that are no longer needed at frame k or later."""
        for idx in list(self.sources):
            if self.plans[idx].last_needed_f < k:
                self.sources.pop(idx).close()

    def active_index(self, k: int) -> Optional[int]:
        top = None
        for p in self.plans:
            if p.start_f <= k < p.end_f:
                top = p.index
        return top

    def frame(self, k: int) -> Image.Image:
        top_i = self.active_index(k)
        if top_i is None:
            # Under a transition that started in a gap the previous clip may still be needed.
            return self.bg.copy()
        top = self.plans[top_i]
        img = self._clip_frame(top, k)
        local = k - top.start_f
        if top.trans_f <= 0 or local >= top.trans_f:
            return img
        a = local / float(top.trans_f)
        under = self._under(top, k)
        mode = top.clip.transition_in
        if mode == "crossfade":
            base = under if under is not None else self.bg
            if base.size != img.size:
                base = base.resize(img.size)
            return Image.blend(base, img, a)
        # dip_black
        if a < 0.5:
            base = under if under is not None else self.black
            return Image.blend(base, self.black, a * 2.0)
        return Image.blend(self.black, img, (a - 0.5) * 2.0)

    def _under(self, top: ClipPlan, k: int) -> Optional[Image.Image]:
        # Another clip active underneath at k (overlapping clips) wins.
        cand = None
        for p in self.plans:
            if p.index == top.index:
                continue
            if p.start_f <= k < p.end_f and p.index < top.index:
                cand = p
        if cand is None:
            # The previous clip, if it ends where this one starts.
            for p in self.plans[: top.index][::-1]:
                if abs(p.end_f - top.start_f) <= 1 and p.last_needed_f >= k:
                    cand = p
                    break
        if cand is None:
            return None
        return self._clip_frame(cand, k)

    def close(self) -> None:
        for src in self.sources.values():
            src.close()
        self.sources.clear()
        self.grader.close()
