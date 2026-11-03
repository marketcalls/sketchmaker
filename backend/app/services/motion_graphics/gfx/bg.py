"""Style backgrounds as base-track clips.

Textured backgrounds (film grain, paper, the Swiss grid, soft color blobs)
are generated once per (style palette, canvas, seed) as PNG files in a cache
directory and used as image clips, so the engine's still plates handle the
slow drift and no per-frame drawing is needed.
"""

from __future__ import annotations

import hashlib
import os
import random
import tempfile

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from app.render.colors import parse_color

from ..design import Frame, Look, mix


def cache_root(sub: str) -> str:
    """A writable cache folder: XDG_CACHE_HOME (app/config.py points it at
    {DATA_DIR}/cache), else the system temp directory."""
    base = os.environ.get("XDG_CACHE_HOME") or ""
    for root in ([base] if base else []) + [tempfile.gettempdir()]:
        path = os.path.join(root, sub)
        try:
            os.makedirs(path, exist_ok=True)
            if os.access(path, os.W_OK):
                return path
        except OSError:
            continue
    return tempfile.gettempdir()


_PRUNED: dict[str, float] = {}


def touch(path: str) -> None:
    """Mark a cache hit (mtime is the LRU clock; atime is often disabled)."""
    try:
        os.utime(path, None)
    except OSError:
        pass


def prune_dir(root: str, *, max_bytes: int, max_age: float, every: float = 600.0) -> None:
    """Bound a cache folder: drop files older than ``max_age`` seconds, then
    the least recently used until the folder is under ``max_bytes``. Runs at
    most once per ``every`` seconds per process; never raises."""
    import time

    now = time.time()
    if now - _PRUNED.get(root, 0.0) < every:
        return
    _PRUNED[root] = now
    files = []
    try:
        for dirpath, _dirs, names in os.walk(root):
            for n in names:
                fp = os.path.join(dirpath, n)
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                files.append((st.st_mtime, st.st_size, fp))
    except OSError:
        return
    total = sum(f[1] for f in files)
    for mtime, size, fp in sorted(files):
        if now - mtime <= max_age and total <= max_bytes:
            break
        try:
            os.remove(fp)
            total -= size
        except OSError:
            pass


BG_CACHE_MAX_BYTES = 512 * 1024 * 1024
BG_CACHE_MAX_AGE = 14 * 24 * 3600


def _save(img: Image.Image, key: str) -> str:
    folder = cache_root("motion-graphics-bg")
    path = os.path.join(folder, f"{key}.png")
    if not os.path.isfile(path):
        tmp = f"{path}.{os.getpid()}.tmp"
        img.save(tmp, format="PNG", compress_level=3)
        os.replace(tmp, path)
        # Keys include the brand palette and canvas size, so the folder would
        # otherwise grow with every palette a user tries.
        prune_dir(folder, max_bytes=BG_CACHE_MAX_BYTES, max_age=BG_CACHE_MAX_AGE)
    return path


def _grain(size, amount: float, seed: int) -> Image.Image:
    random.seed(seed)
    n = Image.effect_noise(size, 64).filter(ImageFilter.GaussianBlur(0.6))
    return n.point(lambda v: int(128 + (v - 128) * amount))


def _rgb(c: str):
    return parse_color(c)[:3]


