"""Product explainer elements: an app window, toggle rows that switch on, a
code card that types itself, an API list, a hub diagram with pulses flowing
in, a struck-through list and a scrolling tag marquee.

Static parts (labels, the typed code, pills) are drawn once per element and
cached; each frame only composites them with the animated state.
"""

from __future__ import annotations

import math
import re

from PIL import Image, ImageDraw

from ..design import E, mix
from . import prim
from .ext import El, element

MONO = "JetBrains Mono"


def _p(c: float, t: float, dur: float, ease: str = "decel") -> float:
    return E(ease, (c - t) / max(1e-3, dur))


def _line_glyph(text: str, fam: str, wt: int, size: float, color, max_w: float):
    """One line of text, shortened with an ellipsis to fit ``max_w``."""
    g = prim.glyph(text, fam, wt, size, color)
    if g.adv <= max_w or len(text) < 4:
        return g
    while len(text) > 3 and prim.measure(text + "...", fam, wt, size) > max_w:
        text = text[:-1]
    return prim.glyph(text.rstrip() + "...", fam, wt, size, color)


def _blit(canvas: Image.Image, g, x: float, baseline: float) -> None:
    if g.img is not None:
        canvas.alpha_composite(g.img, (int(round(x + g.ox)), int(round(baseline + g.oy))))


# ---------------------------------------------------------------------------
# App window
# ---------------------------------------------------------------------------

@element("window")
class Window(El):
    """An app window card: rounded surface, hairline border, a title bar with
    three dots and a mono path. Rises in at ``t``. params: x, y, w, h, title,
    surface, border, bar_line, muted, radius, bar (title bar height), t, dur."""

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self._img = None

    def build(self):
        if self._img is not None:
            return self._img
        p, u = self.p, self.u
        w, h = float(p["w"]), float(p["h"])
        r = float(p.get("radius", 20 * u))
        bar = float(p.get("bar", 58 * u))
        img = Image.new("RGBA", (int(math.ceil(w)), int(math.ceil(h))), (0, 0, 0, 0))
        img.alpha_composite(prim.rect(w, h, p.get("surface", "#0F0F10"), r))
        line = prim.rect(w - 2, max(1, 1.5 * u), p.get("bar_line", p.get("border", "#2A2A2A")))
        img.alpha_composite(line, (1, int(bar)))
        d = 12 * u
        for j, col in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
            dot = prim.circle(d, mix(col, p.get("surface", "#0F0F10"), 0.25))
            img.alpha_composite(dot, (int(26 * u + j * (d + 9 * u)), int((bar - d) / 2)))
        title = str(p.get("title") or "")
        if title:
            size = bar * 0.34
            g = _line_glyph(title, MONO, 500, size, p.get("muted", "#8A8A86"), w - 220 * u)
            if g.img is not None:
                img.alpha_composite(g.img, (int((w - g.img.width) / 2), int((bar - g.img.height) / 2)))
        img.alpha_composite(prim.frame_rect(w, h, p.get("border", "#2A2A2A"), max(1.0, 1.5 * u), r))
        self._img = img
        return img

    def sprites(self, c):
        p = self.p
        pr = _p(c, float(p.get("t", self.t0)), float(p.get("dur", 0.5)), "snap")
        if pr <= 0:
            return []
        a, dy = self.out_state(c)
        img = self.build()
        s = 0.96 + 0.04 * pr
        x, y = float(p["x"]), float(p["y"])
        if s < 0.999:
            sm = prim.scaled(img, s)
            x += (img.width - sm.width) / 2
            y += (img.height - sm.height) / 2
            img = sm
        a *= min(1.0, pr * 1.4)
        if a < 0.999:
            img = prim.alpha(img, a)
        return [(img, x, y + dy + (1 - pr) * 36 * self.u)]


# ---------------------------------------------------------------------------
# Toggle rows
# ---------------------------------------------------------------------------

