"""SQLite engine, sessions and the write lock.

How transactions work here, because it is easy to break:

The pysqlite default is deliberate. SELECTs run outside any transaction and the
first INSERT, UPDATE or DELETE issues BEGIN. So a transaction never holds a stale
read snapshot, the first write takes the write lock, and busy_timeout works. With a
deferred read transaction in WAL mode (isolation_level=None, or the SQLAlchemy BEGIN
recipe), a later write fails at once with SQLITE_BUSY_SNAPSHOT and busy_timeout does
not help. Do not "fix" this.

The one rule that matters: no network call and no ffmpeg between the first write and
the commit, because that holds the only write lock. The pattern is read, commit,
network, then lock, re-check, apply, commit.
"""

from __future__ import annotations

import os

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings

PRAGMAS = (
    "PRAGMA busy_timeout=10000",  # first: the journal_mode switch can need the lock
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA secure_delete=ON",
)


def ensure_data_dirs() -> None:
    """Create DATA_DIR and its folders, and keep them and the database private."""
    root = settings.data_dir
    for folder in (root, settings.static_dir, settings.private_media_dir, settings.backups_dir,
                   settings.cache_dir, settings.logs_dir):
        folder.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    for name in (settings.database_path.name, f"{settings.database_path.name}-wal",
                 f"{settings.database_path.name}-shm"):
        path = root / name
        if path.exists():
            os.chmod(path, 0o600)


ensure_data_dirs()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)


@event.listens_for(engine, "connect")
def _set_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    for pragma in PRAGMAS:
        cursor.execute(pragma)
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Named constraints, so a future batch migration can refer to them on SQLite.
Base = declarative_base(metadata=MetaData(naming_convention={
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}))

# JSON columns store row ids, and a reused rowid would make them point at new rows.
AUTOINCREMENT = {"sqlite_autoincrement": True}


def get_db():
    """Request-scoped session. Closing it rolls back anything uncommitted."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def apply_row_lock(query, **_):
    """Take the database write lock, then return the query reading fresh values.

    SQLite has one write lock, so this stands in for SELECT ... FOR UPDATE. It holds
    until the caller commits or rolls back, and waits up to busy_timeout for another
    writer. Call it right before the writes it protects, never before a network call.
    """
    conn = query.session.connection()
    if not conn.connection.driver_connection.in_transaction:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
    return query.populate_existing()
