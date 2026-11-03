"""Word-synced captions, drawn in the Pillow overlay layer.

Why Pillow rather than ASS/libass: the presets need per-word scale pops,
rounded highlight boxes and the exact stroke-under-fill look of the
story-telling subtitles; the same drawing code serves preview_frame (no
ffmpeg needed for a storyboard still); the bundled fonts are used directly
(no fontconfig lookup, which differs between servers); and Devanagari shaping
goes through raqm like every other overlay. Caption sprites are cached per
(group, active word, animation phase), so a 3 minute Short re-draws only a
few hundred small sprites.

Grouping: words_per_group (default 3 vertical, 4 square, 6 landscape),
never across a speaker change, a pause over 0.35 s or a sentence end, and
never wider than two lines at the preset size; a group never ends on a
one-letter word.

Placement fixes the story-telling bug of captions sitting under the platform
UI: in vertical frames the block stays above the bottom zone (260 px Shorts,
280 Reels, 300 TikTok at 1080 width) plus a margin, and inside the width left
by the right-side buttons (120 px), centered on the frame. Ads use the paid
placement zone (bottom 35 per cent, top 14 per cent, right 13 per cent).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional

from PIL import Image

from . import text as tx
from .colors import RGBA, parse_color, readable_on
from .draw import Shadow, box_sprite, scale_alpha
from .easing import back_out, clamp, ease
from .layout import Layout
from .overlays import Op
from .timeline import CaptionTrack, CaptionWord, Timeline

PAUSE_SPLIT = 0.35
HOLD_AFTER = 0.6  # keep the last group up this long after its last word
_SENTENCE_END = re.compile(r"[.!?\u0964\u0965]['\")\]]*$")


@dataclass
class Group:
    words: list[CaptionWord]
    start: float
    end: float


def _one_letter(text: str) -> bool:
    return sum(1 for ch in text if ch.isalnum()) == 1


def default_words_per_group(orientation: str) -> int:
    return {"vertical": 3, "square": 4}.get(orientation, 6)


def group_words(track: CaptionTrack, orientation: str, max_chars: Optional[int] = None) -> list[Group]:
    words = [w for w in track.words if w.text and w.text.strip()]
    words.sort(key=lambda w: (w.start, w.end))
    n = track.words_per_group or default_words_per_group(orientation)
    if max_chars is None:
        max_chars = {"vertical": 22, "square": 28}.get(orientation, 44)
    groups: list[list[CaptionWord]] = []
    cur: list[CaptionWord] = []
    for w in words:
        if cur:
            prev = cur[-1]
            chars = sum(len(x.text) + 1 for x in cur) + len(w.text)
            hard = (
                (w.speaker or None) != (prev.speaker or None)
                or w.start - prev.end > PAUSE_SPLIT
                or _SENTENCE_END.search(prev.text.strip()) is not None
            )
            if hard:
                groups.append(cur)
                cur = []
            elif len(cur) >= n or (chars > max_chars and len(cur) >= 1):
                # A cue never ends on a one-letter word ("a", "I"): it leads
                # into the next word, so it moves to the next group.
                carry = cur.pop() if len(cur) > 1 and _one_letter(cur[-1].text) else None
                groups.append(cur)
                cur = [carry] if carry else []
        cur.append(w)
    if cur:
        groups.append(cur)
    out: list[Group] = []
    for i, g in enumerate(groups):
        start = g[0].start
        end = max(g[-1].end, start + 0.05)
        nxt = groups[i + 1][0].start if i + 1 < len(groups) else None
        if nxt is not None:
            # Bridge short gaps so captions do not flicker between groups.
            end = nxt if nxt - end <= PAUSE_SPLIT else min(end + HOLD_AFTER * 0.5, nxt)
        else:
            end = end + HOLD_AFTER
        out.append(Group(g, start, end))
    return out


@dataclass(frozen=True)
class Preset:
    family: str
    weight: int
    color: RGBA
    uppercase: bool
    stroke: float  # fraction of the font size (outside the glyph)
    shadow: bool
    highlight_mode: str  # "color" | "box" | "none"
    pop_scale: float
    letter_spacing: float  # fraction of the font size
    line_height: float
    backdrop: bool = False  # translucent box behind the whole group
    rise: bool = True


PRESETS: dict[str, Preset] = {
    # Story-telling subtitle look: heavy face, white, black outline 0.32 x size
    # centered (0.16 outside), groups fade in over 5 frames and rise 26 px over 9.
    "bold_pop": Preset("Anton", 400, (255, 255, 255, 255), True, 0.16, True, "color", 1.12, 0.01, 1.08),
    "karaoke_box": Preset("Poppins", 800, (255, 255, 255, 255), False, 0.045, True, "box", 1.06, 0.0, 1.22),
    "minimal_lower": Preset("Inter", 600, (255, 255, 255, 255), False, 0.0, True, "none", 1.0, 0.0, 1.25, backdrop=True, rise=False),
    "serif_story": Preset("Playfair Display", 700, (255, 255, 255, 255), False, 0.035, True, "color", 1.0, 0.0, 1.2),
}


class CaptionRenderer:
    def __init__(self, track: CaptionTrack, lay: Layout, tl: Timeline):
        self.track = track
        self.L = lay
        self.fps = tl.fps
        self.preset = PRESETS.get(track.preset, PRESETS["bold_pop"])
        self.enabled = track.preset != "none" and bool(track.words)
        self.groups = group_words(track, lay.orientation) if self.enabled else []
        self.highlight = parse_color(track.highlight, (255, 209, 102, 255))
        self._blocks: dict[int, tx.Block] = {}
        self._cache: list = []
        self._starts = [g.start for g in self.groups]

    # --- layout -----------------------------------------------------------
    def _style(self, size: float) -> tx.RunStyle:
        p = self.preset
        col = parse_color(self.track.color, p.color) if self.track.color else p.color
        upper = p.uppercase if self.track.uppercase is None else self.track.uppercase
        shadow = None
        if p.shadow:
            shadow = Shadow(0, size * 0.06, size * 0.28, (0, 0, 0, 150 if p.stroke > 0.1 else 190))
        return tx.RunStyle(
            self.track.font or p.family,
            p.weight,
            size,
            col,
            p.line_height,
            p.letter_spacing * size,
            uppercase=upper,
            stroke=p.stroke * size,
            stroke_color=(0, 0, 0, 255),
            shadow=shadow,
            max_lines=self.track.max_lines,
        )

    def block(self, gi: int) -> tx.Block:
        blk = self._blocks.get(gi)
        if blk is None:
            text = " ".join(w.text.strip() for w in self.groups[gi].words)
            # Leave room for the active word's pop and the karaoke box padding.
            maxw = self.L.caption_max_width / max(1.0, self.preset.pop_scale) - (self.L.caption_size * 0.5 if self.preset.highlight_mode == "box" else 0)
            blk = tx.layout_block([tx.Run(text, self._style(self.L.caption_size))], maxw, "center")
            if len(self._blocks) > 8:
                self._blocks.clear()
            self._blocks[gi] = blk
        return blk

    def group_at(self, t: float) -> Optional[int]:
        import bisect

        i = bisect.bisect_right(self._starts, t) - 1
        if i < 0:
            return None
        g = self.groups[i]
        return i if g.start <= t < g.end else None

    def active_word(self, gi: int, t: float) -> int:
        ws = self.groups[gi].words
        act = 0
        for i, w in enumerate(ws):
            if t >= w.start - 1e-6:
                act = i
        return act

    # --- drawing ----------------------------------------------------------
    def _group_sprite(self, gi: int, active: int, pop_q: int):
        key = (gi, active, pop_q)
        for k, v in self._cache:
            if k == key:
                return v
        blk = self.block(gi)
        p = self.preset
        states: dict[int, tx.WordState] = {}
        boxes = []
        if p.highlight_mode != "none" and active < len(blk.words):
            pop_p = pop_q / 4.0
            sc = 1.0 + (p.pop_scale - 1.0) * back_out(pop_p, 1.6) if p.pop_scale > 1.0 else 1.0
            if p.highlight_mode == "color":
                states[active] = tx.WordState(scale=sc, color=self.highlight)
            else:
                size = blk.styles[0].size
                states[active] = tx.WordState(scale=sc, color=readable_on(self.highlight))
                boxes.append((active, self.highlight, size * 0.22, size * 0.22, size * 0.14))
        img, ox, oy = tx.render_block(blk, states, None, boxes)
        if p.backdrop:
            size = blk.styles[0].size
            padx, pady = size * 0.6, size * 0.32
            bw, bh = int(blk.width + 2 * padx), int(blk.height + 2 * pady)
            box, bx, by = box_sprite(bw, bh, size * 0.3, (0, 0, 0, 140))
            pad = max(ox, oy, int(padx) + 4)
            canvas = Image.new("RGBA", (bw + 2 * pad, bh + 2 * pad), (0, 0, 0, 0))
            canvas.alpha_composite(box, (pad + bx, pad + by))
            tx.composite_clipped(canvas, img, int(pad + padx - ox), int(pad + pady - oy))
            img, ox, oy = canvas, int(pad + padx), int(pad + pady)
        val = (img, ox, oy, blk)
        self._cache.append((key, val))
        if len(self._cache) > 6:
            self._cache.pop(0)
        return val

    def _position(self, blk: tx.Block) -> tuple[float, float]:
        """Top-left of the block in frame coordinates."""
        L = self.L
        x = (L.width - blk.width) / 2.0
        pos = self.track.position
        if pos == "middle":
            y = (L.height - blk.height) / 2.0
        elif pos == "upper":
            top = max(L.zone_top, L.safe_y) + (L.ipx(120) if L.orientation == "vertical" else 0)
            y = top
        else:
            y = L.height - L.caption_bottom - blk.height
        return x, y

    def ops(self, t: float) -> list[Op]:
        if not self.enabled:
            return []
        gi = self.group_at(t)
        if gi is None:
            return []
        g = self.groups[gi]
        active = self.active_word(gi, t)
        aw = g.words[active]
        f_word = (t - aw.start) * self.fps
        pop_q = int(clamp(f_word / 4.0 * 4.0, 0, 4)) if self.preset.pop_scale > 1.0 else 4
        img, ox, oy, blk = self._group_sprite(gi, active, pop_q)
        x, y = self._position(blk)
        f = (t - g.start) * self.fps
        opacity = 1.0
        dy = 0.0
        if self.preset.rise:
            opacity = clamp(f / 5.0)
            dy = (1.0 - ease("bezier_out", clamp(f / 9.0))) * self.L.px(26)
        else:
            opacity = clamp(f / 4.0)
        # Fade out at the end of the last group before a long pause.
        tail = (g.end - t) * self.fps
        if tail < 4:
            nxt = gi + 1 < len(self.groups) and abs(self.groups[gi + 1].start - g.end) < 1e-3
            if not nxt:
                opacity *= clamp(tail / 4.0)
        if opacity <= 0.003:
            return []
        sprite = scale_alpha(img, opacity)
        return [Op("sprite", sprite, int(round(x - ox)), int(round(y - oy + dy)))]

    def caption_box(self, t: float) -> Optional[tuple[int, int, int, int]]:
        """Frame-space box of the caption block at t (for tests and the UI)."""
        gi = self.group_at(t)
        if gi is None:
            return None
        blk = self.block(gi)
        x, y = self._position(blk)
        return int(x), int(y), int(math.ceil(x + blk.width)), int(math.ceil(y + blk.height))