@element("toggles")
class Toggles(El):
    """Settings rows: a label and a switch each. Rows appear one by one, then
    the switches marked on flip on in turn (knob slides, track fills with the
    accent). params: x, y, w, rows [{label, on}], row_h, size, font, weight,
    color, muted, accent, track, rule, t, stagger, flip_t, flip_gap."""

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self._labels = None

    def labels(self):
        if self._labels is None:
            p = self.p
            size = float(p.get("size", 34 * self.u))
            room = float(p["w"]) - float(p.get("row_h", 90 * self.u)) * 1.1
            self._labels = [_line_glyph(str(r.get("label") or ""), p.get("font", "Inter"), int(p.get("weight", 600)),
                                        size, p.get("color", "#F4F4F1"), room) for r in p.get("rows") or []]
        return self._labels

    def sprites(self, c):
        p, u = self.p, self.u
        x, y, w = float(p["x"]), float(p["y"]), float(p["w"])
        rh = float(p.get("row_h", 90 * u))
        size = float(p.get("size", 34 * u))
        t, stagger = float(p.get("t", 0.0)), float(p.get("stagger", 0.12))
        flip_t, flip_gap = float(p.get("flip_t", t + 0.8)), float(p.get("flip_gap", 0.45))
        a_out, dy = self.out_state(c)
        th = rh * 0.4
        tw = th * 1.85
        out, k_on = [], 0
        for j, (row, g) in enumerate(zip(p.get("rows") or [], self.labels())):
            pr = _p(c, t + j * stagger, 0.4)
            on = bool(row.get("on", True))
            ft = flip_t + k_on * flip_gap
            if on:
                k_on += 1
            if pr <= 0:
                continue
            a = pr * a_out
            ry = y + j * rh + dy + (1 - pr) * 18 * u
            if j:
                out.append((prim.alpha(prim.rect(w, max(1, 1.2 * u), p.get("rule", "#2A2A2A")), a), x, ry))
            base = ry + rh / 2 + prim.cap_height(p.get("font", "Inter"), int(p.get("weight", 600)), size) / 2
            if g.img is not None:
                out.append((prim.alpha(g.img, a), x + g.ox, base + g.oy))
            q = _p(c, ft, 0.32, "smooth") if on else 0.0
            track = mix(p.get("track", "#2A2A2A"), p.get("accent", "#19C39B"), q)
            sx, sy = x + w - tw, ry + (rh - th) / 2
            out.append((prim.alpha(prim.rect(tw, th, track, th / 2), a), sx, sy))
            kd = th * 0.78
            kx = sx + (th - kd) / 2 + (tw - th) * q
            out.append((prim.alpha(prim.circle(kd, "#FFFFFF" if q > 0.5 else mix("#FFFFFF", track, 0.35)), a),
                        kx, sy + (th - kd) / 2))
        return out


# ---------------------------------------------------------------------------
# Code card
# ---------------------------------------------------------------------------

_KEYWORDS = {
    "def", "return", "import", "from", "as", "const", "let", "var", "await", "async", "if", "else", "elif", "for",
    "while", "in", "class", "function", "new", "with", "try", "except", "catch", "export", "True", "False", "None",
    "true", "false", "null", "print", "curl", "pip", "npm", "install",
}
_TOKEN = re.compile(r"(#[^\n]*|//[^\n]*)|(\"[^\"]*\"?|'[^']*'?)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)(\s*\()?|(.)")


def code_spans(line: str, colors: dict) -> list[tuple[str, str]]:
    """(text, color) runs of one code line: comments, strings, numbers,
    keywords and called names get their own colors."""
    out = []
    for m in _TOKEN.finditer(line):
        com, s, num, ident, call, other = m.groups()
        if com:
            out.append((com, colors["comment"]))
        elif s:
            out.append((s, colors["string"]))
        elif num:
            out.append((num, colors["number"]))
        elif ident:
            col = colors["keyword"] if ident in _KEYWORDS else colors["call"] if call else colors["text"]
            out.append((ident, col))
            if call:
                out.append((call, colors["text"]))
        else:
            out.append((other, colors["text"]))
    return out


