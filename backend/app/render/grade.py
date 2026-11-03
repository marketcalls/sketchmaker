"""Colour grade for the base track (``Timeline.grade``).

A look is a 33 point 3D LUT from ``looks/`` (built offline by
looks/build_looks.py). It applies to image and video clips only: colour and
gradient clips, overlays, captions and end cards are drawn after the base
track and never pass through it. Stills are graded once per clip on their
plate with Pillow's ``Color3DLUT``; video clips get ffmpeg ``lut3d`` at the
end of their decode filter (base.video_filter), so every frame is graded
inside the decoder.

``strength`` is baked into the table (identity plus strength times the
look's change), which equals a per pixel blend with the ungraded picture.
"neutral" or a strength of 0 is no grade at all: the clip is not touched.

With ``grade.match`` on, a clip that names an approved plate
(``Clip.match_ref``) is first pulled toward that plate's colour with a
Reinhard transfer in CIE Lab (the scenario-video-color-grade skill's
scripts/match.py), ``match_strength`` of the way. That reduces colour drift
between generated clips of one scene. The transfer is a fixed function of
colour, so it is baked into the same LUT, ahead of the look.

Pure Python (no numpy): a 33 point table is 35,937 entries, which takes a
fraction of a second per graded clip.
"""

from __future__ import annotations

import logging
import math
import os
import shutil
import subprocess
import tempfile
from functools import lru_cache
from typing import Optional

from PIL import Image, ImageFilter, ImageOps

from . import ffmpeg as ff
from .timeline import GRADE_LOOKS, Clip, Grade, RenderError, Timeline

log = logging.getLogger(__name__)

LOOKS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "looks")

# id -> (label, one line description). The ids are GRADE_LOOKS (timeline.py).
LOOKS: dict[str, tuple[str, str]] = {
    "neutral": ("Neutral", "No grade: the pictures as generated"),
    "warm_film": ("Warm film", "A little warmer, soft lifted blacks, a gentle print shoulder"),
    "teal_orange": ("Teal and orange", "Warm skin against teal shadows, kept gentle"),
    "cool_clean": ("Cool clean", "Cooler and crisp, a modern clean feel"),
    "soft_pastel": ("Soft pastel", "Brighter and flatter with softened colour"),
    "mono_contrast": ("High contrast mono", "Black and white with deep blacks"),
    "golden_hour": ("Golden hour", "Late sun warmth with golden highlights"),
    "documentary_muted": ("Documentary muted", "Muted, natural colour like available light"),
}
assert tuple(LOOKS) == GRADE_LOOKS

LUT_SIZE = 33
# Reinhard spread ratios are kept in this range: a plate much flatter or
# punchier than the clip should nudge it, not crush or blow it out.
MATCH_SPREAD_RANGE = (0.6, 1.6)
SAMPLE_SIDE = 48  # pixels per side of each colour statistics sample

Table = tuple[int, list[float]]  # (points per axis, flat RGB list, red fastest)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def look_path(look: str) -> Optional[str]:
    if look == "neutral" or look not in LOOKS:
        return None
    return os.path.join(LOOKS_DIR, f"{look}.cube")


@lru_cache(maxsize=16)
def read_cube(path: str) -> Table:
    size = 0
    values: list[float] = []
    try:
        with open(path, "r", encoding="ascii") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                head = line.split(None, 1)[0]
                if head == "LUT_3D_SIZE":
                    size = int(line.split()[1])
                    continue
                if head[0].isalpha():  # TITLE, DOMAIN_MIN, DOMAIN_MAX and other keywords
                    continue
                values.extend(float(v) for v in line.split()[:3])
    except (OSError, ValueError) as exc:
        raise RenderError(f"cannot read grade look {os.path.basename(path)}: {exc}") from exc
    if size < 2 or len(values) != size ** 3 * 3:
        raise RenderError(f"grade look {os.path.basename(path)} is not a {size} point 3D LUT")
    return size, values


