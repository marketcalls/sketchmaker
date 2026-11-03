"""Special elements: timeline track with a camera, audiogram waveform,
device frame with a camera push and callout, and a cursor with a click."""

from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw

from ..design import E
from . import prim
from .elements import KText
from .ext import El, element


def _block(sc, params: dict):
    """Static sprite of a text block (KText laid out, no animation)."""
    kt = KText({**params, "anim": {"type": "none"}}, sc)
    spr = kt._static_block()
    return spr[0] if spr else None


# ---------------------------------------------------------------------------
# Timeline track
# ---------------------------------------------------------------------------

@element("timeline_track")
class TimelineTrack(El):
    """A track larger than the frame with a camera that moves milestone to
    milestone (700 ms E.camera moves); the track line draws ahead of the
    camera.

    params: x, y, w, h (viewport), items [{date, title, desc, src}],
    orientation h|v, t, per (seconds per milestone), move, text, muted,
    accent, rule, date_font, date_weight, title_font, title_weight,
    desc_font, upper_dates.
    """

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self._blocks = {}

    def _cam(self, c: float, n: int) -> float:
        t, per = float(self.p.get("t", 0)), float(self.p.get("per", 3.5))
        move = float(self.p.get("move", 0.7))
        k = int(math.floor((c - t) / per)) if c >= t else 0
        k = max(0, min(n - 1, k))
        if k == 0:
            return 0.0
        seg = E("camera", (c - (t + k * per)) / move)
        return (k - 1) + seg

    def _item_blocks(self, i: int, it: dict, wtxt: float):
        if i in self._blocks:
            return self._blocks[i]
        p = self.p
        u = self.u
        date = _block(self.sc, {"text": str(it.get("date", "")), "x": 0, "y": 0, "w": wtxt, "h": 400 * u,
                                "font": p.get("date_font", "Inter"), "weight": int(p.get("date_weight", 900)),
                                "size": float(p.get("date_size", 150 * u)), "color": p.get("accent", "#FFD166"),
                                "lh": 0.95, "tracking": -0.03, "max_lines": 1, "min_size": 60 * u})
        title = _block(self.sc, {"text": str(it.get("title", "")), "x": 0, "y": 0, "w": wtxt, "h": 260 * u,
                                 "font": p.get("title_font", "Inter"), "weight": int(p.get("title_weight", 800)),
                                 "size": float(p.get("title_size", 58 * u)), "color": p.get("text", "#FFFFFF"),
                                 "lh": 1.05, "max_lines": 3, "min_size": 34 * u})
        desc = None
        if it.get("desc"):
            desc = _block(self.sc, {"text": str(it["desc"]), "x": 0, "y": 0, "w": wtxt, "h": 260 * u,
                                    "font": p.get("desc_font", "Inter"), "weight": 500,
                                    "size": float(p.get("desc_size", 36 * u)), "color": p.get("muted", "#9AA5B1"),
                                    "lh": 1.25, "max_lines": 4, "min_size": 26 * u})
        img = None
        if it.get("src"):
            src = prim.load_rgba(it["src"])
            if src is not None:
                from PIL import ImageOps

                side = int(wtxt * 0.62)
                img = ImageOps.fit(src, (side, int(side * 0.62)), Image.Resampling.LANCZOS)
                from PIL import ImageChops

                from app.render.draw import rounded_mask

                img.putalpha(ImageChops.multiply(img.getchannel("A"), rounded_mask(img.width, img.height, 18 * u)))
        self._blocks[i] = (date, title, desc, img)
        return self._blocks[i]

    def sprites(self, c):
        p = self.p
        items = list(p.get("items") or [])
        n = len(items)
        if n == 0:
            return []
        x, y, w, h = float(p["x"]), float(p["y"]), float(p["w"]), float(p["h"])
        u = self.u
        vertical = p.get("orientation", "h") == "v"
        t, per = float(p.get("t", 0)), float(p.get("per", 3.5))
        cam = self._cam(c, n)
        accent = p.get("accent", "#FFD166")
        rule = prim.rgba(p.get("rule", "#FFFFFF"))
        out = []
        lw = max(3.0, 5 * u)
        intro = E("decel", (c - t + 0.4) / 0.4)
        if vertical:
            spacing = h * 0.42
            track_x = x + 26 * u
            anchor_y = y + h * 0.34
            pos = lambda k: anchor_y + (k - cam) * spacing  # noqa: E731
            head = pos(min(n - 1, cam + 0.85))
            top = pos(0) - 40 * u
            line_len = max(0.0, (head - top)) * intro
            out.append((prim.rect(lw, max(1.0, line_len), accent), track_x - lw / 2, top))
            rest = prim.rect(lw * 0.5, max(1.0, pos(n - 1) + spacing * 0.5 - top), prim.with_a(rule, 0.18))
            out.insert(0, (rest, track_x - lw * 0.25, top))
            wtxt = w - 90 * u
        else:
            spacing = w * 0.46
            track_y = y + h * 0.47
            anchor_x = x + w * 0.3
            pos = lambda k: anchor_x + (k - cam) * spacing  # noqa: E731
            head = pos(min(n - 1, cam + 0.85))
            left = pos(0) - 60 * u
            line_len = max(0.0, head - left) * intro
            rest = prim.rect(max(1.0, pos(n - 1) + spacing - left), lw * 0.5, prim.with_a(rule, 0.18))
            out.append((rest, left, track_y - lw * 0.25))
            out.append((prim.rect(max(1.0, line_len), lw, accent), left, track_y - lw / 2))
            wtxt = spacing * 0.86
        d_dot = 30 * u
        for k in range(n):
            # upcoming milestones show as hollow markers on the track
            kp = pos(k)
            if vertical:
                out.append((prim.ring(d_dot, 3 * u, prim.with_a(rule, 0.5 * intro)), track_x - d_dot / 2, kp - d_dot / 2))
            else:
                out.append((prim.ring(d_dot, 3 * u, prim.with_a(rule, 0.5 * intro)), kp - d_dot / 2, track_y - d_dot / 2))
        for k, it in enumerate(items):
            arrive = t + k * per + (float(p.get("move", 0.7)) * 0.55 if k else 0.0)
            ap = E("snap", (c - arrive) / 0.45)
            if ap <= 0:
                continue
            active = abs(cam - k) < 0.5
            dim = 1.0 if active or k == n - 1 and cam >= n - 1.5 else 0.42
            date, title, desc, img = self._item_blocks(k, it, wtxt)
            d = 30 * u
            if vertical:
                cy = pos(k)
                if cy < y - h * 0.6 or cy > y + h * 1.4:
                    continue
                out.append((prim.circle(d, accent), track_x - d / 2, cy - d / 2))
                tx = track_x + 56 * u
                yy = cy - 30 * u
                for blk in (date, title, desc):
                    if blk is None:
                        continue
                    bimg, bx, by = blk
                    out.append((prim.alpha(bimg, ap * dim), tx + bx, yy + (1 - ap) * 40 * u))
                    yy += bimg.height + 14 * u
                if img is not None:
                    out.append((prim.alpha(img, ap * dim), tx, yy + 10 * u))
            else:
                cx = pos(k)
                if cx < x - w or cx > x + w * 2:
                    continue
                out.append((prim.circle(d, accent), cx - d / 2, track_y - d / 2))
                if date is not None:
                    bimg, bx, by = date
                    out.append((prim.alpha(bimg, ap * dim), cx + bx, track_y - 40 * u - bimg.height + (1 - ap) * 50 * u))
                yy = track_y + 46 * u
                for blk in (title, desc):
                    if blk is None:
                        continue
                    bimg, bx, by = blk
                    out.append((prim.alpha(bimg, ap * dim), cx + bx, yy + (1 - ap) * 30 * u))
                    yy += bimg.height + 16 * u
                if img is not None and date is not None:
                    pass
        a, dy = self.out_state(c)
        if a < 0.999 or dy:
            out = [(prim.alpha(i, a), xx, yy + dy) for i, xx, yy in out]
        return out