@element("code_card")
class CodeCard(El):
    """Code lines typed in at ``cps`` characters per second, with line
    numbers and a blinking caret. params: x, y, w, lines, size, colors {text,
    keyword, string, number, comment, call, gutter, caret}, t, cps."""

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self._img = None

    def geometry(self):
        p = self.p
        size = float(p.get("size", 30 * self.u))
        cell = prim.mono_cell_width(MONO, 500, size)
        lines = [str(s) for s in p.get("lines") or []]
        gutter = cell * (len(str(len(lines))) + 2)
        return size, cell, size * 1.6, gutter, lines

    def build(self):
        if self._img is not None:
            return self._img
        p = self.p
        size, cell, lh, gutter, lines = self.geometry()
        cols = {"text": "#F4F4F1", "keyword": "#19C39B", "string": "#E9C46A", "number": "#4CC9F0",
                "comment": "#6B6B68", "call": "#8FD3FE", "gutter": "#4A4A48", **(p.get("colors") or {})}
        w = float(p["w"])
        img = Image.new("RGBA", (int(math.ceil(w)), int(math.ceil(lh * max(1, len(lines))))), (0, 0, 0, 0))
        asc = size * 0.8
        for i, line in enumerate(lines):
            base = i * lh + (lh - size) / 2 + asc
            _blit(img, prim.glyph(str(i + 1), MONO, 500, size, cols["gutter"], mono_cell=cell), 0, base)
            x = gutter
            for text, col in code_spans(line, cols):
                if x > w:
                    break
                _blit(img, prim.glyph(text, MONO, 500, size, col, mono_cell=cell), x, base)
                x += len(text) * cell
        self._img = img
        return img

    def sprites(self, c):
        p = self.p
        t, cps = float(p.get("t", 0.0)), float(p.get("cps", 40.0))
        if c < t:
            return []
        a, dy = self.out_state(c)
        size, cell, lh, gutter, lines = self.geometry()
        img = self.build()
        n = int((c - t) * cps)
        x, y = float(p["x"]), float(p["y"]) + dy
        out, left = [], n
        caret = None
        for i, line in enumerate(lines):
            ln = max(1, len(line))
            y0 = int(i * lh)
            y1 = min(img.height, int((i + 1) * lh))
            if left >= ln:
                row = img.crop((0, y0, img.width, y1))
                left -= ln
                caret = (gutter + len(line) * cell, i)
            else:
                cw = int(min(img.width, gutter + left * cell))
                row = img.crop((0, y0, max(1, cw), y1))
                caret = (gutter + left * cell, i)
                out.append((prim.alpha(row, a) if a < 0.999 else row, x, y + y0))
                break
            out.append((prim.alpha(row, a) if a < 0.999 else row, x, y + y0))
        if caret is not None and int(c * 2.2) % 2 == 0:
            cx_, ci = caret
            bar = prim.rect(max(2, cell * 0.55), size * 1.1, (p.get("colors") or {}).get("caret", "#19C39B"))
            out.append((prim.alpha(bar, a * 0.9), x + cx_ + 2 * self.u, y + ci * lh + (lh - size * 1.1) / 2))
        return out


# ---------------------------------------------------------------------------
# API list
# ---------------------------------------------------------------------------

METHOD_COLORS = {"GET": "#19C39B", "POST": "#4CC9F0", "PUT": "#E9C46A", "PATCH": "#E9C46A", "DELETE": "#E5383B",
                 "WS": "#B794F6"}


