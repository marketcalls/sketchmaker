"""0003_faceless_studio on a database with real rows in it."""

from contextlib import closing
import sqlite3

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
import pytest
from sqlalchemy import create_engine, pool

from app.config import settings
from app.database import Base
from app.services import migration_service
from app.services.migration_service import migrate, schema_problem

NEW_TABLES = {"faceless_series", "faceless_project", "faceless_script_version", "faceless_step_run"}


def _drop_everything() -> None:
    with closing(sqlite3.connect(settings.database_path)) as conn, conn:
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                    "AND name NOT LIKE 'sqlite_%'").fetchall():
            conn.execute(f'DROP TABLE "{name}"')


@pytest.fixture
def at_0002():
    _drop_everything()
    settings.backups_dir.mkdir(exist_ok=True)
    for path in settings.backups_dir.glob("*"):
        path.unlink()
    command.upgrade(migration_service.alembic_config(), "0002_latest_models")
    yield
    _drop_everything()


def _tables(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_an_upgrade_from_0002_keeps_characters_and_activity(at_0002):
    with closing(sqlite3.connect(settings.database_path)) as conn, conn:
        assert not NEW_TABLES & _tables(conn)
        conn.execute("INSERT INTO user (id, username, password_hash) VALUES (1, 'owner', 'x')")
        media = '[{"id": "m1", "kind": "image", "role": "reference", "file": "a.png", "storage": "uploads"}]'
        conn.execute(
            "INSERT INTO faceless_character (id, user_id, name, kind, media, consent_attested_at, is_archived) "
            "VALUES (7, 1, 'Mira', 'real_person', ?, '2026-10-01 00:00:00', 0)", (media,))
        conn.execute("INSERT INTO faceless_activity (id, user_id, character_id, kind, detail, created_at) "
                     "VALUES (3, 1, 7, 'consent_attested', '{\"relationship\": \"self\"}', '2026-10-01 00:00:00')")

    result = migrate()

    assert result.upgraded
    assert result.backup is not None, "a real database is backed up first"
    assert schema_problem() is None
    with closing(sqlite3.connect(settings.database_path)) as conn:
        assert NEW_TABLES <= _tables(conn)
        assert conn.execute("SELECT id, name, kind, media FROM faceless_character").fetchall() == \
            [(7, "Mira", "real_person", media)]
        assert conn.execute("SELECT id, project_id, character_id, kind FROM faceless_activity").fetchall() == \
            [(3, None, 7, "consent_attested")]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_the_new_tables_keep_ids_from_being_reused(at_0002):
    """JSON columns store row ids, so a reused rowid would point at a new row."""
    migrate()
    with closing(sqlite3.connect(settings.database_path)) as conn:
        for table in NEW_TABLES:
            sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (table,)).fetchone()[0]
            assert "AUTOINCREMENT" in sql.upper(), table


def test_the_migrations_end_up_exactly_where_the_models_are(at_0002):
    migrate()
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    with engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True, "render_as_batch": True})
        assert compare_metadata(context, Base.metadata) == []