# ---------------------------------------------------------------------------
# Waveform
# ---------------------------------------------------------------------------

@element("waveform")
class Waveform(El):
    """params: x, y, w, h, amps (per frame values 0..1 at 30 fps), offset
    (global seconds at content time 0), bars, color, color2, gap, style
    mirror|up, seed."""

    def sprites(self, c):
        p = self.p
        x, y, w, h = float(p["x"]), float(p["y"]), float(p["w"]), float(p["h"])
        n = int(p.get("bars", 48))
        amps = p.get("amps") or []
        gt = float(p.get("offset", 0.0)) + c
        idx = int(gt * 30)
        rnd = random.Random(int(p.get("seed", 7)))
        jit = [0.72 + 0.28 * rnd.random() for _ in range(n)]
        slot = w / n
        bw = max(2.0, slot * (1 - float(p.get("gap", 0.38))))
        col = p.get("color", "#FFD166")
        col2 = p.get("color2", col)
        mid = (n - 1) / 2.0
        canvas = Image.new("RGBA", (int(math.ceil(w)) + 2, int(math.ceil(h)) + 2), (0, 0, 0, 0))

        def amp(k: int) -> float:
            if amps:
                k = max(0, min(len(amps) - 1, k))
                return float(amps[k])
            # synthetic speech-like envelope for previews without audio
            tt = k / 30.0
            return max(0.0, 0.45 + 0.3 * math.sin(tt * 7.1) * math.sin(tt * 2.3 + 1) + 0.15 * math.sin(tt * 17.0))

        intro = E("decel", c / 0.4)
        for j in range(n):
            d = abs(j - mid) / max(1.0, mid)
            a = amp(idx - int(d * 7))
            a = (0.5 * a + 0.3 * amp(idx - int(d * 7) - 1) + 0.2 * amp(idx - int(d * 7) - 2))
            hh = max(bw, h * min(1.0, a * jit[j] * (1.0 - 0.45 * d)) * intro)
            bx = j * slot + (slot - bw) / 2
            cc = col if d < 0.5 else col2
            bar = prim.rect(bw, hh, cc, bw / 2)
            if p.get("style", "mirror") == "mirror":
                canvas.alpha_composite(bar, (int(round(bx)), int(round((h - hh) / 2))))
            else:
                canvas.alpha_composite(bar, (int(round(bx)), int(round(h - hh))))
        a, dy = self.out_state(c)
        if a < 0.999:
            canvas = prim.alpha(canvas, a)
        return [(canvas, x, y + dy)]


