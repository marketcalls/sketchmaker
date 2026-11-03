"""Text layout and rendering on top of Pillow.

A text block is a list of runs (eyebrow, headline, subline...) stacked
vertically. Each run wraps to ``max_width`` and the whole block shrinks
uniformly until every word fits and each run is within its ``max_lines``
(auto-fit). Rendering is per word: each word is drawn once into a cached
glyph sprite (stroke under the fill, CSS ``paint-order: stroke fill``) and an
optional blurred shadow sprite, so word level animation (word_pop,
typewriter, the caption highlight) only re-composites small sprites.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from typing import Optional

from PIL import Image, ImageDraw

from . import fonts
from .colors import RGBA
from .draw import Shadow, colorize, shadow_from_alpha

# ---------------------------------------------------------------------------
# Styles and layout structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunStyle:
    family: Optional[str]
    weight: int
    size: float  # px
    color: RGBA
    line_height: float = 1.15
    letter_spacing: float = 0.0  # px
    uppercase: bool = False
    stroke: float = 0.0  # px outside the glyph
    stroke_color: RGBA = (0, 0, 0, 255)
    shadow: Optional[Shadow] = None
    max_lines: Optional[int] = None

    def scaled(self, f: float) -> "RunStyle":
        if f == 1.0:
            return self
        sh = self.shadow
        if sh is not None:
            sh = Shadow(sh.dx * f, sh.dy * f, sh.blur * f, sh.color)
        return replace(
            self,
            size=self.size * f,
            letter_spacing=self.letter_spacing * f,
            stroke=self.stroke * f,
            shadow=sh,
        )


@dataclass(frozen=True)
class Run:
    text: str
    style: RunStyle
    gap_before: float = 0.0  # px above this run (ignored for the first run)


@dataclass
class Word:
    text: str
    x: float  # left edge within the block
    baseline: float  # baseline y within the block
    width: float
    run: int
    unit: int  # word index across the block
    char_start: int  # character index across the block
    line: int


@dataclass
class Line:
    run: int
    top: float
    height: float
    width: float
    x: float


@dataclass
class Block:
    width: float
    height: float
    words: list[Word]
    lines: list[Line]
    styles: list[RunStyle]  # fitted styles per run
    fonts: list  # FreeTypeFont per run
    fit: float  # applied auto-fit factor
    char_count: int
    pad: int = 0  # margin a renderer should leave for strokes and shadows
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class WordState:
    opacity: float = 1.0
    scale: float = 1.0
    dx: float = 0.0
    dy: float = 0.0
    color: Optional[RGBA] = None


IDENTITY = WordState()


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


def _measure(font, text: str, ls: float) -> float:
    if not text:
        return 0.0
    w = font.getlength(text)
    if ls and not fonts.needs_devanagari(text):
        w += ls * (len(text) - 1)
    return w


def _font_for(style: RunStyle, text: str):
    return fonts.font_for(style.family, style.weight, style.size, text)


def _wrap(words: list[str], widths: list[float], space: float, max_width: float) -> list[list[int]]:
    lines: list[list[int]] = []
    cur: list[int] = []
    cur_w = 0.0
    for i, w in enumerate(widths):
        if not cur:
            cur, cur_w = [i], w
            continue
        if cur_w + space + w <= max_width + 0.5:
            cur.append(i)
            cur_w += space + w
        else:
            lines.append(cur)
            cur, cur_w = [i], w
    if cur:
        lines.append(cur)
    return lines


def _balance(words_w: list[float], lines: list[list[int]], space: float, max_width: float) -> list[list[int]]:
    """Avoid a lone short last line (orphan) when two lines would balance."""
    if len(lines) != 2 or len(lines[1]) != 1 or len(lines[0]) < 3:
        return lines
    moved = [lines[0][:-1], [lines[0][-1]] + lines[1]]
    w2 = sum(words_w[i] for i in moved[1]) + space * (len(moved[1]) - 1)
    return moved if w2 <= max_width else lines


def layout_block(
    runs: list[Run],
    max_width: float,
    align: str = "left",
    *,
    fit: bool = True,
    min_fit: float = 0.42,
    balance: bool = True,
    max_height: Optional[float] = None,
) -> Block:
    """Wrap and auto-fit: shrink uniformly until no word is wider than
    ``max_width``, every run is within its ``max_lines`` and, when given, the
    block is no taller than ``max_height``."""
    runs = [r for r in runs if r.text and r.text.strip()]
    f = 1.0
    while True:
        block, ok = _try_layout(runs, max_width, align, f, balance)
        if ok and max_height is not None and block.height > max_height:
            ok = False
        if ok or not fit or f <= min_fit:
            return block
        f *= 0.93


def _try_layout(runs: list[Run], max_width: float, align: str, f: float, balance: bool):
    styles: list[RunStyle] = []
    fnts = []
    words_out: list[Word] = []
    lines_out: list[Line] = []
    y = 0.0
    unit = 0
    chars = 0
    ok = True
    block_w = 0.0
    for ri, run in enumerate(runs):
        st = run.style.scaled(f)
        text = run.text.upper() if st.uppercase else run.text
        font = _font_for(st, text)
        styles.append(st)
        fnts.append(font)
        words = text.split()
        widths = [_measure(font, w, st.letter_spacing) for w in words]
        space = font.getlength(" ") + st.letter_spacing
        if any(w > max_width + 0.5 for w in widths):
            ok = False
        groups = _wrap(words, widths, space, max_width)
        if balance:
            groups = _balance(widths, groups, space, max_width)
        if st.max_lines and len(groups) > st.max_lines:
            ok = False
        if ri > 0:
            y += run.gap_before * f
        asc, desc = font.getmetrics()
        lh = st.size * st.line_height
        for g in groups:
            lw = sum(widths[i] for i in g) + space * (len(g) - 1)
            baseline = y + (lh - (asc + desc)) / 2.0 + asc
            line_idx = len(lines_out)
            x = 0.0
            for i in g:
                words_out.append(Word(words[i], x, baseline, widths[i], ri, unit, chars, line_idx))
                unit += 1
                chars += len(words[i]) + 1
                x += widths[i] + space
            lines_out.append(Line(ri, y, lh, lw, 0.0))
            block_w = max(block_w, lw)
            y += lh
    # Alignment within the block width.
    for li, line in enumerate(lines_out):
        if align == "center":
            line.x = (block_w - line.width) / 2.0
        elif align == "right":
            line.x = block_w - line.width
        else:
            line.x = 0.0
    for w in words_out:
        w.x += lines_out[w.line].x
    pad = 0
    for st in styles:
        p = st.stroke + st.size * 0.25 + 4
        if st.shadow:
            p += st.shadow.blur * 1.5 + max(abs(st.shadow.dx), abs(st.shadow.dy))
        pad = max(pad, int(math.ceil(p)))
    blk = Block(block_w, y, words_out, lines_out, styles, fnts, f, chars, pad)
    return blk, ok


# ---------------------------------------------------------------------------
# Word sprites
# ---------------------------------------------------------------------------


class _LRU(OrderedDict):
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


_WORD_CACHE = _LRU(320)


def _draw_glyphs(mask: Image.Image, origin: tuple[float, float], text: str, font, ls: float, stroke: int) -> None:
    d = ImageDraw.Draw(mask)
    x0, y0 = origin
    if not ls or fonts.needs_devanagari(text) or len(text) == 1:
        d.text((x0, y0), text, font=font, fill=255, anchor="ls", stroke_width=stroke, stroke_fill=255)
        return
    for i, ch in enumerate(text):
        x = x0 + font.getlength(text[:i]) + ls * i
        d.text((x, y0), ch, font=font, fill=255, anchor="ls", stroke_width=stroke, stroke_fill=255)


def word_sprites(text: str, style: RunStyle, color: Optional[RGBA] = None):
    """(glyph RGBA, gx, gy, shadow RGBA or None, sx, sy). Offsets are the
    sprite top-left relative to the word's (left, baseline) point."""
    color = color or style.color
    key = (text, style, color)
    return _WORD_CACHE.get_or(key, lambda: _make_word(text, style, color))


