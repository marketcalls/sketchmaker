"""FastAPI dependencies: the session cookie and who it belongs to.

One HS256 JWT in an httpOnly cookie, valid 30 days. It has to be long-lived because
<img> and <video> load /static with the cookie alone and cannot trigger a refresh.
The ``pwd`` claim is required and checked on every request, so a password change or a
logout ends every session at once.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import hmac
from typing import Annotated

import bcrypt
from fastapi import Depends, HTTPException, Request, Response, status
import jwt
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.utils.security import PASSWORD_MAX_BYTES


def verify_password(plain_password: str, hashed_password: str) -> bool:
    encoded = plain_password.encode("utf-8")
    if len(encoded) > PASSWORD_MAX_BYTES:
        return False  # no stored password is this long, and bcrypt 5 would raise
    return bcrypt.checkpw(encoded, hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    """Hash a password that already passed utils.security.password_problem."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_session_token(user: User) -> str:
    expires = datetime.utcnow() + timedelta(days=settings.SESSION_DAYS)
    claims = {"sub": str(user.id), "pwd": user.password_fingerprint(), "exp": expires}
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def set_session_cookie(response: Response, request: Request, user: User) -> None:
    """Secure follows the scheme this request arrived on, as the browser saw it
    (uvicorn applies X-Forwarded-Proto from TRUSTED_PROXIES)."""
    response.set_cookie(
        key=settings.SESSION_COOKIE,
        value=create_session_token(user),
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
        max_age=settings.SESSION_DAYS * 24 * 60 * 60,
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        key=settings.SESSION_COOKIE,
        path="/",
        secure=request.url.scheme == "https",
        httponly=True,
        samesite="lax",
    )


def user_from_session(request: Request, db: Session) -> User | None:
    """The user a valid session cookie belongs to, else None."""
    token = request.cookies.get(settings.SESSION_COOKIE)
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub", "pwd"]},
        )
        user_id = int(payload["sub"])
    except (InvalidTokenError, TypeError, ValueError):
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not hmac.compare_digest(str(payload["pwd"]), user.password_fingerprint()):
        return None
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = user_from_session(request, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