# ---------------------------------------------------------------------------
# Device frame with camera push and callout
# ---------------------------------------------------------------------------

@element("device")
class Device(El):
    """params: src, kind browser|phone, x, y, w, h, url, t (enter), push {from,
    to, t, dur, fx, fy}, callout {fx, fy, label, t}, surface, bar, text,
    accent, shadow."""

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self._dev = None

    def _build(self):
        if self._dev is not None:
            return self._dev
        p = self.p
        u = self.u
        w, h = int(p["w"]), int(p["h"])
        kind = p.get("kind", "browser")
        surface = p.get("surface", "#16171C")
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        if kind == "phone":
            radius = w * 0.12
            canvas.alpha_composite(prim.rect(w, h, surface, radius))
            inset = w * 0.04
            cx0, cy0, cw, ch = inset, inset, w - 2 * inset, h - 2 * inset
            inner_r = radius - inset
        else:
            radius = 18 * u
            canvas.alpha_composite(prim.rect(w, h, surface, radius))
            bar_h = 58 * u
            for i, dc in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
                d = 16 * u
                canvas.alpha_composite(prim.circle(d, dc), (int(24 * u + i * 26 * u), int((bar_h - d) / 2)))
            pill_w = w * 0.46
            canvas.alpha_composite(prim.rect(pill_w, 30 * u, p.get("bar", "#26272E"), 15 * u),
                                   (int((w - pill_w) / 2), int((bar_h - 30 * u) / 2)))
            if p.get("url"):
                g = prim.glyph(p["url"], "Inter", 500, 18 * u, p.get("text_muted", "#9AA0AA"))
                if g.img is not None:
                    canvas.alpha_composite(g.img, (int((w - g.adv) / 2 + g.ox), int(bar_h / 2 + 7 * u + g.oy)))
            cx0, cy0, cw, ch = 8 * u, bar_h, w - 16 * u, h - bar_h - 8 * u
            inner_r = radius * 0.6
        shot = prim.load_rgba(p.get("src"))
        cw_i, ch_i = int(cw), int(ch)
        if shot is None:
            shot = Image.new("RGBA", (cw_i, ch_i), prim.rgba(p.get("placeholder", "#2B2D36")))
            g = prim.glyph("Your screenshot", "Inter", 600, 36 * u, "#8A8F9C")
            if g.img is not None:
                shot.alpha_composite(g.img, (int((cw_i - g.adv) / 2 + g.ox), int(ch_i / 2 + g.oy + 12 * u)))
        else:
            from PIL import ImageOps

            shot = ImageOps.fit(shot, (cw_i, ch_i), Image.Resampling.LANCZOS, centering=(0.5, 0.0))
        from PIL import ImageChops

        from app.render.draw import rounded_mask

        shot.putalpha(ImageChops.multiply(shot.getchannel("A"), rounded_mask(cw_i, ch_i, max(0.0, inner_r))))
        canvas.alpha_composite(shot, (int(cx0), int(cy0)))
        self._dev = (canvas, (cx0, cy0, cw, ch))
        return self._dev

    def sprites(self, c):
        p = self.p
        u = self.u
        x, y = float(p["x"]), float(p["y"])
        dev, (cx0, cy0, cw, ch) = self._build()
        t = float(p.get("t", self.t0))
        ep = E("decel", (c - t) / 0.6)
        if ep <= 0:
            return []
        out = []
        push = p.get("push") or {}
        s = 1.0
        fx = cx0 + cw * float(push.get("fx", 0.5))
        fy = cy0 + ch * float(push.get("fy", 0.4))
        if push:
            pp = E("camera", (c - float(push.get("t", t + 0.6))) / float(push.get("dur", 1.2)))
            s = float(push.get("from", 1.0)) + (float(push.get("to", 1.25)) - float(push.get("from", 1.0))) * pp
        # Keep the focus point fixed on screen while zooming; drift it toward the frame center.
        sx_focus = x + fx
        sy_focus = y + fy
        img = dev
        if p.get("shadow", True):
            sh = prim.rect(dev.width, dev.height, (0, 0, 0, 120), 24 * u)
            from PIL import ImageFilter

            pad = int(40 * u)
            canv = Image.new("RGBA", (sh.width + 2 * pad, sh.height + 2 * pad), (0, 0, 0, 0))
            canv.alpha_composite(sh, (pad, pad))
            key = ("shadow", dev.width, dev.height)
            if getattr(self, "_shkey", None) != key:
                self._sh = canv.filter(ImageFilter.GaussianBlur(26 * u))
                self._shkey = key
            sh_img = prim.scaled(self._sh, s, fast=True)
            out.append((prim.alpha(sh_img, ep * 0.9), sx_focus - (fx + pad) * s, sy_focus - (fy + pad) * s + 30 * u * s))
        img = prim.scaled(dev, s, fast=abs(s - 1) > 0.02)
        dx = sx_focus - fx * s
        dy = sy_focus - fy * s + (1 - ep) * 60 * u
        out.append((prim.alpha(img, ep) if ep < 0.999 else img, dx, dy))
        co = p.get("callout")
        if co:
            ct = float(co.get("t", t + 2.0))
            rp = E("snap", (c - ct) / 0.4)
            if rp > 0:
                px = x + (cx0 + cw * float(co.get("fx", 0.5)) - fx) * s + fx
                py = y + (cy0 + ch * float(co.get("fy", 0.5)) - fy) * s + fy
                d = float(co.get("d", 150 * u))
                ring = prim.ring(d, 6 * u, p.get("accent", "#FFD166"), 360 * rp)
                out.append((ring, px - d / 2, py - d / 2))
                if co.get("label"):
                    lp = E("decel", (c - ct - 0.25) / 0.35)
                    if lp > 0:
                        lab = co["label"]
                        size = 34 * u
                        g = prim.glyph(lab, "Inter", 700, size, "#0B0B0F")
                        padx, pady = 22 * u, 14 * u
                        cap = prim.cap_height("Inter", 700, size)
                        bw, bh = g.adv + 2 * padx, cap + 2 * pady
                        box = Image.new("RGBA", (int(bw) + 1, int(bh) + 1), (0, 0, 0, 0))
                        box.alpha_composite(prim.rect(bw, bh, p.get("accent", "#FFD166"), bh / 2))
                        if g.img is not None:
                            box.alpha_composite(g.img, (int(padx + g.ox), int(pady + cap + g.oy)))
                        bx = px + d * 0.45
                        if bx + bw > self.W - 40 * u:
                            bx = px - d * 0.45 - bw
                        out.append((prim.alpha(box, lp), bx, py - d * 0.5 - bh + (1 - lp) * 16 * u))
        a, dy2 = self.out_state(c)
        if a < 0.999 or dy2:
            out = [(prim.alpha(i, a), xx, yy + dy2) for i, xx, yy in out]
        return out