def _make_word(text: str, style: RunStyle, color: RGBA):
    font = _font_for(style, text)
    asc, desc = font.getmetrics()
    sw = int(round(style.stroke))
    width = _measure(font, text, style.letter_spacing)
    pad = sw + int(math.ceil(style.size * 0.2)) + 2
    w = int(math.ceil(width)) + 2 * pad
    h = int(asc + desc) + 2 * pad
    origin = (pad, pad + asc)
    fill_mask = Image.new("L", (w, h), 0)
    _draw_glyphs(fill_mask, origin, text, font, style.letter_spacing, 0)
    if sw > 0:
        full = Image.new("L", (w, h), 0)
        _draw_glyphs(full, origin, text, font, style.letter_spacing, sw)
        glyph = colorize(full, style.stroke_color)
        glyph = Image.alpha_composite(glyph, colorize(fill_mask, color))
        cover = full
    else:
        glyph = colorize(fill_mask, color)
        cover = fill_mask
    bbox = cover.getbbox()
    if bbox is None:
        return None
    glyph = glyph.crop(bbox)
    cover_c = cover.crop(bbox)
    gx, gy = bbox[0] - origin[0], bbox[1] - origin[1]
    shadow = None
    sx = sy = 0
    if style.shadow and style.shadow.color[3] > 0:
        sh, ox, oy = shadow_from_alpha(cover_c, style.shadow)
        shadow, sx, sy = sh, gx + ox, gy + oy
    return glyph, int(gx), int(gy), shadow, int(sx), int(sy)


