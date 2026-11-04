"""FastAPI application entry point. One process, one port: the API, /static and the SPA."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import shutil

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from sqlalchemy import inspect, text

from app.config import ConfigError, settings
from app.database import SessionLocal, engine, ensure_data_dirs
from app.envfile import BACKEND_DIR
from app.middleware.security import set_inline_script_hashes
from app.middleware.setup import install_foundation
from app.models.api import APISettings
from app.models.user import User
from app.routers import (
    assets,
    auth,
    explainer,
    faceless,
    gallery,
    generate,
    image_edit,
    jobs,
    lipsync,
    logo,
    magix,
    media,
    motion_graphics,
    notifications,
    pricing,
    quality,
    reduce,
    remove_bg,
    settings as settings_router,
    story,
    story_room,
    subtitle,
    text_overlay,
    usage,
    users,
    video,
    virtual,
)
from app.seed import seed_defaults
from app.services.faceless.errors import FacelessError
from app.services.migration_service import schema_problem
from app.services.scheduler_service import job_scheduler
from app.utils import secret_box
from app.utils.logging import setup_logging

logger = logging.getLogger(__name__)

FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"
ROBOTS_TXT = "User-agent: *\nDisallow: /\n"


def _prepare_database() -> None:
    """Seed an empty database, check the secrets and arrange first-run setup."""
    if not inspect(engine).has_table(User.__tablename__):
        raise ConfigError("The database has no tables. Start with: uv run run.py, or run `python -m app.cli migrate` first.")
    problem = schema_problem()
    if problem:
        raise ConfigError(problem)

    db = SessionLocal()
    try:
        seed_defaults(db)

        row = db.query(APISettings).first()
        if row is not None:
            if secret_box.canary_status(row.secrets_canary) == "unreadable":
                logger.error(
                    "The stored API keys were encrypted with a different SECRET_KEY or ENCRYPTION_SALT and "
                    "cannot be read. Restore the original .env, or enter the keys again in Settings."
                )
            else:
                row.get_all_keys()  # registers them with the log redaction

        if db.query(User.id).first() is None:
            if settings.TRUSTED_PROXIES:
                print("\nNo account yet. Create it in the terminal: python -m app.cli create-account\n", flush=True)
            else:
                host = "127.0.0.1" if settings.HOST in ("0.0.0.0", "::") else settings.HOST
                print(f"\nFirst run. Create your account at:\n  http://{host}:{settings.PORT}\n", flush=True)
    finally:
        db.close()


def _warn_about_environment() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        logger.warning("ffmpeg or ffprobe is missing: video tools and studio renders will fail until installed.")
    # A container listens on every address of its own network; docker-compose.yml decides
    # what the host publishes, and that is 127.0.0.1.
    if not settings.is_loopback and not settings.TRUSTED_PROXIES and not os.environ.get("SKETCHMAKER_CONTAINER"):
        logger.warning(
            f"Listening on {settings.HOST} without a trusted HTTPS proxy. Other computers are refused, because "
            "sessions and API keys would cross the network unencrypted. See docs/DEPLOYMENT.md."
        )


def _release_orphaned_claims() -> None:
    from app.services.job_state import release_orphaned_claims

    db = SessionLocal()
    try:
        released = release_orphaned_claims(db)
        if released:
            logger.info(f"Resuming {released} job(s) that were saving a result when the app last stopped")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    ensure_data_dirs()
    _warn_about_environment()
    _prepare_database()
    _release_orphaned_claims()
    job_scheduler.start()
    try:
        yield
    finally:
        job_scheduler.stop()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

install_foundation(app)


@app.exception_handler(FacelessError)
async def faceless_exception_handler(_request: Request, exc: FacelessError):
    """The message in "detail" (as everywhere else) plus a machine-readable "code" and
    any extra fields."""
    body = {"detail": exc.message}
    if exc.code:
        body["code"] = exc.code
    body.update(jsonable_encoder(exc.extra or {}))
    return JSONResponse(status_code=exc.status_code, content=body)


app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["Settings"])
app.include_router(usage.router, prefix="/api/usage", tags=["Usage"])
app.include_router(pricing.router, prefix="/api/pricing", tags=["Pricing"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["Jobs"])
app.include_router(generate.router, prefix="/api/generate", tags=["Image Generation"])
app.include_router(gallery.router, prefix="/api/gallery", tags=["Gallery"])
app.include_router(explainer.router, prefix="/api/explainer", tags=["Explainer"])
app.include_router(magix.router, prefix="/api/magix", tags=["Magix"])
app.include_router(logo.router, prefix="/api/logo", tags=["Logo"])
app.include_router(virtual.router, prefix="/api/virtual", tags=["Virtual"])
app.include_router(remove_bg.router, prefix="/api/remove-bg", tags=["Background Removal"])
app.include_router(reduce.router, prefix="/api/reduce", tags=["Image Reduce"])
app.include_router(video.router, prefix="/api/video", tags=["Video Generation"])
app.include_router(lipsync.router, prefix="/api/lip-sync", tags=["Lip Sync"])
app.include_router(assets.router, prefix="/api/assets", tags=["My Assets"])
app.include_router(faceless.router, prefix="/api/faceless", tags=["Faceless Studio"])
app.include_router(motion_graphics.router, prefix="/api/motion-graphics", tags=["Motion Graphics Studio"])
app.include_router(story.router, prefix="/api/story", tags=["Story Generation"])
app.include_router(story_room.router, prefix="/api/story-room", tags=["Story Room"])
app.include_router(text_overlay.router, prefix="/api/text-overlay", tags=["Add Text"])
app.include_router(image_edit.router, prefix="/api/image-edit", tags=["Image Edit"])
app.include_router(subtitle.router, prefix="/api/subtitle", tags=["Subtitle Generation"])
app.include_router(quality.router, prefix="/api/quality", tags=["Quality Checks"])
app.include_router(media.router)


@app.get("/api/health", include_in_schema=False)
def health_check():
    """Liveness. Public, so it says nothing beyond whether the database answers."""
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check could not reach the database")
        return JSONResponse(status_code=503, content={"status": "degraded"})
    finally:
        db.close()
    return {"status": "healthy"}


@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    return PlainTextResponse(ROBOTS_TXT)


def _spa_response(full_path: str, dist: Path):
    """A built file if the path names one, otherwise the app shell for client routes."""
    root = dist.resolve()
    candidate = (root / full_path).resolve()
    if full_path and candidate.is_relative_to(root) and candidate.is_file():
        immutable = full_path.startswith("assets/")
        cache = "public, max-age=31536000, immutable" if immutable else "no-cache"
        return FileResponse(candidate, headers={"Cache-Control": cache})
    index = root / "index.html"
    if not index.is_file():
        return JSONResponse(status_code=404, content={"detail": "The frontend has not been built. Start with: uv run run.py"})
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


if (FRONTEND_DIST / "index.html").is_file():
    set_inline_script_hashes((FRONTEND_DIST / "index.html").read_text(encoding="utf-8"))


@app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
def spa_fallback(full_path: str):
    """Serve frontend/dist with SPA fallback. /api and /static are never the SPA."""
    if full_path in ("api", "static") or full_path.startswith(("api/", "static/")):
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    return _spa_response(full_path, FRONTEND_DIST)
