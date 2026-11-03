"""Logo generator: prompt building, input checks and the Ideogram Vector calls.

Three fal endpoints:
- ideogram/vector/text-to-vector turns a description (plus optional reference
  images) into SVG logos.
- ideogram/vector/image-to-vector traces an existing image into an SVG.
- google/nano-banana-2.1/edit places a finished mark on a styled 16:9
  backdrop (showcase images, stored as raster gallery images).

Every SVG fal returns is downloaded through url_fetch, sanitised
(app/utils/svg_sanitize.py) and only then stored, because stored files may be
served same-origin under /static.
"""

from __future__ import annotations

import base64
import binascii
import logging
import random
import re
import uuid
from dataclasses import dataclass

import httpx
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.clients.fal_client import _image_dimensions, build_edit_arguments, validate_url
from app.services.fal_keys import get_sync_client
from app.services.storage_service import STATIC_PREFIX, UnsafeMediaPath, read_local_media
from app.services.url_fetch import UnsafeURLError, afetch_bytes
from app.utils.svg_sanitize import SVGSanitizeError, sanitize_svg

logger = logging.getLogger(__name__)

TEXT_TO_VECTOR = "ideogram/vector/text-to-vector"
IMAGE_TO_VECTOR = "ideogram/vector/image-to-vector"

MODEL_PROMPT_LIMIT = 9500
REFERENCE_MAX_BYTES = 10 * 1024 * 1024
VECTORIZE_MAX_BYTES = 20 * 1024 * 1024
SVG_MAX_BYTES = 10 * 1024 * 1024
MAX_REFERENCES = 5

QUALITIES = ("low", "medium", "high")
ASPECT_RATIOS = ("1:1", "4:3", "3:4", "3:2", "16:9", "3:1", "4:1", "2:1")
VECTORIZE_MODES = ("default", "simple")

# Style presets and the descriptor each adds to the prompt.
STYLE_DESCRIPTORS: dict[str, str] = {
    "minimal": "a minimalist logo: one simple, memorable mark built from very few shapes with generous negative space",
    "wordmark": "a wordmark logo: the brand name set in distinctive, custom-looking typography is the whole logo",
    "lettermark": "a lettermark (monogram) logo built from the brand's initials, tightly interlocked",
    "emblem": "an emblem logo: lettering and symbol enclosed together inside a badge, seal or crest shape",
    "mascot": "a mascot logo: a friendly illustrated character with bold, confident outlines",
    "abstract": "an abstract logo mark: a distinctive non-literal form that suggests the idea rather than depicting it",
    "geometric": "a geometric logo constructed from precise circles, lines and polygons on a strict grid",
    "vintage": "a vintage retro logo with classic heritage typography and a timeless badge feel",
    "hand-drawn": "a hand-drawn logo with organic, confident brush or pen strokes",
}

# Personality sliders of the brief: axis -> (word at -2, word at +2).
PERSONALITY_AXES: dict[str, tuple[str, str]] = {
    "tone": ("classic", "modern"),
    "mood": ("playful", "serious"),
    "energy": ("calm", "energetic"),
    "market": ("accessible", "luxurious"),
    "form": ("minimal", "ornate"),
}

# Lettering preference of the brief (keys match logo_fonts.FONT_PAIRINGS).
FONT_STYLE_DESCRIPTORS: dict[str, str] = {
    "sans": "clean sans-serif lettering",
    "geometric": "geometric sans-serif lettering",
    "serif": "elegant serif lettering",
    "display": "bold, expressive display lettering",
    "condensed": "tall condensed lettering",
    "rounded": "soft, rounded, friendly lettering",
    "script": "flowing script lettering",
    "tech": "technical, monospaced-feeling lettering",
}

MAX_PALETTE = 5


# Explore directions: each concept of a request follows a different pattern
# family instead of N takes on one prompt. Only for symbol-led styles (or no
# style), where the mark is free to change construction.
DIRECTION_STYLES = (None, "minimal", "abstract", "geometric")