# ---------------------------------------------------------------------------
# Block rendering
# ---------------------------------------------------------------------------


def _scaled(img: Image.Image, s: float) -> Image.Image:
    w = max(1, int(round(img.width * s)))
    h = max(1, int(round(img.height * s)))
    return img.resize((w, h), Image.Resampling.BICUBIC)


def render_block(
    block: Block,
    states: Optional[dict[int, WordState]] = None,
    char_limit: Optional[int] = None,
    boxes: Optional[list[tuple[int, RGBA, float, float, float]]] = None,
    pad: Optional[int] = None,
) -> tuple[Image.Image, int, int]:
    """Draw the block. Returns (sprite, ox, oy) where (ox, oy) is the position
    of the block's top-left inside the sprite.

    ``states`` maps word unit to a WordState (opacity, scale about the word
    center, offset, color override). ``char_limit`` reveals only the first N
    characters (typewriter). ``boxes`` are (unit, color, radius, pad_x, pad_y)
    rounded boxes drawn behind a word (karaoke)."""
    from .draw import box_sprite  # local import keeps module import light

    p = block.pad if pad is None else pad
    W = int(math.ceil(block.width)) + 2 * p
    H = int(math.ceil(block.height)) + 2 * p
    canvas = Image.new("RGBA", (max(1, W), max(1, H)), (0, 0, 0, 0))
    items = []
    for w in block.words:
        st = (states or {}).get(w.unit, IDENTITY)
        if st.opacity <= 0.003:
            continue
        text = w.text
        if char_limit is not None:
            visible = char_limit - w.char_start
            if visible <= 0:
                continue
            if visible < len(text):
                text = text[:visible]
        style = block.styles[w.run]
        sprites = word_sprites(text, style, st.color)
        if sprites is None:
            continue
        items.append((w, st, text, sprites))

    def place(w: Word, st: WordState, img: Image.Image, ox: int, oy: int):
        if st.scale != 1.0:
            cx = w.x + w.width / 2.0
            cy = w.baseline - block.styles[w.run].size * 0.35
            img2 = _scaled(img, st.scale)
            x = cx + (w.x + ox - cx) * st.scale
            y = cy + (w.baseline + oy - cy) * st.scale
            img = img2
        else:
            x, y = w.x + ox, w.baseline + oy
        x += st.dx + p
        y += st.dy + p
        if st.opacity < 0.999:
            from .draw import scale_alpha

            img = scale_alpha(img, st.opacity)
        xi, yi = int(round(x)), int(round(y))
        _composite_clipped(canvas, img, xi, yi)

    for unit, color, radius, bpx, bpy in boxes or []:
        for w, st, text, sprites in items:
            if w.unit != unit:
                continue
            style = block.styles[w.run]
            font = block.fonts[w.run]
            asc, desc = font.getmetrics()
            bw = int(round((w.width) * st.scale + 2 * bpx))
            bh = int(round(style.size * 1.0 * st.scale + 2 * bpy))
            box, bx, by = box_sprite(bw, bh, radius, color)
            cx = w.x + w.width / 2.0 + p + st.dx
            cy = w.baseline - style.size * 0.36 + p + st.dy
            x = int(round(cx - bw / 2.0)) + bx
            y = int(round(cy - bh / 2.0)) + by
            _composite_clipped(canvas, scale_alpha_safe(box, st.opacity), x, y)

    for w, st, text, (g, gx, gy, sh, sx, sy) in items:
        if sh is not None:
            place(w, st, sh, sx, sy)
    for w, st, text, (g, gx, gy, sh, sx, sy) in items:
        place(w, st, g, gx, gy)
    return canvas, p, p


def scale_alpha_safe(img: Image.Image, o: float) -> Image.Image:
    from .draw import scale_alpha

    return scale_alpha(img, o)


def _composite_clipped(canvas: Image.Image, img: Image.Image, x: int, y: int) -> None:
    """alpha_composite that tolerates sprites partly outside the canvas."""
    if x >= canvas.width or y >= canvas.height or x + img.width <= 0 or y + img.height <= 0:
        return
    sx0 = max(0, -x)
    sy0 = max(0, -y)
    sx1 = min(img.width, canvas.width - x)
    sy1 = min(img.height, canvas.height - y)
    if sx0 or sy0 or sx1 < img.width or sy1 < img.height:
        img = img.crop((sx0, sy0, sx1, sy1))
    canvas.alpha_composite(img, (x + sx0, y + sy0))


def text_width(text: str, style: RunStyle) -> float:
    t = text.upper() if style.uppercase else text
    return _measure(_font_for(style, t), t, style.letter_spacing)


def composite_clipped(canvas: Image.Image, img: Image.Image, x: int, y: int) -> None:
    _composite_clipped(canvas, img, x, y)
