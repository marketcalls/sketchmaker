"""Deterministic logo edits and brand assets: no AI calls.

Everything here works on SVG that svg_sanitize has already rebuilt, and every
result goes through sanitize_svg again before it is returned, so a stored or
served file is always the sanitiser's output:

- palette extraction (dominant colors, weighted by drawn area)
- background removal and knockout of background-colored shapes
- recolor (exact or tolerant color mapping), one-color and inverted versions
- wordmark lockups: the brand name set in a bundled OFL font as vector paths
  next to (or under) the symbol, so the spelling is always exact
- a one-page brand sheet (logo, clear space, variations, palette, type)

Colors that enter from a request are validated as #RRGGBB by the router and
are only ever written as #rrggbb by this module.
"""

from __future__ import annotations

import colorsys
import copy
import logging
import math
import re
from dataclasses import dataclass

from lxml import etree

from app.services import logo_fonts
from app.utils.svg_sanitize import SVG_NS, XLINK_NS, SVGSanitizeError, sanitize_svg

logger = logging.getLogger(__name__)

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
EDIT_MAX_BYTES = 12 * 1024 * 1024
SHEET_MAX_BYTES = 40 * 1024 * 1024

_NAMED = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0), "green": (0, 128, 0),
    "blue": (0, 0, 255), "yellow": (255, 255, 0), "gray": (128, 128, 128), "grey": (128, 128, 128),
    "orange": (255, 165, 0), "purple": (128, 0, 128), "navy": (0, 0, 128), "silver": (192, 192, 192),
    "maroon": (128, 0, 0), "teal": (0, 128, 128), "lime": (0, 255, 0), "aqua": (0, 255, 255),
    "cyan": (0, 255, 255), "fuchsia": (255, 0, 255), "magenta": (255, 0, 255), "olive": (128, 128, 0),
}
_COLOR_TOKEN = re.compile(r"#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3,4}\b|rgba?\(\s*[^)]*\)", re.I)
_URL_REF = re.compile(r"url\(\s*['\"]?\s*#([A-Za-z_][\w.\-:]*)\s*['\"]?\s*\)", re.I)
_CSS_PAINT = re.compile(r"(?<![\w-])(fill|stroke|stop-color|flood-color|lighting-color|color)(\s*:\s*)([^;}{]+)", re.I)
PAINT_ATTRS = ("fill", "stroke", "stop-color", "flood-color", "lighting-color", "color")

_NON_RENDERED = {"defs", "clipPath", "mask", "symbol", "pattern", "marker", "linearGradient",
                 "radialGradient", "filter", "style", "title", "desc", "metadata"}
_SHAPES = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}

RGB = tuple[int, int, int]
Box = tuple[float, float, float, float]  # min x, min y, max x, max y


class LogoEditError(ValueError):
    """The SVG cannot be edited as asked (maps to HTTP 400)."""


# ---------------------------------------------------------------------------
# Parsing and output
# ---------------------------------------------------------------------------

def _parser() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                           dtd_validation=False, huge_tree=False, remove_comments=True,
                           remove_pis=True, recover=False)


def load(data: bytes) -> etree._Element:
    """Sanitise and parse an SVG; the tree only holds allowlisted content."""
    try:
        clean = sanitize_svg(data, max_bytes=EDIT_MAX_BYTES)
    except SVGSanitizeError as exc:
        logger.warning(f"Logo SVG could not be loaded for editing: {exc}")
        raise LogoEditError("The logo file could not be read. Generate the logo again and retry.") from exc
    return etree.fromstring(clean.data, parser=_parser())


def finish(root: etree._Element, max_bytes: int = EDIT_MAX_BYTES) -> bytes:
    """Serialise and rebuild through the sanitiser."""
    raw = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
    try:
        return sanitize_svg(raw, max_bytes=max_bytes).data
    except SVGSanitizeError as exc:
        logger.warning(f"Edited logo SVG failed sanitising: {exc}")
        raise LogoEditError("The edited logo could not be saved. Try a different change.") from exc


def _local(el: etree._Element) -> str:
    tag = el.tag if isinstance(el.tag, str) else ""
    return tag.rsplit("}", 1)[-1]


def _q(name: str) -> str:
    return f"{{{SVG_NS}}}{name}"


def _fmt(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

def parse_color(token: str) -> tuple[RGB, str | None] | None:
    """(r, g, b) and an alpha suffix to keep, or None when not a plain color."""
    t = token.strip().lower()
    if t in _NAMED:
        return _NAMED[t], None
    if t.startswith("#"):
        h = t[1:]
        if len(h) in (3, 4):
            rgb = tuple(int(c * 2, 16) for c in h[:3])
            return rgb, (h[3] * 2 if len(h) == 4 else None)  # type: ignore[return-value]
        if len(h) in (6, 8) and all(c in "0123456789abcdef" for c in h):
            rgb = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
            return rgb, (h[6:8] if len(h) == 8 else None)
        return None
    m = re.match(r"rgba?\(\s*([^)]*)\)$", t)
    if m:
        parts = [p for p in re.split(r"[\s,/]+", m.group(1)) if p]
        if len(parts) < 3:
            return None
        vals = []
        for p in parts[:3]:
            try:
                vals.append(round(float(p[:-1]) * 2.55) if p.endswith("%") else round(float(p)))
            except ValueError:
                return None
        rgb = tuple(max(0, min(255, v)) for v in vals)
        alpha = None
        if len(parts) >= 4:
            try:
                a = float(parts[3][:-1]) / 100 if parts[3].endswith("%") else float(parts[3])
                alpha = f"{max(0, min(255, round(a * 255))):02x}"
            except ValueError:
                alpha = None
        return rgb, alpha  # type: ignore[return-value]
    return None


def to_hex(rgb: RGB) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(round(c)))) for c in rgb))


def hex_to_rgb(value: str) -> RGB:
    if not HEX_COLOR.match(value or ""):
        raise LogoEditError(f"Not a #RRGGBB color: {value!r}")
    return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))


