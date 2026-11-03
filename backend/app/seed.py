"""Defaults for an empty database: providers, LLM models and the default model choice.

Runs once. It keys on the provider table being empty, so a model the owner deleted is
never added back. The DB stores the bare model id; litellm_client prepends the
provider prefix.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.api import AIModel, APIProvider, APISettings
from app.utils import secret_box

logger = logging.getLogger(__name__)

PROVIDERS = ("OpenAI", "Anthropic", "Google Gemini", "Groq", "xAI", "Cerebras", "OpenRouter", "Baseten", "FAL")
# OpenAI-compatible providers need their endpoint; the rest use the vendor default.
PROVIDER_BASE_URLS = {"Baseten": "https://inference.baseten.co/v1"}

DEFAULT_MODEL = ("Anthropic", "claude-opus-5")
# On a different provider from the default, so one outage does not take out both.
FALLBACK_MODEL = ("Google Gemini", "gemini-3.6-flash")

DEFAULT_MODELS = [
    # OpenAI models
    {"name": "gpt-5.6-sol", "display_name": "GPT-5.6 Sol", "provider": "OpenAI", "description": "Frontier model for complex professional work", "is_latest": True, "sort_order": 1},
    {"name": "gpt-5.6-terra", "display_name": "GPT-5.6 Terra", "provider": "OpenAI", "description": "Balanced capability and cost for everyday work", "is_latest": True, "sort_order": 2},
    {"name": "gpt-5.6-luna", "display_name": "GPT-5.6 Luna", "provider": "OpenAI", "description": "Most cost-efficient of the 5.6 family", "is_latest": True, "sort_order": 3},
    {"name": "gpt-5.5-pro", "display_name": "GPT-5.5 Pro", "provider": "OpenAI", "description": "Enhanced 5.5 for more precise responses", "sort_order": 4},
    {"name": "gpt-5.5", "display_name": "GPT-5.5", "provider": "OpenAI", "description": "Previous frontier model for coding and professional work", "sort_order": 5},
    {"name": "gpt-5.4", "display_name": "GPT-5.4", "provider": "OpenAI", "description": "More affordable 5.4-class model", "sort_order": 6},
    {"name": "gpt-5.4-mini", "display_name": "GPT-5.4 Mini", "provider": "OpenAI", "description": "Strong mini model for coding and computer use", "sort_order": 7},
    {"name": "gpt-5.4-nano", "display_name": "GPT-5.4 Nano", "provider": "OpenAI", "description": "Cheapest 5.4-class model for high-volume tasks", "sort_order": 8},
    # Anthropic models
    {"name": "claude-fable-5", "display_name": "Claude Fable 5", "provider": "Anthropic", "description": "Next-generation intelligence for long-running agents", "context_window": 1000000, "is_latest": True, "sort_order": 1},
    {"name": "claude-opus-5", "display_name": "Claude Opus 5", "provider": "Anthropic", "description": "For complex agentic coding and enterprise work", "context_window": 1000000, "is_latest": True, "sort_order": 2},
    {"name": "claude-sonnet-5", "display_name": "Claude Sonnet 5", "provider": "Anthropic", "description": "Best combination of speed and intelligence", "context_window": 1000000, "is_latest": True, "sort_order": 3},
    {"name": "claude-haiku-4-5-20251001", "display_name": "Claude Haiku 4.5", "provider": "Anthropic", "description": "Fastest model with near-frontier intelligence", "context_window": 200000, "is_latest": True, "sort_order": 4},
    {"name": "claude-opus-4-8", "display_name": "Claude Opus 4.8", "provider": "Anthropic", "description": "Previous Opus generation", "context_window": 1000000, "sort_order": 5},
    {"name": "claude-sonnet-4-6", "display_name": "Claude Sonnet 4.6", "provider": "Anthropic", "description": "Previous Sonnet generation", "context_window": 1000000, "sort_order": 6},
    # Google Gemini models
    {"name": "gemini-3.6-flash", "display_name": "Gemini 3.6 Flash", "provider": "Google Gemini", "description": "Strong agentic and multimodal performance at lower cost", "context_window": 1000000, "is_latest": True, "sort_order": 1},
    {"name": "gemini-3.5-flash", "display_name": "Gemini 3.5 Flash", "provider": "Google Gemini", "description": "Fast general-purpose Gemini 3.5", "context_window": 1000000, "is_latest": True, "sort_order": 2},
    {"name": "gemini-3.5-flash-lite", "display_name": "Gemini 3.5 Flash Lite", "provider": "Google Gemini", "description": "Fastest, lowest-cost model in the 3.5 family", "context_window": 1000000, "is_latest": True, "sort_order": 3},
    {"name": "gemini-3.1-pro-preview", "display_name": "Gemini 3.1 Pro (Preview)", "provider": "Google Gemini", "description": "Latest Pro iteration, preview", "context_window": 1000000, "sort_order": 4},
    {"name": "gemini-3.1-flash-lite", "display_name": "Gemini 3.1 Flash Lite", "provider": "Google Gemini", "description": "High-throughput low-cost model", "context_window": 1000000, "sort_order": 5},
    # Groq models
    {"name": "groq/compound", "display_name": "Compound (Groq)", "provider": "Groq", "description": "Agentic system with web search and code execution", "context_window": 131072, "is_latest": True, "sort_order": 1},
    {"name": "groq/compound-mini", "display_name": "Compound Mini (Groq)", "provider": "Groq", "description": "Lighter agentic system", "context_window": 131072, "is_latest": True, "sort_order": 2},
    {"name": "openai/gpt-oss-120b", "display_name": "GPT-OSS 120B (Groq)", "provider": "Groq", "description": "OpenAI open-weight 120B on Groq", "context_window": 131072, "sort_order": 3},
    {"name": "openai/gpt-oss-20b", "display_name": "GPT-OSS 20B (Groq)", "provider": "Groq", "description": "OpenAI open-weight 20B on Groq", "context_window": 131072, "sort_order": 4},
    {"name": "llama-3.3-70b-versatile", "display_name": "Llama 3.3 70B Versatile", "provider": "Groq", "description": "Meta Llama for versatile tasks", "context_window": 131072, "sort_order": 5},
    {"name": "llama-3.1-8b-instant", "display_name": "Llama 3.1 8B Instant", "provider": "Groq", "description": "Fast 8B model for instant responses", "context_window": 131072, "sort_order": 6},
    # xAI models
    {"name": "grok-4.5", "display_name": "Grok 4.5", "provider": "xAI", "description": "xAI's most intelligent and fastest model", "context_window": 500000, "is_latest": True, "sort_order": 1},
    {"name": "grok-4.3", "display_name": "Grok 4.3", "provider": "xAI", "description": "Previous flagship with 1M context", "context_window": 1000000, "sort_order": 2},
    {"name": "grok-4.20-0309-reasoning", "display_name": "Grok 4.20 Reasoning", "provider": "xAI", "description": "Reasoning variant with 1M context", "context_window": 1000000, "sort_order": 3},
    # Cerebras models
    {"name": "zai-glm-4.7", "display_name": "ZAI GLM 4.7", "provider": "Cerebras", "description": "Strong coding and agentic performance (deprecates 2026-08-17)", "is_latest": True, "sort_order": 1},
    {"name": "gemma-4-31b", "display_name": "Gemma 4 31B", "provider": "Cerebras", "description": "Fast 31B preview model", "is_latest": True, "sort_order": 2},
    {"name": "gpt-oss-120b", "display_name": "GPT-OSS 120B (Cerebras)", "provider": "Cerebras", "description": "OpenAI open-weight 120B, production", "is_latest": True, "sort_order": 3},
    # OpenRouter models
    {"name": "openai/gpt-5.6-sol", "display_name": "GPT-5.6 Sol (OpenRouter)", "provider": "OpenRouter", "description": "OpenAI flagship via OpenRouter", "is_latest": True, "sort_order": 1},
    {"name": "anthropic/claude-opus-5", "display_name": "Claude Opus 5 (OpenRouter)", "provider": "OpenRouter", "description": "Anthropic Opus 5 via OpenRouter", "is_latest": True, "sort_order": 2},
    {"name": "google/gemini-3.6-flash", "display_name": "Gemini 3.6 Flash (OpenRouter)", "provider": "OpenRouter", "description": "Google Gemini via OpenRouter", "is_latest": True, "sort_order": 3},
    {"name": "x-ai/grok-4.5", "display_name": "Grok 4.5 (OpenRouter)", "provider": "OpenRouter", "description": "xAI Grok via OpenRouter", "is_latest": True, "sort_order": 4},
    # Baseten Model APIs — OpenAI-compatible, served at inference.baseten.co.
    # Slugs taken from Baseten's own model-apis docs on 2026-07-27.
    {"name": "moonshotai/Kimi-K3", "display_name": "Kimi K3 (Baseten)", "provider": "Baseten", "description": "Moonshot Kimi K3", "is_latest": True, "sort_order": 1},
    {"name": "zai-org/GLM-5.2", "display_name": "GLM 5.2 (Baseten)", "provider": "Baseten", "description": "Z.ai GLM 5.2", "is_latest": True, "sort_order": 2},
    {"name": "zai-org/GLM-5.2-Fast", "display_name": "GLM 5.2 Fast (Baseten)", "provider": "Baseten", "description": "Lower-latency GLM 5.2", "is_latest": True, "sort_order": 3},
    {"name": "moonshotai/Kimi-K2.7-Code", "display_name": "Kimi K2.7 Code (Baseten)", "provider": "Baseten", "description": "Kimi tuned for code", "sort_order": 4},
    {"name": "moonshotai/Kimi-K2.6", "display_name": "Kimi K2.6 (Baseten)", "provider": "Baseten", "description": "Previous Kimi generation", "sort_order": 5},
    {"name": "zai-org/GLM-4.7", "display_name": "GLM 4.7 (Baseten)", "provider": "Baseten", "description": "Previous GLM generation", "sort_order": 6},
    {"name": "deepseek-ai/DeepSeek-V4-Pro", "display_name": "DeepSeek V4 Pro (Baseten)", "provider": "Baseten", "description": "DeepSeek V4 Pro", "sort_order": 7},
    {"name": "openai/gpt-oss-120b", "display_name": "GPT-OSS 120B (Baseten)", "provider": "Baseten", "description": "OpenAI open-weight 120B on Baseten", "sort_order": 8},
]


def seed_defaults(db: Session) -> bool:
    """Fill an empty database and commit. Returns whether anything was seeded."""
    if db.query(APIProvider.id).first() is not None:
        return False

    providers = {}
    for name in PROVIDERS:
        providers[name] = APIProvider(name=name, is_active=True, base_url=PROVIDER_BASE_URLS.get(name))
        db.add(providers[name])
    db.flush()

    models = {}
    for row in DEFAULT_MODELS:
        model = AIModel(
            name=row["name"],
            display_name=row["display_name"],
            description=row.get("description"),
            provider_id=providers[row["provider"]].id,
            context_window=row.get("context_window"),
            is_latest=row.get("is_latest", False),
            sort_order=row.get("sort_order", 0),
            is_active=True,
        )
        db.add(model)
        models[(row["provider"], row["name"])] = model
    db.flush()

    default, fallback = models[DEFAULT_MODEL], models[FALLBACK_MODEL]
    db.add(APISettings(
        secrets_canary=secret_box.make_canary(),
        default_provider_id=default.provider_id,
        default_model_id=default.id,
        fallback_provider_id=fallback.provider_id,
        fallback_model_id=fallback.id,
    ))
    db.commit()
    logger.info(f"Seeded {len(PROVIDERS)} providers and {len(DEFAULT_MODELS)} models")
    return True
