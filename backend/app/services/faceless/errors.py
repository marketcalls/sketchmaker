"""Errors raised by the Faceless services; the JSON handler in app/main.py renders them."""


class FacelessError(Exception):
    status_code = 400

    def __init__(self, message: str, *, code: str | None = None, extra: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.extra = extra or {}


class InvalidRequest(FacelessError):
    status_code = 400


class Blocked(FacelessError):
    """Consent, safety or compliance blocks the generation."""

    status_code = 403


class NotFound(FacelessError):
    status_code = 404


class Conflict(FacelessError):
    status_code = 409


class RateLimited(FacelessError):
    status_code = 429


class Unavailable(FacelessError):
    status_code = 503


class UpstreamError(FacelessError):
    """The LLM or a provider returned something unusable."""

    status_code = 502


class NotReady(FacelessError):
    """A dependency (script engine, render engine) is not built yet."""

    status_code = 501
