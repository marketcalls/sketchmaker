"""Middleware and error handlers every app instance needs.

Separate from main.py so the tests can compose an app from a few routers with the
same behaviour.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.middleware.rate_limiter import ApiRateLimitMiddleware, limiter, rate_limit_exceeded_handler
from app.middleware.security import SecurityHeadersMiddleware

logger = logging.getLogger(__name__)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Log field names only, and drop "input" so a submitted password is not echoed."""
    fields = [e.get("loc", [])[-1] for e in exc.errors() if e.get("loc")]
    logger.warning(f"Validation error on {request.url.path}: fields={fields}")
    errors = [{k: v for k, v in e.items() if k != "input"} for e in exc.errors()]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": jsonable_encoder(errors)},
    )


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """A catch-all handler runs outside the middleware stack, so this reply has to
    carry X-SM-Origin itself or the browser would treat it as a proxy error."""
    logger.error(f"Unexpected error on {request.url.path}: {type(exc).__name__}", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred"},
        headers={"X-SM-Origin": "app"},
    )


def install_foundation(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unexpected_error)
    # Added last, so it runs first: every refusal below it still gets the headers.
    app.add_middleware(ApiRateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
