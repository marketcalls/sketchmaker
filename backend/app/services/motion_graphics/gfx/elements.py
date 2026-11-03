"""Core motion graphics elements: kinetic text, odometer, shapes, images.

Every element is drawn per frame from its params (no state between frames,
so preview_frame can sample any time). Time ``c`` is scene content seconds.
"""

from __future__ import annotations

import math
from typing import Optional

from PIL import Image, ImageFilter

from app.render.colors import readable_on

from ..design import E
from . import prim
from .ext import El, element


def _box(p, W, H):
    return float(p.get("x", 0)), float(p.get("y", 0)), float(p.get("w", W)), float(p.get("h", H))


# ---------------------------------------------------------------------------
# Kinetic text
# ---------------------------------------------------------------------------

class _Word:
    __slots__ = ("text", "size", "weight", "family", "color", "emph", "x", "w", "line", "baseline", "asc",
                 "desc", "idx")


@element("text")
class KText(El):
    """Word-level kinetic typography.

    params: text, x, y, w, h, align, valign, font, weight, size, min_size, lh,
    tracking (em), upper, color, mono, max_lines, balance, emph [word indices],
    emph_color, emph_text_color, emph_weight, emph_scale, emph_style
    (color|marker|underline|outline|box), anim {type, t, dur, stagger, ease,
    times, dist}, out {t, dur, type: fade_up|fade|mask_down}.
    Anim types: mask_up, slide_mask, slam, blur_in, fade_up, typewriter,
    weight_morph, pop, none.
    """

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self._layout = None
        self._static = None
        a = p.get("anim") or {}
        self.atype = a.get("type", "fade_up")
        self.at = float(a.get("t", self.t0))
        self.adur = max(1e-3, float(a.get("dur", 0.3)))
        self.astag = float(a.get("stagger", 0.08))
        self.aease = a.get("ease", "snap")
        self.atimes = a.get("times")
        self.adist = float(a.get("dist", 24))
        self.slam_from = float(a.get("slam_from", 1.3))

    # --- layout -----------------------------------------------------------
    def _measure_word(self, wd: _Word) -> float:
        return prim.measure(wd.text, wd.family, wd.weight, wd.size, self.tracking * wd.size,
                            self._cell(wd) if self.mono else None)

    def _cell(self, wd: _Word) -> float:
        return prim.mono_cell_width(wd.family, wd.weight, wd.size)

    def layout(self):
        if self._layout is not None:
            return self._layout
        p = self.p
        x, y, w, h = _box(p, self.W, self.H)
        family = p.get("font", "Inter")
        weight = int(p.get("weight", 700))
        size0 = float(p.get("size", 80))
        min_size = float(p.get("min_size", size0 * 0.5))
        lh = float(p.get("lh", 1.05))
        self.tracking = float(p.get("tracking", 0.0))
        self.mono = bool(p.get("mono", False))
        upper = bool(p.get("upper", False))
        max_lines = int(p.get("max_lines", 4))
        emph = set(int(i) for i in (p.get("emph") or []))
        escale = float(p.get("emph_scale", 1.0))
        eweight = int(p.get("emph_weight", weight))
        color = prim.rgba(p.get("color", "#FFFFFF"))
        ecolor = prim.rgba(p.get("emph_color", p.get("color", "#FFFFFF")))
        raw = (p.get("text") or "").split()
        if upper:
            raw = [t.upper() for t in raw]

        def build(s: float) -> list[_Word]:
            out = []
            for i, t in enumerate(raw):
                wd = _Word()
                wd.text, wd.idx = t, i
                wd.emph = i in emph
                wd.size = s * (escale if wd.emph else 1.0)
                wd.weight = eweight if wd.emph else weight
                wd.family = family
                wd.color = ecolor if wd.emph else color
                wd.w = self._measure_word(wd)
                out.append(wd)
            return out

        def wrap(words: list[_Word], s: float, width: float) -> list[list[_Word]]:
            space = prim.measure(" ", family, weight, s) * (1.0 + (0.6 if self.mono else 0.0)) + self.tracking * s
            lines, cur, cw = [], [], 0.0
            for wd in words:
                if cur and cw + space + wd.w > width + 0.5:
                    lines.append(cur)
                    cur, cw = [], 0.0
                cw = cw + (space if cur else 0.0) + wd.w
                cur.append(wd)
            if cur:
                lines.append(cur)
            return lines

        s = size0
        while True:
            words = build(s)
            lines = wrap(words, s, w)
            fits = all(wd.w <= w + 0.5 for wd in words) and len(lines) <= max_lines
            height = sum(max(wd.size for wd in ln) * lh for ln in lines)
            if fits and height <= h + 0.5:
                break
            if s <= min_size:
                break
            s = max(min_size, s * 0.95)
        # Balanced wrap: the narrowest width that keeps the line count.
        if p.get("balance", True) and len(lines) > 1:
            lo, hi = max(wd.w for wd in words), w
            n = len(lines)
            for _ in range(14):
                mid = (lo + hi) / 2
                if len(wrap(words, s, mid)) <= n:
                    hi = mid
                else:
                    lo = mid
            lines = wrap(words, s, hi)
        space = prim.measure(" ", family, weight, s) * (1.0 + (0.6 if self.mono else 0.0)) + self.tracking * s
        # Vertical metrics
        line_boxes = []
        top = 0.0
        for ln in lines:
            big = max(wd.size for wd in ln)
            lhp = big * lh
            asc, desc = prim.metrics(family, weight, big)
            base = top + (lhp - (asc + desc)) / 2.0 + asc
            line_boxes.append((top, lhp, base, asc, desc))
            top += lhp
        block_h = top
        align = p.get("align", "left")
        valign = p.get("valign", "top")
        y0 = y if valign == "top" else (y + (h - block_h) / 2.0 if valign == "center" else y + h - block_h)
        out_words = []
        lines_px = []
        for li, (ln, (lt, lhp, base, asc, desc)) in enumerate(zip(lines, line_boxes)):
            lw = sum(wd.w for wd in ln) + space * (len(ln) - 1)
            lx = x if align == "left" else (x + (w - lw) / 2.0 if align == "center" else x + w - lw)
            cx = lx
            for wd in ln:
                wd.x = cx
                wd.line = li
                wd.baseline = y0 + base
                wa, wdsc = prim.metrics(wd.family, wd.weight, wd.size)
                wd.asc, wd.desc = wa, wdsc
                out_words.append(wd)
                cx += wd.w + space
            lines_px.append((lx, y0 + lt, lw, lhp, y0 + base, asc, desc))
        self.size = s
        self._layout = (out_words, lines_px, (x, y0, w, block_h))
        return self._layout

    def bounds(self) -> tuple[float, float, float, float]:
        """(x, y, w, h) of the laid out text block (for builders)."""
        words, lines, (x, y0, w, bh) = self.layout()
        if not lines:
            return x, y0, 0, 0
        lx = min(l[0] for l in lines)
        rx = max(l[0] + l[2] for l in lines)
        return lx, y0, rx - lx, bh

    # --- per frame ----------------------------------------------------------
    def _start(self, wd: _Word) -> float:
        if self.atimes and wd.idx < len(self.atimes) and self.atimes[wd.idx] is not None:
            return float(self.atimes[wd.idx])
        return self.at + wd.idx * self.astag

    def _settled_at(self) -> float:
        words, _, _ = self.layout()
        if not words:
            return self.at
        last = max(self._start(wd) for wd in words) + self.adur
        if self.p.get("emph") and self.p.get("emph_style", "color") != "color":
            last += 0.45
        if self.atype == "typewriter":
            n = sum(len(wd.text) + 1 for wd in words)
            last = self.at + n * self.astag + 0.05
        return last

    def _glyph(self, wd: _Word, text: Optional[str] = None, weight: Optional[int] = None, color=None,
               outline: bool = False):
        cell = self._cell(wd) if self.mono else None
        stroke = max(1.5, wd.size * 0.03) if outline else 0.0
        col = color if color is not None else wd.color
        return prim.glyph(text if text is not None else wd.text, wd.family, weight or wd.weight, wd.size, col,
                          tracking=self.tracking * wd.size, stroke=stroke, stroke_color=col, outline=outline,
                          mono_cell=cell)

    def sprites(self, c: float):
        words, lines, _ = self.layout()
        if not words:
            return []
        o = self.p.get("out") or {}
        out_t = float(o.get("t", 1e9)) if o else 1e9
        if c >= self._settled_at() and c < out_t:
            return self._static_block()
        return self._draw(c, words, lines)

    def _static_block(self):
        if self._static is None:
            words, lines, _ = self.layout()
            sprites = self._draw(1e6, words, lines, settle=True)
            self._static = _compose(sprites)
        return [self._static] if self._static[0] is not None else []

    def _draw(self, c: float, words, lines, settle: bool = False):
        p = self.p
        res = []
        o = p.get("out") or {}
        q = 0.0
        if o and not settle:
            q = E(o.get("ease", "exit"), (c - float(o.get("t", 1e9))) / max(1e-3, float(o.get("dur", 0.2))))
        out_type = o.get("type", "fade_up") if o else None
        u = self.u
        estyle = p.get("emph_style", "color")
        accent = prim.rgba(p.get("emph_color", "#FFD166"))
        etext = prim.rgba(p.get("emph_text_color")) if p.get("emph_text_color") else None
        typed = None
        if self.atype == "typewriter" and not settle:
            typed = int(max(0.0, c - self.at) / max(1e-3, self.astag))
        char_pos = 0
        for wd in words:
            st = self._start(wd)
            raw = 1.0 if settle else (c - st) / self.adur
            if self.atype == "none":
                raw = 1.0 if settle or c >= st else -1.0
            if raw <= 0 and self.atype not in ("typewriter",):
                char_pos += len(wd.text) + 1
                continue
            pw = E(self.aease, raw)
            lx, ltop, lw, lhp, lbase, lasc, ldesc = lines[wd.line]
            x, base = wd.x, wd.baseline
            dx = dy = 0.0
            a = 1.0
            sc = 1.0
            clip = None
            blur = 0.0
            weight = None
            text = None
            if self.atype == "mask_up":
                hgt = (wd.asc + wd.desc) * 1.05
                dy = (1.0 - pw) * hgt
                clip = (x - wd.size, base - wd.asc * 1.08, x + wd.w + wd.size, base + wd.desc * 1.15)
            elif self.atype == "slide_mask":
                dx = -(1.0 - pw) * min(wd.w, wd.size * 1.4)
                clip = (x - 2, base - wd.asc * 1.2, x + wd.w + wd.size, base + wd.desc * 1.3)
            elif self.atype == "slam":
                sc = self.slam_from + (1.0 - self.slam_from) * pw
                a = min(1.0, max(0.0, raw) * 5.0)
            elif self.atype == "pop":
                sc = 0.6 + 0.4 * E("overshoot", raw)
                a = min(1.0, max(0.0, raw) * 4.0)
            elif self.atype == "blur_in":
                blur = 12.0 * u * (1.0 - pw)
                a = min(1.0, pw * 1.2)
                dy = 10.0 * u * (1.0 - pw)
            elif self.atype == "weight_morph":
                target = wd.weight
                wq = int(round((300 + (target - 300) * pw) / 25.0) * 25)
                weight = max(100, wq)
                a = min(1.0, max(0.0, raw) * 3.0)
            elif self.atype == "typewriter":
                if typed is not None:
                    vis = typed - char_pos
                    if vis <= 0:
                        char_pos += len(wd.text) + 1
                        continue
                    if vis < len(wd.text):
                        text = wd.text[:vis]
            elif self.atype == "fade_up":
                a = pw
                dy = self.adist * u * (1.0 - pw)
            char_pos += len(wd.text) + 1
            # Exit
            if q > 0:
                if out_type == "mask_down":
                    dy += q * (wd.asc + wd.desc) * 1.05
                    clip = (x - wd.size, base - wd.asc * 1.08, x + wd.w + wd.size, base + wd.desc * 1.15)
                elif out_type == "fade":
                    a *= 1.0 - q
                else:
                    a *= 1.0 - q
                    dy -= 24.0 * u * q
            if a <= 0.003:
                continue
            # Emphasis decorations (behind the word)
            color = None
            if wd.emph and estyle != "color":
                ep = 1.0 if settle else E("smooth", (c - (st + self.adur * 0.6)) / 0.35)
                if estyle in ("marker", "box") and ep > 0:
                    cap = prim.cap_height(wd.family, wd.weight, wd.size)
                    if estyle == "marker":
                        top_y, bot_y = base - cap * 1.12, base + wd.size * 0.12
                        padx = wd.size * 0.1
                    else:
                        top_y, bot_y = base - cap - wd.size * 0.16, base + wd.size * 0.18
                        padx = wd.size * 0.14
                        ep = 1.0 if settle else E("snap", (c - st) / 0.12)
                    mw = (wd.w + 2 * padx) * ep
                    if mw >= 1:
                        mk = prim.rect(mw, bot_y - top_y, prim.with_a(accent, 0.92 if estyle == "marker" else 1.0),
                                       radius=wd.size * 0.06 if estyle == "marker" else 0)
                        if q > 0 or a < 1:
                            mk = prim.alpha(mk, a)
                        res.append((mk, x - padx + dx, top_y + dy, clip))
                    if ep > 0.45:
                        color = etext or readable_on(accent)
                elif estyle == "underline" and ep > 0:
                    th = max(2.0, wd.size * 0.07)
                    ln = prim.rect(max(1.0, wd.w * ep), th, accent)
                    res.append((prim.alpha(ln, a), x + dx, base + wd.size * 0.1 + dy, None))
                elif estyle == "outline":
                    fill_p = 1.0 if settle else max(0.0, min(1.0, (c - st - 0.15) / 0.2))
                    g = self._glyph(wd, text, weight, outline=True)
                    if g.img is not None and fill_p < 1.0:
                        res.append((prim.alpha(g.img, a), x + g.ox + dx, base + g.oy + dy, clip))
                    if fill_p <= 0:
                        continue
                    a *= fill_p
            g = self._glyph(wd, text, weight, color=color)
            if g.img is None:
                continue
            img = g.img
            gx, gy = x + g.ox + dx, base + g.oy + dy
            if abs(sc - 1.0) > 0.002:
                cx, cy = x + wd.w / 2.0, base - wd.size * 0.35
                img = prim.scaled(img, sc)
                gx = cx + (gx - cx) * sc
                gy = cy + (gy - cy) * sc
            if blur > 0.4:
                pad = int(math.ceil(blur * 2))
                canvas = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
                canvas.paste(img, (pad, pad))
                img = canvas.filter(ImageFilter.GaussianBlur(blur))
                gx -= pad
                gy -= pad
            if a < 0.999:
                img = prim.alpha(img, a)
            res.append((img, gx, gy, clip))
            if typed is not None and text is not None:
                # block cursor after the last typed character
                cw = prim.measure(text, wd.family, wd.weight, wd.size, self.tracking * wd.size,
                                  self._cell(wd) if self.mono else None)
                cur = prim.rect(max(2.0, wd.size * 0.5), wd.size * 0.78, wd.color)
                res.append((cur, x + cw + wd.size * 0.06, base - wd.size * 0.72, None))
        out = []
        for img, x, y, clip in res:
            if clip is not None:
                r = prim.crop_to(img, x, y, clip)
                if r is None:
                    continue
                out.append(r)
            else:
                out.append((img, x, y))
        return out


