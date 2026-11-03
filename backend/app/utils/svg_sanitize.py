"""Make an SVG safe to store and serve.

Generated logos are SVG files. SVG is a document format: it can carry
<script>, event handler attributes, <foreignObject> with HTML, links to
javascript: URLs and references to external resources. The files are stored
public-read on the CDN and, with local storage, served same-origin under
/static, so a hostile SVG opened directly would run in the site's origin.

sanitize_svg() parses the file with a parser that never resolves entities,
loads DTDs or touches the network, then rebuilds it from an allowlist of
elements and attributes. Anything not on the list is dropped. The output is a
fresh document (no DOCTYPE, comments or processing instructions) that renders
the same as the input for ordinary vector artwork.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import etree

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_NS = "http://www.w3.org/XML/1998/namespace"

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
MAX_ELEMENTS = 200_000

# Elements kept with their children (after filtering).
ALLOWED_ELEMENTS = {
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "text", "tspan", "defs", "linearGradient", "radialGradient", "stop", "clipPath",
    "mask", "pattern", "symbol", "use", "title", "desc", "style", "marker",
    # Filters are pure paint operations. feImage is left out: it loads images.
    "filter", "feBlend", "feColorMatrix", "feComponentTransfer", "feComposite",
    "feDisplacementMap", "feDropShadow", "feFlood", "feFuncA", "feFuncB", "feFuncG",
    "feFuncR", "feGaussianBlur", "feMerge", "feMergeNode", "feMorphology", "feOffset",
    "feTurbulence",
}

# Harmless wrappers whose children are kept but which are themselves removed:
# <a> would otherwise be a clickable link, <switch> only selects among children.
UNWRAP_ELEMENTS = {"a", "switch"}

# Everything else (script, foreignObject, iframe, image, feImage, animate,
# animateMotion, animateTransform, set, metadata, editor namespaces, HTML) is
# dropped together with its subtree.

ALLOWED_ATTRIBUTES = {
    # Core and geometry
    "id", "class", "style", "transform", "viewBox", "preserveAspectRatio", "version",
    "width", "height", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "fx", "fy", "fr", "d", "points", "pathLength",
    # Painting
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity",
    "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray",
    "stroke-dashoffset", "opacity", "color", "display", "visibility", "overflow",
    "clip-path", "clip-rule", "mask", "mask-type", "vector-effect", "paint-order",
    "shape-rendering", "text-rendering", "image-rendering", "color-interpolation",
    "color-rendering", "isolation", "mix-blend-mode", "filter",
    "marker-start", "marker-mid", "marker-end",
    # Gradients, patterns, clip paths, masks, markers, symbols
    "offset", "stop-color", "stop-opacity", "gradientUnits", "gradientTransform",
    "spreadMethod", "patternUnits", "patternContentUnits", "patternTransform",
    "clipPathUnits", "maskUnits", "maskContentUnits", "markerUnits", "markerWidth",
    "markerHeight", "orient", "refX", "refY", "href",
    # Text
    "font-family", "font-size", "font-weight", "font-style", "font-variant",
    "font-stretch", "letter-spacing", "word-spacing", "text-anchor",
    "dominant-baseline", "alignment-baseline", "baseline-shift", "text-decoration",
    "writing-mode", "direction", "unicode-bidi", "dx", "dy", "rotate", "textLength",
    "lengthAdjust",
    # <style>
    "type", "media",
    # Filters
    "filterUnits", "primitiveUnits", "color-interpolation-filters", "in", "in2",
    "result", "stdDeviation", "mode", "values", "operator", "k1", "k2", "k3", "k4",
    "flood-color", "flood-opacity", "radius", "tableValues", "slope", "intercept",
    "amplitude", "exponent", "baseFrequency", "numOctaves", "seed", "stitchTiles",
    "scale", "xChannelSelector", "yChannelSelector",
}

# Attributes allowed outside the null namespace.
ALLOWED_NS_ATTRIBUTES = {
    (XLINK_NS, "href"),
    (XML_NS, "space"),
}

_LOCAL_REF = re.compile(r"^#[A-Za-z_][\w.\-:]*$")
_URL_FUNC = re.compile(r"url\s*\(", re.IGNORECASE)
_LOCAL_URL = re.compile(r"""url\(\s*(['"]?)\s*#[A-Za-z_][\w.\-:]*\s*\1\s*\)""", re.IGNORECASE)
_ANY_URL = re.compile(r"""url\(\s*(?:"[^"]*"|'[^']*'|[^)]*)\s*\)""", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x20\x7f]+")
# Blocked anywhere in an attribute value.
_SCRIPT_SCHEMES = ("javascript:", "vbscript:", "livescript:")
# Blocked at the start of a value (an id such as "metadata:1" is fine).
_URL_SCHEMES = ("data:", "http:", "https:", "file:", "ftp:", "//")
# CSS that can load resources or run code even without url().
_CSS_BLOCKLIST = ("expression", "javascript:", "vbscript:", "behavior", "-moz-binding",
                  "image-set", "cross-fade", "element(", "</")
_CSS_AT_IMPORT = re.compile(r"@(import|namespace|charset)\b[^;{}]*;?", re.IGNORECASE)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_VIEWBOX_SPLIT = re.compile(r"[\s,]+")
_LENGTH = re.compile(r"^\s*([0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*(px)?\s*$")


class SVGSanitizeError(ValueError):
    """The input is not an SVG document that can be made safe."""


@dataclass
class SanitizedSVG:
    data: bytes
    width: int | None
    height: int | None


def _parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
        remove_comments=True,
        remove_pis=True,
        recover=False,
    )


def _split_tag(tag: str) -> tuple[str | None, str]:
    if tag.startswith("{"):
        ns, _, local = tag[1:].partition("}")
        return ns, local
    return None, tag


def _normalised(value: str) -> str:
    """Lowercase with whitespace and control characters removed, the form a
    browser effectively sees when it strips them out of a URL scheme."""
    return _CONTROL.sub("", value).lower()


def sanitize_css(css: str) -> str:
    """CSS with comments, @import and every non-local url() removed.

    Returns "" when the stylesheet uses escapes or constructs that could hide or
    perform a resource load; dropping it is safer than guessing.
    """
    if not css:
        return ""
    text = _CSS_COMMENT.sub("", css)
    if "\\" in text or "&" in text:
        # CSS escapes (u\72l) and entity tricks could rebuild a blocked token.
        return ""
    lowered = _normalised(text)
    if any(token in lowered for token in _CSS_BLOCKLIST):
        return ""
    text = _CSS_AT_IMPORT.sub("", text)

    def _url(match: re.Match) -> str:
        return match.group(0) if _LOCAL_URL.fullmatch(match.group(0)) else "none"

    text = _ANY_URL.sub(_url, text)
    # An unterminated url( that the regex could not pair up.
    if len(_URL_FUNC.findall(text)) != len(_LOCAL_URL.findall(text)):
        return ""
    return text


def _clean_attribute(name: str, value: str) -> str | None:
    """The value to keep for an allowed attribute, or None to drop it."""
    norm = _normalised(value)
    if name == "href":
        return value.strip() if _LOCAL_REF.match(value.strip()) else None
    if name == "style":
        cleaned = sanitize_css(value)
        return cleaned or None
    if any(scheme in norm for scheme in _SCRIPT_SCHEMES):
        return None
    if norm.startswith(_URL_SCHEMES):
        return None
    if "url(" in norm:
        # Only same-document references such as fill="url(#gradient)".
        urls = _URL_FUNC.findall(value)
        if len(urls) != len(_LOCAL_URL.findall(value)):
            return None
    return value


def _copy_attributes(src: etree._Element, dst: etree._Element) -> None:
    for raw_name, value in src.attrib.items():
        ns, local = _split_tag(raw_name)
        if local.lower().startswith("on"):
            continue
        if ns is None:
            if local not in ALLOWED_ATTRIBUTES:
                continue
            key = local
            check_name = local
        elif (ns, local) in ALLOWED_NS_ATTRIBUTES:
            key = raw_name
            check_name = "href" if local == "href" else local
        else:
            continue
        cleaned = _clean_attribute(check_name, value)
        if cleaned is not None:
            dst.set(key, cleaned)


def _append_text(parent: etree._Element, text: str | None) -> None:
    """Append text after the last child of parent (or to its text)."""
    if not text:
        return
    if len(parent):
        last = parent[-1]
        last.tail = (last.tail or "") + text
    else:
        parent.text = (parent.text or "") + text


class _Builder:
    def __init__(self, svg_ns_for_none: bool):
        # SVG files without an xmlns are treated as SVG (browsers would not
        # render them as images otherwise, so the fix only helps).
        self.svg_ns_for_none = svg_ns_for_none
        self.count = 0

    def _is_svg(self, ns: str | None) -> bool:
        return ns == SVG_NS or (ns is None and self.svg_ns_for_none)

    def copy_children(self, src: etree._Element, dst: etree._Element) -> None:
        for child in src:
            if not isinstance(child.tag, str):
                # Comment, processing instruction or unresolved entity. Keep
                # only the text that follows it.
                _append_text(dst, child.tail)
                continue
            ns, local = _split_tag(child.tag)
            if self._is_svg(ns) and local in ALLOWED_ELEMENTS:
                self.count += 1
                if self.count > MAX_ELEMENTS:
                    raise SVGSanitizeError("SVG has too many elements")
                new = etree.SubElement(dst, f"{{{SVG_NS}}}{local}")
                _copy_attributes(child, new)
                if local == "style":
                    css = sanitize_css("".join(child.itertext()))
                    if css:
                        new.text = css
                    else:
                        dst.remove(new)
                else:
                    new.text = child.text
                    self.copy_children(child, new)
                if new.getparent() is not None:
                    new.tail = child.tail
                else:
                    _append_text(dst, child.tail)
            elif self._is_svg(ns) and local in UNWRAP_ELEMENTS:
                _append_text(dst, child.text)
                self.copy_children(child, dst)
                _append_text(dst, child.tail)
            else:
                _append_text(dst, child.tail)


def _parse_length(value: str | None) -> float | None:
    if not value:
        return None
    match = _LENGTH.match(value)
    if not match:
        return None
    number = float(match.group(1))
    return number if number > 0 else None


def svg_dimensions(root: etree._Element) -> tuple[int | None, int | None]:
    """Width and height from the viewBox, else from width/height in px."""
    view_box = root.get("viewBox")
    if view_box:
        parts = [p for p in _VIEWBOX_SPLIT.split(view_box.strip()) if p]
        if len(parts) == 4:
            try:
                w, h = float(parts[2]), float(parts[3])
                if w > 0 and h > 0:
                    return round(w), round(h)
            except ValueError:
                pass
    w = _parse_length(root.get("width"))
    h = _parse_length(root.get("height"))
    return (round(w) if w else None, round(h) if h else None)


def sanitize_svg(data: bytes, max_bytes: int = DEFAULT_MAX_BYTES) -> SanitizedSVG:
    """Parse, check and rebuild an SVG from the allowlist.

    Raises SVGSanitizeError when the bytes are not a well-formed SVG document.
    """
    if not data:
        raise SVGSanitizeError("Empty SVG")
    if len(data) > max_bytes:
        raise SVGSanitizeError(f"SVG is larger than {max_bytes} bytes")
    try:
        root = etree.fromstring(data, parser=_parser())
    except etree.XMLSyntaxError as exc:
        raise SVGSanitizeError(f"Not well-formed XML: {exc}") from exc
    if root is None or not isinstance(root.tag, str):
        raise SVGSanitizeError("No root element")

    ns, local = _split_tag(root.tag)
    if local != "svg" or ns not in (SVG_NS, None):
        raise SVGSanitizeError("Root element is not <svg>")

    out = etree.Element(f"{{{SVG_NS}}}svg", nsmap={None: SVG_NS, "xlink": XLINK_NS})
    _copy_attributes(root, out)
    out.text = root.text
    _Builder(svg_ns_for_none=ns is None).copy_children(root, out)

    # Drop the xlink declaration again when nothing uses it.
    etree.cleanup_namespaces(out)

    width, height = svg_dimensions(out)
    body = etree.tostring(out, xml_declaration=True, encoding="UTF-8")
    return SanitizedSVG(data=body, width=width, height=height)

