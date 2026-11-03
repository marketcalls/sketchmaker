"""Local database backups: VACUUM INTO, keep the newest 14, mode 0600.

Database only. Media files are on disk and not included, and .env is never included.

To restore: stop the app, copy a backup over {DATA_DIR}/sketchmaker.db, and delete
sketchmaker.db-wal and sketchmaker.db-shm. A backup holds the encrypted API keys, so
it needs the same SECRET_KEY and ENCRYPTION_SALT in .env.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import re
import sqlite3

from app.config import settings

logger = logging.getLogger(__name__)

KEEP_BACKUPS = 14
KEEP_MIGRATION_BACKUPS = 5
BUSY_TIMEOUT_MS = 10000

_FILENAME = re.compile(r"^sketchmaker-\d{8}-\d{6}\.db$")
_MIGRATION_FILENAME = re.compile(r"^pre-migrate-\d{8}-\d{6}\.db$")


class BackupError(RuntimeError):
    """A backup operation failed. The message is written for people."""


def _backup_dir() -> Path:
    path = settings.backups_dir
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def _describe(path: Path) -> dict:
    stat = path.stat()
    return {
        "filename": path.name,
        "size_bytes": stat.st_size,
        "created_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
    }


def _new_path(prefix: str = "sketchmaker") -> Path:
    moment = datetime.now()
    while True:
        path = _backup_dir() / f"{prefix}-{moment:%Y%m%d-%H%M%S}.db"
        if not path.exists():
            return path
        moment += timedelta(seconds=1)


def create_backup(prefix: str = "sketchmaker") -> dict:
    """Write a consistent copy of the database. Returns its description.

    Raw sqlite3 in autocommit mode: VACUUM cannot run in a transaction, and it reads
    from its own snapshot, so writers carry on.
    """
    path = _new_path(prefix)
    # Written under another name and renamed when complete: a backup killed part way must
    # not look finished or count toward the ones kept.
    for leftover in _backup_dir().glob("*.partial"):
        leftover.unlink(missing_ok=True)
    partial = path.with_name(path.name + ".partial")
    conn = sqlite3.connect(settings.database_path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    try:
        conn.execute("VACUUM INTO ?", (str(partial),))
    except sqlite3.Error as exc:
        logger.error(f"Backup failed: {exc}")
        partial.unlink(missing_ok=True)
        raise BackupError("The backup could not be written. See the server log.") from exc
    finally:
        conn.close()
    os.chmod(partial, 0o600)
    os.replace(partial, path)
    logger.info(f"Database backed up to {path.name}")
    return _describe(path)


def list_backups() -> list[dict]:
    """Every backup, newest first."""
    paths = [p for p in _backup_dir().iterdir() if _FILENAME.match(p.name)]
    return [_describe(p) for p in sorted(paths, key=lambda p: p.name, reverse=True)]


def prune_old_backups(keep: int = KEEP_BACKUPS) -> int:
    """Delete all but the newest ``keep``. Returns how many were deleted."""
    removed = 0
    for entry in list_backups()[keep:]:
        (_backup_dir() / entry["filename"]).unlink(missing_ok=True)
        removed += 1
    return removed


def create_migration_backup() -> Path:
    """The copy taken before a schema upgrade. Named apart from the nightly backups, so
    their rotation never removes it."""
    return _backup_dir() / create_backup(prefix="pre-migrate")["filename"]


def prune_migration_backups(keep: int = KEEP_MIGRATION_BACKUPS) -> int:
    paths = sorted((p for p in _backup_dir().iterdir() if _MIGRATION_FILENAME.match(p.name)),
                   key=lambda p: p.name, reverse=True)
    for path in paths[keep:]:
        path.unlink(missing_ok=True)
    return len(paths[keep:])


def run_scheduled_backup() -> None:
    """The nightly scheduler job: back up, then rotate. Never raises into the scheduler."""
    try:
        create_backup()
        prune_old_backups()
    except Exception:
        logger.exception("Nightly backup failed")
