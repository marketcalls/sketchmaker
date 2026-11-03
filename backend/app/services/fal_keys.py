"""The fal API key and SDK clients built from it.

The key never goes in os.environ: ffmpeg and every other subprocess would inherit it,
and the SDK's module-level functions (fal_client.submit and friends) belong to one
client that caches the first key it saw. Use these clients instead:

    from app.services.fal_keys import get_sync_client

    client = get_sync_client(db)
    handle = client.submit(endpoint, arguments=arguments)
    status = client.status(endpoint, request_id, with_logs=True)
    result = client.result(endpoint, request_id)

    # Blocking network calls. In an async def:
    #     await asyncio.to_thread(get_sync_client(db).subscribe, endpoint, arguments=arguments)
"""

from __future__ import annotations

from functools import lru_cache

import fal_client
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.api import APISettings


FAL_KEY_REJECTED = "fal rejected your API key. Check it in Settings, under API keys."


def is_fal_auth_error(exc: BaseException) -> bool:
    """fal refused the stored key, as opposed to any other failure."""
    return isinstance(exc, fal_client.client.FalClientHTTPError) and exc.status_code in (401, 403)


class FalKeyMissing(ValueError):
    """No fal key is stored, or it cannot be read with this SECRET_KEY."""


def load_fal_key(db: Session | None = None) -> str | None:
    """The decrypted fal key. Reads through ``db``, or a short session of its own."""
    if db is not None:
        row = db.query(APISettings).first()
        return row.get_fal_key() if row else None
    session = SessionLocal()
    try:
        row = session.query(APISettings).first()
        return row.get_fal_key() if row else None
    finally:
        session.close()


def require_fal_key(db: Session | None = None) -> str:
    """The decrypted fal key. Raises FalKeyMissing (a ValueError) when there is none."""
    key = load_fal_key(db)
    if not key:
        raise FalKeyMissing("Add your fal API key in Settings, under API keys.")
    return key


@lru_cache(maxsize=1)
def _sync_client_for(key: str) -> fal_client.SyncClient:
    # A client keeps its HTTP connection pool, so reuse it until the key changes.
    return fal_client.SyncClient(key=key)


def get_sync_client(db: Session | None = None) -> fal_client.SyncClient:
    """A SyncClient for the current key, safe to share between threads."""
    return _sync_client_for(require_fal_key(db))


def new_async_client(db: Session | None = None) -> fal_client.AsyncClient:
    """A new AsyncClient for the current key. Not cached: its connection pool belongs
    to one event loop, and the scheduler runs each coroutine on a loop of its own."""
    return fal_client.AsyncClient(key=require_fal_key(db))