def _dist(a: RGB, b: RGB) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def luminance(rgb: RGB) -> float:
    def ch(c: float) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def invert_lightness(rgb: RGB) -> RGB:
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    r, g, b = colorsys.hls_to_rgb(h, 1 - l, s)
    return (round(r * 255), round(g * 255), round(b * 255))


def _map_value(value: str, fn, replace_all: str | None = None) -> str:
    """Apply fn to every color in a paint value. With replace_all, any paint
    other than none/transparent/currentColor/inherit becomes that color."""
    v = value.strip()
    low = v.lower()
    if low in ("none", "transparent", "currentcolor", "inherit", ""):
        return value
    if replace_all is not None:
        return replace_all
    if low in _NAMED:
        return to_hex(fn(_NAMED[low]))

    def sub(m: re.Match) -> str:
        parsed = parse_color(m.group(0))
        if not parsed:
            return m.group(0)
        rgb, alpha = parsed
        out = to_hex(fn(rgb))
        return out + alpha if alpha else out

    return _COLOR_TOKEN.sub(sub, value)


def _map_css(css: str, fn, replace_all: str | None = None) -> str:
    def sub(m: re.Match) -> str:
        return m.group(1) + m.group(2) + _map_value(m.group(3), fn, replace_all)
    return _CSS_PAINT.sub(sub, css)


def map_colors(root: etree._Element, fn, replace_all: str | None = None) -> None:
    """Rewrite every paint in the tree (attributes, style attributes, <style>)."""
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        for attr in PAINT_ATTRS:
            if attr in el.attrib:
                el.set(attr, _map_value(el.get(attr), fn, replace_all))
        if "style" in el.attrib:
            el.set("style", _map_css(el.get("style"), fn, replace_all))
        if _local(el) == "style" and el.text:
            el.text = _map_css(el.text, fn, replace_all)


# ---------------------------------------------------------------------------
# Geometry: transforms, path and shape bounding boxes
# ---------------------------------------------------------------------------

Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
_TRANSFORM = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)")
_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _mul(m: Matrix, n: Matrix) -> Matrix:
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (a * a2 + c * b2, b * a2 + d * b2, a * c2 + c * d2, b * c2 + d * d2,
            a * e2 + c * f2 + e, b * e2 + d * f2 + f)


def parse_transform(value: str | None) -> Matrix:
    m = IDENTITY
    if not value:
        return m
    for name, args in _TRANSFORM.findall(value):
        nums = [float(x) for x in _NUMBER.findall(args)]
        t = IDENTITY
        if name == "matrix" and len(nums) == 6:
            t = tuple(nums)  # type: ignore[assignment]
        elif name == "translate" and nums:
            t = (1, 0, 0, 1, nums[0], nums[1] if len(nums) > 1 else 0)
        elif name == "scale" and nums:
            t = (nums[0], 0, 0, nums[1] if len(nums) > 1 else nums[0], 0, 0)
        elif name == "rotate" and nums:
            r = math.radians(nums[0])
            cos, sin = math.cos(r), math.sin(r)
            t = (cos, sin, -sin, cos, 0, 0)
            if len(nums) == 3:
                cx, cy = nums[1], nums[2]
                t = _mul(_mul((1, 0, 0, 1, cx, cy), t), (1, 0, 0, 1, -cx, -cy))
        elif name == "skewX" and nums:
            t = (1, 0, math.tan(math.radians(nums[0])), 1, 0, 0)
        elif name == "skewY" and nums:
            t = (1, math.tan(math.radians(nums[0])), 0, 1, 0, 0)
        m = _mul(m, t)  # type: ignore[arg-type]
    return m


def _apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


_PATH_TOKEN = re.compile(r"([MmZzLlHhVvCcSsQqTtAa])|([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")
_ARGS = {"m": 2, "l": 2, "h": 1, "v": 1, "c": 6, "s": 4, "q": 4, "t": 2, "a": 7, "z": 0}


def _path_tokens(d: str) -> list:
    out: list = []
    i = 0
    n = len(d)
    current = None
    arg_index = 0
    while i < n:
        ch = d[i]
        if ch in " \t\r\n,":
            i += 1
            continue
        if ch.isalpha():
            if ch.lower() not in _ARGS:
                raise ValueError("bad path command")
            current = ch
            arg_index = 0
            out.append(ch)
            i += 1
            continue
        # Arc flags are single characters and may be packed together ("011").
        if current and current.lower() == "a" and arg_index % 7 in (3, 4) and ch in "01":
            out.append(float(ch))
            arg_index += 1
            i += 1
            continue
        m = _NUMBER.match(d, i)
        if not m:
            raise ValueError("bad path number")
        out.append(float(m.group(0)))
        arg_index += 1
        i = m.end()
    return out


def _cubic_extrema(p0, p1, p2, p3) -> list[float]:
    ts = []
    a = -p0 + 3 * p1 - 3 * p2 + p3
    b = 2 * (p0 - 2 * p1 + p2)
    c = p1 - p0
    if abs(a) < 1e-12:
        if abs(b) > 1e-12:
            ts.append(-c / b)
    else:
        disc = b * b - 4 * a * c
        if disc >= 0:
            r = math.sqrt(disc)
            ts += [(-b + r) / (2 * a), (-b - r) / (2 * a)]
    return [t for t in ts if 0 < t < 1]


def _cubic_at(p0, p1, p2, p3, t):
    u = 1 - t
    return u ** 3 * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t ** 3 * p3


