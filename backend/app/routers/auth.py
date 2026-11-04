"""First-run setup, login and the session.

Every route is a plain ``def`` so bcrypt and SQLite run on the thread pool: with one
worker, a password hash on the event loop would freeze the whole app for a moment.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache
import logging
import secrets

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import case, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import (
    CurrentUser,
    DbSession,
    clear_session_cookie,
    get_password_hash,
    set_session_cookie,
    user_from_session,
    verify_password,
)
from app.middleware.rate_limiter import AUTH_LIMIT, limiter, login_failures_exceeded, record_login_failure
from app.middleware.security import get_client_ip
from app.models.user import OWNER_ID, User
from app.schemas.auth import AuthSettingsResponse, LoginRequest, SetupRequest, TokenResponse
from app.schemas.common import MessageResponse
from app.schemas.user import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Ten failures block the address they came from (middleware/rate_limiter.py). This many
# within the window, which takes many addresses, lock the account for the lockout time.
# It stays far above ten so that one stranger who knows the username cannot lock everyone out.
LOGIN_MAX_FAILED_ATTEMPTS = 100
LOGIN_ATTEMPT_WINDOW_MINUTES = 15
LOGIN_LOCKOUT_MINUTES = 15

# One message for unknown username, wrong password and locked account.
INVALID_LOGIN_DETAIL = "Invalid username or password"
WEB_SETUP_DISABLED = "On a public server, the account is created in the terminal. See docs/DEPLOYMENT.md."


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    """Compared against when the username is unknown, so a missing account costs the
    same bcrypt round as a wrong password."""
    return get_password_hash(secrets.token_urlsafe(16))


def _record_failed_login(db: Session) -> None:
    """Count a failed password, locking the account at the threshold.

    One UPDATE evaluated against the current row, so concurrent attempts are all
    counted. Every SET expression sees the pre-update row.
    """
    now = datetime.utcnow()
    window_open = now - timedelta(minutes=LOGIN_ATTEMPT_WINDOW_MINUTES)
    stale = or_(User.failed_login_window_start.is_(None), User.failed_login_window_start < window_open)
    new_count = case((stale, 1), else_=User.failed_login_count + 1)
    db.execute(
        update(User)
        .where(User.id == OWNER_ID)
        .values(
            failed_login_count=new_count,
            failed_login_window_start=case((stale, now), else_=User.failed_login_window_start),
            locked_until=case(
                (new_count >= LOGIN_MAX_FAILED_ATTEMPTS, now + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)),
                else_=User.locked_until,
            ),
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()


def _owner_exists(db: Session) -> bool:
    return db.query(User.id).first() is not None


@router.get("/settings", response_model=AuthSettingsResponse)
def get_auth_settings(db: DbSession):
    """Whether the app is waiting for first-run setup."""
    return AuthSettingsResponse(setup_required=not _owner_exists(db), web_setup=not settings.TRUSTED_PROXIES)


@router.post("/setup", response_model=TokenResponse)
@limiter.limit(AUTH_LIMIT)
def setup(request: Request, response: Response, payload: SetupRequest, db: DbSession):
    """Create the owner, once, from the machine the app runs on. Whoever gets here first
    becomes the owner, so a public site never offers this: its account is created in the
    terminal (`python -m app.cli create-account`). Locally, the Host check in
    middleware/security.py keeps other websites out through DNS rebinding."""
    if _owner_exists(db):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Setup is already complete")
    if settings.TRUSTED_PROXIES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=WEB_SETUP_DISABLED)

    user = User(id=OWNER_ID, username=payload.username, password_hash=get_password_hash(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # The primary key closes the race between two setup requests.
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Setup is already complete")
    db.refresh(user)

    logger.info("Owner account created")
    set_session_cookie(response, request, user)
    return TokenResponse(user=UserResponse.model_validate(user), message="Setup complete")


@router.post("/login", response_model=TokenResponse)
@limiter.limit(AUTH_LIMIT)
def login(request: Request, response: Response, payload: LoginRequest, db: DbSession):
    """Log in with username and password."""
    user = db.query(User).filter(User.username == payload.username).first()
    client_ip = get_client_ip(request)
    address_blocked = login_failures_exceeded(client_ip)
    locked = address_blocked or bool(user and user.is_locked_out())

    # A locked account and an unknown username still pay for a bcrypt round, so the
    # response time matches a wrong password.
    password_ok = verify_password(
        payload.password,
        user.password_hash if user and not locked else _dummy_password_hash(),
    )
    if not user or locked or not password_ok:
        if not locked:
            # Attempts made while locked are not counted, so an attacker cannot keep
            # extending the lock.
            record_login_failure(client_ip)
            if user:
                _record_failed_login(db)
        if address_blocked:
            logger.warning(f"Login refused: too many failed attempts from {client_ip}. It clears within 15 minutes.")
        elif locked:
            logger.warning("Login refused: the account is locked. `python -m app.cli unlock` lifts it.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_LOGIN_DETAIL)

    if user.failed_login_count or user.locked_until or user.failed_login_window_start:
        user.failed_login_count = 0
        user.failed_login_window_start = None
        user.locked_until = None
        db.commit()
        db.refresh(user)

    set_session_cookie(response, request, user)
    return TokenResponse(user=UserResponse.model_validate(user), message="Login successful")


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, response: Response, db: DbSession):
    """End every session. Clearing the cookie alone would leave a copied one working
    for its full 30 days, so token_version moves on. A stale cookie cannot do this: it
    could otherwise keep signing the owner out."""
    user = user_from_session(request, db)
    if user is not None:
        db.execute(
            update(User)
            .where(User.id == user.id)
            .values(token_version=User.token_version + 1)
            .execution_options(synchronize_session=False)
        )
        db.commit()
    clear_session_cookie(response, request)
    return MessageResponse(message="Logout successful")


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response, db: DbSession):
    """Re-issue a valid session for another 30 days."""
    user = user_from_session(request, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    set_session_cookie(response, request, user)
    return TokenResponse(user=UserResponse.model_validate(user), message="Token refreshed")


@router.get("/me", response_model=UserResponse)
def get_me(current_user: CurrentUser):
    return UserResponse.model_validate(current_user)
