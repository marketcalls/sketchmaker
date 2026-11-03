"""Build the house colour grade looks as 33 point .cube LUTs.

    python -m app.render.looks.build_looks        (from backend/)

Run offline; the .cube files it writes next to this script are committed and
read at render time by app/render/grade.py. Pure Python (no numpy), so the
same recipe gives the same files on any machine.

Every op takes and returns Rec.709 display RGB in 0 to 1, as in the
scenario-video-color-grade skill (references/ops.md): white balance in linear
light, a filmic contrast curve around a pivot, levels, luma preserving
saturation and vibrance, split toning, single hue range changes, a channel mix
for black and white, and a soft highlight shoulder. Generated footage is
already contrasty and saturated, so these recipes sit at about two thirds of
the skill's "normal" ranges: a look should read as a grade, never as a filter.

Neutral is the identity and has no file: the engine skips the grade.
"""

from __future__ import annotations

import colorsys
import math
import os

SIZE = 33
HERE = os.path.dirname(os.path.abspath(__file__))
LUMA = (0.2126, 0.7152, 0.0722)


def _clip(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def _lin(v: float) -> float:
    return max(0.0, v) ** 2.4


def _disp(v: float) -> float:
    return max(0.0, v) ** (1 / 2.4)


def _luma(c) -> float:
    return c[0] * LUMA[0] + c[1] * LUMA[1] + c[2] * LUMA[2]


def _smooth(e0: float, e1: float, x: float) -> float:
    t = _clip((x - e0) / (e1 - e0))
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------
# Ops (ops.md)
# ---------------------------------------------------------------------------

def white_balance(c, temp=0.0, tint=0.0):
    """temp > 0 warmer, tint > 0 magenta; gains in linear light."""
    g = (1 + temp, 1 - tint, 1 - temp)
    return tuple(_disp(_lin(c[i]) * g[i]) for i in range(3))


def exposure(c, stops=0.0):
    k = 2.0 ** stops
    return tuple(_disp(_lin(v) * k) for v in c)


def cdl(c, slope=(1, 1, 1), offset=(0, 0, 0), power=(1, 1, 1)):
    return tuple(max(0.0, c[i] * slope[i] + offset[i]) ** power[i] for i in range(3))


def contrast(c, amount=0.0, pivot=0.45):
    """Filmic S-curve around pivot; amount > 0 adds contrast."""
    out = []
    for v in c:
        y = _clip(v)
        if y < pivot:
            out.append(pivot * (y / pivot) ** (1 + amount))
        else:
            out.append(1 - (1 - pivot) * ((1 - y) / (1 - pivot)) ** (1 + amount))
    return tuple(out)


def levels(c, black=0.0, white=1.0):
    return tuple(black + (white - black) * v for v in c)


def saturation(c, amount=1.0):
    y = _luma(c)
    return tuple(y + (v - y) * amount for v in c)


def vibrance(c, amount=0.0):
    """Lifts weak colours more than strong ones."""
    _, s, _ = colorsys.rgb_to_hsv(*(_clip(v) for v in c))
    y = _luma(c)
    k = 1 + amount * (1 - s)
    return tuple(y + (v - y) * k for v in c)


def split_tone(c, shadows=(0, 0, 0), highlights=(0, 0, 0), balance=0.5):
    y = _clip(_luma(tuple(_clip(v) for v in c)))
    ws = 1 - _smooth(0.0, balance * 2, y)
    wh = _smooth(balance * 0.6, 1.0, y)
    return tuple(c[i] + ws * shadows[i] + wh * highlights[i] for i in range(3))


def hue_shift(c, center, width, shift=0.0, sat=1.0, val=1.0, min_sat=0.05):
    """Rotate one hue range (degrees) and scale its saturation and value;
    the edges blend so a shift never sweeps through other hues."""
    xc = tuple(_clip(v) for v in c)
    h, s, v = colorsys.rgb_to_hsv(*xc)
    h *= 360.0
    dist = abs((h - center + 180) % 360 - 180)
    w = (1 - _smooth(width * 0.5, width, dist)) * _smooth(min_sat, min_sat + 0.08, s)
    if w <= 0:
        return c
    full = colorsys.hsv_to_rgb(((h + shift) % 360) / 360.0, _clip(s * sat), _clip(v * val))
    return tuple(xc[i] + w * (full[i] - xc[i]) for i in range(3))


def mono(c, weights=LUMA, tint=(0, 0, 0)):
    total = sum(weights)
    y = sum(_clip(c[i]) * weights[i] for i in range(3)) / total
    k = 1 - abs(2 * y - 1)
    return tuple(y + tint[i] * k for i in range(3))


def highlight_rolloff(c, knee=0.8):
    out = []
    for v in c:
        v = max(0.0, v)
        out.append(knee + (1 - knee) * math.tanh((v - knee) / (1 - knee)) if v > knee else v)
    return tuple(out)


OPS = {
    "white_balance": white_balance, "exposure": exposure, "cdl": cdl, "contrast": contrast,
    "levels": levels, "saturation": saturation, "vibrance": vibrance, "split_tone": split_tone,
    "hue_shift": hue_shift, "mono": mono, "highlight_rolloff": highlight_rolloff,
}


# ---------------------------------------------------------------------------
# The house looks (ids and labels in app/render/grade.py LOOKS)
# ---------------------------------------------------------------------------

LOOK_RECIPES: dict[str, list[dict]] = {
    # Kodak-ish print warmth: a little warmer, lifted and slightly warm
    # blacks, soft shoulder, saturation just under the source.
    "warm_film": [
        {"op": "white_balance", "temp": 0.09, "tint": 0.01},
        {"op": "contrast", "amount": 0.14},
        {"op": "levels", "black": 0.03, "white": 0.975},
        {"op": "saturation", "amount": 0.93},
        {"op": "split_tone", "shadows": (0.012, 0.004, -0.012), "highlights": (0.03, 0.012, -0.024)},
        {"op": "highlight_rolloff", "knee": 0.88},
    ],
    # Gentle complementary grade: skin and warm objects toward orange,
    # cyans and blues toward teal, teal shadows and warm highlights.
    "teal_orange": [
        {"op": "contrast", "amount": 0.16},
        {"op": "hue_shift", "center": 25, "width": 50, "shift": 3, "sat": 1.15, "val": 1.01},
        {"op": "hue_shift", "center": 195, "width": 50, "shift": -4, "sat": 1.1},
        {"op": "hue_shift", "center": 215, "width": 40, "shift": -7, "sat": 1.0},
        {"op": "split_tone", "shadows": (-0.03, 0.006, 0.035), "highlights": (0.03, 0.012, -0.026)},
        {"op": "highlight_rolloff", "knee": 0.88},
    ],
    # Clean and modern: cooler white balance, crisp but not hard, a touch of
    # blue in the shadows, saturation slightly down.
    "cool_clean": [
        {"op": "white_balance", "temp": -0.09, "tint": -0.008},
        {"op": "contrast", "amount": 0.12},
        {"op": "saturation", "amount": 0.95},
        {"op": "split_tone", "shadows": (-0.012, 0.0, 0.022), "highlights": (0.0, 0.004, 0.012)},
        {"op": "highlight_rolloff", "knee": 0.9},
    ],
    # Airy: a little brighter, flatter, lifted blacks, softened colour with
    # weak tones kept alive, lilac shadows and peach highlights.
    "soft_pastel": [
        {"op": "exposure", "stops": 0.15},
        {"op": "contrast", "amount": -0.12},
        {"op": "levels", "black": 0.05, "white": 0.985},
        {"op": "saturation", "amount": 0.8},
        {"op": "vibrance", "amount": 0.15},
        {"op": "split_tone", "shadows": (0.014, 0.0, 0.026), "highlights": (0.02, 0.01, 0.0)},
        {"op": "highlight_rolloff", "knee": 0.85},
    ],
    # Black and white with a red filter mix (bright skin, darker skies),
    # hard contrast and deep blacks.
    "mono_contrast": [
        {"op": "mono", "weights": (0.45, 0.45, 0.1)},
        {"op": "contrast", "amount": 0.45},
        {"op": "cdl", "offset": (-0.02, -0.02, -0.02)},
        {"op": "highlight_rolloff", "knee": 0.9},
    ],
    # Late sun: clearly warm, yellows pushed toward gold, warm highlights and
    # a faint magenta in the shadows.
    "golden_hour": [
        {"op": "white_balance", "temp": 0.17, "tint": 0.02},
        {"op": "contrast", "amount": 0.14},
        {"op": "hue_shift", "center": 55, "width": 40, "shift": -6, "sat": 1.1},
        {"op": "saturation", "amount": 1.04},
        {"op": "split_tone", "shadows": (0.016, 0.0, 0.012), "highlights": (0.05, 0.026, -0.036)},
        {"op": "highlight_rolloff", "knee": 0.86},
    ],
    # Observational: muted colour, a slightly flat curve, neutral to faintly
    # cool shadows; reads like available light.
    "documentary_muted": [
        {"op": "saturation", "amount": 0.74},
        {"op": "contrast", "amount": 0.07},
        {"op": "levels", "black": 0.02, "white": 0.98},
        {"op": "split_tone", "shadows": (-0.006, 0.004, 0.01), "highlights": (0.01, 0.005, -0.005)},
        {"op": "highlight_rolloff", "knee": 0.9},
    ],
}

TITLES = {
    "warm_film": "Warm film",
    "teal_orange": "Teal and orange",
    "cool_clean": "Cool clean",
    "soft_pastel": "Soft pastel",
    "mono_contrast": "High contrast mono",
    "golden_hour": "Golden hour",
    "documentary_muted": "Documentary muted",
}


def apply_recipe(rgb, recipe: list[dict]):
    c = tuple(rgb)
    for step in recipe:
        args = {k: v for k, v in step.items() if k != "op"}
        c = OPS[step["op"]](c, **args)
    return tuple(_clip(v) for v in c)


def write_cube(path: str, title: str, recipe: list[dict], size: int = SIZE) -> None:
    """A .cube with red changing fastest (the format's order, also Pillow's
    Color3DLUT table order). Four decimals is far below one 8-bit step."""
    step = 1.0 / (size - 1)
    lines = [f'TITLE "{title}"', f"LUT_3D_SIZE {size}", "DOMAIN_MIN 0.0 0.0 0.0", "DOMAIN_MAX 1.0 1.0 1.0"]
    for b in range(size):
        for g in range(size):
            for r in range(size):
                out = apply_recipe((r * step, g * step, b * step), recipe)
                lines.append(f"{out[0]:.4f} {out[1]:.4f} {out[2]:.4f}")
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> None:
    for key, recipe in LOOK_RECIPES.items():
        path = os.path.join(HERE, f"{key}.cube")
        write_cube(path, TITLES[key], recipe)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