def _compose(sprites: list[tuple]) -> tuple:
    """Flatten sprites into one (img, x, y)."""
    if not sprites:
        return (None, 0, 0)
    x0 = min(int(math.floor(s[1])) for s in sprites)
    y0 = min(int(math.floor(s[2])) for s in sprites)
    x1 = max(int(math.ceil(s[1])) + s[0].width for s in sprites)
    y1 = max(int(math.ceil(s[2])) + s[0].height for s in sprites)
    canvas = Image.new("RGBA", (max(1, x1 - x0), max(1, y1 - y0)), (0, 0, 0, 0))
    for img, x, y in sprites:
        canvas.alpha_composite(img, (int(round(x)) - x0, int(round(y)) - y0))
    return (canvas, x0, y0)


# ---------------------------------------------------------------------------
# Odometer and counter
# ---------------------------------------------------------------------------

def format_number(v: float, decimals: int = 0, sep: str = ",") -> str:
    s = f"{abs(v):,.{max(0, decimals)}f}"
    if sep != ",":
        s = s.replace(",", "\x00").replace("\x00", sep)
    return ("-" if v < 0 else "") + s


@element("odometer")
class Odometer(El):
    """A number that rolls into place digit by digit (or counts up).

    params: value, decimals, prefix, suffix, sep, x, y, w, h, align, valign,
    font, weight, size, min_size, color, suffix_color, suffix_scale,
    prefix_scale, tracking (em), t, dur, stagger, mode roll|count,
    pop {from, dur} (scale pop), units_at (fraction of dur), out.
    """

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self._prep = None
        self._final = None
        self.t = float(p.get("t", self.t0))
        self.dur = max(0.05, float(p.get("dur", 1.5)))
        self.stag = float(p.get("stagger", 0.04))
        self.mode = p.get("mode", "roll")

    def _layout(self):
        if self._prep is not None:
            return self._prep
        p = self.p
        x, y, w, h = _box(p, self.W, self.H)
        fam = p.get("font", "Inter")
        wt = int(p.get("weight", 900))
        size = float(p.get("size", 300))
        min_size = float(p.get("min_size", size * 0.45))
        dec = int(p.get("decimals", 0))
        val = float(p.get("value", 0))
        body = format_number(val, dec, p.get("sep", ","))
        prefix = p.get("prefix") or ""
        suffix = p.get("suffix") or ""
        ps = float(p.get("prefix_scale", 0.62))
        ss = float(p.get("suffix_scale", 0.42))
        tr = float(p.get("tracking", -0.02))
        while True:
            cell = prim.digit_cell(fam, wt, size)
            parts = []
            if prefix:
                parts.append(("p", prefix, size * ps, prim.measure(prefix, fam, wt, size * ps)))
            for ch in body:
                if ch.isdigit():
                    parts.append(("d", ch, size, cell + tr * size))
                else:
                    parts.append(("s", ch, size, prim.measure(ch, fam, wt, size) + tr * size))
            if suffix:
                parts.append(("u", suffix, size * ss, prim.measure(suffix, fam, max(600, wt - 200), size * ss)
                              + size * 0.06))
            total = sum(q[3] for q in parts)
            cap = prim.cap_height(fam, wt, size)
            if (total <= w and cap * 1.25 <= h) or size <= min_size:
                break
            size = max(min_size, size * 0.94)
        align = p.get("align", "center")
        x0 = x if align == "left" else (x + (w - total) / 2.0 if align == "center" else x + w - total)
        valign = p.get("valign", "center")
        cap = prim.cap_height(fam, wt, size)
        if valign == "top":
            base = y + cap
        elif valign == "bottom":
            base = y + h
        else:
            base = y + (h + cap) / 2.0
        self._prep = (parts, x0, base, total, cap, fam, wt, size)
        return self._prep

    def bounds(self):
        parts, x0, base, total, cap, fam, wt, size = self._layout()
        return x0, base - cap, total, cap

    def _digit_cols(self):
        parts = self._layout()[0]
        idx = [i for i, q in enumerate(parts) if q[0] == "d"]
        n = len(idx)
        return {i: n - 1 - k for k, i in enumerate(idx)}  # part index -> position from right

    def sprites(self, c):
        p = self.p
        parts, x0, base, total, cap, fam, wt, size = self._layout()
        done_at = self.t + self.dur + self.stag * 8
        a, dyo = self.out_state(c)
        if c >= done_at and self._final is not None and a >= 0.999:
            return [self._final]
        color = p.get("color", "#FFFFFF")
        scol = p.get("suffix_color", color)
        cols = self._digit_cols()
        n = max(1, len(cols))
        pieces = []
        xx = x0
        units_p = E("decel", (c - (self.t + self.dur * float(p.get("units_at", 0.8)))) / 0.3)
        lead_p = E("decel", (c - self.t) / 0.25)
        count_v = None
        if self.mode == "count":
            count_v = float(p.get("value", 0)) * E("counter", (c - self.t) / self.dur)
            s = format_number(count_v, int(p.get("decimals", 0)), p.get("sep", ","))
            digits = [ch for ch in s if ch.isdigit()]
            all_digits = [q for q in parts if q[0] == "d"]
            pad = len(all_digits) - len(digits)
            digits = ["0"] * max(0, pad) + digits
        di = 0
        cell_h = cap * 1.32
        for i, (kind, txt, sz, adv) in enumerate(parts):
            if kind == "d":
                k = cols[i]
                target = int(txt)
                if self.mode == "count":
                    ch = digits[di] if di < len(digits) else txt
                    di += 1
                    lead_zero = count_v is not None and c < self.t + self.dur and k >= len(
                        str(int(abs(count_v)))) + int(p.get("decimals", 0)) and k > int(p.get("decimals", 0))
                    if not lead_zero:
                        g = prim.glyph(ch, fam, wt, sz, color)
                        cw = prim.measure(ch, fam, wt, sz)
                        pieces.append((g, xx + (adv - cw) / 2.0, base, None))
                else:
                    start = self.t + k * self.stag
                    pk = E("counter", (c - start) / max(0.05, self.dur - k * self.stag))
                    spins = max(0, min(2, n - 1 - k + (1 if k == 0 else 0)))
                    R = target + 10 * spins
                    pos = R * pk
                    d0 = int(math.floor(pos)) % 10
                    frac = pos - math.floor(pos)
                    clip = (xx - sz * 0.1, base - cap * 1.06, xx + adv + sz * 0.1, base + cap * 0.04)
                    for dd, off in ((d0, -frac), ((d0 + 1) % 10, 1.0 - frac)):
                        if off >= 0.999 or off <= -0.999:
                            continue
                        g = prim.glyph(str(dd), fam, wt, sz, color)
                        cw = prim.measure(str(dd), fam, wt, sz)
                        pieces.append((g, xx + (adv - cw) / 2.0, base + off * cell_h, clip))
            elif kind == "p":
                g = prim.glyph(txt, fam, wt, sz, scol if p.get("prefix_accent") else color)
                pieces.append((g, xx, base, None, lead_p))
            elif kind == "s":
                g = prim.glyph(txt, fam, wt, sz, color)
                pieces.append((g, xx, base, None, lead_p))
            else:
                g = prim.glyph(txt, fam, max(600, wt - 200), sz, scol)
                pieces.append((g, xx + size * 0.06, base, None, units_p))
            xx += adv
        sprites = []
        for item in pieces:
            g, gx, gb, clip = item[0], item[1], item[2], item[3]
            al = item[4] if len(item) > 4 else 1.0
            if g.img is None or al <= 0.003:
                continue
            img = g.img if al >= 0.999 else prim.alpha(g.img, al)
            sx, sy = gx + g.ox, gb + g.oy
            if clip is not None:
                r = prim.crop_to(img, sx, sy, clip)
                if r is None:
                    continue
                sprites.append(r)
            else:
                sprites.append((img, sx, sy))
        block = _compose(sprites)
        if block[0] is None:
            return []
        img, bx, by = block
        pop = p.get("pop")
        if pop:
            pf = float(pop.get("from", 0.92))
            pp = E(pop.get("ease", "overshoot"), (c - self.t) / float(pop.get("dur", 0.4)))
            s = pf + (1.0 - pf) * pp
            if abs(s - 1.0) > 0.002:
                cx, cy = x0 + total / 2.0, base - cap / 2.0
                img = prim.scaled(img, s)
                bx = cx + (bx - cx) * s
                by = cy + (by - cy) * s
            a *= min(1.0, max(0.0, (c - self.t) / 0.12))
        if c >= done_at and a >= 0.999 and not pop:
            self._final = (img, bx, by)
        elif c >= done_at and a >= 0.999 and pop and c >= self.t + float(pop.get("dur", 0.4)):
            self._final = (img, bx, by)
        if a < 0.999:
            img = prim.alpha(img, a)
        return [(img, bx, by + dyo)]


