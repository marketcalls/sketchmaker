"""Scene builders: spec scenes -> motion graphics elements, per template.

Each builder receives the scene, the build context and the scene's content
duration D (seconds) and returns a SceneOut (elements with content times,
an optional camera drift and sound cues). Layout reflows per aspect: the
builders read the Frame's content rect and orientation and switch between
stacked (9:16, 4:5), centered (1:1) and column (16:9) compositions instead
of cropping one layout.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Callable, Optional

from .design import Frame, Look, accent_on, hold_seconds, mix, readable
from .gfx.elements import KText, Odometer
from .kit import Kit
from .spec import Scene, Spec, Template


@dataclass
class SceneOut:
    elements: list[dict]
    camera: Optional[dict] = None
    sfx: list[tuple[float, str]] = field(default_factory=list)
    transition: Optional[str] = None  # override the style's transition into this scene


@dataclass
class BuildCtx:
    spec: Spec
    tpl: Template
    fr: Frame
    look: Look
    kit: Kit
    data: Optional[dict]
    files: dict  # upload id -> local path
    vo: dict  # scene id -> [{text, start, end}] in content seconds
    audio: dict  # {"amps": [...], "offset": seconds, "duration": seconds} for audiograms
    starts: dict = field(default_factory=dict)  # scene id -> global start

    def scenes_of(self, t: str) -> list[Scene]:
        return [s for s in self.spec.scenes if s.type == t]

    def image(self, value) -> Optional[str]:
        if isinstance(value, dict):
            uid = value.get("upload_id") or value.get("id")
            return self.files.get(uid) if uid else None
        if isinstance(value, str):
            return self.files.get(value)
        return None


def _fake_sc(fr: Frame):
    return SimpleNamespace(W=fr.W, H=fr.H, u=fr.u, content_dur=10.0, lead_out=0.0)


def text_height(el: dict, fr: Frame) -> float:
    """Height of a text element's laid out block (its box may shrink it)."""
    kt = KText({**el, "anim": {"type": "none"}}, _fake_sc(fr))
    return kt.bounds()[3]


def text_bounds(el: dict, fr: Frame):
    kt = KText({**el, "anim": {"type": "none"}}, _fake_sc(fr))
    return kt.bounds()


def odo_bounds(el: dict, fr: Frame):
    return Odometer(el, _fake_sc(fr)).bounds()


class Stack:
    """Vertical stack of blocks centered (or top or bottom aligned) in a band."""

    def __init__(self):
        self.items: list[tuple[float, Callable[[float], list[dict]], float]] = []

    def add(self, h: float, make: Callable[[float], list[dict]], gap: float = 0.0):
        if h > 0:
            self.items.append((h, make, gap))

    def text(self, el: dict, fr: Frame, gap: float = 0.0):
        h = text_height(el, fr)
        self.add(h, lambda y, el=el, h=h: [{**el, "y": y, "h": h + 4, "valign": "top"}], gap)
        return h

    def height(self) -> float:
        return sum(h + (g if i else 0) for i, (h, _, g) in enumerate(self.items))

    def place(self, top: float, bottom: float, valign: str = "center") -> list[dict]:
        total = self.height()
        if valign == "top":
            y = top
        elif valign == "bottom":
            y = bottom - total
        else:
            y = top + max(0.0, (bottom - top - total) / 2)
        out = []
        for i, (h, make, g) in enumerate(self.items):
            if i:
                y += g
            out.extend(make(y))
            y += h
        return out


def _rect(cx: BuildCtx):
    l, t, r, b = cx.fr.content
    return l, t, r, b, r - l, b - t


def _src_band(cx: BuildCtx) -> float:
    return max(cx.fr.type("meta") * 0.85, 30 * cx.fr.u) * 2.2


def _drift(cx: BuildCtx, scale: float = 1.0) -> dict:
    return {"drift": cx.look.intensity.drift * scale}


def _fmt_from_reveal(cx: BuildCtx) -> dict:
    rv = next((s for s in cx.spec.scenes if s.type == "reveal"), None)
    if rv is None:
        return {}
    sl = rv.slots
    return {"prefix": sl.get("prefix") or "", "suffix": sl.get("unit") or "", "decimals": int(sl.get("decimals") or 0)}


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _logo(cx: BuildCtx, x, y, w, h, t, align="center", z=15) -> list[dict]:
    if not cx.look.logo_path:
        return []
    return [{"type": "logo", "src": cx.look.logo_path, "x": x, "y": y, "w": w, "h": h, "align": align, "z": z,
             "t0": t, "anim": {"type": "pop", "t": t, "dur": cx.look.t(0.45)}}]


# ---------------------------------------------------------------------------
# Durations
# ---------------------------------------------------------------------------

def duration(cx: BuildCtx, scene: Scene, index: int) -> float:
    """Planned content seconds for a scene (without a voiceover)."""
    tpl = cx.tpl
    st = tpl.scene_type(scene.type)
    base = st.default_seconds if st else 3.0
    if scene.duration:
        return max(st.min_seconds if st else 1.0, float(scene.duration))
    sl = scene.slots
    t = scene.type
    if t in ("hook", "line", "payoff", "question", "claim", "takeaway", "cta", "verdict"):
        text = str(sl.get("text") or "")
        base = max(base, 0.6 + hold_seconds(text))
        if t == "payoff":
            base = max(base, 0.7 + hold_seconds(text) + 0.6)
    elif t == "item":
        base = max(base, 1.0 + hold_seconds(str(sl.get("title") or "")) + 0.5 * hold_seconds(str(sl.get("detail") or "")))
        items = cx.scenes_of("item")
        if items and items[-1] is scene:
            base *= 1.5  # number one gets 1.5x time
    elif t == "race":
        v = cx.data or {}
        n = len(v.get("periods") or []) or 2
        pd = cx.spec.data_options.period_seconds or 0.8
        base = 0.8 + (n - 1) * pd + 3.0
    elif t == "track":
        n = len(sl.get("items") or []) or 1
        base = max(base, 0.9 + n * 3.4)
    elif t == "chart":
        base = max(base, 6.5)
    elif t == "clip":
        d = (cx.audio or {}).get("duration")
        if d:
            base = float(d) + 0.4
        else:
            text = str(sl.get("script") or "")
            base = max(4.0, len(text.split()) / 2.6 + 0.6)
    elif t == "disclaimer":
        base = max(3.0, hold_seconds(cx.spec.disclaimer or "") * 0.55)
    elif t == "end_card":
        base = max(base, 0.8 + hold_seconds(str(sl.get("headline") or "")))
    return round(base, 3)


# ---------------------------------------------------------------------------
# Shared scenes
# ---------------------------------------------------------------------------

def b_source_card(cx: BuildCtx, sc: Scene, D: float, i: int) -> SceneOut:
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    align = k.st.align
    st = Stack()
    kick, kh = k.kicker("Source", l, 0, cw, t=0.0, align=align)
    st.add(kh, lambda y: k.kicker("Source", l, y, cw, t=0.0, align=align)[0])
    src = (cx.spec.source or "Source not given").strip()
    st.text(k.headline(src, l, 0, cw, ch * 0.45, token="h2", t=0.15, align=align, anim="fade_up",
                       max_lines=4), fr, gap=34 * fr.u)
    rw = 120 * fr.u
    st.add(4 * fr.u, lambda y: [k.rule(l if align == "left" else l + (cw - rw) / 2, y, rw, t=0.3,
                                       origin="left" if align == "left" else "center")], gap=34 * fr.u)
    note = (sc.slots.get("note") or "").strip()
    if note:
        st.text(k.body(note, l, 0, cw, ch * 0.3, t=0.35, align=align), fr, gap=22 * fr.u)
    els = st.place(t, b)
    return SceneOut(els)


def b_disclaimer(cx: BuildCtx, sc: Scene, D: float, i: int) -> SceneOut:
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    pad = 48 * u
    align = k.st.align
    body = k.body(cx.spec.disclaimer or "", l + pad, 0, cw - 2 * pad, ch * 0.6, t=0.2, align=align,
                  color=k.text, token="body", max_lines=8)
    bh = text_height(body, fr)
    kh = 60 * u
    total = kh + bh + 2 * pad + 20 * u
    y0 = t + max(0.0, (ch - total) / 2)
    els = k.card(l, y0, cw, total, t=0.0)
    els += k.kicker("Important", l + pad, y0 + pad, cw - 2 * pad, t=0.1, align=align)[0]
    els.append({**body, "y": y0 + pad + kh + 20 * u, "h": bh + 4})
    return SceneOut(els, transition="fade")


def b_end_card(cx: BuildCtx, sc: Scene, D: float, i: int) -> SceneOut:
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    sl = sc.slots
    st = Stack()
    align = "center" if k.st.align == "center" or fr.landscape else k.st.align
    if cx.look.logo_path:
        lh = 120 * u
        st.add(lh, lambda y: _logo(cx, l, y, cw, lh, 0.0, align=align))
    head = k.headline(str(sl.get("headline") or ""), l, 0, cw, ch * 0.45, token="h1", t=0.1, align=align,
                      emph=k.emph_indices(str(sl.get("headline") or ""), auto=True))
    st.text(head, fr, gap=36 * u)
    if sl.get("cta"):
        size = fr.type("h3") * 0.62
        bh = size * 0.72 + 2 * size * 0.5

        def mk(y, size=size):
            x = l if align == "left" else l + cw / 2
            return [{"type": "badge", "text": str(sl["cta"]), "x": x, "y": y,
                     "anchor": "top_left" if align == "left" else "top", "font": k.st.text_font, "weight": 700,
                     "size": size, "color": k.on_accent(), "bg": k.accent, "radius": 0 if k.st.radius < 2 else None,
                     "padx": size * 0.9, "pady": size * 0.5, "anim": {"type": "fade", "t": 0.45, "dur": 0.3},
                     "t0": 0.45, "z": 14}]

        st.add(bh, mk, gap=40 * u)
    if sl.get("url"):
        st.text(k.meta(str(sl["url"]), l, 0, cw, t=0.6, align=align, color=k.text), fr, gap=26 * u)
    els = st.place(t, b)
    for e in els:
        if e.get("type") == "badge" and e.get("radius") is None:
            e.pop("radius")
    return SceneOut(els, camera=_drift(cx, 0.6), sfx=[(0.1, "hit")])