def texture_path(fr: Frame, look: Look) -> str | None:
    kind = look.style.background
    p = look.p
    W, H = fr.W, fr.H
    key = hashlib.sha1(f"v4|{kind}|{p.bg}|{p.bg2}|{p.accent}|{p.accent2}|{p.rule}|{W}x{H}|{look.seed % 7}".encode(), usedforsecurity=False).hexdigest()[:20]
    folder = cache_root("motion-graphics-bg")
    path = os.path.join(folder, f"{key}.png")
    if os.path.isfile(path):
        touch(path)
        return path
    if kind == "solid":
        img = Image.new("RGB", (W, H), _rgb(p.bg))
        g = _grain((W, H), 0.18, look.seed)
        img = ImageChops.add(img, Image.merge("RGB", (g, g, g)), scale=1.0, offset=-128)
    elif kind == "noise":
        img = Image.new("RGB", (W, H), _rgb(p.bg))
        glow = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(glow)
        d.ellipse((-W * 0.3, -H * 0.25, W * 1.1, H * 0.75), fill=255)
        glow = glow.filter(ImageFilter.GaussianBlur(min(W, H) * 0.25))
        img = Image.composite(Image.new("RGB", (W, H), _rgb(p.bg2)), img, glow)
        g = _grain((W, H), 0.2, look.seed)
        img = ImageChops.add(img, Image.merge("RGB", (g, g, g)), scale=1.0, offset=-128)
    elif kind == "paper":
        img = Image.new("RGB", (W, H), _rgb(p.bg))
        fib = Image.effect_noise((max(8, W // 6), max(8, H // 6)), 40).resize((W, H), Image.Resampling.BICUBIC)
        fib = fib.point(lambda v: int(128 + (v - 128) * 0.08))
        img = ImageChops.add(img, Image.merge("RGB", (fib, fib, fib)), scale=1.0, offset=-128)
        g = _grain((W, H), 0.16, look.seed)
        img = ImageChops.add(img, Image.merge("RGB", (g, g, g)), scale=1.0, offset=-128)
        vig = Image.radial_gradient("L").resize((int(W * 1.5), int(H * 1.5))).crop(
            (int(W * 0.25), int(H * 0.25), int(W * 1.25), int(H * 1.25)))
        vig = vig.point(lambda v: int(max(0, v - 150) * 0.35))
        img = Image.composite(Image.new("RGB", (W, H), _rgb(mix(p.bg, "#6B5A3C", 0.5))), img, vig)
    elif kind == "grid":
        img = Image.new("RGB", (W, H), _rgb(p.bg))
        d = ImageDraw.Draw(img)
        col = _rgb(p.rule)
        for i in range(13):
            if i < 12:
                x, _ = fr.col(i, 1)
                d.line([(int(x), 0), (int(x), H)], fill=col, width=max(1, int(fr.u)))
            else:
                l, t, r, b = fr.content
                d.line([(r, 0), (r, H)], fill=col, width=max(1, int(fr.u)))
        g = _grain((W, H), 0.12, look.seed)
        img = ImageChops.add(img, Image.merge("RGB", (g, g, g)), scale=1.0, offset=-128)
    elif kind == "blobs":
        rnd = random.Random(look.seed)
        img = Image.new("RGB", (W, H), _rgb(p.bg))
        sm = (max(16, W // 8), max(16, H // 8))
        layer = Image.new("RGB", sm, _rgb(p.bg))
        spots = [(p.bg2, 0.55, 230), (mix(p.accent2, p.bg2, 0.35), 0.38, 200), (mix(p.accent, p.bg2, 0.25), 0.3, 190),
                 ("#5B3FD0", 0.34, 170)]
        anchors = [(0.15, 0.2), (0.85, 0.35), (0.25, 0.85), (0.8, 0.9)]
        rnd.shuffle(anchors)
        for (col, rad, alpha_), (ax, ay) in zip(spots, anchors):
            m = Image.new("L", sm, 0)
            r = rad * max(sm) * rnd.uniform(0.85, 1.15)
            cx, cy = (ax + rnd.uniform(-0.08, 0.08)) * sm[0], (ay + rnd.uniform(-0.08, 0.08)) * sm[1]
            ImageDraw.Draw(m).ellipse((cx - r, cy - r, cx + r, cy + r), fill=alpha_)
            m = m.filter(ImageFilter.GaussianBlur(r * 0.6))
            layer = Image.composite(Image.new("RGB", sm, _rgb(col)), layer, m)
        img = layer.resize((W, H), Image.Resampling.BICUBIC)
        dark = Image.new("RGB", (W, H), _rgb(p.bg))
        img = Image.blend(img, dark, 0.12)
        g = _grain((W, H), 0.1, look.seed)
        img = ImageChops.add(img, Image.merge("RGB", (g, g, g)), scale=1.0, offset=-128)
    elif kind == "lattice":
        # Faint diamond lattice (white at about 3.4 percent, 150u pitch), grain
        # and a radial vignette; the clip drifts it slowly.
        img = Image.new("RGB", (W, H), _rgb(p.bg))
        pitch = max(24, int(150 * fr.u))
        lines = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(lines)
        lw = max(1, int(round(fr.u * 1.2)))
        for k in range(-H // pitch - 2, (W + H) // pitch + 2):
            x0 = k * pitch
            d.line([(x0, 0), (x0 + H, H)], fill=255, width=lw)
            d.line([(x0, 0), (x0 - H, H)], fill=255, width=lw)
        img = Image.composite(Image.new("RGB", (W, H), _rgb(mix(p.bg, "#FFFFFF", 0.034 * 2.2))), img,
                              lines.point(lambda v: int(v * 0.45)))
        g = _grain((W, H), 0.11, look.seed)
        img = ImageChops.add(img, Image.merge("RGB", (g, g, g)), scale=1.0, offset=-128)
        vig = Image.radial_gradient("L").resize((int(W * 1.6), int(H * 1.6))).crop(
            (int(W * 0.3), int(H * 0.3), int(W * 1.3), int(H * 1.3)))
        vig = vig.point(lambda v: int(min(255, max(0, v - 70) * 0.75)))
        img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, vig)
    else:
        return None
    return _save(img, key)


def base_clips(fr: Frame, look: Look, duration: float) -> list[dict]:
    path = texture_path(fr, look)
    if path is None:
        return [{"start": 0.0, "duration": duration, "kind": "color", "color": look.p.bg}]
    motion = look.style.background in ("blobs", "noise", "lattice")
    clip = {"start": 0.0, "duration": duration, "kind": "image", "src": path, "transition_in": "cut"}
    if motion:
        clip.update({"motion": "push_in", "zoom_from": 1.0, "zoom_to": 1.0 + min(0.12, 0.01 * duration),
                     "drift_px": 10})
    return [clip]
