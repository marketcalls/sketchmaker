"""The upgrade procedure itself: backup, restore on failure, and the startup check."""

import os
from pathlib import Path
import sqlite3
import textwrap

from alembic.config import Config
import pytest

from app.config import settings
from app.envfile import BACKEND_DIR
from app.models.user import User
from app.services import backup_service, migration_service
from app.services.migration_service import MigrationError, migrate, schema_problem


def _drop_everything() -> None:
    with sqlite3.connect(settings.database_path) as conn:
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                    "AND name NOT LIKE 'sqlite_%'").fetchall():
            conn.execute(f'DROP TABLE "{name}"')


@pytest.fixture
def empty_database():
    """No tables at all, as on a new install."""
    _drop_everything()
    settings.backups_dir.mkdir(exist_ok=True)
    for path in settings.backups_dir.glob("*"):
        path.unlink()
    yield
    _drop_everything()


def config_with_revision(tmp_path: Path, upgrade_body: str) -> Config:
    """The real migrations plus one more, written for this test."""
    versions = BACKEND_DIR / "alembic" / "versions"
    extra = tmp_path / "versions"
    extra.mkdir()
    head = migration_service.ScriptDirectory.from_config(migration_service.alembic_config()).get_current_head()
    body = textwrap.indent(textwrap.dedent(upgrade_body).strip(), "    ")
    (extra / "9999_test.py").write_text(
        "import sqlalchemy as sa\nfrom alembic import op\n"
        f'revision = "9999_test"\ndown_revision = "{head}"\nbranch_labels = None\ndepends_on = None\n'
        f"def upgrade():\n{body}\ndef downgrade():\n    pass\n"
    )
    config = migration_service.alembic_config()
    config.set_main_option("path_separator", "os")
    config.set_main_option("version_locations", f"{versions}{os.pathsep}{extra}")
    return config


def tables() -> set[str]:
    with sqlite3.connect(settings.database_path) as conn:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def version() -> str | None:
    with sqlite3.connect(settings.database_path) as conn:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    return row[0] if row else None


def test_a_new_database_is_created_without_a_backup(empty_database):
    result = migrate()
    assert result.upgraded
    assert result.backup is None
    assert schema_problem() is None
    assert User.__tablename__ in tables()


def test_an_up_to_date_database_is_left_alone(empty_database):
    migrate()
    result = migrate()
    assert not result.upgraded
    assert result.backup is None
    assert backup_service.list_backups() == []


def test_a_good_migration_keeps_a_backup_of_the_old_schema(empty_database, tmp_path):
    migrate()
    head_before = version()
    config = config_with_revision(tmp_path, 'op.create_table("added", sa.Column("id", sa.Integer, primary_key=True))')

    result = migrate(config)

    assert result.upgraded
    assert "added" in tables()
    assert version() == "9999_test"
    assert result.backup.name.startswith("pre-migrate-")
    assert result.backup.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(result.backup) as old:
        assert old.execute("SELECT version_num FROM alembic_version").fetchone()[0] == head_before
    # The nightly rotation must not count or remove it.
    assert backup_service.list_backups() == []


def test_a_failed_migration_puts_the_database_back(empty_database, tmp_path):
    migrate()
    head_before = version()
    with sqlite3.connect(settings.database_path) as conn:
        conn.execute("CREATE TABLE keep_me (value TEXT)")
        conn.execute("INSERT INTO keep_me VALUES ('still here')")
    # SQLite DDL here is not transactional, so the first step stays applied unless restored.
    config = config_with_revision(tmp_path, """\
        op.create_table("half_done", sa.Column("id", sa.Integer, primary_key=True))
        raise RuntimeError("boom")
        """)

    with pytest.raises(MigrationError, match="put back"):
        migrate(config)

    assert "half_done" not in tables()
    assert version() == head_before
    with sqlite3.connect(settings.database_path) as conn:
        assert conn.execute("SELECT value FROM keep_me").fetchone()[0] == "still here"
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert settings.database_path.stat().st_mode & 0o777 == 0o600
    assert list(settings.backups_dir.glob("pre-migrate-*.db"))


def test_a_migration_that_orphans_rows_is_undone(empty_database, tmp_path):
    migrate()
    with sqlite3.connect(settings.database_path) as conn:
        conn.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))")
        conn.execute("INSERT INTO parent VALUES (1)")
        conn.execute("INSERT INTO child VALUES (1)")
    config = config_with_revision(tmp_path, 'op.execute("DELETE FROM parent")')

    with pytest.raises(MigrationError):
        migrate(config)

    with sqlite3.connect(settings.database_path) as conn:
        assert conn.execute("SELECT count(*) FROM parent").fetchone()[0] == 1


def test_rows_already_orphaned_do_not_block_an_upgrade(empty_database, tmp_path):
    migrate()
    with sqlite3.connect(settings.database_path) as conn:
        conn.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))")
        conn.execute("INSERT INTO child VALUES (42)")
    config = config_with_revision(tmp_path, 'op.create_table("added", sa.Column("id", sa.Integer, primary_key=True))')
    assert migrate(config).upgraded


def test_a_database_from_newer_code_is_refused_untouched(empty_database):
    migrate()
    with sqlite3.connect(settings.database_path) as conn:
        conn.execute("UPDATE alembic_version SET version_num = 'from_the_future'")

    assert "newer version" in schema_problem()
    with pytest.raises(MigrationError, match="newer version"):
        migrate()
    assert version() == "from_the_future"
    assert backup_service.list_backups() == []
    assert not list(settings.backups_dir.glob("pre-migrate-*.db"))


def test_a_database_behind_the_code_is_reported(empty_database, tmp_path):
    migrate()
    config = config_with_revision(tmp_path, "pass")
    assert "out of date" in schema_problem(config)


def test_only_the_newest_migration_backups_are_kept(empty_database):
    migrate()
    settings.backups_dir.mkdir(exist_ok=True)
    for day in range(10, 18):
        (settings.backups_dir / f"pre-migrate-202601{day}-000000.db").write_text("x")
    (settings.backups_dir / "sketchmaker-20260101-000000.db").write_text("nightly")

    assert backup_service.prune_migration_backups() == 3
    assert len(list(settings.backups_dir.glob("pre-migrate-*.db"))) == 5
    assert (settings.backups_dir / "sketchmaker-20260101-000000.db").exists()