def _arc_points(x1, y1, rx, ry, phi, large, sweep, x2, y2) -> list[tuple[float, float]]:
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [(x2, y2)]
    rx, ry = abs(rx), abs(ry)
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = (x1p ** 2) / (rx ** 2) + (y1p ** 2) / (ry ** 2)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        coef = -coef
    cxp, cyp = coef * rx * y1p / ry, -coef * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2

    def angle(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    pts = []
    for k in range(1, 25):
        t = t1 + dt * k / 24
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append((cp * x - sp * y + cx, sp * x + cp * y + cy))
    return pts


def path_points(d: str) -> list[tuple[float, float]]:
    """Points whose bounding box is the path's bounding box (extrema included)."""
    tokens = _path_tokens(d)
    pts: list[tuple[float, float]] = []
    i = 0
    cx = cy = sx = sy = 0.0
    last_ctrl = None
    last_cmd = ""
    cmd = None
    while i < len(tokens):
        tok = tokens[i]
        if isinstance(tok, str):
            cmd = tok
            i += 1
            if cmd in "Zz":
                cx, cy = sx, sy
                last_ctrl = None
                last_cmd = cmd
                continue
        if cmd is None:
            raise ValueError("path data must start with a command")
        lc = cmd.lower()
        rel = cmd.islower()
        need = _ARGS[lc]
        if need == 0:
            # Numbers after Z are malformed; stop rather than loop.
            break
        args = tokens[i:i + need]
        if len(args) < need or any(isinstance(a, str) for a in args):
            break
        i += need
        ox, oy = (cx, cy) if rel else (0.0, 0.0)
        if lc == "m":
            cx, cy = args[0] + ox, args[1] + oy
            sx, sy = cx, cy
            pts.append((cx, cy))
            cmd = "l" if rel else "L"
            last_ctrl = None
        elif lc == "l":
            cx, cy = args[0] + ox, args[1] + oy
            pts.append((cx, cy))
            last_ctrl = None
        elif lc == "h":
            cx = args[0] + (cx if rel else 0)
            pts.append((cx, cy))
            last_ctrl = None
        elif lc == "v":
            cy = args[0] + (cy if rel else 0)
            pts.append((cx, cy))
            last_ctrl = None
        elif lc in ("c", "s"):
            if lc == "c":
                x1, y1 = args[0] + ox, args[1] + oy
                x2, y2, x, y = args[2] + ox, args[3] + oy, args[4] + ox, args[5] + oy
            else:
                if last_ctrl is not None and last_cmd.lower() in ("c", "s"):
                    x1, y1 = 2 * cx - last_ctrl[0], 2 * cy - last_ctrl[1]
                else:
                    x1, y1 = cx, cy
                x2, y2, x, y = args[0] + ox, args[1] + oy, args[2] + ox, args[3] + oy
            for t in _cubic_extrema(cx, x1, x2, x):
                pts.append((_cubic_at(cx, x1, x2, x, t), _cubic_at(cy, y1, y2, y, t)))
            for t in _cubic_extrema(cy, y1, y2, y):
                pts.append((_cubic_at(cx, x1, x2, x, t), _cubic_at(cy, y1, y2, y, t)))
            pts.append((x, y))
            last_ctrl = (x2, y2)
            cx, cy = x, y
        elif lc in ("q", "t"):
            if lc == "q":
                qx, qy, x, y = args[0] + ox, args[1] + oy, args[2] + ox, args[3] + oy
            else:
                if last_ctrl is not None and last_cmd.lower() in ("q", "t"):
                    qx, qy = 2 * cx - last_ctrl[0], 2 * cy - last_ctrl[1]
                else:
                    qx, qy = cx, cy
                x, y = args[0] + ox, args[1] + oy
            # Quadratic as cubic for the extrema.
            c1 = (cx + 2 / 3 * (qx - cx), cy + 2 / 3 * (qy - cy))
            c2 = (x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y))
            for t in _cubic_extrema(cx, c1[0], c2[0], x) + _cubic_extrema(cy, c1[1], c2[1], y):
                pts.append((_cubic_at(cx, c1[0], c2[0], x, t), _cubic_at(cy, c1[1], c2[1], y, t)))
            pts.append((x, y))
            last_ctrl = (qx, qy)
            cx, cy = x, y
        elif lc == "a":
            x, y = args[5] + ox, args[6] + oy
            pts.extend(_arc_points(cx, cy, args[0], args[1], args[2], bool(args[3]), bool(args[4]), x, y))
            cx, cy = x, y
            last_ctrl = None
        last_cmd = lc
    return pts


def _length(value: str | None) -> float | None:
    if value is None:
        return None
    m = re.fullmatch(r"\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(px)?\s*", value)
    return float(m.group(1)) if m else None


def element_points(el: etree._Element) -> list[tuple[float, float]] | None:
    """Untransformed extreme points of a basic shape, or None if unknown."""
    name = _local(el)
    try:
        if name == "path":
            return path_points(el.get("d") or "") or None
        if name == "rect":
            x, y = _length(el.get("x")) or 0.0, _length(el.get("y")) or 0.0
            w, h = _length(el.get("width")), _length(el.get("height"))
            if not w or not h:
                return None
            return [(x, y), (x + w, y + h)]
        if name in ("circle", "ellipse"):
            cx, cy = _length(el.get("cx")) or 0.0, _length(el.get("cy")) or 0.0
            rx = _length(el.get("r") if name == "circle" else el.get("rx"))
            ry = _length(el.get("r") if name == "circle" else el.get("ry"))
            if not rx or not ry:
                return None
            return [(cx - rx, cy - ry), (cx + rx, cy + ry)]
        if name == "line":
            return [(_length(el.get("x1")) or 0.0, _length(el.get("y1")) or 0.0),
                    (_length(el.get("x2")) or 0.0, _length(el.get("y2")) or 0.0)]
        if name in ("polyline", "polygon"):
            nums = [float(n) for n in _NUMBER.findall(el.get("points") or "")]
            return [(nums[k], nums[k + 1]) for k in range(0, len(nums) - 1, 2)] or None
    except (ValueError, ZeroDivisionError):
        return None
    return None


def _box(points) -> Box | None:
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _union(a: Box | None, b: Box | None) -> Box | None:
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _hidden(el: etree._Element) -> bool:
    if (el.get("display") or "").strip() == "none":
        return True
    return "display:none" in (el.get("style") or "").replace(" ", "")


