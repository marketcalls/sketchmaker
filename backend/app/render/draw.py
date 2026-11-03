"""Pillow drawing primitives.

Everything is drawn as 8 bit ``L`` coverage masks and then colorized, never
by drawing colored ink straight onto a transparent RGBA canvas: Pillow blends
anti-aliased edges against the canvas color (transparent black), which leaves
dark fringes. Shapes are supersampled for anti-aliasing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Sequence

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .colors import RGBA, parse_color

SS = 3  # supersampling factor for shapes


@dataclass(frozen=True)
class Shadow:
    dx: float
    dy: float
    blur: float  # CSS blur radius in px (Gaussian sigma = blur / 2)
    color: RGBA


def solid(size: tuple[int, int], color: RGBA) -> Image.Image:
    return Image.new("RGBA", size, color)


def colorize(mask: Image.Image, color: RGBA) -> Image.Image:
    """RGBA image of ``color`` with ``mask`` (L) times the color alpha as alpha."""
    img = Image.new("RGBA", mask.size, (color[0], color[1], color[2], 0))
    if color[3] >= 255:
        img.putalpha(mask)
    else:
        a = color[3] / 255.0
        img.putalpha(mask.point(lambda v: int(v * a + 0.5)))
    return img


@lru_cache(maxsize=64)
def _alpha_lut(o256: int) -> tuple[int, ...]:
    o = o256 / 256.0
    return tuple(int(v * o + 0.5) for v in range(256))


def scale_alpha(img: Image.Image, opacity: float) -> Image.Image:
    """Copy of an RGBA image with alpha multiplied by ``opacity``."""
    if opacity >= 0.999:
        return img
    o = max(0, min(256, int(round(opacity * 256))))
    out = img.copy()
    out.putalpha(img.getchannel("A").point(list(_alpha_lut(o))))
    return out


def scale_mask(mask: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 0.999:
        return mask
    o = max(0, min(256, int(round(opacity * 256))))
    return mask.point(list(_alpha_lut(o)))


def blur_mask(mask: Image.Image, blur: float) -> Image.Image:
    sigma = blur / 2.0
    if sigma < 0.3:
        return mask
    return mask.filter(ImageFilter.GaussianBlur(sigma))


def shadow_from_alpha(alpha: Image.Image, shadow: Shadow) -> tuple[Image.Image, int, int]:
    """Blurred shadow sprite for a coverage mask. Returns (sprite, ox, oy):
    the sprite's top-left relative to the mask's top-left."""
    pad = int(math.ceil(shadow.blur * 1.5)) + 2
    w, h = alpha.size
    big = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    big.paste(alpha, (pad, pad))
    big = blur_mask(big, shadow.blur)
    return colorize(big, shadow.color), int(round(shadow.dx)) - pad, int(round(shadow.dy)) - pad


@lru_cache(maxsize=128)
def rounded_mask(w: int, h: int, radius: float, ss: int = SS) -> Image.Image:
    """Anti-aliased rounded rectangle coverage mask of exactly w x h."""
    w, h = max(1, int(w)), max(1, int(h))
    r = max(0.0, min(radius, w / 2.0, h / 2.0))
    big = Image.new("L", (w * ss, h * ss), 0)
    d = ImageDraw.Draw(big)
    if r <= 0.5:
        d.rectangle((0, 0, w * ss - 1, h * ss - 1), fill=255)
    else:
        d.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=r * ss, fill=255)
    return big.resize((w, h), Image.Resampling.BOX)


@lru_cache(maxsize=64)
def ellipse_mask(w: int, h: int, ss: int = SS) -> Image.Image:
    w, h = max(1, int(w)), max(1, int(h))
    big = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(big).ellipse((0, 0, w * ss - 1, h * ss - 1), fill=255)
    return big.resize((w, h), Image.Resampling.BOX)


def box_sprite(
    w: int,
    h: int,
    radius: float,
    fill: RGBA,
    border: Optional[RGBA] = None,
    border_w: float = 0.0,
    shadow: Optional[Shadow] = None,
) -> tuple[Image.Image, int, int]:
    """A filled rounded box with optional inside border and drop shadow.
    Returns (sprite, ox, oy): the box's top-left inside the sprite is at
    (-ox, -oy), i.e. paste the sprite at (box_x + ox, box_y + oy)."""
    return _box_sprite(int(w), int(h), round(radius, 2), fill, border, round(border_w, 2), shadow)


@lru_cache(maxsize=64)
def _box_sprite(w, h, radius, fill, border, border_w, shadow):
    outer = rounded_mask(w, h, radius)
    body = colorize(outer, fill)
    if border and border_w > 0:
        bw = max(1.0, border_w)
        inner_w, inner_h = int(round(w - 2 * bw)), int(round(h - 2 * bw))
        if inner_w > 0 and inner_h > 0:
            inner = Image.new("L", (w, h), 0)
            inner.paste(rounded_mask(inner_w, inner_h, max(0.0, radius - bw)), (int(round(bw)), int(round(bw))))
            ring = ImageChops.subtract(outer, inner)
            body = Image.alpha_composite(body, colorize(ring, border))
    if not shadow:
        return body, 0, 0
    sh, sx, sy = shadow_from_alpha(outer, shadow)
    left, top = min(0, sx), min(0, sy)
    right, bottom = max(w, sx + sh.width), max(h, sy + sh.height)
    canvas = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
    canvas.alpha_composite(sh, (sx - left, sy - top))
    canvas.alpha_composite(body, (-left, -top))
    return canvas, left, top


def gradient_mask_vertical(size: tuple[int, int], stops: Sequence[tuple[float, float]]) -> Image.Image:
    """L mask varying top to bottom. ``stops`` are (pos, alpha 0..1) with pos 0
    at the BOTTOM and 1 at the top (CSS "to top")."""
    w, h = size
    stops = sorted(stops)
    col = Image.new("L", (1, h))
    px = col.load()
    for y in range(h):
        pos = 1.0 - (y + 0.5) / h
        a = stops[0][1]
        for (p0, a0), (p1, a1) in zip(stops, stops[1:]):
            if p0 <= pos <= p1:
                a = a0 + (a1 - a0) * ((pos - p0) / (p1 - p0) if p1 > p0 else 0)
                break
        else:
            if pos > stops[-1][0]:
                a = stops[-1][1]
        px[0, y] = int(round(max(0.0, min(1.0, a)) * 255))
    return col.resize((w, h), Image.Resampling.NEAREST)


def vignette_mask(size: tuple[int, int], inner: float, strength: float) -> Image.Image:
    """CSS radial-gradient(ellipse at center, transparent inner, black
    strength at 100%) as an L mask (farthest-corner ellipse)."""
    w, h = size
    rad = Image.radial_gradient("L")  # 256x256, value = 255 * r / 128 (clipped)
    big = rad.resize((int(math.ceil(w * math.sqrt(2))), int(math.ceil(h * math.sqrt(2)))), Image.Resampling.BILINEAR)
    left = (big.width - w) // 2
    top = (big.height - h) // 2
    r = big.crop((left, top, left + w, top + h))
    lut = []
    for v in range(256):
        x = v / 255.0
        if x <= inner:
            lut.append(0)
        else:
            t = (x - inner) / max(1e-6, 1.0 - inner)
            lut.append(int(round(min(1.0, t) * strength * 255)))
    return r.point(lut)


def linear_gradient_rgb(size: tuple[int, int], colors: Sequence[RGBA], angle: float = 180.0) -> Image.Image:
    """CSS linear-gradient(<angle>deg, colors...) as RGB, lightly dithered."""
    w, h = size
    if not colors:
        colors = [(0, 0, 0, 255)]
    if len(colors) == 1:
        return Image.new("RGB", (w, h), colors[0][:3])
    # Gradient line length per CSS: |w sin a| + |h cos a|
    a = math.radians(angle)
    diag = int(math.ceil(math.hypot(w, h))) + 4
    ramp = Image.linear_gradient("L").resize((diag, diag), Image.Resampling.BILINEAR)  # 0 top -> 255 bottom
    # Rotate so that the ramp runs along the CSS angle (0deg = to top, 180 = to bottom).
    rot = ramp.rotate(-(angle - 180.0), resample=Image.Resampling.BILINEAR, expand=False)
    left = (diag - w) // 2
    top = (diag - h) // 2
    t = rot.crop((left, top, left + w, top + h))
    # Rescale so the CSS gradient line spans exactly 0..255 inside the frame.
    span = abs(w * math.sin(a)) + abs(h * math.cos(a))
    k = diag / max(1.0, span)
    lut_t = [max(0, min(255, int(round((v - 127.5) * k + 127.5)))) for v in range(256)]
    t = t.point(lut_t)
    n = len(colors) - 1
    chans = []
    for ci in range(3):
        lut = []
        for v in range(256):
            pos = v / 255.0 * n
            i = min(n - 1, int(pos))
            f = pos - i
            lut.append(int(round(colors[i][ci] + (colors[i + 1][ci] - colors[i][ci]) * f)))
        chans.append(t.point(lut))
    img = Image.merge("RGB", chans)
    noise = Image.effect_noise((w, h), 1.6)
    noise_rgb = Image.merge("RGB", (noise, noise, noise))
    return ImageChops.add(img, noise_rgb, scale=1.0, offset=-128)


def parse_gradient(value) -> list[RGBA]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p for p in _split_colors(value) if p.strip()]
    else:
        parts = list(value)
    return [parse_color(p, (0, 0, 0, 255)) for p in parts]


def _split_colors(s: str) -> list[str]:
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def paste_sprite(frame: Image.Image, sprite: Image.Image, x: int, y: int) -> None:
    """Composite a straight-alpha RGBA sprite onto an RGB frame."""
    if sprite.width <= 0 or sprite.height <= 0:
        return
    if x >= frame.width or y >= frame.height or x + sprite.width <= 0 or y + sprite.height <= 0:
        return
    frame.paste(sprite, (x, y), sprite)
