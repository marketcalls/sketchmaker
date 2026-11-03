"""Motion design system for /motion-graphics.

Numbers come from the research spec (mg_research.md, "Motion design system"):

* Units: u = min(W, H) / 1080. Canvases 1080x1920 (9:16), 1080x1350 (4:5),
  1080x1080 (1:1), 1920x1080 (16:9). 8u spacing grid, 12 columns, gutter
  24u, margin 64u.
* Type scale at u = 1: numeric-xxl 320, display 200, h1 140, h2 96, h3 72,
  body 56, caption 48, meta 34 (min 32). Landscape multiplier 0.8, square
  0.92, 4:5 1.04, 9:16 1.14. Auto-fit shrinks to at most 70 percent of the
  token, then wraps.
* Easing tokens (cubic-bezier), durations snapped to frames, stagger caps,
  safe-zone presets per aspect, color tokens with 4.5:1 contrast.

A *style* changes the layout grid, the transition family and the type
pairing, not only colors. Brand kits override palette tokens and fonts and
set the motion intensity (calm, standard, punchy).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Optional

from app.render.colors import luminance, parse_color
from app.render.easing import clamp, cubic_bezier

FPS = 30

# ---------------------------------------------------------------------------
# Canvases and safe zones
# ---------------------------------------------------------------------------

ASPECTS = ("9:16", "4:5", "1:1", "16:9")
CANVAS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "4:5": (1080, 1350),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}

# Safe zone presets: (top, bottom, left, right) in px of the full canvas.
SAFE_ZONES: dict[str, dict[str, tuple[int, int, int, int]]] = {
    "9:16": {
        "organic": (240, 440, 72, 150),      # Shorts, Reels, TikTok organic UI
        "strict_ads": (270, 672, 65, 120),   # paid placements with CTA buttons
        "cover": (240, 240, 72, 72),         # key title inside the central 1080x1440 grid crop
        "none": (96, 96, 72, 72),
    },
    "4:5": {
        "organic": (81, 81, 65, 65),          # 6 percent each side
        "strict_ads": (110, 160, 65, 65),
        "cover": (135, 135, 65, 65),          # critical content in the central 1080x1080
        "none": (64, 64, 64, 64),
    },
    "1:1": {
        "organic": (54, 54, 54, 54),          # 5 percent
        "strict_ads": (80, 110, 60, 60),
        "cover": (54, 54, 54, 54),
        "none": (48, 48, 48, 48),
    },
    "16:9": {
        "organic": (54, 54, 96, 96),          # 5 percent action safe
        "strict_ads": (108, 108, 192, 192),   # 10 percent title safe
        "cover": (54, 54, 96, 96),
        "none": (48, 48, 64, 64),
    },
}
SAFE_ZONE_PRESETS = ("organic", "strict_ads", "cover", "none")

# Engine caption platform zone per aspect.
CAPTION_PLATFORM = {"9:16": "shorts", "4:5": "reels", "1:1": "reels", "16:9": "youtube"}


@dataclass(frozen=True)
class Frame:
    """Layout context for one output aspect (all values in output pixels)."""

    aspect: str
    W: int
    H: int
    u: float
    type_mult: float
    safe: tuple[int, int, int, int]  # left, top, right, bottom of the safe content rect
    scale: float = 1.0  # preview downscale factor already applied to W and H

    @property
    def orientation(self) -> str:
        if self.H > self.W * 1.1:
            return "vertical"
        if self.W > self.H * 1.1:
            return "landscape"
        return "square"

    @property
    def landscape(self) -> bool:
        return self.orientation == "landscape"

    @property
    def vertical(self) -> bool:
        return self.orientation == "vertical"

    def px(self, v: float) -> float:
        return v * self.u

    def type(self, token: str) -> float:
        return TYPE_SCALE[token] * self.u * self.type_mult

    @property
    def content(self) -> tuple[int, int, int, int]:
        """Safe rect (left, top, right, bottom) further inset to the 64u margin."""
        l, t, r, b = self.safe
        m = int(round(64 * self.u))
        return (max(l, m), max(t, m), min(r, self.W - m), min(b, self.H - m))

    @property
    def cw(self) -> int:
        l, t, r, b = self.content
        return r - l

    @property
    def ch(self) -> int:
        l, t, r, b = self.content
        return b - t

    def col(self, i: float, span: float = 1.0) -> tuple[float, float]:
        """(x, width) of a 12 column grid span inside the content rect."""
        l, t, r, b = self.content
        gutter = 24 * self.u
        colw = (r - l - 11 * gutter) / 12.0
        x = l + i * (colw + gutter)
        w = span * colw + max(0.0, span - 1) * gutter
        return x, w


def make_frame(aspect: str, safe_zone: str = "organic", scale: float = 1.0) -> Frame:
    W0, H0 = CANVAS[aspect]
    W = int(round(W0 * scale)) // 2 * 2
    H = int(round(H0 * scale)) // 2 * 2
    sx = W / W0
    t, b, l, r = SAFE_ZONES[aspect].get(safe_zone) or SAFE_ZONES[aspect]["organic"]
    u = min(W, H) / 1080.0
    # Tall frames have far more height than width: type a notch larger so a
    # headline holds the frame on a phone instead of floating in empty space.
    mult = {"16:9": 0.8, "1:1": 0.92, "4:5": 1.04, "9:16": 1.14}.get(aspect, 1.0)
    safe = (int(round(l * sx)), int(round(t * sx)), W - int(round(r * sx)), H - int(round(b * sx)))
    return Frame(aspect=aspect, W=W, H=H, u=u, type_mult=mult, safe=safe, scale=scale)


# ---------------------------------------------------------------------------
# Type scale, easing, durations
# ---------------------------------------------------------------------------

TYPE_SCALE = {
    "numeric": 320.0,
    "display": 200.0,
    "h1": 140.0,
    "h2": 96.0,
    "h3": 72.0,
    "body": 56.0,
    "caption": 48.0,
    "meta": 34.0,
}
MIN_META_PX = 32.0

EASING = {
    "standard": (0.4, 0.0, 0.2, 1.0),
    "decel": (0.05, 0.7, 0.1, 1.0),
    "exit": (0.3, 0.0, 0.8, 0.15),
    "snap": (0.16, 1.0, 0.3, 1.0),
    "smooth": (0.22, 1.0, 0.36, 1.0),
    "overshoot": (0.34, 1.56, 0.64, 1.0),
    "camera": (0.65, 0.0, 0.35, 1.0),
    "camera_strong": (0.76, 0.0, 0.24, 1.0),
    "counter": (0.23, 1.0, 0.32, 1.0),
    "linear": None,
}


@lru_cache(maxsize=None)
def _curve(name: str):
    pts = EASING.get(name, EASING["standard"])
    if pts is None:
        return lambda p: clamp(p)
    return cubic_bezier(*pts)


def E(name: str, p: float) -> float:
    """Eased progress for an easing token (input clamped to 0..1; overshoot
    curves may return values above 1)."""
    p = clamp(p)
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    return _curve(name)(p)


DUR = {"micro": 0.1, "short": 0.2, "base": 0.3, "medium": 0.5, "long": 0.7, "xl": 1.0}


def snap(seconds: float) -> float:
    """Round to whole frames."""
    return round(round(seconds * FPS) / FPS, 4)


def hold_seconds(text: str) -> float:
    """Static text hold: max(900 ms, 300 ms + 65 ms per character)."""
    return max(0.9, 0.3 + 0.065 * len(text or ""))


@dataclass(frozen=True)
class Intensity:
    id: str
    label: str
    time: float        # multiplier on animation durations
    distance: float    # multiplier on travel distances
    overshoot: bool    # allow overshoot easing
    slam: float        # start scale of word slams
    drift: float       # camera drift per scene (fraction)
    glitch: bool


INTENSITIES = {
    "calm": Intensity("calm", "Calm", 1.25, 0.7, False, 1.12, 0.02, False),
    "standard": Intensity("standard", "Standard", 1.0, 1.0, True, 1.3, 0.03, False),
    "punchy": Intensity("punchy", "Punchy", 0.8, 1.3, True, 1.42, 0.04, True),
}


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

def hex_of(rgba) -> str:
    return "#{:02X}{:02X}{:02X}".format(rgba[0], rgba[1], rgba[2])


def contrast(a: str, b: str) -> float:
    la = luminance(parse_color(a))
    lb = luminance(parse_color(b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix(a: str, b: str, t: float) -> str:
    ca, cb = parse_color(a), parse_color(b)
    return hex_of(tuple(int(round(ca[i] + (cb[i] - ca[i]) * t)) for i in range(3)) + (255,))


def readable(fg: str, bg: str, minimum: float = 4.5) -> str:
    """``fg`` when it reaches ``minimum`` contrast on ``bg``, else the best of
    near-black and near-white."""
    if contrast(fg, bg) >= minimum:
        return fg
    dark, light = "#0B0B0F", "#FAFAF7"
    return dark if contrast(dark, bg) >= contrast(light, bg) else light


def accent_on(accent: str, bg: str) -> str:
    """Accent that stays visible on bg (3:1 for large text and shapes): darken
    or lighten toward the readable pole when needed."""
    if contrast(accent, bg) >= 3.0:
        return accent
    pole = readable("#808080", bg, 99)
    for k in range(1, 9):
        c = mix(accent, pole, k * 0.1)
        if contrast(c, bg) >= 3.0:
            return c
    return pole


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Palette:
    bg: str
    bg2: str          # second background stop (gradients, panels)
    surface: str      # cards and tiles
    text: str
    muted: str
    accent: str
    accent2: str
    positive: str
    negative: str
    rule: str         # hairlines, gridlines
    chart: tuple[str, ...]


@dataclass(frozen=True)
class Style:
    id: str
    name: str
    description: str
    display_font: str
    display_weight: int
    text_font: str
    text_weight: int
    numeric_font: str
    numeric_weight: int
    label_font: str
    label_weight: int
    label_upper: bool
    label_tracking: float      # em
    display_tracking: float    # em
    display_upper: bool
    line_height: float
    align: str                 # left | center
    background: str            # solid | grid | blobs | paper | noise | lattice
    text_anim: str             # mask_up | slide_mask | slam | blur_in | typewriter
    emphasis: str              # color | marker | underline | outline | box
    transition: str            # push | slide | wipe | zoom | cut
    transition_seconds: float
    card: str                  # none | outline | fill | glass | heavy | panel
    radius: float              # card corner radius (u)
    border: float              # card border width (u)
    rules: bool                # hairline rules and kickers
    mono_labels: bool          # fixed cell (monospaced) labels
    caption_preset: str
    caption_font: str
    palette: Palette

    def with_palette(self, **kw) -> "Style":
        return replace(self, palette=replace(self.palette, **kw))


CHART_DARK = ("#FF6B4A", "#4CC9F0", "#FFD166", "#7BD389", "#B794F6", "#F72585", "#FF9F1C", "#2EC4B6",
              "#E7EAF0", "#9AA5B1", "#C3F73A", "#5E60CE")
CHART_LIGHT = ("#E63022", "#1D4ED8", "#0F766E", "#B45309", "#7C3AED", "#BE185D", "#0E7490", "#4D7C0F",
               "#374151", "#9333EA", "#C2410C", "#065F46")

STYLES: dict[str, Style] = {
    "editorial_serif": Style(
        id="editorial_serif", name="Editorial Serif",
        description="Magazine feel: Playfair headlines over Inter, warm dark paper, thin rules, words rise from a mask.",
        display_font="Playfair Display", display_weight=800, text_font="Inter", text_weight=500,
        numeric_font="Playfair Display", numeric_weight=900, label_font="Inter", label_weight=600,
        label_upper=True, label_tracking=0.16, display_tracking=-0.01, display_upper=False, line_height=1.04,
        align="left", background="noise", text_anim="mask_up", emphasis="color", transition="slide",
        transition_seconds=0.5, card="none", radius=6, border=1.5, rules=True, mono_labels=False,
        caption_preset="serif_story", caption_font="Playfair Display",
        palette=Palette(bg="#14110F", bg2="#1E1915", surface="#231D18", text="#F4EDE1", muted="#B8AC9A",
                        accent="#E2725B", accent2="#D9B26F", positive="#7BC67E", negative="#E2725B",
                        rule="#4A4038", chart=CHART_DARK),
    ),
    "swiss_grid": Style(
        id="swiss_grid", name="Swiss Grid",
        description="International style: heavy Inter on a visible 12 column grid, flush left, red accent, hard horizontal pushes.",
        display_font="Inter", display_weight=900, text_font="Inter", text_weight=500,
        numeric_font="Inter", numeric_weight=900, label_font="Inter", label_weight=700,
        label_upper=True, label_tracking=0.08, display_tracking=-0.035, display_upper=False, line_height=0.95,
        align="left", background="grid", text_anim="slide_mask", emphasis="color", transition="push",
        transition_seconds=0.45, card="fill", radius=0, border=0, rules=True, mono_labels=False,
        caption_preset="karaoke_box", caption_font="Inter",
        palette=Palette(bg="#F1F0EA", bg2="#E6E4DC", surface="#FFFFFF", text="#111111", muted="#5C5C58",
                        accent="#E63022", accent2="#111111", positive="#0F7B3F", negative="#E63022",
                        rule="#D3D1C7", chart=CHART_LIGHT),
    ),
    "brutalist_mono": Style(
        id="brutalist_mono", name="Brutalist Mono",
        description="Raw and loud: monospaced Space Grotesk labels in fixed cells, Anton slams, thick boxes, hard cuts.",
        display_font="Anton", display_weight=400, text_font="Space Grotesk", text_weight=500,
        numeric_font="Space Grotesk", numeric_weight=700, label_font="Space Grotesk", label_weight=700,
        label_upper=True, label_tracking=0.0, display_tracking=0.0, display_upper=True, line_height=0.98,
        align="left", background="solid", text_anim="slam", emphasis="box", transition="cut",
        transition_seconds=0.0, card="heavy", radius=0, border=6, rules=False, mono_labels=True,
        caption_preset="karaoke_box", caption_font="Space Grotesk",
        palette=Palette(bg="#0A0A0A", bg2="#141414", surface="#0A0A0A", text="#F5F5F0", muted="#9A9A92",
                        accent="#D7FF3A", accent2="#FF4D2E", positive="#D7FF3A", negative="#FF4D2E",
                        rule="#F5F5F0", chart=("#D7FF3A", "#FF4D2E", "#F5F5F0", "#4DD0FF", "#FFB800",
                                               "#B18CFF", "#00E0A4", "#FF7AC6", "#9A9A92", "#FFE14D",
                                               "#5CFFC8", "#FF9A6B")),
    ),
    "soft_gradient": Style(
        id="soft_gradient", name="Soft Gradient",
        description="Friendly product look: Bricolage Grotesque, drifting color blobs, glass cards, blur-in text, zoom transitions.",
        display_font="Bricolage Grotesque", display_weight=750, text_font="Poppins", text_weight=500,
        numeric_font="Bricolage Grotesque", numeric_weight=800, label_font="Poppins", label_weight=600,
        label_upper=False, label_tracking=0.01, display_tracking=-0.025, display_upper=False, line_height=1.0,
        align="center", background="blobs", text_anim="blur_in", emphasis="marker", transition="zoom",
        transition_seconds=0.5, card="glass", radius=36, border=1.5, rules=False, mono_labels=False,
        caption_preset="bold_pop", caption_font="Poppins",
        palette=Palette(bg="#120F2A", bg2="#2A1B54", surface="#FFFFFF", text="#FFFFFF", muted="#D6D0F0",
                        accent="#FFB86B", accent2="#8EC5FF", positive="#7CF0B5", negative="#FF8A9A",
                        rule="#FFFFFF", chart=("#FFB86B", "#8EC5FF", "#C9A7FF", "#7CF0B5", "#FF8A9A",
                                               "#FFE08A", "#6EE7F9", "#F0ABFC", "#A5B4FC", "#FDBA74",
                                               "#86EFAC", "#F9A8D4")),
    ),
    "newsprint": Style(
        id="newsprint", name="Newsprint",
        description="Broadsheet: black Playfair on paper texture, double rules, column layout, page-turn wipes.",
        display_font="Playfair Display", display_weight=900, text_font="Inter", text_weight=500,
        numeric_font="Playfair Display", numeric_weight=900, label_font="Inter", label_weight=700,
        label_upper=True, label_tracking=0.2, display_tracking=-0.015, display_upper=False, line_height=1.0,
        align="center", background="paper", text_anim="mask_up", emphasis="underline", transition="wipe",
        transition_seconds=0.55, card="outline", radius=0, border=2, rules=True, mono_labels=False,
        caption_preset="minimal_lower", caption_font="Inter",
        palette=Palette(bg="#EFE8DA", bg2="#E5DCCB", surface="#F7F2E8", text="#151311", muted="#5B544A",
                        accent="#B3121F", accent2="#151311", positive="#1F6B3A", negative="#B3121F",
                        rule="#151311", chart=("#151311", "#B3121F", "#6B6257", "#1F4E79", "#8A6D3B",
                                               "#3F6F4A", "#9C4F7D", "#2F6E7D", "#A9A091", "#5A3E8E",
                                               "#7A2E1A", "#405D27")),
    ),
    # Product and SaaS explainers: one accent on near black, a faint
    # drifting diamond lattice with grain and vignette, black uppercase
    # headlines whose emphasis words take the accent, words that rise from a
    # mask, and app-window cards (surface, hairline border, rounded).
    "dark_tech": Style(
        id="dark_tech", name="Dark Tech",
        description="Product explainer look: one accent on near black, lattice texture, black uppercase headlines, app-window cards.",
        display_font="Inter", display_weight=900, text_font="Inter", text_weight=500,
        numeric_font="Inter", numeric_weight=900, label_font="Inter", label_weight=700,
        label_upper=True, label_tracking=0.15, display_tracking=-0.02, display_upper=True, line_height=0.98,
        align="left", background="lattice", text_anim="mask_up", emphasis="color", transition="zoom",
        transition_seconds=0.45, card="panel", radius=20, border=1.5, rules=False, mono_labels=False,
        caption_preset="bold_pop", caption_font="Inter",
        palette=Palette(bg="#050505", bg2="#0B0B0C", surface="#0F0F10", text="#F4F4F1", muted="#8A8A86",
                        accent="#19C39B", accent2="#E9C46A", positive="#19C39B", negative="#E5383B",
                        rule="#2A2A2A", chart=("#19C39B", "#4CC9F0", "#E9C46A", "#E5383B", "#B794F6", "#F4F4F1",
                                               "#FF9F1C", "#2EC4B6", "#8A8A86", "#F72585", "#C3F73A", "#5E60CE")),
    ),
}
STYLE_IDS = tuple(STYLES)
DEFAULT_STYLE = "swiss_grid"

# Fonts a brand kit may pick (bundled, OFL). Keys are app.render.fonts families.
BRAND_FONTS = ("Inter", "Poppins", "Bricolage Grotesque", "Space Grotesk", "Playfair Display", "Anton", "Bebas Neue")


def style_catalog() -> list[dict]:
    out = []
    for s in STYLES.values():
        p = s.palette
        out.append({
            "id": s.id, "name": s.name, "description": s.description,
            "fonts": {"display": s.display_font, "text": s.text_font},
            "swatches": [p.bg, p.text, p.accent, p.accent2],
            "transition": s.transition, "text_animation": s.text_anim,
        })
    return out


@dataclass(frozen=True)
class Look:
    """A style with the brand kit applied and the motion intensity resolved."""

    style: Style
    intensity: Intensity
    seed: int
    logo_path: Optional[str] = None
    brand_name: Optional[str] = None
    extra: dict = field(default_factory=dict)

    @property
    def p(self) -> Palette:
        return self.style.palette

    def rng(self, salt: str | int = "") -> random.Random:
        return random.Random(f"{self.seed}:{salt}")

    def t(self, seconds: float) -> float:
        """An animation duration scaled by the motion intensity, snapped to frames."""
        return snap(max(1 / FPS, seconds * self.intensity.time))

    def ease_pop(self) -> str:
        return "overshoot" if self.intensity.overshoot else "snap"


def apply_brand(style: Style, brand: Optional[dict]) -> Style:
    """Brand kit palette tokens and fonts over a style, with contrast enforced."""
    if not brand:
        return style
    pal = style.palette
    colors = brand.get("palette") or {}
    kw = {}
    if colors.get("primary"):
        kw["accent"] = colors["primary"]
    if colors.get("secondary"):
        kw["accent2"] = colors["secondary"]
    use_bg = bool(brand.get("use_brand_background")) and colors.get("background")
    if use_bg:
        kw["bg"] = colors["background"]
        kw["bg2"] = mix(colors["background"], readable("#808080", colors["background"], 99), 0.08)
        kw["surface"] = mix(colors["background"], readable("#808080", colors["background"], 99), 0.06)
    if colors.get("text"):
        kw["text"] = colors["text"]
    pal = replace(pal, **kw) if kw else pal
    # Contrast guarantees: text 4.5:1 on bg, accent 3:1 (large display use).
    text = readable(pal.text, pal.bg, 4.5)
    muted = pal.muted if contrast(pal.muted, pal.bg) >= 3.0 else mix(text, pal.bg, 0.35)
    accent = accent_on(pal.accent, pal.bg)
    chart = (accent,) + tuple(c for c in pal.chart if c.upper() != accent.upper())
    pal = replace(pal, text=text, muted=muted, accent=accent, chart=chart,
                  rule=pal.rule if not use_bg else mix(text, pal.bg, 0.7))
    out = replace(style, palette=pal)
    fonts = brand.get("fonts") or {}
    if fonts.get("display") in BRAND_FONTS:
        out = replace(out, display_font=fonts["display"],
                      display_weight=_weight_for(fonts["display"], style.display_weight),
                      display_upper=style.display_upper or fonts["display"] in ("Anton", "Bebas Neue"))
    if fonts.get("text") in BRAND_FONTS and fonts["text"] not in ("Anton", "Bebas Neue"):
        out = replace(out, text_font=fonts["text"], label_font=fonts["text"])
    return out


def _weight_for(family: str, wanted: int) -> int:
    ranges = {"Inter": (100, 900), "Poppins": (500, 800), "Bricolage Grotesque": (200, 800),
              "Space Grotesk": (300, 700), "Playfair Display": (400, 900), "Anton": (400, 400),
              "Bebas Neue": (400, 400)}
    lo, hi = ranges.get(family, (400, 900))
    return max(lo, min(hi, wanted))


def make_look(style_id: str, brand: Optional[dict], seed: int, intensity: Optional[str] = None,
              logo_path: Optional[str] = None) -> Look:
    style = STYLES.get(style_id) or STYLES[DEFAULT_STYLE]
    style = apply_brand(style, brand)
    level = intensity or (brand or {}).get("intensity") or "standard"
    return Look(style=style, intensity=INTENSITIES.get(level, INTENSITIES["standard"]), seed=int(seed or 0),
                logo_path=logo_path, brand_name=(brand or {}).get("name"))


def nice_step(span: float, target_ticks: int = 4) -> float:
    """1, 2 or 5 times a power of ten giving about ``target_ticks`` intervals."""
    if span <= 0:
        return 1.0
    raw = span / max(1, target_ticks)
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag
