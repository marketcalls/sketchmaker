"""File storage under DATA_DIR.

    {DATA_DIR}/static/images/{user_id}/x.png         /static/images/{user_id}/x.png
    {DATA_DIR}/static/videos/{user_id}/x.mp4         /static/videos/{user_id}/x.mp4
    {DATA_DIR}/static/videos/thumbnails/{user_id}/x  /static/videos/thumbnails/{user_id}/x
    {DATA_DIR}/static/videos/uploads/{user_id}/x     /static/videos/uploads/{user_id}/x

URLs are relative, so a change of host does not break stored rows. /static is an
authenticated route (app/routers/media.py), not a public mount. Writes are atomic:
a reader never sees half a file.

    from app.services.storage_service import storage_service

    url = await storage_service.upload_file(content, "image.png", "images", user_id=1)
    await storage_service.delete_file("image.png", "images", user_id=1)
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import shutil
import tempfile
from typing import Literal, Optional
from urllib.parse import unquote, urlsplit

from app.config import settings

logger = logging.getLogger(__name__)

StorageType = Literal["images", "videos", "thumbnails", "uploads"]

STATIC_PREFIX = "/static/"

_SUBPATHS = {
    "images": "images",
    "videos": "videos",
    "thumbnails": "videos/thumbnails",
    "uploads": "videos/uploads",
}

_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
}


class UnsafeMediaPath(ValueError):
    """A media path that would step outside its folder."""


def _safe_name(filename: str) -> str:
    """Refuse a filename that could step outside its folder.

    Filenames are generated server-side today, but they are joined straight onto local
    paths, so one that ever carried user input could write or delete other files.
    """
    name = filename or ""
    if not name or "\\" in name or "\0" in name or name.startswith("/") or ".." in name.split("/"):
        raise ValueError(f"Unsafe storage filename: {filename!r}")
    return name


def safe_static_path(relative: str) -> Path:
    """The absolute path of a file under {DATA_DIR}/static, from a path relative to it.

    ``relative`` is already percent-decoded. Raises UnsafeMediaPath for traversal,
    backslashes, NUL, percent signs (a second round of encoding), dot files (temp
    files of a write in progress) and anything that resolves outside the folder,
    symlinks included. The file need not exist.
    """
    root = settings.static_dir.resolve()
    if not relative or "\\" in relative or "\0" in relative or "%" in relative or relative.startswith("/"):
        raise UnsafeMediaPath(f"Unsafe media path: {relative!r}")
    parts = relative.split("/")
    if any(part in ("", ".", "..") or part.startswith(".") for part in parts):
        raise UnsafeMediaPath(f"Unsafe media path: {relative!r}")
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise UnsafeMediaPath(f"Unsafe media path: {relative!r}")
    return candidate


def own_media_relpath(url: str | None) -> str | None:
    """The path under /static of one of our own URLs (query string dropped and percent
    decoded), or None when the URL points anywhere else."""
    if not url or not isinstance(url, str) or not url.startswith(STATIC_PREFIX):
        return None
    return unquote(urlsplit(url).path)[len(STATIC_PREFIX):]


def read_local_media(url: str | None) -> Path | None:
    """The file behind one of our own /static URLs, for code that needs the bytes.

    None when the URL is not ours or the file is gone, so the caller can go on to
    url_fetch for a real remote URL (which refuses local addresses). Raises
    UnsafeMediaPath for a /static URL that tries to leave the folder.
    """
    relative = own_media_relpath(url)
    if relative is None:
        return None
    path = safe_static_path(relative)
    return path if path.is_file() else None


class StorageService:
    """Local file storage. A singleton: StorageService() returns the same object."""

    _instance: Optional["StorageService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _folder(self, storage_type: StorageType, user_id: Optional[int]) -> Path:
        base = settings.static_dir / _SUBPATHS[storage_type]
        return base / str(user_id) if user_id is not None else base

    def get_public_url(self, filename: str, storage_type: StorageType, user_id: Optional[int] = None) -> str:
        """Relative URL for a stored file."""
        folder = f"{_SUBPATHS[storage_type]}/{user_id}" if user_id is not None else _SUBPATHS[storage_type]
        return f"{STATIC_PREFIX}{folder}/{filename}"

    def get_local_path(self, filename: str, storage_type: StorageType, user_id: Optional[int] = None) -> str:
        """Absolute local path for a file, as a string."""
        _safe_name(filename)
        return str(self._folder(storage_type, user_id) / filename)

    def _write_atomic(self, target: Path, write) -> None:
        """Write through a temp file in the same folder, then rename over the target."""
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(dir=target.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as fh:
                write(fh)
            os.replace(temp_path, target)
        except BaseException:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise

    async def upload_file(
        self,
        file_data: bytes,
        filename: str,
        storage_type: StorageType,
        content_type: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> str:
        """Store bytes and return the URL."""
        _safe_name(filename)
        target = self._folder(storage_type, user_id) / filename
        await asyncio.to_thread(self._write_atomic, target, lambda fh: fh.write(file_data))
        logger.debug(f"Saved {target}")
        return self.get_public_url(filename, storage_type, user_id)

    async def upload_file_from_path(
        self,
        source_path: str,
        filename: str,
        storage_type: StorageType,
        content_type: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> str:
        """Copy a file that is already on disk and return the URL. For large files (a
        500 MB subtitle source): the bytes are never held in memory."""
        _safe_name(filename)
        target = self._folder(storage_type, user_id) / filename

        def copy(fh) -> None:
            with open(source_path, "rb") as source:
                shutil.copyfileobj(source, fh, 1024 * 1024)

        await asyncio.to_thread(self._write_atomic, target, copy)
        logger.debug(f"Saved {target}")
        return self.get_public_url(filename, storage_type, user_id)

    async def delete_file(self, filename: str, storage_type: StorageType, user_id: Optional[int] = None) -> bool:
        """Delete a stored file. True when it is gone, including when it never existed;
        False when the delete failed, so the caller can say so."""
        _safe_name(filename)
        target = self._folder(storage_type, user_id) / filename
        try:
            await asyncio.to_thread(target.unlink, missing_ok=True)
            return True
        except OSError as exc:
            logger.error(f"Could not delete {target}: {type(exc).__name__}: {exc}")
            return False

    async def file_exists(self, filename: str, storage_type: StorageType, user_id: Optional[int] = None) -> bool:
        _safe_name(filename)
        return (self._folder(storage_type, user_id) / filename).is_file()

    async def get_file_bytes(
        self,
        filename: str,
        storage_type: StorageType,
        user_id: Optional[int] = None,
    ) -> Optional[bytes]:
        """The bytes of a stored file, or None when it is missing or unreadable."""
        path = Path(self.get_local_path(filename, storage_type, user_id))
        if not path.is_file():
            return None
        try:
            return await asyncio.to_thread(path.read_bytes)
        except OSError as exc:
            logger.warning(f"Could not read {path}: {type(exc).__name__}")
            return None

    async def download_from_url(
        self,
        url: str,
        filename: str,
        storage_type: StorageType,
        user_id: Optional[int] = None,
    ) -> str:
        """Download through the SSRF-safe fetcher and store it. Returns the URL."""
        from app.services.url_fetch import afetch_bytes

        content = await afetch_bytes(url, timeout=300)
        return await self.upload_file(content, filename, storage_type, None, user_id)

    def _guess_content_type(self, filename: str) -> str:
        return _CONTENT_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")


storage_service = StorageService()
