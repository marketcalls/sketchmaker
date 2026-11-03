"""Errors raised by the motion graphics services.

They subclass the Faceless error base so the JSON handler in app/main.py renders
them the same way: {"detail", "code", ...extra}.
"""

from app.services.faceless.errors import FacelessError


class MGError(FacelessError):
    status_code = 400


class InvalidRequest(MGError):
    status_code = 400


class NotFound(MGError):
    status_code = 404


class Conflict(MGError):
    status_code = 409


class RateLimited(MGError):
    status_code = 429


class UpstreamError(MGError):
    status_code = 502


class Unavailable(MGError):
    status_code = 503
