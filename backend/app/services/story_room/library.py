"""The shared library behind Story Room: characters (faceless_character) and the
story_environment places.

Saving a proposed cast member always makes a fictional character (a
real_person character needs the likeness consent, which only the character
form collects). Environment photos are stored as env_<uuid>.<ext> under the
user's images/{user_id}/ folder and are deleted with their entry.
"""

from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.faceless import FacelessCharacter
from app.models.story_room import StoryEnvironment

from .models import CastEntry, EnvEntry

logger = logging.getLogger(__name__)

MAX_LIBRARY_CHARACTERS = 200    # same cap as POST /api/faceless/characters
MAX_ENVIRONMENTS = 200
MAX_ENV_MEDIA = 6
ENV_MEDIA_MAX_BYTES = 25 * 1024 * 1024
SUMMARY_ITEMS = 30
RASTER_FORMATS = {"PNG": (".png", "image/png"), "JPEG": (".jpg", "image/jpeg"), "WEBP": (".webp", "image/webp")}


class LibraryError(Exception):
    """A problem the user should see; ``status_code`` maps it to HTTP."""

    status_code = 400

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code:
            self.status_code = status_code


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------

def character_clause(char: FacelessCharacter) -> str:
    """The character's likeness clause from its bible, else its notes."""
    bible = char.bible if isinstance(char.bible, dict) else {}
    clause = str(bible.get("likeness_clause") or "").strip()
    if clause:
        return clause
    parts = [char.name or ""]
    for value in (bible.get("canonical_description"), char.notes, char.style_notes):
        if value and str(value).strip():
            parts.append(str(value).strip())
    return ", ".join(p for p in parts if p)[:600]


def owned_character(db: Session, user_id: int, char_id: int | None) -> FacelessCharacter | None:
    if not char_id:
        return None
    return db.query(FacelessCharacter).filter(
        FacelessCharacter.id == int(char_id), FacelessCharacter.user_id == user_id).first()


def entry_clause(entry: CastEntry) -> str:
    """A likeness clause built from the story's own description of a character."""
    parts = [entry.name]
    if entry.description:
        parts.append(entry.description)
    if entry.wardrobe:
        parts.append(f"wearing {entry.wardrobe}")
    return ", ".join(p.strip().rstrip(".") for p in parts if p and p.strip())[:600]


def save_character(db: Session, user_id: int, entry: CastEntry) -> FacelessCharacter:
    """A new fictional faceless_character for a proposed cast member. No commit.

    The bible is built from the story's description (source "notes"), so the
    character's likeness clause works straight away; the AI bible can replace
    it later."""
    count = db.query(FacelessCharacter).filter(FacelessCharacter.user_id == user_id).count()
    if count >= MAX_LIBRARY_CHARACTERS:
        raise LibraryError(f"You can keep at most {MAX_LIBRARY_CHARACTERS} characters. Delete some first.")
    name = (entry.name or "Unnamed").strip()[:120] or "Unnamed"
    bible = {
        "name": name,
        "canonical_description": entry.description or name,
        "outfit": entry.wardrobe or "",
        "distinguishing_features": [],
        "likeness_clause": entry_clause(entry),
        "style_notes": "",
        "age_range": "",
        "species": "human",
        "safety_flags": [],
        "source": "notes",
        "model": None,
    }
    char = FacelessCharacter(
        user_id=user_id, name=name, kind="fictional", role=(entry.role or None) and entry.role[:120],
        notes=entry.description or None,
        style_notes=f"Wardrobe: {entry.wardrobe}" if entry.wardrobe else None,
        species="human", bible=bible, media=[], safety_flags=[],
    )
    if entry.voice_notes:
        char.personality = f"Voice: {entry.voice_notes}"
    db.add(char)
    db.flush()
    return char


def character_view(char: FacelessCharacter) -> dict:
    from app.services.faceless import views

    return views.character_view(char)


# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------

def owned_environment(db: Session, user_id: int, env_id: int | None, lock: bool = False) -> StoryEnvironment | None:
    from app.database import apply_row_lock

    if not env_id:
        return None
    query = db.query(StoryEnvironment).filter(StoryEnvironment.id == int(env_id),
                                              StoryEnvironment.user_id == user_id)
    if lock:
        query = apply_row_lock(query.populate_existing())
    return query.first()


def check_environment_room(db: Session, user_id: int) -> None:
    count = db.query(StoryEnvironment).filter(StoryEnvironment.user_id == user_id).count()
    if count >= MAX_ENVIRONMENTS:
        raise LibraryError(f"You can keep at most {MAX_ENVIRONMENTS} environments. Delete some first.")


def save_environment(db: Session, user_id: int, entry: EnvEntry) -> StoryEnvironment:
    """A new story_environment for a proposed place. No commit."""
    check_environment_room(db, user_id)
    env = StoryEnvironment(
        user_id=user_id, name=(entry.name or "Unnamed place").strip()[:120] or "Unnamed place",
        description=entry.description or None, time_of_day=(entry.time_of_day or None),
        mood=(entry.mood or None), media=[],
    )
    db.add(env)
    db.flush()
    return env


def media_url(entry: dict, user_id: int) -> str:
    from app.services.storage_service import storage_service

    return storage_service.get_public_url(entry["key"], "images", user_id=user_id)


