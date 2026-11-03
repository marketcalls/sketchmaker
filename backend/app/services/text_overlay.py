"""Exact text on a generated image ("Add text").

Image models drift on lettering, so words that must be exact are drawn here
with Pillow from the bundled OFL fonts (app/render/fonts) and composited onto
a copy of the image (skills scenario-text-overlay and scenario-thumbnails).
One card holds up to four layers (headline, subhead, label, call to action)
in ONE font family; hierarchy comes from weight and size. Text containing
Devanagari is set in Noto Sans Devanagari automatically (complex shaping
through Pillow's raqm layout).

Sizes are a percentage of the image width, so a spec means the same on any
resolution, and positions are the centre of each text block as fractions of
the image. The result is judged where it will be seen: every layer is
checked against the destination of the image's format (a thumbnail is read
about 120 px wide, a vertical video on a phone) and against the format's
safe zone (9:16 keeps the top 14 per cent and bottom 35 per cent clear, as
the paid placement zone in services/motion_graphics/design.py SAFE_ZONES).
Problems come back as warnings; the image is still made.

Pure functions over PIL images; no database or storage access.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from typing import Literal, Optional

from PIL import Image, ImageDraw, ImageFilter, ImageOps
from pydantic import BaseModel, Field, field_validator

from app.render import fonts

MAX_LAYERS = 4
MAX_TEXT_CHARS = 240
MAX_LINES = 6
MAX_SOURCE_PIXELS = 40_000_000  # refuse anything larger than about 8K x 5K
PREVIEW_LONG_SIDE = 960
HEX = r"^#[0-9A-Fa-f]{6}$"

Role = Literal["headline", "subhead", "label", "cta"]

# Default look of each role. size is a percentage of the image width.
ROLES: dict[str, dict] = {
    "headline": {"label": "Headline", "weight": 800, "size": 8.0, "uppercase": True, "backdrop": "scrim",
                 "y": 0.24},
    "subhead": {"label": "Subhead", "weight": 500, "size": 4.6, "uppercase": False, "backdrop": "none",
                "y": 0.36},
    "label": {"label": "Label", "weight": 700, "size": 3.6, "uppercase": True, "backdrop": "box", "y": 0.12},
    "cta": {"label": "Call to action", "weight": 800, "size": 4.4, "uppercase": True, "backdrop": "box",
            "y": 0.62},
}

# Families offered (keys of app.render.fonts.FAMILIES) with what each reads as.
FONT_CHOICES: tuple[tuple[str, str], ...] = (
    ("anton", "Heavy condensed: hooks, prices, thumbnails"),
    ("bebasneue", "Condensed capitals: posters and labels"),
    ("bricolagegrotesque", "Characterful grotesque: editorial headlines"),
    ("inter", "Neutral sans: clean, premium, legal lines"),
    ("poppins", "Rounded geometric: friendly and casual"),
    ("spacegrotesk", "Technical grotesque: product and tech"),
    ("playfairdisplay", "High contrast serif: heritage and luxury"),
    ("notosansdevanagari", "Hindi and other Devanagari text, with Latin"),
)

# Colours offered as swatches, named after the app's design tokens.
PALETTE: tuple[tuple[str, str], ...] = (
    ("Paper", "#F7F7F2"),
    ("Ink", "#0B0D12"),
    ("Lime", "#D4FB37"),
    ("Amber", "#FFC53D"),
    ("Coral", "#FF5A4E"),
    ("Sky", "#5AC8FA"),
)

# Position presets: (x, y) of the block centre.
POSITIONS: dict[str, tuple[float, float]] = {
    "top": (0.5, 0.2),
    "centre": (0.5, 0.5),
    "bottom": (0.5, 0.8),
    "upper_third": (0.5, 1 / 3),
    "lower_third": (0.5, 2 / 3),
}

# Where each format is seen, and the smallest font that still reads there:
# view_width is the image's width at the destination (px or pt), min_px the
# smallest legible font size at that width. The thumbnail rule is the
# scenario-thumbnails stress test (a roughly 120 px wide preview).
DESTINATIONS: dict[str, dict] = {
    "16:9": {"destination": "a video thumbnail, about 120 px wide in search and suggestions",
             "view_width": 120, "min_px": 8},
    "9:16": {"destination": "a phone screen, about 390 pt wide", "view_width": 390, "min_px": 14},
    "4:5": {"destination": "a feed post on a phone, about 390 pt wide", "view_width": 390, "min_px": 12},
    "1:1": {"destination": "a feed post on a phone, about 390 pt wide", "view_width": 390, "min_px": 12},
    "other": {"destination": "a screen, about 800 px wide", "view_width": 800, "min_px": 12},
}

FORMATS = {"9:16": 9 / 16, "4:5": 4 / 5, "1:1": 1.0, "16:9": 16 / 9}


class TextOverlayError(Exception):
    """A problem with the request, written for the user."""


class Layer(BaseModel):
    role: Role = "headline"
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    weight: int = Field(700, ge=100, le=900)
    size: float = Field(6.0, ge=1.0, le=30.0)  # per cent of the image width
    color: str = Field("#F7F7F2", pattern=HEX)
    uppercase: bool = False
    align: Literal["left", "center", "right"] = "center"
    x: float = Field(0.5, ge=0.0, le=1.0)  # block centre, fraction of the width
    y: float = Field(0.5, ge=0.0, le=1.0)  # block centre, fraction of the height
    max_width: float = Field(0.86, ge=0.2, le=1.0)  # wrap width, fraction of the width
    line_height: float = Field(1.1, ge=0.8, le=1.8)
    backdrop: Literal["none", "scrim", "box"] = "none"
    backdrop_color: str = Field("#000000", pattern=HEX)
    backdrop_opacity: float = Field(0.55, ge=0.0, le=1.0)
    stroke: bool = False
    stroke_color: str = Field("#000000", pattern=HEX)
    shadow: bool = False

    @field_validator("text")
    @classmethod
    def _clean(cls, value: str) -> str:
        value = re.sub(r"[\x00-\x09\x0b-\x1f\x7f]", "", value.replace("\r\n", "\n")).strip()
        if not value:
            raise ValueError("Text cannot be empty")
        if value.count("\n") >= MAX_LINES:
            raise ValueError(f"Use at most {MAX_LINES} lines per layer")
        return value


class Spec(BaseModel):
    font: str = "anton"
    layers: list[Layer] = Field(min_length=1, max_length=MAX_LAYERS)

    @field_validator("font")
    @classmethod
    def _known_font(cls, value: str) -> str:
        if value not in dict(FONT_CHOICES):
            raise ValueError("Pick one of the listed fonts")
        return value


@dataclass
class Placed:
    box: tuple[int, int, int, int]  # block including its backdrop, pixels
    font_key: str
    font_px: int


# ---------------------------------------------------------------------------
# Format, legibility and safe zones
# ---------------------------------------------------------------------------

def format_of(width: int, height: int) -> str:
    """The named format an image is closest to, or "other"."""
    ratio = width / max(1, height)
    best = min(FORMATS, key=lambda k: abs(FORMATS[k] - ratio) / FORMATS[k])
    return best if abs(FORMATS[best] - ratio) / FORMATS[best] < 0.06 else "other"


def safe_zone(fmt: str) -> dict[str, float]:
    """{top, bottom, left, right} fractions of the frame to keep clear."""
    from app.services.motion_graphics.design import CANVAS, SAFE_ZONES

    if fmt not in SAFE_ZONES:
        return {"top": 0.05, "bottom": 0.05, "left": 0.05, "right": 0.05,
                "name": "a 5 per cent margin"}
    # Vertical video: the paid placement zone (top 14, bottom 35 per cent),
    # which also clears the organic Shorts, Reels and TikTok UI.
    preset = "strict_ads" if fmt == "9:16" else "organic"
    t, b, l, r = SAFE_ZONES[fmt][preset]
    w, h = CANVAS[fmt]
    name = {"9:16": "the Shorts, Reels and TikTok interface", "16:9": "the 5 per cent action safe margin"}.get(
        fmt, "the feed safe margin")
    return {"top": round(t / h, 4), "bottom": round(b / h, 4), "left": round(l / w, 4), "right": round(r / w, 4),
            "name": name}


def min_size(fmt: str) -> float:
    """Smallest legible size for the format, in per cent of the width."""
    d = DESTINATIONS.get(fmt) or DESTINATIONS["other"]
    return round(100.0 * d["min_px"] / d["view_width"], 2)


def config() -> dict:
    """Everything the editor needs (GET /api/text-overlay/config)."""
    families = {f["key"]: f for f in fonts.available_families()}
    return {
        "max_layers": MAX_LAYERS,
        "max_text_chars": MAX_TEXT_CHARS,
        "roles": [{"id": k, **v} for k, v in ROLES.items()],
        "fonts": [{"key": k, "name": families[k]["name"], "weights": families[k]["weights"], "hint": hint}
                  for k, hint in FONT_CHOICES if k in families],
        "palette": [{"name": n, "hex": h} for n, h in PALETTE],
        "positions": [{"id": k, "x": round(v[0], 4), "y": round(v[1], 4)} for k, v in POSITIONS.items()],
        "formats": {fmt: {**(DESTINATIONS.get(fmt) or DESTINATIONS["other"]), "min_size": min_size(fmt),
                          "safe_zone": safe_zone(fmt)}
                    for fmt in (*FORMATS, "other")},
    }


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def _rgba(hex_color: str, alpha: float = 1.0) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(round(255 * max(0.0, min(1.0, alpha))))


def _wrap(text: str, font, max_w: float) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for word in words[1:]:
            trial = f"{cur} {word}"
            if font.getlength(trial) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines[: MAX_LINES * 2]


def _layout(layer: Layer, font_name: str, W: int, H: int):
    text = layer.text.upper() if layer.uppercase else layer.text
    px = max(6, int(round(layer.size / 100.0 * W)))
    key = fonts.resolve(font_name, text)
    font = fonts.get_font(key, layer.weight, px)
    lines = _wrap(text, font, layer.max_width * W)
    ascent, descent = font.getmetrics()
    step = max(int(round(px * layer.line_height)), 1)
    widths = [font.getlength(line) for line in lines]
    block_w = max(widths) if widths else 0.0
    block_h = step * (len(lines) - 1) + ascent + descent
    return text, key, px, font, lines, widths, block_w, block_h, step


def _pads(layer: Layer, px: int) -> tuple[int, int]:
    """Padding of a solid box around the text block."""
    if layer.backdrop == "box":
        return int(round(px * 0.45)), int(round(px * 0.28))
    return 0, 0


def _place(layer: Layer, font_name: str, W: int, H: int):
    """Layout of one layer on a W x H image: (lines, widths, font, font key,
    px, line step, left, top, block width, box). The box is the text block
    plus its solid box backdrop; a scrim feathers out beyond it and does not
    count toward the safe zone."""
    _text, key, px, font, lines, widths, block_w, block_h, step = _layout(layer, font_name, W, H)
    padx, pady = _pads(layer, px)
    # Centre the block on (x, y), then keep it (with its box) inside the image.
    left = layer.x * W - block_w / 2
    top = layer.y * H - block_h / 2
    left = min(max(left, padx), max(padx, W - padx - block_w))
    top = min(max(top, pady), max(pady, H - pady - block_h))
    box = (int(left - padx), int(top - pady), int(left + block_w + padx), int(top + block_h + pady))
    return lines, widths, font, key, px, step, left, top, block_w, box


def place_all(spec: Spec, W: int, H: int) -> list[Placed]:
    """Where every layer lands on a W x H image, without drawing."""
    out = []
    for layer in spec.layers:
        _l, _w, _f, key, px, _s, _x, _y, _bw, box = _place(layer, spec.font, W, H)
        out.append(Placed(box=box, font_key=key, font_px=px))
    return out


def _soft(img: Image.Image, region: tuple[int, int, int, int], draw_fn, radius: float) -> Image.Image:
    """Composite a blurred drawing onto ``img``, working on ``region`` only
    (the blur of a full size layer on a large image is slow)."""
    W, H = img.size
    m = int(radius * 3) + 2
    x0, y0 = max(0, region[0] - m), max(0, region[1] - m)
    x1, y1 = min(W, region[2] + m), min(H, region[3] + m)
    if x1 <= x0 or y1 <= y0:
        return img
    over = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(over), -x0, -y0)
    over = over.filter(ImageFilter.GaussianBlur(radius))
    patch = img.crop((x0, y0, x1, y1))
    img.paste(Image.alpha_composite(patch, over), (x0, y0))
    return img


def draw_layers(base: Image.Image, spec: Spec) -> tuple[Image.Image, list[Placed]]:
    """``base`` (any mode) with the spec's layers on it, as RGB, and where
    each layer landed. Scrims go down first, under every layer's text, so a
    headline's scrim never dims a label box drawn before it."""
    img = base.convert("RGBA")
    W, H = img.size
    placed = [(layer, _place(layer, spec.font, W, H)) for layer in spec.layers]

    for layer, (_lines, _widths, _font, _key, px, _step, _left, _top, _bw, box) in placed:
        if layer.backdrop != "scrim" or layer.backdrop_opacity <= 0:
            continue
        sx, sy = int(px * 1.1), int(px * 0.8)
        pool = (box[0] - sx, box[1] - sy, box[2] + sx, box[3] + sy)
        fill = _rgba(layer.backdrop_color, layer.backdrop_opacity)

        def scrim(d, dx, dy, pool=pool, fill=fill, px=px):
            d.rounded_rectangle((pool[0] + dx, pool[1] + dy, pool[2] + dx, pool[3] + dy), radius=int(px * 0.8), fill=fill)

        img = _soft(img, pool, scrim, max(2.0, px * 0.45))

    placed: list[Placed] = []
    for layer, (lines, widths, font, key, px, step, left, top, block_w, box) in placed:
        if layer.backdrop == "box" and layer.backdrop_opacity > 0:
            over = Image.new("RGBA", (max(1, box[2] - box[0]), max(1, box[3] - box[1])), (0, 0, 0, 0))
            ImageDraw.Draw(over).rounded_rectangle((0, 0, over.width - 1, over.height - 1), radius=int(px * 0.22),
                                                   fill=_rgba(layer.backdrop_color, layer.backdrop_opacity))
            img.alpha_composite(over, (max(0, box[0]), max(0, box[1])))
        color = _rgba(layer.color)
        stroke = max(1, int(round(px * 0.06))) if layer.stroke else 0
        if layer.shadow:
            off = max(1, int(round(px * 0.05)))

            def shadow(d, dx, dy, lines=lines, widths=widths, font=font, left=left, top=top, block_w=block_w,
                       step=step, off=off, stroke=stroke, align=layer.align):
                for i, line in enumerate(lines):
                    lx = _line_x(align, left, block_w, widths[i])
                    d.text((lx + off + dx, top + i * step + off + dy), line, font=font, fill=(0, 0, 0, 170),
                           anchor="la", stroke_width=stroke, stroke_fill=(0, 0, 0, 170))

            img = _soft(img, box, shadow, max(1.0, px * 0.06))
        d = ImageDraw.Draw(img)
        for i, line in enumerate(lines):
            lx = _line_x(layer.align, left, block_w, widths[i])
            d.text((lx, top + i * step), line, font=font, fill=color, anchor="la",
                   stroke_width=stroke, stroke_fill=_rgba(layer.stroke_color) if stroke else None)
        placed.append(Placed(box=box, font_key=key, font_px=px))
    return img.convert("RGB"), placed

