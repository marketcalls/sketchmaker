"""Schema upgrades with a safety net: back up, migrate, verify, restore on failure.

Alembic runs non-transactional DDL on SQLite, so a migration that fails part way leaves
a half-changed database, and the only safe recovery is the copy taken before it began.
Every way of starting the app (run.py, the Docker entrypoint, server/update.sh) goes
through migrate(), and the app refuses to start on a schema that does not match its code.

The app must be stopped while this runs: a restore replaces the database file.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import shutil
import sqlite3

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import create_engine, pool

from app.config import settings
from app.database import ensure_data_dirs
from app.envfile import BACKEND_DIR
from app.services.backup_service import create_migration_backup, prune_migration_backups

logger = logging.getLogger(__name__)


class MigrationError(RuntimeError):
    """The schema could not be brought up to date. The message is written for people."""


@dataclass(frozen=True)
class MigrationResult:
    upgraded: bool
    backup: Path | None = None


def alembic_config() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


def _current_revisions() -> set[str]:
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            return set(MigrationContext.configure(connection).get_current_heads())
    finally:
        engine.dispose()


def schema_problem(config: Config | None = None) -> str | None:
    """Why this code cannot run on this database, or None when they match."""
    script = ScriptDirectory.from_config(config or alembic_config())
    current = _current_revisions()
    heads = set(script.get_heads())
    if current == heads:
        return None
    for revision in current:
        try:
            script.get_revision(revision)
        except CommandError:
            return ("This database was upgraded by a newer version of Sketchmaker than this code. "
                    "Update the code, or restore a backup taken before that upgrade.")
    return "The database schema is out of date. Run `python -m app.cli migrate`."


def _database_has_tables() -> bool:
    """False for a new install, where there is nothing to back up or put back."""
    if not settings.database_path.exists():
        return False
    with closing(sqlite3.connect(settings.database_path)) as conn:
        return conn.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table' "
                            "AND name NOT LIKE 'sqlite_%'").fetchone()[0] > 0


def _foreign_key_violations() -> int:
    with closing(sqlite3.connect(settings.database_path)) as conn:
        return len(conn.execute("PRAGMA foreign_key_check").fetchall())


def _verify(heads: set[str], violations_before: int) -> None:
    if _current_revisions() != heads:
        raise MigrationError("The database did not reach the latest revision.")
    with closing(sqlite3.connect(settings.database_path)) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise MigrationError("The database failed its integrity check after the migration.")
    # Migrations run without foreign key enforcement (alembic/env.py), so a bad one could
    # orphan rows silently. Rows that were already orphaned must not block every upgrade.
    if _foreign_key_violations() > violations_before:
        raise MigrationError("The migration left rows pointing at records that do not exist.")


def _remove_database_files() -> None:
    db = settings.database_path
    for path in (db, db.with_name(f"{db.name}-wal"), db.with_name(f"{db.name}-shm")):
        path.unlink(missing_ok=True)


def _restore(backup: Path | None) -> None:
    """Put the database back as it was. No backup means there was no database."""
    db = settings.database_path
    if backup is None:
        _remove_database_files()
        return
    # Copied beside the target and renamed, so a crash here leaves one whole file, and
    # the backup itself survives.
    restoring = db.with_name(f"{db.name}.restoring")
    shutil.copy2(backup, restoring)
    os.chmod(restoring, 0o600)
    for suffix in ("-wal", "-shm"):
        db.with_name(f"{db.name}{suffix}").unlink(missing_ok=True)
    os.replace(restoring, db)


def migrate(config: Config | None = None) -> MigrationResult:
    """Bring the schema to the latest revision. Raises MigrationError, leaving the
    database as it was, when that does not work."""
    ensure_data_dirs()
    config = config or alembic_config()
    script = ScriptDirectory.from_config(config)
    heads = set(script.get_heads())
    existed = _database_has_tables()
    current = _current_revisions()
    if current == heads:
        return MigrationResult(upgraded=False)
    problem = schema_problem(config)
    if problem and "newer version" in problem:
        raise MigrationError(problem)

    backup = create_migration_backup() if existed else None
    violations_before = _foreign_key_violations() if existed else 0
    try:
        command.upgrade(config, "head")
        _verify(heads, violations_before)
    except Exception as exc:
        logger.exception("Migration failed")
        _restore(backup)
        # A container restarting on a failed upgrade would otherwise fill the disk with copies.
        prune_migration_backups()
        kept = f" A copy is kept at {backup}." if backup else ""
        raise MigrationError(f"The migration failed, so the database was put back as it was.{kept}") from exc

    prune_migration_backups()
    return MigrationResult(upgraded=True, backup=backup)