def drawn_shapes(root: etree._Element):
    """(element, accumulated transform) for every rendered basic shape."""
    def walk(node, matrix):
        for child in node:
            if not isinstance(child.tag, str):
                continue
            name = _local(child)
            if name in _NON_RENDERED or _hidden(child):
                continue
            m = _mul(matrix, parse_transform(child.get("transform")))
            if name == "svg":
                x, y = _length(child.get("x")) or 0.0, _length(child.get("y")) or 0.0
                m = _mul(m, (1, 0, 0, 1, x, y))
            if name in _SHAPES:
                yield child, m
            elif name in ("g", "svg"):
                yield from walk(child, m)
    yield from walk(root, parse_transform(root.get("transform")))


def shape_box(el: etree._Element, matrix: Matrix) -> Box | None:
    pts = element_points(el)
    if not pts:
        return None
    return _box([_apply(matrix, x, y) for x, y in pts])


def view_box(root: etree._Element) -> Box | None:
    vb = root.get("viewBox")
    if vb:
        parts = [float(p) for p in _NUMBER.findall(vb)]
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            return (parts[0], parts[1], parts[0] + parts[2], parts[1] + parts[3])
    w, h = _length(root.get("width")), _length(root.get("height"))
    if w and h:
        return (0.0, 0.0, w, h)
    return None


def content_box(root: etree._Element) -> Box | None:
    box = None
    for el, m in drawn_shapes(root):
        box = _union(box, shape_box(el, m))
    vb = view_box(root)
    if box is not None and vb is not None:
        # Clip to the canvas: shapes may bleed past it.
        box = (max(box[0], vb[0]), max(box[1], vb[1]), min(box[2], vb[2]), min(box[3], vb[3]))
        if box[2] <= box[0] or box[3] <= box[1]:
            box = None
    return box or vb


# ---------------------------------------------------------------------------
# Paint resolution, background, palette
# ---------------------------------------------------------------------------

def _style_prop(el: etree._Element, prop: str) -> str | None:
    style = el.get("style")
    if style:
        for part in style.split(";"):
            k, _, v = part.partition(":")
            if k.strip().lower() == prop:
                return v.strip()
    return None


def own_paint(el: etree._Element, prop: str) -> str | None:
    return _style_prop(el, prop) or el.get(prop)


def resolved_paint(el: etree._Element, prop: str = "fill") -> str:
    node = el
    while node is not None and isinstance(node.tag, str):
        value = own_paint(node, prop)
        if value and value.strip().lower() != "inherit":
            return value.strip()
        node = node.getparent()
    return "black" if prop == "fill" else "none"


def _opaque(el: etree._Element) -> bool:
    for prop in ("opacity", "fill-opacity"):
        v = own_paint(el, prop)
        if v is not None:
            try:
                if float(v) < 0.999:
                    return False
            except ValueError:
                return False
    return True


def find_background(root: etree._Element) -> tuple[etree._Element, RGB] | None:
    """The full-canvas solid shape painted first (model outputs carry a white
    one), with its color; None when the logo has no such background."""
    vb = view_box(root)
    if vb is None:
        return None
    w, h = vb[2] - vb[0], vb[3] - vb[1]
    tol_x, tol_y = w * 0.005, h * 0.005
    for el, m in drawn_shapes(root):
        name = _local(el)
        if name == "path":
            d = el.get("d") or ""
            if re.search(r"[CcSsQqTtAa]", d):
                return None
            try:
                if len(path_points(d)) > 8:
                    return None
            except ValueError:
                return None
        elif name == "rect":
            rx = _length(el.get("rx")) or 0.0
            if rx > min(w, h) * 0.01:
                return None
        elif name != "polygon":
            return None
        box = shape_box(el, m)
        if box is None or not (box[0] <= vb[0] + tol_x and box[1] <= vb[1] + tol_y
                               and box[2] >= vb[2] - tol_x and box[3] >= vb[3] - tol_y):
            return None
        if not _opaque(el):
            return None
        parsed = parse_color(resolved_paint(el, "fill"))
        if not parsed or parsed[1] not in (None, "ff"):
            return None
        return el, parsed[0]
    return None


def remove_background(root: etree._Element, knockout: bool = False) -> RGB | None:
    """Drop the background shape; with knockout, also every unstroked shape in
    the background color (counters and gaps drawn on top become holes)."""
    found = find_background(root)
    if not found:
        return None
    el, color = found
    el.getparent().remove(el)
    if knockout:
        for shape, _m in list(drawn_shapes(root)):
            stroke = resolved_paint(shape, "stroke").lower()
            if stroke not in ("none", "transparent"):
                continue
            parsed = parse_color(resolved_paint(shape, "fill"))
            if parsed and _dist(parsed[0], color) <= 6 and shape.getparent() is not None:
                shape.getparent().remove(shape)
    return color


def _gradient_stops(root: etree._Element, ref: str) -> list[RGB]:
    by_id = {e.get("id"): e for e in root.iter() if isinstance(e.tag, str) and e.get("id")}
    seen = set()
    grad = by_id.get(ref)
    while grad is not None and id(grad) not in seen:
        seen.add(id(grad))
        stops = []
        for stop in grad:
            if _local(stop) == "stop":
                parsed = parse_color(own_paint(stop, "stop-color") or "black")
                if parsed:
                    stops.append(parsed[0])
        if stops:
            return stops
        href = grad.get("href") or grad.get(f"{{{XLINK_NS}}}href") or ""
        grad = by_id.get(href[1:]) if href.startswith("#") else None
    return []