def _line_x(align: str, left: float, block_w: float, line_w: float) -> float:
    if align == "left":
        return left
    if align == "right":
        return left + block_w - line_w
    return left + (block_w - line_w) / 2


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def warnings_for(spec: Spec, placed: list[Placed], W: int, H: int) -> list[dict]:
    """Legibility at the destination and safe zone problems, per layer."""
    fmt = format_of(W, H)
    dest = DESTINATIONS.get(fmt) or DESTINATIONS["other"]
    floor = min_size(fmt)
    zone = safe_zone(fmt)
    out: list[dict] = []
    for i, (layer, p) in enumerate(zip(spec.layers, placed)):
        name = ROLES[layer.role]["label"]
        if layer.size < floor:
            at = layer.size / 100.0 * dest["view_width"]
            out.append({"layer": i, "kind": "legibility",
                        "message": f"{name} would be about {at:.0f} px tall on {dest['destination']}. "
                                   f"Make it at least {floor:.1f} per cent of the width to stay readable."})
        x0, y0, x1, y1 = p.box
        clear_top, clear_bottom = zone["top"] * H, (1 - zone["bottom"]) * H
        clear_left, clear_right = zone["left"] * W, (1 - zone["right"]) * W
        if y0 < clear_top - 1 or y1 > clear_bottom + 1 or x0 < clear_left - 1 or x1 > clear_right + 1:
            out.append({"layer": i, "kind": "safe_zone",
                        "message": f"{name} reaches into the area {zone['name']} covers. Move it inside the guides."})
        if p.font_key == "notosansdevanagari" and spec.font != "notosansdevanagari":
            out.append({"layer": i, "kind": "font",
                        "message": f"{name} contains Devanagari, so it is set in Noto Sans Devanagari."})
    return out


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def open_image(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > MAX_SOURCE_PIXELS:
            raise TextOverlayError("This image is too large to add text to.")
        img = ImageOps.exif_transpose(img)
        img.load()
    except TextOverlayError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise TextOverlayError("This image could not be read.") from exc
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        flat = Image.new("RGBA", img.size, (0, 0, 0, 255))
        flat.alpha_composite(img)
        img = flat
    return img.convert("RGB")


def boxes(placed: list[Placed], W: int, H: int) -> list[dict]:
    return [{"x0": round(max(0, p.box[0]) / W, 4), "y0": round(max(0, p.box[1]) / H, 4),
             "x1": round(min(W, p.box[2]) / W, 4), "y1": round(min(H, p.box[3]) / H, 4)} for p in placed]


def preview(img: Image.Image, spec: Spec, full_size: Optional[tuple[int, int]] = None
            ) -> tuple[bytes, list[dict], list[dict]]:
    """A PNG of the result at most PREVIEW_LONG_SIDE px, the layer boxes
    (fractions) and the warnings. ``img`` may already be a downscaled copy of
    an image of ``full_size``: sizes are relative to the width, so the small
    copy draws the same card, while boxes and warnings are worked out at the
    full size."""
    W, H = full_size or img.size
    scale = min(1.0, PREVIEW_LONG_SIDE / max(img.size))
    small = img if scale >= 1.0 else img.resize(
        (max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.Resampling.LANCZOS)
    out, _placed = draw_layers(small, spec)
    buf = io.BytesIO()
    out.save(buf, format="PNG", compress_level=3)
    full = place_all(spec, W, H)
    return buf.getvalue(), boxes(full, W, H), warnings_for(spec, full, W, H)


def render(img: Image.Image, spec: Spec, *, source_format: str) -> tuple[bytes, str, str, list[dict]]:
    """(file bytes, extension, content type, warnings) of the final image.
    PNG keeps the type crisp; a JPEG source stays JPEG at high quality. A
    PNG carries the spec in a text chunk so the card can be reproduced."""
    out, placed = draw_layers(img, spec)
    warnings = warnings_for(spec, placed, *img.size)
    buf = io.BytesIO()
    if source_format in ("JPEG", "MPO"):
        out.save(buf, format="JPEG", quality=94, subsampling=0, optimize=True)
        return buf.getvalue(), ".jpg", "image/jpeg", warnings
    from PIL.PngImagePlugin import PngInfo

    meta = PngInfo()
    meta.add_text("sketchmaker:text_overlay", json.dumps(spec.model_dump(), ensure_ascii=False))
    out.save(buf, format="PNG", pnginfo=meta, compress_level=6)
    return buf.getvalue(), ".png", "image/png", warnings


def headline_of(spec: Spec) -> str:
    for layer in spec.layers:
        if layer.role == "headline":
            return layer.text.replace("\n", " ")
    return spec.layers[0].text.replace("\n", " ")
