import os
from pathlib import Path
import secrets
import subprocess
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def run(args, env_file, extra=None, stdin=None):
    env = {k: v for k, v in os.environ.items()
           if k not in ("SECRET_KEY", "JWT_SECRET_KEY", "ENCRYPTION_SALT", "DATA_DIR")}
    env.update({"SKETCHMAKER_ENV_FILE": str(env_file), **(extra or {})})
    return subprocess.run([sys.executable, *args], cwd=BACKEND, env=env, capture_output=True, text=True,
                          input=stdin, timeout=120)


def start(env_file, extra=None):
    """What happens when the app imports its settings."""
    return run(["-c", "import app.config"], env_file, extra)


def good_env(data_dir) -> str:
    return (f"SECRET_KEY={secrets.token_urlsafe(48)}\nJWT_SECRET_KEY={secrets.token_urlsafe(48)}\n"
            f"ENCRYPTION_SALT={secrets.token_urlsafe(48)}\nDATA_DIR={data_dir}\n")


def test_init_writes_a_private_env_and_refuses_to_overwrite(tmp_path):
    env_file = tmp_path / ".env"
    first = run(["-m", "app.cli", "init"], env_file)
    assert first.returncode == 0, first.stderr
    assert env_file.stat().st_mode & 0o777 == 0o600
    content = env_file.read_text()
    for name in ("SECRET_KEY=", "JWT_SECRET_KEY=", "ENCRYPTION_SALT=", "DATA_DIR=./data", "HOST=127.0.0.1", "PORT=8000"):
        assert name in content

    second = run(["-m", "app.cli", "init"], env_file)
    assert second.returncode != 0
    assert "already exists" in second.stderr
    assert env_file.read_text() == content
    assert content.split("SECRET_KEY=")[1] not in second.stdout + second.stderr


def test_init_values_are_distinct_and_accepted(tmp_path):
    env_file = tmp_path / ".env"
    run(["-m", "app.cli", "init"], env_file)
    values = dict(line.split("=", 1) for line in env_file.read_text().splitlines() if "=" in line and line[0] != "#")
    assert len({values["SECRET_KEY"], values["JWT_SECRET_KEY"], values["ENCRYPTION_SALT"]}) == 3
    assert start(env_file).returncode == 0


def test_missing_env_refuses_and_says_what_to_do(tmp_path):
    result = start(tmp_path / "absent")
    assert result.returncode != 0
    assert "python -m app.cli init" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("field", ["SECRET_KEY", "JWT_SECRET_KEY", "ENCRYPTION_SALT"])
@pytest.mark.parametrize("value", ["", "too-short", "your-secret-key-here-your-secret-key-here-0123",
                                   "change-me-change-me-change-me-change-me", "a" * 64])
def test_bad_secrets_refuse(tmp_path, field, value):
    env_file = tmp_path / ".env"
    lines = [line for line in good_env(tmp_path).splitlines() if not line.startswith(f"{field}=")]
    env_file.write_text("\n".join([*lines, f"{field}={value}"]) + "\n")
    env_file.chmod(0o600)
    result = start(env_file)
    assert result.returncode != 0
    assert field in result.stderr
    if value:
        assert value not in result.stderr


def test_same_key_for_both_refuses(tmp_path):
    env_file = tmp_path / ".env"
    shared = secrets.token_urlsafe(48)
    env_file.write_text(f"SECRET_KEY={shared}\nJWT_SECRET_KEY={shared}\nENCRYPTION_SALT={secrets.token_urlsafe(48)}\n")
    env_file.chmod(0o600)
    assert start(env_file).returncode != 0


@pytest.mark.parametrize("mode", [0o644, 0o604, 0o606])
def test_world_readable_env_refuses(tmp_path, mode):
    env_file = tmp_path / ".env"
    env_file.write_text(good_env(tmp_path))
    env_file.chmod(mode)
    result = start(env_file)
    assert result.returncode != 0
    assert "chmod 600" in result.stderr


