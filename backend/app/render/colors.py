"""Color parsing: #RGB, #RGBA, #RRGGBB, #RRGGBBAA, rgb(), rgba(), a few names."""

from __future__ import annotations

import re
from functools import lru_cache

RGBA = tuple[int, int, int, int]

_NAMES: dict[str, RGBA] = {
    "white": (255, 255, 255, 255),
    "black": (0, 0, 0, 255),
    "transparent": (0, 0, 0, 0),
    "red": (255, 0, 0, 255),
    "green": (0, 128, 0, 255),
    "blue": (0, 0, 255, 255),
}

_FUNC = re.compile(r"^rgba?\(\s*([^)]*)\)$", re.I)


@lru_cache(maxsize=1024)
def parse_color(value: str | None, default: RGBA = (255, 255, 255, 255)) -> RGBA:
    if not value:
        return default
    s = value.strip().lower()
    if s in _NAMES:
        return _NAMES[s]
    if s.startswith("#"):
        h = s[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            h += "ff"
        if len(h) == 8:
            try:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))
            except ValueError:
                return default
        return default
    m = _FUNC.match(s)
    if m:
        parts = [p.strip() for p in m.group(1).replace("/", ",").split(",") if p.strip()]
        try:
            rgb = [int(round(float(p.rstrip("%")) * (2.55 if p.endswith("%") else 1))) for p in parts[:3]]
            a = 255
            if len(parts) > 3:
                ap = parts[3]
                af = float(ap.rstrip("%")) / (100.0 if ap.endswith("%") else 1.0)
                a = int(round(max(0.0, min(1.0, af)) * 255))
            r, g, b = (max(0, min(255, c)) for c in rgb)
            return (r, g, b, a)
        except (ValueError, IndexError):
            return default
    return default


def with_alpha(c: RGBA, alpha: float) -> RGBA:
    return (c[0], c[1], c[2], int(round(c[3] * max(0.0, min(1.0, alpha)))))


def rgb(c: RGBA) -> tuple[int, int, int]:
    return (c[0], c[1], c[2])


def luminance(c: RGBA) -> float:
    def lin(v: int) -> float:
        x = v / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])


def readable_on(c: RGBA) -> RGBA:
    """Black or white text, whichever reads better on ``c``."""
    return (10, 12, 18, 255) if luminance(c) > 0.35 else (255, 255, 255, 255)
