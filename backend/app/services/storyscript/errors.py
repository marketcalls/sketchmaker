"""Errors raised by the script engine.

Routers map these to HTTP responses: ``LLMNotConfigured`` is a 503 (an
operator has to set a default provider and model), ``InvalidLLMOutput`` is a
502 (the model did not produce a valid script after the retries),
``StoryScriptInputError`` is a 400 or 422, and ``NotImplementedYet`` is a 501.
"""


class StoryScriptError(Exception):
    """Base class for every script engine error."""


class StoryScriptInputError(StoryScriptError, ValueError):
    """The caller passed something the engine cannot work with."""


class LLMNotConfigured(StoryScriptError):
    """No default LLM provider or model is configured in APISettings."""


class InvalidLLMOutput(StoryScriptError):
    """The LLM did not return valid JSON for the schema after every retry."""

    def __init__(self, message: str, attempts: int = 0, last_error: str = ""):
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error


class NotImplementedYet(StoryScriptError, NotImplementedError):
    """The function exists for its signature but is not built yet."""


class LLMCallFailed(StoryScriptError):
    """The provider call itself failed (network, auth, rate limit, outage)."""