def identity(size: int = LUT_SIZE) -> list[float]:
    step = 1.0 / (size - 1)
    out: list[float] = []
    for b in range(size):
        for g in range(size):
            for r in range(size):
                out.extend((r * step, g * step, b * step))
    return out


@lru_cache(maxsize=16)
def look_table(look: str, strength: float) -> Optional[Table]:
    """The look at ``strength`` (0 to 1), or None when it changes nothing."""
    path = look_path(look)
    if path is None or strength <= 0.0:
        return None
    size, table = read_cube(path)
    if strength >= 1.0:
        return size, table
    base = identity(size)
    return size, [i + strength * (t - i) for i, t in zip(base, table)]


def sample(table: Table, r: float, g: float, b: float) -> tuple[float, float, float]:
    """Trilinear lookup of one colour (0 to 1 per channel)."""
    size, t = table
    n = size - 1
    fr, fg, fb = (min(max(v, 0.0), 1.0) * n for v in (r, g, b))
    r0, g0, b0 = min(int(fr), n - 1), min(int(fg), n - 1), min(int(fb), n - 1)
    dr, dg, db = fr - r0, fg - g0, fb - b0
    out = [0.0, 0.0, 0.0]
    for ib, wb in ((b0, 1 - db), (b0 + 1, db)):
        if wb == 0:
            continue
        for ig, wg in ((g0, 1 - dg), (g0 + 1, dg)):
            if wg == 0:
                continue
            for ir, wr in ((r0, 1 - dr), (r0 + 1, dr)):
                w = wb * wg * wr
                if w == 0:
                    continue
                k = ((ib * size + ig) * size + ir) * 3
                out[0] += w * t[k]
                out[1] += w * t[k + 1]
                out[2] += w * t[k + 2]
    return out[0], out[1], out[2]


# ---------------------------------------------------------------------------
# CIE Lab (D65) and the Reinhard transfer
# ---------------------------------------------------------------------------

_M = ((0.4124, 0.3576, 0.1805), (0.2126, 0.7152, 0.0722), (0.0193, 0.1192, 0.9505))
_WHITE = tuple(sum(row) for row in _M)
_MI = (
    (3.2406, -1.5372, -0.4986),
    (-0.9689, 1.8758, 0.0415),
    (0.0557, -0.2040, 1.0570),
)


def _f(t: float) -> float:
    return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0


def _finv(t: float) -> float:
    return t ** 3 if t > 0.2069 else (t - 16.0 / 116.0) / 7.787


def rgb_to_lab(r: float, g: float, b: float) -> tuple[float, float, float]:
    lin = (max(0.0, r) ** 2.4, max(0.0, g) ** 2.4, max(0.0, b) ** 2.4)
    x, y, z = (sum(_M[i][j] * lin[j] for j in range(3)) / _WHITE[i] for i in range(3))
    fx, fy, fz = _f(x), _f(y), _f(z)
    return 116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)


def lab_to_rgb(l: float, a: float, bb: float) -> tuple[float, float, float]:
    fy = (l + 16.0) / 116.0
    xyz = (_finv(fy + a / 500.0) * _WHITE[0], _finv(fy) * _WHITE[1], _finv(fy - bb / 200.0) * _WHITE[2])
    lin = (sum(_MI[i][j] * xyz[j] for j in range(3)) for i in range(3))
    return tuple(min(1.0, max(0.0, v) ** (1 / 2.4)) for v in lin)  # type: ignore[return-value]


def lab_stats(pixels) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """(mean, standard deviation) of L, a, b over 8-bit RGB tuples."""
    n = 0
    s = [0.0, 0.0, 0.0]
    sq = [0.0, 0.0, 0.0]
    for p in pixels:
        lab = rgb_to_lab(p[0] / 255.0, p[1] / 255.0, p[2] / 255.0)
        n += 1
        for i in range(3):
            s[i] += lab[i]
            sq[i] += lab[i] * lab[i]
    if n == 0:
        raise RenderError("no pixels to measure")
    mean = tuple(v / n for v in s)
    std = tuple(math.sqrt(max(0.0, sq[i] / n - mean[i] ** 2)) for i in range(3))
    return mean, std  # type: ignore[return-value]