# ---------------------------------------------------------------------------
# Shapes, panels, images
# ---------------------------------------------------------------------------

@element("shape")
class Shape(El):
    """params: shape rect|circle|ring|frame|tri_up|tri_down, x, y, w, h, color,
    radius, stroke, anim {type grow_x|grow_y|scale|fade|draw|none, t, dur,
    ease, origin left|right|center|top|bottom}, alpha, out."""

    def sprites(self, c):
        p = self.p
        x, y, w, h = _box(p, self.W, self.H)
        shape = p.get("shape", "rect")
        color = p.get("color", "#FFFFFF")
        an = p.get("anim") or {}
        at = float(an.get("t", self.t0))
        ad = max(1e-3, float(an.get("dur", 0.3)))
        kind = an.get("type", "none")
        pr = E(an.get("ease", "snap"), (c - at) / ad) if kind != "none" else (1.0 if c >= at else 0.0)
        if pr <= 0:
            return []
        a, dy = self.out_state(c)
        a *= float(p.get("alpha", 1.0))
        origin = an.get("origin", "left")
        if kind == "grow_x":
            nw = w * pr
            nx = x if origin == "left" else (x + w - nw if origin == "right" else x + (w - nw) / 2)
            x, w = nx, nw
        elif kind == "grow_y":
            nh = h * pr
            ny = y + h - nh if origin in ("bottom",) else (y if origin == "top" else y + (h - nh) / 2)
            y, h = ny, nh
        elif kind == "fade":
            a *= pr
        if w < 1 or h < 1:
            return []
        if shape == "circle":
            img = prim.circle(min(w, h), color)
        elif shape == "ring":
            sweep = 360.0 * pr if kind == "draw" else 360.0
            img = prim.ring(min(w, h), float(p.get("stroke", 4)), color, sweep)
        elif shape == "frame":
            img = prim.frame_rect(w, h, color, float(p.get("stroke", 3)), float(p.get("radius", 0)))
        elif shape in ("tri_up", "tri_down"):
            img = prim.triangle(w, h, color, up=shape == "tri_up")
        else:
            img = prim.rect(w, h, color, float(p.get("radius", 0)))
        if kind == "scale":
            s = max(0.01, pr)
            img2 = prim.scaled(img, s)
            x += (img.width - img2.width) / 2
            y += (img.height - img2.height) / 2
            img = img2
            a *= min(1.0, pr * 2)
        if a < 0.999:
            img = prim.alpha(img, a)
        return [(img, x, y + dy)]


