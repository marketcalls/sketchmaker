"""Rate limits, in three layers.

- ApiRateLimitMiddleware: a ceiling on every /api route, per client address. Generous,
  because an office of editors can share one address. It stops floods and a stolen
  session draining the provider keys, not normal work.
- slowapi decorators: tighter limits on routes a password can be guessed through
  (AUTH_LIMIT) and on the costly Story Room and Motion Graphics routes.
- Failed logins per address (login_failures_exceeded), so a guesser locks out itself and
  not the owner. routers/auth.py keeps a much higher account-wide lock for attacks
  spread across many addresses, which is what persists across restarts.

Counters live in this process (memory://): the app runs one worker, and they only need
to survive as long as the attacker's patience, not a restart. server/sketchmaker.nginx.conf
adds its own limits in front of these on a public server.
"""

from __future__ import annotations

import json

from fastapi import Request
from fastapi.responses import JSONResponse
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from starlette.types import ASGIApp, Receive, Scope, Send

from app.middleware.security import client_key, get_client_ip

# Login, first-run setup and change password.
AUTH_LIMIT = "5/minute"

API_READ_LIMIT = parse("1200/minute")
API_WRITE_LIMIT = parse("240/minute")
# Requests that can spend money with a provider. Motion Graphics, Story Room and Faceless
# are not here: they set their own limits on each route, because most of their writes are
# autosaves, which must not use up what starting paid work is allowed.
API_PAID_LIMIT = parse("60/minute")
PAID_ROUTERS = frozenset({
    "generate", "magix", "virtual", "explainer", "logo", "remove-bg", "video", "lip-sync", "story", "subtitle",
    "image-edit",
})

LOGIN_FAILURE_LIMIT = parse("10 per 15 minute")

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
TOO_MANY_REQUESTS = "Too many requests. Please wait a minute and try again."

limiter = Limiter(key_func=get_client_ip, storage_uri="memory://")

_storage = MemoryStorage()
_window = FixedWindowRateLimiter(_storage)


def reset_rate_limits() -> None:
    limiter.reset()
    _storage.reset()


def login_failures_exceeded(client_ip: str) -> bool:
    return not _window.test(LOGIN_FAILURE_LIMIT, "login-failure", client_ip)


def record_login_failure(client_ip: str) -> None:
    _window.hit(LOGIN_FAILURE_LIMIT, "login-failure", client_ip)


def _within_limits(method: str, path: str, client_ip: str) -> bool:
    if method in SAFE_METHODS:
        return _window.hit(API_READ_LIMIT, "api-read", client_ip)
    if path.split("/")[2] in PAID_ROUTERS and not _window.hit(API_PAID_LIMIT, "api-paid", client_ip):
        return False
    return _window.hit(API_WRITE_LIMIT, "api-write", client_ip)


class ApiRateLimitMiddleware:
    """Pure ASGI, so uploads and media streams pass straight through. It runs inside
    SecurityHeadersMiddleware, so a refusal still carries the security headers."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not limiter.enabled:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if not path.startswith("/api/") or path == "/api/health":
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        if _within_limits(scope["method"], path, client_key(client[0] if client else None)):
            await self.app(scope, receive, send)
            return
        body = json.dumps({"detail": TOO_MANY_REQUESTS}).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 429,
            "headers": [(b"content-type", b"application/json"), (b"retry-after", b"60"),
                        (b"content-length", str(len(body)).encode("ascii"))],
        })
        await send({"type": "http.response.body", "body": body})


def rate_limit_exceeded_handler(_request: Request, _exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many attempts. Please wait a minute and try again."},
    )
