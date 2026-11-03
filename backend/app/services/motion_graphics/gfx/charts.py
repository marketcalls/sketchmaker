"""Data elements: bar chart race, bars, line chart, donut, market tiles,
versus metric. Bars always start at zero; ticks use 1, 2, 2.5 and 5 steps.

All of them are stateless per frame. The bar chart race smooths rank swaps
and axis rescales with a short windowed average of the instantaneous state
(sampled at earlier times), so any frame can be drawn in isolation.
"""

from __future__ import annotations

import math

from PIL import Image


from ..design import E, nice_step
from . import prim
from .elements import format_number
from .ext import El, element


def tick_fmt(step: float, f: dict) -> dict:
    dec = 0 if step >= 1 else (1 if step >= 0.1 else 2)
    return {**f, "compact": True, "decimals": dec}


def fmt_value(v: float, f: dict) -> str:
    prefix, suffix = f.get("prefix", ""), f.get("suffix", "")
    dec = int(f.get("decimals", 0))
    if f.get("compact"):
        a = abs(v)
        for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if a >= div:
                q = v / div
                d = 1 if abs(q) < 100 else 0
                s = f"{q:.{d}f}"
                if d:
                    s = s.rstrip("0").rstrip(".")
                return f"{prefix}{s}{suf}{suffix}"
    return f"{prefix}{format_number(v, dec)}{suffix}"


def _text(img_list, text, fam, wt, size, color, x, base, align="left", tracking=0.0, alpha=1.0):
    """Append a glyph sprite positioned by its baseline. Returns the advance."""
    g = prim.glyph(text, fam, wt, size, color, tracking=tracking * size)
    if g.img is None or alpha <= 0.003:
        return g.adv
    gx = x if align == "left" else (x - g.adv if align == "right" else x - g.adv / 2)
    img = g.img if alpha >= 0.999 else prim.alpha(g.img, alpha)
    img_list.append((img, gx + g.ox, base + g.oy))
    return g.adv


def _fit_text(text, fam, wt, size, max_w, min_size=None):
    min_size = min_size or size * 0.6
    s = size
    while s > min_size and prim.measure(text, fam, wt, s) > max_w:
        s *= 0.93
    if prim.measure(text, fam, wt, s) <= max_w:
        return text, s
    t = text
    while len(t) > 2 and prim.measure(t + "...", fam, wt, s) > max_w:
        t = t[:-1]
    return t.rstrip() + "...", s


def _bar(w, h, color, radius):
    """Horizontal bar with a rounded right end (square left end at the axis)."""
    w, h = max(1, int(round(w))), max(1, int(round(h)))
    if radius <= 0.5 or w <= 2:
        return prim.rect(w, h, color)
    r = min(radius, h / 2)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cap = prim.rect(int(math.ceil(2 * r)), h, color, r)
    body = int(w - r)
    if body > 0:
        img.paste(prim.rect(body, h, color), (0, 0))
    if cap.width > w:
        cap = cap.crop((cap.width - w, 0, cap.width, h))
    img.alpha_composite(cap, (w - cap.width, 0))
    return img


def _col(w, h, color, radius):
    """Vertical column with a rounded top."""
    w, h = max(1, int(round(w))), max(1, int(round(h)))
    if radius <= 0.5 or h <= 2:
        return prim.rect(w, h, color)
    r = min(radius, w / 2, h)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cap = prim.rect(w, int(math.ceil(2 * r)), color, r)
    if cap.height > h:
        cap = cap.crop((0, 0, w, h))
    img.alpha_composite(cap, (0, 0))
    if h - int(r) > 0:
        img.paste(prim.rect(w, h - int(r), color), (0, int(r)))
    return img


# ---------------------------------------------------------------------------
# Bar chart race
# ---------------------------------------------------------------------------

