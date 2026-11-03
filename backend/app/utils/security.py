"""Password rules and subprocess environment."""

from __future__ import annotations

import os

PASSWORD_MIN_LENGTH = 12
# bcrypt reads 72 bytes and bcrypt 5 raises above that.
PASSWORD_MAX_BYTES = 72

# What ffmpeg and ffprobe may inherit: enough to find libraries and write temp files.
_SUBPROCESS_ENV_KEEP = (
    "PATH", "HOME", "LANG", "LANGUAGE", "TMPDIR", "TEMP", "TMP", "XDG_CACHE_HOME",
    "FONTCONFIG_PATH", "FONTCONFIG_FILE", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "SYSTEMROOT",
)


def password_problem(password: str | None) -> str | None:
    """Why this cannot be a password, or None. The one rule for setup, change
    password and the CLI: length only, no composition rules."""
    if not password or len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters"
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        return f"Password must be at most {PASSWORD_MAX_BYTES} bytes"
    return None


def scrubbed_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for a subprocess: an allow-list, so no secret can be inherited.

    Pass as ``env=`` to every ffmpeg and ffprobe call.
    """
    env = {key: os.environ[key] for key in _SUBPROCESS_ENV_KEEP if key in os.environ}
    env.update({key: value for key, value in os.environ.items() if key.startswith("LC_")})
    if extra:
        env.update(extra)
    return env
