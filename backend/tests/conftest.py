"""Test environment: real secrets, a throwaway DATA_DIR, no .env. Set before app imports."""

from __future__ import annotations

import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile

TMP_ROOT = Path(tempfile.mkdtemp(prefix="sketchmaker-tests-"))

os.environ.update({
    "SECRET_KEY": secrets.token_urlsafe(48),
    "JWT_SECRET_KEY": secrets.token_urlsafe(48),
    "ENCRYPTION_SALT": secrets.token_urlsafe(48),
    "DATA_DIR": str(TMP_ROOT / "data"),
    "SKETCHMAKER_ENV_FILE": str(TMP_ROOT / "no-such-env"),
    "HOST": "127.0.0.1",
    "PORT": "8000",
})

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.middleware.rate_limiter import limiter, reset_rate_limits  # noqa: E402
from app.middleware.setup import install_foundation  # noqa: E402
import app.models  # noqa: E402,F401
from app.middleware import security  # noqa: E402
from app.routers import auth, jobs, media, notifications, pricing, settings as settings_router, usage, users  # noqa: E402
from app.seed import seed_defaults  # noqa: E402

PASSWORD = "correct horse battery"
USERNAME = "owner"


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(TMP_ROOT, ignore_errors=True)


def make_app() -> FastAPI:
    """Only the routers this suite owns: the tool routers are not needed to test them."""
    application = FastAPI()
    install_foundation(application)
    application.include_router(auth.router, prefix="/api/auth")
    application.include_router(users.router, prefix="/api/users")
    application.include_router(settings_router.router, prefix="/api/settings")
    application.include_router(usage.router, prefix="/api/usage")
    application.include_router(pricing.router, prefix="/api/pricing")
    application.include_router(notifications.router, prefix="/api/notifications")
    application.include_router(jobs.router, prefix="/api/jobs")
    application.include_router(media.router)
    return application


security.LOOPBACK_HOSTS.add("testserver")  # the Host header TestClient sends


@pytest.fixture(autouse=True)
def fresh_state():
    """An empty database, no media and open rate limits for every test."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    shutil.rmtree(settings.static_dir, ignore_errors=True)
    settings.static_dir.mkdir(parents=True)
    reset_rate_limits()
    limiter.enabled = True
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def seeded(db):
    seed_defaults(db)
    return db


@pytest.fixture
def api():
    return TestClient(make_app())


@pytest.fixture
def owner_client(api):
    """A client signed in as the owner, through the real setup route."""
    response = api.post("/api/auth/setup", json={"username": USERNAME, "password": PASSWORD})
    assert response.status_code == 200, response.text
    reset_rate_limits()
    return api