@element("image")
class ImageEl(El):
    """params: src, x, y, w, h, fit cover|contain, radius, focus [fx, fy],
    zoom [from, to] over the element life, anim {type fade|reveal_up|scale|
    wipe|none, t, dur, ease}, border, border_w, shadow, out."""

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self._plate = None
        self._mask = None

    def _prepare(self):
        if self._plate is not None:
            return self._plate
        p = self.p
        src = prim.load_rgba(p.get("src"))
        x, y, w, h = _box(p, self.W, self.H)
        w, h = max(2, int(round(w))), max(2, int(round(h)))
        zmax = max(1.0, *(float(z) for z in (p.get("zoom") or [1.0, 1.0])))
        if src is None:
            plate = Image.new("RGBA", (int(w * zmax), int(h * zmax)), prim.rgba(p.get("placeholder", "#2A2A30")))
            self._plate = (plate, zmax)
            return self._plate
        fit = p.get("fit", "cover")
        if fit == "contain":
            from PIL import ImageOps

            fitted = ImageOps.contain(src, (int(w * zmax), int(h * zmax)), Image.Resampling.LANCZOS)
            plate = Image.new("RGBA", (int(w * zmax), int(h * zmax)), prim.rgba(p.get("matte", "#00000000")))
            plate.alpha_composite(fitted, ((plate.width - fitted.width) // 2, (plate.height - fitted.height) // 2))
        else:
            s = max(w * zmax / src.width, h * zmax / src.height)
            rs = src.resize((max(1, int(math.ceil(src.width * s))), max(1, int(math.ceil(src.height * s)))),
                            Image.Resampling.LANCZOS)
            fx, fy = p.get("focus") or (0.5, 0.5)
            pw, ph = int(w * zmax), int(h * zmax)
            l = int(max(0, min(rs.width - pw, fx * rs.width - pw / 2)))
            t = int(max(0, min(rs.height - ph, fy * rs.height - ph / 2)))
            plate = rs.crop((l, t, l + pw, t + ph))
        self._plate = (plate, zmax)
        return self._plate

    def sprites(self, c):
        p = self.p
        x, y, w, h = _box(p, self.W, self.H)
        w, h = max(2, int(round(w))), max(2, int(round(h)))
        plate, zmax = self._prepare()
        z0, z1 = (p.get("zoom") or [1.0, 1.0])[:2]
        life = max(0.1, (float(self.t1) if self.t1 is not None else self.sc.content_dur + 0.5) - self.t0)
        z = float(z0) + (float(z1) - float(z0)) * E("linear", (c - self.t0) / life)
        k = zmax / max(1e-3, z)
        ww, wh = w * k, h * k
        cx, cy = plate.width / 2.0, plate.height / 2.0
        box = (cx - ww / 2, cy - wh / 2, cx + ww / 2, cy + wh / 2)
        img = plate.resize((w, h), Image.Resampling.BILINEAR, box=box) if (zmax > 1.0 or plate.size != (w, h)) \
            else plate.copy()
        radius = float(p.get("radius", 0))
        if radius > 0:
            from PIL import ImageChops

            from app.render.draw import rounded_mask

            img.putalpha(ImageChops.multiply(img.getchannel("A"), rounded_mask(w, h, radius)))
        if p.get("border") and float(p.get("border_w", 0)) > 0:
            img.alpha_composite(prim.frame_rect(w, h, p["border"], float(p["border_w"]), radius))
        an = p.get("anim") or {}
        kind = an.get("type", "fade")
        at = float(an.get("t", self.t0))
        pr = E(an.get("ease", "decel"), (c - at) / max(1e-3, float(an.get("dur", 0.5))))
        if kind != "none" and pr <= 0:
            return []
        a, dy = self.out_state(c)
        ox = oy = 0.0
        if kind == "fade":
            a *= pr
        elif kind == "reveal_up":
            cut = int(round(h * pr))
            if cut < 1:
                return []
            img = img.crop((0, h - cut, w, h))
            oy = h - cut
        elif kind == "wipe":
            cut = int(round(w * pr))
            if cut < 1:
                return []
            img = img.crop((0, 0, cut, h))
        elif kind == "scale":
            s = 0.9 + 0.1 * pr
            img2 = prim.scaled(img, s)
            ox, oy = (w - img2.width) / 2, (h - img2.height) / 2
            img = img2
            a *= pr
        out = []
        if p.get("shadow"):
            sh = prim.rect(w, h, (0, 0, 0, 110), radius)
            pad = int(24 * self.u)
            canvas = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
            canvas.alpha_composite(sh, (pad, pad))
            canvas = canvas.filter(ImageFilter.GaussianBlur(14 * self.u))
            out.append((prim.alpha(canvas, a * min(1.0, pr if kind != "none" else 1.0)), x - pad,
                        y - pad + 14 * self.u + dy))
        if a < 0.999:
            img = prim.alpha(img, a)
        out.append((img, x + ox, y + oy + dy))
        return out


@element("logo")
class LogoEl(El):
    """params: src, x, y, w, h (max box), align, anim {type pop|fade|none, t, dur}, out."""

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self._img = None

    def sprites(self, c):
        p = self.p
        if self._img is None:
            src = prim.load_rgba(p.get("src"))
            if src is None:
                self._img = False
            else:
                x, y, w, h = _box(p, self.W, self.H)
                s = min(w / src.width, h / src.height)
                self._img = src.resize((max(1, int(src.width * s)), max(1, int(src.height * s))),
                                       Image.Resampling.LANCZOS)
        if not self._img:
            return []
        x, y, w, h = _box(p, self.W, self.H)
        img = self._img
        align = p.get("align", "center")
        px = x if align == "left" else (x + w - img.width if align == "right" else x + (w - img.width) / 2)
        py = y + (h - img.height) / 2
        an = p.get("anim") or {}
        kind = an.get("type", "fade")
        pr = E("overshoot" if kind == "pop" else "decel",
               (c - float(an.get("t", self.t0))) / max(1e-3, float(an.get("dur", 0.5))))
        if kind != "none" and pr <= 0:
            return []
        a, dy = self.out_state(c)
        if kind == "pop":
            s = 0.8 + 0.2 * pr
            img2 = prim.scaled(img, s)
            px += (img.width - img2.width) / 2
            py += (img.height - img2.height) / 2
            img = img2
            a *= min(1.0, pr * 3)
        elif kind == "fade":
            a *= pr
        if a < 0.999:
            img = prim.alpha(img, a)
        return [(img, px, py + dy)]


@element("badge")
class Badge(El):
    """A pill or tag: text in a box. params: text, x, y, anchor (top_left |
    top_right | bottom_left | bottom_right | center), font, weight, size, color,
    bg, border, border_w, radius, padx, pady, upper, tracking, mono, anim {type
    fade|slide|none, t, dur}, out."""

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self._spr = None

    def build(self):
        if self._spr is not None:
            return self._spr
        p = self.p
        text = p.get("text", "")
        if p.get("upper"):
            text = text.upper()
        size = float(p.get("size", 30))
        fam, wt = p.get("font", "Inter"), int(p.get("weight", 700))
        cell = prim.mono_cell_width(fam, wt, size) if p.get("mono") else None
        g = prim.glyph(text, fam, wt, size, p.get("color", "#FFFFFF"), tracking=float(p.get("tracking", 0)) * size,
                       mono_cell=cell)
        padx = float(p.get("padx", size * 0.7))
        pady = float(p.get("pady", size * 0.42))
        cap = prim.cap_height(fam, wt, size)
        bw = g.adv + 2 * padx
        bh = cap + 2 * pady
        canvas = Image.new("RGBA", (int(math.ceil(bw)), int(math.ceil(bh))), (0, 0, 0, 0))
        radius = float(p.get("radius", bh / 2))
        if p.get("bg"):
            canvas.alpha_composite(prim.rect(bw, bh, p["bg"], radius))
        if p.get("border") and float(p.get("border_w", 0)) > 0:
            canvas.alpha_composite(prim.frame_rect(bw, bh, p["border"], float(p["border_w"]), radius))
        if g.img is not None:
            canvas.alpha_composite(g.img, (int(round(padx + g.ox)), int(round(pady + cap + g.oy))))
        self._spr = canvas
        return canvas

    def sprites(self, c):
        p = self.p
        img = self.build()
        x, y = float(p.get("x", 0)), float(p.get("y", 0))
        anchor = p.get("anchor", "top_left")
        if "right" in anchor:
            x -= img.width
        elif anchor in ("center", "top", "bottom"):
            x -= img.width / 2
        if "bottom" in anchor:
            y -= img.height
        elif anchor == "center":
            y -= img.height / 2
        an = p.get("anim") or {}
        kind = an.get("type", "fade")
        pr = E("decel", (c - float(an.get("t", self.t0))) / max(1e-3, float(an.get("dur", 0.3))))
        if kind != "none" and pr <= 0:
            return []
        a, dy = self.out_state(c)
        dx = 0.0
        if kind == "fade":
            a *= pr
        elif kind == "slide":
            a *= pr
            dx = -(1 - pr) * 30 * self.u
        if a < 0.999:
            img = prim.alpha(img, a)
        return [(img, x + dx, y + dy)]


@element("panel")
class Panel(El):
    """A full-frame (or boxed) solid color, optionally sliding in. params: x, y,
    w, h, color, anim {type none|fade|wipe_up|wipe_left, t, dur, ease}, out."""

    def sprites(self, c):
        p = self.p
        x, y, w, h = _box(p, self.W, self.H)
        an = p.get("anim") or {}
        kind = an.get("type", "none")
        pr = 1.0 if kind == "none" else E(an.get("ease", "camera_strong"),
                                          (c - float(an.get("t", self.t0))) / max(1e-3, float(an.get("dur", 0.4))))
        if pr <= 0:
            return []
        a, dy = self.out_state(c)
        if kind == "fade":
            a *= pr
        elif kind == "wipe_up":
            nh = h * pr
            y, h = y + h - nh, nh
        elif kind == "wipe_left":
            w = w * pr
        elif kind == "from_left":
            x -= (1.0 - pr) * (x + w)
        elif kind == "from_right":
            x += (1.0 - pr) * (self.W - x)
        elif kind == "from_top":
            y -= (1.0 - pr) * (y + h)
        elif kind == "from_bottom":
            y += (1.0 - pr) * (self.H - y)
        if w < 1 or h < 1:
            return []
        img = prim.rect(w, h, p.get("color", "#000000"), float(p.get("radius", 0)))
        if a < 0.999:
            img = prim.alpha(img, a)
        return [(img, x, y + dy)]


@element("numeral")
class Numeral(El):
    """A big numeral or short word that slams in with scale and rotation.
    params: text, x, y (left, baseline), align left|center|right, font,
    weight, size, color, outline (bool), t, dur, from_scale, from_rot (deg),
    ease, out."""

    def sprites(self, c):
        p = self.p
        t, dur = float(p.get("t", self.t0)), float(p.get("dur", 0.35))
        raw = (c - t) / max(1e-3, dur)
        if raw <= 0:
            return []
        pr = E(p.get("ease", "overshoot"), raw)
        size = float(p.get("size", 300))
        fam, wt = p.get("font", "Inter"), int(p.get("weight", 900))
        col = p.get("color", "#FFFFFF")
        g = prim.glyph(str(p.get("text", "")), fam, wt, size, col, tracking=float(p.get("tracking", -0.02)) * size,
                       stroke=max(2.0, size * 0.025) if p.get("outline") else 0.0, stroke_color=col,
                       outline=bool(p.get("outline")))
        if g.img is None:
            return []
        x, base = float(p.get("x", 0)), float(p.get("y", 0))
        align = p.get("align", "left")
        gx = x if align == "left" else (x - g.adv / 2 if align == "center" else x - g.adv)
        img = g.img
        sx, sy = gx + g.ox, base + g.oy
        s = float(p.get("from_scale", 1.4)) + (1.0 - float(p.get("from_scale", 1.4))) * pr
        rot = float(p.get("from_rot", 10.0)) * (1.0 - min(1.0, max(0.0, pr)))
        cx, cy = sx + img.width / 2.0, sy + img.height / 2.0
        if abs(s - 1.0) > 0.002:
            img = prim.scaled(img, s)
        if abs(rot) > 0.05:
            img, _, _ = prim.rotated(img, rot)
        a, dy = self.out_state(c)
        a *= min(1.0, raw * 4.0)
        if a < 0.999:
            img = prim.alpha(img, a)
        return [(img, cx - img.width / 2.0, cy - img.height / 2.0 + dy)]
