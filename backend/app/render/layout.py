"""Frame layout rules ported from the story-telling project.

Everything scales off a 1080 px wide baseline (``scale = width / 1080``):
key text stays 80 px from the sides and 100 px from top and bottom, headline
84, subline 44, eyebrow 28, stat value 72 and label 22, outro 96.

Fix over the original: vertical captions sat 100 px from the bottom, under the
Shorts, TikTok and Reels UI. Captions now keep the platform zones clear
(vertical: bottom 260 px and right 120 px at 1080 width, more on TikTok and
Reels), and the title card region is derived from the caption position.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .timeline import Timeline

BASELINE_WIDTH = 1080.0

# Platform UI zones in baseline px for a vertical 1080 wide frame:
# (top, bottom, right). Captions and bottom-anchored overlays stay clear.
PLATFORM_ZONES: dict[str, tuple[float, float, float]] = {
    "shorts": (160.0, 260.0, 120.0),
    "tiktok": (160.0, 300.0, 130.0),
    "reels": (200.0, 280.0, 120.0),
    "youtube": (0.0, 0.0, 0.0),
}
# Vertical ad delivery safe zone as fractions of the frame (top and bottom of
# the height, right of the width; the left 6 per cent is inside safe_x).
ADS_ZONE: tuple[float, float, float] = (0.14, 0.35, 0.13)

# Caption font size per preset in baseline px: (vertical, square, landscape).
# Landscape uses smaller baseline numbers because width/1080 is 1.78 there.
CAPTION_SIZES: dict[str, tuple[float, float, float]] = {
    "bold_pop": (84.0, 74.0, 46.0),
    "karaoke_box": (66.0, 58.0, 38.0),
    "minimal_lower": (46.0, 42.0, 28.0),
    "serif_story": (62.0, 56.0, 36.0),
    "none": (52.0, 52.0, 30.0),
}


@dataclass
class Layout:
    width: int
    height: int
    fps: int
    scale: float
    orientation: str  # vertical | square | landscape
    safe_x: int
    safe_y: int
    title_size: int
    subline_size: int
    eyebrow_size: int
    stat_value_size: int
    stat_label_size: int
    outro_size: int
    zone_top: int
    zone_bottom: int
    zone_right: int
    platform: str
    caption_preset: str
    caption_size: int
    caption_bottom: int  # distance from the frame bottom to the caption block bottom
    caption_max_width: int
    accent: str
    display_font: str
    text_font: str
    background: str
    has_captions: bool = False
    extra: dict = field(default_factory=dict)

    def px(self, baseline: float) -> float:
        return baseline * self.scale

    def ipx(self, baseline: float) -> int:
        return int(round(baseline * self.scale))

    def usable(self, safe_area: bool = True) -> tuple[int, int, int, int]:
        """(left, top, right, bottom) of the area overlays are placed in."""
        if not safe_area:
            return (0, 0, self.width, self.height)
        left = self.safe_x
        right = self.width - max(self.safe_x, self.zone_right + self.ipx(16) if self.zone_right else 0)
        top = max(self.safe_y, self.zone_top)
        bottom = self.height - max(self.safe_y, self.zone_bottom + self.ipx(40) if self.zone_bottom else 0)
        return (left, top, right, bottom)

    @property
    def caption_top_estimate(self) -> int:
        """Top of a two line caption block, used to keep cards clear of it."""
        return int(self.height - self.caption_bottom - self.caption_size * 2.3)

    @property
    def title_pad_bottom(self) -> int:
        """Bottom padding of the title card region (story formula:
        subtitleBottom + subtitleSize * 3.2, with the fixed caption bottom)."""
        return int(self.caption_bottom + self.caption_size * 3.2)


def build_layout(tl: Timeline) -> Layout:
    w, h = tl.width, tl.height
    s = w / BASELINE_WIDTH
    orient = tl.orientation
    cap = tl.captions
    has_caps = bool(cap and cap.preset != "none" and cap.words)
    platform = cap.platform_safe_zone if cap else ("youtube" if orient == "landscape" else "shorts")
    if orient == "landscape":
        zt = zb = zr = 0
        platform_eff = "youtube"
    elif platform == "ads":
        # Paid placements stack the CTA button, captions and the advertiser
        # line low in the frame: fractions of the frame, not fixed pixels.
        platform_eff = "ads"
        t0, b0, r0 = ADS_ZONE
        if orient == "square":
            t0, b0, r0 = t0 * 0.5, b0 * 0.45, r0 * 0.6
        zt, zb, zr = int(round(t0 * h)), int(round(b0 * h)), int(round(r0 * w))
    else:
        platform_eff = platform if platform != "youtube" else ("shorts" if orient == "vertical" else "youtube")
        t0, b0, r0 = PLATFORM_ZONES[platform_eff]
        if orient == "square":
            # Square posts get feed UI, not the full Shorts overlay.
            t0, b0, r0 = t0 * 0.5, b0 * 0.45, r0 * 0.6
        zt, zb, zr = int(round(t0 * s)), int(round(b0 * s)), int(round(r0 * s))

    preset = cap.preset if cap else "bold_pop"
    sizes = CAPTION_SIZES.get(preset, CAPTION_SIZES["bold_pop"])
    idx = {"vertical": 0, "square": 1, "landscape": 2}[orient]
    cap_size = cap.size if (cap and cap.size) else sizes[idx]
    cap_px = int(round(cap_size * s))

    if orient == "vertical":
        cap_bottom = zb + int(round(70 * s))
        side = max(zr + int(round(20 * s)), int(round(80 * s)))
        cap_max_w = w - 2 * side
    elif orient == "square":
        cap_bottom = max(zb + int(round(40 * s)), int(round(110 * s)))
        side = max(zr + int(round(20 * s)), int(round(80 * s)))
        cap_max_w = w - 2 * side
    else:
        cap_bottom = int(round(h * 0.085))
        cap_max_w = int(w * 0.72)

    return Layout(
        width=w,
        height=h,
        fps=tl.fps,
        scale=s,
        orientation=orient,
        safe_x=max(int(round(80 * s)), int(round(0.06 * w)) if platform_eff == "ads" else 0),
        safe_y=int(round(100 * s)),
        title_size=int(round(84 * s)),
        subline_size=int(round(44 * s)),
        eyebrow_size=int(round(28 * s)),
        stat_value_size=int(round(72 * s)),
        stat_label_size=int(round(22 * s)),
        outro_size=int(round(96 * s)),
        zone_top=zt,
        zone_bottom=zb,
        zone_right=zr,
        platform=platform_eff,
        caption_preset=preset,
        caption_size=cap_px,
        caption_bottom=cap_bottom,
        caption_max_width=cap_max_w,
        accent=tl.accent,
        display_font=tl.display_font,
        text_font=tl.text_font,
        background=tl.background,
        has_captions=has_caps,
    )