def match_table(src, ref, strength: float, size: int = LUT_SIZE) -> Table:
    """A LUT moving colours with the source's Lab statistics ``src`` toward
    the reference's ``ref`` (both (mean, std)), ``strength`` of the way."""
    (sm, ss), (rm, rs) = src, ref
    lo, hi = MATCH_SPREAD_RANGE
    k = [min(hi, max(lo, rs[i] / max(ss[i], 1e-6))) for i in range(3)]
    base = identity(size)
    out: list[float] = []
    for j in range(0, len(base), 3):
        r, g, b = base[j], base[j + 1], base[j + 2]
        lab = rgb_to_lab(r, g, b)
        moved = lab_to_rgb(*((lab[i] - sm[i]) * k[i] + rm[i] for i in range(3)))
        out.extend((r + strength * (moved[0] - r), g + strength * (moved[1] - g), b + strength * (moved[2] - b)))
    return size, out


def compose(first: Table, then: Optional[Table]) -> Table:
    """``first`` followed by ``then``, on ``first``'s grid."""
    if then is None:
        return first
    size, t = first
    out: list[float] = []
    for j in range(0, len(t), 3):
        out.extend(sample(then, t[j], t[j + 1], t[j + 2]))
    return size, out


def write_table(table: Table, path: str) -> str:
    size, t = table
    lines = ["TITLE \"SketchMaker grade\"", f"LUT_3D_SIZE {size}"]
    lines.extend(f"{t[j]:.5f} {t[j + 1]:.5f} {t[j + 2]:.5f}" for j in range(0, len(t), 3))
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def pillow_filter(table: Table) -> ImageFilter.Color3DLUT:
    size, t = table
    return ImageFilter.Color3DLUT(size, t)


def apply_to_image(img: Image.Image, table: Optional[Table]) -> Image.Image:
    """``img`` (RGB) through ``table``; unchanged when there is none."""
    if table is None:
        return img
    return img.convert("RGB").filter(pillow_filter(table))


def filter_path(path: str) -> str:
    """``path`` as an ffmpeg filter option value (quoted; ``:`` escaped for
    Windows drive letters)."""
    if "'" in path:
        raise RenderError("grade LUT path contains a quote")
    return "'" + path.replace("\\", "/").replace(":", "\\:") + "'"


# ---------------------------------------------------------------------------
# Measuring clips and plates
# ---------------------------------------------------------------------------

def image_pixels(path: str) -> list:
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im.draft("RGB", (SAMPLE_SIDE * 4, SAMPLE_SIDE * 4))
        small = im.convert("RGB").resize((SAMPLE_SIDE, SAMPLE_SIDE), Image.Resampling.BILINEAR)
        return list(small.getdata())


