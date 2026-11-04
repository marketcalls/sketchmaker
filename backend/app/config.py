"""Application configuration, read from the .env file `python -m app.cli init` writes.

Secrets have no defaults. A random fallback per process would silently make every
stored API key unreadable after a restart, so a missing, short or placeholder value
stops the app with a message saying how to fix it.
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from typing import ClassVar

from pydantic import ValidationError
from pydantic_settings import BaseSettings

from app.envfile import SECRET_FIELDS, env_file_path, secret_problem

# Every file this process creates is private: the database, media, logs, backups,
# and whatever ffmpeg writes (it inherits the umask).
os.umask(0o077)

# Must be set before anything imports litellm: in its default mode it loads the
# nearest .env into os.environ, which would hand SECRET_KEY to every subprocess.
os.environ["LITELLM_MODE"] = "PRODUCTION"


class ConfigError(SystemExit):
    """The app cannot start with this configuration. Prints the message and exits 1."""


class Settings(BaseSettings):
    """Values from the environment or the .env file."""

    model_config = {"extra": "ignore", "env_file_encoding": "utf-8"}

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings,
                                   file_secret_settings):
        # .env wins. An exported SECRET_KEY would otherwise silently make every stored key
        # unreadable, and an exported DEBUG or HOST would change how the app runs.
        return init_settings, dotenv_settings, env_settings, file_secret_settings

    SECRET_KEY: str = ""
    JWT_SECRET_KEY: str = ""
    ENCRYPTION_SALT: str = ""
    DATA_DIR: str = "./data"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    TRUSTED_PROXIES: str = ""
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Constants, not configuration.
    APP_NAME: ClassVar[str] = "Sketchmaker"
    APP_VERSION: ClassVar[str] = "3.0.0"
    JWT_ALGORITHM: ClassVar[str] = "HS256"
    SESSION_DAYS: ClassVar[int] = 30
    SESSION_COOKIE: ClassVar[str] = "sm_session"
    MAX_UPLOAD_SIZE_MB: ClassVar[int] = 50
    MAX_VIDEO_UPLOAD_SIZE_MB: ClassVar[int] = 100

    @property
    def data_dir(self) -> Path:
        """Absolute DATA_DIR. A relative one is relative to the .env file."""
        path = Path(self.DATA_DIR).expanduser()
        return path if path.is_absolute() else (env_file_path().parent / path).resolve()

    @property
    def database_path(self) -> Path:
        return self.data_dir / "sketchmaker.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    @property
    def static_dir(self) -> Path:
        return self.data_dir / "static"

    @property
    def private_media_dir(self) -> Path:
        return self.data_dir / "private_media"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def is_loopback(self) -> bool:
        if self.HOST == "localhost":
            return True
        try:
            return ipaddress.ip_address(self.HOST).is_loopback
        except ValueError:
            return False


INIT_HINT = "Run `python -m app.cli init` from backend/ to create it."


def load_settings() -> Settings:
    """Read and check the configuration. Raises ConfigError with a readable message."""
    path = env_file_path()
    # Windows does not keep file modes: write_new_env_file limits the file with icacls there.
    if os.name != "nt" and path.exists() and path.stat().st_mode & 0o007:
        raise ConfigError(f"{path} can be accessed by other users on this machine. Run: chmod 600 {path}")

    try:
        loaded = Settings(_env_file=path)
    except ValidationError as exc:
        fields = ", ".join(str(err["loc"][0]) for err in exc.errors() if err.get("loc"))
        raise ConfigError(f"{path} has an invalid value for: {fields}") from None

    problems = []
    for field in SECRET_FIELDS:
        problem = secret_problem(getattr(loaded, field))
        if problem:
            problems.append(f"{field} {problem}")
    if problems:
        hint = INIT_HINT if not path.exists() else "Fix it, or move the file away and run `python -m app.cli init`."
        raise ConfigError(f"Cannot start: {'; '.join(problems)} (in {path}). {hint}")
    if loaded.SECRET_KEY == loaded.JWT_SECRET_KEY:
        raise ConfigError(f"Cannot start: SECRET_KEY and JWT_SECRET_KEY must differ (in {path}).")
    return loaded


settings = load_settings()

# Render work directories are created under this (faceless/render_job.py,
# motion_graphics/jobs.py), and a video render does not fit in a tmpfs.
os.environ["XDG_CACHE_HOME"] = str(settings.cache_dir)
