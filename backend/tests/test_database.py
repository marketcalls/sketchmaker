import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

from sqlalchemy import select, text

from app.config import settings
from app.database import Base, SessionLocal, apply_row_lock, engine
from app.models.api import APIProvider

BACKEND = Path(__file__).resolve().parents[1]


def test_pragmas_are_set():
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA synchronous")).scalar() == 1  # NORMAL
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 10000
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA secure_delete")).scalar() == 1


def test_database_lives_in_data_dir_and_is_private():
    assert str(engine.url.database) == str(settings.database_path)
    assert settings.data_dir.stat().st_mode & 0o777 == 0o700
    assert settings.database_path.stat().st_mode & 0o777 == 0o600


def test_select_does_not_open_a_transaction():
    # The rule the whole locking design rests on: never hold a stale read snapshot.
    with SessionLocal() as db:
        db.execute(select(APIProvider)).all()
        assert db.connection().connection.driver_connection.in_transaction is False


def _new_counter() -> int:
    with SessionLocal() as db:
        row = APIProvider(name="counter", is_active=True, base_url="0")
        db.add(row)
        db.commit()
        return row.id


def test_row_lock_stops_lost_updates_between_threads():
    row_id = _new_counter()
    threads_count, increments = 8, 25
    errors: list[Exception] = []
    start = threading.Barrier(threads_count)

    def worker() -> None:
        start.wait()
        for _ in range(increments):
            try:
                with SessionLocal() as db:
                    row = apply_row_lock(db.query(APIProvider).filter(APIProvider.id == row_id)).first()
                    row.base_url = str(int(row.base_url) + 1)
                    db.commit()
            except Exception as exc:  # "database is locked" would land here
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(threads_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    with SessionLocal() as db:
        assert db.get(APIProvider, row_id).base_url == str(threads_count * increments)


def test_row_lock_refreshes_a_stale_identity_map():
    row_id = _new_counter()
    with SessionLocal() as db:
        row = db.get(APIProvider, row_id)
        assert row.base_url == "0"
        db.rollback()
        with SessionLocal() as other:
            other.get(APIProvider, row_id).base_url = "7"
            other.commit()
        locked = apply_row_lock(db.query(APIProvider).filter(APIProvider.id == row_id)).first()
        assert locked.base_url == "7"
        db.rollback()


def test_row_lock_inside_an_open_write_transaction_is_fine():
    row_id = _new_counter()
    with SessionLocal() as db:
        db.add(APIProvider(name="pending", is_active=True))
        db.flush()  # the first write already holds the lock
        row = apply_row_lock(db.query(APIProvider).filter(APIProvider.id == row_id)).first()
        row.base_url = "1"
        db.commit()


def test_write_after_a_select_survives_another_connections_commit():
    """SQLITE_BUSY_SNAPSHOT: a read transaction in WAL that later writes after another
    connection committed fails at once, and busy_timeout does not help. Reads run
    outside a transaction here, so this has to work."""
    row_id = _new_counter()
    with SessionLocal() as db:
        row = db.get(APIProvider, row_id)
        assert row.base_url == "0"

        with SessionLocal() as other:
            other.add(APIProvider(name="committed-in-between", is_active=True))
            other.commit()

        row.base_url = "written after"
        db.commit()

    with SessionLocal() as db:
        assert db.get(APIProvider, row_id).base_url == "written after"


def test_that_busy_snapshot_is_real_without_the_design(tmp_path):
    """The failure the design avoids, so the test above means something."""
    path = tmp_path / "plain.db"
    first = sqlite3.connect(path, isolation_level=None, timeout=0.1)
    first.execute("PRAGMA journal_mode=WAL")
    first.execute("CREATE TABLE t (v INTEGER)")
    first.execute("INSERT INTO t VALUES (1)")
    second = sqlite3.connect(path, isolation_level=None, timeout=0.1)

    first.execute("BEGIN")
    first.execute("SELECT * FROM t").fetchall()
    second.execute("INSERT INTO t VALUES (2)")
    try:
        first.execute("UPDATE t SET v = 3")
        raised = False
    except sqlite3.OperationalError:
        raised = True
    finally:
        first.close()
        second.close()
    assert raised


def test_every_table_has_autoincrement():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )).all()
    names = {name for name, _ in rows}
    assert names == set(Base.metadata.tables)
    missing = [name for name, sql in rows if "AUTOINCREMENT" not in sql]
    assert missing == []


def test_owner_row_is_limited_to_id_one(db):
    from sqlalchemy.exc import IntegrityError
    import pytest

    from app.models.user import User

    db.add(User(id=1, username="owner", password_hash="x"))
    db.commit()
    db.add(User(id=2, username="second", password_hash="x"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_baseline_migration_matches_the_models(tmp_path):
    """upgrade head on an empty database, then `alembic check`, with models alone."""
    env = {**os.environ, "DATA_DIR": str(tmp_path / "data")}
    alembic = str(Path(sys.executable).with_name("alembic"))
    for args in (["upgrade", "head"], ["check"]):
        result = subprocess.run([alembic, *args], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
    assert "No new upgrade operations detected" in result.stdout + result.stderr
    assert (tmp_path / "data" / "sketchmaker.db").stat().st_mode & 0o777 == 0o600
