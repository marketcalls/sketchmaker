import sqlite3

from app.config import settings
from app.models.api import APIProvider
from app.services import backup_service


def test_backup_is_a_readable_private_database(db):
    db.add(APIProvider(name="in the backup", is_active=True))
    db.commit()
    backup = backup_service.create_backup()
    path = settings.backups_dir / backup["filename"]
    assert path.stat().st_mode & 0o777 == 0o600
    assert settings.backups_dir.stat().st_mode & 0o777 == 0o700
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT name FROM api_provider").fetchall() == [("in the backup",)]
    finally:
        conn.close()


def test_two_backups_in_one_second_do_not_collide():
    names = {backup_service.create_backup()["filename"] for _ in range(3)}
    assert len(names) == 3


def test_rotation_keeps_fourteen_newest():
    for name in settings.backups_dir.iterdir():
        name.unlink()
    for day in range(1, 21):
        (settings.backups_dir / f"sketchmaker-202601{day:02d}-030000.db").write_bytes(b"x")
    keep = settings.backups_dir / "not-a-backup.txt"
    keep.write_text("leave me alone")
    assert backup_service.prune_old_backups() == 6
    remaining = backup_service.list_backups()
    assert len(remaining) == 14
    assert remaining[0]["filename"] == "sketchmaker-20260120-030000.db"
    assert remaining[-1]["filename"] == "sketchmaker-20260107-030000.db"
    assert keep.exists()


def test_scheduled_backup_rotates_and_never_raises(monkeypatch):
    for name in settings.backups_dir.iterdir():
        name.unlink()
    for day in range(1, 21):
        (settings.backups_dir / f"sketchmaker-202601{day:02d}-030000.db").write_bytes(b"x")
    backup_service.run_scheduled_backup()
    assert len(backup_service.list_backups()) == 14

    def broken():
        raise backup_service.BackupError("disk full")

    monkeypatch.setattr(backup_service, "create_backup", broken)
    backup_service.run_scheduled_backup()


def test_leftover_partial_is_removed_and_never_listed():
    from app.services import backup_service

    leftover = backup_service._backup_dir() / "sketchmaker-20200101-000000.db.partial"
    leftover.write_bytes(b"incomplete")
    assert leftover.name not in [b["filename"] for b in backup_service.list_backups()]
    backup_service.create_backup()
    assert not leftover.exists()
    assert not list(backup_service._backup_dir().glob("*.partial"))