@element("api_list")
class ApiList(El):
    """Endpoint rows: a method tag, a mono path and a note, appearing one by
    one, then a highlight settles on one row. params: x, y, w, rows [{method,
    path, note}], row_h, size, color, muted, rule, highlight (row index or
    -1), hl_color, t, stagger."""

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self._rows = None

    def rows(self):
        if self._rows is not None:
            return self._rows
        p, u = self.p, self.u
        w = float(p["w"])
        rh = float(p.get("row_h", 86 * u))
        size = float(p.get("size", 30 * u))
        out = []
        for r in p.get("rows") or []:
            method = str(r.get("method") or "GET").upper()[:6]
            col = METHOD_COLORS.get(method, "#8A8A86")
            img = Image.new("RGBA", (int(math.ceil(w)), int(math.ceil(rh))), (0, 0, 0, 0))
            ts = size * 0.62
            tag_w = prim.mono_cell_width(MONO, 700, ts) * 6 + ts * 1.2
            tag_h = ts * 1.9
            img.alpha_composite(prim.rect(tag_w, tag_h, mix(col, "#000000", 0.78), 6 * u), (0, int((rh - tag_h) / 2)))
            img.alpha_composite(prim.frame_rect(tag_w, tag_h, mix(col, "#000000", 0.35), max(1, 1.2 * u), 6 * u),
                                (0, int((rh - tag_h) / 2)))
            g = prim.glyph(method, MONO, 700, ts, col)
            if g.img is not None:
                img.alpha_composite(g.img, (int((tag_w - g.img.width) / 2), int((rh - g.img.height) / 2)))
            px = tag_w + 24 * u
            note = str(r.get("note") or "")
            note_w = min(w * 0.38, prim.measure(note, "Inter", 500, size * 0.8)) if note else 0
            gp = _line_glyph(str(r.get("path") or ""), MONO, 500, size, p.get("color", "#F4F4F1"),
                             w - px - note_w - 30 * u)
            base = rh / 2 + prim.cap_height(MONO, 500, size) / 2
            _blit(img, gp, px, base)
            if note:
                gn = _line_glyph(note, "Inter", 500, size * 0.8, p.get("muted", "#8A8A86"), note_w + 1)
                if gn.img is not None:
                    img.alpha_composite(gn.img, (int(w - gn.img.width), int((rh - gn.img.height) / 2)))
            out.append(img)
        self._rows = out
        return out

    def sprites(self, c):
        p, u = self.p, self.u
        x, y, w = float(p["x"]), float(p["y"]), float(p["w"])
        rh = float(p.get("row_h", 86 * u))
        t, stagger = float(p.get("t", 0.0)), float(p.get("stagger", 0.14))
        a_out, dy = self.out_state(c)
        hl = int(p.get("highlight", -1))
        rows = self.rows()
        out = []
        if 0 <= hl < len(rows):
            q = _p(c, t + len(rows) * stagger + 0.3, 0.4, "smooth")
            if q > 0:
                band = prim.rect(w + 32 * u, rh, mix(p.get("hl_color", "#19C39B"), "#000000", 0.84), 10 * u)
                out.append((prim.alpha(band, q * a_out), x - 16 * u, y + hl * rh + dy))
        for j, img in enumerate(rows):
            pr = _p(c, t + j * stagger, 0.35)
            if pr <= 0:
                continue
            ry = y + j * rh + dy
            if j:
                out.append((prim.alpha(prim.rect(w, max(1, 1.2 * u), p.get("rule", "#2A2A2A")), pr * a_out), x, ry))
            out.append((prim.alpha(img, pr * a_out), x - (1 - pr) * 24 * u, ry))
        return out


# ---------------------------------------------------------------------------
# Hub diagram
# ---------------------------------------------------------------------------

