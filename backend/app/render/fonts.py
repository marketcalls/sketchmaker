"""Bundled font registry (all SIL Open Font License, see fonts/*/OFL.txt).

Families and the weights they cover:

* Inter (variable 100 to 900)                  fonts/inter
* Poppins (static 500, 600, 700, 800)          fonts/poppins
* Bricolage Grotesque (variable 200 to 800)    fonts/bricolage   default display font
* Space Grotesk (variable 300 to 700)          fonts/spacegrotesk
* Playfair Display (variable 400 to 900)       fonts/playfair
* Anton (400, a heavy condensed face)          fonts/anton       captions
* Bebas Neue (400, condensed caps)             fonts/bebas
* Noto Sans Devanagari (variable 100 to 900)   fonts/devanagari  Hindi and fallback

Unknown family names fall back to Inter. Text containing Devanagari switches
to Noto Sans Devanagari automatically (it also covers Latin), so mixed Hindi
and English lines render. Complex shaping needs Pillow built with raqm
(the PyPI wheels include it; it loads the system fribidi at runtime).
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from PIL import ImageFont

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


@dataclass(frozen=True)
class Family:
    name: str
    variable: Optional[str] = None  # relative path of a variable font
    statics: dict[int, str] = field(default_factory=dict)  # weight -> relative path
    wmin: int = 400
    wmax: int = 400
    devanagari: bool = False


FAMILIES: dict[str, Family] = {
    "inter": Family("Inter", variable="inter/Inter-Variable.ttf", wmin=100, wmax=900),
    "poppins": Family(
        "Poppins",
        statics={
            500: "poppins/Poppins-Medium.ttf",
            600: "poppins/Poppins-SemiBold.ttf",
            700: "poppins/Poppins-Bold.ttf",
            800: "poppins/Poppins-ExtraBold.ttf",
        },
        wmin=500,
        wmax=800,
    ),
    "bricolagegrotesque": Family(
        "Bricolage Grotesque", variable="bricolage/BricolageGrotesque-Variable.ttf", wmin=200, wmax=800
    ),
    "spacegrotesk": Family("Space Grotesk", variable="spacegrotesk/SpaceGrotesk-Variable.ttf", wmin=300, wmax=700),
    "playfairdisplay": Family(
        "Playfair Display", variable="playfair/PlayfairDisplay-Variable.ttf", wmin=400, wmax=900
    ),
    "anton": Family("Anton", statics={400: "anton/Anton-Regular.ttf"}),
    "bebasneue": Family("Bebas Neue", statics={400: "bebas/BebasNeue-Regular.ttf"}),
    # Code cards in motion graphics (product explainers).
    "jetbrainsmono": Family("JetBrains Mono", variable="jetbrainsmono/JetBrainsMono-Variable.ttf", wmin=100, wmax=800),
    "notosansdevanagari": Family(
        "Noto Sans Devanagari",
        variable="devanagari/NotoSansDevanagari-Variable.ttf",
        wmin=100,
        wmax=900,
        devanagari=True,
    ),
}

ALIASES: dict[str, str] = {
    "bricolage": "bricolagegrotesque",
    "display": "bricolagegrotesque",
    "space": "spacegrotesk",
    "playfair": "playfairdisplay",
    "serif": "playfairdisplay",
    "sans": "inter",
    "sansserif": "inter",
    "bebas": "bebasneue",
    "condensed": "anton",
    "devanagari": "notosansdevanagari",
    "notodevanagari": "notosansdevanagari",
    "hindi": "notosansdevanagari",
    "anekdevanagari": "notosansdevanagari",
}

DEFAULT_FAMILY = "inter"

_DEVANAGARI = re.compile(r"[\u0900-\u097F\uA8E0-\uA8FF]")
_lock = threading.Lock()


def family_key(name: Optional[str]) -> str:
    if not name:
        return DEFAULT_FAMILY
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    key = ALIASES.get(key, key)
    return key if key in FAMILIES else DEFAULT_FAMILY


def needs_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI.search(text or ""))


def resolve(name: Optional[str], text: str = "") -> str:
    """Family key to use for ``text`` (switches to Devanagari when needed)."""
    key = family_key(name)
    if needs_devanagari(text) and not FAMILIES[key].devanagari:
        return "notosansdevanagari"
    return key


def _axis_name(axis: dict) -> str:
    n = axis.get("name")
    if isinstance(n, bytes):
        n = n.decode("latin-1", "replace")
    return str(n or "").lower()


@lru_cache(maxsize=256)
def get_font(key: str, weight: int, size: int) -> ImageFont.FreeTypeFont:
    """A FreeType font for a registry key at ``weight`` and ``size`` px."""
    fam = FAMILIES.get(key) or FAMILIES[DEFAULT_FAMILY]
    size = max(4, int(size))
    w = max(fam.wmin, min(fam.wmax, int(weight or 400)))
    with _lock:
        if fam.variable:
            font = ImageFont.truetype(os.path.join(FONT_DIR, fam.variable), size)
            try:
                axes = font.get_variation_axes()
                values = []
                for axis in axes:
                    name = _axis_name(axis)
                    lo, hi = axis["minimum"], axis["maximum"]
                    if "weight" in name:
                        values.append(max(lo, min(hi, w)))
                    elif "optical" in name:
                        # Display sizes want the large optical master.
                        values.append(max(lo, min(hi, size * 0.75)))
                    else:
                        values.append(axis.get("default", lo))
                font.set_variation_by_axes(values)
            except (OSError, AttributeError, KeyError):
                pass
            return font
        best = min(fam.statics, key=lambda k: (abs(k - w), -k))
        return ImageFont.truetype(os.path.join(FONT_DIR, fam.statics[best]), size)


def font_for(name: Optional[str], weight: int, size: float, text: str = "") -> ImageFont.FreeTypeFont:
    return get_font(resolve(name, text), int(weight or 400), int(round(size)))


def available_families() -> list[dict]:
    """For UIs: [{key, name, weights: [min, max]}]."""
    return [
        {"key": k, "name": f.name, "weights": [f.wmin, f.wmax]}
        for k, f in FAMILIES.items()
    ]