def palette(root: etree._Element, limit: int = 8) -> dict:
    """Dominant colors weighted by drawn area, similar shades merged."""
    bg = find_background(root)
    bg_el = bg[0] if bg else None
    weights: dict[RGB, float] = {}
    total_colors = set()

    def add(rgb: RGB, w: float) -> None:
        weights[rgb] = weights.get(rgb, 0.0) + w
        total_colors.add(rgb)

    for el, m in drawn_shapes(root):
        if el is bg_el:
            continue
        box = shape_box(el, m)
        area = max(1.0, (box[2] - box[0]) * (box[3] - box[1])) if box else 1.0
        fill = resolved_paint(el, "fill")
        stroke = resolved_paint(el, "stroke")
        for paint, w in ((fill, area), (stroke, area * 0.1)):
            low = paint.lower()
            if low in ("none", "transparent", "currentcolor"):
                continue
            ref = _URL_REF.search(paint)
            if ref:
                stops = _gradient_stops(root, ref.group(1))
                for rgb in stops:
                    add(rgb, w / len(stops))
                continue
            parsed = parse_color(paint)
            if parsed:
                add(parsed[0], w)

    clusters: list[list] = []  # [representative, weight]
    for rgb, w in sorted(weights.items(), key=lambda kv: -kv[1]):
        for cluster in clusters:
            if _dist(cluster[0], rgb) < 40:
                cluster[1] += w
                break
        else:
            clusters.append([rgb, w])
    total = sum(c[1] for c in clusters) or 1.0
    clusters.sort(key=lambda c: -c[1])
    return {
        "colors": [{"hex": to_hex(c[0]), "share": round(c[1] / total, 4)} for c in clusters[:limit]],
        "background": to_hex(bg[1]) if bg else None,
        "total_colors": len(total_colors),
    }


# ---------------------------------------------------------------------------
# Edits
# ---------------------------------------------------------------------------

def recolor(root: etree._Element, mapping: list[tuple[str, str]], tolerance: int = 0) -> None:
    """Map colors: each color within the tolerance of a source becomes the
    target shifted by the same offset (shading is kept)."""
    pairs = [(hex_to_rgb(a), hex_to_rgb(b)) for a, b in mapping]
    threshold = 2.0 + max(0, min(100, tolerance)) * 1.6

    def fn(rgb: RGB) -> RGB:
        best = None
        for src, dst in pairs:
            d = _dist(rgb, src)
            if d <= threshold and (best is None or d < best[0]):
                best = (d, src, dst)
        if best is None:
            return rgb
        _, src, dst = best
        return tuple(max(0, min(255, dst[k] + rgb[k] - src[k])) for k in range(3))  # type: ignore[return-value]

    map_colors(root, fn)
    if root.get("fill") is None and _style_prop(root, "fill") is None:
        mapped = fn((0, 0, 0))
        if mapped != (0, 0, 0):
            root.set("fill", to_hex(mapped))


def one_color(root: etree._Element, color: str, paper: str | None = None) -> None:
    """Every paint becomes one color and the background is removed.

    Model outputs draw inner details (counters, gaps, outlines) as shapes in
    the background color on top of other shapes. Without `paper` those shapes
    are knocked out, which keeps the file transparent but merges such details
    into the shape below. With `paper` (the color the logo will sit on) they
    are painted that color instead, which keeps every detail.
    """
    hex_to_rgb(color)
    target = color.lower()
    if paper is None:
        remove_background(root, knockout=True)
        map_colors(root, lambda rgb: rgb, replace_all=target)
    else:
        hex_to_rgb(paper)
        bg = remove_background(root, knockout=False)
        paper = paper.lower()
        if bg is not None:
            for shape, _m in list(drawn_shapes(root)):
                if resolved_paint(shape, "stroke").lower() not in ("none", "transparent"):
                    continue
                parsed = parse_color(resolved_paint(shape, "fill"))
                if parsed and _dist(parsed[0], bg) <= 6:
                    shape.set("data-paper", "1")
        map_colors(root, lambda rgb: rgb, replace_all=target)
        for shape in root.iter():
            if isinstance(shape.tag, str) and shape.get("data-paper"):
                del shape.attrib["data-paper"]
                shape.set("fill", paper)
                if shape.get("style"):
                    shape.set("style", _map_css(shape.get("style"), lambda rgb: rgb, replace_all=paper))
    root.set("fill", target)


def invert(root: etree._Element) -> None:
    """Lightness inverted (hue kept) for dark backgrounds, background removed."""
    remove_background(root, knockout=True)
    map_colors(root, invert_lightness)
    if root.get("fill") is None and _style_prop(root, "fill") is None:
        root.set("fill", "#ffffff")


def apply_operation(data: bytes, operation: str, *, mapping=None, tolerance: int = 0,
                    color: str | None = None, paper: str | None = None, remove_bg: bool = False,
                    knockout: bool = False) -> bytes:
    root = load(data)
    if operation == "recolor":
        if not mapping:
            raise LogoEditError("Pick at least one color to change")
        if remove_bg:
            remove_background(root, knockout=knockout)
        recolor(root, mapping, tolerance)
    elif operation == "mono":
        one_color(root, color or "#111111", paper)
    elif operation == "invert":
        invert(root)
    elif operation == "transparent":
        if remove_background(root, knockout=knockout) is None:
            raise LogoEditError("This logo has no solid background to remove")
    else:
        raise LogoEditError(f"Unknown operation '{operation}'")
    return finish(root)


# ---------------------------------------------------------------------------
# Embedding a logo inside another SVG
# ---------------------------------------------------------------------------

_CSS_SELECTOR_REF = re.compile(r"([.#])(-?[_a-zA-Z][\w-]*)")


def _prefix_css(css: str, prefix: str, ids: dict[str, str]) -> str:
    """Prefix class and id selectors (outside declaration blocks) and local url() refs."""
    out = []
    depth = 0
    buf = ""
    for ch in css:
        if ch == "{":
            if depth == 0:
                buf = _CSS_SELECTOR_REF.sub(
                    lambda m: m.group(1) + (ids.get(m.group(2), prefix + m.group(2))), buf)
            out.append(buf + ch)
            buf = ""
            depth += 1
        elif ch == "}":
            out.append(buf + ch)
            buf = ""
            depth = max(0, depth - 1)
        else:
            buf += ch
    out.append(buf)
    text = "".join(out)
    return _URL_REF.sub(lambda m: f"url(#{ids.get(m.group(1), m.group(1))})", text)