@element("hub")
class Hub(El):
    """A centre node joined to up to eight labelled nodes around it. The
    links draw out from the centre, then pulses flow in along each link.
    params: x, y, w, h (the box), center, nodes [text], size, color, muted,
    accent, surface, rule, t, period."""

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self._pills = None
        self._core = None

    def _pill(self, text: str, size: float, fg, bg, border, bw: float):
        u = self.u
        g = prim.glyph(text, self.p.get("font", "Inter"), 650, size, fg)
        cap = prim.cap_height(self.p.get("font", "Inter"), 650, size)
        w, h = g.adv + size * 1.5, cap + size * 1.1
        img = Image.new("RGBA", (int(math.ceil(w)), int(math.ceil(h))), (0, 0, 0, 0))
        img.alpha_composite(prim.rect(w, h, bg, h / 2))
        img.alpha_composite(prim.frame_rect(w, h, border, max(1.0, bw * u), h / 2))
        if g.img is not None:
            img.alpha_composite(g.img, (int((w - g.img.width) / 2), int((h - g.img.height) / 2)))
        return img

    def layout(self):
        if self._pills is not None:
            return self._pills, self._core
        p = self.p
        size = float(p.get("size", 30 * self.u))
        self._pills = [self._pill(str(n)[:24], size, p.get("color", "#F4F4F1"), p.get("surface", "#0F0F10"),
                                  p.get("rule", "#2A2A2A"), 1.5) for n in (p.get("nodes") or [])[:8]]
        self._core = self._pill(str(p.get("center") or "")[:20], size * 1.25, p.get("on_accent", "#050505"),
                                p.get("accent", "#19C39B"), p.get("accent", "#19C39B"), 1.5)
        return self._pills, self._core

    def positions(self):
        p = self.p
        pills, core = self.layout()
        x, y, w, h = (float(p[k]) for k in ("x", "y", "w", "h"))
        cx, cy = x + w / 2, y + h / 2
        mw = max([im.width for im in pills] + [1])
        mh = max([im.height for im in pills] + [1])
        rx, ry = max(10.0, w / 2 - mw / 2), max(10.0, h / 2 - mh / 2)
        n = max(1, len(pills))
        pts = []
        for j in range(len(pills)):
            ang = -math.pi / 2 + 2 * math.pi * j / n + (math.pi / n if n in (2, 4) else 0.0)
            pts.append((cx + rx * math.cos(ang), cy + ry * math.sin(ang)))
        return cx, cy, pts

    def sprites(self, c):
        p, u = self.p, self.u
        t = float(p.get("t", 0.0))
        a_out, dy = self.out_state(c)
        pills, core = self.layout()
        cx, cy, pts = self.positions()
        acc = p.get("accent", "#19C39B")
        out = []
        # Links, drawn from the centre outward.
        W, H = self.W, self.H
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        lw = max(1, int(round(2 * u)))
        link = prim.rgba(mix(p.get("rule", "#2A2A2A"), acc, 0.25))
        grown = []
        for j, (px, py) in enumerate(pts):
            q = _p(c, t + 0.25 + j * 0.07, 0.5, "smooth")
            grown.append(q)
            if q > 0:
                d.line([(cx, cy), (cx + (px - cx) * q, cy + (py - cy) * q)], fill=link, width=lw)
        # Pulses flow in from each node to the centre once its link is drawn.
        period = float(p.get("period", 1.6))
        ready = t + 0.25 + len(pts) * 0.07 + 0.5
        if c > ready:
            for j, (px, py) in enumerate(pts):
                ph = ((c - ready) / period + j / max(1, len(pts)) * 0.6) % 1.0
                for k, (lag, rad, al) in enumerate(((0.0, 7.0, 1.0), (0.05, 5.0, 0.5), (0.1, 4.0, 0.25))):
                    f = ph - lag
                    if 0.0 < f < 1.0:
                        qx, qy = px + (cx - px) * f, py + (cy - py) * f
                        r = rad * u
                        d.ellipse((qx - r, qy - r, qx + r, qy + r), fill=prim.with_a(prim.rgba(acc), al * 0.95))
        bb = lay.getbbox()
        if bb:
            img = lay.crop(bb)
            out.append((prim.alpha(img, a_out) if a_out < 0.999 else img, bb[0], bb[1] + dy))
        for j, ((px, py), im) in enumerate(zip(pts, pills)):
            q = _p(c, t + 0.45 + j * 0.07, 0.4, "overshoot")
            if q <= 0:
                continue
            s = max(0.01, min(1.15, q))
            sm = prim.scaled(im, s) if abs(s - 1) > 0.01 else im
            out.append((prim.alpha(sm, min(1.0, q) * a_out), px - sm.width / 2, py - sm.height / 2 + dy))
        q = _p(c, t, 0.45, "overshoot")
        if q > 0:
            glow = 1.0 + 0.04 * math.sin(max(0.0, c - ready) * 4.0) if c > ready else 1.0
            s = max(0.01, min(1.15, q)) * glow
            sm = prim.scaled(core, s) if abs(s - 1) > 0.01 else core
            out.append((prim.alpha(sm, min(1.0, q) * a_out), cx - sm.width / 2, cy - sm.height / 2 + dy))
        return out


# ---------------------------------------------------------------------------
# Struck-through list
# ---------------------------------------------------------------------------

@element("strike_list")
class StrikeList(El):
    """Lines that appear, then get struck through (and dim) one by one: the
    old way, the pain points. params: x, y, w, items, size, font, weight,
    color, strike, line_h, t, stagger, strike_t, strike_gap."""

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self._g = None

    def glyphs(self):
        if self._g is None:
            p = self.p
            size = float(p.get("size", 44 * self.u))
            self._g = [_line_glyph(str(s), p.get("font", "Inter"), int(p.get("weight", 700)), size,
                                   p.get("color", "#F4F4F1"), float(p["w"])) for s in p.get("items") or []]
        return self._g

    def sprites(self, c):
        p, u = self.p, self.u
        x, y = float(p["x"]), float(p["y"])
        size = float(p.get("size", 44 * u))
        lh = float(p.get("line_h", size * 1.9))
        t, stagger = float(p.get("t", 0.0)), float(p.get("stagger", 0.15))
        st, sg = float(p.get("strike_t", t + 0.9)), float(p.get("strike_gap", 0.35))
        a_out, dy = self.out_state(c)
        cap = prim.cap_height(p.get("font", "Inter"), int(p.get("weight", 700)), size)
        out = []
        for j, g in enumerate(self.glyphs()):
            pr = _p(c, t + j * stagger, 0.4)
            if pr <= 0 or g.img is None:
                continue
            q = _p(c, st + j * sg, 0.3, "smooth")
            a = pr * a_out * (1.0 - 0.55 * q)
            base = y + j * lh + cap + dy + (1 - pr) * 20 * u
            out.append((prim.alpha(g.img, a), x + g.ox, base + g.oy))
            if q > 0:
                bar = prim.rect(max(1.0, (g.adv + 16 * u) * q), max(3.0, size * 0.09), p.get("strike", "#E5383B"))
                out.append((prim.alpha(bar, pr * a_out), x - 8 * u, base - cap * 0.5))
        return out


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------

