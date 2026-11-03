"""Logging setup, with API keys kept out of every log line.

The filter runs on handlers, not the root logger: a filter on a logger only sees
records logged directly on that logger, not ones propagated from its children.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
from logging.handlers import RotatingFileHandler

from app.config import settings

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_MAX_BYTES = 50 * 1024 * 1024
LOG_BACKUP_COUNT = 5

REDACTED = "[REDACTED]"

_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{8,}"),
    re.compile(r"gsk_[A-Za-z0-9_\-]{8,}"),
    re.compile(r"xai-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=\-]+"),
    # fal's Authorization header: "Key <id>:<secret>"
    re.compile(r"\bKey\s+[A-Za-z0-9_\-]{8,}:[A-Za-z0-9_\-]{8,}"),
)

# Shorter values would redact ordinary words.
_MIN_SECRET_LENGTH = 8

_secrets: set[str] = set()
_secrets_lock = threading.Lock()


def register_secret(value: str | None) -> None:
    """Add a stored key's value to what every log line has removed."""
    if value and len(value) >= _MIN_SECRET_LENGTH:
        with _secrets_lock:
            _secrets.add(value)


def redact(text: str) -> str:
    """The text with stored key values and key-shaped strings replaced."""
    with _secrets_lock:
        known = tuple(_secrets)
    for value in known:
        if value in text:
            text = text.replace(value, REDACTED)
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def _clean_arg(value):
    # Numbers stay numbers for %d. Everything else may print a key, so it becomes text.
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact(str(value))


class RedactingFilter(logging.Filter):
    """Rewrites a record's message, traceback and stack before it is formatted.

    args stay separate rather than being merged into msg: uvicorn's access formatter
    unpacks them, so a record without its five args breaks every access log line.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if isinstance(record.args, dict):
            record.args = {key: _clean_arg(value) for key, value in record.args.items()}
        elif record.args:
            record.args = tuple(_clean_arg(value) for value in record.args)
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True


_redacting_filter = RedactingFilter()

# Installed by uvicorn with propagate off, so the root handlers never see them.
_OWN_HANDLER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def setup_logging() -> None:
    """Console and a rotating file under DATA_DIR/logs, both redacted."""
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    logfile = RotatingFileHandler(
        settings.logs_dir / "sketchmaker.log",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    logfile.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [console, logfile]
    for handler in root.handlers:
        handler.addFilter(_redacting_filter)

    for name in _OWN_HANDLER_LOGGERS:
        for handler in logging.getLogger(name).handlers:
            handler.addFilter(_redacting_filter)

    # Their INFO lines carry full request URLs.
    for name in ("httpx", "httpcore", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