@element("bar_race")
class BarRace(El):
    """params: x, y, w, h, periods [labels], entities [{name, color, values}],
    top_n, t (race start), period_dur, format {prefix, suffix, decimals,
    compact}, label_font, label_weight, value_font, value_weight, ticker
    {x, y, w, h, size, font, weight, color, alpha}, text, muted, rule,
    highlight_at (content time the final ranking highlight starts), accent,
    radius, label_mode column|inside."""

    WINDOW = 0.42
    SAMPLES = 9

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self.periods = list(p.get("periods") or [])
        self.ents = list(p.get("entities") or [])
        self.n = max(1, len(self.periods))
        self.top = int(p.get("top_n", 10))
        self.t = float(p.get("t", 0.0))
        self.pd = max(0.2, float(p.get("period_dur", 0.8)))
        self._names = {}

    def _f(self, c: float) -> float:
        return max(0.0, min(self.n - 1.0, (c - self.t) / self.pd))

    def _vals(self, f: float) -> list[float]:
        i = int(math.floor(f))
        a = f - i
        j = min(self.n - 1, i + 1)
        out = []
        for e in self.ents:
            v = e["values"]
            v0 = float(v[i] or 0.0) if i < len(v) and v[i] is not None else 0.0
            v1 = float(v[j] or 0.0) if j < len(v) and v[j] is not None else v0
            out.append(v0 + (v1 - v0) * a)
        return out

    def _ranks(self, vals: list[float]) -> list[int]:
        order = sorted(range(len(vals)), key=lambda k: (-vals[k], self.ents[k]["name"]))
        r = [0] * len(vals)
        for pos, k in enumerate(order):
            r[k] = pos
        return r

    def _smoothed(self, c: float):
        K = self.SAMPLES
        ranks = [0.0] * len(self.ents)
        vmax = 0.0
        wsum = 0.0
        for k in range(K):
            tt = c - self.WINDOW * k / (K - 1)
            w = 0.5 - 0.5 * math.cos(2 * math.pi * (k + 0.5) / K)
            vals = self._vals(self._f(tt))
            rk = self._ranks(vals)
            for e in range(len(ranks)):
                ranks[e] += rk[e] * w
            vmax += max(vals + [0.0]) * w
            wsum += w
        return [r / wsum for r in ranks], vmax / wsum

    def _name_sprite(self, k: int, size: float, max_w: float, color, fam, wt):
        key = (k, int(size), int(max_w), color)
        if key not in self._names:
            text, s = _fit_text(self.ents[k]["name"], fam, wt, size, max_w)
            self._names[key] = prim.glyph(text, fam, wt, s, color)
        return self._names[key]

    def sprites(self, c):
        p = self.p
        x, y, w, h = float(p["x"]), float(p["y"]), float(p["w"]), float(p["h"])
        u = self.u
        text = p.get("text", "#FFFFFF")
        muted = p.get("muted", "#9AA5B1")
        rule = p.get("rule", "#FFFFFF")
        lf, lw = p.get("label_font", "Inter"), int(p.get("label_weight", 600))
        vf, vw = p.get("value_font", "Inter"), int(p.get("value_weight", 800))
        fmt = p.get("format") or {}
        out = []
        f = self._f(c)
        vals = self._vals(f)
        ranks, vmax = self._smoothed(c)
        vmax = max(vmax * 1.06, 1e-9)
        n_rows = min(self.top, len(self.ents))
        axis_h = 46 * u
        rows_y = y + axis_h
        row_h = (h - axis_h) / max(1, n_rows)
        land = self.W > self.H * 1.2
        above = not land  # portrait and square: names sit above the bars, bars use the full width
        thick = row_h * (0.5 if above else 0.74)
        label_w = 0.0 if above else w * 0.24
        bar_x = x + (0.0 if above else label_w + 18 * u)
        value_room = 150 * u
        bar_w_max = max(10.0, x + w - bar_x - value_room)
        name_size = min(row_h * 0.26, 30 * u) if above else min(thick * 0.5, 34 * u)
        value_size = min(thick * 0.6 if above else thick * 0.48, 32 * u)
        # Gridlines and tick labels with a crossfade when the step changes.
        intro = E("decel", (c - (self.t - 0.6)) / 0.4)
        step_now = nice_step(vmax, 4)
        ticks = [(step_now, 1.0)]
        for back in range(1, 7):
            _, vm2 = self._smoothed(c - back / 30.0)
            st2 = nice_step(max(vm2 * 1.06, 1e-9), 4)
            if st2 != step_now:
                fade = back / 6.0
                ticks = [(step_now, fade), (st2, 1.0 - fade)]
                break
        tick_size = 22 * u
        for step, ta in ticks:
            k = 0
            while True:
                v = step * k
                if v > vmax:
                    break
                gx = bar_x + bar_w_max * (v / vmax)
                lw_ = max(1.0, 1.5 * u)
                line = prim.rect(lw_, h - axis_h + 6 * u, prim.with_a(prim.rgba(rule), 0.16 * ta * intro))
                out.append((line, gx, rows_y - 6 * u))
                _text(out, fmt_value(v, tick_fmt(step, fmt)), lf, 600, tick_size, muted, gx, y + axis_h - 18 * u,
                      align="center", alpha=ta * intro)
                k += 1
                if k > 12:
                    break
        # Final ranking highlight
        hl = 0.0
        if p.get("highlight_at") is not None:
            hl = E("smooth", (c - float(p["highlight_at"])) / 0.5)
        accent = p.get("accent", "#FFD166")
        winner = min(range(len(self.ents)), key=lambda k: (-vals[k], self.ents[k]["name"])) if self.ents else -1
        # Bars, bottom ranks first so the leaders draw on top during swaps.
        order = sorted(range(len(self.ents)), key=lambda k: -ranks[k])
        radius = float(p.get("radius", thick * 0.18))
        for k in order:
            r = ranks[k]
            if r > n_rows + 0.6:
                continue
            a = max(0.0, min(1.0, n_rows + 0.35 - r)) * intro
            if a <= 0.01:
                continue
            if hl > 0 and k != winner:
                a *= 1.0 - 0.55 * hl
            cy = rows_y + r * row_h + row_h / 2 + (row_h * 0.16 if above else 0.0)
            v = vals[k]
            bw = bar_w_max * max(0.0, v) / vmax * min(1.0, intro * 1.2)
            col = self.ents[k].get("color") or accent
            if bw >= 1:
                bar = _bar(bw, thick, col, radius)
                if hl > 0 and k == winner:
                    ring = prim.frame_rect(bw + 8 * u, thick + 8 * u, accent, 3 * u, radius + 4 * u)
                    out.append((prim.alpha(ring, hl), bar_x - 4 * u, cy - thick / 2 - 4 * u))
                out.append((prim.alpha(bar, a) if a < 0.999 else bar, bar_x, cy - thick / 2))
            g = self._name_sprite(k, name_size, w * 0.9 if above else label_w, text, lf, lw)
            if g.img is not None:
                cap = prim.cap_height(lf, lw, name_size)
                img = g.img if a >= 0.999 else prim.alpha(g.img, a)
                if above:
                    out.append((img, bar_x + g.ox, cy - thick / 2 - 10 * u + g.oy))
                else:
                    out.append((img, bar_x - 18 * u - g.adv + g.ox, cy + cap / 2 + g.oy))
            vcap = prim.cap_height(vf, vw, value_size)
            _text(out, fmt_value(v, fmt), vf, vw, value_size, text, bar_x + bw + 14 * u, cy + vcap / 2, alpha=a)
        # Period ticker
        tk = p.get("ticker")
        if tk and self.periods:
            label = str(self.periods[int(round(f))])
            size = float(tk.get("size", 160 * u))
            fam, wt = tk.get("font", vf), int(tk.get("weight", 900))
            tx = float(tk.get("x", x + w))
            ty = float(tk.get("y", y + h))
            _text(out, label, fam, wt, size, tk.get("color", muted), tx, ty, align=tk.get("align", "right"),
                  alpha=float(tk.get("alpha", 0.9)) * intro, tracking=-0.02)
        return out


