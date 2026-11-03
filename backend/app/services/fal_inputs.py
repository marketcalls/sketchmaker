"""Hand our own local files to fal.

fal cannot read local URLs. resolve_fal_inputs walks a fal arguments dict and swaps
every own /static/... URL (or private media reference) for a fal storage URL, so the
callers of the fal_client wrappers do not change. The fal URL is only ever a request
argument: database columns keep the local URL (assets.py compares them), which is
why it is memoised here and never persisted.

upload_file takes a path. Above 100 MB the SDK uploads in 10 MB parts from disk, so a
500 MB video is not read into memory; at or below that it reads the whole file.

These are blocking network calls. From async code, use resolve_fal_inputs_async.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
import logging
from pathlib import Path
import threading
import time

from app.config import settings
from app.services.storage_service import UnsafeMediaPath, own_media_relpath, safe_static_path

logger = logging.getLogger(__name__)

# Internal form of a private media file (real-person photos, never served at /static):
#     /private_media/{user_id}/{filename}
PRIVATE_MEDIA_PREFIX = "/private_media/"

# Longer than any job, and shorter than fal could plausibly keep a file.
MEMO_TTL_SECONDS = 6 * 60 * 60
MEMO_MAX_ENTRIES = 512

_memo: OrderedDict[tuple[str, int], tuple[str, float]] = OrderedDict()
_memo_lock = threading.Lock()


def clear_memo() -> None:
    with _memo_lock:
        _memo.clear()


def upload_local_file(path: Path) -> str:
    """Upload one file to fal storage. Returns its fal URL."""
    from app.services.fal_keys import get_sync_client

    return get_sync_client().upload_file(path)


def _private_media_path(url: str) -> Path:
    root = settings.private_media_dir.resolve()
    parts = url[len(PRIVATE_MEDIA_PREFIX):].split("/")
    if len(parts) != 2 or not parts[0].isdigit() or parts[1] in ("", ".", "..") or "\\" in parts[1] or "\0" in parts[1]:
        raise UnsafeMediaPath(f"Unsafe media path: {url!r}")
    candidate = (root / parts[0] / parts[1]).resolve()
    if not candidate.is_relative_to(root):
        raise UnsafeMediaPath(f"Unsafe media path: {url!r}")
    return candidate


def _local_path(url: str) -> Path | None:
    """The file behind one of our own references, or None when it is not ours.
    Raises UnsafeMediaPath for traversal."""
    relative = own_media_relpath(url)
    if relative is not None:
        return safe_static_path(relative)
    if url.startswith(PRIVATE_MEDIA_PREFIX):
        return _private_media_path(url)
    return None


def _fal_url_for(path: Path) -> str:
    """The fal URL of a local file, from the memo while the file is unchanged."""
    try:
        stat = path.stat()
    except FileNotFoundError:
        raise FileNotFoundError(f"A local file for this request is missing: {path.name}") from None
    key = (str(path), stat.st_mtime_ns)
    now = time.monotonic()
    with _memo_lock:
        entry = _memo.get(key)
        if entry is not None and now - entry[1] < MEMO_TTL_SECONDS:
            _memo.move_to_end(key)
            return entry[0]
    url = upload_local_file(path)
    with _memo_lock:
        _memo[key] = (url, now)
        while len(_memo) > MEMO_MAX_ENTRIES:
            _memo.popitem(last=False)
    return url


def resolve_fal_inputs(arguments):
    """A copy of a fal arguments value with every own file replaced by a fal URL.

    Walks dicts and lists. https and data: URLs and everything else pass through
    untouched. Raises UnsafeMediaPath for a path trying to leave its folder and
    FileNotFoundError for a local file that is gone.
    """
    if isinstance(arguments, str):
        path = _local_path(arguments)
        return arguments if path is None else _fal_url_for(path)
    if isinstance(arguments, list):
        return [resolve_fal_inputs(item) for item in arguments]
    if isinstance(arguments, dict):
        return {key: resolve_fal_inputs(value) for key, value in arguments.items()}
    return arguments


async def resolve_fal_inputs_async(arguments):
    """resolve_fal_inputs off the event loop."""
    return await asyncio.to_thread(resolve_fal_inputs, arguments)