@element("cursor")
class Cursor(El):
    """An arrow cursor travelling along a quadratic bezier with a click
    ripple. params: x0, y0, x1, y1, t, dur, color, size."""

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self._arrow = None

    def _make(self, size, color):
        s = int(size)
        big = Image.new("L", (s * 3, int(s * 1.5) * 3), 0)
        pts = [(0, 0), (0, s * 1.3), (s * 0.36, s * 1.0), (s * 0.62, s * 1.48), (s * 0.82, s * 1.38), (s * 0.58, s * 0.92),
               (s * 1.0, s * 0.9)]
        ImageDraw.Draw(big).polygon([(a * 3, b * 3) for a, b in pts], fill=255)
        from app.render.draw import colorize

        m = big.resize((s, int(s * 1.5)), Image.Resampling.BOX)
        outline = colorize(m, prim.rgba("#0B0B0F"))
        inner = m.resize((max(1, int(s * 0.8)), max(1, int(s * 1.2))), Image.Resampling.BOX)
        fill = colorize(inner, prim.rgba(color))
        outline.alpha_composite(fill, (int(s * 0.07), int(s * 0.16)))
        return outline

    def sprites(self, c):
        p = self.p
        u = self.u
        t, dur = float(p.get("t", 0)), float(p.get("dur", 1.0))
        if c < t - 0.3:
            return []
        size = float(p.get("size", 44 * u))
        if self._arrow is None:
            self._arrow = self._make(size, p.get("color", "#FFFFFF"))
        q = E("smooth", (c - t) / dur)
        x0, y0, x1, y1 = (float(p[k]) for k in ("x0", "y0", "x1", "y1"))
        mx, my = (x0 + x1) / 2 + (y1 - y0) * 0.25, (y0 + y1) / 2 - (x1 - x0) * 0.25
        bx = (1 - q) ** 2 * x0 + 2 * (1 - q) * q * mx + q * q * x1
        by = (1 - q) ** 2 * y0 + 2 * (1 - q) * q * my + q * q * y1
        out = []
        rp = (c - t - dur) / 0.25
        if 0 < rp < 1.6:
            d = 30 * u + 90 * u * E("decel", rp)
            out.append((prim.alpha(prim.ring(d, 4 * u, p.get("color", "#FFFFFF")), max(0.0, 1 - rp / 1.6)), x1 - d / 2, y1 - d / 2))
        press = 0.88 if 0 < rp < 0.5 else 1.0
        img = prim.scaled(self._arrow, press)
        a = E("decel", (c - t + 0.3) / 0.3)
        out.append((prim.alpha(img, a), bx, by))
        return out