# ---------------------------------------------------------------------------
# Bars (grow from zero)
# ---------------------------------------------------------------------------

@element("bars")
class Bars(El):
    """params: x, y, w, h, labels, values, highlight (index or None),
    orientation v|h, t, dur, stagger, format, color, highlight_color,
    muted_color, text, muted, rule, font, value_font, show_values."""

    def sprites(self, c):
        p = self.p
        x, y, w, h = float(p["x"]), float(p["y"]), float(p["w"]), float(p["h"])
        labels = list(p.get("labels") or [])
        values = [float(v or 0) for v in (p.get("values") or [])]
        n = len(values)
        if n == 0:
            return []
        u = self.u
        t0 = float(p.get("t", 0.0))
        dur = float(p.get("dur", 0.6))
        stag = float(p.get("stagger", 0.06))
        hi = p.get("highlight")
        fmt = p.get("format") or {}
        text, muted, rule = p.get("text", "#FFFFFF"), p.get("muted", "#9AA5B1"), p.get("rule", "#FFFFFF")
        base_col = p.get("color", "#9AA5B1")
        hi_col = p.get("highlight_color", base_col)
        lf = p.get("font", "Inter")
        vf = p.get("value_font", lf)
        vmin = min(0.0, min(values))
        vmax = max(0.0, max(values))
        if vmax - vmin <= 0:
            vmax = vmin + 1
        a_out, dy = self.out_state(c)
        out = []
        axis_p = E("decel", (c - t0 + 0.2) / 0.4)
        if p.get("orientation", "v") == "v":
            label_band = 70 * u
            value_band = 64 * u
            top = y + value_band
            bottom = y + h - label_band
            span = bottom - top
            zero_y = bottom - span * (0 - vmin) / (vmax - vmin)
            slot = w / n
            bw = slot * 0.62
            out.append((prim.rect(w * axis_p, max(2, 3 * u), prim.with_a(prim.rgba(rule), 0.5)), x, zero_y))
            for i, v in enumerate(values):
                pr = E("counter", (c - t0 - i * stag) / dur)
                col = hi_col if (hi is None or i == hi) else p.get("muted_color", base_col)
                bh = span * abs(v) / (vmax - vmin) * pr
                cx = x + slot * (i + 0.5)
                if bh >= 1:
                    img = _col(bw, bh, col, min(10 * u, bw / 4))
                    if v < 0:
                        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                    out.append((img, cx - bw / 2, zero_y - bh if v >= 0 else zero_y))
                if p.get("show_values", True) and pr > 0.05:
                    vs = fmt_value(v * pr, fmt)
                    vsz = min(40 * u, slot * 0.9 / max(3, len(vs)) * 1.75)
                    vy = (zero_y - bh - 16 * u) if v >= 0 else (zero_y + bh + vsz + 10 * u)
                    _text(out, vs, vf, 800, vsz, text if (hi is None or i == hi) else muted, cx, vy, "center",
                          alpha=min(1.0, pr * 2))
                if i < len(labels):
                    lab, ls = _fit_text(str(labels[i]), lf, 600, 28 * u, slot * 0.96)
                    _text(out, lab, lf, 600, ls, muted, cx, y + h - label_band + 44 * u, "center", alpha=axis_p)
        else:
            label_w = w * 0.3
            bx = x + label_w + 16 * u
            bwmax = w - label_w - 16 * u - 140 * u
            slot = h / n
            th = slot * 0.66
            out.append((prim.rect(max(2, 3 * u), h * axis_p, prim.with_a(prim.rgba(rule), 0.5)), bx - 2 * u, y))
            for i, v in enumerate(values):
                pr = E("counter", (c - t0 - i * stag) / dur)
                col = hi_col if (hi is None or i == hi) else p.get("muted_color", base_col)
                bwid = bwmax * max(0.0, v) / max(1e-9, vmax) * pr
                cy = y + slot * (i + 0.5)
                if bwid >= 1:
                    out.append((_bar(bwid, th, col, min(10 * u, th / 4)), bx, cy - th / 2))
                if i < len(labels):
                    lab, ls = _fit_text(str(labels[i]), lf, 600, min(32 * u, th * 0.5), label_w)
                    cap = prim.cap_height(lf, 600, ls)
                    _text(out, lab, lf, 600, ls, text, bx - 16 * u, cy + cap / 2, "right", alpha=axis_p)
                if p.get("show_values", True) and pr > 0.05:
                    vsz = min(34 * u, th * 0.5)
                    cap = prim.cap_height(vf, 800, vsz)
                    _text(out, fmt_value(v * pr, fmt), vf, 800, vsz, text, bx + bwid + 12 * u, cy + cap / 2,
                          alpha=min(1.0, pr * 2))
        if a_out < 0.999 or dy:
            out = [(prim.alpha(i, a_out), xx, yy + dy) for i, xx, yy in out]
        return out


