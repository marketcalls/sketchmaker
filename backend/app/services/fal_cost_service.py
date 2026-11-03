"""fal's live model prices, for the Usage page.

Nothing here decides what anything costs: app/services/pricing.py does. This shows
what fal's pricing API says today so the two can be compared. One model per request,
cached for an hour, because fal rate limits the pricing API.
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

FAL_API_BASE = "https://api.fal.ai/v1"
CACHE_SECONDS = 3600

_cache: dict[str, tuple[float, dict]] = {}

# Display name by endpoint, grouped as the Usage page shows them.
MODEL_CATEGORIES: dict[str, dict[str, str]] = {
    "Image Generation": {
        "openai/gpt-image-2.5/sunburst/text-to-image": "GPT Image 2.5",
        "blackforestlabs/flux-3/text-to-image": "Flux 3",
        "blackforestlabs/flux-3/klein/text-to-image": "Flux 3 Klein",
        "google/nano-banana-2.1": "Nano Banana 2.1",
        "ideogram/v4.5": "Ideogram V4.5",
        "microsoft/mai-image-2.5": "MAI Image 2.5",
        "xai/grok-imagine-image/v2.0/text-to-image": "Grok Imagine 2.0",
        "fal-ai/z-image/turbo/lora": "Z-Image Turbo",
        "bytedance/seedream/v5/pro/text-to-image": "Seedream V5 Pro",
    },
    "Image Editing": {
        "google/nano-banana-2.1/edit": "Nano Banana 2.1 Edit (Magix & Virtual)",
        "openai/gpt-image-2.5/sunburst/edit": "GPT Image 2.5 Edit (Magix & Virtual)",
        "blackforestlabs/flux-3/edit-image": "Flux 3 Edit (Magix & Virtual)",
        "xai/grok-imagine-image/v2.0/edit": "Grok Imagine 2.0 Edit (Magix & Virtual)",
        "ideogram/v4.5/edit": "Ideogram V4.5 Edit (Magix & Virtual)",
        "fal-ai/bria/background/remove": "Background Removal",
    },
    "Logo": {
        "ideogram/vector/text-to-vector": "Ideogram Vector Text-to-Vector (Logo)",
        "ideogram/vector/image-to-vector": "Ideogram Vector Image-to-Vector (Logo)",
    },
    "Video Generation": {
        "fal-ai/kling-video/v3/standard/motion-control": "Kling V3 Standard (Motion)",
        "fal-ai/kling-video/v3/pro/motion-control": "Kling V3 Pro (Motion)",
        "fal-ai/kling-video/v2.6/standard/motion-control": "Kling Video v2.6 (Motion)",
        "minimax/h3-max/recast": "MiniMax H3 Max Recast (Motion Control, multi-character)",
        "minimax/h3-max/lip-sync/image-to-video": "MiniMax H3 Max Lip Sync",
        "minimax/h3-max/text-to-video": "MiniMax H3 Max Text-to-Video (Stories)",
        "minimax/h3-max/image-to-video": "MiniMax H3 Max Image-to-Video (Stories)",
        "minimax/h3-max/reference-to-video": "MiniMax H3 Max Reference-to-Video (Stories)",
        "bytedance/seedance-2.5/us/text-to-video": "Seedance 2.5 Text-to-Video (Stories)",
        "bytedance/seedance-2.5/us/image-to-video": "Seedance 2.5 Image-to-Video (Stories)",
        "bytedance/seedance-2.5/us/reference-to-video": "Seedance 2.5 Reference-to-Video (Stories)",
        "kling/v4/text-to-video": "Kling v4 Text-to-Video (Stories)",
        "kling/v4/image-to-video": "Kling v4 Image-to-Video (Stories)",
        "kling/v4/reference-to-video": "Kling v4 Reference-to-Video (Stories)",
        "blackforestlabs/flux-3-max/text-to-video": "FLUX 3 Max Text-to-Video (Stories)",
        "blackforestlabs/flux-3-max/image-to-video": "FLUX 3 Max Image-to-Video (Stories)",
        "blackforestlabs/flux-3-max/keyframes-to-video": "FLUX 3 Max Keyframes-to-Video (Stories)",
        "google/gemini-omni-flash/v1.1/text-to-video": "Gemini Omni Flash 1.1 Text-to-Video (Stories)",
        "google/gemini-omni-flash/v1.1/image-to-video": "Gemini Omni Flash 1.1 Image-to-Video (Stories)",
        "google/gemini-omni-flash/v1.1/reference-to-video": "Gemini Omni Flash 1.1 Reference-to-Video (Stories)",
    },
    "Utilities": {
        "fal-ai/workflow-utilities/auto-subtitle": "Auto Subtitles",
    },
    "Audio": {
        "elevenlabs/tts/eleven-v4": "Eleven v4 Voice (Faceless, Motion Graphics)",
        "fal-ai/elevenlabs/music": "ElevenLabs Music (Faceless, Motion Graphics)",
    },
}

MODEL_DISPLAY_NAMES = {
    endpoint: name for models in MODEL_CATEGORIES.values() for endpoint, name in models.items()
}


def get_available_models() -> dict:
    """Models the Usage page can price, with their categories."""
    return {
        "models": [
            {"endpoint_id": endpoint, "display_name": name, "category": category}
            for category, models in MODEL_CATEGORIES.items()
            for endpoint, name in models.items()
        ],
        "total_models": len(MODEL_DISPLAY_NAMES),
    }


def _price_row(model_id: str, *, unit_price=None, unit="unknown", currency="USD", error: str | None = None) -> dict:
    row = {
        "endpoint_id": model_id,
        "display_name": MODEL_DISPLAY_NAMES.get(model_id, model_id),
        "unit_price": unit_price,
        "unit": unit,
        "currency": currency,
    }
    if error:
        row["error"] = error
    return row


async def fetch_single_model_pricing(api_key: str | None, model_id: str) -> dict:
    """fal's current price for one endpoint. Failures come back in ``error`` as a
    sentence for people; only successful answers are cached."""
    if model_id not in MODEL_DISPLAY_NAMES:
        return _price_row(model_id, error="This model is not in the supported list.")
    if not api_key:
        return _price_row(model_id, error="Add a fal API key to see live prices.")

    cached = _cache.get(model_id)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{FAL_API_BASE}/models/pricing",
                params={"endpoint_id": model_id},
                headers={"Authorization": f"Key {api_key}"},
            )
    except httpx.HTTPError as exc:
        logger.warning(f"Could not read fal's price for {model_id}: {type(exc).__name__}")
        return _price_row(model_id, error="Could not reach fal. Please try again.")

    if response.status_code == 429:
        return _price_row(model_id, error="fal is rate limiting price lookups. Please try again shortly.")
    if response.status_code != 200:
        logger.warning(f"fal's pricing API answered {response.status_code} for {model_id}")
        return _price_row(model_id, error="fal did not return a price. Please try again.")

    prices = response.json().get("prices") or []
    if not prices:
        return _price_row(model_id, error="fal has no price listed for this model.")
    price = prices[0]
    row = _price_row(
        model_id,
        unit_price=price.get("unit_price", 0),
        unit=price.get("unit", "unknown"),
        currency=price.get("currency", "USD"),
    )
    _cache[model_id] = (time.monotonic(), row)
    return row
