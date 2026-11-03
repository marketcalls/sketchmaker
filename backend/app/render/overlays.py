"""Overlay layer: every overlay kind drawn per frame with Pillow.

Each overlay renderer produces its content as an RGBA sprite (cached while
the content does not change), and a generic animator applies the enter and
exit animations (fade, slides, scale_in, pop, mask_reveal, and word level
word_pop and typewriter for text kinds) as opacity, offset, scale and crop.
The compositor pastes the result onto the RGB base frame. Full-frame kinds
(scrim, vignette, outro tint) are drawn as masked color fills, which is far
cheaper than pasting a full-frame RGBA image.

Numbers follow the story-telling grammar (see layout.py and the research
notes): title card enters over frames 0 to 26 with bezier_out from 40 px
below and fades out over [dur - 55, dur - 20]; the stat card enters over
frames 16 to 34 from the right (landscape) or above (vertical) and fades
over [dur - 30, dur - 8]; the outro headline scales 0.84 to 1 over 24 frames
with a glow pulsing on a 60 frame period and the frame fades out over the
last 22 frames.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

from PIL import Image, ImageDraw

from . import text as tx
from .colors import RGBA, parse_color, readable_on, with_alpha
from .draw import (
    Shadow,
    box_sprite,
    colorize,
    ellipse_mask,
    gradient_mask_vertical,
    paste_sprite,
    rounded_mask,
    scale_alpha,
    scale_mask,
    vignette_mask,
)
from .easing import back_out, clamp, ease, perceptual
from .layout import Layout
from .timeline import Anim, Timeline

WHITE: RGBA = (255, 255, 255, 255)
SUBLINE: RGBA = parse_color("#C9CFDA")
LABEL: RGBA = parse_color("#E7EAF0")
SCRIM_RGB = (4, 6, 10)
STORY_SCRIM = [(0.0, 0.88), (0.32, 0.25), (0.60, 0.05), (1.0, 0.35)]
PALETTE = ["#4CC9F0", "#F72585", "#7BD389", "#B794F6", "#FF9F1C", "#E7EAF0"]


# ---------------------------------------------------------------------------
# Draw operations
# ---------------------------------------------------------------------------


@dataclass
class Op:
    kind: str  # "sprite" | "fill" | "tint"
    sprite: Optional[Image.Image] = None
    x: int = 0
    y: int = 0
    mask: Optional[Image.Image] = None
    color: tuple[int, int, int] = (0, 0, 0)
    alpha: float = 1.0


_MERGED: list = []  # [(m1, m2, merged)], identity keyed, newest last


def _merge_fills(ops: list[Op]) -> list[Op]:
    """Fold consecutive full-frame fills of near-identical dark colors (the
    story scrim plus vignette) into one fill with a screen-combined mask:
    1 - (1 - a)(1 - b) is exactly the alpha of drawing one over the other, and
    a color difference of a few levels is invisible. Saves a full-frame paste
    (about 8 ms at 1080x1920) on every frame."""
    out: list[Op] = []
    for op in ops:
        prev = out[-1] if out else None
        if (
            prev is not None
            and op.kind == "fill"
            and prev.kind == "fill"
            and prev.mask is not None
            and op.mask is not None
            and max(abs(a - b) for a, b in zip(prev.color, op.color)) <= 12
        ):
            merged = None
            for m1, m2, mm in _MERGED:
                if m1 is prev.mask and m2 is op.mask:
                    merged = mm
                    break
            if merged is None:
                from PIL import ImageChops

                merged = ImageChops.screen(prev.mask, op.mask)
                _MERGED.append((prev.mask, op.mask, merged))
                if len(_MERGED) > 4:
                    _MERGED.pop(0)
            out[-1] = Op("fill", mask=merged, color=prev.color)
            continue
        out.append(op)
    return out


def apply_ops(frame: Image.Image, ops: list[Op]) -> Image.Image:
    for op in _merge_fills(ops):
        if op.kind == "sprite" and op.sprite is not None:
            paste_sprite(frame, op.sprite, op.x, op.y)
        elif op.kind == "fill" and op.mask is not None:
            frame.paste(op.color, (0, 0, frame.width, frame.height), op.mask)
        elif op.kind == "tint" and op.alpha > 0.002:
            if op.alpha >= 0.998:
                frame.paste(op.color, (0, 0, frame.width, frame.height))
            else:
                solid = Image.new("RGB", frame.size, op.color)
                frame = Image.blend(frame, solid, op.alpha)
    return frame


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class Content:
    sprite: Image.Image
    ox: int  # box top-left inside the sprite
    oy: int
    bw: int  # box size (excludes shadows and strokes)
    bh: int


def fmt_number(v: float, decimals: int = 0, sep: str = ",", compact: bool = False) -> str:
    if compact:
        a = abs(v)
        for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if a >= div:
                q = v / div
                d = 1 if abs(q) < 100 else 0
                s = f"{q:.{d}f}".rstrip("0").rstrip(".") if d else f"{q:.0f}"
                return s + suf
        return f"{v:.{decimals}f}"
    s = f"{v:,.{decimals}f}"
    if sep != ",":
        s = s.replace(",", "\x00").replace("\x00", sep)
    return s


def anchor_pos(anchor: str, bw: int, bh: int, area: tuple[int, int, int, int]) -> tuple[int, int]:
    l, t, r, b = area
    if anchor in ("top_left", "left", "bottom_left"):
        x = l
    elif anchor in ("top_right", "right", "bottom_right"):
        x = r - bw
    else:
        x = (l + r - bw) // 2
    if anchor in ("top", "top_left", "top_right"):
        y = t
    elif anchor in ("bottom", "bottom_left", "bottom_right"):
        y = b - bh
    else:
        y = (t + b - bh) // 2
    return int(x), int(y)


class _SmallCache:
    def __init__(self, size: int = 3):
        self.size = size
        self.items: list[tuple[Any, Any]] = []

    def get(self, key, factory):
        for k, v in self.items:
            if k == key:
                return v
        v = factory()
        self.items.append((key, v))
        if len(self.items) > self.size:
            self.items.pop(0)
        return v


# ---------------------------------------------------------------------------
# Base renderer with the generic animator
# ---------------------------------------------------------------------------


class Renderer:
    default_anchor = "center"
    supports_text_reveal = False

    def __init__(self, ov, lay: Layout, tl: Timeline):
        self.ov = ov
        self.L = lay
        self.tl = tl
        self.fps = tl.fps
        self.st = ov.style
        self.cache = _SmallCache(3)
        self.enter = ov.enter or self.default_enter()
        self.exit = ov.exit or self.default_exit()
        self.anchor = ov.anchor or self.default_anchor

    # --- defaults -------------------------------------------------------
    def default_enter(self) -> Anim:
        return Anim(type="fade", duration=0.5, easing="bezier_out")

    def default_exit(self) -> Anim:
        return Anim(type="fade", duration=0.4, easing="linear")

    # --- style helpers --------------------------------------------------
    def S(self, v: float) -> float:
        return v * self.L.scale

    @property
    def accent(self) -> RGBA:
        return parse_color(self.st.accent or self.L.accent, parse_color(self.L.accent))

    def color(self, default: RGBA) -> RGBA:
        return parse_color(self.st.color, default) if self.st.color else default

    def size(self, default_baseline: float) -> float:
        return self.S(self.st.size if self.st.size else default_baseline)

    def area(self) -> tuple[int, int, int, int]:
        return self.L.usable(self.ov.safe_area)

    def max_width(self, default_px: float) -> float:
        l, t, r, b = self.area()
        usable = r - l
        mw = self.st.max_width
        if mw is None:
            return min(default_px, usable)
        if mw <= 1.0:
            return max(10.0, usable * mw)
        return min(self.S(mw), usable)

    def shadow(self, default: Optional[Shadow]) -> Optional[Shadow]:
        if self.st.shadow is False:
            return None
        if self.st.shadow is True and default is None:
            return Shadow(0, self.S(8), self.S(30), parse_color(self.st.shadow_color))
        if default is not None and self.st.shadow is True:
            return Shadow(default.dx, default.dy, default.blur, parse_color(self.st.shadow_color, default.color))
        return default

    def stroke(self) -> tuple[float, RGBA]:
        if self.st.stroke:
            return self.S(self.st.stroke), parse_color(self.st.stroke_color, (0, 0, 0, 255))
        return 0.0, (0, 0, 0, 255)

    # --- content --------------------------------------------------------
    def units(self) -> int:
        return 0

    def chars(self) -> int:
        return 0

    def content(self, lt: float, states: Optional[dict] = None, char_limit: Optional[int] = None) -> Optional[Content]:
        raise NotImplementedError

    def content_key(self, lt: float) -> Any:
        """Key for the animated part of the content (None: static)."""
        return None

    def place(self, c: Content) -> tuple[int, int]:
        bx, by = anchor_pos(self.anchor, c.bw, c.bh, self.area())
        return bx + int(round(self.S(self.ov.x))), by + int(round(self.S(self.ov.y)))

    # --- animation ------------------------------------------------------
    def _phase(self, lt: float) -> tuple[float, float, float, float]:
        """(enter raw, enter eased, exit raw, exit eased) progress."""
        D = self.ov.duration
        en, ex = self.enter, self.exit
        if en.type == "none" or en.duration <= 0:
            er = 1.0 if lt >= en.delay else 0.0
        else:
            er = clamp((lt - en.delay) / en.duration)
        if ex.type == "none" or ex.duration <= 0:
            xr = 1.0 if lt >= D - ex.delay - 1e-6 and ex.type != "none" else 0.0
        else:
            xr = clamp((lt - (D - ex.delay - ex.duration)) / ex.duration)
        return er, ease(en.easing, er), xr, ease(ex.easing, xr)

    def _word_states(self, lt: float) -> Optional[dict]:
        en = self.enter
        n = self.units()
        if en.type != "word_pop" or n <= 0:
            return None
        unit_d = min(0.32, max(0.12, en.duration * 0.5))
        if en.stagger is not None:
            stagger = en.stagger
        else:
            stagger = (en.duration - unit_d) / max(1, n - 1) if n > 1 else 0.0
            stagger = max(0.0, stagger)
        states = {}
        size_hint = self.S(40)
        for i in range(n):
            p = clamp((lt - en.delay - i * stagger) / unit_d)
            if p >= 1.0:
                continue
            if p <= 0.0:
                states[i] = tx.WordState(opacity=0.0)
                continue
            states[i] = tx.WordState(
                opacity=min(1.0, p * 2.2),
                scale=0.55 + 0.45 * back_out(p, 2.2),
                dy=(1.0 - ease("bezier_out", p)) * size_hint * 0.5,
            )
        return states

    def _char_limit(self, lt: float) -> Optional[int]:
        en = self.enter
        n = self.chars()
        if en.type != "typewriter" or n <= 0:
            return None
        cps = (1.0 / en.stagger) if en.stagger else n / max(0.05, en.duration)
        k = int(math.floor(max(0.0, lt - en.delay) * cps))
        return None if k >= n else k

    def ops(self, t: float) -> list[Op]:
        ov = self.ov
        lt = t - ov.start
        if lt < 0 or lt >= ov.duration:
            return []
        er, ee, xr, xe = self._phase(lt)
        opacity = ov.opacity
        dx = dy = 0.0
        scale = 1.0
        reveal_frac = 1.0
        en, ex = self.enter, self.exit
        states = None
        char_limit = None
        text_reveal = self.supports_text_reveal and en.type in ("word_pop", "typewriter")
        # Enter
        if en.type in ("fade",) or (en.type in ("word_pop", "typewriter") and not text_reveal):
            opacity *= ee
        elif en.type.startswith("slide_"):
            dist = self.S(en.distance if en.distance is not None else 40)
            opacity *= ee
            off = (1.0 - ee) * dist
            if en.type == "slide_up":
                dy += off
            elif en.type == "slide_down":
                dy -= off
            elif en.type == "slide_left":
                dx += off
            else:
                dx -= off
        elif en.type == "scale_in":
            opacity *= ee
            scale *= perceptual(0.84, 1.0, ee)
        elif en.type == "pop":
            opacity *= clamp(er * 3.0)
            scale *= 0.5 + 0.5 * back_out(er, 2.0)
        elif en.type == "mask_reveal":
            reveal_frac = ee
        elif text_reveal:
            if en.type == "word_pop":
                states = self._word_states(lt)
            else:
                char_limit = self._char_limit(lt)
        # Exit
        if xr > 0:
            if ex.type.startswith("slide_"):
                dist = self.S(ex.distance if ex.distance is not None else 40)
                off = xe * dist
                if ex.type == "slide_up":
                    dy -= off
                elif ex.type == "slide_down":
                    dy += off
                elif ex.type == "slide_left":
                    dx -= off
                else:
                    dx += off
                opacity *= 1.0 - xe
            elif ex.type == "scale_in":
                scale *= perceptual(1.0, 0.84, xe)
                opacity *= 1.0 - xe
            elif ex.type == "pop":
                scale *= 1.0 - 0.5 * xe
                opacity *= 1.0 - xe
            elif ex.type == "mask_reveal":
                reveal_frac = min(reveal_frac, 1.0 - xe)
            elif ex.type != "none":
                opacity *= 1.0 - xe
        if opacity <= 0.003 or reveal_frac <= 0.002:
            return []
        dyn = self.content_key(lt)
        skey = None
        if states is not None:
            skey = tuple(sorted((k, round(v.opacity, 3), round(v.scale, 3), round(v.dy, 1)) for k, v in states.items()))
        key = (dyn, skey, char_limit)
        c = self.cache.get(key, lambda: self.content(lt, states, char_limit))
        if c is None:
            return []
        bx, by = self.place(c)
        return self._emit(c, bx, by, opacity, dx, dy, scale, reveal_frac)

    def _emit(self, c: Content, bx: int, by: int, opacity: float, dx: float, dy: float, scale: float, reveal: float) -> list[Op]:
        sprite = c.sprite
        sx = bx - c.ox
        sy = by - c.oy
        if reveal < 0.999:
            cut = c.ox + int(round(c.bw * reveal))
            cut = max(1, min(sprite.width, cut))
            sprite = sprite.crop((0, 0, cut, sprite.height))
        if abs(scale - 1.0) > 0.001:
            cx = bx + c.bw / 2.0
            cy = by + c.bh / 2.0
            nw = max(1, int(round(sprite.width * scale)))
            nh = max(1, int(round(sprite.height * scale)))
            sprite = sprite.resize((nw, nh), Image.Resampling.BICUBIC)
            sx = cx + (sx - cx) * scale
            sy = cy + (sy - cy) * scale
        sprite = scale_alpha(sprite, opacity)
        return [Op("sprite", sprite, int(round(sx + dx)), int(round(sy + dy)))]


def _content_from_block(block: tx.Block, states=None, char_limit=None) -> Content:
    img, ox, oy = tx.render_block(block, states, char_limit)
    return Content(img, ox, oy, int(math.ceil(block.width)), int(math.ceil(block.height)))


# ---------------------------------------------------------------------------
# Text kinds
# ---------------------------------------------------------------------------


class TextBlockRenderer(Renderer):
    """Kinds whose content is a single text block (plus an optional box)."""

    supports_text_reveal = True
    align = "left"

    def __init__(self, ov, lay, tl):
        super().__init__(ov, lay, tl)
        self._block: Optional[tx.Block] = None

    def runs(self) -> list[tx.Run]:
        raise NotImplementedError

    def block_width(self) -> float:
        l, t, r, b = self.area()
        return self.max_width(r - l)

    def block(self) -> tx.Block:
        if self._block is None:
            self._block = tx.layout_block(self.runs(), self.block_width(), self.st.align or self.align)
        return self._block

    def units(self) -> int:
        return len(self.block().words)

    def chars(self) -> int:
        return self.block().char_count

    def content(self, lt, states=None, char_limit=None):
        return _content_from_block(self.block(), states, char_limit)


class TitleCardRenderer(TextBlockRenderer):
    default_anchor = "left"

    def default_enter(self):
        return Anim(type="slide_up", duration=26 / 30, easing="bezier_out", distance=40)

    def default_exit(self):
        # Fade over [dur - 55, dur - 20] frames.
        return Anim(type="fade", duration=35 / 30, delay=20 / 30, easing="linear")

    def runs(self):
        L, ov = self.L, self.ov
        out = []
        sub_shadow = Shadow(0, self.S(4), self.S(18), (0, 0, 0, 150))
        if ov.eyebrow:
            out.append(
                tx.Run(
                    ov.eyebrow,
                    tx.RunStyle(L.text_font, 700, L.eyebrow_size, self.accent, 1.2, self.S(10),
                                uppercase=bool(self.st.uppercase), shadow=sub_shadow, max_lines=2),
                )
            )
        stroke, stroke_c = self.stroke()
        out.append(
            tx.Run(
                ov.title,
                tx.RunStyle(
                    self.st.font or L.display_font,
                    self.st.weight or 800,
                    self.size(84),
                    self.color(WHITE),
                    self.st.line_height or 0.96,
                    self.S(self.st.letter_spacing) if self.st.letter_spacing is not None else -self.S(5),
                    stroke=stroke,
                    stroke_color=stroke_c,
                    shadow=self.shadow(Shadow(0, self.S(10), self.S(40), (0, 0, 0, 191))),
                    max_lines=self.st.max_lines or 4,
                ),
                gap_before=self.S(18),
            )
        )
        if ov.subtitle:
            out.append(
                tx.Run(
                    ov.subtitle,
                    tx.RunStyle(L.text_font, 500, L.subline_size, SUBLINE, 1.15, shadow=sub_shadow, max_lines=3),
                    gap_before=self.S(22),
                )
            )
        return out

    def block_width(self):
        L = self.L
        full = L.width - 2 * L.safe_x
        w = full * 0.58 if L.orientation == "landscape" else full
        return self.max_width(w) if self.st.max_width else w

    def _region(self) -> tuple[int, int]:
        """Vertical band the title is centered in (story formula: clear of
        the caption area, lowered under a top-centre stat card)."""
        L = self.L
        top = L.safe_y
        if L.orientation == "vertical":
            top = max(top, L.zone_top)
        if self.ov.narrow and L.orientation == "vertical":
            top = L.safe_y + L.ipx(220)
        if L.has_captions:
            bottom = L.height - L.title_pad_bottom
        else:
            bottom = L.usable(True)[3]
        return top, max(top + L.ipx(120), bottom)

    def block(self):
        if self._block is None:
            top, bottom = self._region()
            self._block = tx.layout_block(self.runs(), self.block_width(), self.st.align or self.align,
                                          max_height=None if self.ov.anchor else bottom - top)
        return self._block

    def place(self, c):
        if self.ov.anchor:
            return super().place(c)
        L = self.L
        top, bottom = self._region()
        y = top + max(0, (bottom - top - c.bh) // 2)
        return L.safe_x + int(round(self.S(self.ov.x))), y + int(round(self.S(self.ov.y)))


class TextRenderer(TextBlockRenderer):
    default_anchor = "center"
    align = "center"

    def runs(self):
        stroke, stroke_c = self.stroke()
        return [
            tx.Run(
                self.ov.text,
                tx.RunStyle(
                    self.st.font or self.L.display_font,
                    self.st.weight or 800,
                    self.size(96),
                    self.color(WHITE),
                    self.st.line_height or 1.04,
                    self.S(self.st.letter_spacing) if self.st.letter_spacing is not None else -self.S(2),
                    uppercase=bool(self.st.uppercase),
                    stroke=stroke,
                    stroke_color=stroke_c,
                    shadow=self.shadow(Shadow(0, self.S(8), self.S(30), (0, 0, 0, 150))),
                    max_lines=self.st.max_lines or 5,
                ),
            )
        ]

    def content(self, lt, states=None, char_limit=None):
        c = super().content(lt, states, char_limit)
        if not self.st.background:
            return c
        size = self.block().styles[0].size
        px_, py_ = size * 0.55, size * 0.32
        bw, bh = int(c.bw + 2 * px_), int(c.bh + 2 * py_)
        box, bx, by = box_sprite(bw, bh, size * 0.3, parse_color(self.st.background))
        pad = max(c.ox, c.oy, -bx, -by) + 2
        W, H = bw + 2 * pad, bh + 2 * pad
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        canvas.alpha_composite(box, (pad + bx, pad + by))
        tx.composite_clipped(canvas, c.sprite, int(pad + px_ - c.ox), int(pad + py_ - c.oy))
        return Content(canvas, pad, pad, bw, bh)


class QuoteRenderer(TextBlockRenderer):
    default_anchor = "center"
    align = "left"

    def default_enter(self):
        return Anim(type="slide_up", duration=0.8, easing="bezier_out", distance=30)

    def _all_runs(self):
        L = self.L
        out = [
            tx.Run(
                self.ov.text,
                tx.RunStyle(
                    self.st.font or "Playfair Display",
                    self.st.weight or 700,
                    self.size(62),
                    self.color(WHITE),
                    self.st.line_height or 1.2,
                    0.0,
                    shadow=self.shadow(Shadow(0, self.S(6), self.S(24), (0, 0, 0, 150))),
                    max_lines=self.st.max_lines or 8,
                ),
            )
        ]
        if self.ov.author:
            out.append(
                tx.Run(
                    self.ov.author,
                    tx.RunStyle(L.text_font, 600, self.S(30), self.accent, 1.2, self.S(3), uppercase=True, max_lines=2),
                    gap_before=self.S(40),
                )
            )
        return out

    def block_width(self):
        l, t, r, b = self.area()
        return self.max_width((r - l) * 0.9)

    def runs(self):
        # Only the quote text is a reveal unit; the author is drawn separately.
        return [r for r in self._all_runs()[:1]]

    def _author_block(self) -> Optional[tx.Block]:
        if not self.ov.author:
            return None
        if not hasattr(self, "_ab"):
            l, t, r, b = self.area()
            self._ab = tx.layout_block(self._all_runs()[1:], self.block_width() - self.S(70), "left")
        return self._ab

    def content(self, lt, states=None, char_limit=None):
        blk = self.block()
        c = _content_from_block(blk, states, char_limit)
        qsize = self.S(190) * blk.fit
        qstyle = tx.RunStyle("Playfair Display", 900, qsize, with_alpha(self.accent, 0.95))
        q = tx.word_sprites("\u201C", qstyle)
        band = int(qsize * 0.45)
        ab = self._author_block()
        gap = int(self.S(40))
        ah = int(ab.height) + gap if ab else 0
        pad = max(c.ox, c.oy)
        W = c.sprite.width
        H = pad * 2 + band + c.bh + ah
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if q:
            g, gx, gy, _, _, _ = q
            # The mark's top sits at the top of the band, left aligned with the text.
            tx.composite_clipped(canvas, g, pad - int(qsize * 0.03), pad - int(qsize * 0.12))
        tx.composite_clipped(canvas, c.sprite, pad - c.ox, pad + band - c.oy)
        if ab is not None:
            done = (states is None or len(states) == 0) and char_limit is None
            if done:
                bar_w, bar_h = int(self.S(46)), max(2, int(self.S(4)))
                ay = pad + band + c.bh + gap
                rule = colorize(rounded_mask(bar_w, bar_h, bar_h / 2), self.accent)
                line_mid = ab.lines[0].top + ab.lines[0].height / 2 if ab.lines else 0
                tx.composite_clipped(canvas, rule, pad, int(ay + line_mid - bar_h / 2))
                aimg, aox, aoy = tx.render_block(ab)
                tx.composite_clipped(canvas, aimg, pad + bar_w + int(self.S(18)) - aox, ay - aoy)
        return Content(canvas, pad, pad, c.bw, band + c.bh + ah)


class LowerThirdRenderer(TextBlockRenderer):
    default_anchor = "bottom_left"

    def default_enter(self):
        return Anim(type="slide_right", duration=0.6, easing="bezier_out", distance=60)

    def runs(self):
        L = self.L
        out = [
            tx.Run(
                self.ov.title,
                tx.RunStyle(self.st.font or L.text_font, self.st.weight or 700, self.size(40), self.color(WHITE), 1.15,
                            max_lines=2),
            )
        ]
        if self.ov.subtitle:
            out.append(tx.Run(self.ov.subtitle, tx.RunStyle(L.text_font, 500, self.S(28), SUBLINE, 1.2, max_lines=2),
                              gap_before=self.S(6)))
        return out

    def block_width(self):
        l, t, r, b = self.area()
        return self.max_width((r - l) * 0.8)

    def content(self, lt, states=None, char_limit=None):
        c = super().content(lt, states, char_limit)
        padx, pady = self.S(30), self.S(20)
        bar = max(4, int(self.S(8)))
        bw = int(c.bw + 2 * padx + bar)
        bh = int(c.bh + 2 * pady)
        box, bx, by = box_sprite(bw, bh, self.S(14), (10, 12, 18, 220), shadow=Shadow(0, self.S(14), self.S(40), (0, 0, 0, 120)))
        pad = max(-bx, -by, c.ox, c.oy) + 2
        W, H = bw + 2 * pad - min(0, 0), bh + 2 * pad
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        canvas.alpha_composite(box, (pad + bx, pad + by))
        # Accent bar clipped to the box's rounded left edge.
        barmask = Image.new("L", (bw, bh), 0)
        barmask.paste(255, (0, 0, bar, bh))
        from PIL import ImageChops

        barmask = ImageChops.multiply(barmask, rounded_mask(bw, bh, self.S(14)))
        canvas.alpha_composite(colorize(barmask, self.accent), (pad, pad))
        tx.composite_clipped(canvas, c.sprite, int(pad + bar + padx - c.ox), int(pad + pady - c.oy))
        return Content(canvas, pad, pad, bw, bh)

    def place(self, c):
        if self.ov.anchor and self.ov.anchor != "bottom_left":
            return super().place(c)
        L = self.L
        l, t, r, b = self.area()
        bottom = b
        if L.has_captions:
            bottom = min(bottom, L.caption_top_estimate - L.ipx(30))
        return l + int(round(self.S(self.ov.x))), bottom - c.bh + int(round(self.S(self.ov.y)))


class StatCardRenderer(Renderer):
    default_anchor = "top"
    supports_text_reveal = False

    def default_enter(self):
        if self.L.orientation == "vertical":
            return Anim(type="slide_down", duration=18 / 30, delay=16 / 30, easing="bezier_out", distance=40)
        return Anim(type="slide_left", duration=18 / 30, delay=16 / 30, easing="bezier_out", distance=60)

    def default_exit(self):
        # Fade over [dur - 30, dur - 8] frames.
        return Anim(type="fade", duration=22 / 30, delay=8 / 30, easing="linear")

    def __init__(self, ov, lay, tl):
        super().__init__(ov, lay, tl)
        if ov.anchor is None:
            self.anchor = "top" if lay.orientation == "vertical" else "top_right"
        self._c: Optional[Content] = None

    def content(self, lt, states=None, char_limit=None):
        if self._c is not None:
            return self._c
        L = self.L
        vertical = L.orientation == "vertical"
        comfortable = 9 if vertical else 12
        base = self.size(72)
        n = len(self.ov.value)
        vsize = base if n <= comfortable else base * (comfortable / n) ** 0.55
        runs = [
            tx.Run(self.ov.value, tx.RunStyle(self.st.font or L.display_font, self.st.weight or 800, vsize,
                                              parse_color(self.st.color, self.accent) if self.st.color else self.accent,
                                              1.0, -self.S(3), max_lines=1))
        ]
        if self.ov.label:
            runs.append(tx.Run(self.ov.label, tx.RunStyle(L.text_font, 600, L.stat_label_size, LABEL, 1.2, self.S(3),
                                                           max_lines=2), gap_before=self.S(10)))
        l, t, r, b = self.area()
        padx, pady = self.S(34), self.S(22)
        maxw = self.max_width((r - l) * (0.92 if vertical else 0.5)) - 2 * padx
        blk = tx.layout_block(runs, maxw, self.st.align or ("center" if vertical else "right"))
        img, ox, oy = tx.render_block(blk)
        bw = int(math.ceil(blk.width + 2 * padx))
        bh = int(math.ceil(blk.height + 2 * pady))
        border = max(2.0, round(2 * L.scale))
        box, bx, by = box_sprite(bw, bh, self.S(20), (10, 12, 18, 209), self.accent, border,
                                 Shadow(0, self.S(24), self.S(60), (0, 0, 0, 140)))
        pad = max(-bx, -by, ox, oy) + 2
        W = bw + 2 * pad
        H = bh + 2 * pad + max(0, by + box.height - bh - pad)
        canvas = Image.new("RGBA", (W, max(H, box.height + pad + by)), (0, 0, 0, 0))
        canvas.alpha_composite(box, (pad + bx, pad + by))
        tx.composite_clipped(canvas, img, int(pad + padx - ox), int(pad + pady - oy))
        self._c = Content(canvas, pad, pad, bw, bh)
        return self._c


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class ListRenderer(Renderer):
    default_anchor = "center"

    def __init__(self, ov, lay, tl):
        super().__init__(ov, lay, tl)
        self._rows = None

    def default_enter(self):
        return Anim(type="fade", duration=0.4, easing="bezier_out")

    def _build(self):
        if self._rows is not None:
            return self._rows
        L = self.L
        l, t, r, b = self.area()
        width = self.max_width((r - l) * 0.94)
        isz = self.size(44)
        title = None
        if self.ov.title:
            tb = tx.layout_block(
                [tx.Run(self.ov.title, tx.RunStyle(L.display_font, 800, self.S(64), WHITE, 1.02, -self.S(1.5),
                                                   shadow=Shadow(0, self.S(6), self.S(24), (0, 0, 0, 140)), max_lines=3))],
                width,
                "left",
            )
            title = tx.render_block(tb) + (tb,)
        d = int(round(isz * 1.3))
        gap = int(round(self.S(26)))
        rows = []
        for i, item in enumerate(self.ov.items):
            tb = tx.layout_block(
                [tx.Run(item, tx.RunStyle(self.st.font or L.text_font, self.st.weight or 600, isz, self.color(WHITE), 1.2,
                                          shadow=Shadow(0, self.S(4), self.S(16), (0, 0, 0, 130)), max_lines=3))],
                width - d - gap,
                "left",
            )
            img, ox, oy = tx.render_block(tb)
            badge = colorize(ellipse_mask(d, d), self.accent)
            if self.ov.numbered:
                num = tx.word_sprites(str(i + 1), tx.RunStyle(L.display_font, 800, d * 0.5, readable_on(self.accent)))
                if num:
                    g, gx, gy, _, _, _ = num
                    badge.alpha_composite(g, ((d - g.width) // 2, (d - g.height) // 2))
            else:
                badge = colorize(ellipse_mask(int(d * 0.36), int(d * 0.36)), self.accent)
            first_line_h = tb.lines[0].height if tb.lines else d
            rh = int(max(d, tb.height))
            row = Image.new("RGBA", (int(width) + 2 * ox, rh + 2 * oy), (0, 0, 0, 0))
            by_ = oy + int(max(0, (first_line_h - badge.height) / 2)) if tb.height > d else oy + (rh - badge.height) // 2
            row.alpha_composite(badge, (ox + (d - badge.width) // 2, by_))
            ty = oy + (0 if tb.height >= d else (rh - int(tb.height)) // 2)
            tx.composite_clipped(row, img, ox + d + gap - ox, ty - oy)
            rows.append((row, ox, oy, rh))
        self._rows = (title, rows, width, gap)
        return self._rows

    def content_key(self, lt):
        n = len(self.ov.items)
        return tuple(round(self._row_p(lt, i), 3) for i in range(n))

    def _row_p(self, lt: float, i: int) -> float:
        title_delay = 0.25 if self.ov.title else 0.0
        t0 = self.enter.delay + title_delay + i * self.ov.item_stagger
        return ease("bezier_out", clamp((lt - t0) / 0.45))

    def content(self, lt, states=None, char_limit=None):
        title, rows, width, gap = self._build()
        row_gap = int(self.S(26))
        heights = []
        H = 0
        if title:
            timg, tox, toy, tb = title
            H += int(tb.height) + int(self.S(34))
        for row, ox, oy, rh in rows:
            heights.append(H)
            H += rh + row_gap
        H = max(1, H - row_gap)
        pad = max([title[1] if title else 0] + [r[1] for r in rows] + [int(self.S(60))])
        canvas = Image.new("RGBA", (int(width) + 2 * pad, H + 2 * pad), (0, 0, 0, 0))
        if title:
            timg, tox, toy, tb = title
            tx.composite_clipped(canvas, timg, pad - tox, pad - toy)
        for i, (row, ox, oy, rh) in enumerate(rows):
            p = self._row_p(lt, i)
            if p <= 0.002:
                continue
            img = scale_alpha(row, p)
            x = pad - ox - int(round((1 - p) * self.S(40)))
            tx.composite_clipped(canvas, img, x, pad + heights[i] - oy)
        return Content(canvas, pad, pad, int(width), H)


# ---------------------------------------------------------------------------
# Counter
# ---------------------------------------------------------------------------


class CounterRenderer(Renderer):
    default_anchor = "center"

    def __init__(self, ov, lay, tl):
        super().__init__(ov, lay, tl)
        self._prep = None

    def default_enter(self):
        return Anim(type="scale_in", duration=0.5, easing="bezier_out")

    def _count_d(self) -> float:
        if self.ov.count_duration is not None:
            return max(0.01, self.ov.count_duration)
        return max(0.3, min(2.5, self.ov.duration * 0.6))

    def value_at(self, lt: float) -> float:
        p = ease(self.ov.count_easing, clamp((lt - self.enter.delay) / self._count_d()))
        return self.ov.from_value + (self.ov.to_value - self.ov.from_value) * p

    def text_at(self, lt: float) -> str:
        ov = self.ov
        return ov.prefix + fmt_number(self.value_at(lt), ov.decimals, ov.separator, ov.compact) + ov.suffix

    def content_key(self, lt):
        return self.text_at(lt)

    def _style(self):
        if self._prep is not None:
            return self._prep
        ov = self.ov
        l, t, r, b = self.area()
        maxw = self.max_width((r - l))
        size = self.size(170 if self.L.orientation != "landscape" else 120)
        widest = max(
            (ov.prefix + fmt_number(v, ov.decimals, ov.separator, ov.compact) + ov.suffix for v in (ov.from_value, ov.to_value)),
            key=len,
        )
        while True:
            st = tx.RunStyle(self.st.font or self.L.display_font, self.st.weight or 800, size, self.color(WHITE), 1.0,
                             -self.S(2), shadow=self.shadow(Shadow(0, self.S(10), self.S(36), (0, 0, 0, 150))))
            cell = max(tx.text_width(d, st) for d in "0123456789")
            if self._measure(widest, st, cell) <= maxw or size < 12:
                break
            size *= 0.92
        label_block = None
        if ov.label:
            label_block = tx.layout_block(
                [tx.Run(ov.label, tx.RunStyle(self.L.text_font, 600, self.S(36), SUBLINE, 1.2, self.S(5) * 0.5, uppercase=True,
                                              max_lines=2))],
                maxw,
                "center",
            )
        self._prep = (st, cell, label_block, self._measure(widest, st, cell))
        return self._prep

    def _measure(self, s: str, st, cell: float) -> float:
        w = 0.0
        for ch in s:
            w += cell if ch.isdigit() else tx.text_width(ch, st) + st.letter_spacing
        return w

    def content(self, lt, states=None, char_limit=None):
        st, cell, label_block, maxw_val = self._style()
        s = self.text_at(lt)
        width = self._measure(s, st, cell)
        font_px = st.size
        bw = int(math.ceil(max(maxw_val, label_block.width if label_block else 0)))
        rule_h = max(3, int(self.S(6)))
        gap1 = int(self.S(26))
        gap2 = int(self.S(22))
        val_h = int(font_px * 1.0)
        bh = val_h + ((gap1 + rule_h + gap2 + int(label_block.height)) if label_block else 0)
        pad = int(font_px * 0.6)
        canvas = Image.new("RGBA", (bw + 2 * pad, bh + 2 * pad), (0, 0, 0, 0))
        x = pad + (bw - width) / 2.0
        # Baseline so the digits' cap height sits inside the value band.
        font = tx._font_for(st, "0")
        asc, desc = font.getmetrics()
        baseline = pad + (val_h - (asc + desc)) / 2.0 + asc
        sprites = []
        for ch in s:
            adv = cell if ch.isdigit() else tx.text_width(ch, st) + st.letter_spacing
            spr = tx.word_sprites(ch, st)
            if spr is not None:
                cw = tx.text_width(ch, st)
                sprites.append((spr, x + (adv - cw) / 2.0 if ch.isdigit() else x))
            x += adv
        for (g, gx, gy, sh, sx, sy), cx in sprites:
            if sh is not None:
                tx.composite_clipped(canvas, sh, int(round(cx + sx)), int(round(baseline + sy)))
        for (g, gx, gy, sh, sx, sy), cx in sprites:
            tx.composite_clipped(canvas, g, int(round(cx + gx)), int(round(baseline + gy)))
        if label_block:
            ry = pad + val_h + gap1
            rule_w = int(self.S(90))
            canvas.alpha_composite(colorize(rounded_mask(rule_w, rule_h, rule_h / 2), self.accent),
                                   (pad + (bw - rule_w) // 2, ry))
            limg, lox, loy = tx.render_block(label_block)
            tx.composite_clipped(canvas, limg, int(pad + (bw - label_block.width) / 2 - lox), ry + rule_h + gap2 - loy)
        return Content(canvas, pad, pad, bw, bh)


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------


class ChartRenderer(Renderer):
    default_anchor = "center"

    def default_enter(self):
        return Anim(type="fade", duration=0.4, easing="bezier_out")

    def __init__(self, ov, lay, tl):
        super().__init__(ov, lay, tl)
        self._label_cache: dict = {}

    def colors(self) -> list[RGBA]:
        if self.ov.colors:
            return [parse_color(c, self.accent) for c in self.ov.colors]
        if self.ov.chart_type == "bar":
            return [self.accent]
        return [self.accent] + [parse_color(c) for c in PALETTE]

    def build_p(self, lt: float) -> float:
        return clamp((lt - self.enter.delay - 0.1) / max(0.01, self.ov.build_duration))

    def content_key(self, lt):
        p = self.build_p(lt)
        return round(p, 4) if p < 1.0 else 1.0

    def dims(self) -> tuple[int, int]:
        l, t, r, b = self.area()
        uw, uh = r - l, b - t
        land = self.L.orientation == "landscape"
        if self.ov.width is not None:
            w = uw * self.ov.width if self.ov.width <= 1 else min(uw, self.S(self.ov.width))
        else:
            w = uw * (0.78 if land else 0.96)
        if self.ov.height is not None:
            h = min(uh, self.S(self.ov.height))
        else:
            h = w * (0.5 if land else 0.82)
        return int(w), int(min(h, uh * 0.8))

    def fmt(self, v: float) -> str:
        ov = self.ov
        return ov.value_prefix + fmt_number(v, ov.decimals) + ov.value_suffix

    def _text(self, s: str, size: float, color: RGBA, weight: int = 600, family: Optional[str] = None):
        st = tx.RunStyle(family or self.L.text_font, weight, size, color)
        return tx.word_sprites(s, st), tx.text_width(s, st)

    def _put_text(self, canvas, s, size, color, cx, baseline, weight=600, family=None, align="center"):
        spr, w = self._text(s, size, color, weight, family)
        if spr is None:
            return
        g, gx, gy, _, _, _ = spr
        x = cx - w / 2 if align == "center" else (cx if align == "left" else cx - w)
        tx.composite_clipped(canvas, g, int(round(x + gx)), int(round(baseline + gy)))

    def _label_block(self, s: str, width: float, size: float):
        key = (s, int(width), int(size))
        if key not in self._label_cache:
            blk = tx.layout_block([tx.Run(s, tx.RunStyle(self.L.text_font, 600, size, SUBLINE, 1.1, max_lines=2))],
                                  width, "center", min_fit=0.5)
            self._label_cache[key] = (tx.render_block(blk), blk)
        return self._label_cache[key]

    def content(self, lt, states=None, char_limit=None):
        w, h = self.dims()
        p = self.build_p(lt)
        title_h = 0
        title_img = None
        if self.ov.title:
            tb = tx.layout_block(
                [tx.Run(self.ov.title, tx.RunStyle(self.L.display_font, 800, self.S(52), WHITE, 1.05, -self.S(1),
                                                   shadow=Shadow(0, self.S(6), self.S(24), (0, 0, 0, 140)), max_lines=2))],
                w,
                "left",
            )
            title_img = tx.render_block(tb)
            title_h = int(tb.height + self.S(36))
        pad = int(self.S(40))
        canvas = Image.new("RGBA", (w + 2 * pad, h + title_h + 2 * pad), (0, 0, 0, 0))
        if title_img:
            img, ox, oy = title_img
            tx.composite_clipped(canvas, img, pad - ox, pad - oy)
        area = (pad, pad + title_h, pad + w, pad + title_h + h)
        kind = self.ov.chart_type
        if kind == "bar":
            self._bar(canvas, area, lt, p)
        elif kind == "line":
            self._line(canvas, area, p)
        else:
            self._pie(canvas, area, p)
        return Content(canvas, pad, pad, w, h + title_h)

    # Bar ----------------------------------------------------------------
    def _bar(self, canvas, area, lt, p):
        x0, y0, x1, y1 = area
        vals = [max(0.0, v) for v in self.ov.values]
        n = max(1, len(vals))
        vmax = max(vals) if vals and max(vals) > 0 else 1.0
        lab_size = self.S(26 if n > 6 else 30)
        label_band = int(lab_size * 2.6) if self.ov.labels else int(self.S(10))
        value_band = int(self.S(56)) if self.ov.show_values else int(self.S(10))
        base_y = y1 - label_band
        top_y = y0 + value_band
        slot = (x1 - x0) / n
        bw = max(4, int(slot * 0.62))
        cols = self.colors()
        bd = self.ov.build_duration
        stagger = min(0.09, bd * 0.4 / max(1, n - 1)) if n > 1 else 0.0
        bar_d = max(0.2, bd - stagger * (n - 1))
        # Baseline
        line_h = max(2, int(self.S(3)))
        canvas.alpha_composite(colorize(Image.new("L", (x1 - x0, line_h), 255), (255, 255, 255, 90)), (x0, base_y))
        radius = min(self.S(12), bw / 3)
        for i, v in enumerate(vals):
            pi = ease("bezier_out", clamp((lt - self.enter.delay - 0.1 - i * stagger) / bar_d))
            full_h = (base_y - top_y) * (v / vmax)
            bh = int(round(full_h * pi))
            cx = x0 + slot * (i + 0.5)
            bx = int(round(cx - bw / 2))
            col = cols[i % len(cols)]
            if bh >= 1:
                rr = min(radius, bh)
                m = rounded_mask(bw, bh + int(rr) + 1, rr)
                m = m.crop((0, 0, bw, bh))
                canvas.alpha_composite(colorize(m, col), (bx, base_y - bh))
            if self.ov.show_values and pi > 0.02:
                vs = self.fmt(v * pi if p < 1.0 else v)
                vsize = min(self.S(34), slot * 0.9 / max(1, len(vs)) * 1.7)
                spr = self._put_text  # alias for readability
                spr(canvas, vs, vsize, with_alpha(WHITE, min(1.0, pi * 1.5)), cx, base_y - bh - self.S(14), 800,
                    self.L.display_font)
            if self.ov.labels and i < len(self.ov.labels):
                (limg, lox, loy), blk = self._label_block(self.ov.labels[i], slot * 0.94, lab_size)
                tx.composite_clipped(canvas, limg, int(round(cx - blk.width / 2 - lox)), int(base_y + self.S(14) - loy))

    # Line ---------------------------------------------------------------
    def _line(self, canvas, area, p):
        x0, y0, x1, y1 = area
        vals = list(self.ov.values)
        n = len(vals)
        if n == 0:
            return
        lab_size = self.S(26)
        label_band = int(lab_size * 2.4) if self.ov.labels else int(self.S(10))
        value_band = int(self.S(56)) if self.ov.show_values else int(self.S(16))
        base_y = y1 - label_band
        top_y = y0 + value_band
        vmin = min(0.0, min(vals))
        vmax = max(vals) if max(vals) > vmin else vmin + 1
        inset = self.S(30)
        xs = [x0 + inset + (x1 - x0 - 2 * inset) * (i / max(1, n - 1)) for i in range(n)]
        ys = [base_y - (base_y - top_y) * ((v - vmin) / (vmax - vmin)) for v in vals]
        col = self.colors()[0]
        line_h = max(2, int(self.S(3)))
        canvas.alpha_composite(colorize(Image.new("L", (x1 - x0, line_h), 255), (255, 255, 255, 90)), (x0, base_y))
        pe = ease("ease_in_out", p)
        # Path up to fraction pe of the x extent.
        xr = xs[0] + (xs[-1] - xs[0]) * pe if n > 1 else xs[0]
        pts = []
        for i in range(n):
            if xs[i] <= xr + 1e-6:
                pts.append((xs[i], ys[i]))
            else:
                if i > 0:
                    f = (xr - xs[i - 1]) / max(1e-6, xs[i] - xs[i - 1])
                    pts.append((xr, ys[i - 1] + (ys[i] - ys[i - 1]) * f))
                break
        ss = 2
        Wc, Hc = canvas.size
        if len(pts) >= 2:
            area_mask = Image.new("L", (Wc * ss, Hc * ss), 0)
            poly = [(x * ss, y * ss) for x, y in pts] + [(pts[-1][0] * ss, base_y * ss), (pts[0][0] * ss, base_y * ss)]
            ImageDraw.Draw(area_mask).polygon(poly, fill=255)
            area_mask = area_mask.resize((Wc, Hc), Image.Resampling.BOX)
            fade = gradient_mask_vertical((Wc, Hc), [(0.0, 0.0), (1.0 - (top_y / Hc), 0.30), (1.0, 0.30)])
            from PIL import ImageChops

            canvas.alpha_composite(colorize(ImageChops.multiply(area_mask, fade), col))
            lm = Image.new("L", (Wc * ss, Hc * ss), 0)
            ImageDraw.Draw(lm).line([(x * ss, y * ss) for x, y in pts], fill=255, width=int(self.S(7) * ss), joint="curve")
            r = self.S(3.5) * ss
            for x, y in (pts[0], pts[-1]):
                ImageDraw.Draw(lm).ellipse((x * ss - r, y * ss - r, x * ss + r, y * ss + r), fill=255)
            canvas.alpha_composite(colorize(lm.resize((Wc, Hc), Image.Resampling.BOX), col))
        dot = int(self.S(22))
        dot_img = colorize(ellipse_mask(dot, dot), col)
        inner = int(dot * 0.5)
        dot_img.alpha_composite(colorize(ellipse_mask(inner, inner), (10, 12, 18, 255)), ((dot - inner) // 2, (dot - inner) // 2))
        for i in range(n):
            if xs[i] <= xr + 1e-6:
                canvas.alpha_composite(dot_img, (int(round(xs[i] - dot / 2)), int(round(ys[i] - dot / 2))))
                if self.ov.show_values:
                    self._put_text(canvas, self.fmt(vals[i]), self.S(28), WHITE, xs[i], ys[i] - self.S(22), 800,
                                   self.L.display_font)
        if self.ov.labels:
            slot = (x1 - x0 - 2 * inset) / max(1, n - 1) if n > 1 else (x1 - x0)
            for i in range(min(n, len(self.ov.labels))):
                (limg, lox, loy), blk = self._label_block(self.ov.labels[i], min(slot * 0.96, (x1 - x0) / 2), lab_size)
                tx.composite_clipped(canvas, limg, int(round(xs[i] - blk.width / 2 - lox)), int(base_y + self.S(14) - loy))

    # Pie ----------------------------------------------------------------
    def _pie(self, canvas, area, p):
        x0, y0, x1, y1 = area
        vals = [max(0.0, v) for v in self.ov.values]
        total = sum(vals) or 1.0
        land = (x1 - x0) > (y1 - y0) * 1.25
        if land:
            d = int(min(y1 - y0, (x1 - x0) * 0.5))
            cx, cy = x0 + d / 2, y0 + (y1 - y0) / 2
        else:
            d = int(min((x1 - x0) * 0.72, (y1 - y0) * 0.62))
            cx, cy = x0 + (x1 - x0) / 2, y0 + d / 2
        cols = self.colors()
        ss = 3
        sweep_total = 360.0 * ease("ease_in_out", p)
        start = -90.0
        Wd = d * ss
        thick = 0.34
        hole = int(Wd * (1 - thick * 2 * 0.5 * 2) / 1) if False else int(Wd * (1 - thick))
        acc = 0.0
        for i, v in enumerate(vals):
            a0 = acc / total * 360.0
            a1 = (acc + v) / total * 360.0
            acc += v
            if a0 >= sweep_total:
                break
            a1 = min(a1, sweep_total)
            if a1 - a0 < 0.05:
                continue
            m = Image.new("L", (Wd, Wd), 0)
            dr = ImageDraw.Draw(m)
            dr.pieslice((0, 0, Wd - 1, Wd - 1), start + a0, start + a1, fill=255)
            off = (Wd - hole) // 2
            dr.ellipse((off, off, off + hole, off + hole), fill=0)
            m = m.resize((d, d), Image.Resampling.BOX)
            canvas.alpha_composite(colorize(m, cols[i % len(cols)]), (int(round(cx - d / 2)), int(round(cy - d / 2))))
        # Center figure: share of the first slice.
        if vals and p > 0.3:
            share = vals[0] / total * 100.0 * ease("ease_out", clamp((p - 0.3) / 0.7))
            self._put_text(canvas, f"{share:.0f}%", d * 0.2, WHITE, cx, cy + d * 0.07, 800, self.L.display_font)
        # Legend
        labels = self.ov.labels or [f"Item {i + 1}" for i in range(len(vals))]
        lsize = self.S(30)
        row_h = lsize * 1.6
        sw = int(lsize * 0.8)
        if land:
            lx = x0 + d + self.S(50)
            ly = cy - row_h * len(vals) / 2
        else:
            lx = x0 + (x1 - x0) * 0.16
            ly = y0 + d + self.S(40)
        for i, v in enumerate(vals):
            if i >= len(labels):
                break
            alpha = clamp((p * len(vals) - i) * 1.5) if p < 1 else 1.0
            if alpha <= 0:
                continue
            yy = ly + i * row_h
            sq = colorize(rounded_mask(sw, sw, sw * 0.28), with_alpha(cols[i % len(cols)], alpha))
            canvas.alpha_composite(sq, (int(lx), int(yy + (row_h - sw) / 2)))
            txt = f"{labels[i]}  {v / total * 100:.0f}%"
            self._put_text(canvas, txt, lsize, with_alpha(LABEL, alpha), lx + sw + self.S(16), yy + row_h * 0.68, 600,
                           None, "left")


# ---------------------------------------------------------------------------
# Progress, shape, image, logo
# ---------------------------------------------------------------------------


class ProgressRenderer(Renderer):
    default_anchor = "top"

    def default_enter(self):
        return Anim(type="fade", duration=0.3, easing="ease_out")

    def value(self, lt):
        p = clamp(lt / max(0.01, self.ov.duration))
        return self.ov.from_value + (self.ov.to_value - self.ov.from_value) * p

    def content_key(self, lt):
        l, t, r, b = self.area()
        return int(round(self.value(lt) * (r - l)))

    def content(self, lt, states=None, char_limit=None):
        l, t, r, b = self.area()
        w = int(r - l)
        h = max(2, int(self.S(self.ov.thickness)))
        fill_w = int(round(self.value(lt) * w))
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        canvas.alpha_composite(colorize(rounded_mask(w, h, h / 2), parse_color(self.ov.track_color)))
        if fill_w >= 1:
            col = parse_color(self.ov.color, self.accent) if self.ov.color else self.accent
            canvas.alpha_composite(colorize(rounded_mask(max(h, fill_w), h, h / 2), col).crop((0, 0, fill_w, h)), (0, 0))
        return Content(canvas, 0, 0, w, h)


class ShapeRenderer(Renderer):
    def default_enter(self):
        return Anim(type="scale_in", duration=0.5, easing="bezier_out")

    def content(self, lt, states=None, char_limit=None):
        ov = self.ov
        l, t, r, b = self.area()
        w = int((r - l) * ov.width) if ov.width <= 1 else int(self.S(ov.width))
        h = int(self.S(ov.height))
        fill = parse_color(ov.fill, self.accent) if ov.fill else self.accent
        if ov.shape == "circle":
            m = ellipse_mask(w, h)
        elif ov.shape == "line":
            h = max(1, h)
            m = rounded_mask(w, h, h / 2)
        else:
            m = rounded_mask(w, h, self.S(ov.radius) if ov.shape == "rounded_rect" else 0)
        img = colorize(m, fill)
        if ov.stroke_color and ov.stroke_width > 0 and ov.shape != "line":
            sw = max(1, int(self.S(ov.stroke_width)))
            inner = Image.new("L", (w, h), 0)
            if ov.shape == "circle":
                inner.paste(ellipse_mask(max(1, w - 2 * sw), max(1, h - 2 * sw)), (sw, sw))
            else:
                rr = max(0.0, (self.S(ov.radius) if ov.shape == "rounded_rect" else 0) - sw)
                inner.paste(rounded_mask(max(1, w - 2 * sw), max(1, h - 2 * sw), rr), (sw, sw))
            from PIL import ImageChops

            ring = ImageChops.subtract(m, inner)
            img = Image.alpha_composite(img, colorize(ring, parse_color(ov.stroke_color)))
        return Content(img, 0, 0, w, h)


def _load_rgba(path: str) -> Optional[Image.Image]:
    import os

    from PIL import ImageOps

    if not path or not os.path.isfile(path):
        return None
    try:
        im = Image.open(path)
        im = ImageOps.exif_transpose(im)
        return im.convert("RGBA")
    except Exception:
        return None


class ImageOverlayRenderer(Renderer):
    def default_enter(self):
        return Anim(type="scale_in", duration=0.6, easing="bezier_out")

    def __init__(self, ov, lay, tl):
        super().__init__(ov, lay, tl)
        self._c = None

    def content(self, lt, states=None, char_limit=None):
        if self._c is not None:
            return self._c
        ov = self.ov
        src = _load_rgba(ov.src)
        if src is None:
            return None
        l, t, r, b = self.area()
        w = int((r - l) * ov.width) if ov.width <= 1 else int(min(r - l, self.S(ov.width)))
        h = int(self.S(ov.height)) if ov.height else int(round(src.height * w / src.width))
        h = min(h, b - t)
        from PIL import ImageOps

        img = ImageOps.fit(src, (w, h), Image.Resampling.LANCZOS) if ov.height else src.resize((w, h), Image.Resampling.LANCZOS)
        mask = rounded_mask(w, h, self.S(ov.radius))
        from PIL import ImageChops

        img.putalpha(ImageChops.multiply(img.getchannel("A"), mask))
        if ov.border and ov.border_width > 0:
            bw = max(1, int(self.S(ov.border_width)))
            inner = Image.new("L", (w, h), 0)
            inner.paste(rounded_mask(w - 2 * bw, h - 2 * bw, max(0, self.S(ov.radius) - bw)), (bw, bw))
            img = Image.alpha_composite(img, colorize(ImageChops.subtract(mask, inner), parse_color(ov.border)))
        if ov.shadow:
            from .draw import shadow_from_alpha

            sh, sx, sy = shadow_from_alpha(mask, Shadow(0, self.S(20), self.S(50), (0, 0, 0, 150)))
            pad = max(-sx, -sy, 0) + 2
            canvas = Image.new("RGBA", (w + 2 * pad + max(0, sx + sh.width - w), h + 2 * pad + max(0, sy + sh.height - h)), (0, 0, 0, 0))
            tx.composite_clipped(canvas, sh, pad + sx, pad + sy)
            canvas.alpha_composite(img, (pad, pad))
            self._c = Content(canvas, pad, pad, w, h)
        else:
            self._c = Content(img, 0, 0, w, h)
        return self._c


class LogoRenderer(Renderer):
    default_anchor = "top_right"

    def default_enter(self):
        return Anim(type="fade", duration=0.6, easing="ease_out")

    def __init__(self, ov, lay, tl):
        super().__init__(ov, lay, tl)
        self._c = None

    def content(self, lt, states=None, char_limit=None):
        if self._c is None:
            src = _load_rgba(self.ov.src)
            if src is None:
                return None
            w = max(8, int(self.S(self.ov.width)))
            h = max(1, int(round(src.height * w / src.width)))
            self._c = Content(src.resize((w, h), Image.Resampling.LANCZOS), 0, 0, w, h)
        return self._c


# ---------------------------------------------------------------------------
# Full-frame kinds
# ---------------------------------------------------------------------------


class ScrimRenderer(Renderer):
    def default_enter(self):
        return Anim(type="fade", duration=0.0, easing="linear")

    def default_exit(self):
        return Anim(type="fade", duration=0.0, easing="linear")

    def __init__(self, ov, lay, tl):
        super().__init__(ov, lay, tl)
        self._mask = None
        self._rgba = None
        self._scaled = _SmallCache(2)

    def _prepare(self):
        if self._mask is not None or self._rgba is not None:
            return
        size = (self.L.width, self.L.height)
        stops = self.ov.stops
        if not stops:
            self._mask = gradient_mask_vertical(size, STORY_SCRIM)
            self._color = SCRIM_RGB
            return
        cols = [parse_color(c) for _, c in stops]
        if all(c[:3] == cols[0][:3] for c in cols):
            self._mask = gradient_mask_vertical(size, [(p, c[3] / 255.0) for (p, _), c in zip(stops, cols)])
            self._color = cols[0][:3]
            return
        # Multi-color scrim: per channel gradients.
        chans = []
        for ci in range(4):
            chans.append(gradient_mask_vertical(size, [(p, c[ci] / 255.0) for (p, _), c in zip(stops, cols)]))
        self._rgba = Image.merge("RGBA", chans)

    def ops(self, t):
        lt = t - self.ov.start
        if lt < 0 or lt >= self.ov.duration:
            return []
        er, ee, xr, xe = self._phase(lt)
        o = self.ov.opacity * (ee if self.enter.type != "none" else 1.0) * (1.0 - xe)
        if o <= 0.003:
            return []
        self._prepare()
        q = round(o * 64) / 64.0
        if self._mask is not None:
            m = self._scaled.get(q, lambda: scale_mask(self._mask, q))
            return [Op("fill", mask=m, color=self._color)]
        img = self._scaled.get(q, lambda: scale_alpha(self._rgba, q))
        return [Op("sprite", img, 0, 0)]


class VignetteRenderer(ScrimRenderer):
    def _prepare(self):
        if self._mask is None:
            self._mask = vignette_mask((self.L.width, self.L.height), self.ov.inner, self.ov.strength)
            self._color = (0, 0, 0)


class OutroCardRenderer(Renderer):
    """Scrim rgba(4,6,10,.62), accent headline scaling 0.84 to 1 over 24
    frames with a glow pulsing on a 60 frame period, subline fading in over
    frames 14 to 34, and the whole frame fading to the background over the
    last ``fade_out`` seconds."""

    def __init__(self, ov, lay, tl):
        super().__init__(ov, lay, tl)
        self._prep = None

    def _build(self):
        if self._prep is not None:
            return self._prep
        L = self.L
        l, t, r, b = self.L.usable(True)
        width = r - l
        head = tx.layout_block(
            [tx.Run(self.ov.title, tx.RunStyle(self.st.font or L.display_font, self.st.weight or 800, self.size(96),
                                               parse_color(self.st.color, self.accent) if self.st.color else self.accent,
                                               1.0, -self.S(3), uppercase=bool(self.st.uppercase), max_lines=2))],
            width,
            "center",
        )
        # Glyph layer, dark drop shadow and accent glow are separate so the
        # glow can pulse without re-rendering text.
        glyph, ox, oy = tx.render_block(head)
        alpha = glyph.getchannel("A")
        glow_pad = int(self.S(60))
        big = Image.new("L", (alpha.width + 2 * glow_pad, alpha.height + 2 * glow_pad), 0)
        big.paste(alpha, (glow_pad, glow_pad))
        from .draw import blur_mask

        glow = colorize(blur_mask(big, self.S(46)), with_alpha(self.accent, 0.53 * 1.6))
        dark = colorize(blur_mask(big, self.S(30)), (0, 0, 0, 178))
        sub = None
        if self.ov.subtitle:
            sb = tx.layout_block(
                [tx.Run(self.ov.subtitle, tx.RunStyle(L.text_font, 600, L.subline_size, LABEL, 1.2, self.S(6), max_lines=2))],
                width,
                "center",
            )
            sub = tx.render_block(sb) + (sb,)
        self._prep = (head, glyph, ox, oy, glow, dark, glow_pad, sub)
        return self._prep

    def ops(self, t):
        ov = self.ov
        lt = t - ov.start
        if lt < 0 or lt >= ov.duration:
            return []
        f = lt * self.fps
        D = ov.duration * self.fps
        head, glyph, ox, oy, glow, dark, gp, sub = self._build()
        L = self.L
        ops: list[Op] = []
        scrim_in = clamp(f / 12.0)
        ops.append(Op("tint", color=SCRIM_RGB, alpha=ov.scrim_opacity * scrim_in))
        enter = ease("bezier_out", clamp(f / 24.0))
        pulse = 0.35 + 0.65 * (1.0 - abs((f % 60) - 30) / 30.0)
        # Compose headline sprite: dark shadow, glow (pulsing), glyphs.
        q = round(pulse * 20) / 20.0
        key = ("head", q)

        def make():
            canvas = Image.new("RGBA", glow.size, (0, 0, 0, 0))
            tx.composite_clipped(canvas, dark, 0, int(self.S(8)))
            canvas.alpha_composite(scale_alpha(glow, q))
            canvas.alpha_composite(glyph, (gp, gp))
            return canvas

        head_img = self.cache.get(key, make)
        sub_h = (sub[3].height + self.S(24)) if sub else 0
        total_h = head.height + sub_h
        cy = (L.height - total_h) / 2.0
        hx = (L.width - head.width) / 2.0
        hy = cy
        s = perceptual(0.84, 1.0, enter)
        img = head_img
        sx, sy = hx - ox - gp, hy - oy - gp
        if abs(s - 1.0) > 0.001:
            ccx, ccy = hx + head.width / 2, hy + head.height / 2
            img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.Resampling.BICUBIC)
            sx = ccx + (sx - ccx) * s
            sy = ccy + (sy - ccy) * s
        ops.append(Op("sprite", scale_alpha(img, enter * ov.opacity), int(round(sx)), int(round(sy))))
        if sub:
            simg, sox, soy, sb = sub
            so = clamp((f - 14) / 20.0)
            if so > 0:
                x = (L.width - sb.width) / 2 - sox
                y = hy + head.height + self.S(24) - soy
                ops.append(Op("sprite", scale_alpha(simg, so * ov.opacity), int(round(x)), int(round(y))))
        fo = ov.fade_out * self.fps
        if fo > 0 and f >= D - fo:
            a = clamp((f - (D - fo)) / fo)
            bg = parse_color(L.background, (4, 6, 10, 255))[:3]
            ops.append(Op("tint", color=bg, alpha=a))
        return ops


RENDERERS = {
    "title_card": TitleCardRenderer,
    "stat_card": StatCardRenderer,
    "lower_third": LowerThirdRenderer,
    "text": TextRenderer,
    "quote": QuoteRenderer,
    "list": ListRenderer,
    "counter": CounterRenderer,
    "chart": ChartRenderer,
    "progress": ProgressRenderer,
    "shape": ShapeRenderer,
    "image_overlay": ImageOverlayRenderer,
    "logo": LogoRenderer,
    "outro_card": OutroCardRenderer,
    "scrim": ScrimRenderer,
    "vignette": VignetteRenderer,
}


def build_renderers(tl: Timeline, lay: Layout) -> list[Renderer]:
    items = sorted(enumerate(tl.overlays), key=lambda iv: (iv[1].z, iv[0]))
    return [RENDERERS[ov.kind](ov, lay, tl) for _, ov in items]
