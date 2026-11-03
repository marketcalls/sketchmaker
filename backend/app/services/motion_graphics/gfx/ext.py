"""Additive extension of the shared render engine for motion graphics.

app/render is not modified. This module

* defines one extra overlay kind, ``mg_scene`` (a scene: a list of motion
  graphics elements, a scene transition in and out, and a camera drift),
* defines ``MGTimeline``, a subclass of app.render.Timeline whose overlay
  union also accepts ``mg_scene`` (render_timeline and preview_frame accept a
  Timeline instance as is, so a subclass passes straight through), and
* registers the ``mg_scene`` renderer in app.render.overlays.RENDERERS at
  import time (a dict insert; the engine looks renderers up by kind).

Elements draw themselves as RGBA sprites in scene coordinates (output
pixels); the scene applies the camera (zoom about an origin), the transition
transform (push, slide, zoom, wipe, fade) and opacity, and hands the engine
plain sprite ops. A future engine release can adopt this as a first-class
plugin point; until then keep MGTimeline instances in memory (do not
round-trip them through Timeline.model_validate).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union, get_args

from pydantic import Field

from app.render import overlays as _ov
from app.render import timeline as _tl
from app.render.overlays import Op, Renderer

from ..design import E
from . import prim


class MGSceneOverlay(_tl._OverlayBase):
    kind: Literal["mg_scene"] = "mg_scene"
    params: dict[str, Any] = Field(default_factory=dict)


_BASE_KINDS = get_args(get_args(_tl.Overlay)[0])
MGOverlay = Annotated[Union[(*_BASE_KINDS, MGSceneOverlay)], Field(discriminator="kind")]


class MGTimeline(_tl.Timeline):
    overlays: list[MGOverlay] = Field(default_factory=list)  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Element registry
# ---------------------------------------------------------------------------

ELEMENTS: dict[str, type] = {}


def element(name: str):
    def deco(cls):
        ELEMENTS[name] = cls
        cls.type_name = name
        return cls

    return deco


class El:
    """Base element. ``p`` is the element's params dict; times are content
    seconds of the scene (0 = the scene's first content frame)."""

    type_name = "base"

    def __init__(self, p: dict, sc: "SceneRenderer"):
        self.p = p
        self.sc = sc
        self.W, self.H = sc.W, sc.H
        self.u = sc.u
        self.t0 = float(p.get("t0", 0.0))
        self.t1 = p.get("t1")  # None: scene end
        self.z = int(p.get("z", 0))
        self.camera = bool(p.get("camera", True))  # follows the scene camera drift

    def end(self) -> float:
        return float(self.t1) if self.t1 is not None else 1e9  # the overlay window bounds it

    def visible(self, c: float) -> bool:
        return self.t0 - 1e-6 <= c < self.end()

    def out_state(self, c: float) -> tuple[float, float]:
        """(alpha, dy) of the generic exit: params out = {t, dur, type}."""
        o = self.p.get("out")
        if not o:
            return 1.0, 0.0
        t = float(o.get("t", 0.0))
        d = max(1e-3, float(o.get("dur", 0.2)))
        q = E(o.get("ease", "exit"), (c - t) / d)
        if q <= 0:
            return 1.0, 0.0
        kind = o.get("type", "fade_up")
        if kind == "fade":
            return 1.0 - q, 0.0
        return 1.0 - q, -float(o.get("dist", 24)) * self.u * q

    def sprites(self, c: float) -> list[tuple]:  # [(img, x, y)]
        return []


# ---------------------------------------------------------------------------
# Scene renderer
# ---------------------------------------------------------------------------

class SceneRenderer(Renderer):
    """Renders one ``mg_scene`` overlay.

    params:
      elements: [ {type, ...} ]
      lead_in, lead_out: seconds of transition overlap before and after content
      content_start: seconds after the overlay start where content time 0 is
                     (default lead_in; 0 lets elements animate during a push)
      content_dur: seconds of content
      enter, exit: {type: cut|fade|push_left|push_up|slide|zoom|wipe, dur, ease}
      camera: {drift: fraction, ox, oy} or None
    """

    def __init__(self, ov, lay, tl):
        super().__init__(ov, lay, tl)
        p = ov.params
        self.W, self.H = tl.width, tl.height
        self.u = min(self.W, self.H) / 1080.0
        self.lead_in = float(p.get("lead_in", 0.0))
        self.lead_out = float(p.get("lead_out", 0.0))
        self.content_start = float(p.get("content_start", self.lead_in))
        self.content_dur = float(p.get("content_dur", ov.duration - self.lead_in - self.lead_out))
        self.enter_t = p.get("enter") or {"type": "cut"}
        self.exit_t = p.get("exit") or {"type": "cut"}
        self.cam = p.get("camera")
        self.els: list[El] = []
        for i, ep in enumerate(p.get("elements") or []):
            cls = ELEMENTS.get(ep.get("type"))
            if cls is None:
                continue
            el = cls(ep, self)
            el._order = i
            self.els.append(el)
        self.els.sort(key=lambda e: (e.z, e._order))

    # The generic animator is bypassed entirely.
    def ops(self, t: float) -> list[Op]:
        ov = self.ov
        lt = t - ov.start
        if lt < 0 or lt >= ov.duration:
            return []
        c = lt - self.content_start
        dx, dy, s, a, clip = self._transition(lt)
        if a <= 0.003:
            return []
        zc = 1.0
        ox, oy = self.W / 2.0, self.H / 2.0
        if self.cam and self.content_dur > 0:
            drift = float(self.cam.get("drift", 0.0))
            prog = E("camera", lt / max(0.1, ov.duration))
            zc = 1.0 + drift * prog
            ox = float(self.cam.get("ox", ox))
            oy = float(self.cam.get("oy", oy))
        out: list[Op] = []
        cx, cy = self.W / 2.0, self.H / 2.0
        for el in self.els:
            if not el.visible(c):
                continue
            for item in el.sprites(c):
                img, x, y = item[0], item[1], item[2]
                if img is None:
                    continue
                k = zc if el.camera else 1.0
                tot = k * s
                if abs(tot - 1.0) > 0.0015:
                    # camera about (ox, oy), then transition scale about the frame center
                    x1 = ox + (x - ox) * k
                    y1 = oy + (y - oy) * k
                    x = cx + (x1 - cx) * s
                    y = cy + (y1 - cy) * s
                    img = prim.scaled(img, tot, fast=abs(tot - 1.0) < 0.06)
                x += dx
                y += dy
                if a < 0.999:
                    img = prim.alpha(img, a)
                if clip is not None:
                    r = prim.crop_to(img, x, y, clip)
                    if r is None:
                        continue
                    img, x, y = r
                out.append(Op("sprite", img, int(round(x)), int(round(y))))
        return out

    def _transition(self, lt: float):
        """(dx, dy, scale, alpha, clip) for the scene at local time lt."""
        D = self.ov.duration
        dx = dy = 0.0
        s = 1.0
        a = 1.0
        clip = None
        en, ex = self.enter_t, self.exit_t
        tin = float(en.get("dur", 0.0)) if en.get("type", "cut") != "cut" else 0.0
        tout = float(ex.get("dur", 0.0)) if ex.get("type", "cut") != "cut" else 0.0
        W, H = self.W, self.H
        if tin > 0 and lt < tin:
            p = E(en.get("ease", "camera_strong"), lt / tin)
            k = en.get("type")
            if k == "push_left":
                dx += W * (1.0 - p)
            elif k == "push_up":
                dy += H * (1.0 - p)
            elif k == "slide":
                dy += 0.05 * H * (1.0 - p)
                a *= min(1.0, p * 1.6)
            elif k == "zoom":
                s *= 0.9 + 0.1 * p
                a *= p
            elif k == "wipe":
                clip = (0.0, 0.0, W * p, float(H))
            else:  # fade
                a *= p
        if tout > 0 and lt > D - tout:
            q = E(ex.get("ease", "camera_strong"), (lt - (D - tout)) / tout)
            k = ex.get("type")
            if k == "push_left":
                dx -= W * q
            elif k == "push_up":
                dy -= H * q
            elif k == "slide":
                dy -= 0.025 * H * q
                a *= max(0.0, 1.0 - q * 1.6)
            elif k == "zoom":
                s *= 1.0 + 0.12 * q
                a *= 1.0 - q
            elif k == "wipe":
                clip = (W * q, 0.0, float(W), float(H))
            else:
                a *= 1.0 - q
        return dx, dy, s, a, clip


def register() -> None:
    _ov.RENDERERS.setdefault("mg_scene", SceneRenderer)


register()