# ---------------------------------------------------------------------------
# Line chart
# ---------------------------------------------------------------------------

@element("line_chart")
class LineChart(El):
    """params: x, y, w, h, labels, series [{name, values, color, highlight}],
    t, axes_dur, draw_dur, annotation {index, text, series}, format, text,
    muted, rule, font, value_font, accent, zero (force a zero baseline)."""

    def _range(self):
        vals = [float(v) for s in self.p.get("series") or [] for v in s.get("values") or [] if v is not None]
        if not vals:
            return 0.0, 1.0
        lo, hi = min(vals), max(vals)
        if self.p.get("zero", lo >= 0 and lo < hi * 0.35):
            lo = min(0.0, lo)
        span = hi - lo or abs(hi) or 1.0
        step = nice_step(span, 5)
        lo = math.floor(lo / step) * step
        hi = math.ceil(hi / step) * step
        if hi == lo:
            hi = lo + step
        return lo, hi

    def sprites(self, c):
        p = self.p
        x, y, w, h = float(p["x"]), float(p["y"]), float(p["w"]), float(p["h"])
        u = self.u
        t0 = float(p.get("t", 0.0))
        axes_dur = float(p.get("axes_dur", 0.4))
        draw_dur = float(p.get("draw_dur", 3.0))
        labels = list(p.get("labels") or [])
        series = list(p.get("series") or [])
        fmt = p.get("format") or {}
        text, muted, rule = p.get("text", "#FFFFFF"), p.get("muted", "#9AA5B1"), p.get("rule", "#FFFFFF")
        lf = p.get("font", "Inter")
        vf = p.get("value_font", lf)
        lo, hi = self._range()
        step = nice_step(hi - lo, 5)
        out = []
        tick_w = 110 * u
        px0 = x + tick_w
        px1 = x + w - 30 * u
        py0 = y + 30 * u
        py1 = y + h - 64 * u
        ax = E("decel", (c - t0) / axes_dur)
        if ax <= 0:
            return []
        # gridlines and ticks
        k = 0
        while lo + k * step <= hi + 1e-9 and k < 12:
            v = lo + k * step
            gy = py1 - (py1 - py0) * (v - lo) / (hi - lo)
            out.append((prim.rect((px1 - px0) * ax, max(1, 1.5 * u), prim.with_a(prim.rgba(rule), 0.14 if v else 0.45)),
                        px0, gy))
            _text(out, fmt_value(v, tick_fmt(step, fmt)), lf, 600, 22 * u, muted, px0 - 14 * u, gy + 8 * u,
                  "right", alpha=ax)
            k += 1
        n = max((len(s.get("values") or []) for s in series), default=0)
        if n == 0:
            return out
        xs = [px0 + (px1 - px0) * (i / max(1, n - 1)) for i in range(n)]
        every = max(1, int(math.ceil(n / (8 if self.W > self.H else 5))))
        for i, lab in enumerate(labels[:n]):
            if i % every and i != n - 1:
                continue
            _text(out, str(lab), lf, 600, 22 * u, muted, xs[i], py1 + 40 * u, "center", alpha=ax)
        dp = E("standard", (c - t0 - axes_dur) / draw_dur)
        head = dp * (n - 1)
        Wc, Hc = int(math.ceil(w)), int(math.ceil(h))
        for si, s in enumerate(series):
            vals = [float(v) if v is not None else None for v in s.get("values") or []]
            pts = []
            for i, v in enumerate(vals):
                if v is None:
                    continue
                if i <= head:
                    pts.append((xs[i] - x, py1 - (py1 - py0) * (v - lo) / (hi - lo) - y))
                elif i - 1 >= 0 and vals[i - 1] is not None and i - 1 <= head:
                    f = head - (i - 1)
                    y0v = vals[i - 1]
                    vv = y0v + (v - y0v) * f
                    pts.append((xs[i - 1] - x + (xs[i] - xs[i - 1]) * f, py1 - (py1 - py0) * (vv - lo) / (hi - lo) - y))
                    break
                else:
                    break
            if len(pts) < 1:
                continue
            col = s.get("color") or p.get("accent", "#FFD166")
            highlight = s.get("highlight", si == 0)
            if highlight and len(pts) >= 2:
                out.append((prim.area_fill((Wc, Hc), pts, py1 - y, col, 0.22, py0 - y), x, y))
            if len(pts) >= 2:
                out.append((prim.polyline((Wc, Hc), pts, (7 if highlight else 4) * u, col), x, y))
            if highlight and pts:
                hx, hy = pts[-1]
                d = 26 * u
                out.append((prim.circle(d * 1.9, prim.with_a(prim.rgba(col), 0.25)), x + hx - d * 0.95, y + hy - d * 0.95))
                out.append((prim.circle(d, col), x + hx - d / 2, y + hy - d / 2))
                vnow = lo + (hi - lo) * ((py1 - y) - hy) / (py1 - py0)
                if dp < 1.0 or True:
                    _text(out, fmt_value(vnow, fmt), vf, 800, 34 * u, text, x + hx, y + hy - 30 * u, "center",
                          alpha=1.0 if dp < 0.98 else max(0.0, 1.0 - (c - t0 - axes_dur - draw_dur) / 0.4))
        # Annotation callout at the key point
        an = p.get("annotation")
        if an and an.get("text") and series:
            idx = int(an.get("index", n - 1))
            sv = series[int(an.get("series", 0))].get("values") or []
            if 0 <= idx < len(sv) and sv[idx] is not None:
                t_hit = t0 + axes_dur + draw_dur * (idx / max(1, n - 1))
                lp = E("snap", (c - t_hit) / 0.25)
                if lp > 0:
                    ax_ = xs[idx]
                    ay_ = py1 - (py1 - py0) * (float(sv[idx]) - lo) / (hi - lo)
                    up = ay_ > py0 + (py1 - py0) * 0.35
                    length = 120 * u
                    ly0 = ay_ - 18 * u if up else ay_ + 18 * u
                    ll = length * lp
                    acc = p.get("accent", "#FFD166")
                    out.append((prim.rect(max(2, 3 * u), ll, acc), ax_ - 1.5 * u, ly0 - ll if up else ly0))
                    lab_p = E("decel", (c - t_hit - 0.25) / 0.35)
                    if lab_p > 0:
                        from .elements import KText

                        ty = (ly0 - length - 12 * u) if up else (ly0 + length + 12 * u)
                        bw = min(520 * u, w * 0.5)
                        bx = min(max(x, ax_ - bw / 2), x + w - bw)
                        kt = getattr(self, "_ann", None)
                        if kt is None:
                            kt = KText({"text": an["text"], "x": bx, "y": 0, "w": bw, "h": 200 * u, "font": lf,
                                        "weight": 700, "size": 34 * u, "color": text, "align": "center",
                                        "anim": {"type": "none"}, "max_lines": 3}, self.sc)
                            self._ann = kt
                        spr = kt._static_block()
                        if spr:
                            img, sx, sy = spr[0]
                            hgt = img.height
                            yy = (ty - hgt) if up else ty
                            out.append((prim.alpha(img, lab_p), sx, yy + (1 - lab_p) * 16 * u))
        a, dy = self.out_state(c)
        if a < 0.999 or dy:
            out = [(prim.alpha(i, a), xx, yy + dy) for i, xx, yy in out]
        return out