def video_pixels(c: Clip, nice: int = 10) -> list:
    """Pixels of three frames across the part of the video the clip shows."""
    info = ff.measure_media(c.src or "")
    dur = float(info.get("duration") or 0.0)
    span = c.duration * c.speed
    end = c.src_start + span
    if dur > 0 and not c.loop_video:
        end = min(end, dur)
    times = [c.src_start + (end - c.src_start) * f for f in (0.15, 0.5, 0.85)]
    frame = SAMPLE_SIDE * SAMPLE_SIDE * 3
    pixels: list = []
    for t in times:
        args = [ff.ffmpeg_bin(), "-nostdin", "-v", "error", "-ss", f"{max(0.0, t):.3f}", *ff.input_guard(),
                "-i", c.src or "", "-frames:v", "1", "-vf", f"scale={SAMPLE_SIDE}:{SAMPLE_SIDE}",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
        out = subprocess.run(args, capture_output=True, timeout=60, **ff._popen_kwargs(nice))
        if out.returncode == 0 and len(out.stdout) >= frame:
            data = out.stdout[:frame]
            pixels.extend((data[i], data[i + 1], data[i + 2]) for i in range(0, frame, 3))
    if not pixels:
        raise RenderError(f"cannot sample video colours: {c.src}")
    return pixels


# ---------------------------------------------------------------------------
# Per clip grades for one render
# ---------------------------------------------------------------------------

def gradable(c: Clip) -> bool:
    return c.kind in ("image", "video") and c.grade


def active(grade: Optional[Grade]) -> bool:
    if grade is None:
        return False
    return (grade.look != "neutral" and grade.strength > 0) or (grade.match and grade.match_strength > 0)


class Grader:
    """The grade table of every clip of a render, built on first use.

    ``workdir`` holds the LUT files written for video clips (a temporary
    directory is made and removed by close() when it is None). A clip whose
    match cannot be measured keeps the plain look: the drift correction is a
    refinement, never a reason to fail a render.
    """

    def __init__(self, tl: Timeline, workdir: Optional[str] = None, nice: int = 10):
        self.tl = tl
        self.grade = tl.grade if active(tl.grade) else None
        self.nice = nice
        self._dir = workdir
        self._own_dir = False
        self._tables: dict[int, Optional[Table]] = {}
        self._matched: set[int] = set()
        self._files: dict[int, Optional[str]] = {}
        self._plates: dict[str, tuple] = {}

    def table(self, index: int, c: Clip) -> Optional[Table]:
        if index in self._tables:
            return self._tables[index]
        result: Optional[Table] = None
        if self.grade is not None and gradable(c):
            look = look_table(self.grade.look, round(float(self.grade.strength), 3))
            result = look
            if self.grade.match and self.grade.match_strength > 0 and c.match_ref:
                try:
                    result = compose(self._match(c), look)
                    self._matched.add(index)
                except (RenderError, OSError, ValueError) as exc:
                    log.warning("grade match skipped for clip %d: %s", index, exc)
        self._tables[index] = result
        return result

    def _match(self, c: Clip) -> Table:
        ref = self._plates.get(c.match_ref or "")
        if ref is None:
            if not c.match_ref or not os.path.isfile(c.match_ref):
                raise RenderError("plate not found")
            ref = lab_stats(image_pixels(c.match_ref))
            self._plates[c.match_ref] = ref
        if c.kind == "video":
            src = lab_stats(video_pixels(c, self.nice))
        else:
            src = lab_stats(image_pixels(c.src or ""))
        return match_table(src, ref, float(self.grade.match_strength))  # type: ignore[union-attr]

    def lut_file(self, index: int, c: Clip) -> Optional[str]:
        """A .cube path for ffmpeg lut3d, or None for no grade."""
        if index in self._files:
            return self._files[index]
        table = self.table(index, c)
        path: Optional[str] = None
        if table is not None:
            if index not in self._matched and self.grade.strength >= 1.0:  # type: ignore[union-attr]
                path = look_path(self.grade.look)  # type: ignore[union-attr]  # the bundled file as is
            elif index not in self._matched:
                # The look at a lower strength: one file shared by every clip.
                path = self._files.get(-1)
                if path is None:
                    path = write_table(table, os.path.join(self._workdir(), "grade_look.cube"))
                    self._files[-1] = path
            else:
                path = write_table(table, os.path.join(self._workdir(), f"grade_{index}.cube"))
        self._files[index] = path
        return path

    def _workdir(self) -> str:
        if self._dir is None:
            self._dir = tempfile.mkdtemp(prefix="grade_")
            self._own_dir = True
        os.makedirs(self._dir, exist_ok=True)
        return self._dir

    def close(self) -> None:
        if self._own_dir and self._dir:
            shutil.rmtree(self._dir, ignore_errors=True)
            self._dir = None
            self._own_dir = False


def looks_catalog() -> list[dict]:
    """For UIs: [{id, label, description}] in display order."""
    return [{"id": k, "label": v[0], "description": v[1]} for k, v in LOOKS.items()]


__all__ = [
    "Grader",
    "LOOKS",
    "LUT_SIZE",
    "apply_to_image",
    "compose",
    "filter_path",
    "identity",
    "lab_stats",
    "look_table",
    "looks_catalog",
    "match_table",
    "read_cube",
    "sample",
]