def prefix_ids(root: etree._Element, prefix: str) -> None:
    """Make ids and class names unique so several copies can share a document."""
    ids: dict[str, str] = {}
    for el in root.iter():
        if isinstance(el.tag, str) and el.get("id"):
            ids[el.get("id")] = prefix + el.get("id")
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if el.get("id"):
            el.set("id", ids[el.get("id")])
        if el.get("class"):
            el.set("class", " ".join(prefix + c for c in el.get("class").split()))
        for key, value in list(el.attrib.items()):
            if key in ("id", "class"):
                continue
            if key in ("href", f"{{{XLINK_NS}}}href") and value.startswith("#"):
                el.set(key, "#" + ids.get(value[1:], value[1:]))
            elif "url(" in value:
                el.set(key, _URL_REF.sub(lambda m: f"url(#{ids.get(m.group(1), m.group(1))})", value))
        if _local(el) == "style" and el.text:
            el.text = _prefix_css(el.text, prefix, ids)


_INHERITED = ("fill", "stroke", "stroke-width", "fill-rule", "opacity", "color", "style",
              "font-family", "font-size", "font-weight")


def embed(src: etree._Element, box: Box, x: float, y: float, w: float, h: float, prefix: str) -> etree._Element:
    """A nested <svg> showing `box` of `src` fitted into (x, y, w, h)."""
    copy_root = copy.deepcopy(src)
    prefix_ids(copy_root, prefix)
    nested = etree.Element(_q("svg"))
    nested.set("x", _fmt(x))
    nested.set("y", _fmt(y))
    nested.set("width", _fmt(w))
    nested.set("height", _fmt(h))
    nested.set("viewBox", " ".join(_fmt(v) for v in (box[0], box[1], box[2] - box[0], box[3] - box[1])))
    nested.set("preserveAspectRatio", "xMidYMid meet")
    nested.set("overflow", "visible")
    group = etree.SubElement(nested, _q("g"))
    for attr in _INHERITED:
        if copy_root.get(attr) is not None:
            group.set(attr, copy_root.get(attr))
    if copy_root.get("transform"):
        group.set("transform", copy_root.get("transform"))
    for child in list(copy_root):
        group.append(child)
    return nested


def _new_root(width: float, height: float, min_x: float = 0.0, min_y: float = 0.0) -> etree._Element:
    root = etree.Element(_q("svg"), nsmap={None: SVG_NS})
    root.set("viewBox", " ".join(_fmt(v) for v in (min_x, min_y, width, height)))
    root.set("width", _fmt(width))
    root.set("height", _fmt(height))
    return root


def _text(parent: etree._Element, text: str, font: str, size: float, x: float, baseline: float,
          fill: str, *, weight: int | None = None, tracking: float = 0.0, anchor: str = "start",
          max_width: float | None = None) -> logo_fonts.TextPath | None:
    """Append `text` as a filled path; returns its metrics (None for empty text)."""
    if not text:
        return None
    tp = logo_fonts.text_path(text, font, size, weight=weight, tracking=tracking)
    if max_width and tp.advance > max_width:
        size = size * max_width / tp.advance
        tp = logo_fonts.text_path(text, font, size, weight=weight, tracking=tracking)
    dx = x
    if anchor == "middle":
        dx = x - tp.advance / 2
    elif anchor == "end":
        dx = x - tp.advance
    tp = logo_fonts.text_path(text, font, size, weight=weight, tracking=tracking, x=dx, baseline=baseline)
    if tp.d:
        path = etree.SubElement(parent, _q("path"))
        path.set("d", tp.d)
        path.set("fill", fill)
    return tp


# ---------------------------------------------------------------------------
# Wordmark lockup
# ---------------------------------------------------------------------------

LOCKUP_LAYOUTS = ("horizontal", "stacked", "text")


@dataclass
class LockupSpec:
    brand_name: str
    tagline: str = ""
    font: str = logo_fonts.DEFAULT_FONT
    weight: int | None = None
    tagline_font: str | None = None
    tagline_weight: int | None = None
    layout: str = "horizontal"
    text_color: str = "#111111"
    tagline_color: str | None = None
    tracking: int = 0
    uppercase: bool = False
    remove_background: bool = True
    knockout: bool = False


