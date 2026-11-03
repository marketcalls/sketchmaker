"""LLM access for the script engine.

Text calls go through ``app.clients.litellm_client.generate_completion`` with
the APISettings default provider and model, exactly like the Stories enhancer
and Magix. That keeps the configured fallback model, the provider endpoint
handling and token usage accounting in one place. Nothing here reads a key or
names a model.

Vision calls (character descriptions) need image content blocks, which
generate_completion cannot send, so they call ``litellm.acompletion`` with the
same helpers (key, prefix, endpoint, temperature rules, usage recording).
Images are downloaded through ``app.services.url_fetch`` and sent inline, so
no provider is asked to fetch a URL on our behalf.

Structured output: the JSON schema of the expected pydantic model is put in
the prompt, the reply is parsed and validated, and on failure the call is
retried (up to ``max_retries`` times) with the validation error fed back.
After that ``InvalidLLMOutput`` is raised.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from .errors import InvalidLLMOutput, LLMCallFailed, LLMNotConfigured, StoryScriptError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_MAX_TOKENS = 8192
MAX_RETRIES = 2


@dataclass(frozen=True)
class ModelChoice:
    provider: str
    model: str
    supports_vision: bool = False

    @property
    def label(self) -> str:
        return f"{self.provider}/{self.model}"


def resolve_model(db) -> ModelChoice:
    """The APISettings default provider and model, as the Stories router reads them."""
    from app.models.api import AIModel, APIProvider, APISettings

    settings = db.query(APISettings).first()
    if not settings or not settings.default_provider_id or not settings.default_model_id:
        raise LLMNotConfigured("No default LLM provider and model are configured")
    provider = db.query(APIProvider).filter(APIProvider.id == settings.default_provider_id).first()
    model = db.query(AIModel).filter(AIModel.id == settings.default_model_id).first()
    if not provider or not model:
        raise LLMNotConfigured("The default LLM provider or model no longer exists")
    return ModelChoice(provider=provider.name, model=model.name,
                       supports_vision=_model_supports_vision(provider.name, model))


def _model_supports_vision(provider_name: str, model_row) -> bool:
    caps = getattr(model_row, "capabilities", None) or {}
    if isinstance(caps, dict):
        for key in ("vision", "image_input", "images", "multimodal"):
            if key in caps:
                return bool(caps[key])
    try:
        import litellm
        from app.clients.litellm_client import get_model_prefix

        return bool(litellm.supports_vision(model=f"{get_model_prefix(provider_name)}{model_row.name}"))
    except Exception:
        return False


async def _call_text(db, choice: ModelChoice, *, system: str, prompt: str, max_tokens: int,
                     temperature: float, feature: str, user_id: int | None) -> str:
    from app.clients.litellm_client import generate_completion

    return await generate_completion(
        prompt=prompt,
        model_name=choice.model,
        provider_name=choice.provider,
        db=db,
        max_tokens=max_tokens,
        temperature=temperature,
        system_prompt=system,
        feature=feature,
        user_id=user_id,
    )


async def _call_vision(db, choice: ModelChoice, *, system: str, prompt: str, images: list[str],
                       max_tokens: int, temperature: float, feature: str,
                       user_id: int | None) -> str:
    """One multimodal call on the default model (no fallback: it may lack vision)."""
    import litellm
    from app.clients.litellm_client import (
        get_model_prefix, get_provider_api_key, get_provider_base_url,
        is_reasoning_model, record_token_usage, supports_temperature,
    )

    api_key = get_provider_api_key(choice.provider, db)
    if not api_key:
        raise LLMNotConfigured(f"API key not configured for {choice.provider}")
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for url in images:
        content.append({"type": "image_url", "image_url": {"url": url}})
    kwargs: dict[str, Any] = {
        "model": f"{get_model_prefix(choice.provider)}{choice.model}",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "api_key": api_key,
    }
    base_url = get_provider_base_url(choice.provider, db)
    if base_url:
        kwargs["api_base"] = base_url
    if is_reasoning_model(choice.model):
        if choice.provider in ("OpenAI", "Groq", "Cerebras"):
            kwargs["reasoning_effort"] = "medium"
    elif supports_temperature(choice.model):
        kwargs["temperature"] = temperature
    response = await litellm.acompletion(**kwargs)
    record_token_usage(db, response, choice.provider, choice.model, feature, user_id)
    return response.choices[0].message.content


# --------------------------------------------------------------------------
# JSON parsing and the retry loop
# --------------------------------------------------------------------------

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def extract_json(raw: str) -> Any:
    """Parse the first JSON object in a reply (tolerates code fences and chatter)."""
    if raw is None:
        raise ValueError("Empty reply")
    text = raw.strip()
    m = _FENCE.search(text)
    if m:
        text = m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in the reply")
    return json.loads(text[start:end + 1])


def schema_text(model: type[BaseModel]) -> str:
    return json.dumps(model.model_json_schema(), separators=(",", ":"))


def _short_errors(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = []
        for e in exc.errors()[:12]:
            loc = ".".join(str(x) for x in e.get("loc", ()))
            parts.append(f"{loc}: {e.get('msg')}")
        return "; ".join(parts)
    return str(exc)[:800]


async def complete_json(
    db,
    *,
    system: str,
    prompt: str,
    schema: type[T],
    feature: str,
    validate: Callable[[T], list[str]] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.7,
    max_retries: int = MAX_RETRIES,
    user_id: int | None = None,
    choice: ModelChoice | None = None,
    images: list[str] | None = None,
) -> tuple[T, ModelChoice]:
    """Call the default model and return a validated ``schema`` instance.

    ``validate`` may return semantic problems (wrong scene count and so on);
    they count as invalid output and are fed back like a schema error.
    """
    choice = choice or resolve_model(db)
    full_system = (
        system.rstrip()
        + "\n\nReply with one JSON object only, no prose and no code fences. "
        "It must validate against this JSON schema:\n" + schema_text(schema)
    )
    attempt_prompt = prompt
    last_error = ""
    attempts = 0
    for attempt in range(max_retries + 1):
        attempts = attempt + 1
        try:
            if images:
                raw = await _call_vision(db, choice, system=full_system, prompt=attempt_prompt,
                                         images=images, max_tokens=max_tokens,
                                         temperature=temperature, feature=feature, user_id=user_id)
            else:
                raw = await _call_text(db, choice, system=full_system, prompt=attempt_prompt,
                                       max_tokens=max_tokens, temperature=temperature,
                                       feature=feature, user_id=user_id)
        except StoryScriptError:
            raise
        except ValueError as exc:
            # generate_completion raises ValueError for a missing key or settings row.
            raise LLMNotConfigured(str(exc)) from exc
        except Exception as exc:
            raise LLMCallFailed(f"LLM call failed on {choice.label}: {type(exc).__name__}") from exc
        try:
            data = extract_json(raw)
            obj = schema.model_validate(data)
            problems = validate(obj) if validate else []
            if problems:
                raise ValueError("; ".join(problems[:12]))
            return obj, choice
        except (ValueError, ValidationError, json.JSONDecodeError) as exc:
            last_error = _short_errors(exc)
            logger.warning(f"storyscript {feature}: invalid LLM output on attempt {attempts}: {last_error[:300]}")
            attempt_prompt = (
                prompt
                + "\n\nYOUR PREVIOUS REPLY WAS REJECTED. Fix these problems and reply again "
                "with the complete JSON object only:\n" + last_error
            )
    raise InvalidLLMOutput(
        f"The model did not return a valid {schema.__name__} after {attempts} attempts",
        attempts=attempts, last_error=last_error,
    )


# --------------------------------------------------------------------------
# Images for vision calls
# --------------------------------------------------------------------------

async def load_images_as_data_urls(urls: list[str], *, max_images: int = 4,
                                   max_side: int = 1024) -> list[str]:
    """Download (through url_fetch) and downscale images to JPEG data URLs.

    ``data:`` URLs are passed through. Unreadable images are skipped.
    """
    out: list[str] = []
    for url in (urls or [])[:max_images]:
        if not isinstance(url, str) or not url:
            continue
        if url.startswith("data:image/"):
            out.append(url)
            continue
        try:
            from app.services.url_fetch import afetch_bytes

            blob = await afetch_bytes(url, max_bytes=20 * 1024 * 1024, timeout=30.0)
            out.append(_to_jpeg_data_url(blob, max_side))
        except Exception as exc:
            logger.warning(f"storyscript: could not load reference image: {type(exc).__name__}")
    return out


def _to_jpeg_data_url(blob: bytes, max_side: int) -> str:
    from PIL import Image

    with Image.open(io.BytesIO(blob)) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