def test_private_env_is_accepted(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(good_env(tmp_path))
    env_file.chmod(0o600)
    result = start(env_file)
    assert result.returncode == 0, result.stderr


def test_relative_data_dir_follows_the_env_file(tmp_path):
    env_file = tmp_path / ".env"
    run(["-m", "app.cli", "init"], env_file)
    result = run(["-c", "from app.config import settings; print(settings.database_path)"], env_file)
    assert result.stdout.strip() == str(tmp_path / "data" / "sketchmaker.db")


def _ready_install(tmp_path) -> Path:
    env_file = tmp_path / ".env"
    run(["-m", "app.cli", "init"], env_file)
    env = {"SKETCHMAKER_ENV_FILE": str(env_file)}
    alembic = str(Path(sys.executable).with_name("alembic"))
    upgraded = subprocess.run([alembic, "upgrade", "head"], cwd=BACKEND, capture_output=True, text=True,
                              env={k: v for k, v in {**os.environ, **env}.items()
                                   if k not in ("SECRET_KEY", "JWT_SECRET_KEY", "ENCRYPTION_SALT", "DATA_DIR")})
    assert upgraded.returncode == 0, upgraded.stderr
    return env_file


CREATE_OWNER = """
from app.database import SessionLocal
from app.dependencies import get_password_hash
from app.models.user import User
db = SessionLocal()
db.add(User(id=1, username="owner", password_hash=get_password_hash("correct horse battery"),
            failed_login_count=9, token_version=3))
db.commit()
"""
READ_OWNER = """
from app.database import SessionLocal
from app.dependencies import verify_password
from app.models.user import User
db = SessionLocal()
u = db.query(User).first()
print(u.token_version, u.failed_login_count, verify_password("a brand new long password", u.password_hash))
"""


def test_reset_password_unlock_logout_all_and_backup(tmp_path):
    env_file = _ready_install(tmp_path)
    assert run(["-c", CREATE_OWNER], env_file).returncode == 0

    assert run(["-m", "app.cli", "unlock"], env_file).returncode == 0
    assert run(["-c", READ_OWNER], env_file).stdout.split() == ["3", "0", "False"]

    assert run(["-m", "app.cli", "logout-all"], env_file).returncode == 0
    assert run(["-c", READ_OWNER], env_file).stdout.split()[0] == "4"

    script = (
        "import getpass, sys\n"
        "getpass.getpass = lambda prompt='': 'a brand new long password'\n"
        "from app.cli import main\n"
        "sys.exit(main(['reset-password']))\n"
    )
    assert run(["-c", script], env_file).returncode == 0
    assert run(["-c", READ_OWNER], env_file).stdout.split() == ["5", "0", "True"]

    backup = run(["-m", "app.cli", "backup"], env_file)
    assert backup.returncode == 0, backup.stderr
    assert len(list((tmp_path / "data" / "backups").glob("sketchmaker-*.db"))) == 1


def test_reset_password_applies_the_rule(tmp_path):
    env_file = _ready_install(tmp_path)
    script = (
        "import getpass, sys\n"
        "getpass.getpass = lambda prompt='': 'short'\n"
        "from app.cli import main\n"
        "sys.exit(main(['reset-password']))\n"
    )
    result = run(["-c", script], env_file)
    assert result.returncode == 1
    assert "at least 12" in result.stderr


def test_removed_commands_are_gone(tmp_path):
    for command in ("rotate-secret-key", "restore"):
        assert run(["-m", "app.cli", command], tmp_path / ".env").returncode == 2


def test_env_file_wins_over_exported_variables(tmp_path):
    env_file = tmp_path / ".env"
    fd = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(fd, ("\n".join(f"{name}={'x' * 8}{secrets.token_urlsafe(32)}" for name in
                            ("SECRET_KEY", "JWT_SECRET_KEY", "ENCRYPTION_SALT")) +
                  f"\nDATA_DIR={tmp_path}/data\nHOST=127.0.0.1\nDEBUG=false\n").encode())
    os.close(fd)
    env = {**os.environ, "SKETCHMAKER_ENV_FILE": str(env_file), "HOST": "0.0.0.0", "DEBUG": "*",
           "SECRET_KEY": "exported-" + "y" * 40}
    code = "from app.config import settings as s; print(s.HOST, s.DEBUG, s.SECRET_KEY.startswith('exported'))"
    done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=BACKEND)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "127.0.0.1 False False"


def test_secrets_only_env_takes_other_settings_from_the_environment(tmp_path):
    env = tmp_path / ".env"
    assert run(["-m", "app.cli", "init", "--secrets-only"], env).returncode == 0
    text = env.read_text()
    assert "SECRET_KEY=" in text and "HOST=" not in text and "DATA_DIR=" not in text
    assert env.stat().st_mode & 0o777 == 0o600

    result = run(["-c", "from app.config import settings as s; print(s.HOST, s.DATA_DIR, s.TRUSTED_PROXIES)"], env,
                 {"HOST": "0.0.0.0", "DATA_DIR": str(tmp_path / "data"), "TRUSTED_PROXIES": "*"})
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["0.0.0.0", str(tmp_path / "data"), "*"]


def test_migrate_command_creates_then_reports_up_to_date(tmp_path):
    env = tmp_path / ".env"
    env.write_text(good_env(tmp_path / "data"))
    env.chmod(0o600)

    first = run(["-m", "app.cli", "migrate"], env)
    assert first.returncode == 0, first.stderr
    assert "created" in first.stdout

    second = run(["-m", "app.cli", "migrate"], env)
    assert second.returncode == 0, second.stderr
    assert "up to date" in second.stdout
    assert (tmp_path / "data" / "sketchmaker.db").stat().st_mode & 0o777 == 0o600


CREATE_ACCOUNT = """
import getpass, builtins, sys
getpass.getpass = lambda prompt="": {password!r}
builtins.input = lambda prompt="": {username!r}
from app.cli import main
sys.exit(main(["create-account"]))
"""


def test_create_account_from_the_terminal(tmp_path):
    env = tmp_path / ".env"
    env.write_text(good_env(tmp_path / "data"))
    env.chmod(0o600)
    assert run(["-m", "app.cli", "migrate"], env).returncode == 0

    bad_name = run(["-c", CREATE_ACCOUNT.format(username="no spaces", password="a long enough password")], env)
    assert bad_name.returncode == 1
    short = run(["-c", CREATE_ACCOUNT.format(username="editor_team", password="short")], env)
    assert short.returncode == 1

    created = run(["-c", CREATE_ACCOUNT.format(username="editor_team", password="a long enough password")], env)
    assert created.returncode == 0, created.stderr
    assert "a long enough password" not in created.stdout + created.stderr

    again = run(["-c", CREATE_ACCOUNT.format(username="someone_else", password="a long enough password")], env)
    assert again.returncode == 1
    assert "already exists" in again.stderr


def test_app_refuses_to_start_on_an_out_of_date_schema(tmp_path):
    import sqlite3

    env = tmp_path / ".env"
    env.write_text(good_env(tmp_path / "data"))
    env.chmod(0o600)
    assert run(["-m", "app.cli", "migrate"], env).returncode == 0
    with sqlite3.connect(tmp_path / "data" / "sketchmaker.db") as conn:
        conn.execute("UPDATE alembic_version SET version_num = 'from_the_future'")

    result = run(["-c", "import app.main as m; m._prepare_database()"], env)
    assert result.returncode != 0
    assert "newer version" in result.stderr + result.stdout