def b_logo_sting(cx: BuildCtx, sc: Scene, D: float, i: int) -> SceneOut:
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    els = []
    band = 14 * u
    cy = fr.H / 2
    els.append({"type": "panel", "x": 0, "y": cy - band / 2, "w": fr.W, "h": band, "color": k.accent, "z": 2,
                "anim": {"type": "wipe_left", "t": 0.0, "dur": 0.35, "ease": "camera_strong"}, "t0": 0.0,
                "out": {"t": 0.5, "dur": 0.25, "type": "fade"}})
    if cx.look.logo_path:
        lh = min(260 * u, ch * 0.3)
        els += _logo(cx, l, cy - lh / 2, cw, lh, 0.35)
        ty = cy + lh / 2 + 36 * u
    else:
        name = cx.look.brand_name or cx.spec.title
        els.append(k.headline(name, l, cy - fr.type("h1") * 0.6, cw, fr.type("h1") * 1.3, token="h1", t=0.35,
                              align="center", anim="slam" if k.st.text_anim != "blur_in" else "blur_in",
                              max_lines=1))
        ty = cy + fr.type("h1") * 0.75
    tag = (sc.slots.get("tagline") or "").strip()
    if tag:
        els.append(k.body(tag, l, ty, cw, 120 * u, t=0.7, align="center", color=k.text))
    return SceneOut(els, sfx=[(0.3, "hit")], transition="fade")


