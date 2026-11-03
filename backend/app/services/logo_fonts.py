"""Text to SVG path outlines for logo wordmarks and brand sheets.

AI logo models often misspell brand names. The logo studio renders the name
itself instead: each glyph outline is read from a bundled OFL font (the
families in app/render/fonts) and written as SVG path data, so the result is
exact, scales like the rest of the logo and needs no font on the viewer's
machine.

This is a small TrueType reader (no fontTools in the stack): cmap formats 4
and 12, glyf simple and composite glyphs, hmtx advances, gvar variations for
the variable families (so any weight on the axis works), avar, and pair
kerning from the GPOS kern feature. There is no text shaping, so scripts that
need it (Devanagari, Arabic, Hebrew, Thai and other complex scripts) are
refused rather than rendered wrongly; Latin, Greek and Cyrillic are fine.
"""

from __future__ import annotations

import os
import struct
import threading
from dataclasses import dataclass
from functools import lru_cache

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "render", "fonts")


@dataclass(frozen=True)
class LogoFont:
    key: str
    name: str
    category: str
    # weight -> file for static families; a single variable file otherwise.
    files: tuple[tuple[int, str], ...]
    variable: bool
    wmin: int
    wmax: int
    default_weight: int


# Families offered for wordmarks, with the role they suit.
LOGO_FONTS: dict[str, LogoFont] = {
    f.key: f
    for f in (
        LogoFont("poppins", "Poppins", "Geometric sans",
                 ((500, "poppins/Poppins-Medium.ttf"), (600, "poppins/Poppins-SemiBold.ttf"),
                  (700, "poppins/Poppins-Bold.ttf"), (800, "poppins/Poppins-ExtraBold.ttf")),
                 False, 500, 800, 600),
        LogoFont("inter", "Inter", "Neutral sans", ((400, "inter/Inter-Variable.ttf"),), True, 100, 900, 600),
        LogoFont("spacegrotesk", "Space Grotesk", "Technical sans",
                 ((400, "spacegrotesk/SpaceGrotesk-Variable.ttf"),), True, 300, 700, 600),
        LogoFont("bricolage", "Bricolage Grotesque", "Expressive grotesque",
                 ((400, "bricolage/BricolageGrotesque-Variable.ttf"),), True, 200, 800, 700),
        LogoFont("playfair", "Playfair Display", "High-contrast serif",
                 ((400, "playfair/PlayfairDisplay-Variable.ttf"),), True, 400, 900, 600),
        LogoFont("anton", "Anton", "Condensed display", ((400, "anton/Anton-Regular.ttf"),), False, 400, 400, 400),
        LogoFont("bebas", "Bebas Neue", "Condensed capitals", ((400, "bebas/BebasNeue-Regular.ttf"),),
                 False, 400, 400, 400),
    )
}

DEFAULT_FONT = "poppins"

# Scripts that need shaping, which this renderer does not do.
_COMPLEX_RANGES = (
    (0x0590, 0x08FF),  # Hebrew, Arabic, Syriac, Thaana, NKo and friends
    (0x0900, 0x0DFF),  # Indic scripts
    (0x0E00, 0x0FFF),  # Thai, Lao, Tibetan
    (0x1000, 0x109F),  # Myanmar
    (0x1780, 0x17FF),  # Khmer
    (0xFB1D, 0xFDFF),  # Hebrew and Arabic presentation forms
    (0xFE70, 0xFEFF),
)


class FontError(ValueError):
    """The text cannot be set in the requested font."""


def _complex_script(text: str) -> bool:
    for ch in text:
        cp = ord(ch)
        for lo, hi in _COMPLEX_RANGES:
            if lo <= cp <= hi:
                return True
    return False


def _f2dot14(raw: int) -> float:
    if raw >= 0x8000:
        raw -= 0x10000
    return raw / 16384.0


