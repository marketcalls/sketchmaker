"""Drawing primitives for motion graphics elements.

Glyphs are rendered as coverage masks with Pillow (bundled OFL fonts through
app.render.fonts, so variable weights work) and colorized, like the engine's
text module, but with features the motion templates need: per word sprites
with tracking, outline-only glyphs, fixed-cell (monospaced) layout and
tabular digit cells. Everything is cached in small LRUs: a 60 second render
draws a few thousand distinct sprites at most.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from app.render import fonts
from app.render.colors import RGBA, parse_color
from app.render.draw import colorize, ellipse_mask, rounded_mask

SS = 3


class LRU(OrderedDict):
    def __init__(self, size: int):
        super().__init__()
        self.size = size

    def get_or(self, key, factory):
        if key in self:
            self.move_to_end(key)
            return self[key]
        val = factory()
        self[key] = val
        if len(self) > self.size:
            self.popitem(last=False)
        return val


_GLYPHS = LRU(2500)
_SHAPES = LRU(400)


def rgba(c, default: RGBA = (255, 255, 255, 255)) -> RGBA:
    if isinstance(c, tuple):
        return c
    return parse_color(c, default)


def with_a(c: RGBA, a: float) -> RGBA:
    return (c[0], c[1], c[2], int(round(c[3] * max(0.0, min(1.0, a)))))


@dataclass
class Glyph:
    img: Optional[Image.Image]  # RGBA, None for blank text
    ox: int  # sprite top-left relative to the pen position (left, baseline)
    oy: int
    adv: float  # advance width in px
    asc: int
    desc: int


def font(family: str, weight: int, size: float, text: str = ""):
    return fonts.font_for(family, int(weight), max(4, int(round(size))), text)


def measure(text: str, family: str, weight: int, size: float, tracking: float = 0.0,
            mono_cell: Optional[float] = None) -> float:
    if not text:
        return 0.0
    if mono_cell:
        return mono_cell * len(text)
    f = font(family, weight, size, text)
    return f.getlength(text) + tracking * (len(text) - 1)


def metrics(family: str, weight: int, size: float) -> tuple[int, int]:
    return font(family, weight, size).getmetrics()


def cap_height(family: str, weight: int, size: float) -> float:
    f = font(family, weight, size)
    try:
        box = f.getbbox("H", anchor="ls")
        return float(-box[1])
    except Exception:
        return size * 0.7


def mono_cell_width(family: str, weight: int, size: float) -> float:
    f = font(family, weight, size)
    return max(f.getlength(ch) for ch in "0nae") * 1.1


def digit_cell(family: str, weight: int, size: float) -> float:
    f = font(family, weight, size)
    return max(f.getlength(d) for d in "0123456789")


def glyph(text: str, family: str, weight: int, size: float, color, *, tracking: float = 0.0,
          stroke: float = 0.0, stroke_color=None, outline: bool = False,
          mono_cell: Optional[float] = None) -> Glyph:
    """A text run as one sprite. ``outline`` draws only the stroke ring."""
    c = rgba(color)
    sc = rgba(stroke_color) if stroke_color is not None else c
    key = (text, family, int(weight), int(round(size)), c, round(tracking, 2), round(stroke, 1), sc, outline,
           round(mono_cell, 2) if mono_cell else None)
    return _GLYPHS.get_or(key, lambda: _make_glyph(text, family, int(weight), size, c, tracking, stroke, sc,
                                                    outline, mono_cell))


def _draw_text(mask: Image.Image, origin, text: str, f, tracking: float, stroke: int, mono_cell):
    d = ImageDraw.Draw(mask)
    x0, y0 = origin
    if mono_cell:
        for i, ch in enumerate(text):
            w = f.getlength(ch)
            d.text((x0 + i * mono_cell + (mono_cell - w) / 2, y0), ch, font=f, fill=255, anchor="ls",
                   stroke_width=stroke, stroke_fill=255)
        return
    if not tracking or len(text) == 1 or fonts.needs_devanagari(text):
        d.text((x0, y0), text, font=f, fill=255, anchor="ls", stroke_width=stroke, stroke_fill=255)
        return
    for i, ch in enumerate(text):
        x = x0 + f.getlength(text[:i]) + tracking * i
        d.text((x, y0), ch, font=f, fill=255, anchor="ls", stroke_width=stroke, stroke_fill=255)


def _make_glyph(text, family, weight, size, color, tracking, stroke, stroke_color, outline, mono_cell) -> Glyph:
    f = font(family, weight, size, text)
    asc, desc = f.getmetrics()
    adv = measure(text, family, weight, size, tracking, mono_cell)
    if not text or not text.strip():
        return Glyph(None, 0, 0, adv, asc, desc)
    sw = int(round(stroke))
    pad = sw + int(math.ceil(size * 0.25)) + 2
    w = int(math.ceil(adv)) + 2 * pad
    h = int(asc + desc) + 2 * pad
    origin = (pad, pad + asc)
    fill = Image.new("L", (w, h), 0)
    _draw_text(fill, origin, text, f, tracking, 0, mono_cell)
    if sw > 0:
        full = Image.new("L", (w, h), 0)
        _draw_text(full, origin, text, f, tracking, sw, mono_cell)
        if outline:
            ring = ImageChops.subtract(full, fill)
            img = colorize(ring, stroke_color)
            cover = ring
        else:
            img = Image.alpha_composite(colorize(full, stroke_color), colorize(fill, color))
            cover = full
    else:
        img = colorize(fill, color)
        cover = fill
    bbox = cover.getbbox()
    if bbox is None:
        return Glyph(None, 0, 0, adv, asc, desc)
    img = img.crop(bbox)
    return Glyph(img, bbox[0] - origin[0], bbox[1] - origin[1], adv, asc, desc)


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

def rect(w: float, h: float, color, radius: float = 0.0) -> Image.Image:
    w, h = max(1, int(round(w))), max(1, int(round(h)))
    c = rgba(color)
    key = ("rect", w, h, round(radius, 1), c)

    def make():
        if radius <= 0.5:
            return Image.new("RGBA", (w, h), c)
        return colorize(rounded_mask(w, h, radius), c)

    if w * h > 400_000:  # large panels are not worth caching per size
        return make()
    return _SHAPES.get_or(key, make)


def frame_rect(w: float, h: float, color, width: float, radius: float = 0.0) -> Image.Image:
    """Outline of a (rounded) rectangle, ``width`` px inside the box."""
    w, h = max(2, int(round(w))), max(2, int(round(h)))
    c = rgba(color)
    bw = max(1.0, width)
    key = ("frame", w, h, round(bw, 1), round(radius, 1), c)

    def make():
        outer = rounded_mask(w, h, radius)
        iw, ih = int(round(w - 2 * bw)), int(round(h - 2 * bw))
        if iw <= 0 or ih <= 0:
            return colorize(outer, c)
        inner = Image.new("L", (w, h), 0)
        inner.paste(rounded_mask(iw, ih, max(0.0, radius - bw)), (int(round(bw)), int(round(bw))))
        return colorize(ImageChops.subtract(outer, inner), c)

    return _SHAPES.get_or(key, make)


def circle(d: float, color) -> Image.Image:
    d = max(1, int(round(d)))
    c = rgba(color)
    return _SHAPES.get_or(("circle", d, c), lambda: colorize(ellipse_mask(d, d), c))


def ring(d: float, width: float, color, sweep: float = 360.0, start: float = -90.0) -> Image.Image:
    """Circle outline, drawn clockwise from ``start`` over ``sweep`` degrees."""
    d = max(2, int(round(d)))
    c = rgba(color)
    sweep = max(0.0, min(360.0, sweep))
    key = ("ring", d, round(width, 1), c, round(sweep, 1), round(start, 1))

    def make():
        big = Image.new("L", (d * SS, d * SS), 0)
        dr = ImageDraw.Draw(big)
        wpx = max(1, int(round(width * SS)))
        if sweep >= 359.9:
            dr.ellipse((0, 0, d * SS - 1, d * SS - 1), outline=255, width=wpx)
        elif sweep > 0.1:
            dr.arc((0, 0, d * SS - 1, d * SS - 1), start, start + sweep, fill=255, width=wpx)
        return colorize(big.resize((d, d), Image.Resampling.BOX), c)

    return _SHAPES.get_or(key, make)


def donut_slice(d: float, thickness: float, a0: float, a1: float, color) -> Image.Image:
    d = max(2, int(round(d)))
    big = Image.new("L", (d * SS, d * SS), 0)
    dr = ImageDraw.Draw(big)
    dr.pieslice((0, 0, d * SS - 1, d * SS - 1), a0, a1, fill=255)
    hole = int(round((d - 2 * thickness) * SS))
    off = (d * SS - hole) // 2
    if hole > 0:
        dr.ellipse((off, off, off + hole, off + hole), fill=0)
    return colorize(big.resize((d, d), Image.Resampling.BOX), rgba(color))


def triangle(w: float, h: float, color, up: bool = True) -> Image.Image:
    w, h = max(2, int(round(w))), max(2, int(round(h)))
    c = rgba(color)

    def make():
        big = Image.new("L", (w * SS, h * SS), 0)
        pts = [(w * SS / 2, 0), (w * SS, h * SS), (0, h * SS)] if up else [(0, 0), (w * SS, 0), (w * SS / 2, h * SS)]
        ImageDraw.Draw(big).polygon(pts, fill=255)
        return colorize(big.resize((w, h), Image.Resampling.BOX), c)

    return _SHAPES.get_or(("tri", w, h, c, up), make)


def polyline(size: tuple[int, int], pts: list[tuple[float, float]], width: float, color,
             round_caps: bool = True) -> Image.Image:
    """Anti-aliased polyline on a transparent canvas of ``size``."""
    W, H = size
    big = Image.new("L", (W * 2, H * 2), 0)
    dr = ImageDraw.Draw(big)
    if len(pts) >= 2:
        dr.line([(x * 2, y * 2) for x, y in pts], fill=255, width=max(1, int(round(width * 2))), joint="curve")
    if round_caps and pts:
        r = width
        for x, y in (pts[0], pts[-1]):
            dr.ellipse((x * 2 - r, y * 2 - r, x * 2 + r, y * 2 + r), fill=255)
    return colorize(big.resize((W, H), Image.Resampling.BOX), rgba(color))


def area_fill(size: tuple[int, int], pts: list[tuple[float, float]], base_y: float, color, top_alpha: float,
              top_y: float) -> Image.Image:
    """Polygon under a line, fading from ``top_alpha`` at top_y to 0 at base_y."""
    W, H = size
    if len(pts) < 2:
        return Image.new("RGBA", (W, H), (0, 0, 0, 0))
    big = Image.new("L", (W * 2, H * 2), 0)
    poly = [(x * 2, y * 2) for x, y in pts] + [(pts[-1][0] * 2, base_y * 2), (pts[0][0] * 2, base_y * 2)]
    ImageDraw.Draw(big).polygon(poly, fill=255)
    m = big.resize((W, H), Image.Resampling.BOX)
    grad = Image.new("L", (1, H), 0)
    px = grad.load()
    span = max(1.0, base_y - top_y)
    for y in range(H):
        f = (base_y - y) / span
        px[0, y] = int(round(max(0.0, min(1.0, f)) * top_alpha * 255))
    m = ImageChops.multiply(m, grad.resize((W, H)))
    return colorize(m, rgba(color))


# ---------------------------------------------------------------------------
# Sprite transforms
# ---------------------------------------------------------------------------

def alpha(img: Image.Image, a: float) -> Image.Image:
    if a >= 0.999:
        return img
    a = max(0.0, a)
    out = img.copy()
    out.putalpha(img.getchannel("A").point(lambda v: int(v * a + 0.5)))
    return out


def scaled(img: Image.Image, s: float, fast: bool = False) -> Image.Image:
    if abs(s - 1.0) < 0.002:
        return img
    w = max(1, int(round(img.width * s)))
    h = max(1, int(round(img.height * s)))
    return img.resize((w, h), Image.Resampling.BILINEAR if fast else Image.Resampling.BICUBIC)


def blurred(img: Image.Image, radius: float) -> Image.Image:
    if radius < 0.4:
        return img
    pad = int(math.ceil(radius * 2))
    canvas = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
    canvas.paste(img, (pad, pad))
    return canvas.filter(ImageFilter.GaussianBlur(radius)), pad  # type: ignore[return-value]


def rotated(img: Image.Image, degrees: float) -> tuple[Image.Image, float, float]:
    """Rotate about the center; returns (sprite, dx, dy) to add to the original top-left."""
    if abs(degrees) < 0.05:
        return img, 0.0, 0.0
    out = img.rotate(degrees, resample=Image.Resampling.BICUBIC, expand=True)
    return out, (img.width - out.width) / 2.0, (img.height - out.height) / 2.0


def crop_to(img: Image.Image, x: float, y: float, clip: tuple[float, float, float, float]):
    """Crop a sprite placed at (x, y) to the clip rect; returns (img, x, y) or None."""
    cx0, cy0, cx1, cy1 = clip
    x0, y0 = int(round(x)), int(round(y))
    l = max(0, int(math.floor(cx0)) - x0)
    t = max(0, int(math.floor(cy0)) - y0)
    r = min(img.width, int(math.ceil(cx1)) - x0)
    b = min(img.height, int(math.ceil(cy1)) - y0)
    if r <= l or b <= t:
        return None
    if l == 0 and t == 0 and r == img.width and b == img.height:
        return img, x0, y0
    return img.crop((l, t, r, b)), x0 + l, y0 + t


def load_rgba(path: Optional[str]) -> Optional[Image.Image]:
    import os

    from PIL import ImageOps

    if not path or not os.path.isfile(path):
        return None
    try:
        im = Image.open(path)
        im = ImageOps.exif_transpose(im)
        im.draft("RGB", (4000, 4000))
        return im.convert("RGBA")
    except Exception:
        return None