def b_poll(cx: BuildCtx, sc: Scene, D: float, i: int) -> SceneOut:
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    sl = sc.slots
    opts = [str(it.get("text") or "") for it in (sl.get("options") or []) if isinstance(it, dict)][:4]
    letters = "ABCD"
    note = str(sl.get("note") or "").strip() or ("Comment " + ", ".join(letters[:max(1, len(opts) - 1)])
                                                  + (f" or {letters[len(opts) - 1]}" if len(opts) > 1 else ""))
    st = Stack()
    kh = k.kicker("Poll", l, 0, cw, t=0.0)[1]
    st.add(kh, lambda y: k.kicker("Poll", l, y, cw, t=0.0)[0])
    st.text(k.headline(str(sl.get("question") or ""), l, 0, cw, ch * 0.3, token="h2", t=0.1, max_lines=4), fr,
            gap=26 * u)
    n = len(opts)
    gap = 22 * u
    cols = 2 if fr.landscape and n > 2 else 1
    rows = math.ceil(n / cols) if n else 0
    box_h = min(130 * u, ch * 0.12) if not fr.landscape else min(120 * u, ch * 0.2)
    grid_h = rows * box_h + max(0, rows - 1) * gap
    t_opt = 0.6

    def grid(y):
        out = []
        bw = (cw - gap * (cols - 1)) / cols
        for j, text in enumerate(opts):
            bx = l + (j % cols) * (bw + gap)
            by = y + (j // cols) * (box_h + gap)
            tt = t_opt + 0.14 * j
            out += k.card(bx, by, bw, box_h, t=tt)
            pad = 30 * u
            ls = box_h * 0.42
            out.append({"type": "badge", "text": letters[j], "x": bx + pad, "y": by + box_h / 2, "anchor": "top_left",
                        "font": k.st.text_font, "weight": 800, "size": ls * 0.62, "color": k.on_accent(),
                        "bg": k.accent, "padx": ls * 0.36, "pady": ls * 0.27, "radius": ls * 0.2,
                        "anim": {"type": "fade", "t": tt + 0.05, "dur": 0.25}, "t0": tt, "z": 9})
            out[-1]["y"] = by + (box_h - (ls * 0.62 * 0.72 + 2 * ls * 0.27)) / 2
            tx = pad + ls * 1.25 + 22 * u
            out.append(k.headline(text, bx + tx, by + box_h * 0.18, bw - tx - pad, box_h * 0.64, token="h3",
                                  t=tt + 0.08, align="left", valign="center", font=k.st.text_font, weight=650,
                                  color=k.text, max_lines=2, anim="fade_up"))
        return out

    if n:
        st.add(grid_h, grid, gap=40 * u)
    st.text(k.meta(note, l, 0, cw, t=t_opt + 0.14 * n + 0.2, color=k.accent), fr, gap=36 * u)
    els = st.place(t, b)
    return SceneOut(els, camera=_drift(cx, 0.4), sfx=[(t_opt + 0.14 * j, "click") for j in range(n)])


def b_next_part(cx: BuildCtx, sc: Scene, D: float, i: int) -> SceneOut:
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    sl = sc.slots
    ser = cx.spec.options.series
    align = "center" if k.st.align == "center" or fr.landscape else k.st.align
    kicker = f"Next: part {ser.part + 1}" if ser.enabled and ser.part < max(ser.part, ser.total) else "Up next"
    st = Stack()
    kh = k.kicker(kicker, l, 0, cw, t=0.0, align=align)[1]
    st.add(kh, lambda y: k.kicker(kicker, l, y, cw, t=0.0, align=align)[0])
    teaser = str(sl.get("teaser") or "")
    st.text(k.headline(teaser, l, 0, cw, ch * 0.45, token="h1", t=0.12, align=align,
                       emph=k.emph_indices(teaser, auto=True), max_lines=4), fr, gap=30 * u)
    cta = str(sl.get("cta") or "").strip()
    if cta:
        size = fr.type("h3") * 0.62
        bh = size * 0.72 + 2 * size * 0.5

        def mk(y, size=size):
            x = l if align == "left" else l + cw / 2
            return [{"type": "badge", "text": cta, "x": x, "y": y, "anchor": "top_left" if align == "left" else "top",
                     "font": k.st.text_font, "weight": 700, "size": size, "color": k.on_accent(), "bg": k.accent,
                     "padx": size * 0.9, "pady": size * 0.5, "anim": {"type": "fade", "t": 0.5, "dur": 0.3},
                     "t0": 0.5, "z": 14}]

        st.add(bh, mk, gap=40 * u)
    comment = str(sl.get("comment") or "").strip()
    if comment:
        st.text(k.meta(comment, l, 0, cw, t=0.7, align=align, color=k.text), fr, gap=26 * u)
    return SceneOut(st.place(t, b), camera=_drift(cx, 0.6), sfx=[(0.1, "hit")])


# ---------------------------------------------------------------------------
# Big Number Reveal
# ---------------------------------------------------------------------------

def _hook_block(cx: BuildCtx, text: str, kicker: str, *, token: Optional[str] = None, t: float = 0.0,
                emph=None) -> list[dict]:
    k, fr = cx.kit, cx.fr
    l, top, r, b, cw, ch = _rect(cx)
    n = len(text.split())
    tok = token or ("display" if n <= 3 else "h1")
    st = Stack()
    if kicker:
        kh = k.kicker(kicker, l, 0, cw, t=t)[1]
        st.add(kh, lambda y: k.kicker(kicker, l, y, cw, t=t)[0])
    head = k.headline(text, l, 0, cw, ch * 0.75, token=tok, t=t + (0.15 if kicker else 0.0),
                      emph=emph if emph is not None else k.emph_indices(text, auto=True), max_lines=5)
    st.text(head, fr, gap=34 * fr.u)
    return st.place(top, b, "center")


def b_big_hook(cx, sc, D, i):
    sl = sc.slots
    return SceneOut(_hook_block(cx, str(sl.get("text") or ""), str(sl.get("kicker") or "")), camera=_drift(cx))


def b_big_reveal(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    sl = sc.slots
    value = _num(sl.get("value"))
    dec = int(_num(sl.get("decimals"), 0))
    prefix, unit = str(sl.get("prefix") or ""), str(sl.get("unit") or "")
    label = str(sl.get("label") or "")
    bottom = b - _src_band(cx)
    t_num, d_num = 0.15, 1.5
    land_ = cx.fr.landscape
    if land_:
        xn, wn = fr.col(0, 7)
        num = k.number(value, xn, t, wn, bottom - t, t=t_num, dur=d_num, decimals=dec, prefix=prefix, suffix=unit,
                       align="left", size=fr.type("numeric") * 1.15)
        xl, wl = fr.col(7.4, 4.6)
        lab = k.headline(label, xl, t, wl, bottom - t, token="h3", t=t_num + d_num * 0.85, valign="center",
                         align="left", anim="fade_up", font=k.st.text_font, weight=650, color=k.text, max_lines=5)
        x0, y0, w0, h0 = text_bounds(lab, fr)
        els = [num, lab, k.rule(xl, y0 - 30 * u, min(wl, 140 * u), t=t_num + d_num * 0.7)]
    else:
        align = k.st.align
        num = k.number(value, l, 0, cw, fr.type("numeric") * 1.0, t=t_num, dur=d_num, decimals=dec, prefix=prefix,
                       suffix=unit, align=align)
        nx, ny, nw, nh = odo_bounds({**num, "y": 0}, fr)
        st = Stack()
        st.add(nh * 1.18, lambda y: [{**num, "y": y, "h": nh * 1.18, "valign": "center"}])
        rw = min(cw, 160 * u)
        st.add(6 * u, lambda y: [k.rule(l if align == "left" else l + (cw - rw) / 2, y, rw,
                                        t=t_num + d_num * 0.7, origin="left" if align == "left" else "center")],
               gap=34 * u)
        st.text(k.headline(label, l, 0, cw, ch * 0.3, token="h3", t=t_num + d_num * 0.85, align=align,
                           anim="fade_up", font=k.st.text_font, weight=650, color=k.text, max_lines=3), fr,
                gap=34 * u)
        els = st.place(t, bottom)
    els += k.source_line(cx.spec.source, t=0.4)
    land_at = t_num + d_num * 0.92
    return SceneOut(els, camera=_drift(cx, 0.5), sfx=[(land_at - 0.6, "riser"), (land_at, "hit")])


def b_big_meaning(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    sl = sc.slots
    text = str(sl.get("text") or "")
    bottom = b - _src_band(cx)
    has_cmp = sl.get("compare_value") not in (None, "")
    rv = next((s for s in cx.spec.scenes if s.type == "reveal"), None)
    value = _num(rv.slots.get("value")) if rv else 0.0
    fmt = _fmt_from_reveal(cx)
    if not has_cmp:
        return SceneOut(_hook_block(cx, text, "", token="h2") + k.source_line(cx.spec.source, t=0.4),
                        camera=_drift(cx))
    cs = k.chart_style()
    labels = [str(sl.get("compare_label") or "Before"), str(sl.get("value_label") or "Now")]
    vals = [_num(sl.get("compare_value")), value]
    if fr.landscape:
        xt, wt = fr.col(0, 5.5)
        head = k.headline(text, xt, t, wt, bottom - t, token="h2", t=0.0, valign="center", align="left",
                          emph=k.emph_indices(text, auto=True))
        xb, wb = fr.col(6.2, 5.8)
        bars = {"type": "bars", "x": xb, "y": t + ch * 0.1, "w": wb, "h": (bottom - t) * 0.8, "labels": labels,
                "values": vals, "highlight": 1, "orientation": "v", "t": 0.5, "dur": 0.8, "stagger": 0.12,
                "format": fmt, "color": cs["accent"], "highlight_color": cs["accent"],
                "muted_color": mix(k.p.bg, k.p.text, 0.32), **cs, "z": 8, "t0": 0.0}
        els = [head, bars]
    else:
        st = Stack()
        st.text(k.headline(text, l, 0, cw, ch * 0.4, token="h2", t=0.0, emph=k.emph_indices(text, auto=True)), fr)
        bh = min(ch * 0.46, cw * 0.95)
        bw = min(cw, 760 * u)
        bx = l if k.st.align == "left" else l + (cw - bw) / 2
        st.add(bh, lambda y: [{"type": "bars", "x": bx, "y": y, "w": bw, "h": bh, "labels": labels, "values": vals,
                               "highlight": 1, "orientation": "v", "t": 0.5, "dur": 0.8, "stagger": 0.12,
                               "format": fmt, "color": cs["accent"], "highlight_color": cs["accent"],
                               "muted_color": mix(k.p.bg, k.p.text, 0.32), **cs, "z": 8, "t0": 0.0}], gap=56 * u)
        els = st.place(t, bottom)
    els += k.source_line(cx.spec.source, t=0.4)
    return SceneOut(els, camera=_drift(cx, 0.4))


def b_big_takeaway(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    text = str(sc.slots.get("text") or "")
    st = Stack()
    st.text(k.headline(text, l, 0, cw, ch * 0.55, token="h1", t=0.0, emph=k.emph_indices(text, auto=True)), fr)
    if cx.look.logo_path:
        st.add(110 * u, lambda y: _logo(cx, l, y, cw * (0.4 if k.st.align == "left" else 1.0), 110 * u, 0.6,
                                        align="left" if k.st.align == "left" else "center"), gap=60 * u)
    els = st.place(t, b - _src_band(cx)) + k.source_line(cx.spec.source, t=0.5)
    return SceneOut(els, camera=_drift(cx))


# ---------------------------------------------------------------------------
# Kinetic Quote
# ---------------------------------------------------------------------------

def _quote_anim(cx: BuildCtx) -> str:
    return {"swiss_grid": "weight_morph", "brutalist_mono": "slam", "soft_gradient": "blur_in",
            "editorial_serif": "mask_up", "newsprint": "mask_up"}.get(cx.look.style.id, "mask_up")


def _word_times(text: str, words: list[dict]) -> Optional[list]:
    toks = text.split()
    if not words:
        return None
    norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())  # noqa: E731
    out: list = []
    j = 0
    for tk in toks:
        nt = norm(tk)
        found = None
        for k in range(j, min(len(words), j + 4)):
            if norm(words[k]["text"]) == nt or (nt and norm(words[k]["text"]).startswith(nt[:4])):
                found = k
                break
        if found is None and j < len(words):
            found = j
        if found is None:
            out.append(None)
        else:
            out.append(max(0.0, float(words[found]["start"]) - 0.05))
            j = found + 1
    return out


def b_quote_line(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    sl = sc.slots
    text = str(sl.get("text") or "")
    times = _word_times(text, cx.vo.get(sc.id) or [])
    n = len(text.split())
    tok = "display" if n <= 4 else "h1"
    emph = k.emph_indices(text, sl.get("emphasis"))
    head = k.headline(text, l, t, cw, ch, token=tok, t=0.05, emph=emph, valign="center", anim=_quote_anim(cx),
                      emph_scale=1.18 if k.st.id != "brutalist_mono" else 1.0, max_lines=5, times=times)
    els = [head]
    if sc.type == "payoff" and k.st.rules:
        x0, y0, w0, h0 = text_bounds(head, fr)
        els.append(k.rule(x0, y0 + h0 + 30 * fr.u, min(w0, 220 * fr.u), t=0.6))
    return SceneOut(els, camera=_drift(cx, 1.2), sfx=[(0.05, "hit")] if sc.type == "payoff" else [])


def b_quote_attr(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    sl = sc.slots
    align = k.st.align
    st = Stack()
    photo = cx.image(sl.get("photo"))
    if photo:
        d = min(260 * u, cw * 0.4)
        px = l if align == "left" else l + (cw - d) / 2
        st.add(d, lambda y: [{"type": "image", "src": photo, "x": px, "y": y, "w": d, "h": d, "radius": d / 2,
                              "zoom": [1.0, 1.05], "anim": {"type": "scale", "t": 0.0, "dur": 0.5}, "z": 6,
                              "border": k.accent, "border_w": 4 * u}])
    qsize = fr.type("display") * 1.6
    qx = l if align == "left" else l + cw / 2
    st.add(qsize * 0.55, lambda y: [{"type": "numeral", "text": "“", "x": qx,
                                     "y": y + qsize * 0.78, "align": align, "font": "Playfair Display",
                                     "weight": 900, "size": qsize, "color": k.accent, "t": 0.0, "dur": 0.4,
                                     "from_scale": 1.25, "from_rot": 0, "ease": "snap", "z": 6}],
           gap=20 * u)
    rw = 80 * u
    st.add(5 * u, lambda y: [k.rule(l if align == "left" else l + (cw - rw) / 2, y, rw, t=0.1,
                                    origin="left" if align == "left" else "center")], gap=30 * u)
    st.text(k.headline(str(sl.get("name") or ""), l, 0, cw, ch * 0.3, token="h1", t=0.2, align=align, max_lines=2),
            fr, gap=30 * u)
    if sl.get("title"):
        st.text(k.body(str(sl["title"]), l, 0, cw, ch * 0.2, t=0.4, align=align, token="h3", color=k.muted), fr,
                gap=16 * u)
    if cx.look.logo_path:
        st.add(90 * u, lambda y: _logo(cx, l, y, cw * (0.35 if align == "left" else 1), 90 * u, 0.6,
                                       align=align if align != "right" else "center"), gap=50 * u)
    return SceneOut(st.place(t, b), camera=_drift(cx, 0.5))


# ---------------------------------------------------------------------------
# Bar Chart Race
# ---------------------------------------------------------------------------

def b_race_title(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    sl = sc.slots
    st = Stack()
    units = str(sl.get("units") or "")
    if units:
        st.add(k.kicker(units, l, 0, cw)[1], lambda y: k.kicker(units, l, y, cw, t=0.0)[0])
    title = str(sl.get("title") or "")
    st.text(k.headline(title, l, 0, cw, ch * 0.55, token="h1", t=0.12, emph=k.emph_indices(title, auto=True)), fr,
            gap=30 * u)
    if sl.get("subtitle"):
        st.text(k.body(str(sl["subtitle"]), l, 0, cw, ch * 0.2, t=0.45), fr, gap=26 * u)
    return SceneOut(st.place(t, b), camera=_drift(cx))


def race_entities(cx: BuildCtx) -> list[dict]:
    v = cx.data or {}
    ents = v.get("entities") or []
    vals = v.get("values") or {}
    order = sorted(ents, key=lambda e: -max(vals.get(e) or [0]))
    pal = list(cx.look.p.chart)
    bg = cx.look.p.bg
    colors = {}
    for i, e in enumerate(order):
        colors[e] = accent_on(pal[i % len(pal)], bg)
    return [{"name": e, "color": colors[e], "values": vals.get(e) or []} for e in ents]


def b_race(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    sl = sc.slots
    v = cx.data or {}
    periods = [str(p) for p in v.get("periods") or []]
    do = cx.spec.data_options
    pd = do.period_seconds or 0.8
    top_n = do.top_n or (10 if fr.landscape else 8)
    units = v.get("units") or {}
    mx = float(v.get("max") or 0)
    fmt = {"prefix": do.prefix if do.prefix is not None else units.get("prefix", ""),
           "suffix": do.suffix if do.suffix is not None else units.get("suffix", ""),
           "decimals": do.decimals if do.decimals is not None else int(v.get("decimals") or 0),
           "compact": do.compact if do.compact is not None else mx >= 10000}
    els = []
    heading = str(sl.get("heading") or "")
    y = t
    if heading:
        hd = k.headline(heading, l, t, cw, fr.type("h3") * 2.4, token="h3", t=0.0, anim="fade_up", max_lines=2,
                        align="left")
        hh = text_height(hd, fr)
        els.append({**hd, "h": hh + 4})
        y = t + hh + 24 * u
    bottom = b - _src_band(cx)
    t_race = 0.8
    cs = k.chart_style()
    end_t = t_race + (len(periods) - 1) * pd
    els.append({
        "type": "bar_race", "x": l, "y": y, "w": cw, "h": bottom - y, "periods": periods,
        "entities": race_entities(cx), "top_n": top_n, "t": t_race, "period_dur": pd, "format": fmt,
        "label_font": k.st.text_font, "label_weight": 600, "value_font": k.data_font,
        "value_weight": max(600, min(800, k.st.numeric_weight)), "text": cs["text"], "muted": cs["muted"],
        "rule": cs["rule"], "accent": cs["accent"], "highlight_at": end_t + 0.3, "z": 6, "t0": 0.0,
        "radius": 0 if k.st.radius < 2 else 10 * u,
        "ticker": {"x": l + cw, "y": bottom - 16 * u, "size": fr.type("numeric") * (0.55 if fr.landscape else 0.42),
                   "font": k.data_font, "weight": 800, "color": cs["muted"], "alpha": 0.42},
    })
    for note in sl.get("notes") or []:
        try:
            idx = periods.index(str(note.get("period")).strip())
        except ValueError:
            continue
        nt = t_race + idx * pd
        size = fr.type("h3") * 0.62
        els.append({"type": "badge", "text": str(note.get("text") or ""), "x": l + cw, "y": y + 4 * u,
                    "anchor": "top_right", "font": k.st.text_font, "weight": 700, "size": size,
                    "color": k.on_accent(), "bg": k.accent, "radius": 0 if k.st.radius < 2 else None,
                    "anim": {"type": "slide", "t": nt, "dur": 0.3}, "t0": nt, "t1": nt + 2.6,
                    "out": {"t": nt + 2.3, "dur": 0.3, "type": "fade"}, "z": 20})
    for e in els:
        if e.get("type") == "badge" and e.get("radius") is None:
            e.pop("radius")
    els += k.source_line(cx.spec.source, t=0.4)
    return SceneOut(els, sfx=[(end_t + 0.3, "hit")])


# ---------------------------------------------------------------------------
# Countdown Listicle
# ---------------------------------------------------------------------------

def b_list_hook(cx, sc, D, i):
    sl = sc.slots
    n = len(cx.scenes_of("item"))
    kicker = str(sl.get("kicker") or (f"Top {n}" if n else ""))
    return SceneOut(_hook_block(cx, str(sl.get("text") or ""), kicker), camera=_drift(cx))


def b_list_item(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    sl = sc.slots
    items = cx.scenes_of("item")
    rank = len(items) - next((j for j, s in enumerate(items) if s is sc), 0)
    img = cx.image(sl.get("image"))
    title = str(sl.get("title") or "")
    detail = str(sl.get("detail") or "")
    st_ = k.st
    num_size = fr.type("display") * (1.55 if not fr.landscape else 1.7)
    outline = st_.id in ("newsprint", "editorial_serif")
    num_color = k.accent
    els = []
    rng = cx.look.rng(f"item{rank}")
    if fr.landscape:
        xn, wn = fr.col(0, 3)
        num_size = fr.type("display") * (1.7 if img else 2.1)
        cy = (t + b) / 2
        els.append({"type": "numeral", "text": str(rank), "x": xn, "y": cy + num_size * 0.36, "font": st_.numeric_font,
                    "weight": st_.numeric_weight, "size": num_size, "color": num_color, "outline": outline,
                    "t": 0.0, "dur": cx.look.t(0.35), "from_scale": 1.4, "from_rot": rng.choice((-1, 1)) * 10,
                    "ease": cx.look.ease_pop(), "z": 8, "t0": 0.0})
        span = 4.6 if img else 8.6
        xt, wt = fr.col(3.4, span)
        st = Stack()
        st.text(k.headline(title, xt, 0, wt, ch * 0.5, token="h1" if img else "display", t=0.25, align="left",
                           anim="slide_mask" if st_.text_anim != "slam" else "slam", max_lines=3), fr)
        if detail:
            st.text(k.body(detail, xt, 0, wt, ch * 0.3, t=0.45, align="left", token="body" if img else "h3"), fr,
                    gap=28 * u)
        els += st.place(t, b)
        if img:
            xi, wi = fr.col(8.2, 3.8)
            hi = min(ch * 0.9, wi * 1.25)
            els.append({"type": "image", "src": img, "x": xi, "y": t + (ch - hi) / 2, "w": wi, "h": hi,
                        "radius": st_.radius * u, "zoom": [1.0, 1.07], "anim": {"type": "reveal_up", "t": 0.3, "dur": 0.5},
                        "z": 5, "t0": 0.3})
    else:
        # Numeral, title and detail are one block centred in the frame (with
        # an image, in the space above it), not pinned to the top.
        top_block = num_size * 0.78
        align = st_.align
        nx = l if align == "left" else l + cw / 2
        numeral = {"type": "numeral", "text": str(rank), "x": nx, "align": align,
                   "font": st_.numeric_font, "weight": st_.numeric_weight, "size": num_size, "color": num_color,
                   "outline": outline, "t": 0.0, "dur": cx.look.t(0.35), "from_scale": 1.4,
                   "from_rot": rng.choice((-1, 1)) * 10, "ease": cx.look.ease_pop(), "z": 8, "t0": 0.0}
        avail_b = b
        if img:
            ih = min(ch * (0.4 if fr.vertical else 0.36), cw * 0.8)
            avail_b = b - ih - 40 * u
            els.append({"type": "image", "src": img, "x": l, "y": b - ih, "w": cw, "h": ih,
                        "radius": st_.radius * u, "zoom": [1.0, 1.07], "anim": {"type": "reveal_up", "t": 0.3, "dur": 0.5},
                        "z": 5, "t0": 0.3})
        room = avail_b - t - top_block - 40 * u
        st = Stack()
        st.add(top_block, lambda y: [{**numeral, "y": y + top_block}])
        st.text(k.headline(title, l, 0, cw, room * 0.7, token="h1", t=0.25,
                           anim="slide_mask" if st_.text_anim not in ("slam", "blur_in") else st_.text_anim), fr,
                gap=40 * u)
        if detail:
            st.text(k.body(detail, l, 0, cw, room * 0.35, t=0.45), fr, gap=26 * u)
        els += st.place(t, avail_b, "center")
    return SceneOut(els, camera=_drift(cx, 0.8), sfx=[(0.0, "hit")])


def b_list_cta(cx, sc, D, i):
    return SceneOut(_hook_block(cx, str(sc.slots.get("text") or ""), "", token="h1"), camera=_drift(cx))


# ---------------------------------------------------------------------------
# X vs Y
# ---------------------------------------------------------------------------

def _vs_names(cx: BuildCtx) -> tuple[str, str]:
    intro = next((s for s in cx.spec.scenes if s.type == "intro"), None)
    a = str((intro.slots.get("a_name") if intro else "") or (cx.data or {}).get("a_name") or "A")
    b = str((intro.slots.get("b_name") if intro else "") or (cx.data or {}).get("b_name") or "B")
    return a, b


def _vs_colors(cx: BuildCtx) -> tuple[str, str]:
    p = cx.look.p
    return accent_on(p.accent, p.bg), accent_on(p.accent2 if p.accent2.upper() != p.text.upper() else p.chart[1], p.bg)


def _round_values(cx: BuildCtx, sc: Scene, ri: int) -> dict:
    sl = dict(sc.slots)
    metrics = (cx.data or {}).get("metrics") or []
    if metrics and ri < len(metrics):
        m = metrics[ri]
        sl.setdefault("label", m["label"])
        if sl.get("a") in (None, ""):
            sl["a"] = m["a"]
        if sl.get("b") in (None, ""):
            sl["b"] = m["b"]
        if sl.get("higher_is_better") is None:
            sl["higher_is_better"] = m["higher_is_better"]
    return sl


def _winner(sl: dict) -> Optional[str]:
    a, b = _num(sl.get("a")), _num(sl.get("b"))
    if a == b:
        return None
    hib = sl.get("higher_is_better")
    hib = True if hib is None else bool(hib)
    return ("a" if a > b else "b") if hib else ("a" if a < b else "b")


def b_vs_intro(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    u = fr.u
    a_name, b_name = _vs_names(cx)
    ca, cb = _vs_colors(cx)
    W, H = fr.W, fr.H
    els = []
    side = fr.landscape or fr.orientation == "square"
    if side:
        pa = {"x": 0, "y": 0, "w": W / 2, "h": H}
        pb = {"x": W / 2, "y": 0, "w": W / 2, "h": H}
        an_a, an_b = "from_left", "from_right"
    else:
        pa = {"x": 0, "y": 0, "w": W, "h": H / 2}
        pb = {"x": 0, "y": H / 2, "w": W, "h": H / 2}
        an_a, an_b = "from_top", "from_bottom"
    els.append({"type": "panel", **pa, "color": ca, "z": 1, "anim": {"type": an_a, "t": 0.0, "dur": cx.look.t(0.5),
                                                                      "ease": "decel"}, "t0": 0.0})
    els.append({"type": "panel", **pb, "color": cb, "z": 1, "anim": {"type": an_b, "t": 0.0, "dur": cx.look.t(0.5),
                                                                      "ease": "decel"}, "t0": 0.0})
    l, t, r, b, cw, ch = _rect(cx)
    pad = 60 * u
    for name, pnl, col, logo_key, dt in ((a_name, pa, ca, "a_logo", 0.35), (b_name, pb, cb, "b_logo", 0.45)):
        tc = readable("#FFFFFF", col)
        if side:
            bx = max(pnl["x"] + pad, l)
            bw = min(pnl["x"] + pnl["w"] - pad, r) - bx
            by, bh = t, ch
        else:
            bx, bw = l, cw
            by = max(pnl["y"] + pad, t)
            bh = min(pnl["y"] + pnl["h"] - pad, b) - by
        logo = cx.image(sc.slots.get(logo_key))
        if logo:
            lh = min(160 * u, bh * 0.35)
            els.append({"type": "logo", "src": logo, "x": bx, "y": by + bh / 2 - lh - 20 * u, "w": bw, "h": lh,
                        "align": "center", "z": 5, "t0": dt, "anim": {"type": "pop", "t": dt, "dur": 0.4}})
            els.append(k.headline(name, bx, by + bh / 2 + 10 * u, bw, bh / 2, token="h1", t=dt, align="center",
                                  color=tc, max_lines=2, anim="fade_up"))
        else:
            els.append(k.headline(name, bx, by, bw, bh, token="display", t=dt, align="center", valign="center",
                                  color=tc, max_lines=2))
    vs = 150 * u
    els.append({"type": "shape", "shape": "circle", "x": W / 2 - vs / 2, "y": H / 2 - vs / 2, "w": vs, "h": vs,
                "color": k.p.bg, "z": 9, "anim": {"type": "scale", "t": 0.55, "dur": 0.35, "ease": "overshoot"},
                "t0": 0.55})
    els.append({"type": "text", "text": "VS", "x": W / 2 - vs / 2, "y": H / 2 - vs / 2, "w": vs, "h": vs,
                "align": "center", "valign": "center", "font": k.st.display_font, "weight": k.st.display_weight,
                "size": vs * 0.42, "color": k.text, "max_lines": 1, "z": 10, "t0": 0.65,
                "anim": {"type": "pop", "t": 0.65, "dur": 0.3, "stagger": 0}})
    q = str(sc.slots.get("question") or "")
    if q:
        size = fr.type("h3") * 0.6
        els.append({"type": "badge", "text": q, "x": W / 2, "y": t, "anchor": "top", "font": k.st.text_font,
                    "weight": 700, "size": size, "color": "#FFFFFF", "bg": "rgba(0,0,0,0.55)",
                    "anim": {"type": "fade", "t": 0.8, "dur": 0.3}, "t0": 0.8, "z": 12})
    return SceneOut(els, sfx=[(0.0, "whoosh"), (0.6, "hit")])


def b_vs_round(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    rounds = cx.scenes_of("round")
    ri = next((j for j, s in enumerate(rounds) if s is sc), 0)
    sl = _round_values(cx, sc, ri)
    a_name, b_name = _vs_names(cx)
    ca, cb = _vs_colors(cx)
    sa = sb = 0
    for j, s in enumerate(rounds[: ri + 1]):
        w = _winner(_round_values(cx, s, j))
        sa += w == "a"
        sb += w == "b"
    els = []
    score = f"{a_name}  {sa} : {sb}  {b_name}"
    ssize = fr.type("caption") * 0.62
    els.append({"type": "badge", "text": score, "x": fr.W / 2, "y": t, "anchor": "top", "font": k.data_font,
                "weight": 700, "size": ssize, "color": k.text, "border": k.muted, "border_w": 1.5 * u,
                "anim": {"type": "fade", "t": 1.2, "dur": 0.3}, "t0": 1.2, "z": 12})
    lab = str(sl.get("label") or "")
    hib = sl.get("higher_is_better")
    head = k.headline(lab, l, t + ssize * 2.6, cw, ch * 0.22, token="h2", t=0.0, align="center", max_lines=2)
    hh = text_height(head, fr)
    els.append({**head, "h": hh + 4})
    vy = t + ssize * 2.6 + hh + 20 * u
    if hib is False:
        els.append(k.meta("Lower is better", l, vy, cw, t=0.4, align="center"))
    vy += 70 * u
    bottom = b - _src_band(cx)
    vw = min(cw, 900 * u)
    fmt = {"prefix": str(sl.get("prefix") or ""), "suffix": str(sl.get("unit") or ""),
           "decimals": 1 if any(abs(_num(sl.get(x_)) - round(_num(sl.get(x_)))) > 1e-9 for x_ in ("a", "b")) else 0}
    els.append({"type": "versus", "x": l + (cw - vw) / 2, "y": vy, "w": vw, "h": bottom - vy - 20 * u, "a": _num(sl.get("a")),
                "b": _num(sl.get("b")), "a_name": a_name, "b_name": b_name, "a_color": ca, "b_color": cb,
                "winner": _winner(sl), "t": 0.3, "dur": cx.look.t(0.8), "format": fmt, **k.chart_style(),
                "z": 6, "t0": 0.0})
    els += k.source_line(cx.spec.source, t=0.5)
    return SceneOut(els, sfx=[(0.3 + 0.8, "hit")])


def b_vs_verdict(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    rounds = cx.scenes_of("round")
    sa = sum(_winner(_round_values(cx, s, j)) == "a" for j, s in enumerate(rounds))
    sb = sum(_winner(_round_values(cx, s, j)) == "b" for j, s in enumerate(rounds))
    a_name, b_name = _vs_names(cx)
    ca, cb = _vs_colors(cx)
    st = Stack()
    if sa != sb:
        name, col = (a_name, ca) if sa > sb else (b_name, cb)
        st.add(k.kicker("Winner", l, 0, cw)[1], lambda y: k.kicker("Winner", l, y, cw, t=0.0, align="center")[0])
        st.text(k.headline(name, l, 0, cw, ch * 0.3, token="display", t=0.1, align="center", color=col, max_lines=2),
                fr, gap=20 * u)
        st.text(k.meta(f"{max(sa, sb)} of {len(rounds)} rounds", l, 0, cw, t=0.4, align="center"), fr, gap=10 * u)
    text = str(sc.slots.get("text") or "")
    st.text(k.headline(text, l, 0, cw, ch * 0.35, token="h2", t=0.6, align="center", anim="fade_up",
                       font=k.st.text_font, weight=650, color=k.text), fr, gap=50 * u)
    return SceneOut(st.place(t, b), camera=_drift(cx), sfx=[(0.1, "hit")])


# ---------------------------------------------------------------------------
# Product Promo
# ---------------------------------------------------------------------------

def b_promo_claim(cx, sc, D, i):
    sl = sc.slots
    return SceneOut(_hook_block(cx, str(sl.get("text") or ""), str(sl.get("product") or ""),
                                token="display" if len(str(sl.get("text") or "").split()) <= 3 else "h1"),
                    camera=_drift(cx))


def _device_geometry(kind: str, w: float, h: float, u: float):
    if kind == "phone":
        inset = w * 0.04
        return inset, inset, w - 2 * inset, h - 2 * inset
    return 8 * u, 58 * u, w - 16 * u, h - 66 * u


def b_promo_feature(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    sl = sc.slots
    kind = str(sl.get("device") or "browser")
    shot = cx.image(sl.get("screenshot"))
    fx = min(0.95, max(0.05, _num(sl.get("focus_x"), 0.5)))
    fy = min(0.95, max(0.05, _num(sl.get("focus_y"), 0.4)))
    title, line = str(sl.get("title") or ""), str(sl.get("line") or "")
    els = []
    if fr.landscape:
        xt, wt = fr.col(0, 4.3)
        st = Stack()
        st.text(k.headline(title, xt, 0, wt, ch * 0.5, token="h2", t=0.0, align="left"), fr)
        if line:
            st.text(k.body(line, xt, 0, wt, ch * 0.4, t=0.3, align="left"), fr, gap=24 * u)
        els += st.place(t, b)
        xd, wd = fr.col(4.8, 7.2)
        if kind == "phone":
            dh = ch * 0.98
            dw = dh * 0.49
            dx, dy = xd + (wd - dw) / 2, t + (ch - dh) / 2
        else:
            dw = wd
            dh = min(ch * 0.95, dw * 0.64)
            dx, dy = xd, t + (ch - dh) / 2
    else:
        st = Stack()
        st.text(k.headline(title, l, 0, cw, ch * 0.22, token="h2", t=0.0, max_lines=2), fr)
        if line:
            st.text(k.body(line, l, 0, cw, ch * 0.16, t=0.3, max_lines=2), fr, gap=18 * u)
        th = st.height()
        els += st.place(t, t + th, "top")
        top = t + th + 50 * u
        avail = b - top
        if kind == "phone":
            dh = avail
            dw = min(cw * 0.8, dh * 0.49)
            dh = dw / 0.49
            dx, dy = l + (cw - dw) / 2, top
        else:
            dw = cw
            dh = min(avail, dw * 0.68)
            dx, dy = l, top + (avail - dh) * 0.3
    cx0, cy0, ccw, cch = _device_geometry(kind, dw, dh, u)
    px, py = dx + cx0 + ccw * fx, dy + cy0 + cch * fy
    p = cx.look.p
    surface = "#15161B" if p.bg.upper() < "#888888" else "#FFFFFF"
    els.append({"type": "device", "src": shot, "kind": kind, "x": dx, "y": dy, "w": dw, "h": dh,
                "url": str((cx.spec.scenes[0].slots.get("product") or "")).lower().replace(" ", "") + ".app"
                if kind == "browser" else None,
                "surface": surface if kind == "browser" else "#0B0B0F", "bar": mix(surface, "#808080", 0.15),
                "accent": k.accent, "t": 0.2, "t0": 0.0, "z": 6,
                # Push toward the callout. A vertical frame already fills the
                # width with the device, so it pushes less and stays on screen.
                "push": {"from": 1.0, "to": 1.1 if fr.vertical else 1.24, "t": 1.0, "dur": cx.look.t(1.2),
                         "fx": fx, "fy": fy},
                "callout": {"fx": fx, "fy": fy, "label": str(sl.get("callout") or ""), "t": 2.4, "d": 150 * u}})
    els.append({"type": "cursor", "x0": dx + dw * 0.85, "y0": dy + dh * 0.95, "x1": px, "y1": py, "t": 1.7,
                "dur": 0.7, "color": "#FFFFFF", "size": 40 * u, "z": 9, "t0": 1.4})
    return SceneOut(els, sfx=[(2.4, "hit")])


def b_promo_recap(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    items = [str(it.get("text") or "") for it in (sc.slots.get("benefits") or []) if isinstance(it, dict)][:3]
    if not items:
        return SceneOut([])
    els = []
    n = len(items)
    gap = 28 * u
    if fr.landscape:
        cwid = (cw - gap * (n - 1)) / n
        chh = ch * 0.5
        y0 = t + (ch - chh) / 2
        boxes = [(l + j * (cwid + gap), y0, cwid, chh) for j in range(n)]
    else:
        chh = min((ch - gap * (n - 1)) / n, 260 * u)
        total = n * chh + (n - 1) * gap
        y0 = t + (ch - total) / 2
        boxes = [(l, y0 + j * (chh + gap), cw, chh) for j in range(n)]
    for j, (bx, by, bw, bh) in enumerate(boxes):
        tt = 0.12 * j
        els += k.card(bx, by, bw, bh, t=tt)
        pad = 36 * u
        els.append(k.meta(f"0{j + 1}", bx + pad, by + pad, bw - 2 * pad, t=tt + 0.1, color=k.accent, align="left"))
        els.append(k.headline(items[j], bx + pad, by + pad + 50 * u, bw - 2 * pad, bh - 2 * pad - 50 * u, token="h3",
                              t=tt + 0.15, align="left", valign="center", font=k.st.text_font, weight=700, max_lines=3,
                              anim="fade_up"))
    return SceneOut(els, camera=_drift(cx, 0.5))


# ---------------------------------------------------------------------------
# Product Explainer
# ---------------------------------------------------------------------------

def _pe_split(cx: BuildCtx, title: str, line: str, *, t: float = 0.0) -> tuple[list[dict], tuple]:
    """Title and line, plus the box left for the scene's visual: text on the
    left and the visual on the right in landscape, text on top otherwise."""
    k, fr = cx.kit, cx.fr
    l, top, r, b, cw, ch = _rect(cx)
    u = fr.u
    st = Stack()
    if fr.landscape:
        xt, wt = fr.col(0, 4.3)
        st.text(k.headline(title, xt, 0, wt, ch * 0.5, token="h2", t=t, align="left"), fr)
        if line:
            st.text(k.body(line, xt, 0, wt, ch * 0.4, t=t + 0.3, align="left"), fr, gap=24 * u)
        xv, wv = fr.col(4.8, 7.2)
        return st.place(top, b), (xv, top, wv, ch)
    st.text(k.headline(title, l, 0, cw, ch * 0.24, token="h2", t=t, max_lines=3), fr)
    if line:
        st.text(k.body(line, l, 0, cw, ch * 0.14, t=t + 0.3, max_lines=2), fr, gap=18 * u)
    th = st.height()
    els = st.place(top, top + th, "top")
    vy = top + th + 56 * u
    return els, (l, vy, cw, b - vy)


def _pe_colors(cx: BuildCtx) -> dict:
    k, p = cx.kit, cx.look.p
    dark = p.bg.upper() < "#888888"
    surface = p.surface if p.surface.upper() != p.bg.upper() else mix(p.bg, "#FFFFFF" if dark else "#000000", 0.05)
    return {"text": k.text, "muted": k.muted, "accent": k.accent, "on_accent": k.on_accent(), "surface": surface,
            "rule": p.rule or mix(p.bg, k.text, 0.18), "negative": p.negative or "#E5383B", "dark": dark}


def _pe_window(cx: BuildCtx, x, y, w, h, title: str, t: float = 0.1) -> dict:
    c, u = _pe_colors(cx), cx.fr.u
    return {"type": "window", "x": x, "y": y, "w": w, "h": h, "title": title, "surface": c["surface"],
            "border": c["rule"], "bar_line": c["rule"], "muted": c["muted"],
            "radius": max(6.0, cx.kit.st.radius) * u, "bar": 58 * u, "t": t, "t0": max(0.0, t - 0.05), "z": 5}


def _pe_center(cx: BuildCtx, els: list[dict], used_bottom: float) -> list[dict]:
    """Portrait and square: move the title and visual down together so the
    block sits just above the middle instead of hugging the top."""
    if cx.fr.landscape:
        return els
    b = _rect(cx)[3]
    off = max(0.0, (b - used_bottom) * 0.42)
    for e in els:
        if "y" in e:
            e["y"] = float(e["y"]) + off
    return els


def _wrap_code(lines: list[str], limit: int) -> list[str]:
    """Break code lines longer than ``limit`` at a comma or space, continuing
    with an indent (narrow frames keep the type readable)."""
    out = []
    for line in lines:
        indent = len(line) - len(line.lstrip())
        while len(line) > limit:
            cut = max(line.rfind(", ", 0, limit), line.rfind("(", 0, limit))
            cut = cut + 1 if cut > indent + 4 else line.rfind(" ", indent + 4, limit)
            if cut <= indent + 4:
                break
            out.append(line[:cut].rstrip())
            line = " " * (indent + 4) + line[cut:].lstrip()
        out.append(line)
    return out


def b_pe_problem(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    u = fr.u
    sl = sc.slots
    items = [str(it.get("text") or "") for it in (sl.get("items") or []) if isinstance(it, dict)][:5]
    els, (x, y, w, h) = _pe_split(cx, str(sl.get("title") or ""), "")
    if not items:
        return SceneOut(els, camera=_drift(cx))
    c = _pe_colors(cx)
    n = len(items)
    size = min(fr.type("h3") * 0.82, h / (n * 1.9))
    lh = size * 1.9
    y0 = y + max(0.0, (h - n * lh) / 2) if fr.landscape else y + 10 * u
    t0, stagger = 0.35, 0.16
    strike_t = t0 + n * stagger + 0.35
    els.append({"type": "strike_list", "x": x, "y": y0, "w": w, "items": items, "size": size,
                "font": k.st.text_font, "weight": 700, "color": c["text"], "strike": c["negative"], "line_h": lh,
                "t": t0, "stagger": stagger, "strike_t": strike_t, "strike_gap": 0.32, "t0": t0, "z": 8})
    return SceneOut(_pe_center(cx, els, y0 + n * lh), camera=_drift(cx, 0.5),
                    sfx=[(strike_t + j * 0.32, "click") for j in range(n)])


def b_pe_hub(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    u = fr.u
    sl = sc.slots
    nodes = [str(it.get("text") or "") for it in (sl.get("nodes") or []) if isinstance(it, dict)][:8]
    els, (x, y, w, h) = _pe_split(cx, str(sl.get("title") or ""), str(sl.get("line") or ""))
    c = _pe_colors(cx)
    side = min(w, h)
    hw, hh = (w, min(h, w * 0.9)) if not fr.landscape else (w, h)
    hy = y + (h - hh) / 2 if fr.landscape else y + max(0.0, (h - hh) * 0.35)
    els.append({"type": "hub", "x": x, "y": hy, "w": hw, "h": hh, "center": str(sl.get("center") or ""),
                "nodes": nodes, "size": max(22 * u, min(34 * u, side * 0.045)), "font": k.st.text_font,
                "color": c["text"], "accent": c["accent"], "on_accent": c["on_accent"], "surface": c["surface"],
                "rule": c["rule"], "t": 0.35, "t0": 0.3, "z": 6})
    return SceneOut(_pe_center(cx, els, hy + hh), camera=_drift(cx, 0.4), sfx=[(0.35, "hit")])


def b_pe_app(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    u = fr.u
    sl = sc.slots
    rows = [{"label": str(it.get("label") or ""), "on": it.get("on") is not False}
            for it in (sl.get("rows") or []) if isinstance(it, dict)][:6]
    els, (x, y, w, h) = _pe_split(cx, str(sl.get("title") or ""), str(sl.get("line") or ""))
    c = _pe_colors(cx)
    bar, pad = 58 * u, 36 * u
    n = max(1, len(rows))
    rh = min(104 * u, (h - bar - 2 * pad) / n)
    wh = bar + 2 * pad + n * rh
    wy = y + (h - wh) / 2 if fr.landscape else y
    els.append(_pe_window(cx, x, wy, w, wh, str(sl.get("window") or "")))
    flip_t = 0.4 + n * 0.12 + 0.45
    els.append({"type": "toggles", "x": x + pad, "y": wy + bar + pad, "w": w - 2 * pad, "rows": rows, "row_h": rh,
                "size": min(fr.type("body") * 0.8, rh * 0.38), "font": k.st.text_font, "weight": 600,
                "color": c["text"], "muted": c["muted"], "accent": c["accent"],
                "track": mix(c["surface"], c["text"], 0.18), "rule": c["rule"], "t": 0.4, "stagger": 0.12,
                "flip_t": flip_t, "flip_gap": 0.42, "t0": 0.35, "z": 7})
    n_on = sum(1 for r in rows if r["on"])
    return SceneOut(_pe_center(cx, els, wy + wh), camera=_drift(cx, 0.4),
                    sfx=[(flip_t + j * 0.42, "click") for j in range(n_on)])


def b_pe_code(cx, sc, D, i):
    from .gfx.product import MONO
    from .gfx import prim

    k, fr = cx.kit, cx.fr
    u = fr.u
    sl = sc.slots
    lines = str(sl.get("code") or "").replace("\t", "    ").split("\n")[:12]
    while lines and not lines[-1].strip():
        lines.pop()
    if not fr.landscape:
        lines = _wrap_code(lines, 34 if fr.vertical else 44)[:14]
    els, (x, y, w, h) = _pe_split(cx, str(sl.get("title") or ""), str(sl.get("line") or ""))
    c = _pe_colors(cx)
    bar, pad = 58 * u, 34 * u
    inner = w - 2 * pad
    longest = max([len(s) for s in lines] + [16])
    ratio = prim.mono_cell_width(MONO, 500, 100) / 100
    gutter_cells = len(str(len(lines))) + 2
    size = min(fr.type("body") * 0.62, inner / ((longest + gutter_cells + 1) * ratio))
    size = max(size, 14 * u)
    lh = size * 1.6
    ch_ = min(h - bar - 2 * pad, max(1, len(lines)) * lh)
    wh = bar + 2 * pad + ch_
    wy = y + (h - wh) / 2 if fr.landscape else y
    els.append(_pe_window(cx, x, wy, w, wh, str(sl.get("filename") or "")))
    chars = sum(max(1, len(s)) for s in lines)
    type_t = 0.55
    # Type the whole snippet in about 55 percent of the scene, at 25 to 70 cps.
    cps = min(70.0, max(25.0, chars / max(0.8, (D - type_t) * 0.55)))
    cols = {"text": c["text"], "keyword": c["accent"], "string": cx.look.p.accent2 or "#E9C46A",
            "number": "#4CC9F0", "comment": c["muted"], "call": mix(c["accent"], c["text"], 0.55),
            "gutter": mix(c["surface"], c["text"], 0.3), "caret": c["accent"]}
    if not c["dark"]:
        cols.update({"number": "#1D6FA5", "string": mix(cx.look.p.accent2 or "#B5832A", "#000000", 0.25)})
    els.append({"type": "code_card", "x": x + pad, "y": wy + bar + pad, "w": inner, "lines": lines, "size": size,
                "colors": cols, "t": type_t, "cps": cps, "t0": type_t, "z": 7})
    return SceneOut(_pe_center(cx, els, wy + wh), camera=_drift(cx, 0.3))


def b_pe_api(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    u = fr.u
    sl = sc.slots
    rows = [{"method": str(it.get("method") or "GET"), "path": str(it.get("path") or ""),
             "note": str(it.get("note") or "")} for it in (sl.get("endpoints") or []) if isinstance(it, dict)][:6]
    els, (x, y, w, h) = _pe_split(cx, str(sl.get("title") or ""), str(sl.get("line") or ""))
    c = _pe_colors(cx)
    bar, pad = 58 * u, 34 * u
    n = max(1, len(rows))
    rh = min(96 * u, (h - bar - 2 * pad) / n)
    wh = bar + 2 * pad + n * rh
    wy = y + (h - wh) / 2 if fr.landscape else y
    els.append(_pe_window(cx, x, wy, w, wh, str(sl.get("host") or "")))
    hl = int(_num(sl.get("highlight"), 0)) - 1
    els.append({"type": "api_list", "x": x + pad, "y": wy + bar + pad, "w": w - 2 * pad, "rows": rows, "row_h": rh,
                "size": min(fr.type("body") * 0.62, rh * 0.34), "color": c["text"], "muted": c["muted"],
                "rule": c["rule"], "highlight": hl if 0 <= hl < len(rows) else -1, "hl_color": c["accent"],
                "t": 0.45, "stagger": 0.14, "t0": 0.4, "z": 7})
    return SceneOut(_pe_center(cx, els, wy + wh), camera=_drift(cx, 0.4))


def b_pe_counter(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    sl = sc.slots
    c = _pe_colors(cx)
    tags = [str(it.get("text") or "") for it in (sl.get("tags") or []) if isinstance(it, dict)][:16]
    size = fr.type("body") * 0.55
    band = size * 2.4 if tags else 0.0
    bottom = b - (band + 70 * u if tags else 0.0)
    align = "center" if fr.landscape or k.st.align == "center" else k.st.align
    t_num, d_num = 0.15, 1.4
    num = k.number(_num(sl.get("value")), l, 0, cw, fr.type("numeric") * 1.0, t=t_num, dur=d_num,
                   prefix=str(sl.get("prefix") or ""), suffix=str(sl.get("suffix") or ""), align=align)
    nx, ny, nw, nh = odo_bounds({**num, "y": 0}, fr)
    st = Stack()
    st.add(nh * 1.18, lambda y: [{**num, "y": y, "h": nh * 1.18, "valign": "center"}])
    st.text(k.headline(str(sl.get("label") or ""), l, 0, cw, ch * 0.3, token="h3", t=t_num + d_num * 0.8,
                       align=align, anim="fade_up", font=k.st.text_font, weight=650, color=k.text, max_lines=3), fr,
            gap=30 * u)
    els = st.place(t, bottom)
    if tags:
        els.append({"type": "marquee", "y": b - band - 20 * u, "h": band, "items": tags, "size": size,
                    "font": k.st.text_font, "color": c["text"], "surface": c["surface"], "rule": c["rule"],
                    "speed": 80, "t": t_num + d_num * 0.6, "t0": t_num + d_num * 0.6, "z": 6, "camera": False})
    land_at = t_num + d_num * 0.92
    return SceneOut(els, camera=_drift(cx, 0.5), sfx=[(land_at - 0.6, "riser"), (land_at, "hit")])


# ---------------------------------------------------------------------------
# Chart Story
# ---------------------------------------------------------------------------

def b_chart(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    sl = sc.slots
    v = cx.data or {}
    labels = v.get("labels") or []
    series = v.get("series") or []
    kind = sl.get("chart") or cx.spec.data_options.chart or "auto"
    if kind == "auto":
        kind = v.get("suggested_chart") or "line"
    units = v.get("units") or {}
    do = cx.spec.data_options
    fmt = {"prefix": do.prefix if do.prefix is not None else units.get("prefix", ""),
           "suffix": do.suffix if do.suffix is not None else units.get("suffix", ""),
           "decimals": do.decimals if do.decimals is not None else int(v.get("decimals") or 0),
           "compact": bool(do.compact)}
    els = []
    y = t
    title = str(sl.get("title") or "")
    if title:
        hd = k.headline(title, l, t, cw, fr.type("h3") * 2.5, token="h3", t=0.0, anim="fade_up", max_lines=2,
                        align="left")
        hh = text_height(hd, fr)
        els.append({**hd, "h": hh + 4})
        y = t + hh + 30 * u
    bottom = b - _src_band(cx)
    cs = k.chart_style()
    hl = (sl.get("highlight") or do.highlight or "").strip().lower()
    muted_col = mix(k.p.bg, k.p.text, 0.38)
    if kind == "line" and series:
        hi_idx = next((j for j, s in enumerate(series) if s["name"].strip().lower() == hl), 0)
        ss = []
        for j, s in enumerate(series):
            ss.append({"name": s["name"], "values": s["values"], "highlight": j == hi_idx,
                       "color": k.accent if j == hi_idx else muted_col})
        ann = None
        if sl.get("annotation"):
            at = str(sl.get("annotation_at") or "").strip()
            idx = labels.index(at) if at in labels else len(labels) - 1
            ann = {"index": idx, "text": str(sl["annotation"]), "series": hi_idx}
        draw = min(4.0, max(2.0, D * 0.5))
        els.append({"type": "line_chart", "x": l, "y": y, "w": cw, "h": bottom - y, "labels": labels, "series": ss,
                    "t": 0.3, "axes_dur": 0.4, "draw_dur": draw, "annotation": ann, "format": fmt, **cs,
                    "z": 6, "t0": 0.0})
    elif kind == "donut" and series:
        vals = [x_ or 0 for x_ in series[0]["values"]]
        total = sum(vals) or 1.0
        top = max(range(len(vals)), key=lambda j: vals[j]) if vals else 0
        pal = [accent_on(c, k.p.bg) for c in k.p.chart]
        els.append({"type": "donut", "x": l, "y": y, "w": cw, "h": bottom - y, "labels": labels, "values": vals,
                    "colors": pal, "t": 0.3, "dur": 1.3, "center_text": f"{vals[top] / total * 100:.0f}%" if vals else "",
                    "center_label": str(labels[top]) if labels else "", **cs, "z": 6, "t0": 0.0})
    elif series:
        vals = [x_ or 0 for x_ in series[0]["values"]]
        hi_idx = next((j for j, lb in enumerate(labels) if str(lb).strip().lower() == hl),
                      max(range(len(vals)), key=lambda j: vals[j]) if vals else None)
        orient = "v" if (fr.landscape or len(vals) <= 5) else "h"
        els.append({"type": "bars", "x": l, "y": y, "w": cw, "h": bottom - y, "labels": labels, "values": vals,
                    "highlight": hi_idx, "orientation": orient, "t": 0.3, "dur": 0.6, "stagger": 0.06,
                    "format": fmt, "color": k.accent, "highlight_color": k.accent, "muted_color": muted_col,
                    **cs, "z": 6, "t0": 0.0})
    els += k.source_line(cx.spec.source, t=0.4)
    return SceneOut(els)


def b_text_center(cx, sc, D, i):
    sl = sc.slots
    text = str(sl.get("text") or "")
    tok = "display" if len(text.split()) <= 3 else ("h1" if len(text.split()) <= 9 else "h2")
    els = _hook_block(cx, text, "", token=tok)
    if cx.tpl.requires_source and sc.type == "takeaway":
        els += cx.kit.source_line(cx.spec.source, t=0.5)
    return SceneOut(els, camera=_drift(cx))


# ---------------------------------------------------------------------------
# Market Recap
# ---------------------------------------------------------------------------

def _market_colors(cx: BuildCtx) -> tuple[str, str]:
    p = cx.look.p
    return accent_on(p.positive, p.bg), accent_on(p.negative, p.bg)


def b_mkt_date(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    sl = sc.slots
    st = Stack()
    st.add(k.kicker("Market recap", l, 0, cw)[1], lambda y: k.kicker("Market recap", l, y, cw, t=0.0)[0])
    st.text(k.headline(str(sl.get("date") or ""), l, 0, cw, ch * 0.2, token="h2", t=0.1, font=k.st.numeric_font,
                       weight=k.st.numeric_weight, color=k.accent, max_lines=2, anim="fade_up"), fr, gap=34 * u)
    head = str(sl.get("headline") or "")
    st.text(k.headline(head, l, 0, cw, ch * 0.45, token="h1", t=0.35, emph=k.emph_indices(head, auto=True)), fr,
            gap=26 * u)
    return SceneOut(st.place(t, b), camera=_drift(cx))


def b_mkt_tiles(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    v = cx.data or {}
    items = (v.get("items") or [])[:6]
    pos, neg = _market_colors(cx)
    els = []
    heading = str(sc.slots.get("heading") or "")
    y = t
    if heading:
        kel, kh = k.kicker(heading, l, t, cw, t=0.0)
        els += kel
        y = t + kh + 40 * u
    cols = 3 if fr.landscape and len(items) > 4 else (2 if len(items) > 1 else 1)
    els.append({"type": "tiles", "x": l, "y": y, "w": cw, "h": b - _src_band(cx) - y, "items": items, "cols": cols,
                "t": 0.2, "stagger": 0.05, "count_dur": 0.9, "card": k.card_fill(), "text": k.text, "muted": k.muted,
                "positive": pos, "negative": neg, "font": k.st.label_font, "value_font": k.data_font,
                "value_format": {"decimals": 2}, "z": 6, "t0": 0.0})
    els += k.source_line(cx.spec.source, t=0.5)
    return SceneOut(els)


def b_mkt_movers(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    items = [it for it in (cx.data or {}).get("items") or [] if it.get("change") is not None]
    gainers = sorted([it for it in items if it["change"] > 0], key=lambda it: -it["change"])[:3]
    losers = sorted([it for it in items if it["change"] < 0], key=lambda it: it["change"])[:3]
    pos, neg = _market_colors(cx)
    els = []
    heading = str(sc.slots.get("heading") or "")
    y = t
    if heading:
        kel, kh = k.kicker(heading, l, t, cw, t=0.0)
        els += kel
        y = t + kh + 40 * u
    bottom = b - _src_band(cx)
    side = fr.landscape or fr.orientation == "square"
    sections = [("Gainers", gainers, pos, True), ("Losers", losers, neg, False)]
    if side:
        colw = (cw - 60 * u) / 2
        boxes = [(l, y, colw, bottom - y), (l + colw + 60 * u, y, colw, bottom - y)]
    else:
        hh = (bottom - y - 50 * u) / 2
        boxes = [(l, y, cw, hh), (l, y + hh + 50 * u, cw, hh)]
    size = fr.type("h3") * 0.7
    tt = 0.15
    for (title, rows, col, up), (bx, by, bw, bh) in zip(sections, boxes):
        els.append(k.meta(title.upper(), bx, by, bw, t=tt, color=col, align="left"))
        row_h = min(size * 2.0, (bh - 70 * u) / 3)
        for j, it in enumerate(rows):
            ry = by + 70 * u + j * row_h
            tt += 0.08
            els.append({"type": "shape", "x": bx, "y": ry + row_h - 2 * u, "w": bw, "h": max(1, 1.5 * u),
                        "color": mix(k.p.bg, k.p.text, 0.2), "anim": {"type": "grow_x", "t": tt, "dur": 0.4}, "t0": tt,
                        "z": 4})
            els.append(k.headline(str(it["name"]), bx, ry, bw * 0.62, row_h, token="h3", size=size, t=tt,
                                  align="left", valign="center", font=k.st.text_font, weight=650, color=k.text,
                                  anim="fade_up", max_lines=1))
            tri = size * 0.5
            chg = f"{'+' if up else ''}{it['change']:.2f}%"
            els.append({"type": "shape", "shape": "tri_up" if up else "tri_down", "x": bx + bw - size * 4.6,
                        "y": ry + (row_h - tri) / 2, "w": tri, "h": tri * 0.85, "color": col,
                        "anim": {"type": "fade", "t": tt + 0.1, "dur": 0.2}, "t0": tt, "z": 6})
            els.append(k.headline(chg, bx + bw * 0.5, ry, bw * 0.5, row_h, token="h3", size=size, t=tt + 0.1,
                                  align="right", valign="center", font=k.data_font, weight=800, color=col,
                                  anim="fade_up", max_lines=1))
        if not rows:
            els.append(k.body("None today", bx, by + 70 * u, bw, row_h, t=tt, align="left"))
    els += k.source_line(cx.spec.source, t=0.5)
    return SceneOut(els)


def b_mkt_spark(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    items = (cx.data or {}).get("items") or []
    want = str(sc.slots.get("name") or "").strip().lower()
    it = next((x_ for x_ in items if x_["name"].strip().lower() == want and x_.get("spark")), None) or \
        next((x_ for x_ in items if x_.get("spark")), None)
    els = []
    if it is None:
        return SceneOut(_hook_block(cx, str(sc.slots.get("caption") or "No chart data"), "", token="h2"))
    pos, neg = _market_colors(cx)
    up = (it.get("change") or 0) >= 0
    kel, kh = k.kicker(it["name"], l, t, cw, t=0.0)
    els += kel
    y = t + kh + 30 * u
    if sc.slots.get("caption"):
        hd = k.headline(str(sc.slots["caption"]), l, y, cw, fr.type("h3") * 2.6, token="h3", t=0.1, max_lines=2,
                        align="left", anim="fade_up", font=k.st.text_font, weight=650)
        hh = text_height(hd, fr)
        els.append({**hd, "h": hh + 4})
        y += hh + 30 * u
    bottom = b - _src_band(cx)
    cs = k.chart_style()
    els.append({"type": "line_chart", "x": l, "y": y, "w": cw, "h": bottom - y, "labels": [""] * len(it["spark"]),
                "series": [{"name": it["name"], "values": it["spark"], "highlight": True, "color": pos if up else neg}],
                "t": 0.2, "axes_dur": 0.3, "draw_dur": 0.9, "format": {"decimals": 2, "compact": True}, **cs,
                "zero": False, "z": 6, "t0": 0.0})
    els += k.source_line(cx.spec.source, t=0.5)
    return SceneOut(els)


def b_mkt_watch(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    items = [str(x_.get("text") or "") for x_ in sc.slots.get("items") or [] if isinstance(x_, dict)][:3]
    st = Stack()
    st.add(k.kicker("What to watch", l, 0, cw)[1], lambda y: k.kicker("What to watch", l, y, cw, t=0.0)[0])
    for j, text in enumerate(items):
        tt = 0.2 + j * 0.15
        el = k.headline(text, l + 90 * u, 0, cw - 90 * u, ch * 0.2, token="h3", t=tt, align="left", anim="fade_up",
                        font=k.st.text_font, weight=650, max_lines=3)
        h = text_height(el, fr)

        def mk(y, el=el, h=h, j=j, tt=tt):
            return [{**el, "y": y, "h": h + 4},
                    {**k.headline(f"{j + 1}", l, y, 70 * u, h, token="h3", t=tt, align="left", color=k.accent,
                                  font=k.st.numeric_font, weight=k.st.numeric_weight, anim="fade_up", max_lines=1)}]

        st.add(h, mk, gap=40 * u)
    return SceneOut(st.place(t, b), camera=_drift(cx, 0.5))


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

def b_tl_title(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    sl = sc.slots
    st = Stack()
    title = str(sl.get("title") or "")
    st.text(k.headline(title, l, 0, cw, ch * 0.55, token="h1", t=0.0, emph=k.emph_indices(title, auto=True)), fr)
    if sl.get("subtitle"):
        st.text(k.body(str(sl["subtitle"]), l, 0, cw, ch * 0.2, t=0.35), fr, gap=26 * fr.u)
    return SceneOut(st.place(t, b), camera=_drift(cx))


def b_tl_track(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    items = []
    for it in sc.slots.get("items") or []:
        if not isinstance(it, dict):
            continue
        items.append({"date": it.get("date", ""), "title": it.get("title", ""), "desc": it.get("desc"),
                      "src": cx.image(it.get("image"))})
    n = max(1, len(items))
    per = max(2.5, (D - 0.9) / n)
    vertical = fr.vertical or fr.aspect == "4:5"
    st = k.st
    return SceneOut([{
        "type": "timeline_track", "x": l, "y": t, "w": cw, "h": b - t, "items": items,
        "orientation": "v" if vertical else "h", "t": 0.4, "per": per, "move": cx.look.t(0.7),
        "text": k.text, "muted": k.muted, "accent": k.accent, "rule": k.p.rule, "date_font": st.numeric_font,
        "date_weight": st.numeric_weight, "title_font": st.display_font, "title_weight": st.display_weight,
        "desc_font": st.text_font, "date_size": fr.type("h1") * (1.05 if vertical else 1.0),
        "title_size": fr.type("h3") * 0.85, "desc_size": fr.type("caption") * 0.75, "z": 6, "t0": 0.0,
        "camera": False,
    }])


# ---------------------------------------------------------------------------
# Audiogram
# ---------------------------------------------------------------------------

def b_ag_cover(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    sl = sc.slots
    art = cx.image(sl.get("art"))
    st = Stack()
    side = min(cw * 0.78, ch * 0.42)
    if art:
        st.add(side, lambda y: [{"type": "image", "src": art, "x": l + (cw - side) / 2, "y": y, "w": side, "h": side,
                                 "radius": max(8 * u, k.st.radius * u), "zoom": [1.0, 1.04], "shadow": True,
                                 "anim": {"type": "scale", "t": 0.0, "dur": 0.5}, "z": 6}])
    st.text(k.headline(str(sl.get("show") or ""), l, 0, cw, ch * 0.2, token="h2", t=0.15, align="center",
                       max_lines=2), fr, gap=50 * u)
    if sl.get("episode"):
        st.text(k.body(str(sl["episode"]), l, 0, cw, ch * 0.15, t=0.35, align="center", color=k.text), fr, gap=20 * u)
    if sl.get("guest"):
        st.text(k.meta(str(sl["guest"]), l, 0, cw, t=0.5, align="center"), fr, gap=14 * u)
    return SceneOut(st.place(t, b), camera=_drift(cx, 0.6))


def b_ag_clip(cx, sc, D, i):
    k, fr = cx.kit, cx.fr
    l, t, r, b, cw, ch = _rect(cx)
    u = fr.u
    cover = next((s for s in cx.spec.scenes if s.type == "cover"), None)
    art = cx.image(cover.slots.get("art")) if cover else None
    show = str(cover.slots.get("show") or "") if cover else ""
    episode = str(cover.slots.get("episode") or "") if cover else ""
    els = []
    head_h = 150 * u
    x_text = l
    if art:
        els.append({"type": "image", "src": art, "x": l, "y": t, "w": head_h, "h": head_h, "radius": 14 * u,
                    "anim": {"type": "fade", "t": 0.0, "dur": 0.3}, "z": 6})
        x_text = l + head_h + 30 * u
    els.append(k.headline(show, x_text, t + 6 * u, r - x_text, head_h * 0.55, token="h3", t=0.0, align="left",
                          max_lines=1, anim="fade_up"))
    if episode:
        els.append(k.meta(episode, x_text, t + head_h * 0.6, r - x_text, t=0.1, align="left"))
    words = cx.vo.get(sc.id) or []
    wave_h = min(260 * u, ch * 0.26)
    cy = t + head_h + (b - t - head_h) * 0.42
    a = cx.audio or {}
    els.append({"type": "waveform", "x": l, "y": cy - wave_h / 2, "w": cw, "h": wave_h, "amps": a.get("amps"),
                "offset": 0.0,
                "bars": 44 if fr.vertical else 64, "color": k.accent, "color2": mix(k.accent, k.text, 0.35),
                "seed": cx.look.seed, "z": 6, "t0": 0.0, "camera": False})
    if words:
        size = fr.type("h3") * (1.0 if fr.vertical else 0.9)
        els.append({"type": "live_caption", "words": words, "x": l, "y": cy + wave_h / 2 + 140 * u, "w": cw,
                    "max_chars": 24 if fr.vertical else 32, "font": k.st.display_font,
                    "weight": k.st.display_weight, "size": size, "color": k.text, "accent": k.accent,
                    "align": "center", "upper": k.st.display_upper, "z": 8, "camera": False})
    els.append({"type": "shape", "x": l, "y": b - 8 * u, "w": cw, "h": 6 * u, "color": mix(k.p.bg, k.p.text, 0.18),
                "z": 4, "anim": {"type": "none"}, "camera": False})
    els.append({"type": "shape", "x": l, "y": b - 8 * u, "w": cw, "h": 6 * u, "color": k.accent, "z": 5,
                "anim": {"type": "grow_x", "t": 0.0, "dur": max(0.5, D), "ease": "linear"}, "camera": False})
    return SceneOut(els)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

BUILDERS: dict[tuple[str, str], Callable] = {
    ("*", "source_card"): b_source_card,
    ("*", "disclaimer"): b_disclaimer,
    ("*", "end_card"): b_end_card,
    ("*", "logo_sting"): b_logo_sting,
    ("*", "poll"): b_poll,
    ("*", "next_part"): b_next_part,
    ("big_number", "hook"): b_big_hook,
    ("big_number", "reveal"): b_big_reveal,
    ("big_number", "meaning"): b_big_meaning,
    ("big_number", "takeaway"): b_big_takeaway,
    ("kinetic_quote", "hook"): b_quote_line,
    ("kinetic_quote", "line"): b_quote_line,
    ("kinetic_quote", "payoff"): b_quote_line,
    ("kinetic_quote", "attribution"): b_quote_attr,
    ("bar_race", "title"): b_race_title,
    ("bar_race", "race"): b_race,
    ("listicle", "hook"): b_list_hook,
    ("listicle", "item"): b_list_item,
    ("listicle", "cta"): b_list_cta,
    ("versus", "intro"): b_vs_intro,
    ("versus", "round"): b_vs_round,
    ("versus", "verdict"): b_vs_verdict,
    ("promo", "claim"): b_promo_claim,
    ("promo", "feature"): b_promo_feature,
    ("promo", "recap"): b_promo_recap,
    ("product_explainer", "hook"): b_big_hook,
    ("product_explainer", "problem"): b_pe_problem,
    ("product_explainer", "hub"): b_pe_hub,
    ("product_explainer", "app"): b_pe_app,
    ("product_explainer", "code"): b_pe_code,
    ("product_explainer", "api"): b_pe_api,
    ("product_explainer", "counter"): b_pe_counter,
    ("chart_story", "question"): b_text_center,
    ("chart_story", "chart"): b_chart,
    ("chart_story", "takeaway"): b_text_center,
    ("market_recap", "date"): b_mkt_date,
    ("market_recap", "tiles"): b_mkt_tiles,
    ("market_recap", "movers"): b_mkt_movers,
    ("market_recap", "spark"): b_mkt_spark,
    ("market_recap", "watch"): b_mkt_watch,
    ("timeline", "title"): b_tl_title,
    ("timeline", "track"): b_tl_track,
    ("audiogram", "cover"): b_ag_cover,
    ("audiogram", "clip"): b_ag_clip,
}


def builder_for(template_id: str, scene_type: str) -> Optional[Callable]:
    return BUILDERS.get((template_id, scene_type)) or BUILDERS.get(("*", scene_type))