class TrueTypeFont:
    """Glyph outlines, advances and kerning of one TrueType (glyf) font file."""

    def __init__(self, path: str):
        with open(path, "rb") as fh:
            self.data = data = fh.read()
        num_tables = struct.unpack_from(">H", data, 4)[0]
        self.tables: dict[str, tuple[int, int]] = {}
        for i in range(num_tables):
            tag, _checksum, offset, length = struct.unpack_from(">4sIII", data, 12 + 16 * i)
            self.tables[tag.decode("latin-1")] = (offset, length)
        if "glyf" not in self.tables or "loca" not in self.tables:
            raise FontError("Only TrueType outline fonts are supported")

        head = self.tables["head"][0]
        self.units_per_em = struct.unpack_from(">H", data, head + 18)[0]
        self.loca_long = struct.unpack_from(">h", data, head + 50)[0] == 1
        self.num_glyphs = struct.unpack_from(">H", data, self.tables["maxp"][0] + 4)[0]
        hhea = self.tables["hhea"][0]
        self.ascender, self.descender = struct.unpack_from(">hh", data, hhea + 4)
        self.num_hmetrics = struct.unpack_from(">H", data, hhea + 34)[0]
        self.cap_height = self._os2_cap_height()

        self._cmap = self._read_cmap()
        self._kern_cache: dict[tuple[int, int], int] | None = None
        self._kern_lock = threading.Lock()

        # Variations
        self.axes: list[tuple[str, float, float, float]] = []
        self._avar: list[list[tuple[float, float]]] = []
        if "fvar" in self.tables and "gvar" in self.tables:
            self._read_fvar()
            self._read_avar()
            self._read_gvar_header()

    # -- tables ---------------------------------------------------------------

    def _os2_cap_height(self) -> int:
        if "OS/2" in self.tables:
            off, length = self.tables["OS/2"]
            version = struct.unpack_from(">H", self.data, off)[0]
            if version >= 2 and length >= 90:
                cap = struct.unpack_from(">h", self.data, off + 88)[0]
                if cap > 0:
                    return cap
        return int(self.units_per_em * 0.7)

    def _read_cmap(self) -> dict[int, int]:
        data = self.data
        base = self.tables["cmap"][0]
        count = struct.unpack_from(">H", data, base + 2)[0]
        best = None
        for i in range(count):
            platform, encoding, offset = struct.unpack_from(">HHI", data, base + 4 + 8 * i)
            fmt = struct.unpack_from(">H", data, base + offset)[0]
            rank = None
            if fmt == 12 and platform in (0, 3):
                rank = 0
            elif fmt == 4 and (platform == 0 or (platform == 3 and encoding in (1, 10))):
                rank = 1
            if rank is not None and (best is None or rank < best[0]):
                best = (rank, base + offset, fmt)
        mapping: dict[int, int] = {}
        if best is None:
            return mapping
        _, sub, fmt = best
        if fmt == 12:
            groups = struct.unpack_from(">I", data, sub + 12)[0]
            for g in range(groups):
                start, end, glyph = struct.unpack_from(">III", data, sub + 16 + 12 * g)
                for cp in range(start, min(end, start + 0x10000) + 1):
                    mapping[cp] = glyph + (cp - start)
            return mapping
        seg_x2 = struct.unpack_from(">H", data, sub + 6)[0]
        segs = seg_x2 // 2
        ends = sub + 14
        starts = ends + seg_x2 + 2
        deltas = starts + seg_x2
        ranges = deltas + seg_x2
        for s in range(segs):
            end = struct.unpack_from(">H", data, ends + 2 * s)[0]
            start = struct.unpack_from(">H", data, starts + 2 * s)[0]
            delta = struct.unpack_from(">h", data, deltas + 2 * s)[0]
            range_offset = struct.unpack_from(">H", data, ranges + 2 * s)[0]
            if start == 0xFFFF:
                continue
            for cp in range(start, end + 1):
                if range_offset == 0:
                    glyph = (cp + delta) & 0xFFFF
                else:
                    addr = ranges + 2 * s + range_offset + 2 * (cp - start)
                    glyph = struct.unpack_from(">H", data, addr)[0]
                    if glyph:
                        glyph = (glyph + delta) & 0xFFFF
                if glyph:
                    mapping[cp] = glyph
        return mapping

    def glyph_id(self, char: str) -> int:
        return self._cmap.get(ord(char), 0)

    def advance(self, glyph: int) -> int:
        hmtx = self.tables["hmtx"][0]
        index = min(glyph, self.num_hmetrics - 1)
        return struct.unpack_from(">H", self.data, hmtx + 4 * index)[0]

    def _lsb(self, glyph: int) -> int:
        hmtx = self.tables["hmtx"][0]
        if glyph < self.num_hmetrics:
            return struct.unpack_from(">h", self.data, hmtx + 4 * glyph + 2)[0]
        return struct.unpack_from(">h", self.data, hmtx + 4 * self.num_hmetrics + 2 * (glyph - self.num_hmetrics))[0]

    def _glyph_range(self, glyph: int) -> tuple[int, int]:
        loca = self.tables["loca"][0]
        if self.loca_long:
            start, end = struct.unpack_from(">II", self.data, loca + 4 * glyph)
        else:
            start, end = struct.unpack_from(">HH", self.data, loca + 2 * glyph)
            start, end = start * 2, end * 2
        return start, end

    # -- variations -----------------------------------------------------------

    def _read_fvar(self) -> None:
        off = self.tables["fvar"][0]
        axes_offset, _reserved, axis_count, axis_size = struct.unpack_from(">HHHH", self.data, off + 4)
        for i in range(axis_count):
            tag, lo, default, hi = struct.unpack_from(">4siii", self.data, off + axes_offset + i * axis_size)
            self.axes.append((tag.decode("latin-1"), lo / 65536.0, default / 65536.0, hi / 65536.0))

    def _read_avar(self) -> None:
        if "avar" not in self.tables:
            return
        off = self.tables["avar"][0]
        axis_count = struct.unpack_from(">H", self.data, off + 6)[0]
        pos = off + 8
        for _ in range(axis_count):
            n = struct.unpack_from(">H", self.data, pos)[0]
            pos += 2
            pairs = []
            for _ in range(n):
                a, b = struct.unpack_from(">HH", self.data, pos)
                pairs.append((_f2dot14(a), _f2dot14(b)))
                pos += 4
            self._avar.append(pairs)

    def _read_gvar_header(self) -> None:
        off = self.tables["gvar"][0]
        (_maj, _min, self._gv_axis_count, shared_count, shared_offset, glyph_count, flags,
         array_offset) = struct.unpack_from(">HHHHIHHI", self.data, off)
        self._gv_base = off
        self._gv_array = off + array_offset
        self._gv_long = bool(flags & 1)
        self._gv_count = glyph_count
        self._gv_shared = []
        for i in range(shared_count):
            coords = struct.unpack_from(">" + "H" * self._gv_axis_count, self.data,
                                        off + shared_offset + i * 2 * self._gv_axis_count)
            self._gv_shared.append([_f2dot14(c) for c in coords])

    def normalized_location(self, weight: float | None) -> list[float] | None:
        """Normalized coordinates for a weight (other axes at their default)."""
        if not self.axes:
            return None
        coords = []
        for i, (tag, lo, default, hi) in enumerate(self.axes):
            value = default
            if tag == "wght" and weight is not None:
                value = max(lo, min(hi, float(weight)))
            if value < default:
                norm = -(default - value) / (default - lo) if default > lo else 0.0
            elif value > default:
                norm = (value - default) / (hi - default) if hi > default else 0.0
            else:
                norm = 0.0
            if i < len(self._avar) and self._avar[i]:
                norm = self._apply_avar(self._avar[i], norm)
            coords.append(norm)
        if all(c == 0 for c in coords):
            return None
        return coords

    @staticmethod
    def _apply_avar(pairs: list[tuple[float, float]], value: float) -> float:
        for k in range(1, len(pairs)):
            a0, b0 = pairs[k - 1]
            a1, b1 = pairs[k]
            if a0 <= value <= a1:
                if a1 == a0:
                    return b0
                return b0 + (value - a0) * (b1 - b0) / (a1 - a0)
        return value

    @staticmethod
    def _tuple_scalar(coords: list[float], peak: list[float],
                      start: list[float] | None, end: list[float] | None) -> float:
        scalar = 1.0
        for i, p in enumerate(peak):
            c = coords[i] if i < len(coords) else 0.0
            if p == 0:
                continue
            if c == p:
                continue
            if start is not None and end is not None:
                s, e = start[i], end[i]
                if s > p or p > e or (s < 0 < e):
                    continue
                if c < s or c > e:
                    return 0.0
                if c < p:
                    scalar *= (c - s) / (p - s) if p != s else 1.0
                else:
                    scalar *= (e - c) / (e - p) if e != p else 1.0
            else:
                if c == 0 or c < min(0, p) or c > max(0, p):
                    return 0.0
                scalar *= c / p
        return scalar

    def _read_points(self, pos: int) -> tuple[list[int] | None, int]:
        """Packed point numbers. None means every point."""
        data = self.data
        count = data[pos]
        pos += 1
        if count == 0:
            return None, pos
        if count & 0x80:
            count = ((count & 0x7F) << 8) | data[pos]
            pos += 1
        points = []
        last = 0
        while len(points) < count:
            control = data[pos]
            pos += 1
            run = (control & 0x7F) + 1
            words = bool(control & 0x80)
            for _ in range(run):
                if words:
                    step = struct.unpack_from(">H", data, pos)[0]
                    pos += 2
                else:
                    step = data[pos]
                    pos += 1
                last += step
                points.append(last)
        return points[:count], pos

    def _read_deltas(self, pos: int, count: int) -> tuple[list[int], int]:
        data = self.data
        out: list[int] = []
        while len(out) < count:
            control = data[pos]
            pos += 1
            run = (control & 0x3F) + 1
            if control & 0x80:
                out.extend([0] * run)
            elif control & 0x40:
                out.extend(struct.unpack_from(">" + "h" * run, data, pos))
                pos += 2 * run
            else:
                out.extend(struct.unpack_from(">" + "b" * run, data, pos))
                pos += run
        return out[:count], pos

    def _glyph_deltas(self, glyph: int, num_points: int, coords: list[float]
                      ) -> list[tuple[float, float, list[int] | None]]:
        """Scaled tuple deltas for a glyph: list of (scalar, dx list, dy list, points)."""
        if glyph >= self._gv_count:
            return []
        data = self.data
        if self._gv_long:
            start, end = struct.unpack_from(">II", data, self._gv_base + 20 + 4 * glyph)
        else:
            start, end = struct.unpack_from(">HH", data, self._gv_base + 20 + 2 * glyph)
            start, end = start * 2, end * 2
        if start == end:
            return []
        base = self._gv_array + start
        tuple_count, data_offset = struct.unpack_from(">HH", data, base)
        shared_points_flag = bool(tuple_count & 0x8000)
        tuple_count &= 0x0FFF
        header = base + 4
        serialized = base + data_offset
        shared_points = None
        if shared_points_flag:
            shared_points, serialized = self._read_points(serialized)
        total = num_points + 4
        results = []
        axis_count = self._gv_axis_count
        for _ in range(tuple_count):
            size, index = struct.unpack_from(">HH", data, header)
            header += 4
            if index & 0x8000:
                peak = [_f2dot14(v) for v in struct.unpack_from(">" + "H" * axis_count, data, header)]
                header += 2 * axis_count
            else:
                peak = self._gv_shared[index & 0x0FFF]
            start_t = end_t = None
            if index & 0x4000:
                start_t = [_f2dot14(v) for v in struct.unpack_from(">" + "H" * axis_count, data, header)]
                header += 2 * axis_count
                end_t = [_f2dot14(v) for v in struct.unpack_from(">" + "H" * axis_count, data, header)]
                header += 2 * axis_count
            chunk_end = serialized + size
            scalar = self._tuple_scalar(coords, peak, start_t, end_t)
            if scalar == 0:
                serialized = chunk_end
                continue
            pos = serialized
            if index & 0x2000:
                points, pos = self._read_points(pos)
            else:
                points = shared_points
            n = total if points is None else len(points)
            xs, pos = self._read_deltas(pos, n)
            ys, pos = self._read_deltas(pos, n)
            results.append((scalar, xs, ys, points))
            serialized = chunk_end
        return results

    @staticmethod
    def _iup(deltas: list[list[float]], touched: list[bool], orig: list[tuple[float, float]],
             ends: list[int]) -> None:
        """Interpolate untouched points of each contour (gvar IUP)."""
        start = 0
        for end in ends:
            idx = list(range(start, end + 1))
            refs = [i for i in idx if touched[i]]
            if not refs:
                start = end + 1
                continue
            if len(refs) == len(idx):
                start = end + 1
                continue
            if len(refs) == 1:
                r = refs[0]
                for i in idx:
                    if not touched[i]:
                        deltas[i][0] = deltas[r][0]
                        deltas[i][1] = deltas[r][1]
                start = end + 1
                continue
            n = len(idx)
            pos_of = {p: k for k, p in enumerate(idx)}
            for k, r in enumerate(refs):
                nxt = refs[(k + 1) % len(refs)]
                a = pos_of[r]
                b = pos_of[nxt]
                j = (a + 1) % n
                while j != b:
                    i = idx[j]
                    for axis in (0, 1):
                        o1, o2 = orig[r][axis], orig[nxt][axis]
                        d1, d2 = deltas[r][axis], deltas[nxt][axis]
                        oi = orig[i][axis]
                        if o1 == o2:
                            deltas[i][axis] = d1 if d1 == d2 else 0.0
                        else:
                            lo_o, hi_o, lo_d, hi_d = (o1, o2, d1, d2) if o1 < o2 else (o2, o1, d2, d1)
                            if oi <= lo_o:
                                deltas[i][axis] = lo_d
                            elif oi >= hi_o:
                                deltas[i][axis] = hi_d
                            else:
                                t = (oi - lo_o) / (hi_o - lo_o)
                                deltas[i][axis] = lo_d + t * (hi_d - lo_d)
                    j = (j + 1) % n
            start = end + 1

    def _apply_variations(self, glyph: int, points: list[tuple[float, float]], ends: list[int],
                          coords: list[float] | None, advance: float, xmin: float
                          ) -> tuple[list[tuple[float, float]], float]:
        if not coords or not hasattr(self, "_gv_array"):
            return points, advance
        n = len(points)
        lsb = self._lsb(glyph)
        phantom = [(xmin - lsb, 0.0), (xmin - lsb + advance, 0.0), (0.0, 0.0), (0.0, 0.0)]
        allpts = list(points) + phantom
        total = [[0.0, 0.0] for _ in allpts]
        for scalar, xs, ys, pts in self._glyph_deltas(glyph, n, coords):
            if pts is None:
                for i in range(min(len(allpts), len(xs))):
                    total[i][0] += xs[i] * scalar
                    total[i][1] += ys[i] * scalar
                continue
            deltas = [[0.0, 0.0] for _ in allpts]
            touched = [False] * len(allpts)
            for k, p in enumerate(pts):
                if p < len(allpts):
                    deltas[p][0] = xs[k]
                    deltas[p][1] = ys[k]
                    touched[p] = True
            if n and ends:
                self._iup(deltas, touched, allpts, ends)
            for i in range(len(allpts)):
                total[i][0] += deltas[i][0] * scalar
                total[i][1] += deltas[i][1] * scalar
        moved = [(x + total[i][0], y + total[i][1]) for i, (x, y) in enumerate(points)]
        new_advance = advance + (total[n + 1][0] - total[n][0])
        return moved, new_advance

    # -- outlines -------------------------------------------------------------

    def glyph_contours(self, glyph: int, coords: list[float] | None, depth: int = 0
                       ) -> tuple[list[list[tuple[float, float, bool]]], float]:
        """Contours as lists of (x, y, on_curve) in font units, and the advance."""
        advance = float(self.advance(glyph))
        if depth > 8:
            return [], advance
        start, end = self._glyph_range(glyph)
        if start == end:
            if coords:
                _, advance = self._apply_variations(glyph, [], [], coords, advance, 0.0)
            return [], advance
        data = self.data
        base = self.tables["glyf"][0] + start
        n_contours, xmin = struct.unpack_from(">hh", data, base)
        pos = base + 10
        if n_contours >= 0:
            ends = list(struct.unpack_from(">" + "H" * n_contours, data, pos))
            pos += 2 * n_contours
            n_points = ends[-1] + 1 if ends else 0
            instr_len = struct.unpack_from(">H", data, pos)[0]
            pos += 2 + instr_len
            flags = []
            while len(flags) < n_points:
                flag = data[pos]
                pos += 1
                flags.append(flag)
                if flag & 8:
                    repeat = data[pos]
                    pos += 1
                    flags.extend([flag] * repeat)
            flags = flags[:n_points]
            xs = []
            value = 0
            for flag in flags:
                if flag & 2:
                    d = data[pos]
                    pos += 1
                    value += d if flag & 16 else -d
                elif not flag & 16:
                    value += struct.unpack_from(">h", data, pos)[0]
                    pos += 2
                xs.append(value)
            ys = []
            value = 0
            for flag in flags:
                if flag & 4:
                    d = data[pos]
                    pos += 1
                    value += d if flag & 32 else -d
                elif not flag & 32:
                    value += struct.unpack_from(">h", data, pos)[0]
                    pos += 2
                ys.append(value)
            points = [(float(x), float(y)) for x, y in zip(xs, ys)]
            points, advance = self._apply_variations(glyph, points, ends, coords, advance, float(xmin))
            contours = []
            first = 0
            for e in ends:
                contours.append([(points[i][0], points[i][1], bool(flags[i] & 1)) for i in range(first, e + 1)])
                first = e + 1
            return contours, advance

        # Composite glyph
        components = []
        more = True
        while more:
            cflags, sub = struct.unpack_from(">HH", data, pos)
            pos += 4
            if cflags & 1:
                a1, a2 = struct.unpack_from(">hh", data, pos)
                pos += 4
            else:
                a1, a2 = struct.unpack_from(">bb", data, pos)
                pos += 2
            xx, xy, yx, yy = 1.0, 0.0, 0.0, 1.0
            if cflags & 8:
                xx = yy = _f2dot14(struct.unpack_from(">H", data, pos)[0])
                pos += 2
            elif cflags & 0x40:
                xx, yy = (_f2dot14(v) for v in struct.unpack_from(">HH", data, pos))
                pos += 4
            elif cflags & 0x80:
                xx, xy, yx, yy = (_f2dot14(v) for v in struct.unpack_from(">HHHH", data, pos))
                pos += 8
            dx, dy = (float(a1), float(a2)) if cflags & 2 else (0.0, 0.0)
            components.append([sub, dx, dy, xx, xy, yx, yy, bool(cflags & 0x200)])
            more = bool(cflags & 0x20)
        if coords:
            offsets = [(c[1], c[2]) for c in components]
            moved, advance = self._apply_variations(glyph, offsets, [], coords, advance, float(xmin))
            for c, (mx, my) in zip(components, moved):
                c[1], c[2] = mx, my
        out = []
        for sub, dx, dy, xx, xy, yx, yy, use_metrics in components:
            sub_contours, sub_adv = self.glyph_contours(sub, coords, depth + 1)
            if use_metrics:
                advance = sub_adv
            for contour in sub_contours:
                out.append([(x * xx + y * yx + dx, x * xy + y * yy + dy, on) for x, y, on in contour])
        return out, advance

    # -- kerning --------------------------------------------------------------

    def kerning(self, left: int, right: int) -> int:
        if self._kern_cache is None:
            with self._kern_lock:
                if self._kern_cache is None:
                    try:
                        self._kern_cache = self._read_gpos_kern()
                    except (struct.error, IndexError):
                        self._kern_cache = {}
        return self._kern_cache.get((left, right), 0)

    def _coverage(self, off: int) -> list[int]:
        data = self.data
        fmt, count = struct.unpack_from(">HH", data, off)
        if fmt == 1:
            return list(struct.unpack_from(">" + "H" * count, data, off + 4))
        glyphs = []
        for r in range(count):
            start, end, _ = struct.unpack_from(">HHH", data, off + 4 + 6 * r)
            glyphs.extend(range(start, end + 1))
        return glyphs

    def _class_def(self, off: int) -> dict[int, int]:
        data = self.data
        fmt = struct.unpack_from(">H", data, off)[0]
        out: dict[int, int] = {}
        if fmt == 1:
            start, count = struct.unpack_from(">HH", data, off + 2)
            for i, cls in enumerate(struct.unpack_from(">" + "H" * count, data, off + 6)):
                out[start + i] = cls
        elif fmt == 2:
            count = struct.unpack_from(">H", data, off + 2)[0]
            for r in range(count):
                start, end, cls = struct.unpack_from(">HHH", data, off + 4 + 6 * r)
                for g in range(start, end + 1):
                    out[g] = cls
        return out

    @staticmethod
    def _value_size(fmt: int) -> int:
        return 2 * bin(fmt & 0xFF).count("1")

    def _x_advance(self, off: int, fmt: int) -> int:
        """XAdvance from a ValueRecord (0 when the format has none)."""
        if not fmt & 4:
            return 0
        skip = 2 * bin(fmt & 3).count("1")
        return struct.unpack_from(">h", self.data, off + skip)[0]

    def _read_gpos_kern(self) -> dict[tuple[int, int], int]:
        if "GPOS" not in self.tables:
            return {}
        data = self.data
        gpos = self.tables["GPOS"][0]
        _maj, _min, _script, feature_list, lookup_list = struct.unpack_from(">HHHHH", data, gpos)
        fl = gpos + feature_list
        lookups: set[int] = set()
        for i in range(struct.unpack_from(">H", data, fl)[0]):
            tag, foff = struct.unpack_from(">4sH", data, fl + 2 + 6 * i)
            if tag != b"kern":
                continue
            feat = fl + foff
            count = struct.unpack_from(">H", data, feat + 2)[0]
            lookups.update(struct.unpack_from(">" + "H" * count, data, feat + 4))
        ll = gpos + lookup_list
        pairs: dict[tuple[int, int], int] = {}
        for li in sorted(lookups):
            lookup = ll + struct.unpack_from(">H", data, ll + 2 + 2 * li)[0]
            ltype, _flag, sub_count = struct.unpack_from(">HHH", data, lookup)
            for s in range(sub_count):
                sub = lookup + struct.unpack_from(">H", data, lookup + 6 + 2 * s)[0]
                stype = ltype
                if ltype == 9:
                    stype, ext = struct.unpack_from(">HI", data, sub + 2)
                    sub = sub + ext
                if stype != 2:
                    continue
                self._read_pair_pos(sub, pairs)
        return pairs

    def _read_pair_pos(self, sub: int, pairs: dict[tuple[int, int], int]) -> None:
        data = self.data
        fmt, cov_off, vf1, vf2 = struct.unpack_from(">HHHH", data, sub)
        coverage = self._coverage(sub + cov_off)
        size1, size2 = self._value_size(vf1), self._value_size(vf2)
        if fmt == 1:
            set_count = struct.unpack_from(">H", data, sub + 8)[0]
            for i in range(min(set_count, len(coverage))):
                first = coverage[i]
                ps = sub + struct.unpack_from(">H", data, sub + 10 + 2 * i)[0]
                count = struct.unpack_from(">H", data, ps)[0]
                rec = ps + 2
                for _ in range(count):
                    second = struct.unpack_from(">H", data, rec)[0]
                    value = self._x_advance(rec + 2, vf1)
                    if value and (first, second) not in pairs:
                        pairs[(first, second)] = value
                    rec += 2 + size1 + size2
        elif fmt == 2:
            cd1, cd2, c1_count, c2_count = struct.unpack_from(">HHHH", data, sub + 8)
            class1 = self._class_def(sub + cd1)
            class2 = self._class_def(sub + cd2)
            rec_size = size1 + size2
            matrix = sub + 16
            by_class2: dict[int, list[int]] = {}
            for g, c in class2.items():
                by_class2.setdefault(c, []).append(g)
            for first in coverage:
                c1 = class1.get(first, 0)
                if c1 >= c1_count:
                    continue
                row = matrix + c1 * c2_count * rec_size
                for c2 in range(c2_count):
                    value = self._x_advance(row + c2 * rec_size, vf1)
                    if not value:
                        continue
                    for second in by_class2.get(c2, []):
                        if (first, second) not in pairs:
                            pairs[(first, second)] = value


