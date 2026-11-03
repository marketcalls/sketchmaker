"""Style-aware layout kit: turns a Look and a Frame into element dicts.

Template builders call these instead of hard-coding fonts, colors or
animation numbers, so the five styles (and brand kits) change the type
pairing, the kicker treatment, the cards, the emphasis treatment and the
text animation family consistently across all templates.
"""

from __future__ import annotations

import re
from typing import Optional

from app.render.colors import readable_on

from .design import Frame, Look, hex_of, mix, readable
from .gfx import prim

PUNCT = re.compile(r"[^\w%$.]+", re.U)


def _norm(w: str) -> str:
    return PUNCT.sub("", (w or "").lower())


class Kit:
    def __init__(self, fr: Frame, look: Look):
        self.fr = fr
        self.look = look
        self.st = look.style
        self.p = look.p
        self.u = fr.u
        # The current scene's spoken words in content seconds (set by build()).
        self.vo_words: Optional[list[dict]] = None

    def spoken_times(self, text: str) -> Optional[list[Optional[float]]]:
        """Entry time per word of ``text`` taken from the narration: each word
        starts rising 0.05 s before it is said. None unless most words of the
        text are actually spoken in this scene, in order (an on-screen line
        that paraphrases the voice keeps its own animation)."""
        words = self.vo_words
        # Sentence stops differ between the script and the screen ("phones."
        # vs "phones"); decimals like 99.2 keep their point.
        toks = [_norm(t).rstrip(".") for t in (text or "").split()]
        if not words or not toks:
            return None
        spoken = [_norm(w.get("text", "")).rstrip(".") for w in words]
        times: list[Optional[float]] = [None] * len(toks)
        j = matched = 0
        for i, tk in enumerate(toks):
            if not tk:
                continue
            for jj in range(j, min(len(spoken), j + 12)):
                if spoken[jj] == tk:
                    times[i] = round(max(0.0, float(words[jj]["start"]) - 0.05), 3)
                    j = jj + 1
                    matched += 1
                    break
        if matched < max(1, int(round(len([t for t in toks if t]) * 0.6))):
            return None
        first = next(x for x in times if x is not None)
        last = None
        for i, x in enumerate(times):
            if x is None:
                times[i] = first if last is None else round(last + 0.06, 3)
            else:
                last = x
        for i in range(1, len(times)):
            times[i] = max(times[i], times[i - 1])
        return times

    # --- colors -------------------------------------------------------------
    @property
    def text(self) -> str:
        return self.p.text

    @property
    def muted(self) -> str:
        return self.p.muted

    @property
    def accent(self) -> str:
        return self.p.accent

    def on_accent(self) -> str:
        return hex_of(readable_on(prim.rgba(self.p.accent)))

    # --- animation presets -----------------------------------------------------
    def text_anim(self, kind: Optional[str] = None, t: float = 0.0, n_words: int = 1) -> dict:
        k = kind or self.st.text_anim
        L = self.look
        base = {
            "mask_up": {"dur": 0.32, "stagger": 0.08, "ease": "snap"},
            "slide_mask": {"dur": 0.36, "stagger": 0.07, "ease": "decel"},
            "slam": {"dur": 0.22, "stagger": 0.1, "ease": "snap", "slam_from": L.intensity.slam},
            "blur_in": {"dur": 0.5, "stagger": 0.07, "ease": "decel"},
            "fade_up": {"dur": 0.3, "stagger": 0.06, "ease": "decel"},
            "weight_morph": {"dur": 0.3, "stagger": 0.08, "ease": "smooth"},
            "typewriter": {"dur": 0.05, "stagger": 0.035, "ease": "linear"},
            "pop": {"dur": 0.35, "stagger": 0.08, "ease": "overshoot"},
            "none": {"dur": 0.01, "stagger": 0.0, "ease": "linear"},
        }.get(k, {"dur": 0.3, "stagger": 0.08, "ease": "snap"})
        stagger = base["stagger"] * L.intensity.time
        if n_words > 1 and k != "typewriter":
            stagger = min(stagger, 0.6 / (n_words - 1))  # cap a group's stagger at 600 ms
        out = {"type": k, "t": t, "dur": L.t(base["dur"]), "stagger": stagger, "ease": base["ease"]}
        if "slam_from" in base:
            out["slam_from"] = base["slam_from"]
        return out

    def emph_indices(self, text: str, words: Optional[str | list] = None, auto: bool = False) -> list[int]:
        toks = (text or "").split()
        if words:
            wanted = {_norm(w) for w in (words.split() if isinstance(words, str) else words) if _norm(w)}
            return [i for i, t in enumerate(toks) if _norm(t) in wanted]
        if not auto or len(toks) < 3:
            return []
        for i, t in enumerate(toks):
            if any(ch.isdigit() for ch in t):
                return [i]
        rng = self.look.rng(text)
        long = [i for i, t in enumerate(toks) if len(_norm(t)) >= 5]
        return [rng.choice(long)] if long else []

    # --- text ---------------------------------------------------------------
    def headline(self, text: str, x: float, y: float, w: float, h: float, *, token: str = "h1", t: float = 0.0,
                 emph: Optional[list[int]] = None, align: Optional[str] = None, valign: str = "top",
                 color: Optional[str] = None, anim: Optional[str] = None, max_lines: int = 4,
                 size: Optional[float] = None, font: Optional[str] = None, weight: Optional[int] = None,
                 emph_scale: float = 1.0, z: int = 10, out: Optional[dict] = None, times=None) -> dict:
        st = self.st
        n = len((text or "").split())
        an = self.text_anim(anim, t, n)
        if times is None and anim != "none":
            times = self.spoken_times(text)
        if times:
            an["times"] = times
        estyle = st.emphasis
        d = {
            "type": "text", "text": text, "x": x, "y": y, "w": w, "h": h, "z": z,
            "align": align or st.align, "valign": valign,
            "font": font or st.display_font, "weight": weight or st.display_weight,
            "size": size or self.fr.type(token), "min_size": max(self.fr.type("meta"), (size or self.fr.type(token)) * 0.42),
            "lh": st.line_height, "tracking": st.display_tracking, "upper": st.display_upper,
            "color": color or self.text, "max_lines": max_lines, "anim": an,
            "emph": emph or [], "emph_color": self.accent, "emph_style": estyle, "emph_scale": emph_scale,
            "emph_text_color": self.on_accent() if estyle in ("marker", "box") else None,
            "t0": min(t, an["t"]) if not times else min([t] + [x_ for x_ in times if x_ is not None]),
        }
        if out:
            d["out"] = out
        return d

    def body(self, text: str, x: float, y: float, w: float, h: float, *, t: float = 0.0, token: str = "body",
             align: Optional[str] = None, color: Optional[str] = None, valign: str = "top", max_lines: int = 4,
             weight: Optional[int] = None, size: Optional[float] = None, z: int = 10) -> dict:
        n = len((text or "").split())
        an = self.text_anim("fade_up", t, n)
        an["stagger"] = min(an["stagger"], 0.03)
        sz = size or self.fr.type(token)
        return {
            "type": "text", "text": text, "x": x, "y": y, "w": w, "h": h, "z": z, "t0": t,
            "align": align or self.st.align, "valign": valign, "font": self.st.text_font,
            "weight": weight or self.st.text_weight, "size": sz, "min_size": max(self.fr.type("meta") * 0.9, sz * 0.6),
            "lh": 1.22, "tracking": 0.0, "color": color or self.muted, "max_lines": max_lines, "anim": an,
            "mono": False,
        }

    def label_style(self) -> dict:
        st = self.st
        return {"font": st.label_font, "weight": st.label_weight, "upper": st.label_upper,
                "tracking": st.label_tracking, "mono": st.mono_labels}

    def kicker(self, text: str, x: float, y: float, w: float, *, t: float = 0.0, align: Optional[str] = None,
               color: Optional[str] = None, z: int = 12) -> tuple[list[dict], float]:
        """A small label above a headline in the style's treatment. Returns
        (elements, height)."""
        if not (text or "").strip():
            return [], 0.0
        st, u = self.st, self.u
        align = align or st.align
        size = max(self.fr.type("caption") * 0.74, 32 * u)
        lab = self.label_style()
        els: list[dict] = []
        sid = st.id
        cap = size * 0.72
        if sid == "brutalist_mono":
            anchor = "top_left" if align == "left" else "top"
            bx = x if align == "left" else x + w / 2
            els.append({"type": "badge", "text": text, "x": bx, "y": y, "anchor": anchor, "z": z,
                        "font": lab["font"], "weight": 700, "size": size, "color": self.on_accent(), "bg": self.accent,
                        "radius": 0, "upper": True, "mono": True, "padx": size * 0.5, "pady": size * 0.35,
                        "anim": {"type": "none", "t": t}, "t0": t})
            return els, cap + size * 0.7
        if sid == "soft_gradient":
            anchor = "top_left" if align == "left" else "top"
            bx = x if align == "left" else x + w / 2
            els.append({"type": "badge", "text": text, "x": bx, "y": y, "anchor": anchor, "z": z,
                        "font": lab["font"], "weight": 600, "size": size, "color": self.text,
                        "bg": "rgba(255,255,255,0.14)", "border": "rgba(255,255,255,0.35)", "border_w": 1.5 * u,
                        "anim": {"type": "fade", "t": t, "dur": 0.4}, "t0": t})
            return els, cap + size * 0.84
        if sid == "newsprint":
            rule_w = w
            els.append({"type": "shape", "x": x, "y": y, "w": rule_w, "h": max(2, 2 * u), "color": self.text, "z": z,
                        "anim": {"type": "grow_x", "t": t, "dur": 0.4, "origin": "center"}, "t0": t})
            els.append({"type": "shape", "x": x, "y": y + 6 * u, "w": rule_w, "h": max(1, 1 * u), "color": self.text,
                        "z": z, "anim": {"type": "grow_x", "t": t + 0.05, "dur": 0.4, "origin": "center"}, "t0": t})
            els.append({**self._label_text(text, x, y + 22 * u, w, size, align, color or self.text, t, z), "align": "center"})
            els.append({"type": "shape", "x": x, "y": y + 22 * u + size * 1.2, "w": rule_w, "h": max(1, 1 * u),
                        "color": self.text, "z": z, "anim": {"type": "grow_x", "t": t + 0.1, "dur": 0.4,
                                                              "origin": "center"}, "t0": t})
            return els, 22 * u + size * 1.2 + 4 * u
        if sid == "dark_tech":
            # Small tracked label in the accent, like a chapter mark.
            els.append(self._label_text(text, x, y, w, size, align, color or self.accent, t, z))
            return els, cap + 4 * u
        if sid == "editorial_serif":
            rule_w = 56 * u
            if align == "left":
                els.append({"type": "shape", "x": x, "y": y + cap / 2, "w": rule_w, "h": max(2, 2 * u),
                            "color": self.accent, "z": z, "anim": {"type": "grow_x", "t": t, "dur": 0.4}, "t0": t})
                els.append(self._label_text(text, x + rule_w + 18 * u, y, w - rule_w - 18 * u, size, "left",
                                            color or self.accent, t + 0.1, z))
            else:
                els.append(self._label_text(text, x, y, w, size, "center", color or self.accent, t, z))
            return els, cap + 4 * u
        # swiss_grid: accent square plus bold label
        sq = cap * 0.95
        if align == "left":
            els.append({"type": "shape", "x": x, "y": y, "w": sq, "h": sq, "color": self.accent, "z": z,
                        "anim": {"type": "scale", "t": t, "dur": 0.25}, "t0": t})
            els.append(self._label_text(text, x + sq + 16 * u, y, w - sq - 16 * u, size, "left", color or self.text,
                                        t + 0.05, z))
        else:
            els.append(self._label_text(text, x, y, w, size, "center", color or self.text, t, z))
        return els, cap + 4 * u

    def _label_text(self, text, x, y, w, size, align, color, t, z) -> dict:
        lab = self.label_style()
        return {"type": "text", "text": text, "x": x, "y": y, "w": w, "h": size * 1.4, "z": z, "t0": t,
                "align": align, "valign": "top", "font": lab["font"], "weight": lab["weight"], "size": size,
                "min_size": size * 0.7, "lh": 1.0, "tracking": lab["tracking"], "upper": lab["upper"],
                "mono": lab["mono"], "color": color, "max_lines": 1, "balance": False,
                "anim": {"type": "typewriter" if lab["mono"] else "fade_up", "t": t,
                         "dur": 0.3 if not lab["mono"] else 0.05, "stagger": 0.03 if lab["mono"] else 0.04,
                         "ease": "decel"}}

    def meta(self, text: str, x: float, y: float, w: float, *, t: float = 0.0, align: Optional[str] = None,
             color: Optional[str] = None, z: int = 14, valign: str = "top") -> dict:
        size = max(self.fr.type("meta") * 0.85, 30 * self.u)
        return {"type": "text", "text": text, "x": x, "y": y, "w": w, "h": size * 2.6, "z": z, "t0": t,
                "align": align or self.st.align, "valign": valign, "font": self.st.text_font, "weight": 500,
                "size": size, "min_size": size * 0.85, "lh": 1.2, "color": color or self.muted, "max_lines": 2,
                "mono": self.st.mono_labels, "upper": False,
                "anim": {"type": "fade_up", "t": t, "dur": 0.3, "stagger": 0.0, "ease": "decel", "dist": 10}}

    def source_line(self, source: Optional[str], *, t: float = 0.3) -> list[dict]:
        if not (source or "").strip():
            return []
        l, top, r, b = self.fr.content
        size = max(self.fr.type("meta") * 0.85, 30 * self.u)
        return [self.meta(f"Source: {source.strip()}", l, b - size * 1.3, r - l, t=t, valign="top")]

    # --- numbers --------------------------------------------------------------
    def number(self, value: float, x: float, y: float, w: float, h: float, *, t: float = 0.2, dur: float = 1.5,
               decimals: int = 0, prefix: str = "", suffix: str = "", align: Optional[str] = None,
               size: Optional[float] = None, color: Optional[str] = None, mode: str = "roll", z: int = 10) -> dict:
        st = self.st
        return {"type": "odometer", "value": value, "decimals": decimals, "prefix": prefix, "suffix": suffix,
                "x": x, "y": y, "w": w, "h": h, "z": z, "align": align or st.align, "valign": "center",
                "font": st.numeric_font, "weight": st.numeric_weight, "size": size or self.fr.type("numeric"),
                "color": color or self.accent, "suffix_color": color or self.accent, "t": t, "t0": t,
                "dur": self.look.t(dur), "stagger": 0.04, "mode": mode,
                "pop": {"from": 0.92, "dur": self.look.t(0.4), "ease": self.look.ease_pop()},
                "tracking": -0.02, "suffix_scale": 0.42 if len(suffix) <= 2 else 0.3}

    # --- surfaces -------------------------------------------------------------
    def card(self, x: float, y: float, w: float, h: float, *, t: float = 0.0, z: int = 4) -> list[dict]:
        st, u = self.st, self.u
        kind = st.card
        an = {"type": "fade", "t": t, "dur": 0.35}
        if kind == "fill":
            return [{"type": "shape", "x": x, "y": y, "w": w, "h": h, "color": self.p.surface, "radius": st.radius * u,
                     "z": z, "anim": {"type": "grow_y", "t": t, "dur": 0.35, "ease": "decel", "origin": "bottom"},
                     "t0": t}]
        if kind == "glass":
            return [{"type": "shape", "x": x, "y": y, "w": w, "h": h, "color": "rgba(255,255,255,0.10)",
                     "radius": st.radius * u, "z": z, "anim": an, "t0": t},
                    {"type": "shape", "shape": "frame", "x": x, "y": y, "w": w, "h": h,
                     "color": "rgba(255,255,255,0.28)", "stroke": 1.5 * u, "radius": st.radius * u, "z": z + 1,
                     "anim": an, "t0": t}]
        if kind == "heavy":
            off = 12 * u
            return [{"type": "shape", "x": x + off, "y": y + off, "w": w, "h": h, "color": self.accent, "z": z,
                     "anim": {"type": "none", "t": t}, "t0": t},
                    {"type": "shape", "x": x, "y": y, "w": w, "h": h, "color": self.p.surface, "z": z + 1,
                     "anim": {"type": "none", "t": t}, "t0": t},
                    {"type": "shape", "shape": "frame", "x": x, "y": y, "w": w, "h": h, "color": self.text,
                     "stroke": st.border * u, "z": z + 2, "anim": {"type": "none", "t": t}, "t0": t}]
        if kind == "outline":
            return [{"type": "shape", "shape": "frame", "x": x, "y": y, "w": w, "h": h, "color": self.text,
                     "stroke": max(1.5, st.border * u), "z": z, "anim": an, "t0": t}]
        if kind == "panel":
            rise = {"type": "fade", "t": t, "dur": 0.4}
            return [{"type": "shape", "x": x, "y": y, "w": w, "h": h, "color": self.p.surface,
                     "radius": st.radius * u, "z": z, "anim": rise, "t0": t},
                    {"type": "shape", "shape": "frame", "x": x, "y": y, "w": w, "h": h, "color": self.p.rule,
                     "stroke": max(1.5, st.border * u), "radius": st.radius * u, "z": z + 1, "anim": rise, "t0": t}]
        return []

    def card_fill(self) -> dict:
        """Tile card params for chart elements."""
        st, u = self.st, self.u
        if st.card == "glass":
            return {"fill": "rgba(255,255,255,0.10)", "border": "rgba(255,255,255,0.28)", "border_w": 1.5 * u,
                    "radius": st.radius * u}
        if st.card == "heavy":
            return {"fill": self.p.surface, "border": self.text, "border_w": 4 * u, "radius": 0}
        if st.card == "outline":
            return {"fill": None, "border": self.text, "border_w": 2 * u, "radius": 0}
        if st.card == "fill":
            return {"fill": self.p.surface, "border": None, "radius": st.radius * u}
        if st.card == "panel":
            return {"fill": self.p.surface, "border": self.p.rule, "border_w": max(1.5, st.border * u),
                    "radius": st.radius * u}
        return {"fill": mix(self.p.bg, self.p.text, 0.06), "border": mix(self.p.bg, self.p.text, 0.2),
                "border_w": 1.5 * u, "radius": 4 * u}

    def rule(self, x: float, y: float, w: float, *, t: float = 0.0, color: Optional[str] = None,
             thick: Optional[float] = None, origin: str = "left", z: int = 6) -> dict:
        return {"type": "shape", "x": x, "y": y, "w": w, "h": thick or max(2, 3 * self.u),
                "color": color or self.accent, "z": z, "t0": t,
                "anim": {"type": "grow_x", "t": t, "dur": self.look.t(0.5), "ease": "smooth", "origin": origin}}

    def text_color_on(self, bg: str) -> str:
        return readable(self.text, bg)

    @property
    def data_font(self) -> str:
        """Figures in tables and charts: lining digits (the serif display faces
        default to old-style figures, which read poorly in data)."""
        return self.st.text_font if self.st.numeric_font == "Playfair Display" else self.st.numeric_font

    def chart_style(self) -> dict:
        st = self.st
        return {"text": self.text, "muted": self.muted, "rule": self.p.rule, "accent": self.accent,
                "font": st.text_font, "value_font": self.data_font}