# ---------------------------------------------------------------------------
# Donut
# ---------------------------------------------------------------------------

@element("donut")
class Donut(El):
    """params: x, y, w, h, labels, values, colors, t, dur, center_text,
    center_label, text, muted, font, value_font, legend (bool)."""

    def sprites(self, c):
        p = self.p
        x, y, w, h = float(p["x"]), float(p["y"]), float(p["w"]), float(p["h"])
        u = self.u
        vals = [max(0.0, float(v or 0)) for v in p.get("values") or []]
        total = sum(vals) or 1.0
        labels = list(p.get("labels") or [])
        cols = list(p.get("colors") or ["#FFD166"])
        t0, dur = float(p.get("t", 0)), float(p.get("dur", 1.2))
        pr = E("standard", (c - t0) / dur)
        if pr <= 0:
            return []
        land = w > h * 1.2
        d = min(h, w * 0.5) if land else min(w * 0.78, h * 0.62)
        cx = x + d / 2 if land else x + w / 2
        cy = y + h / 2 if land else y + d / 2
        out = []
        acc = 0.0
        sweep = 360.0 * pr
        thick = d * 0.2
        for i, v in enumerate(vals):
            a0 = acc / total * 360.0
            a1 = (acc + v) / total * 360.0
            acc += v
            if a0 >= sweep:
                break
            a1 = min(a1, sweep)
            if a1 - a0 < 0.2:
                continue
            gap = 1.2 if len(vals) > 1 else 0
            img = prim.donut_slice(d, thick, -90 + a0 + gap / 2, -90 + a1 - gap / 2, cols[i % len(cols)])
            out.append((img, cx - d / 2, cy - d / 2))
        text, muted = p.get("text", "#FFFFFF"), p.get("muted", "#9AA5B1")
        vf = p.get("value_font", "Inter")
        lf = p.get("font", "Inter")
        cp = E("decel", (c - t0 - dur * 0.5) / 0.5)
        if p.get("center_text") and cp > 0:
            cap = prim.cap_height(vf, 900, d * 0.2)
            _text(out, p["center_text"], vf, 900, d * 0.2, text, cx, cy + cap / 2 - (d * 0.04 if p.get("center_label") else 0),
                  "center", alpha=cp)
            if p.get("center_label"):
                _text(out, p["center_label"], lf, 600, d * 0.065, muted, cx, cy + cap / 2 + d * 0.1, "center", alpha=cp)
        if p.get("legend", True):
            size = 30 * u
            row = size * 1.7
            if land:
                lx, ly = x + d + 60 * u, cy - row * len(vals) / 2
            else:
                lx, ly = x + w * 0.12, y + d + 50 * u
            for i, v in enumerate(vals[: len(labels)]):
                la = E("decel", (c - t0 - dur * (i / max(1, len(vals))) - 0.2) / 0.3)
                if la <= 0:
                    continue
                sw = size * 0.8
                out.append((prim.alpha(prim.rect(sw, sw, cols[i % len(cols)], sw * 0.25), la), lx, ly + i * row + (row - sw) / 2))
                _text(out, f"{labels[i]}  {v / total * 100:.0f}%", lf, 600, size, text, lx + sw + 16 * u,
                      ly + i * row + row * 0.68, alpha=la)
        a, dy = self.out_state(c)
        if a < 0.999 or dy:
            out = [(prim.alpha(i, a), xx, yy + dy) for i, xx, yy in out]
        return out


