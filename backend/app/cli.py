"""Owner commands: python -m app.cli <command>, run from backend/.

    init             create .env with fresh secrets (mode 600); never overwrites
    migrate          bring the database schema up to date, with a backup and restore
    create-account   create the account from the terminal (required on a public server)
    reset-password   set a new password; ends every session and clears the lockout
    unlock           clear the login lockout
    logout-all       end every session
    backup           write a database backup now

Nothing from the app is imported at module level: `init` has to work before a valid
.env exists, and importing app.config without one stops the process.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from app.envfile import env_file_path, write_new_env_file


def _init(args) -> int:
    path = env_file_path()
    try:
        write_new_env_file(path, secrets_only=args.secrets_only)
    except FileExistsError:
        print(f"{path} already exists and was left untouched.", file=sys.stderr)
        return 1
    print(f"Created {path} (mode 600).")
    return 0


def _migrate(_args) -> int:
    from app.services.migration_service import MigrationError, migrate

    try:
        result = migrate()
    except MigrationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not result.upgraded:
        print("The database is up to date.")
    elif result.backup:
        print(f"Database upgraded. The previous version is saved at {result.backup}")
    else:
        print("Database created.")
    return 0


def _create_account(_args) -> int:
    from sqlalchemy.exc import IntegrityError, OperationalError

    from app.database import SessionLocal
    from app.dependencies import get_password_hash
    from app.models.user import OWNER_ID, User
    from app.schemas.auth import USERNAME_ERROR, USERNAME_PATTERN

    db = SessionLocal()
    try:
        if db.query(User.id).first() is not None:
            print("An account already exists. To change its password, use reset-password.", file=sys.stderr)
            return 1
        username = input("Username: ").strip()
        if not USERNAME_PATTERN.match(username):
            print(USERNAME_ERROR, file=sys.stderr)
            return 1
        password = _read_new_password()
        if password is None:
            return 1
        db.add(User(id=OWNER_ID, username=username, password_hash=get_password_hash(password)))
        db.commit()
    except IntegrityError:
        print("An account already exists. To change its password, use reset-password.", file=sys.stderr)
        return 1
    except OperationalError:
        print("The database is not ready. Run the migrate command first.", file=sys.stderr)
        return 1
    finally:
        db.close()
    print(f"Account {username} created. Sign in with it in the browser.")
    return 0


def _with_owner(action) -> int:
    """Run action(db, owner) in a session and commit."""
    from sqlalchemy.exc import OperationalError

    from app.database import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        owner = db.query(User).first()
        if owner is None:
            print("There is no account yet. Create one with the create-account command.", file=sys.stderr)
            return 1
        action(db, owner)
        db.commit()
        return 0
    except OperationalError:
        print("The database is not ready. Start the app once with ./run.sh.", file=sys.stderr)
        return 1
    finally:
        db.close()


def _clear_lockout(owner) -> None:
    owner.failed_login_count = 0
    owner.failed_login_window_start = None
    owner.locked_until = None


def _read_new_password() -> str | None:
    """Prompted, never taken from argv, so it stays out of shell history and ps."""
    from app.utils.security import password_problem

    password = getpass.getpass("New password: ")
    problem = password_problem(password)
    if problem:
        print(problem, file=sys.stderr)
        return None
    if password != getpass.getpass("Repeat it: "):
        print("The passwords did not match.", file=sys.stderr)
        return None
    return password


def _reset_password(_args) -> int:
    from app.dependencies import get_password_hash

    password = _read_new_password()
    if password is None:
        return 1

    def apply(_db, owner) -> None:
        owner.password_hash = get_password_hash(password)
        owner.token_version = (owner.token_version or 0) + 1
        _clear_lockout(owner)

    code = _with_owner(apply)
    if code == 0:
        print("Password changed. Every session has been signed out.")
    return code


def _unlock(_args) -> int:
    code = _with_owner(lambda _db, owner: _clear_lockout(owner))
    if code == 0:
        print("Login lockout cleared.")
    return code


def _logout_all(_args) -> int:
    def apply(_db, owner) -> None:
        owner.token_version = (owner.token_version or 0) + 1

    code = _with_owner(apply)
    if code == 0:
        print("Every session has been signed out.")
    return code


def _backup(_args) -> int:
    from app.services.backup_service import BackupError, create_backup, prune_old_backups

    try:
        backup = create_backup()
        prune_old_backups()
    except BackupError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Wrote {backup['filename']} ({backup['size_bytes']} bytes).")
    return 0


COMMANDS = {
    "init": (_init, "create .env with fresh secrets"),
    "migrate": (_migrate, "bring the database schema up to date, with a backup and restore"),
    "create-account": (_create_account, "create the account from the terminal"),
    "reset-password": (_reset_password, "set a new password and end every session"),
    "unlock": (_unlock, "clear the login lockout"),
    "logout-all": (_logout_all, "end every session"),
    "backup": (_backup, "write a database backup now"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Sketchmaker owner commands")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, (_handler, help_text) in COMMANDS.items():
        command = commands.add_parser(name, help=help_text)
        if name == "init":
            command.add_argument("--secrets-only", action="store_true",
                                 help="write only the secrets, for settings that come from elsewhere")
    args = parser.parse_args(argv)
    return COMMANDS[args.command][0](args)


if __name__ == "__main__":
    sys.exit(main())
