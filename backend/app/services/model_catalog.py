"""What each language model provider offers right now, behind Refresh models in Settings.

Addresses are constants, never read from the database, so a stored key can only go to
its own provider. Keys travel in headers, not URLs, and redirects are not followed, so a
key cannot end up in a log or on another host. Whatever a provider returns is treated as
untrusted input: names are checked against a strict pattern and text is cut to length.

Nothing here writes to the database, and nothing is added without the owner choosing it.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Callable

import httpx

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_KEY_REJECTED = "key_rejected"
STATUS_UNAVAILABLE = "unavailable"

TIMEOUT = httpx.Timeout(20.0, connect=8.0)
# Models this new are ticked for the owner. Older ones are listed, but left unticked.
RECENT_DAYS = 120
# Per provider. OpenRouter alone lists hundreds, and only the newest are worth reading.
MAX_NEW_MODELS = 60
MAX_DESCRIPTION = 300
MAX_DISPLAY_NAME = 150

_VALID_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,99}$")
_DATED_SNAPSHOT = re.compile(r"-\d{4}-\d{2}-\d{2}$")
# Lists also carry models that cannot answer a chat request.
_NOT_CHAT = re.compile(
    r"embed|whisper|tts|transcri|speech|audio|realtime|moderation|guard|image|imagine|imagen|dall-e|sora|video|veo"
    r"|rerank|ocr|aqa|robotics|nano-banana|lyria|computer-use|live|search|orpheus",
    re.IGNORECASE,
)


def valid_model_name(name: str) -> bool:
    return bool(_VALID_NAME.match(name))


@dataclass(frozen=True)
class OfferedModel:
    name: str
    display_name: str
    description: str | None = None
    context_window: int | None = None
    released: datetime | None = None

    @property
    def recommended(self) -> bool:
        return self.released is not None and self.released > datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "context_window": self.context_window,
            "released": self.released.date().isoformat() if self.released else None,
            "recommended": self.recommended,
        }


@dataclass
class ProviderOffer:
    status: str
    # Every name the provider listed, chat or not, so a model is only ever reported as
    # gone when the provider truly no longer lists it.
    listed: set[str] = field(default_factory=set)
    models: list[OfferedModel] = field(default_factory=list)


def _pretty_name(name: str) -> str:
    """gpt-6.1-sol becomes GPT-6.1 Sol. Only for providers that do not supply a name."""
    words = name.rsplit("/", 1)[-1].replace("_", "-").split("-")
    pretty: list[str] = []
    for word in words:
        if pretty and pretty[-1] in ("GPT", "GLM") and word[:1].isdigit():
            pretty[-1] = f"{pretty[-1]}-{word}"
        elif word.lower() in ("gpt", "glm", "oss"):
            pretty.append(word.upper())
        else:
            pretty.append(word.capitalize())
    return " ".join(pretty)


def _context(value) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _text(value, limit: int) -> str | None:
    return value.strip()[:limit] or None if isinstance(value, str) else None


def _from_timestamp(value) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _from_iso(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _build(name: str, display=None, description=None, context=None, released=None) -> OfferedModel:
    return OfferedModel(
        name=name,
        display_name=_text(display, MAX_DISPLAY_NAME) or _pretty_name(name),
        description=_text(description, MAX_DESCRIPTION),
        context_window=_context(context),
        released=released,
    )


def _rows(payload, key: str = "data") -> list[dict]:
    rows = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Unexpected model list")
    return [row for row in rows if isinstance(row, dict)]


def _openai_style(payload) -> tuple[set[str], list[OfferedModel]]:
    """OpenAI, Groq, xAI, Cerebras and Baseten: {"data": [{"id", "created", ...}]}."""
    listed, models = set(), []
    for row in _rows(payload):
        name = row.get("id")
        if not isinstance(name, str):
            continue
        listed.add(name)
        # A model already announced for shutdown is not worth adding.
        if row.get("shutdown_date") or row.get("active") is False:
            continue
        models.append(_build(name, context=row.get("context_window"), released=_from_timestamp(row.get("created"))))
    return listed, models


def _anthropic(payload) -> tuple[set[str], list[OfferedModel]]:
    listed, models = set(), []
    for row in _rows(payload):
        name = row.get("id")
        if not isinstance(name, str):
            continue
        listed.add(name)
        models.append(_build(name, row.get("display_name"), context=row.get("max_input_tokens"),
                             released=_from_iso(row.get("created_at"))))
    return listed, models


def _gemini(payload) -> tuple[set[str], list[OfferedModel]]:
    listed, models = set(), []
    for row in _rows(payload, "models"):
        raw = row.get("name")
        if not isinstance(raw, str):
            continue
        name = raw.removeprefix("models/")
        listed.add(name)
        methods = row.get("supportedGenerationMethods")
        if isinstance(methods, list) and "generateContent" in methods:
            models.append(_build(name, row.get("displayName"), row.get("description"), row.get("inputTokenLimit")))
    return listed, models


def _openrouter(payload) -> tuple[set[str], list[OfferedModel]]:
    listed, models = set(), []
    for row in _rows(payload):
        name = row.get("id")
        if not isinstance(name, str):
            continue
        listed.add(name)
        outputs = (row.get("architecture") or {}).get("output_modalities") or ["text"]
        # :free and :batch are variants of a model already on the list.
        if "text" not in outputs or row.get("expiration_date") or ":" in name:
            continue
        models.append(_build(name, row.get("name"), row.get("description"), row.get("context_length"),
                             _from_timestamp(row.get("created"))))
    return listed, models


def _keep_openai(name: str) -> bool:
    """Only chat families, and only the moving name, not each dated snapshot of it."""
    return (name.startswith(("gpt-", "o1", "o3", "o4", "chat-latest"))
            and "codex" not in name and "instruct" not in name and not _DATED_SNAPSHOT.search(name))


def _bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


@dataclass(frozen=True)
class _Source:
    url: str
    headers: Callable[[str], dict[str, str]]
    parse: Callable
    keep: Callable[[str], bool] = lambda _name: True


SOURCES: dict[str, _Source] = {
    "OpenAI": _Source("https://api.openai.com/v1/models", _bearer, _openai_style, _keep_openai),
    "Anthropic": _Source("https://api.anthropic.com/v1/models?limit=1000",
                         lambda key: {"x-api-key": key, "anthropic-version": "2023-06-01"}, _anthropic),
    "Google Gemini": _Source("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
                             lambda key: {"x-goog-api-key": key}, _gemini),
    "Groq": _Source("https://api.groq.com/openai/v1/models", _bearer, _openai_style),
    "xAI": _Source("https://api.x.ai/v1/models", _bearer, _openai_style),
    "Cerebras": _Source("https://api.cerebras.ai/v1/models", _bearer, _openai_style),
    "OpenRouter": _Source("https://openrouter.ai/api/v1/models", _bearer, _openrouter),
    "Baseten": _Source("https://inference.baseten.co/v1/models", _bearer, _openai_style),
}


def _sort_key(model: OfferedModel) -> tuple:
    return (model.released or datetime.min.replace(tzinfo=timezone.utc), model.name)


def fetch_offer(provider: str, key: str) -> ProviderOffer:
    """One provider's list. Never raises, and never lets a provider's own words or the key
    near a message: the caller gets a status."""
    source = SOURCES[provider]
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=False) as client:
            response = client.get(source.url, headers=source.headers(key))
    except httpx.HTTPError as exc:
        logger.warning(f"Model list from {provider} failed: {type(exc).__name__}")
        return ProviderOffer(STATUS_UNAVAILABLE)

    # A plain GET has nothing else wrong with it: Gemini and xAI answer a bad key with 400.
    if response.status_code in (400, 401, 403):
        logger.warning(f"Model list from {provider}: the key was rejected (HTTP {response.status_code})")
        return ProviderOffer(STATUS_KEY_REJECTED)
    if response.status_code != 200:
        logger.warning(f"Model list from {provider} failed: HTTP {response.status_code}")
        return ProviderOffer(STATUS_UNAVAILABLE)

    try:
        listed, models = source.parse(response.json())
    except ValueError:
        logger.warning(f"Model list from {provider} was not in the expected form")
        return ProviderOffer(STATUS_UNAVAILABLE)

    usable = [m for m in models if valid_model_name(m.name) and not _NOT_CHAT.search(m.name) and source.keep(m.name)]
    usable.sort(key=_sort_key, reverse=True)
    return ProviderOffer(STATUS_OK, listed=listed, models=usable)


def fetch_offers(keys: dict[str, str]) -> dict[str, ProviderOffer]:
    """Every provider with a key, side by side, so one slow provider does not hold up the
    rest. Call it from a plain def route: it blocks."""
    providers = [name for name in keys if name in SOURCES]
    if not providers:
        return {}
    with ThreadPoolExecutor(max_workers=len(providers)) as pool:
        offers = pool.map(lambda name: fetch_offer(name, keys[name]), providers)
        return dict(zip(providers, offers))


def new_models_for(offer: ProviderOffer, known: set[str]) -> list[OfferedModel]:
    return [m for m in offer.models if m.name not in known][:MAX_NEW_MODELS]
