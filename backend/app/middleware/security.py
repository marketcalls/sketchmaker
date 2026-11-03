"""Security headers and the Origin check, as pure ASGI so media streams pass through."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import logging
import re
from urllib.parse import urlsplit

import jwt
from starlette.datastructures import Headers
from starlette.requests import Request, cookie_parser
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings

logger = logging.getLogger(__name__)

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Nothing a stranger may send (sign-in, setup) comes near this, and FastAPI reads a whole
# upload before a route's login check runs.
MAX_BODY_WITHOUT_SESSION = 1024 * 1024
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
_DEFAULT_PORTS = {"http": 80, "https": 443}

PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
    "microphone=(), payment=(), usb=()"
)
HSTS_VALUE = "max-age=31536000"
API_CACHE_CONTROL = "private, no-store, max-age=0"
CROSS_SITE_DETAIL = "This request came from another site and was refused."
SIGN_IN_TO_UPLOAD_DETAIL = "Please sign in to upload files."
UNKNOWN_HOST_DETAIL = (
    "This address is not allowed. Open the app at http://127.0.0.1, or publish it on a domain "
    "(docs/DEPLOYMENT.md)."
)

_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)

# Hashes of the inline scripts in the built index.html, set at startup.
_inline_script_hashes: tuple[str, ...] = ()


def get_client_ip(request: Request) -> str:
    """The client address. uvicorn has already applied X-Forwarded-For when the peer
    is in TRUSTED_PROXIES (--forwarded-allow-ips), and ignored it otherwise."""
    return client_key(request.client.host if request.client else None)


def client_key(host: str | None) -> str:
    """The key rate limits count against. IPv6 counts by /64, because one customer controls
    a whole /64 and could otherwise use a new address for every guess."""
    if not host:
        return "unknown"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if address.version == 6:
        if address.ipv4_mapped:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network((address, 64), strict=False))
    return host


def hash_inline_scripts(html: str) -> tuple[str, ...]:
    """CSP source expressions for every inline script in a page."""
    return tuple(
        "'sha256-" + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode("ascii") + "'"
        for body in _INLINE_SCRIPT.findall(html)
        if body.strip()
    )


def set_inline_script_hashes(html: str) -> None:
    """Allow the inline scripts of the page the app serves, and only those."""
    global _inline_script_hashes
    _inline_script_hashes = hash_inline_scripts(html)


def content_security_policy(https: bool) -> str:
    script_src = " ".join(("'self'", *_inline_script_hashes))
    directives = [
        "default-src 'self'",
        f"script-src {script_src}",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com data:",
        "img-src 'self' data: blob: https:",
        "media-src 'self' blob: https:",
        "connect-src 'self'",
        "frame-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'self'",
    ]
    if https:
        directives.append("upgrade-insecure-requests")
    return "; ".join(directives)


def _host_port(netloc: str, scheme: str) -> tuple[str, int | None]:
    try:
        parts = urlsplit(f"//{netloc}")
        return (parts.hostname or "").lower(), parts.port or _DEFAULT_PORTS.get(scheme)
    except ValueError:
        return "", None


def origin_allowed(origin: str, headers: Headers) -> bool:
    """Whether a browser request's Origin is this app.

    Compared against Host (or X-Forwarded-Host, which a cross-site page cannot set
    without a CORS preflight, and CORS is off). The scheme is left out: behind a TLS
    proxy the request here is plain HTTP while the browser's Origin says https.
    """
    try:
        parts = urlsplit(origin)
        scheme = parts.scheme
        origin_host = (parts.hostname or "").lower()
        origin_port = parts.port or _DEFAULT_PORTS.get(scheme)
    except ValueError:
        return False
    if not origin_host:
        return False  # "null" from sandboxed frames and data: URLs
    # The Vite dev server proxies with changeOrigin, so Host is the backend's.
    if settings.DEBUG and origin_host in LOOPBACK_HOSTS:
        return True
    for name in ("x-forwarded-host", "host"):
        value = headers.get(name)
        if value and _host_port(value.split(",")[0].strip(), scheme) == (origin_host, origin_port):
            return True
    return False


def host_allowed(headers: Headers) -> bool:
    """Whether the browser used a name this app answers to.

    Stops DNS rebinding: a website can point its own name at 127.0.0.1, which passes the
    Origin check because Origin and Host then agree. A browser cannot forge Host, so
    without a proxy only loopback names are served. With a proxy, it picks the names
    (server/sketchmaker.nginx.conf drops unknown ones).
    """
    if settings.TRUSTED_PROXIES:
        return True
    hostname, _port = _host_port(headers.get("host", ""), "http")
    return hostname in LOOPBACK_HOSTS


def _has_valid_session(headers: Headers) -> bool:
    token = cookie_parser(headers.get("cookie", "")).get(settings.SESSION_COOKIE)
    if not token:
        return False
    try:
        jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return False
    return True


def _large_body_without_session(headers: Headers) -> bool:
    """Refused from the headers alone, so a stranger cannot fill the disk with uploads.
    A signature check only: the route still does the full check."""
    length = headers.get("content-length")
    if length is None:
        large = "chunked" in headers.get("transfer-encoding", "").lower()
    else:
        try:
            large = int(length) > MAX_BODY_WITHOUT_SESSION
        except ValueError:
            large = True
    return large and not _has_valid_session(headers)


class SecurityHeadersMiddleware:
    """Adds the security headers to every response, refuses requests for unknown host
    names, cross-site writes, and large bodies from anyone not signed in.

    Tag every reply with X-SM-Origin: the browser trusts an error's "detail" only when
    this is present (frontend/src/utils/errors.ts).
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        https = scope.get("scheme") == "https"
        path = scope.get("path", "")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                _apply_headers(message, https, path)
            await send(message)

        headers = Headers(scope=scope)
        if not host_allowed(headers):
            logger.warning(f"Refused {scope['method']} {path}: not a loopback host name")
            await _refuse(send_with_headers, 421, UNKNOWN_HOST_DETAIL)
            return

        if scope["method"] in UNSAFE_METHODS:
            origin = headers.get("origin")
            if origin and not origin_allowed(origin, headers):
                logger.warning(f"Refused {scope['method']} {path}: cross-site Origin")
                await _refuse(send_with_headers, 403, CROSS_SITE_DETAIL)
                return
            if _large_body_without_session(headers):
                logger.warning(f"Refused {scope['method']} {path}: large body without a session")
                await _refuse(send_with_headers, 401, SIGN_IN_TO_UPLOAD_DETAIL)
                return

        await self.app(scope, receive, send_with_headers)


def _apply_headers(message: Message, https: bool, path: str) -> None:
    headers = list(message.get("headers", []))
    present = {name.lower() for name, _ in headers}

    def add(name: str, value: str, *, replace: bool = False) -> None:
        key = name.lower().encode("latin-1")
        if replace or key not in present:
            headers.append((key, value.encode("latin-1")))
            present.add(key)

    add("x-sm-origin", "app")
    add("x-content-type-options", "nosniff")
    add("x-frame-options", "SAMEORIGIN")
    add("referrer-policy", "strict-origin-when-cross-origin")
    add("permissions-policy", PERMISSIONS_POLICY)
    add("cross-origin-opener-policy", "same-origin")
    add("cross-origin-resource-policy", "same-origin")
    # /static sets its own sandbox policy on SVG and HTML-ish files, which must win.
    add("content-security-policy", content_security_policy(https))
    if https:
        add("strict-transport-security", HSTS_VALUE)
    if path == "/api" or path.startswith("/api/"):
        add("cache-control", API_CACHE_CONTROL)
    message["headers"] = headers


async def _refuse(send: Send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii"))],
    })
    await send({"type": "http.response.body", "body": body})