# ---------------------------------------------------------------------------
# Market tiles
# ---------------------------------------------------------------------------

@element("tiles")
class Tiles(El):
    """params: x, y, w, h, items [{name, value, change, spark}], cols, t,
    stagger, count_dur, card {fill, border, border_w, radius}, text, muted,
    positive, negative, font, value_font, value_format {decimals, prefix,
    suffix}, mono."""

    def sprites(self, c):
        p = self.p
        items = list(p.get("items") or [])
        if not items:
            return []
        x, y, w, h = float(p["x"]), float(p["y"]), float(p["w"]), float(p["h"])
        u = self.u
        cols = max(1, int(p.get("cols", 2)))
        rows = int(math.ceil(len(items) / cols))
        gap = 22 * u
        tw = (w - gap * (cols - 1)) / cols
        th = min((h - gap * (rows - 1)) / rows, tw * 0.75)
        t0 = float(p.get("t", 0))
        stag = float(p.get("stagger", 0.05))
        cdur = float(p.get("count_dur", 0.9))
        card = p.get("card") or {}
        text, muted = p.get("text", "#FFFFFF"), p.get("muted", "#9AA5B1")
        pos, neg = p.get("positive", "#3DDC84"), p.get("negative", "#FF5A5F")
        lf = p.get("font", "Inter")
        vf = p.get("value_font", lf)
        vfmt = p.get("value_format") or {"decimals": 2}
        out = []
        a_out, dyo = self.out_state(c)
        total_h = rows * th + (rows - 1) * gap
        y0 = y + (h - total_h) / 2
        for i, it in enumerate(items):
            r, k = divmod(i, cols)
            tx = x + k * (tw + gap)
            ty = y0 + r * (th + gap)
            ap = E("decel", (c - t0 - i * stag) / 0.3)
            if ap <= 0:
                continue
            dy = (1 - ap) * 24 * u + dyo
            al = ap * a_out
            sprites = []
            if card.get("fill"):
                sprites.append((prim.rect(tw, th, card["fill"], float(card.get("radius", 0))), tx, ty))
            if card.get("border") and float(card.get("border_w", 0)) > 0:
                sprites.append((prim.frame_rect(tw, th, card["border"], float(card["border_w"]),
                                                float(card.get("radius", 0))), tx, ty))
            pad = 26 * u
            name_size = min(30 * u, th * 0.17)
            name, ns = _fit_text(str(it.get("name", "")), lf, 700, name_size, tw - 2 * pad)
            _text(sprites, name.upper() if p.get("upper_names", True) else name, lf, 700, ns, muted, tx + pad,
                  ty + pad + prim.cap_height(lf, 700, ns), tracking=0.06)
            cp = E("counter", (c - t0 - i * stag - 0.1) / cdur)
            value = float(it.get("value") or 0)
            vs = fmt_value(value * (0.85 + 0.15 * cp) if cp < 1 else value, vfmt)
            vsize = min(64 * u, th * 0.3)
            vstr, vsz = _fit_text(vs, vf, 800, vsize, tw - 2 * pad, vsize * 0.6)
            vcap = prim.cap_height(vf, 800, vsz)
            vbase = ty + th * 0.56 + vcap / 2
            _text(sprites, vstr, vf, 800, vsz, text, tx + pad, vbase)
            ch = it.get("change")
            if ch is not None:
                chv = float(ch) * cp
                up = float(ch) >= 0
                col = pos if up else neg
                csz = min(34 * u, th * 0.17)
                ccap = prim.cap_height(vf, 700, csz)
                cy_ = ty + th - pad
                tri = prim.triangle(csz * 0.7, csz * 0.6, col, up=up)
                sprites.append((tri, tx + pad, cy_ - ccap / 2 - tri.height / 2))
                _text(sprites, f"{'+' if up else ''}{chv:.2f}%", vf, 700, csz, col, tx + pad + csz * 0.95, cy_)
                spark = it.get("spark")
                if spark and len(spark) >= 2:
                    sw, sh = tw * 0.36, th * 0.26
                    sx0, sy0 = tx + tw - pad - sw, ty + th - pad - sh
                    lo, hi = min(spark), max(spark)
                    span = (hi - lo) or 1.0
                    sp = E("standard", (c - t0 - i * stag - 0.2) / 0.8)
                    nn = len(spark)
                    head = sp * (nn - 1)
                    pts = []
                    for j, v in enumerate(spark):
                        if j > head + 1e-6:
                            if j > 0:
                                f = head - (j - 1)
                                v0 = spark[j - 1]
                                pts.append((sw * (j - 1 + f) / (nn - 1), sh - sh * ((v0 + (v - v0) * f) - lo) / span))
                            break
                        pts.append((sw * j / (nn - 1), sh - sh * (v - lo) / span))
                    if len(pts) >= 2:
                        sprites.append((prim.polyline((int(sw) + 6, int(sh) + 6), [(a + 3, b + 3) for a, b in pts],
                                                      3.2 * u, col), sx0 - 3, sy0 - 3))
            for img, sx, sy in sprites:
                out.append((prim.alpha(img, al) if al < 0.999 else img, sx, sy + dy))
        return out