@element("live_caption")
class LiveCaption(El):
    """One line of word-by-word captions with the current word in accent.

    params: words [{text, start, end}] (content seconds), x, y, w, max_chars,
    font, weight, size, color, accent, align, upper."""

    def __init__(self, p, sc):
        super().__init__(p, sc)
        self._groups = None

    def groups(self):
        if self._groups is not None:
            return self._groups
        words = [w for w in self.p.get("words") or [] if str(w.get("text", "")).strip()]
        mx = int(self.p.get("max_chars", 24))
        groups, cur, n = [], [], 0
        for w in words:
            t = str(w["text"]).strip()
            gap = (float(w["start"]) - float(cur[-1]["end"])) if cur else 0.0
            if cur and (n + 1 + len(t) > mx or gap > 0.6 or str(cur[-1]["text"]).rstrip().endswith((".", "?", "!"))):
                groups.append(cur)
                cur, n = [], 0
            cur.append(w)
            n += len(t) + (1 if n else 0)
        if cur:
            groups.append(cur)
        self._groups = groups
        return groups

    def sprites(self, c):
        p = self.p
        gs = self.groups()
        if not gs:
            return []
        gi = None
        for i, g in enumerate(gs):
            end = float(gs[i + 1][0]["start"]) if i + 1 < len(gs) else float(g[-1]["end"]) + 0.6
            if float(g[0]["start"]) - 0.05 <= c < end:
                gi = i
                break
        if gi is None:
            return []
        g = gs[gi]
        fam, wt, size = p.get("font", "Inter"), int(p.get("weight", 800)), float(p.get("size", 64))
        color, accent = p.get("color", "#FFFFFF"), p.get("accent", "#FFD166")
        upper = bool(p.get("upper", False))
        texts = [(str(w["text"]).upper() if upper else str(w["text"])) for w in g]
        space = prim.measure(" ", fam, wt, size)
        widths = [prim.measure(t, fam, wt, size) for t in texts]
        total = sum(widths) + space * (len(texts) - 1)
        maxw = float(p.get("w", self.W))
        if total > maxw:
            size *= maxw / total
            space = prim.measure(" ", fam, wt, size)
            widths = [prim.measure(t, fam, wt, size) for t in texts]
            total = sum(widths) + space * (len(texts) - 1)
        x0 = float(p.get("x", 0))
        align = p.get("align", "center")
        if align == "center":
            x0 += (maxw - total) / 2
        elif align == "right":
            x0 += maxw - total
        base = float(p.get("y", 0))
        out = []
        xx = x0
        appear = E("decel", (c - float(g[0]["start"]) + 0.05) / 0.15)
        for w, t, wd in zip(g, texts, widths):
            active = float(w["start"]) <= c < float(w["end"]) + 0.05
            spoken = c >= float(w["start"])
            col = accent if active else (color if spoken else prim.with_a(prim.rgba(color), 0.55))
            gl = prim.glyph(t, fam, wt, size, col)
            if gl.img is not None:
                img = gl.img if appear >= 0.999 else prim.alpha(gl.img, appear)
                out.append((img, xx + gl.ox, base + gl.oy + (1 - appear) * 10 * self.u))
            xx += wd + space
        return out
