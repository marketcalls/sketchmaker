"""Colour grade of a Faceless render.

The project keeps its look in ``settings`` (schemas.ProjectSettings):
``grade_look`` (an app.render.grade LOOKS id), ``grade_strength`` (0 to 1)
and ``grade_match``. A Story Room handoff also stores ``grade_plates``,
``{scene_id: {"file", "storage"}}``: the approved environment image of each
shot's place, read from the owner's images/ folder. With
``grade_match`` on, every image and video clip of a scene that has a plate is
colour matched to it before the look (render engine, Grade.match), which
evens out colour drift between generated clips of one place.

The grade touches the base track only; titles, captions, stat cards and the
end card are drawn over it ungraded (app/render/grade.py).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.render.timeline import GRADE_LOOKS

from . import media

logger = logging.getLogger(__name__)

DEFAULT_LOOK = "neutral"
DEFAULT_STRENGTH = 0.8
MATCH_STRENGTH = 0.5
PLATE_PREFIX = "__grade_plate__"
PLATE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
MAX_PLATE_BYTES = 25 * 1024 * 1024


def settings_grade(settings: Optional[dict]) -> dict:
    """{look, strength, match} from project settings, with defaults."""
    s = settings or {}
    look = s.get("grade_look")
    if look not in GRADE_LOOKS:
        look = DEFAULT_LOOK
    try:
        strength = float(s.get("grade_strength", DEFAULT_STRENGTH))
    except (TypeError, ValueError):
        strength = DEFAULT_STRENGTH
    strength = min(1.0, max(0.0, strength))
    return {"look": look, "strength": round(strength, 3), "match": bool(s.get("grade_match"))}


def timeline_grade(settings: Optional[dict]) -> Optional[dict]:
    """The Timeline.grade dict for a render, or None for no grade."""
    g = settings_grade(settings)
    if g["look"] == "neutral" and not g["match"]:
        return None
    return {"look": g["look"], "strength": g["strength"], "match": g["match"], "match_strength": MATCH_STRENGTH}


def plate_key(scene_id: str) -> str:
    return f"{PLATE_PREFIX}{scene_id}"


def plates(settings: Optional[dict]) -> dict[str, dict]:
    raw = (settings or {}).get("grade_plates")
    if not isinstance(raw, dict):
        return {}
    out = {}
    for scene_id, asset in raw.items():
        name = asset.get("file") if isinstance(asset, dict) else None
        # A bare file name in the owner's images/ folder, nothing else.
        if (isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,200}", name) and ".." not in name
                and asset.get("storage") == "images"):
            out[str(scene_id)] = {"file": name, "storage": "images"}
    return out


def load_plates(project, src_dir: str, local: dict) -> None:
    """Copy the approved plates the render will match to into ``src_dir``
    and add them to ``local`` under plate_key(scene_id). Only when the
    project asks for matching; a plate that cannot be read is skipped (the
    clip keeps the plain look)."""
    if not settings_grade(project.settings).get("match"):
        return
    by_file: dict[str, str] = {}
    for scene_id, asset in plates(project.settings).items():
        name = os.path.basename(asset["file"])
        if os.path.splitext(name)[1].lower() not in PLATE_EXTS:
            continue
        path = by_file.get(name)
        if path is None:
            try:
                content = media.run_async(media.read_bytes(asset, project.user_id))
            except Exception as exc:
                logger.warning(f"Faceless render: grade plate {name} unreadable: {exc}")
                continue
            if not content or len(content) > MAX_PLATE_BYTES:
                continue
            path = os.path.join(src_dir, f"plate_{name}")
            with open(path, "wb") as fh:
                fh.write(content)
            by_file[name] = path
        local[plate_key(scene_id)] = path


# ---------------------------------------------------------------------------
# Story Room handoff (app/services/story_room/faceless.py)
# ---------------------------------------------------------------------------

# First match wins: the words of the story's look (visual style, palette,
# lighting, camera feel) that clearly ask for one of the house looks.
_LOOK_WORDS: tuple[tuple[str, str], ...] = (
    ("mono_contrast", r"black[- ]and[- ]white|monochrome|\bmono\b|\bnoir\b|grayscale|greyscale|\bb&w\b"),
    ("golden_hour", r"golden hour|golden light|sunset|sundown|late sun|magic hour"),
    ("teal_orange", r"teal and orange|orange and teal|teal[/-]orange|blockbuster"),
    ("soft_pastel", r"pastel|dreamy|airy|soft colou?r"),
    ("documentary_muted", r"documentary|muted|desaturated|washed[- ]out|naturalistic|observational"),
    ("cool_clean", r"\bcool\b|\bcold\b|icy|clinical|steel|blue tones?|bluish|moonlight"),
    ("warm_film", r"\bwarm\b|amber|nostalgic|vintage|film grain|35 ?mm|16 ?mm|\bfilm stock|kodak|retro"),
)


def look_for_story(look) -> str:
    """A house look for a Story Room document's look, else neutral."""
    def field(name: str) -> str:
        value = look.get(name) if isinstance(look, dict) else getattr(look, name, "")
        return value if isinstance(value, str) else ""

    text = " ".join(field(n) for n in ("visual_style", "palette", "lighting", "camera_feel")).lower()
    for key, pattern in _LOOK_WORDS:
        if re.search(pattern, text):
            return key
    if field("register").lower() == "documentary":
        return "documentary_muted"
    return DEFAULT_LOOK


def _storage_key(url: Optional[str], user_id: int) -> Optional[str]:
    """The images/ key of an image URL, when it is exactly the URL this app
    serves for one of the user's own stored images; else None."""
    if not url or not isinstance(url, str):
        return None
    from app.services.storage_service import storage_service

    name = url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,200}", name or ""):
        return None
    try:
        if storage_service.get_public_url(name, "images", user_id=user_id) == url.split("?", 1)[0]:
            return name
    except Exception:
        return None
    return None


def _library_plate(db: Session, user_id: int, env_id) -> Optional[str]:
    """The newest photo of a library environment (approved images are copied
    there when the entry is linked)."""
    from app.services.story_room import library

    env = library.owned_environment(db, user_id, env_id)
    for m in reversed(list(env.media or []) if env is not None else []):
        if isinstance(m, dict) and m.get("key"):
            return str(m["key"])
    return None


def handoff_settings(db: Session, user_id: int, doc) -> dict:
    """Project settings for a Story Room handoff: the house look its look
    words ask for, and the approved environment plates by script scene id
    (the script has one scene per shot, s1, s2 and so on in shot order).
    Plates are matched only when there is at least one."""
    look = look_for_story(getattr(doc, "look", None) or {})
    found: dict[str, dict] = {}
    cache: dict[str, Optional[str]] = {}
    index = 0
    for scene in getattr(doc, "scenes", None) or []:
        env = doc.env(scene.environment_key) if getattr(scene, "environment_key", None) else None
        key = None
        if env is not None and env.image_approved:
            if env.key not in cache:
                try:
                    cache[env.key] = _storage_key(env.image_url, user_id) or (
                        _library_plate(db, user_id, env.ref_id) if env.ref_id else None)
                except Exception as exc:
                    logger.warning(f"Story Room handoff: plate for {env.key} skipped: {exc}")
                    cache[env.key] = None
            key = cache[env.key]
        for _shot in scene.shots:
            index += 1
            if key:
                found[f"s{index}"] = {"file": key, "storage": "images"}
    out: dict = {"grade_look": look, "grade_strength": DEFAULT_STRENGTH}
    if found:
        out["grade_match"] = True
        out["grade_plates"] = found
    return out