@dataclass(frozen=True)
class PatternFamily:
    key: str
    name: str
    motifs: tuple[str, str]  # the second is used once every family has had a turn
    rationale: str  # "{concept}" is the brief's concept, shortened


PATTERN_FAMILIES: tuple[PatternFamily, ...] = (
    PatternFamily(
        "geometry", "Pure geometry",
        ("concentric rings or broken arcs that share one centre",
         "two or three overlapping circles or nested polygons where the overlap carves out the form"),
        "{concept}, distilled into circles and arcs: a precise, engineered mark that stays crisp at small sizes.",
    ),
    PatternFamily(
        "dots", "Dot matrix",
        ("a grid or ring of evenly spaced dots that together describe the form",
         "dots or capsules of graded size following one path, or a tight honeycomb cluster"),
        "{concept}, built from a rhythm of dots: modular and digital, at home on screens and in data.",
    ),
    PatternFamily(
        "lines", "Line system",
        ("parallel lines of one weight clipped inside a single simple silhouette",
         "one continuous line that bends into a wave or a spiral"),
        "{concept}, drawn with parallel strokes: movement and flow inside one clear silhouette.",
    ),
    PatternFamily(
        "dots_geometry", "Dots and geometry",
        ("one bold geometric shape with a single dot or a short row of dots as the accent",
         "a ring or arc with a few dots placed on its path like orbits"),
        "{concept}, anchored by one solid shape with a dot as the focal point: simple but lively.",
    ),
    PatternFamily(
        "lines_geometry", "Lines and geometry",
        ("a solid geometric shape sliced by a few parallel cuts",
         "an outlined shape in a steady stroke with one line breaking through it"),
        "{concept}, framed by a clean shape and cut by fine lines: structured, with a sense of direction.",
    ),
    PatternFamily(
        "network", "Node network",
        ("a few nodes of different sizes joined by smooth curved links",
         "two or three offset layers of the same flat shape, stacked to suggest depth without shading"),
        "{concept}, shown as linked nodes and layers: connection, systems and growth in one mark.",
    ),
)

MINIMAL_RULES = (
    "Minimal construction: one or two core elements, one clear focal point, about 40 to 50 percent of the area "
    "left empty, one consistent stroke weight, a deliberate touch of asymmetry, rounded cut-outs where shapes "
    "meet. Flat solid color only: no gradients, no shadows, no decorative outlines."
)


@dataclass(frozen=True)
class PatternDirection:
    family: PatternFamily
    motif: str

    @property
    def name(self) -> str:
        return self.family.name

    def rationale(self, prompt: str) -> str:
        return self.family.rationale.format(concept=_concept_phrase(prompt))