# ---------------------------------------------------------------------------
# Versus metric (two columns)
# ---------------------------------------------------------------------------

@element("versus")
class Versus(El):
    """params: x, y, w, h, a, b (values), a_name, b_name, a_color, b_color,
    winner (a|b|None), t, dur, format, text, muted, accent, font, value_font."""

    def sprites(self, c):
        p = self.p
        x, y, w, h = float(p["x"]), float(p["y"]), float(p["w"]), float(p["h"])
        u = self.u
        av, bv = float(p.get("a") or 0), float(p.get("b") or 0)
        t0, dur = float(p.get("t", 0)), float(p.get("dur", 0.8))
        pr = E("counter", (c - t0) / dur)
        fmt = p.get("format") or {}
        text, muted = p.get("text", "#FFFFFF"), p.get("muted", "#9AA5B1")
        lf, vf = p.get("font", "Inter"), p.get("value_font", "Inter")
        vmax = max(abs(av), abs(bv), 1e-9)
        name_band = 70 * u
        value_band = 110 * u
        base_y = y + h - name_band
        span = base_y - (y + value_band)
        colw = w * 0.3
        centers = (x + w * 0.27, x + w * 0.73)
        out = []
        out.append((prim.rect(w * E("decel", (c - t0 + 0.3) / 0.3), max(2, 3 * u), prim.with_a(prim.rgba(muted), 0.6)),
                    x, base_y))
        winner = p.get("winner")
        for side, v, name, col, cx in (("a", av, p.get("a_name", "A"), p.get("a_color", "#FFD166"), centers[0]),
                                       ("b", bv, p.get("b_name", "B"), p.get("b_color", "#4CC9F0"), centers[1])):
            bh = span * max(0.0, v) / vmax * pr
            if bh >= 1:
                img = _col(colw, bh, col, 12 * u)
                bx, by = cx - colw / 2, base_y - bh
                if winner == side:
                    wp = c - (t0 + dur)
                    if wp > 0:
                        pulse = 1.0 + 0.04 * math.sin(min(1.0, wp / 0.5) * math.pi)
                        ring = prim.frame_rect(colw + 12 * u, bh + 12 * u, p.get("accent", "#FFFFFF"), 4 * u, 14 * u)
                        out.append((prim.alpha(ring, min(1.0, wp / 0.25)), bx - 6 * u, by - 6 * u))
                        if abs(pulse - 1) > 0.002:
                            img2 = prim.scaled(img, pulse)
                            bx -= (img2.width - img.width) / 2
                            by -= img2.height - img.height
                            img = img2
                out.append((img, bx, by))
            vs = fmt_value(v * pr, fmt)
            vsize = min(72 * u, colw / max(3, len(vs)) * 1.8)
            _text(out, vs, vf, 900, vsize, text, cx, base_y - bh - 22 * u, "center", alpha=min(1.0, pr * 3))
            nm, ns = _fit_text(str(name), lf, 700, 34 * u, colw * 1.4)
            _text(out, nm, lf, 700, ns, muted if winner and winner != side else text, cx, base_y + 50 * u, "center")
        a, dy = self.out_state(c)
        if a < 0.999 or dy:
            out = [(prim.alpha(i, a), xx, yy + dy) for i, xx, yy in out]
        return out