def environment_view(env: StoryEnvironment) -> dict:
    media = []
    for m in env.media or []:
        if not isinstance(m, dict) or not m.get("key"):
            continue
        media.append({"url": media_url(m, env.user_id), "key": m["key"], "content_type": m.get("content_type"),
                      "width": m.get("width"), "height": m.get("height")})
    return {
        "id": env.id, "name": env.name, "description": env.description or "", "time_of_day": env.time_of_day or "",
        "mood": env.mood or "", "style_notes": env.style_notes or "", "media": media,
        "is_archived": bool(env.is_archived),
        "created_at": env.created_at.isoformat() if env.created_at else None,
        "updated_at": env.updated_at.isoformat() if env.updated_at else None,
    }


def inspect_image(content: bytes) -> dict:
    """{ext, content_type, width, height} of a PNG, JPEG or WebP, from its own bytes."""
    from PIL import Image, UnidentifiedImageError

    head = content[:12]
    if not (head[:8] == b"\x89PNG\r\n\x1a\n" or head[:3] == b"\xff\xd8\xff"
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")):
        raise LibraryError("Upload a PNG, JPEG or WebP image.")
    try:
        with Image.open(io.BytesIO(content)) as img:
            fmt = (img.format or "").upper()
            width, height = img.size
            img.verify()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
        raise LibraryError("The image could not be read. Upload a PNG, JPEG or WebP image.")
    if fmt not in RASTER_FORMATS or not width or not height:
        raise LibraryError("Upload a PNG, JPEG or WebP image.")
    ext, content_type = RASTER_FORMATS[fmt]
    return {"ext": ext, "content_type": content_type, "width": width, "height": height}


async def store_environment_image(user_id: int, content: bytes) -> dict:
    """Store a checked image under images/{user_id}/; returns its media entry."""
    from app.services.storage_service import storage_service

    if len(content) > ENV_MEDIA_MAX_BYTES:
        raise LibraryError("The image is too large. Upload one up to 25 MB.")
    info = inspect_image(content)
    key = f"env_{uuid.uuid4().hex}{info['ext']}"
    url = await storage_service.upload_file(file_data=content, filename=key, storage_type="images",
                                            content_type=info["content_type"], user_id=user_id)
    return {"url": url, "key": key, "content_type": info["content_type"], "width": info["width"],
            "height": info["height"], "created_at": datetime.utcnow().isoformat()}


async def delete_environment_files(user_id: int, entries: list[dict]) -> None:
    from app.services.storage_service import storage_service

    for entry in entries or []:
        key = (entry or {}).get("key")
        if not key:
            continue
        try:
            await storage_service.delete_file(key, "images", user_id=user_id)
        except Exception:
            logger.exception(f"Could not delete environment photo {key} of user {user_id}")


# ---------------------------------------------------------------------------
# What the director sees
# ---------------------------------------------------------------------------

def summary(db: Session, user_id: int) -> str:
    """The user's library as short lines for the director's context."""
    chars = (db.query(FacelessCharacter)
             .filter(FacelessCharacter.user_id == user_id, FacelessCharacter.is_archived == False)  # noqa: E712
             .order_by(FacelessCharacter.updated_at.desc()).limit(SUMMARY_ITEMS).all())
    envs = (db.query(StoryEnvironment)
            .filter(StoryEnvironment.user_id == user_id, StoryEnvironment.is_archived == False)  # noqa: E712
            .order_by(StoryEnvironment.updated_at.desc()).limit(SUMMARY_ITEMS).all())
    lines = []
    if chars:
        lines.append("Characters:")
        for c in chars:
            role = f" ({c.role})" if c.role else ""
            lines.append(f"- ref_id {c.id}: {c.name}{role}. Likeness: {character_clause(c)[:300]}")
    if envs:
        lines.append("Environments:")
        for e in envs:
            extra = ", ".join(x for x in (e.time_of_day, e.mood) if x)
            lines.append(f"- ref_id {e.id}: {e.name}. {(e.description or '')[:300]}"
                         + (f" ({extra})" if extra else ""))
    return "\n".join(lines) if lines else "The library is empty."


# ---------------------------------------------------------------------------
# Approved reference images
# ---------------------------------------------------------------------------

async def copy_to_character(db: Session, char: FacelessCharacter, content: bytes) -> bool:
    """Add an approved image to a library character's references as its own
    copy (deleting the character media never touches the gallery or My
    Assets file). Skipped, not refused, when the character is full or its
    consent does not allow uploads. The caller commits."""
    from fastapi.concurrency import run_in_threadpool

    from app.services.faceless import catalog, consent, media
    from app.services.faceless.errors import FacelessError

    if len(char.media or []) >= catalog.MAX_CHARACTER_MEDIA:
        return False
    try:
        consent.require_can_upload(char)
        info = await run_in_threadpool(media.prepare_image, content)
    except FacelessError as exc:
        logger.info(f"Approved image not added to character {char.id}: {exc.message}")
        return False
    stored = await media.store_character_bytes(char, info["content"], prefix="fl_char", ext=info["ext"],
                                               content_type=info["content_type"])
    entry = media.media_entry(stored, kind="image", role="reference", width=info["width"], height=info["height"])
    media.set_json(char, "media", list(char.media or []) + [entry])
    return True


async def copy_to_environment(env: StoryEnvironment, content: bytes) -> bool:
    """Add an approved image to an environment's photos as its own copy.
    Skipped when the environment already has the most photos. The caller commits."""
    from sqlalchemy.orm.attributes import flag_modified

    if len(env.media or []) >= MAX_ENV_MEDIA:
        return False
    try:
        entry = await store_environment_image(env.user_id, content)
    except LibraryError:
        return False
    env.media = list(env.media or []) + [entry]
    flag_modified(env, "media")
    return True