def pattern_directions(count: int, seed: int) -> list[PatternDirection]:
    """One direction per concept, each from a different family while there are
    families left. The order is shuffled by the request seed, so a seed
    reproduces the same set; past six concepts the families come round again
    with their second motif."""
    order = random.Random(seed).sample(PATTERN_FAMILIES, len(PATTERN_FAMILIES))
    out = []
    for index in range(count):
        family = order[index % len(order)]
        out.append(PatternDirection(family, family.motifs[(index // len(order)) % len(family.motifs)]))
    return out


def _concept_phrase(prompt: str, limit: int = 70) -> str:
    """The brief's concept as a short opening phrase for a rationale: its first
    clause, cut at a word boundary."""
    text = _clean_text(prompt)
    text = re.split(r"[.;:!?\n]|,\s", text, maxsplit=1)[0].strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",")
    if not text:
        return "The concept"
    return text[0].upper() + text[1:]


_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
_DATA_URL = re.compile(r"^data:(image/(?:png|jpeg|jpg|webp));base64,", re.IGNORECASE)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")


class LogoInputError(ValueError):
    """The request cannot be processed as given (maps to HTTP 400)."""


class LogoGenerationError(RuntimeError):
    """fal returned nothing usable (maps to HTTP 502)."""


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return _WHITESPACE.sub(" ", _CONTROL_CHARS.sub("", value)).strip()


def _personality(values: dict[str, int] | None) -> str:
    words = []
    for axis, value in (values or {}).items():
        if axis not in PERSONALITY_AXES or not isinstance(value, int) or value == 0:
            continue
        low, high = PERSONALITY_AXES[axis]
        word = high if value > 0 else low
        words.append(f"very {word}" if abs(value) >= 2 else word)
    return ", ".join(words)


def build_logo_prompt(
    prompt: str,
    brand_name: str | None = None,
    style: str | None = None,
    colors: str | None = None,
    has_references: bool = False,
    *,
    tagline: str | None = None,
    include_tagline: bool = False,
    industry: str | None = None,
    personality: dict[str, int] | None = None,
    symbol_ideas: str | None = None,
    palette: list[str] | None = None,
    font_style: str | None = None,
    avoid: str | None = None,
    symbol_only: bool = False,
    direction: PatternDirection | None = None,
) -> str:
    """The prompt sent to text-to-vector, built from the brief.

    `palette` holds #RRGGBB values validated by the router. With
    `symbol_only` the model draws an icon without any lettering; the studio
    then sets the name in a real font (wordmark lockup), which keeps the
    spelling exact. A `direction` (explore directions) adds its pattern
    family and the minimalism rules.
    """
    description = _clean_text(prompt)
    # Double quotes delimit the brand name in the prompt, so it cannot hold any.
    brand = _clean_text(brand_name).replace('"', "'")
    line = _clean_text(tagline).replace('"', "'")
    color_words = _clean_text(colors)
    sector = _clean_text(industry)
    ideas = _clean_text(symbol_ideas)
    avoid_text = _clean_text(avoid)
    mood = _personality(personality)
    with_tagline = bool(brand and line and include_tagline and not symbol_only)

    if symbol_only:
        lines = [f"A professional logo symbol (icon only) for a brand called {brand}." if brand
                 else "A professional logo symbol (icon only)."]
    elif brand:
        lines = [f'A professional logo for the brand "{brand}".']
    else:
        lines = ["A professional logo."]
    if sector:
        lines.append(f"Industry: {sector.rstrip('.')}.")
    if style and style in STYLE_DESCRIPTORS:
        lines.append(f"Style: {STYLE_DESCRIPTORS[style]}.")
    lines.append(f"Concept: {description.rstrip('.')}.")
    if ideas:
        lines.append(f"Symbol ideas: {ideas.rstrip('.')}.")
    if mood:
        lines.append(f"Brand personality: {mood}.")
    if direction is not None:
        lines.append(f"Design direction, {direction.name.lower()}: build the mark from {direction.motif}.")
        lines.append(MINIMAL_RULES)
    if symbol_only:
        lines.append("Symbol only: no letters, words, initials or numbers anywhere in the artwork.")
    elif brand:
        lines.append(f'Render the brand name exactly as "{brand}", with that spelling and capitalisation.')
        if with_tagline:
            lines.append(f'Below the name, set the tagline "{line}" in smaller letters, spelled exactly. '
                         "No other words.")
        else:
            lines.append("It is the only text in the logo: no taglines, slogans or extra words.")
        if font_style in FONT_STYLE_DESCRIPTORS:
            lines.append(f"Lettering: {FONT_STYLE_DESCRIPTORS[font_style]}.")
    else:
        lines.append("Do not add any lettering unless the concept asks for it.")
    if line and not with_tagline:
        lines.append(f"Brand promise, for context only and not to be written: {line.rstrip('.')}.")
    if palette:
        lines.append(f"Color palette, use only these solid colors: {', '.join(p.lower() for p in palette)}.")
        if color_words:
            lines.append(f"Color notes: {color_words}.")
    elif color_words:
        lines.append(f"Color palette: {color_words}.")
    else:
        lines.append("Use a restrained palette of two or three solid colors.")
    if avoid_text:
        lines.append(f"Avoid: {avoid_text.rstrip('.')}.")
    if has_references:
        lines.append(_REFERENCE_SENTENCE)
    lines.append(
        "Flat vector logo, clean shapes, crisp edges, centered, plain background, balanced negative space, "
        "scalable and legible at small sizes."
    )
    lines.append(
        "No mockups, no business cards, no signage, no photographs, no 3D rendering, no textures, no drop shadows, "
        "no frames around the artwork."
    )
    final = " ".join(lines)
    if len(final) > MODEL_PROMPT_LIMIT:
        final = final[:MODEL_PROMPT_LIMIT].rstrip()
    return final


_REFERENCE_SENTENCE = "Follow the reference images for the overall look and shapes while making an original, clean logo."


def build_iteration_prompt(base_prompt: str | None, instruction: str | None) -> str:
    """Prompt for a new round from an existing logo, which is sent as the
    reference image: a revision when there is an instruction, otherwise close
    variations ("more like this")."""
    base = _clean_text(base_prompt) or build_logo_prompt("a clean, memorable mark")
    base = base.replace(_REFERENCE_SENTENCE, "").strip()
    change = _clean_text(instruction)
    if change:
        lead = ("Revise the logo in the reference image. Keep its concept, layout and colors except for this "
                f"change: {change.rstrip('.')}.")
    else:
        lead = ("Create a close variation of the logo in the reference image: same concept, brand name, palette "
                "and style, with a fresh take on the composition and details.")
    final = f"{lead} Original brief: {base}"
    if len(final) > MODEL_PROMPT_LIMIT:
        final = final[:MODEL_PROMPT_LIMIT].rstrip()
    return final


# ---------------------------------------------------------------------------
# Input images
# ---------------------------------------------------------------------------

def sniff_image_type(data: bytes) -> str | None:
    """MIME type from the file signature, for the formats fal accepts."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def load_input_image(value: str, max_bytes: int, label: str = "Image") -> tuple[bytes, str]:
    """Bytes and MIME type of a data URL, https URL or one of our own /static files,
    checked for size and type."""
    value = (value or "").strip()
    limit_mb = max_bytes // (1024 * 1024)
    if value.startswith("data:"):
        ok, error = validate_url(value)
        match = _DATA_URL.match(value)
        if not ok or not match:
            raise LogoInputError(f"{label} must be a PNG, JPEG or WebP image")
        payload = value[match.end():]
        # Reject before decoding when the encoded size already shows it is too big.
        if len(payload) * 3 // 4 > max_bytes + 3:
            raise LogoInputError(f"{label} is larger than {limit_mb} MB")
        try:
            data = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError):
            raise LogoInputError(f"{label} is not valid base64 image data")
    elif value.lower().startswith("https://"):
        ok, error = validate_url(value, allow_data_urls=False)
        if not ok:
            logger.warning("%s URL rejected: %s", label, error)
            raise LogoInputError(f"{label} link could not be used. Upload the image instead.")
        try:
            data = await afetch_bytes(value, max_bytes=max_bytes, timeout=30.0)
        except UnsafeURLError as exc:
            logger.warning("%s URL could not be fetched: %s", label, exc)
            raise LogoInputError(f"{label} link could not be used. Upload the image instead.")
        except httpx.HTTPError:
            raise LogoInputError(f"{label} could not be downloaded")
    elif value.startswith(STATIC_PREFIX):
        # One of our own files: url_fetch refuses local addresses, so read the disk.
        try:
            path = read_local_media(value)
        except UnsafeMediaPath:
            logger.warning("%s path rejected", label)
            path = None
        if path is None:
            raise LogoInputError(f"{label} could not be found. Upload the image instead.")
        if path.stat().st_size > max_bytes:
            raise LogoInputError(f"{label} is larger than {limit_mb} MB")
        data = await run_in_threadpool(path.read_bytes)
    else:
        raise LogoInputError(f"{label} must be an uploaded image or an https URL")

    if len(data) > max_bytes:
        raise LogoInputError(f"{label} is larger than {limit_mb} MB")
    mime = sniff_image_type(data)
    if mime not in _ALLOWED_IMAGE_TYPES:
        raise LogoInputError(f"{label} must be a PNG, JPEG or WebP image")
    return data, mime


def _upload_to_fal(client, data: bytes, mime: str) -> str:
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime]
    return client.upload(data, mime, file_name=f"logo_input_{uuid.uuid4().hex}.{ext}")


async def prepare_fal_image(db: Session, value: str, max_bytes: int, label: str) -> str:
    """Check an input image and hand fal a URL for it.

    The checked bytes are uploaded to fal storage, so fal receives exactly what
    was validated (a user URL could change between the check and fal's fetch)
    and large uploads do not travel inside the JSON request.
    """
    data, mime = await load_input_image(value, max_bytes, label)
    client = get_sync_client(db)
    try:
        return await run_in_threadpool(_upload_to_fal, client, data, mime)
    except Exception as exc:
        logger.warning("fal upload failed for %s: %s", label, exc)
        raise LogoGenerationError("Could not upload the image for processing") from exc


# ---------------------------------------------------------------------------
# fal calls and result handling
# ---------------------------------------------------------------------------

async def call_fal(db: Session, endpoint: str, arguments: dict) -> dict:
    """Run a blocking fal request in the threadpool so the worker keeps serving."""
    client = get_sync_client(db)
    try:
        result = await run_in_threadpool(client.subscribe, endpoint, arguments=arguments)
    except Exception as exc:
        logger.warning("fal %s failed: %s", endpoint, exc)
        raise LogoGenerationError("The logo model did not return a result") from exc
    if not isinstance(result, dict):
        raise LogoGenerationError("The logo model returned an unexpected response")
    return result


async def store_result_svgs(result: dict, user_id: int, limit: int) -> list[dict]:
    """Download, sanitise and store up to `limit` SVGs from a fal result.

    Files that fail to download or are not valid SVG are skipped (and logged);
    the caller counts only what was stored.
    """
    stored: list[dict] = []
    for item in (result.get("images") or [])[:limit]:
        url = item.get("url") if isinstance(item, dict) else None
        if not url:
            continue
        try:
            raw = await afetch_bytes(url, max_bytes=SVG_MAX_BYTES)
            stored.append(await store_svg(raw, user_id))
        except (UnsafeURLError, httpx.HTTPError, SVGSanitizeError) as exc:
            logger.warning("Discarded a logo SVG from fal: %s", exc)
            continue
    return stored


async def store_svg(data: bytes, user_id: int) -> dict:
    """Sanitise and store one SVG. Raises SVGSanitizeError for invalid input."""
    from app.services.storage_service import storage_service

    clean = sanitize_svg(data, max_bytes=SVG_MAX_BYTES)
    filename = f"logo_{uuid.uuid4().hex}.svg"
    public_url = await storage_service.upload_file(
        file_data=clean.data,
        filename=filename,
        storage_type="images",
        content_type="image/svg+xml",
        user_id=user_id,
    )
    return {"filename": filename, "url": public_url, "width": clean.width, "height": clean.height}


async def load_stored_svg(filename: str, user_id: int) -> bytes:
    """The stored SVG of a logo (sanitised again by whoever edits it)."""
    from app.services.storage_service import storage_service

    data = await storage_service.get_file_bytes(filename, "images", user_id=user_id)
    if not data:
        raise LogoInputError("The logo file could not be found")
    return data


# ---------------------------------------------------------------------------
# Showcase images
# ---------------------------------------------------------------------------

SHOWCASE_MODEL = "google/nano-banana-2.1/edit"
SHOWCASE_RESOLUTION = "2k"  # also the pricing.edit_key resolution
SHOWCASE_ASPECT = "16:9"
SHOWCASE_MAX = 4
SHOWCASE_VERSION = "v1.0"
SHOWCASE_IMAGE_MAX_BYTES = 30 * 1024 * 1024

# How the mark is colored on each kind of backdrop.
_MARK_COLOR = {
    "dark": "pure white",
    "light": "near-black (#111111)",
    "vivid": "pure white or near-black, whichever stands out more clearly against the color behind it",
}


@dataclass(frozen=True)
class ShowcaseBackground:
    name: str
    tone: str  # key of _MARK_COLOR
    scene: str


# Backdrops (ids match the frontend list in LogoStudio). The prompt is built
# only from these, never from text the client sends.
SHOWCASE_BACKGROUNDS: dict[str, ShowcaseBackground] = {
    "void": ShowcaseBackground(
        "The Void", "dark",
        "a pure black field with a very fine silver grain and a faint, cold blue glow rising from one corner",
    ),
    "frosted-horizon": ShowcaseBackground(
        "Frosted Horizon", "dark",
        "a deep slate backdrop with a subtle brushed metal or honed stone texture and a soft blue-grey haze "
        "drifting across the middle",
    ),
    "fluid-abyss": ShowcaseBackground(
        "Fluid Abyss", "dark",
        "a deep violet to Klein blue backdrop where slow, softly blurred currents of warm orange and electric "
        "blue melt into each other",
    ),
    "studio-spotlight": ShowcaseBackground(
        "Studio Spotlight", "dark",
        "a warm dark charcoal backdrop with low-light film grain, lit from one side so the light falls away "
        "gently into shadow",
    ),
    "analog-liquid": ShowcaseBackground(
        "Analog Liquid", "vivid",
        "a saturated backdrop of molten orange, Klein blue or acid lime with a metallic shimmer and swirling, "
        "chaotic liquid marbling",
    ),
    "led-matrix": ShowcaseBackground(
        "LED Matrix", "dark",
        "a black backdrop filled with a softly glowing dot-matrix display pattern, with faint scan lines and the "
        "small flaws of an old screen",
    ),
    "editorial-paper": ShowcaseBackground(
        "Editorial Paper", "light",
        "an off-white pearl paper backdrop with a visible cold-press watercolor grain and slightly warmer, "
        "darker corners",
    ),
    "iridescent-frost": ShowcaseBackground(
        "Iridescent Frost", "light",
        "a light silver-grey backdrop seen through frosted glass, with faint holographic hints of lilac, mint "
        "and peach",
    ),
    "morning-aura": ShowcaseBackground(
        "Morning Aura", "light",
        "a warm ivory backdrop with large, heavily blurred blooms of pastel mint, baby blue and dawn orange",
    ),
    "clinical-studio": ShowcaseBackground(
        "Clinical Studio", "light",
        "a clean white to cool grey backdrop with a fine digital noise and a barely visible soft gradient",
    ),
    "ui-container": ShowcaseBackground(
        "UI Container", "light",
        "a soft pale gradient backdrop with one large rounded frosted-glass panel in the centre holding the "
        "mark, with delicate micro shadows along its edges, like a modern app interface",
    ),
    "swiss-flat": ShowcaseBackground(
        "Swiss Flat", "dark",
        "a perfectly flat, solid deep green, burgundy or navy backdrop with no texture, no gradient and no "
        "lighting effects",
    ),
}


def showcase_text(value: str | None, limit: int) -> str:
    """A brand name or descriptor for the showcase typography: one line, no
    double quotes (they delimit literal text in the prompt)."""
    return _clean_text(value).replace('"', "'")[:limit].strip()


@dataclass(frozen=True)
class ShowcaseText:
    """The micro typography the app draws on a showcase image."""
    brand: str
    descriptor: str
    version: str = SHOWCASE_VERSION


# The bundled font draws Latin, Greek and Cyrillic (plus general
# punctuation). Text outside that is left to the image model, as before.
def _drawable(text: str) -> bool:
    return all(ord(c) < 0x530 or 0x2000 <= ord(c) <= 0x206F for c in text)


def showcase_overlay(brand_name: str = "", descriptor: str = "", typography: bool = True) -> ShowcaseText | None:
    """The text to draw on each showcase image, or None when there is none
    or the bundled font cannot draw it."""
    if not typography:
        return None
    text = ShowcaseText(showcase_text(brand_name, 60).upper(), showcase_text(descriptor, 48))
    if not _drawable(text.brand + text.descriptor):
        return None
    return text


def build_showcase_prompt(background_id: str, brand_name: str = "", descriptor: str = "",
                          typography: bool = True) -> str:
    """The edit prompt for one showcase image. Raises KeyError for an unknown
    backdrop (the router validates ids first).

    The image model draws no text: the brand name, version and descriptor
    are set afterwards with Pillow in a bundled font (draw_showcase_text),
    so they are spelled exactly. Only text the bundled font cannot draw is
    still left to the model."""
    bg = SHOWCASE_BACKGROUNDS[background_id]
    lines = [
        "Create a wide 16:9 brand showcase image.",
        "The input image shows a logo mark as a dark shape on a white field: use only that shape and ignore the "
        "white field.",
        "Reproduce the mark exactly, with the same outline, proportions and inner cut-outs, adding and removing "
        "nothing.",
        "Place it in the exact centre of the frame at about a quarter of the frame height, as a perfectly flat "
        f"graphic in {_MARK_COLOR[bg.tone]}.",
        "The mark itself has no gradient, bevel, glow, shadow or texture.",
        f"Background: {bg.scene}.",
        "The background stays quiet so the mark is the single point of focus, with calm, even margins at the "
        "corners and along the bottom edge.",
    ]
    if typography and showcase_overlay(brand_name, descriptor, typography) is None:
        brand = showcase_text(brand_name, 60).upper()
        line = showcase_text(descriptor, 48)
        parts = []
        if brand:
            parts.append(f'"{brand}" in small uppercase letters in the top-left corner')
        parts.append(f'"{SHOWCASE_VERSION}" in the top-right corner')
        if line:
            parts.append(f'"{line}" in small letters centred near the bottom edge')
        lines.append(
            "Add restrained Swiss-style micro typography in a clean neo-grotesque sans-serif, in the same color as "
            "the mark at lower opacity, with generous margins: " + ", ".join(parts) + "."
        )
        lines.append("Spell every word exactly as given. No other text anywhere.")
    else:
        lines.append("No text anywhere in the image.")
    lines.append(
        "No other logos, watermarks, devices, products, hands or people. Clean, premium, gallery-quality "
        "presentation."
    )
    return " ".join(lines)


SHOWCASE_FONT = ("inter", "Inter-Variable.ttf")


def _showcase_font(size: int):
    import os

    from PIL import ImageFont

    from app.services.logo_fonts import FONT_DIR

    font = ImageFont.truetype(os.path.join(FONT_DIR, *SHOWCASE_FONT), size)
    try:
        font.set_variation_by_name("Medium")
    except Exception:
        pass  # a static build of the font, or no named instance
    return font


def _tracked_width(font, text: str, tracking: float) -> float:
    if not text:
        return 0.0
    return sum(font.getlength(c) for c in text) + tracking * (len(text) - 1)


def _draw_tracked(draw, x: float, y: float, text: str, font, fill, tracking: float) -> None:
    for c in text:
        draw.text((x, y), c, font=font, fill=fill)
        x += font.getlength(c) + tracking


def draw_showcase_text(data: bytes, text: ShowcaseText) -> bytes:
    """The showcase image with its micro typography drawn in: the brand name
    top left, the version top right, the descriptor centred at the foot, in
    white or near-black (whichever reads on the pixels behind each line) at
    lower opacity. Returns PNG bytes."""
    from io import BytesIO

    from PIL import Image as PILImage, ImageDraw, ImageStat

    with PILImage.open(BytesIO(data)) as src:
        base = src.convert("RGBA")
    width, height = base.size
    margin = round(height * 0.06)
    size = max(12, round(height * 0.022))
    tracking = size * 0.14
    font = _showcase_font(size)
    ascent, descent = font.getmetrics()
    line_height = ascent + descent

    placements = []
    if text.brand:
        placements.append((text.brand, margin, margin))
    if text.version:
        placements.append((text.version, width - margin - _tracked_width(font, text.version, tracking), margin))
    if text.descriptor:
        w = _tracked_width(font, text.descriptor, size * 0.04)
        placements.append((text.descriptor, (width - w) / 2, height - margin - line_height))

    layer = PILImage.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for value, x, y in placements:
        spacing = size * 0.04 if value == text.descriptor else tracking
        box = (int(max(0, x)), int(max(0, y)),
               int(min(width, x + _tracked_width(font, value, spacing) + 1)), int(min(height, y + line_height)))
        lum = ImageStat.Stat(base.crop(box).convert("L")).mean[0] if box[2] > box[0] and box[3] > box[1] else 0
        fill = (17, 17, 17, 200) if lum > 140 else (255, 255, 255, 190)
        _draw_tracked(draw, x, y, value, font, fill, spacing)

    out = BytesIO()
    PILImage.alpha_composite(base, layer).convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


async def render_showcase(db: Session, mark_url: str, prompt: str, user_id: int,
                          overlay: ShowcaseText | None = None) -> dict | None:
    """One showcase image from the edit model, with ``overlay`` drawn in when
    given, stored in the user's images folder. None when fal fails or returns
    nothing usable (logged); the caller leaves that image out."""
    from app.services.storage_service import storage_service

    arguments = build_edit_arguments(
        SHOWCASE_MODEL, prompt, [mark_url], aspect_ratio=SHOWCASE_ASPECT,
        resolution=SHOWCASE_RESOLUTION.upper(), output_format="png", num_images=1,
    )
    try:
        result = await call_fal(db, SHOWCASE_MODEL, arguments)
    except LogoGenerationError:
        return None
    for item in (result.get("images") or [])[:1]:
        url = item.get("url") if isinstance(item, dict) else None
        if not url:
            continue
        try:
            data = await afetch_bytes(url, max_bytes=SHOWCASE_IMAGE_MAX_BYTES)
        except (UnsafeURLError, httpx.HTTPError) as exc:
            logger.warning("Discarded a showcase image from fal: %s", exc)
            continue
        mime = sniff_image_type(data)
        if mime not in _ALLOWED_IMAGE_TYPES:
            logger.warning("Discarded a showcase image from fal: not PNG, JPEG or WebP")
            continue
        if overlay is not None:
            try:
                data = await run_in_threadpool(draw_showcase_text, data, overlay)
                mime = "image/png"
                item = {}  # the dimensions are read from the new file
            except Exception:
                # fal has billed for the image: deliver it without the text rather
                # than not at all.
                logger.exception("Could not draw the showcase text; storing the image without it")
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime]
        filename = f"logo_showcase_{uuid.uuid4().hex}.{ext}"
        public_url = await storage_service.upload_file(
            file_data=data,
            filename=filename,
            storage_type="images",
            content_type=mime,
            user_id=user_id,
        )
        width, height = _image_dimensions(item, data)
        return {"filename": filename, "url": public_url, "width": width, "height": height}
    return None