def build_lockup(data: bytes | None, spec: LockupSpec) -> bytes:
    """The symbol and the brand name (set in a real font, as paths) together."""
    if spec.layout not in LOCKUP_LAYOUTS:
        raise LogoEditError(f"Unknown layout '{spec.layout}'")
    hex_to_rgb(spec.text_color)
    tag_color = spec.tagline_color or spec.text_color
    hex_to_rgb(tag_color)
    name = spec.brand_name.strip()
    tagline = spec.tagline.strip()
    if spec.uppercase:
        name, tagline = name.upper(), tagline.upper()
    if not name:
        raise LogoEditError("Enter the brand name for the wordmark")
    tag_font = spec.tagline_font or spec.font
    try:
        logo_fonts.check_text(name, spec.font, spec.weight)
        if tagline:
            logo_fonts.check_text(tagline, tag_font, spec.tagline_weight)
    except logo_fonts.FontError as exc:
        raise LogoEditError(str(exc)) from exc

    symbol = None
    box = None
    if spec.layout != "text":
        if data is None:
            raise LogoEditError("A symbol is needed for this layout")
        symbol = load(data)
        if spec.remove_background:
            remove_background(symbol, knockout=spec.knockout)
        box = content_box(symbol)
        if box is None:
            raise LogoEditError("The logo has no drawable content")

    S = 1000.0  # symbol height in output units
    family, font, w = logo_fonts.font_choice(spec.font, spec.weight)
    cap_ratio = font.cap_height / font.units_per_em
    _tf, tfont, tw = logo_fonts.font_choice(tag_font, spec.tagline_weight)
    tag_cap_ratio = tfont.cap_height / tfont.units_per_em

    if spec.layout == "horizontal":
        name_cap = 0.36 * S
    elif spec.layout == "stacked":
        name_cap = 0.24 * S
    else:
        name_cap = 0.36 * S
    name_size = name_cap / cap_ratio
    tag_size = (name_cap * 0.42) / tag_cap_ratio
    tag_tracking = 60 if not spec.uppercase else 140

    name_tp = logo_fonts.text_path(name, spec.font, name_size, weight=spec.weight, tracking=spec.tracking)
    tag_tp = (logo_fonts.text_path(tagline, tag_font, tag_size, weight=spec.tagline_weight, tracking=tag_tracking)
              if tagline else None)
    tag_cap = tag_size * tag_cap_ratio

    sym_w = 0.0
    if box is not None:
        bw, bh = box[2] - box[0], box[3] - box[1]
        sym_w = S * bw / bh if bh > 0 else S

    out = etree.Element(_q("svg"), nsmap={None: SVG_NS})
    title = etree.SubElement(out, _q("title"))
    title.text = spec.brand_name.strip()

    pieces: list[Box] = []
    text_w = max(name_tp.advance, tag_tp.advance if tag_tp else 0.0)
    gap_line = name_cap * 0.38

    if spec.layout == "horizontal":
        gap = 0.26 * S
        if box is not None:
            out.append(embed(symbol, box, 0, 0, sym_w, S, "s-"))
            pieces.append((0, 0, sym_w, S))
        block_h = name_cap + ((gap_line + tag_cap) if tag_tp else 0.0)
        top = S / 2 - block_h / 2
        x0 = (sym_w + gap) if box is not None else 0.0
        name_base = top + name_cap
        placed = _text(out, name, spec.font, name_size, x0, name_base, spec.text_color,
                       weight=spec.weight, tracking=spec.tracking)
        if placed and placed.ink:
            pieces.append(placed.ink)
        if tag_tp:
            placed = _text(out, tagline, tag_font, tag_size, x0, name_base + gap_line + tag_cap, tag_color,
                           weight=spec.tagline_weight, tracking=tag_tracking)
            if placed and placed.ink:
                pieces.append(placed.ink)
    else:
        width = max(sym_w, text_w)
        y = 0.0
        if box is not None:
            out.append(embed(symbol, box, (width - sym_w) / 2, 0, sym_w, S, "s-"))
            pieces.append(((width - sym_w) / 2, 0, (width + sym_w) / 2, S))
            y = S + 0.2 * S
        name_base = y + name_cap
        placed = _text(out, name, spec.font, name_size, width / 2, name_base, spec.text_color,
                       weight=spec.weight, tracking=spec.tracking, anchor="middle")
        if placed and placed.ink:
            pieces.append(placed.ink)
        if tag_tp:
            placed = _text(out, tagline, tag_font, tag_size, width / 2, name_base + gap_line + tag_cap,
                           tag_color, weight=spec.tagline_weight, tracking=tag_tracking, anchor="middle")
            if placed and placed.ink:
                pieces.append(placed.ink)

    bounds = None
    for piece in pieces:
        bounds = _union(bounds, piece)
    if bounds is None:
        raise LogoEditError("Nothing to draw")
    pad = 0.12 * (S if box is not None else name_cap * 2)
    min_x, min_y = bounds[0] - pad, bounds[1] - pad
    width, height = bounds[2] - bounds[0] + 2 * pad, bounds[3] - bounds[1] + 2 * pad
    out.set("viewBox", " ".join(_fmt(v) for v in (min_x, min_y, width, height)))
    scale = 2048 / max(width, height)
    out.set("width", _fmt(width * scale))
    out.set("height", _fmt(height * scale))
    return finish(out)


# ---------------------------------------------------------------------------
# Brand sheet
# ---------------------------------------------------------------------------

SHEET_W, SHEET_H = 1600, 2240
_PAPER = "#f6f5f1"
_INK = "#141414"
_MUTED = "#6f6c64"
_LINE = "#dedbd1"
_CARD = "#ffffff"
_DARK = "#141414"


def _rect(parent, x, y, w, h, fill, *, rx=0.0, stroke=None, dash=None, stroke_width=None):
    r = etree.SubElement(parent, _q("rect"))
    for k, v in (("x", x), ("y", y), ("width", w), ("height", h)):
        r.set(k, _fmt(v))
    if rx:
        r.set("rx", _fmt(rx))
    r.set("fill", fill)
    if stroke:
        r.set("stroke", stroke)
        r.set("stroke-width", _fmt(stroke_width or 2))
    if dash:
        r.set("stroke-dasharray", dash)
    return r


def _fit(box: Box, max_w: float, max_h: float) -> tuple[float, float]:
    bw, bh = box[2] - box[0], box[3] - box[1]
    s = min(max_w / bw, max_h / bh) if bw > 0 and bh > 0 else 1.0
    return bw * s, bh * s


