"""Encryption for the API keys stored in the database.

Fernet with a key derived per column by HKDF-SHA256:

    salt  ENCRYPTION_SALT, random per install
    info  sketchmaker/secrets/v3/{field}

Stored as ``v3:<fernet token>``. A database copy alone reveals nothing, and a value
copied into another column does not decrypt there. There is no other format and no
plaintext fallback: anything that is not readable v3 is unreadable.

``secrets_canary`` (APISettings) holds a known value under the same scheme, so a
wrong SECRET_KEY reports "unreadable" rather than "not configured". Changing
SECRET_KEY or ENCRYPTION_SALT by hand orphans every stored key; use
``python -m app.cli rotate-secret-key``. Restoring a backup needs the .env it was
made with.
"""

from __future__ import annotations

import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

PREFIX = "v3:"
_INFO_PREFIX = "sketchmaker/secrets/v3/"

CANARY_FIELD = "canary"
CANARY_VALUE = "sketchmaker-canary-v3"

# Masks show the end of a key only, and only of a key long enough to spare it.
MASK_MIN_LENGTH = 12
MASK_VISIBLE = 4


@lru_cache(maxsize=64)
def _fernet_for(secret_key: str, salt: str, field: str) -> Fernet:
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt.encode("utf-8"),
        info=f"{_INFO_PREFIX}{field}".encode("utf-8"),
    ).derive(secret_key.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key))


def _material(secret_key: str | None, salt: str | None) -> tuple[str, str]:
    if secret_key is not None and salt is not None:
        return secret_key, salt
    from app.config import settings

    return secret_key or settings.SECRET_KEY, salt or settings.ENCRYPTION_SALT


def _remember_for_redaction(plaintext: str) -> None:
    from app.utils.logging import register_secret

    register_secret(plaintext)


def encrypt(plaintext: str, field: str, *, secret_key: str | None = None, salt: str | None = None) -> str:
    """Encrypt for one column. ``field`` is the domain: the column name."""
    if not plaintext:
        raise ValueError("Nothing to encrypt")
    if not field:
        raise ValueError("An encryption field name is required")
    key, salt_value = _material(secret_key, salt)
    if field != CANARY_FIELD:
        _remember_for_redaction(plaintext)
    return PREFIX + _fernet_for(key, salt_value, field).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(value: str | None, field: str, *, secret_key: str | None = None, salt: str | None = None) -> str | None:
    """Plaintext of a stored value, or None when it is empty or cannot be read."""
    if not is_encrypted(value):
        return None
    key, salt_value = _material(secret_key, salt)
    try:
        plaintext = _fernet_for(key, salt_value, field).decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        return None
    if field != CANARY_FIELD:
        _remember_for_redaction(plaintext)
    return plaintext


def is_encrypted(value) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def make_canary(*, secret_key: str | None = None, salt: str | None = None) -> str:
    return encrypt(CANARY_VALUE, CANARY_FIELD, secret_key=secret_key, salt=salt)


def canary_status(stored: str | None, *, secret_key: str | None = None, salt: str | None = None) -> str:
    """"absent", "ok" or "unreadable" (the database was encrypted with other secrets)."""
    if not stored:
        return "absent"
    readable = decrypt(stored, CANARY_FIELD, secret_key=secret_key, salt=salt) == CANARY_VALUE
    return "ok" if readable else "unreadable"


def mask_key(key: str | None) -> str | None:
    """``****abcd``, or None for a key too short to show any of."""
    if not key or len(key) < MASK_MIN_LENGTH:
        return None
    return "****" + key[-MASK_VISIBLE:]


def looks_masked(value: str | None) -> bool:
    """True for a display mask sent back by a client: saving one must not replace
    the real key with it."""
    if not value:
        return False
    return "****" in value or set(value) <= {"*", "•", " "}