@element("progress")
class Progress(El):
    """A thin bar filling from left to right over ``total`` seconds of the
    overlay. params: x, y, w, h, color, track, total."""

    def sprites(self, c):
        p = self.p
        x, y, w, h = float(p["x"]), float(p["y"]), float(p["w"]), float(p["h"])
        q = max(0.0, min(1.0, c / max(1e-3, float(p.get("total", 1.0)))))
        out = [(prim.rect(w, h, p.get("track", "rgba(255,255,255,0.14)"), h / 2), x, y)]
        if q * w >= 1:
            out.append((prim.rect(q * w, h, p.get("color", "#19C39B"), h / 2), x, y))
        return out


# ---------------------------------------------------------------------------
# Marquee
# ---------------------------------------------------------------------------

@element("marquee")
class Marquee(El):
    """A full-width strip of pill tags scrolling sideways, faded at both
    edges. params: y, h, items, size, color, surface, rule, speed (px per
    second, in u), t."""

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self._strip = None
        self._mask = None

    def build(self):
        if self._strip is not None:
            return self._strip
        p, u = self.p, self.u
        size = float(p.get("size", 30 * u))
        pills = []
        for s in [str(x) for x in p.get("items") or [] if str(x).strip()][:24]:
            g = prim.glyph(s[:28], p.get("font", "Inter"), 600, size, p.get("color", "#F4F4F1"))
            cap = prim.cap_height(p.get("font", "Inter"), 600, size)
            w, h = g.adv + size * 1.6, cap + size * 1.2
            im = Image.new("RGBA", (int(math.ceil(w)), int(math.ceil(h))), (0, 0, 0, 0))
            im.alpha_composite(prim.rect(w, h, p.get("surface", "#0F0F10"), h / 2))
            im.alpha_composite(prim.frame_rect(w, h, p.get("rule", "#2A2A2A"), max(1.0, 1.5 * u), h / 2))
            if g.img is not None:
                im.alpha_composite(g.img, (int((w - g.img.width) / 2), int((h - g.img.height) / 2)))
            pills.append(im)
        if not pills:
            self._strip = False
            return False
        gap = 18 * u
        unit = sum(im.width for im in pills) + gap * len(pills)
        reps = max(2, int(math.ceil(self.W / max(1.0, unit))) + 1)
        h = max(im.height for im in pills)
        strip = Image.new("RGBA", (int(math.ceil(unit * reps)), h), (0, 0, 0, 0))
        x = 0.0
        for _ in range(reps):
            for im in pills:
                strip.alpha_composite(im, (int(x), int((h - im.height) / 2)))
                x += im.width + gap
        self._strip = (strip, unit)
        fade = max(2, int(self.W * 0.12))
        m = Image.new("L", (self.W, h), 255)
        dm = ImageDraw.Draw(m)
        for i in range(fade):
            v = int(255 * i / fade)
            dm.line([(i, 0), (i, h)], fill=v)
            dm.line([(self.W - 1 - i, 0), (self.W - 1 - i, h)], fill=v)
        self._mask = m
        return self._strip

    def sprites(self, c):
        p = self.p
        t = float(p.get("t", 0.0))
        pr = _p(c, t, 0.5)
        built = self.build()
        if pr <= 0 or not built:
            return []
        strip, unit = built
        a_out, dy = self.out_state(c)
        off = ((c - t) * float(p.get("speed", 90)) * self.u) % unit
        win = strip.crop((int(off), 0, int(off) + self.W, strip.height))
        win.putalpha(Image.composite(win.getchannel("A"), Image.new("L", win.size, 0), self._mask))
        return [(prim.alpha(win, pr * a_out), 0, float(p["y"]) + dy)]
