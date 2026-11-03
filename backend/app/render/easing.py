"""Easing curves (CSS semantics) and interpolation helpers."""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Callable

EaseFn = Callable[[float], float]


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def cubic_bezier(x1: float, y1: float, x2: float, y2: float) -> EaseFn:
    """CSS cubic-bezier(x1, y1, x2, y2), solved for x with Newton steps and a
    bisection fallback (the same approach browsers use)."""

    cx = 3.0 * x1
    bx = 3.0 * (x2 - x1) - cx
    ax = 1.0 - cx - bx
    cy = 3.0 * y1
    by = 3.0 * (y2 - y1) - cy
    ay = 1.0 - cy - by

    def sample_x(t: float) -> float:
        return ((ax * t + bx) * t + cx) * t

    def sample_y(t: float) -> float:
        return ((ay * t + by) * t + cy) * t

    def sample_dx(t: float) -> float:
        return (3.0 * ax * t + 2.0 * bx) * t + cx

    def solve(x: float) -> float:
        t = x
        for _ in range(8):
            err = sample_x(t) - x
            if abs(err) < 1e-7:
                return t
            d = sample_dx(t)
            if abs(d) < 1e-6:
                break
            t -= err / d
        lo, hi = 0.0, 1.0
        t = x
        for _ in range(60):
            v = sample_x(t)
            if abs(v - x) < 1e-7:
                return t
            if v < x:
                lo = t
            else:
                hi = t
            t = (lo + hi) / 2.0
        return t

    def ease(p: float) -> float:
        if p <= 0.0:
            return 0.0
        if p >= 1.0:
            return 1.0
        return sample_y(solve(p))

    return ease


def _linear(p: float) -> float:
    return clamp(p)


_CURVES: dict[str, EaseFn] = {
    "linear": _linear,
    "ease_out": cubic_bezier(0.0, 0.0, 0.58, 1.0),
    "ease_in_out": cubic_bezier(0.42, 0.0, 0.58, 1.0),
    "bezier_out": cubic_bezier(0.16, 1.0, 0.3, 1.0),
}


@lru_cache(maxsize=None)
def get_easing(name: str) -> EaseFn:
    return _CURVES.get(name, _CURVES["bezier_out"])


def ease(name: str, p: float) -> float:
    return get_easing(name)(clamp(p))


def back_out(p: float, overshoot: float = 1.70158) -> float:
    """easeOutBack, used by the pop animation."""
    p = clamp(p) - 1.0
    return p * p * ((overshoot + 1.0) * p + overshoot) + 1.0


def interp(x: float, x0: float, x1: float, y0: float, y1: float, easing: str = "linear") -> float:
    """Remotion style interpolate with clamped extrapolation."""
    if x1 == x0:
        return y1 if x >= x1 else y0
    p = ease(easing, (x - x0) / (x1 - x0))
    return y0 + (y1 - y0) * p


def perceptual(y0: float, y1: float, p: float) -> float:
    """Geometric interpolation for scales (Remotion output "perceptual-scale")."""
    if y0 <= 0 or y1 <= 0:
        return y0 + (y1 - y0) * p
    return y0 * math.exp(math.log(y1 / y0) * p)