@lru_cache(maxsize=32)
def _load(path: str) -> TrueTypeFont:
    return TrueTypeFont(path)


def font_choice(key: str | None, weight: int | None) -> tuple[LogoFont, TrueTypeFont, int]:
    """The family, the font file to read and the effective weight."""
    family = LOGO_FONTS.get((key or "").lower()) or LOGO_FONTS[DEFAULT_FONT]
    w = family.default_weight if weight is None else max(family.wmin, min(family.wmax, int(weight)))
    if family.variable:
        rel = family.files[0][1]
    else:
        rel = min(family.files, key=lambda item: (abs(item[0] - w), -item[0]))[1]
        w = next(fw for fw, path in family.files if path == rel)
    path = os.path.join(FONT_DIR, rel)
    if not os.path.isfile(path):
        raise FontError(f"The font {family.name} is not installed")
    return family, _load(path), w


@dataclass
class TextPath:
    d: str
    advance: float  # pen advance, in output units
    ink: tuple[float, float, float, float] | None  # min x, min y, max x, max y (y down)
    cap_height: float
    ascent: float
    descent: float


def _fmt(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _contour_to_path(points: list[tuple[float, float, bool]], tx) -> str:
    """One TrueType contour (quadratic, implied on-curve points) as path data."""
    if not points:
        return ""
    pts = points
    # Start on an on-curve point (or the midpoint of the first two off points).
    start_index = next((i for i, p in enumerate(pts) if p[2]), None)
    if start_index is None:
        # Every point is off-curve: start at the implied point between the
        # last and the first one.
        start = ((pts[-1][0] + pts[0][0]) / 2, (pts[-1][1] + pts[0][1]) / 2)
        seq = list(pts)
    else:
        ordered = pts[start_index:] + pts[:start_index]
        start = (ordered[0][0], ordered[0][1])
        seq = ordered[1:]
    parts = ["M" + " ".join(_fmt(c) for c in tx(*start))]
    pending = None
    for x, y, on in seq:
        if on:
            if pending is None:
                parts.append("L" + " ".join(_fmt(c) for c in tx(x, y)))
            else:
                parts.append("Q" + " ".join(_fmt(c) for c in (*tx(*pending), *tx(x, y))))
                pending = None
        else:
            if pending is not None:
                mid = ((pending[0] + x) / 2, (pending[1] + y) / 2)
                parts.append("Q" + " ".join(_fmt(c) for c in (*tx(*pending), *tx(*mid))))
            pending = (x, y)
    if pending is not None:
        parts.append("Q" + " ".join(_fmt(c) for c in (*tx(*pending), *tx(*start))))
    parts.append("Z")
    return "".join(parts)


def check_text(text: str, font_key: str | None = None, weight: int | None = None) -> None:
    """Raise FontError when the text cannot be set in the font."""
    if _complex_script(text):
        raise FontError("Wordmarks support Latin, Greek and Cyrillic text; this script needs shaping")
    _family, font, _w = font_choice(font_key, weight)
    missing = sorted({ch for ch in text if not ch.isspace() and not font.glyph_id(ch)})
    if missing:
        raise FontError(f"The font cannot draw: {' '.join(missing[:10])}")


def text_path(text: str, font_key: str | None, size: float, *, weight: int | None = None,
              x: float = 0.0, baseline: float = 0.0, tracking: float = 0.0) -> TextPath:
    """Outline of `text` at `size` units per em, pen starting at (x, baseline).

    `tracking` is extra space between letters in thousandths of an em. Raises
    FontError for scripts that need shaping or characters the font lacks.
    """
    check_text(text, font_key, weight)
    _family, font, w = font_choice(font_key, weight)
    coords = font.normalized_location(w) if _family.variable else None
    scale = size / font.units_per_em
    track = tracking / 1000.0 * size
    pen = x
    parts: list[str] = []
    ink = [float("inf"), float("inf"), float("-inf"), float("-inf")]
    previous = None
    space_glyph = font.glyph_id(" ")
    for ch in text:
        glyph = font.glyph_id(ch) if not ch.isspace() else space_glyph
        if previous is not None and glyph:
            pen += font.kerning(previous, glyph) * scale
        contours, advance = font.glyph_contours(glyph, coords) if glyph else ([], font.units_per_em * 0.25)
        ox = pen

        def tx(px: float, py: float, _ox=ox) -> tuple[float, float]:
            return (_ox + px * scale, baseline - py * scale)

        for contour in contours:
            for px, py, _on in contour:
                X, Y = tx(px, py)
                ink[0] = min(ink[0], X)
                ink[1] = min(ink[1], Y)
                ink[2] = max(ink[2], X)
                ink[3] = max(ink[3], Y)
            parts.append(_contour_to_path(contour, tx))
        pen += advance * scale + track
        previous = glyph
    pen -= track if text else 0
    return TextPath(
        d="".join(parts),
        advance=pen - x,
        ink=tuple(ink) if ink[0] != float("inf") else None,  # type: ignore[arg-type]
        cap_height=font.cap_height * scale,
        ascent=font.ascender * scale,
        descent=-font.descender * scale,
    )


def available_fonts() -> list[dict]:
    """Families that are installed, for the font picker."""
    out = []
    for family in LOGO_FONTS.values():
        if all(os.path.isfile(os.path.join(FONT_DIR, rel)) for _, rel in family.files):
            weights = [w for w, _ in family.files] if not family.variable else list(
                range(((family.wmin + 99) // 100) * 100, family.wmax + 1, 100))
            out.append({
                "key": family.key,
                "name": family.name,
                "category": family.category,
                "weights": weights,
                "default_weight": family.default_weight,
            })
    return out


# Font style preferences offered in the brief: the heading family and weight
# the brand sheet and wordmark default to, and the body family.
FONT_PAIRINGS: dict[str, dict] = {
    "sans": {"label": "Clean sans", "heading": "poppins", "heading_weight": 700, "body": "inter"},
    "geometric": {"label": "Geometric", "heading": "spacegrotesk", "heading_weight": 700, "body": "inter"},
    "serif": {"label": "Elegant serif", "heading": "playfair", "heading_weight": 700, "body": "inter"},
    "display": {"label": "Expressive", "heading": "bricolage", "heading_weight": 800, "body": "inter"},
    "condensed": {"label": "Condensed", "heading": "anton", "heading_weight": 400, "body": "inter"},
    "rounded": {"label": "Friendly", "heading": "poppins", "heading_weight": 600, "body": "poppins"},
    "script": {"label": "Script", "heading": "playfair", "heading_weight": 600, "body": "inter"},
    "tech": {"label": "Technical", "heading": "spacegrotesk", "heading_weight": 600, "body": "spacegrotesk"},
}