def build_brand_sheet(data: bytes, *, brand_name: str, tagline: str = "", heading_font: str = "playfair",
                      heading_weight: int | None = None, body_font: str = "inter", body_weight: int | None = 400,
                      colors: list[str] | None = None) -> tuple[bytes, int, int]:
    """A one-page brand sheet as SVG (every label is a path, no fonts needed)."""
    original = load(data)
    pal = palette(original)
    if colors:
        for c in colors:
            hex_to_rgb(c)
        swatches = [c.lower() for c in colors][:6]
    else:
        swatches = [c["hex"] for c in pal["colors"]][:6] or ["#141414"]
    try:
        for text, font, wgt in ((brand_name, heading_font, heading_weight), (tagline, body_font, body_weight)):
            if text:
                logo_fonts.check_text(text, font, wgt)
    except logo_fonts.FontError as exc:
        raise LogoEditError(str(exc)) from exc

    clear = copy.deepcopy(original)
    remove_background(clear, knockout=False)
    box = content_box(clear)
    if box is None:
        raise LogoEditError("The logo has no drawable content")

    root = _new_root(SHEET_W, SHEET_H)
    title = etree.SubElement(root, _q("title"))
    title.text = f"{brand_name} brand sheet"
    _rect(root, 0, 0, SHEET_W, SHEET_H, _PAPER)
    M = 96.0
    inner = SHEET_W - 2 * M
    kicker_font = "spacegrotesk"

    _text(root, "BRAND GUIDELINES", kicker_font, 22, M, 128, _MUTED, weight=600, tracking=220)
    _text(root, brand_name, heading_font, 96, M, 236, _INK, weight=heading_weight, max_width=inner)
    if tagline:
        _text(root, tagline, body_font, 30, M, 292, _MUTED, weight=body_weight, max_width=inner)

    # Primary logo with its clear space.
    card_y, card_h = 340.0, 640.0
    _rect(root, M, card_y, inner, card_h, _CARD, rx=24, stroke=_LINE)
    _text(root, "Primary logo", body_font, 20, M + 32, card_y + 48, _MUTED, weight=500)
    lw, lh = _fit(box, inner * 0.56, card_h * 0.56)
    lx, ly = M + (inner - lw) / 2, card_y + (card_h - lh) / 2 + 12
    pad = 0.18 * min(lw, lh)
    _rect(root, lx - pad, ly - pad, lw + 2 * pad, lh + 2 * pad, "none", stroke="#b9b5aa", dash="10 8",
          stroke_width=2)
    root.append(embed(clear, box, lx, ly, lw, lh, "p-"))
    _text(root, "Keep the dashed margin clear", body_font, 18, M + inner - 32, card_y + card_h - 32, _MUTED,
          weight=400, anchor="end")

    # One-color variations.
    var_y, var_h = 1060.0, 300.0
    _text(root, "Variations", heading_font, 34, M, var_y - 22, _INK, weight=heading_weight)
    gap = 32.0
    cw = (inner - 2 * gap) / 3
    accent = next((c for c in swatches if 0.04 < luminance(hex_to_rgb(c)) < 0.8), swatches[0])
    on_accent = "#ffffff" if luminance(hex_to_rgb(accent)) < 0.45 else _INK
    variants = (("One color", _CARD, _INK), ("Reversed", _DARK, "#ffffff"), ("On brand color", accent, on_accent))
    for k, (label, bg, ink) in enumerate(variants):
        x = M + k * (cw + gap)
        _rect(root, x, var_y, cw, var_h, bg, rx=20, stroke=_LINE if bg == _CARD else None)
        mono = copy.deepcopy(original)
        one_color(mono, ink, bg)
        mbox = content_box(mono) or box
        vw, vh = _fit(mbox, cw * 0.62, var_h * 0.56)
        root.append(embed(mono, mbox, x + (cw - vw) / 2, var_y + (var_h - vh) / 2, vw, vh, f"v{k}-"))
        _text(root, label, body_font, 20, x, var_y + var_h + 36, _MUTED, weight=500)

    # Palette.
    pal_y = 1480.0
    _text(root, "Color palette", heading_font, 34, M, pal_y - 22, _INK, weight=heading_weight)
    n = len(swatches)
    sgap = 24.0
    sw = (inner - (n - 1) * sgap) / n
    for k, hx in enumerate(swatches):
        x = M + k * (sw + sgap)
        _rect(root, x, pal_y, sw, 180, hx, rx=16, stroke=_LINE)
        rgb = hex_to_rgb(hx)
        _text(root, hx.upper(), kicker_font, 24, x, pal_y + 222, _INK, weight=600, max_width=sw)
        _text(root, f"RGB {rgb[0]} {rgb[1]} {rgb[2]}", kicker_font, 18, x, pal_y + 254, _MUTED, weight=400,
              max_width=sw)

    # Typography.
    type_y = 1860.0
    _text(root, "Typography", heading_font, 34, M, type_y - 22, _INK, weight=heading_weight)
    hfam, _f, hw = logo_fonts.font_choice(heading_font, heading_weight)
    bfam, _f2, bw = logo_fonts.font_choice(body_font, body_weight)
    _text(root, "Aa", heading_font, 150, M, type_y + 150, _INK, weight=heading_weight)
    _text(root, f"Headings: {hfam.name} {hw}", body_font, 20, M, type_y + 200, _MUTED, weight=500)
    col = M + 360
    col_w = inner - 360
    _text(root, "The quick brown fox jumps over the lazy dog", body_font, 30, col, type_y + 46, _INK,
          weight=body_weight, max_width=col_w)
    _text(root, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", body_font, 26, col, type_y + 98, _INK, weight=body_weight,
          max_width=col_w)
    _text(root, "abcdefghijklmnopqrstuvwxyz 0123456789", body_font, 26, col, type_y + 142, _INK,
          weight=body_weight, max_width=col_w)
    _text(root, f"Body: {bfam.name} {bw}", body_font, 20, col, type_y + 200, _MUTED, weight=500)

    _text(root, "Minimum size: 24 px on screen, 10 mm in print. Use the files in this kit; do not redraw the logo.",
          body_font, 18, M, SHEET_H - 60, _MUTED, weight=400, max_width=inner)
    return finish(root, max_bytes=SHEET_MAX_BYTES), SHEET_W, SHEET_H


def font_preview(font_key: str, weight: int | None = None, text: str | None = None) -> dict:
    """Path data of a font's name in that font, for the picker."""
    family, _font, w = logo_fonts.font_choice(font_key, weight)
    tp = logo_fonts.text_path(text or family.name, family.key, 48, weight=w, baseline=48)
    ink = tp.ink or (0, 0, tp.advance, 48)
    return {"d": tp.d, "view_box": [round(ink[0], 2), round(ink[1], 2), round(ink[2] - ink[0], 2),
                                    round(ink[3] - ink[1], 2)]}
