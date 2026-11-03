"""FAL client for image and video generation.

Every call uses an SDK client built with the stored key (app/services/fal_keys.py), so
the key never reaches os.environ. Own /static files in fal arguments are uploaded to
fal storage inside fal_submit and fal_subscribe (app/services/fal_inputs.py).
"""

import asyncio
import math
import re
import os
import uuid
import json
from urllib.parse import urlparse
from sqlalchemy.orm import Session
import fal_client
import logging

from app.services.fal_inputs import resolve_fal_inputs
from app.services.fal_keys import get_sync_client
from app.services.pricing import (
    MOTION_CONTROL_DEFAULT_TIER,
    MOTION_CONTROL_KEYS,
    MOTION_CONTROL_MAX_SECONDS,
    RECAST_MAX_REFERENCES,
    SUBTITLES_MINUTE_KEY,
    usd_for,
    video_key,
    video_ref_key,
)
from app.services.storage_service import UnsafeMediaPath, own_media_relpath, safe_static_path
from app.utils.security import scrubbed_env

_logger = logging.getLogger(__name__)


# =============================================================================
# SECURITY: Model whitelist to prevent unauthorized API access
# =============================================================================

ALLOWED_MODELS = {
    # Text-to-image models (/generate)
    "openai/gpt-image-2.5/sunburst/text-to-image",
    "blackforestlabs/flux-3/text-to-image",
    "blackforestlabs/flux-3/klein/text-to-image",
    "google/nano-banana-2.1",
    "ideogram/v4.5",
    "microsoft/mai-image-2.5",
    "xai/grok-imagine-image/v2.0/text-to-image",
    "fal-ai/z-image/turbo/lora",
    "bytedance/seedream/v5/pro/text-to-image",
    # Utility models
    "fal-ai/bria/background/remove",
    "fal-ai/workflow-utilities/auto-subtitle",  # Auto subtitle generation
    # Video models
    "fal-ai/kling-video/v3/standard/motion-control",  # Motion control (default)
    "fal-ai/kling-video/v3/pro/motion-control",  # Motion control (highest quality)
    "fal-ai/kling-video/v2.6/standard/motion-control",  # Motion control (budget)
    "bytedance/seedance-2.5/us/text-to-video",  # Seedance 2.5 Text-to-Video (stories)
    "bytedance/seedance-2.5/us/image-to-video",  # Seedance 2.5 Image-to-Video (stories)
    "bytedance/seedance-2.5/us/reference-to-video",  # Seedance 2.5 Reference-to-Video (stories)
}

def validate_model(model: str) -> bool:
    """Validate that the model is in our allowed list."""
    return model in ALLOWED_MODELS


# =============================================================================
# SECURITY: URL validation to prevent SSRF attacks
# =============================================================================

# Allowed URL schemes
ALLOWED_URL_SCHEMES = {"https", "data"}

# Blocked IP ranges (private networks, localhost, link-local)
BLOCKED_IP_PREFIXES = [
    "10.",
    "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.",
    "172.24.", "172.25.", "172.26.", "172.27.",
    "172.28.", "172.29.", "172.30.", "172.31.",
    "192.168.",
    "127.",
    "0.",
    "169.254.",  # Link-local
    "::1",  # IPv6 localhost
    "fe80:",  # IPv6 link-local
]

# Blocked hostnames
BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata.goog",
    "169.254.169.254",  # AWS/GCP metadata
}

# Allowed domains for external URLs (whitelist approach)
ALLOWED_URL_DOMAINS = {
    "fal.media",
    "fal.ai",
    "storage.googleapis.com",
    "s3.amazonaws.com",
    # Add more trusted domains as needed
}


def _is_own_static_url(url: str) -> bool:
    """A /static/... path of our own that stays inside the media folder."""
    relative = own_media_relpath(url)
    if relative is None:
        return False
    try:
        safe_static_path(relative)
    except UnsafeMediaPath:
        return False
    return True


def validate_url(url: str, allow_data_urls: bool = True) -> tuple[bool, str]:
    """
    Validate URL to prevent SSRF attacks. Accepts https, data: images and this
    app's own /static/... files, which fal_submit uploads to fal storage.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url:
        return False, "URL is empty"

    if url.startswith("/"):
        if _is_own_static_url(url):
            return True, ""
        return False, "Only this app's own /static/ files can be used"

    # Allow base64 data URLs for image uploads
    if url.startswith("data:"):
        if allow_data_urls:
            # Validate it's an image data URL
            if url.startswith(("data:image/jpeg", "data:image/png", "data:image/webp", "data:image/gif")):
                return True, ""
            return False, "Invalid data URL format - must be image type"
        return False, "Data URLs not allowed"

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Failed to parse URL"

    # Check scheme
    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        return False, f"URL scheme '{parsed.scheme}' not allowed"

    # Check for blocked hostnames
    hostname = parsed.hostname or ""
    if hostname.lower() in BLOCKED_HOSTNAMES:
        return False, f"Hostname '{hostname}' is blocked"

    # Check for blocked IP prefixes
    for prefix in BLOCKED_IP_PREFIXES:
        if hostname.startswith(prefix):
            return False, f"IP address '{hostname}' is in a blocked range"

    # Optional: Strict domain whitelist (uncomment for maximum security)
    # domain_allowed = False
    # for allowed_domain in ALLOWED_URL_DOMAINS:
    #     if hostname.endswith(allowed_domain):
    #         domain_allowed = True
    #         break
    # if not domain_allowed:
    #     return False, f"Domain '{hostname}' is not in the allowed list"

    return True, ""


def validate_lora_url(url: str) -> tuple[bool, str]:
    """Validate LoRA weights URL."""
    if not url:
        return True, ""  # LoRA is optional

    # LoRA URLs should be from FAL storage or trusted sources
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # Must be HTTPS
    if parsed.scheme != "https":
        return False, "LoRA URL must use HTTPS"

    # Check against allowed domains
    allowed = False
    for domain in ALLOWED_URL_DOMAINS:
        if hostname.endswith(domain):
            allowed = True
            break

    if not allowed:
        return False, f"LoRA URL domain '{hostname}' is not trusted"

    return True, ""


# =============================================================================
# MODEL CONFIGURATION - Unified interface mapping
# =============================================================================

# Size parameter types used by different models
class SizeParamType:
    ASPECT_RATIO = "aspect_ratio"      # String like "16:9" passed as aspect_ratio, plus
                                        # "resolution" when the config maps it
    IMAGE_SIZE_PRESET = "preset"        # String preset like "landscape_4_3"
    IMAGE_SIZE_DICT = "dict"            # Dict {width, height} in pixels
    DIMS_TABLE = "dims_table"           # Dict {width, height} looked up in the config's
                                        # "sizes" table (models with exact size rules)
    SEEDREAM_DIMS = "seedream"          # Dict {width, height} clamped to Seedream V5's
                                        # constraints (1,048,576-4,194,304 total pixels,
                                        # aspect ratio between 1/16 and 16)


# Model configurations with their size parameter handling.
#   defaults      sent with every request
#   supports      optional request fields the model accepts
#   omit          common fields (seed, num_images) the model rejects
#   max_images    images one request can return (the estimate follows this)
#   resolutions   app resolution -> the model's resolution value (ASPECT_RATIO)
#   aspect_fallback  app aspect ratios the model lacks -> nearest it has
# Schemas: https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<model>
MODEL_CONFIG = {
    # GPT Image 2.5, Sunburst tuning (slower than Flare, holds more detail).
    # Billed by tokens, so quality is pinned: "auto" can cost as much as "max".
    "openai/gpt-image-2.5/sunburst/text-to-image": {
        "size_type": SizeParamType.DIMS_TABLE,
        "sizes": "GPT_IMAGE_25_SIZES",
        "defaults": {
            "quality": "high",
            "output_format": "png",
            "enable_safety_checker": True,
        },
        "supports": [],
        "omit": ["seed"],
    },
    # FLUX 3: one image per request, no seed. Billed per megapixel, so 4K costs
    # about 16x 1K and can take several minutes.
    "blackforestlabs/flux-3/text-to-image": {
        "size_type": SizeParamType.ASPECT_RATIO,
        "resolutions": {"1k": "1k", "2k": "2k", "4k": "4k"},
        "defaults": {
            "output_format": "png",
            "safety_tolerance": 2,
            "enable_prompt_expansion": False,
        },
        "supports": [],
        "omit": ["seed", "num_images"],
        "max_images": 1,
    },
    # FLUX 3 Klein: small and fast, native up to 4096px.
    "blackforestlabs/flux-3/klein/text-to-image": {
        "size_type": SizeParamType.DIMS_TABLE,
        "sizes": "FLUX_3_KLEIN_SIZES",
        "defaults": {
            "output_format": "png",
            "enable_safety_checker": True,
            "enable_prompt_expansion": True,
        },
        "supports": [],
    },
    "google/nano-banana-2.1": {
        "size_type": SizeParamType.ASPECT_RATIO,
        "resolutions": {"1k": "1K", "2k": "2K", "4k": "4K"},
        "defaults": {"output_format": "png"},
        "supports": [],
    },
    # Ideogram V4.5: only listed sizes are accepted and 2048px is the ceiling,
    # so 4K renders at the 2K size. Priced per image by quality, not by size.
    "ideogram/v4.5": {
        "size_type": SizeParamType.DIMS_TABLE,
        "sizes": "IDEOGRAM_45_SIZES",
        "defaults": {
            "quality": "medium",
            "enable_prompt_expansion": True,
        },
        "supports": [],
    },
    # MAI Image 2.5: aspect ratio only, no resolution control, no seed. fal's
    # enum is 1:1, 4:3, 3:4, 16:9, 9:16, 3:2, 2:3 (no 21:9, no 4:5).
    "microsoft/mai-image-2.5": {
        "size_type": SizeParamType.ASPECT_RATIO,
        "aspect_fallback": {"21:9": "16:9", "4:5": "3:4"},
        "defaults": {"output_format": "png"},
        "supports": [],
        "omit": ["seed"],
    },
    # Grok Imagine 2.0: up to 2K, no seed, no 4:5.
    "xai/grok-imagine-image/v2.0/text-to-image": {
        "size_type": SizeParamType.ASPECT_RATIO,
        "resolutions": {"1k": "1k", "2k": "2k", "4k": "2k"},
        "aspect_fallback": {"4:5": "3:4"},
        "defaults": {
            "quality": "medium",
            "output_format": "png",
            "enable_safety_checker": True,
        },
        "supports": [],
        "omit": ["seed"],
    },
    "fal-ai/z-image/turbo/lora": {
        "size_type": SizeParamType.IMAGE_SIZE_PRESET,
        "defaults": {
            "image_size": "landscape_4_3",
            "num_inference_steps": 8,
            "output_format": "png",
            "acceleration": "none",
        },
        "supports": ["num_inference_steps", "loras"],
    },

    # Seedream V5 Pro: accepts presets OR custom {width,height}; we always send
    # custom dims from SEEDREAM_V5_SIZES so the aspect ratio is exact.
    "bytedance/seedream/v5/pro/text-to-image": {
        "size_type": SizeParamType.SEEDREAM_DIMS,
        "defaults": {
            "output_format": "jpeg",
            "enable_safety_checker": True,
        },
        "supports": [],
    },
}

# Aspect ratio to image_size preset mapping
# FAL supports: square_hd, square, portrait_4_3, portrait_16_9, landscape_4_3, landscape_16_9
ASPECT_TO_PRESET = {
    "1:1": "square_hd",
    "16:9": "landscape_16_9",
    "9:16": "portrait_16_9",   # Portrait orientation of 16:9
    "4:3": "landscape_4_3",
    "3:4": "portrait_4_3",     # Portrait orientation of 4:3
    "21:9": "landscape_16_9",  # Closest match
    "3:2": "landscape_4_3",    # Closest match
    "2:3": "portrait_4_3",     # Closest match
    "4:5": "portrait_4_3",     # Closest match
}

# Aspect ratio to pixel dimensions (base resolution)
ASPECT_TO_PIXELS = {
    # 1k resolution
    "1:1": {"1k": (1024, 1024), "2k": (2048, 2048), "4k": (4096, 4096)},
    "16:9": {"1k": (1312, 736), "2k": (2048, 1152), "4k": (3840, 2160)},
    "9:16": {"1k": (736, 1312), "2k": (1152, 2048), "4k": (2160, 3840)},
    "4:3": {"1k": (1024, 768), "2k": (2048, 1536), "4k": (4096, 3072)},
    "3:4": {"1k": (768, 1024), "2k": (1536, 2048), "4k": (3072, 4096)},
    "21:9": {"1k": (1680, 720), "2k": (2560, 1080), "4k": (3440, 1440)},
    "3:2": {"1k": (1200, 800), "2k": (2400, 1600), "4k": (3600, 2400)},
    "2:3": {"1k": (800, 1200), "2k": (1600, 2400), "4k": (2400, 3600)},
    "4:5": {"1k": (1024, 1280), "2k": (1632, 2048), "4k": (3072, 3840)},
}

# GPT Image 2.5 dimensions per (aspect_ratio, resolution): edges multiples of
# 16, max edge 3840, 655,360-8,294,400 total pixels, aspect ratio within 3:1.
# OpenAI calls anything above 2560x1440 (3,686,400 pixels) experimental, so
# 2K stays inside that budget; 4K is the experimental per-ratio ceiling.
# Also the Explainer's sizes (generate_explainer_image).
GPT_IMAGE_25_SIZES = {
    "1:1":  {"1k": (1024, 1024), "2k": (1920, 1920), "4k": (2880, 2880)},
    "16:9": {"1k": (1360, 768),  "2k": (2560, 1440), "4k": (3840, 2160)},
    "9:16": {"1k": (768, 1360),  "2k": (1440, 2560), "4k": (2160, 3840)},
    "4:3":  {"1k": (1152, 864),  "2k": (2176, 1632), "4k": (3312, 2480)},
    "3:4":  {"1k": (864, 1152),  "2k": (1632, 2176), "4k": (2480, 3312)},
    "21:9": {"1k": (1568, 672),  "2k": (2912, 1248), "4k": (3840, 1648)},
    "3:2":  {"1k": (1248, 832),  "2k": (2304, 1536), "4k": (3504, 2336)},
    "2:3":  {"1k": (832, 1248),  "2k": (1536, 2304), "4k": (2336, 3504)},
    "4:5":  {"1k": (1024, 1280), "2k": (1664, 2080), "4k": (2560, 3200)},
}

# FLUX 3 Klein: each edge 256-4096 and a multiple of 16; 4K uses the full
# 4096px edge.
FLUX_3_KLEIN_SIZES = {
    "1:1":  {"1k": (1024, 1024), "2k": (2048, 2048), "4k": (4096, 4096)},
    "16:9": {"1k": (1360, 768),  "2k": (2736, 1536), "4k": (4096, 2304)},
    "9:16": {"1k": (768, 1360),  "2k": (1536, 2736), "4k": (2304, 4096)},
    "4:3":  {"1k": (1152, 864),  "2k": (2368, 1776), "4k": (4096, 3072)},
    "3:4":  {"1k": (864, 1152),  "2k": (1776, 2368), "4k": (3072, 4096)},
    "21:9": {"1k": (1568, 672),  "2k": (3136, 1344), "4k": (4096, 1760)},
    "3:2":  {"1k": (1248, 832),  "2k": (2496, 1664), "4k": (4080, 2720)},
    "2:3":  {"1k": (832, 1248),  "2k": (1664, 2496), "4k": (2720, 4080)},
    "4:5":  {"1k": (1024, 1280), "2k": (1792, 2240), "4k": (3264, 4080)},
}

# Ideogram V4.5 accepts only 36 listed sizes and tops out at 2048x2048, so 4K
# uses the 2K size. 21:9 has no exact match: 2:1 at 1K, 2.4:1 at 2K.
IDEOGRAM_45_SIZES = {
    "1:1":  {"1k": (1024, 1024), "2k": (2048, 2048)},
    "16:9": {"1k": (1280, 720),  "2k": (2560, 1440)},
    "9:16": {"1k": (720, 1280),  "2k": (1440, 2560)},
    "4:3":  {"1k": (1152, 864),  "2k": (2304, 1728)},
    "3:4":  {"1k": (864, 1152),  "2k": (1728, 2304)},
    "21:9": {"1k": (1440, 720),  "2k": (3072, 1280)},
    "3:2":  {"1k": (1248, 832),  "2k": (2496, 1664)},
    "2:3":  {"1k": (832, 1248),  "2k": (1664, 2496)},
    "4:5":  {"1k": (896, 1120),  "2k": (1792, 2240)},
}

SIZE_TABLES = {
    "GPT_IMAGE_25_SIZES": GPT_IMAGE_25_SIZES,
    "FLUX_3_KLEIN_SIZES": FLUX_3_KLEIN_SIZES,
    "IDEOGRAM_45_SIZES": IDEOGRAM_45_SIZES,
}

# Seedream V5 dimensions per (aspect_ratio, resolution). fal takes 921,600 to
# 4,624,220 total pixels; the model wants each edge 672-3136 px in steps of 16.
# Every entry is a multiple of 16 inside 1,048,576-4,194,304 pixels (the
# 1024x1024 to 2048x2048 budget), so 4K resolves to the same dims as 2K.
SEEDREAM_V5_SIZES = {
    "1:1":  {"1k": (1024, 1024), "2k": (2048, 2048)},
    "16:9": {"1k": (1376, 768),  "2k": (2720, 1536)},
    "9:16": {"1k": (768, 1376),  "2k": (1536, 2720)},
    "4:3":  {"1k": (1216, 912),  "2k": (2304, 1728)},
    "3:4":  {"1k": (912, 1216),  "2k": (1728, 2304)},
    "21:9": {"1k": (1568, 672),  "2k": (3024, 1296)},
    "3:2":  {"1k": (1296, 864),  "2k": (2496, 1664)},
    "2:3":  {"1k": (864, 1296),  "2k": (1664, 2496)},
    "4:5":  {"1k": (960, 1200),  "2k": (1792, 2240)},
}


def max_images_for(model: str, requested: int) -> int:
    """Images a request can actually return; the estimate is priced on this."""
    return max(1, min(requested, get_model_config(model).get("max_images", requested)))


def get_model_config(model: str) -> dict:
    """Get configuration for a model, with fallback to defaults."""
    return MODEL_CONFIG.get(model, {
        "size_type": SizeParamType.IMAGE_SIZE_DICT,
        "defaults": {},
        "supports": [],
    })


def convert_size_params(
    model: str,
    aspect_ratio: str,
    resolution: str = "1k",
) -> dict:
    """Convert unified aspect_ratio to model-specific size parameters."""
    config = get_model_config(model)
    size_type = config.get("size_type", SizeParamType.IMAGE_SIZE_DICT)

    # Normalize resolution
    res = resolution.lower() if resolution else "1k"
    if res not in ["1k", "2k", "4k"]:
        res = "1k"

    if size_type == SizeParamType.ASPECT_RATIO:
        # Pass aspect ratio directly, mapped to the nearest one the model has
        params = {"aspect_ratio": config.get("aspect_fallback", {}).get(aspect_ratio, aspect_ratio)}
        # Add resolution in the model's own spelling, for models that take one
        resolutions = config.get("resolutions")
        if resolutions:
            params["resolution"] = resolutions.get(res, resolutions["1k"])
        return params

    elif size_type == SizeParamType.IMAGE_SIZE_PRESET:
        # Convert to preset string
        preset = ASPECT_TO_PRESET.get(aspect_ratio, "landscape_4_3")
        return {"image_size": preset}

    elif size_type == SizeParamType.SEEDREAM_DIMS:
        # Seedream V5: custom {width, height} within the model's pixel budget.
        # 4K is clamped to the 2K dims — the model caps at ~4.19M pixels.
        sizes = SEEDREAM_V5_SIZES.get(aspect_ratio) or SEEDREAM_V5_SIZES["16:9"]
        dims = sizes["1k"] if res == "1k" else sizes["2k"]
        return {"image_size": {"width": dims[0], "height": dims[1]}}

    elif size_type == SizeParamType.DIMS_TABLE:
        # Exact {width, height} from the model's table; resolutions it lacks
        # (4K on a 2K-capped model) fall back to its largest.
        table = SIZE_TABLES[config["sizes"]]
        sizes = table.get(aspect_ratio) or table["16:9"]
        dims = sizes.get(res) or sizes.get("2k") or sizes["1k"]
        return {"image_size": {"width": dims[0], "height": dims[1]}}

    else:  # IMAGE_SIZE_DICT
        # Convert to pixel dimensions
        if aspect_ratio in ASPECT_TO_PIXELS:
            dims = ASPECT_TO_PIXELS[aspect_ratio].get(res, ASPECT_TO_PIXELS[aspect_ratio]["1k"])
            return {"image_size": {"width": dims[0], "height": dims[1]}}
        # Fallback
        return {"image_size": {"width": 1024, "height": 1024}}


def fal_submit(endpoint: str, arguments: dict, db: Session | None = None):
    """Submit to fal's queue with the stored key; returns the SDK's request handle.

    Own /static files in ``arguments`` go to fal storage first. Blocking network
    calls: from async code use run_in_threadpool.
    """
    client = get_sync_client(db)
    return client.submit(endpoint, resolve_fal_inputs(arguments))


def fal_subscribe(
    endpoint: str,
    arguments: dict,
    db: Session | None = None,
    *,
    with_logs: bool = False,
    on_queue_update=None,
):
    """Submit and wait for the result, with the stored key. Own /static files in
    ``arguments`` go to fal storage first. Blocking: from async code use
    fal_subscribe_async."""
    client = get_sync_client(db)
    return client.subscribe(
        endpoint,
        resolve_fal_inputs(arguments),
        with_logs=with_logs,
        on_queue_update=on_queue_update,
    )


async def fal_subscribe_async(
    endpoint: str,
    arguments: dict,
    db: Session | None = None,
    *,
    with_logs: bool = False,
    on_queue_update=None,
):
    """fal_subscribe in a worker thread, so a job of several minutes does not freeze
    the event loop. The key is read here, on the caller's session."""
    client = get_sync_client(db)

    def run():
        return client.subscribe(
            endpoint,
            resolve_fal_inputs(arguments),
            with_logs=with_logs,
            on_queue_update=on_queue_update,
        )

    return await asyncio.to_thread(run)


def build_generation_arguments(
    prompt: str,
    model: str,
    aspect_ratio: str = "16:9",
    resolution: str = "1k",
    num_images: int = 1,
    lora_url: str | None = None,
    lora_scale: float = 1.0,
    guidance_scale: float | None = None,
    inference_steps: int | None = None,
    seed: int | None = None,
    negative_prompt: str | None = None,
    width: int | None = None,
    height: int | None = None,
    prompt_expansion: bool | None = None,
) -> dict:
    """Build arguments dict for FAL API call. ``prompt_expansion`` overrides
    a model's enable_prompt_expansion default (off for Magic Prompts)."""
    import random

    # Generate seed if not provided
    if seed is None:
        seed = random.randint(1, 2147483647)

    # Get model configuration
    config = get_model_config(model)

    # Start with model defaults. Some models reject seed or num_images
    # outright, so those are only sent where the schema has them.
    omit = set(config.get("omit", ()))
    arguments = {"prompt": prompt}
    if "num_images" not in omit:
        arguments["num_images"] = num_images
    if "seed" not in omit:
        arguments["seed"] = seed

    # Merge model defaults
    arguments.update(config.get("defaults", {}))
    if prompt_expansion is not None and "enable_prompt_expansion" in arguments:
        arguments["enable_prompt_expansion"] = bool(prompt_expansion)

    # Handle size parameters
    if width is not None and height is not None and config.get("size_type") != SizeParamType.ASPECT_RATIO:
        arguments["image_size"] = {"width": width, "height": height}
    else:
        size_params = convert_size_params(model, aspect_ratio, resolution)
        arguments.update(size_params)

    # Add optional parameters based on model support
    supports = config.get("supports", [])

    if guidance_scale is not None and "guidance_scale" in supports:
        arguments["guidance_scale"] = guidance_scale

    if inference_steps is not None and "num_inference_steps" in supports:
        arguments["num_inference_steps"] = inference_steps

    if negative_prompt and "negative_prompt" in supports:
        arguments["negative_prompt"] = negative_prompt

    # Add LoRA if specified and supported
    if lora_url and "loras" in supports:
        arguments["loras"] = [{"path": lora_url, "scale": lora_scale}]

    return arguments


def submit_image_generation(
    prompt: str,
    model: str,
    db: Session,
    aspect_ratio: str = "16:9",
    resolution: str = "1k",
    num_images: int = 1,
    lora_url: str | None = None,
    lora_scale: float = 1.0,
    guidance_scale: float | None = None,
    inference_steps: int | None = None,
    seed: int | None = None,
    negative_prompt: str | None = None,
    prompt_expansion: bool | None = None,
) -> dict:
    """Submit async image generation job to FAL.

    Returns:
        dict with request_id and seed
    """
    # SECURITY: Validate model is in whitelist
    if not validate_model(model):
        raise ValueError(f"Model '{model}' is not allowed")

    # SECURITY: Validate LoRA URL if provided
    if lora_url:
        is_valid, error = validate_lora_url(lora_url)
        if not is_valid:
            raise ValueError(f"Invalid LoRA URL: {error}")

    # Build arguments
    arguments = build_generation_arguments(
        prompt=prompt,
        model=model,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        num_images=num_images,
        lora_url=lora_url,
        lora_scale=lora_scale,
        guidance_scale=guidance_scale,
        inference_steps=inference_steps,
        seed=seed,
        negative_prompt=negative_prompt,
        prompt_expansion=prompt_expansion,
    )

    handler = fal_submit(model, arguments, db)

    return {
        "request_id": handler.request_id,
        "seed": arguments.get("seed"),
    }


# fal answered that the request itself is unknown or invalid: the job is lost.
# 401/403 (a key problem), 408, 429 and 5xx are not about the job.
_FATAL_STATUS_CODES = {400, 404, 410, 422}


# A provider's content filter refused the request or its output. The stored
# job error starts with CONTENT_FILTER_PREFIX, so pages can tell it apart from
# other failures by its text (frontend utils/errors.ts isContentFilterError)
# or by the code status responses derive from it (job_error_code). The same
# payload on the same model is refused again, so the sentence never suggests
# a retry: it suggests rewording or a model from another provider.
CONTENT_FILTER_CODE = "content_filter"
CONTENT_FILTER_PREFIX = "The provider's content filter blocked"
CONTENT_FILTER_ERROR = (
    f"{CONTENT_FILTER_PREFIX} this generation. Reword the prompt, "
    "or switch to a model from a different provider."
)
# fal's error type for a moderation refusal (422, not retryable), and the
# codes ByteDance's filters put in their messages.
_CONTENT_POLICY_TYPES = {"content_policy_violation"}
_CONTENT_POLICY_MARKERS = (
    "OutputVideoSensitiveContentDetected",
    "OutputAudioSensitiveContentDetected",
    "InputTextSensitiveContentDetected",
    "InputImageSensitiveContentDetected",
)


def _error_status_code(error: Exception) -> int | None:
    code = getattr(error, "status_code", None)
    if code is None:
        code = getattr(getattr(error, "response", None), "status_code", None)
    return code if isinstance(code, int) else None


def is_content_policy_error(error: Exception | None) -> bool:
    """Whether fal answered that a content filter blocked the request.

    Conservative: only a 422 whose body names fal's content_policy_violation
    type (in the detail list, the flat error_type or the X-Fal-Error-Type
    header), or one of ByteDance's sensitive-content codes, counts. Anything
    else keeps the generic failure message.
    """
    if error is None or _error_status_code(error) != 422:
        return False
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None) or getattr(error, "response_headers", None) or {}
    try:
        if str(headers.get("x-fal-error-type") or headers.get("X-Fal-Error-Type") or "") in _CONTENT_POLICY_TYPES:
            return True
    except Exception:
        pass
    body = None
    try:
        body = response.json() if response is not None else None
    except Exception:
        body = None
    details = []
    if isinstance(body, dict):
        if body.get("error_type") in _CONTENT_POLICY_TYPES:
            return True
        details = body.get("detail")
    if not isinstance(details, list):
        details = getattr(error, "message", None)
    if isinstance(details, list):
        for item in details:
            if isinstance(item, dict) and item.get("type") in _CONTENT_POLICY_TYPES:
                return True
    text = str(details if details is not None else error)
    return any(marker in text for marker in _CONTENT_POLICY_MARKERS)


def job_failure_error(error: Exception | None, fallback: str) -> str:
    """The sentence stored on a job whose processing raised: the content
    filter sentence when fal blocked it, otherwise ``fallback``."""
    return CONTENT_FILTER_ERROR if is_content_policy_error(error) else fallback


def job_error_code(error_text: str | None) -> str | None:
    """Stable code for a stored job error, for status responses (or None)."""
    if error_text and error_text.startswith(CONTENT_FILTER_PREFIX):
        return CONTENT_FILTER_CODE
    return None


def _status_check_failed(request_id: str, error: Exception) -> dict:
    """Result of a status check that raised.

    Only a definitive answer from fal fails the job. A network error, timeout,
    rate limit or fal outage is reported as "unknown" so callers keep the job
    and poll again: failing it there left the user with nothing while fal
    still finished and billed the request. The detail is logged, not returned,
    because some callers search the whole dict for the word "error". Jobs that
    never come back are expired by job_state.expire_stuck_fal_jobs.
    A content filter refusal gets its own sentence and error_code.
    """
    code = _error_status_code(error)
    if code is not None and code in _FATAL_STATUS_CODES:
        # Shown to the user on the job; the provider's answer stays in the log.
        _logger.warning(f"fal rejected request {request_id} (HTTP {code}): {type(error).__name__}: {error}")
        if is_content_policy_error(error):
            return {"status": "error", "error": CONTENT_FILTER_ERROR, "error_code": CONTENT_FILTER_CODE}
        return {"status": "error", "error": "This job could not be completed. Please try again."}
    _logger.warning(f"fal status check for {request_id} failed, will retry: {type(error).__name__}: {error}")
    return {"status": "unknown", "in_queue": False, "in_progress": False, "completed": False}


def get_generation_status(model: str, request_id: str, db: Session) -> dict:
    """Check status of an async generation job.

    Returns:
        dict with status, logs, and progress info
    """
    client = get_sync_client(db)

    try:
        status = client.status(model, request_id, with_logs=True)

        # Parse status - FAL returns status objects like InQueue, InProgress, Completed
        status_str = "pending"
        status_type = type(status).__name__

        # Check by class name
        if status_type == "Completed" or status_type == "CompletedStatus":
            status_str = "COMPLETED"
        elif status_type == "InProgress" or status_type == "InProgressStatus":
            status_str = "IN_PROGRESS"
        elif status_type == "InQueue" or status_type == "InQueueStatus" or status_type == "Queued":
            status_str = "IN_QUEUE"

        # Also check if there's a status attribute
        if hasattr(status, "status"):
            attr_status = str(status.status).upper()
            if "COMPLETE" in attr_status:
                status_str = "COMPLETED"
            elif "PROGRESS" in attr_status:
                status_str = "IN_PROGRESS"
            elif "QUEUE" in attr_status:
                status_str = "IN_QUEUE"

        logs = []
        if hasattr(status, "logs") and status.logs:
            logs = [log.get("message", "") if isinstance(log, dict) else str(log) for log in status.logs]

        return {
            "status": status_str,
            "logs": logs,
            "in_queue": status_str == "IN_QUEUE",
            "in_progress": status_str == "IN_PROGRESS",
            "completed": status_str == "COMPLETED",
        }
    except Exception as e:
        return _status_check_failed(request_id, e)


def get_generation_result(model: str, request_id: str, db: Session) -> dict:
    """Fetch result of a completed generation job.

    Returns:
        dict with images list
    """
    return get_sync_client(db).result(model, request_id)


def _image_dimensions(img: dict, file_data: bytes) -> tuple[int | None, int | None]:
    """Width and height from the FAL response, or from the file header when the
    model does not report them (Ideogram V4.5 returns none)."""
    width, height = img.get("width"), img.get("height")
    if width and height:
        return width, height
    try:
        from io import BytesIO
        from PIL import Image as PILImage

        with PILImage.open(BytesIO(file_data)) as probe:
            return probe.size
    except Exception:
        return width, height


# Shown on a /generate job whose every image the provider's safety filter
# blanked: nothing was stored.
SAFETY_BLOCKED_ALL = (
    "The safety filter blocked every image from this job. "
    "Try rewording the prompt or choosing another model."
)


def drop_safety_flagged(result: dict) -> tuple[dict, int]:
    """fal's result without the images its safety checker flagged, and their count.

    Models with a safety checker that report it (FLUX 3 Klein and Z-Image
    return has_nsfw_concepts, one flag per image) still deliver a flagged
    image, blanked. Flagged images are dropped before download, and the job is
    recorded per image kept.
    """
    images = list(result.get("images") or [])
    flags = result.get("has_nsfw_concepts")
    if not isinstance(flags, list) or not images:
        return result, 0
    kept = [img for i, img in enumerate(images) if not (i < len(flags) and bool(flags[i]))]
    blocked = len(images) - len(kept)
    if not blocked:
        return result, 0
    return {**result, "images": kept, "has_nsfw_concepts": [False] * len(kept)}, blocked


def safety_blocked_notice(blocked: int, delivered: int) -> str | None:
    """The sentence shown with a result some of whose images were blocked."""
    if blocked <= 0:
        return None
    total = blocked + delivered
    return (
        f"The safety filter blocked {blocked} of {total} images. "
        "Try rewording the prompt or choosing another model for the rest."
    )


async def download_and_save_images(result: dict, seed: int | None = None, user_id: int | None = None) -> list[dict]:
    """Download images from FAL result and save to storage.

    Args:
        result: FAL API result containing images
        seed: Optional seed used for generation
        user_id: User ID for organizing files by user folder

    Returns:
        list of dicts with filename, url, width, height, seed
    """
    from app.services.storage_service import storage_service
    from app.services.url_fetch import afetch_bytes

    images = []
    for img in result.get("images", []):
        image_url = img.get("url")
        if image_url:
            # Determine extension from content type or URL
            ext = "png"
            content_type = img.get("content_type", "")
            if "jpeg" in content_type or "jpg" in content_type:
                ext = "jpg"
            elif "webp" in content_type:
                ext = "webp"

            filename = f"{uuid.uuid4()}.{ext}"

            # Download image
            file_data = await afetch_bytes(image_url)

            # Save to storage, in the user's folder
            url = await storage_service.upload_file(
                file_data=file_data,
                filename=filename,
                storage_type="images",
                content_type=f"image/{ext}" if ext != "jpg" else "image/jpeg",
                user_id=user_id,
            )

            width, height = _image_dimensions(img, file_data)
            images.append({
                "filename": filename,
                "url": url,
                "width": width,
                "height": height,
                "seed": result.get("seed", seed),
            })

    return images


async def generate_image(
    prompt: str,
    model: str,
    db: Session,
    aspect_ratio: str = "16:9",
    resolution: str = "1k",
    num_images: int = 1,
    lora_url: str | None = None,
    lora_scale: float = 1.0,
    guidance_scale: float | None = None,
    inference_steps: int | None = None,
    seed: int | None = None,
    negative_prompt: str | None = None,
    art_style: str | None = None,
    # Legacy parameters for backwards compatibility
    width: int | None = None,
    height: int | None = None,
    user_id: int | None = None,
) -> list[dict]:
    """Generate images using FAL API (synchronous subscribe mode).

    This is the legacy sync method - use submit_image_generation for async.
    """
    # SECURITY: Validate model is in whitelist
    if not validate_model(model):
        raise ValueError(f"Model '{model}' is not allowed")

    # SECURITY: Validate LoRA URL if provided
    if lora_url:
        is_valid, error = validate_lora_url(lora_url)
        if not is_valid:
            raise ValueError(f"Invalid LoRA URL: {error}")

    # Build arguments
    arguments = build_generation_arguments(
        prompt=prompt,
        model=model,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        num_images=num_images,
        lora_url=lora_url,
        lora_scale=lora_scale,
        guidance_scale=guidance_scale,
        inference_steps=inference_steps,
        seed=seed,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
    )

    _logger.debug(f"\n=== FAL API Call (Sync) ===")
    _logger.debug(f"Model: {model}")
    _logger.debug(f"Arguments: {arguments}")

    result = await fal_subscribe_async(model, arguments, db)

    # Download and save images (organized by user folder)
    return await download_and_save_images(result, arguments.get("seed"), user_id=user_id)


def build_magix_prompt(mode: str, prompt: str, mode_options: dict | None = None,
                       image_roles: list[str] | None = None) -> str:
    """The Magix mode applied to image 1, as plain sentences with one choice per
    field (app/services/edit_prompts.py)."""
    from app.services.edit_prompts import build_magix_prompt as build

    return build(mode, prompt, mode_options, image_roles)


# =============================================================================
# IMAGE EDIT MODELS - Magix and Virtual Try-On
# =============================================================================

DEFAULT_EDIT_MODEL = "google/nano-banana-2.1/edit"

# Per-model rules for the edit endpoints, in the order the UI offers them.
#   max_inputs   input images one request accepts
#   size         "aspect_resolution": aspect_ratio + resolution fields;
#                "image_size": {width, height} from GPT_IMAGE_25_SIZES or "auto";
#                "auto": the model keeps the source geometry
#   aspects      aspect ratios the model accepts (None: every app ratio);
#                anything else is sent as the model's own "auto"
#   formats      output_format values accepted (empty: the field does not exist)
#   omit         common fields the model rejects
#   max_prompt   prompt length limit, when lower than our prompts can reach
EDIT_MODEL_CONFIG = {
    "google/nano-banana-2.1/edit": {
        "label": "Nano Banana 2.1",
        "max_inputs": 14,
        "size": "aspect_resolution",
        "aspects": None,
        "resolutions": {"1K": "1K", "2K": "2K", "4K": "4K"},
        "formats": ("png", "jpeg", "webp"),
        "omit": (),
        "defaults": {},
    },
    "openai/gpt-image-2.5/sunburst/edit": {
        "label": "GPT Image 2.5",
        "max_inputs": 16,
        "size": "image_size",
        "formats": ("png", "jpeg", "webp"),
        "omit": ("seed",),
        "defaults": {"quality": "high", "enable_safety_checker": True},
    },
    # One output per request, no seed.
    "blackforestlabs/flux-3/edit-image": {
        "label": "FLUX 3",
        "max_inputs": 10,
        "size": "aspect_resolution",
        "aspects": None,
        "resolutions": {"1K": "1k", "2K": "2k", "4K": "4k"},
        "formats": ("png", "jpeg"),
        "omit": ("seed", "num_images"),
        "max_images": 1,
        "defaults": {"safety_tolerance": 2},
    },
    "xai/grok-imagine-image/v2.0/edit": {
        "label": "Grok Imagine 2.0",
        "max_inputs": 3,
        "size": "aspect_resolution",
        "aspects": {"16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "1:1", "21:9"},
        "resolutions": {"1K": "1k", "2K": "2k", "4K": "2k"},
        "formats": ("png", "jpeg", "webp"),
        "omit": ("seed",),
        "max_prompt": 8000,
        "defaults": {"quality": "medium", "enable_safety_checker": True},
    },
    # Edits one primary photo; further images go in as references.
    "ideogram/v4.5/edit": {
        "label": "Ideogram V4.5",
        "max_inputs": 5,
        "size": "auto",
        "primary_image": True,
        "formats": (),
        "omit": (),
        "defaults": {"quality": "medium"},
    },
}


def validate_edit_model(model: str) -> bool:
    """Validate that the edit model is one Magix and Virtual Try-On may use."""
    return model in EDIT_MODEL_CONFIG


def edit_max_images(model: str, requested: int) -> int:
    """Images an edit request can actually return; the estimate is priced on this."""
    cap = EDIT_MODEL_CONFIG[model].get("max_images", requested)
    return max(1, min(requested, cap))


def edit_output_extension(img: dict, requested_format: str) -> str:
    """File extension for an edit result, trusting the returned content type."""
    content_type = (img.get("content_type") or "") if isinstance(img, dict) else ""
    if "jpeg" in content_type or "jpg" in content_type:
        return "jpg"
    if "webp" in content_type:
        return "webp"
    if "png" in content_type:
        return "png"
    return "jpg" if requested_format == "jpeg" else requested_format


def build_edit_arguments(
    model: str,
    prompt: str,
    image_urls: list[str],
    aspect_ratio: str | None = None,
    resolution: str = "1K",
    output_format: str = "png",
    num_images: int = 1,
    seed: int | None = None,
) -> dict:
    """Build the request body for an edit model from the shared Magix/Try-On inputs."""
    cfg = EDIT_MODEL_CONFIG[model]
    if len(image_urls) > cfg["max_inputs"]:
        raise ValueError(f"{cfg['label']} accepts at most {cfg['max_inputs']} input images")

    max_prompt = cfg.get("max_prompt")
    if max_prompt and len(prompt) > max_prompt:
        # Our edit prompts are sentences with the keep list first, so a cut
        # at the limit loses the least important clauses.
        prompt = prompt[:max_prompt]

    arguments = {"prompt": prompt, **cfg["defaults"]}

    if cfg.get("primary_image"):
        arguments["image_url"] = image_urls[0]
        if len(image_urls) > 1:
            arguments["reference_image_urls"] = image_urls[1:]
    else:
        arguments["image_urls"] = image_urls

    if "num_images" not in cfg["omit"]:
        arguments["num_images"] = num_images
    if seed is not None and "seed" not in cfg["omit"]:
        arguments["seed"] = seed
    if cfg["formats"]:
        arguments["output_format"] = output_format if output_format in cfg["formats"] else cfg["formats"][0]

    wants_ratio = bool(aspect_ratio) and aspect_ratio != "auto"
    res = (resolution or "1K").upper()
    if cfg["size"] == "aspect_resolution":
        aspects = cfg.get("aspects")
        if wants_ratio and (aspects is None or aspect_ratio in aspects):
            arguments["aspect_ratio"] = aspect_ratio
        arguments["resolution"] = cfg["resolutions"].get(res, cfg["resolutions"]["1K"])
    elif cfg["size"] == "image_size":
        sizes = GPT_IMAGE_25_SIZES.get(aspect_ratio) if wants_ratio else None
        if sizes:
            dims = sizes.get(res.lower(), sizes["1k"])
            arguments["image_size"] = {"width": dims[0], "height": dims[1]}
        else:
            arguments["image_size"] = "auto"

    return arguments


async def generate_magix_image(
    prompt: str,
    db: Session,
    image_url: str | None = None,
    image_urls: list[str] | None = None,
    mode: str = "studio_portrait",
    mode_options: dict | None = None,
    seed: int | None = None,
    aspect_ratio: str | None = None,
    resolution: str = "1K",
    output_format: str = "png",
    num_images: int = 1,
    user_intent_json: dict | None = None,
    user_id: int | None = None,
    model: str = DEFAULT_EDIT_MODEL,
    image_roles: list[str] | None = None,
) -> dict:
    """Generate a Magix-enhanced image with one of the EDIT_MODEL_CONFIG models.

    Uses the chosen edit endpoint (Nano Banana 2.1 by default) for intelligent
    image modification based on the mode and prompt description. The prompt
    is plain sentences (app/services/edit_prompts.py).

    When multiple images are provided, they are ALL combined into a SINGLE
    output: image 1 is the photo being edited, and every further image has
    one job from ``image_roles`` (subject, scene, style, outfit, product,
    light).

    Args:
        user_intent_json: If provided, this LLM-parsed user intent is
            written into the prompt (a targeted edit drops the mode template).
    """
    from app.clients.litellm_client import merge_user_intent_with_template

    # Determine images to process - always combine all images
    all_image_urls: list[str] = []
    if image_urls:
        all_image_urls = image_urls
    elif image_url:
        all_image_urls = [image_url]

    if not all_image_urls:
        raise ValueError("At least one image URL is required")

    if not validate_edit_model(model):
        raise ValueError(f"Model '{model}' is not available for Magix")

    # SECURITY: Validate all image URLs
    for url in all_image_urls:
        is_valid, error = validate_url(url)
        if not is_valid:
            raise ValueError(f"Invalid image URL: {error}")

    roles = list(image_roles or [])
    roles = (roles + ["subject"] * len(all_image_urls))[:len(all_image_urls)]

    if user_intent_json:
        structured_prompt = merge_user_intent_with_template(
            user_intent_json, mode=mode, prompt=prompt, mode_options=mode_options, image_roles=roles,
        )
    else:
        structured_prompt = build_magix_prompt(mode, prompt, mode_options, roles)

    # Pass all images - the AI will decide how to use them based on the prompt
    arguments = build_edit_arguments(
        model,
        structured_prompt,
        all_image_urls,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        output_format=output_format,
        num_images=edit_max_images(model, num_images),
        seed=seed,
    )

    _logger.debug(f"\n=== Magix Generation ({EDIT_MODEL_CONFIG[model]['label']}) ===")
    _logger.debug(f"Mode: {mode}")
    _logger.debug(f"Number of input images: {len(all_image_urls)}")
    _logger.debug(f"Aspect ratio: {aspect_ratio or 'auto'}")
    _logger.debug(f"Resolution: {resolution}")
    _logger.debug(f"Prompt: {structured_prompt[:300]}...")

    result = await fal_subscribe_async(model, arguments, db, with_logs=True)

    _logger.debug(f"FAL Response received")

    # Process result
    if result.get("images"):
        from app.services.storage_service import storage_service
        from app.services.url_fetch import afetch_bytes

        image_data = result["images"][0]
        image_url_result = image_data.get("url") if isinstance(image_data, dict) else image_data

        ext = edit_output_extension(image_data, output_format)
        filename = f"magix_{uuid.uuid4()}.{ext}"

        # Download image
        file_data = await afetch_bytes(image_url_result)

        # Save to storage, in the user's folder
        url = await storage_service.upload_file(
            file_data=file_data,
            filename=filename,
            storage_type="images",
            content_type=f"image/{ext}" if ext != "jpg" else "image/jpeg",
            user_id=user_id,
        )

        width, height = _image_dimensions(image_data if isinstance(image_data, dict) else {}, file_data)

        return {
            "filename": filename,
            "url": url,
            "width": width,
            "height": height,
            "seed": result.get("seed"),
            "magic_prompt": structured_prompt,  # The full prompt used
            "mode": mode,
            "resolution": resolution,
        }

    raise ValueError("No image returned from FAL")


EXPLAINER_TEXT_MODEL = "openai/gpt-image-2.5/sunburst/text-to-image"
EXPLAINER_EDIT_MODEL = "openai/gpt-image-2.5/sunburst/edit"
EXPLAINER_MAX_REFERENCES = 4


async def generate_explainer_image(
    prompt: str,
    db: Session,
    aspect_ratio: str = "16:9",
    resolution: str = "2K",
    output_format: str = "png",
    user_id: int | None = None,
    reference_image_urls: list[str] | None = None,
    mask_url: str | None = None,
) -> dict:
    """Generate an explainer or diagram image with OpenAI GPT Image 2.5
    (Sunburst, the precision tuning) via fal.

    Sunburst holds dense copy, numbers and diagram geometry better than GPT
    Image 2 at a lower price per image, which is what infographics, slides
    and educational explainers need.

    Routing:
      - reference_image_urls present: EXPLAINER_EDIT_MODEL, which takes up to
        16 reference images and a mask_url (white edits, black keeps)
      - otherwise: EXPLAINER_TEXT_MODEL

    Quality is fixed at "high" and num_images at 1 by product decision.
    Sizes come from GPT_IMAGE_25_SIZES.
    """
    references = [u for u in (reference_image_urls or []) if u]

    # Validate reference URLs against SSRF guard
    for ref_url in references:
        ok, err = validate_url(ref_url, allow_data_urls=False)
        if not ok:
            raise ValueError(f"Invalid reference image URL: {err}")
    if mask_url:
        ok, err = validate_url(mask_url, allow_data_urls=False)
        if not ok:
            raise ValueError(f"Invalid mask URL: {err}")

    # The price (pricing explainer edit keys) covers up to 4
    # references and a mask.
    if len(references) > EXPLAINER_MAX_REFERENCES:
        raise ValueError(f"The explainer accepts up to {EXPLAINER_MAX_REFERENCES} reference images")

    # Resolve dimensions for the chosen aspect_ratio + resolution
    res_key = (resolution or "2k").lower()
    if res_key not in {"1k", "2k", "4k"}:
        res_key = "2k"
    sizes = GPT_IMAGE_25_SIZES.get(aspect_ratio) or GPT_IMAGE_25_SIZES["16:9"]
    width, height = sizes.get(res_key, sizes["2k"])

    use_edit = len(references) > 0
    endpoint = EXPLAINER_EDIT_MODEL if use_edit else EXPLAINER_TEXT_MODEL

    arguments: dict = {
        "prompt": prompt,
        "image_size": {"width": width, "height": height},
        "quality": "high",
        "num_images": 1,
        "output_format": output_format,
        "enable_safety_checker": True,
    }
    if use_edit:
        arguments["image_urls"] = references
        if mask_url:
            arguments["mask_url"] = mask_url

    _logger.debug(f"\n=== Explainer Generation (GPT Image 2.5, {'edit' if use_edit else 'text-to-image'}) ===")
    _logger.debug(f"Endpoint: {endpoint}")
    _logger.debug(f"Prompt length: {len(prompt)} chars")
    _logger.debug(f"Image size: {width}x{height} ({aspect_ratio} @ {res_key.upper()})")
    if use_edit:
        _logger.debug(f"References: {len(references)}{' + mask' if mask_url else ''}")

    def print_logs(event) -> None:
        if isinstance(event, fal_client.InProgress):
            for log in (event.logs or []):
                msg = log.get("message") if isinstance(log, dict) else None
                if msg:
                    _logger.debug(f"[fal] {msg}")

    # Stream queue events for visibility
    result = await fal_subscribe_async(endpoint, arguments, db, with_logs=True, on_queue_update=print_logs)

    _logger.debug(f"FAL Response received")

    # Process result
    if result.get("images"):
        from app.services.storage_service import storage_service
        from app.services.url_fetch import afetch_bytes

        image_data = result["images"][0]
        image_url = image_data.get("url") if isinstance(image_data, dict) else image_data

        # Determine extension from output format
        ext = "jpg" if output_format == "jpeg" else output_format
        filename = f"explainer_{uuid.uuid4()}.{ext}"

        # Download image
        file_data = await afetch_bytes(image_url)

        # Save to storage, in the user's folder
        url = await storage_service.upload_file(
            file_data=file_data,
            filename=filename,
            storage_type="images",
            content_type=f"image/{ext}" if ext != "jpg" else "image/jpeg",
            user_id=user_id,
        )

        # Get dimensions
        width = image_data.get("width", 1024) if isinstance(image_data, dict) else 1024
        height = image_data.get("height", 1024) if isinstance(image_data, dict) else 1024

        return {
            "filename": filename,
            "url": url,
            "width": width,
            "height": height,
            "endpoint": endpoint,
        }

    raise ValueError("No image returned from FAL")


def build_tryon_prompt(mode: str, user_prompt: str | None, use_dress_background: bool = False,
                       user_intent: dict | None = None) -> str:
    """The try-on as plain sentences: image 1 is the person, image 2 lends the
    garment only (app/services/edit_prompts.py)."""
    from app.services.edit_prompts import build_tryon_prompt as build

    return build(mode, user_prompt, use_dress_background, user_intent)


async def generate_virtual_tryon(
    person_image: str,
    dress_image: str,
    db: Session,
    prompt: str | None = None,
    mode: str = "natural",
    aspect_ratio: str = "16:9",
    use_dress_background: bool = False,
    num_images: int = 1,
    temperature: float | None = None,
    seed: int | None = None,
    user_intent_json: dict | None = None,
    user_id: int | None = None,
    model: str = DEFAULT_EDIT_MODEL,
) -> dict:
    """Generate a virtual try-on image with one of the EDIT_MODEL_CONFIG models.

    Sends a person image and a garment/dress image to the chosen edit endpoint
    (Nano Banana 2.1 by default), creating a realistic virtual try-on result
    with mode-specific styling.

    Args:
        person_image: Base64 data URL or URL of the person image
        dress_image: Base64 data URL or URL of the dress/garment image
        db: Database session for API key lookup
        prompt: Optional custom instructions
        mode: Try-on style mode (natural, professional, glamour, etc.)
        aspect_ratio: Output aspect ratio (16:9, 9:16, 1:1, etc.)
        use_dress_background: Whether to use the background from the dress image
        num_images: Number of images to generate (1-4)
        temperature: Generation temperature (0.0-2.0)
        seed: Random seed for reproducibility
        user_intent_json: LLM-parsed user intent to merge with mode template
    """
    if not validate_edit_model(model):
        raise ValueError(f"Model '{model}' is not available for Virtual Try-On")

    # SECURITY: Validate image URLs
    is_valid, error = validate_url(person_image)
    if not is_valid:
        raise ValueError(f"Invalid person image URL: {error}")

    is_valid, error = validate_url(dress_image)
    if not is_valid:
        raise ValueError(f"Invalid dress image URL: {error}")

    # Image 1 is the person, image 2 lends the garment only; the parsed
    # intent, when there is one, is written into the same sentences.
    if user_intent_json:
        from app.clients.litellm_client import merge_tryon_intent_with_template
        structured_prompt = merge_tryon_intent_with_template(
            user_intent_json, mode=mode, prompt=prompt, use_dress_background=use_dress_background,
        )
    else:
        structured_prompt = build_tryon_prompt(mode, prompt, use_dress_background)

    _logger.debug(f"\n=== Virtual Try-On Generation ===")
    _logger.debug(f"Mode: {mode}")
    _logger.debug(f"Aspect ratio: {aspect_ratio}")
    _logger.debug(f"Using LLM enhancement: {user_intent_json is not None}")
    _logger.debug(f"Prompt preview: {structured_prompt[:200]}...")

    # temperature is accepted for API compatibility; none of the edit models
    # take it, so it is not sent.
    arguments = build_edit_arguments(
        model,
        structured_prompt,
        [person_image, dress_image],
        aspect_ratio=aspect_ratio,
        output_format="jpeg",
        num_images=edit_max_images(model, num_images),
        seed=seed,
    )

    _logger.debug(f"Model: {EDIT_MODEL_CONFIG[model]['label']}, num images: {arguments.get('num_images', 1)}")

    result = await fal_subscribe_async(model, arguments, db, with_logs=True)

    _logger.debug(f"FAL Response received")

    # Process results
    images = []
    if result.get("images"):
        from app.services.storage_service import storage_service
        from app.services.url_fetch import afetch_bytes

        for img in result["images"]:
            image_url = img.get("url") if isinstance(img, dict) else img

            if image_url:
                ext = edit_output_extension(img, "jpeg")
                filename = f"virtual_{uuid.uuid4()}.{ext}"

                # Download image
                file_data = await afetch_bytes(image_url)

                # Save to storage, in the user's folder
                url = await storage_service.upload_file(
                    file_data=file_data,
                    filename=filename,
                    storage_type="images",
                    content_type=f"image/{ext}" if ext != "jpg" else "image/jpeg",
                    user_id=user_id,
                )

                width, height = _image_dimensions(img if isinstance(img, dict) else {}, file_data)

                images.append({
                    "filename": filename,
                    "url": url,
                    "width": width,
                    "height": height,
                })

    if not images:
        raise ValueError("No images returned from FAL")

    return {
        "images": images,
        "seed": result.get("seed"),
        "prompt": structured_prompt,
        "mode": mode,
    }


async def remove_background(
    image_url: str,
    db: Session,
    user_id: int | None = None,
) -> dict:
    """Remove background from image using FAL's Bria model.

    Uses fal-ai/bria/background/remove to remove the background from an image,
    returning a PNG with transparent background.

    Args:
        image_url: Base64 data URL or URL of the image
        db: Database session for API key lookup

    Returns:
        Dict with filename, url, width, height of the result image
    """
    # SECURITY: Validate image URL
    is_valid, error = validate_url(image_url)
    if not is_valid:
        raise ValueError(f"Invalid image URL: {error}")

    arguments = {
        "image_url": image_url,
    }

    _logger.debug(f"\n=== Background Removal (Bria) ===")
    _logger.debug(f"Processing image...")

    # Call Bria background removal API
    result = await fal_subscribe_async("fal-ai/bria/background/remove", arguments, db, with_logs=True)

    _logger.debug(f"FAL Response received")

    # Process result - Bria returns a single image
    if result.get("image"):
        image_data = result["image"]
        image_url_result = image_data.get("url") if isinstance(image_data, dict) else image_data

        # Save as PNG to preserve transparency
        filename = f"removebg_{uuid.uuid4()}.png"

        # Download image
        from app.services.url_fetch import afetch_bytes
        file_data = await afetch_bytes(image_url_result)

        # Use storage service to save file
        from app.services.storage_service import storage_service
        url = await storage_service.upload_file(
            file_data=file_data,
            filename=filename,
            storage_type="images",
            content_type="image/png",
            user_id=user_id,
        )

        # Get dimensions
        width = image_data.get("width", 1024) if isinstance(image_data, dict) else 1024
        height = image_data.get("height", 1024) if isinstance(image_data, dict) else 1024

        return {
            "filename": filename,
            "url": url,
            "width": width,
            "height": height,
        }

    raise ValueError("No image returned from FAL background removal")


# =============================================================================
# VIDEO GENERATION - Motion Control
# =============================================================================

# Three tiers of fal's Kling motion transfer, all taking the same image plus
# reference video (https://fal.ai/kling-motion-control). V3 adds an optional
# face element for identity preservation, only with character_orientation
# "video". Prices are per second of output in pricing (price_key).
# Each job stores the endpoint it was submitted to (VideoGenerationJob.model)
# and is polled on it; rows from before the tier choice have NULL and went to
# v2.6, which is VIDEO_MODEL.
MOTION_CONTROL_TIERS: dict[str, dict] = {
    "v3-standard": {
        "endpoint": "fal-ai/kling-video/v3/standard/motion-control",
        "label": "Kling V3 Standard",
        "price_key": MOTION_CONTROL_KEYS["v3-standard"],
        "supports_elements": True,
    },
    "v3-pro": {
        "endpoint": "fal-ai/kling-video/v3/pro/motion-control",
        "label": "Kling V3 Pro",
        "price_key": MOTION_CONTROL_KEYS["v3-pro"],
        "supports_elements": True,
    },
    "v2.6": {
        "endpoint": "fal-ai/kling-video/v2.6/standard/motion-control",
        "label": "Kling v2.6 Standard",
        "price_key": MOTION_CONTROL_KEYS["v2.6"],
        "supports_elements": False,
    },
}

# The endpoint of jobs submitted before the tier choice (model column NULL).
VIDEO_MODEL = MOTION_CONTROL_TIERS["v2.6"]["endpoint"]
_MOTION_TIER_BY_ENDPOINT = {cfg["endpoint"]: tier for tier, cfg in MOTION_CONTROL_TIERS.items()}

# The face element is referenced in the prompt by this token (fal's schema).
MOTION_ELEMENT_TOKEN = "@Element1"
MOTION_ELEMENT_SENTENCE = f"The character's face matches {MOTION_ELEMENT_TOKEN}."
# Our own cap on the user's prompt; fal accepts 2,500 characters, which leaves
# room for MOTION_ELEMENT_SENTENCE.
MOTION_PROMPT_MAX_CHARS = 2000


# Multi-character motion transfer (https://fal.ai/models/minimax/h3-max/recast):
# a source video and up to four reference photos, one per person to replace.
# Runs through the Motion Control job pipeline; the job's options carry its
# price tier (pricing.RECAST_KEYS).
RECAST_ENDPOINT = "minimax/h3-max/recast"
RECAST_FAL_RESOLUTIONS = {"768p": "768P", "1080p": "1080P"}
# "#Image2" (any casing) in a Recast prompt: the second reference photo.
RECAST_IMAGE_MENTION = re.compile(r"#image(\d+)\b", re.IGNORECASE)


def motion_control_endpoint(model: str | None) -> str:
    """The fal endpoint to poll for a job: its stored model when it is one of
    the Motion Control endpoints (Kling or Recast), else v2.6 (rows from
    before the tier choice)."""
    if model == RECAST_ENDPOINT:
        return model
    return model if model in _MOTION_TIER_BY_ENDPOINT else VIDEO_MODEL


def motion_control_tier_for_model(model: str | None) -> str:
    """The tier a job was priced on, from its stored endpoint (NULL is v2.6).
    A Recast job without options is priced at its dearest tier."""
    endpoint = motion_control_endpoint(model)
    if endpoint == RECAST_ENDPOINT:
        return "recast-1080p"
    return _MOTION_TIER_BY_ENDPOINT[endpoint]


def motion_job_tier(job) -> str:
    """The price tier of a Motion Control job: its stored option (Recast),
    else the tier of its endpoint."""
    options = getattr(job, "options", None)
    tier = options.get("tier") if isinstance(options, dict) else None
    return tier or motion_control_tier_for_model(getattr(job, "model", None))


def build_recast_arguments(video_url: str, reference_image_urls: list[str], resolution: str,
                           prompt: str | None = None, enhance_realism: bool = False) -> dict:
    """fal arguments for minimax/h3-max/recast. Raises ValueError with a
    message fit for the user."""
    res = (resolution or "").lower()
    if res not in RECAST_FAL_RESOLUTIONS:
        raise ValueError("Resolution must be 768p or 1080p")
    refs = [u for u in reference_image_urls if u]
    if not 1 <= len(refs) <= RECAST_MAX_REFERENCES:
        raise ValueError(f"Add one to {RECAST_MAX_REFERENCES} photos, one per person to replace.")
    text = (prompt or "").strip()
    if len(text) > MOTION_PROMPT_MAX_CHARS:
        raise ValueError(f"The prompt is too long. Keep it under {MOTION_PROMPT_MAX_CHARS} characters.")
    # Photos are referenced as #Image1 to #Image4, in the order sent. Normalise
    # the casing fal documents and refuse a mention of a photo that is not there.
    text = RECAST_IMAGE_MENTION.sub(lambda m: f"#Image{m.group(1)}", text)
    missing = sorted({int(n) for n in RECAST_IMAGE_MENTION.findall(text) if not 1 <= int(n) <= len(refs)})
    if missing:
        names = ", ".join(f"#Image{n}" for n in missing)
        raise ValueError(
            f"The prompt mentions {names}, but there {'is' if len(refs) == 1 else 'are'} only {len(refs)} "
            f"photo{'' if len(refs) == 1 else 's'} (#Image1{f' to #Image{len(refs)}' if len(refs) > 1 else ''})."
        )
    arguments = {
        "video_url": video_url,
        "reference_image_urls": refs,
        "resolution": RECAST_FAL_RESOLUTIONS[res],
        "enhance_realism": bool(enhance_realism),
        "enable_safety_checker": True,
    }
    if text:
        arguments["prompt"] = text
    return arguments


def submit_recast(arguments: dict, db: Session) -> dict:
    """Submit an H3 Max Recast job; returns {"request_id", "model"} like
    submit_video_generation."""
    is_valid, error = validate_video_url(arguments.get("video_url") or "")
    if not is_valid:
        raise ValueError(f"Invalid source video URL: {error}")
    for url in arguments.get("reference_image_urls") or []:
        is_valid, error = validate_url(url, allow_data_urls=False)
        if not is_valid:
            raise ValueError(f"Invalid reference photo URL: {error}")
    handler = fal_submit(RECAST_ENDPOINT, arguments, db)
    _logger.info(f"Recast job submitted to fal: {handler.request_id}")
    return {"request_id": handler.request_id, "model": RECAST_ENDPOINT}


def build_motion_control_arguments(
    source_image_url: str,
    motion_reference_url: str,
    character_orientation: str,
    tier: str = MOTION_CONTROL_DEFAULT_TIER,
    prompt: str | None = None,
    keep_original_sound: bool = True,
    face_image_url: str | None = None,
) -> dict:
    """fal arguments for a Motion Control job. Raises ValueError with a
    message fit for the user when the combination is not allowed."""
    import re

    cfg = MOTION_CONTROL_TIERS.get(tier)
    if cfg is None:
        raise ValueError(f"Unknown model '{tier}'. Choose one of: {', '.join(MOTION_CONTROL_TIERS)}")
    if character_orientation not in MOTION_CONTROL_MAX_SECONDS:
        raise ValueError("character_orientation must be 'video' or 'image'")

    text = (prompt or "").strip()
    if len(text) > MOTION_PROMPT_MAX_CHARS:
        raise ValueError(f"The prompt is too long. Keep it under {MOTION_PROMPT_MAX_CHARS} characters.")

    arguments: dict = {
        "image_url": source_image_url,
        "video_url": motion_reference_url,
        "character_orientation": character_orientation,
        "keep_original_sound": bool(keep_original_sound),
    }

    if face_image_url:
        if not cfg["supports_elements"]:
            raise ValueError(
                f"Face lock needs a Kling V3 model. {cfg['label']} does not support it: "
                "choose V3 Standard or V3 Pro, or remove the face image."
            )
        if character_orientation != "video":
            raise ValueError(
                "Face lock only works with the 'Match the video' orientation. Switch the "
                "orientation to video, or remove the face image."
            )
        # fal rejects an element without reference_image_urls ("Both
        # frontal_image_url and reference_image_urls are required"); with a single
        # face photo, it serves as both the frontal view and the reference.
        arguments["elements"] = [{"frontal_image_url": face_image_url, "reference_image_urls": [face_image_url]}]
        # fal binds the element through the prompt. Normalise a differently
        # cased mention, or append one when the user did not write it.
        if re.search(r"@element1\b", text, flags=re.IGNORECASE):
            text = re.sub(r"@element1\b", MOTION_ELEMENT_TOKEN, text, flags=re.IGNORECASE)
        else:
            text = f"{text} {MOTION_ELEMENT_SENTENCE}".strip() if text else MOTION_ELEMENT_SENTENCE

    if text:
        arguments["prompt"] = text
    return arguments


def validate_video_url(url: str) -> tuple[bool, str]:
    """
    Validate video URL for motion control.
    Videos must be https URLs or this app's own /static/ files (not base64 data URLs).
    """
    if not url:
        return False, "URL is empty"

    if url.startswith("/"):
        if _is_own_static_url(url):
            return True, ""
        return False, "Only this app's own /static/ files can be used"

    # Video URLs cannot be data URLs (too large)
    if url.startswith("data:"):
        return False, "Video must be a hosted URL, not a data URL"

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Failed to parse URL"

    # Check scheme
    if parsed.scheme != "https":
        return False, "Video URL must use HTTPS"

    # Check for blocked hostnames
    hostname = parsed.hostname or ""
    if hostname.lower() in BLOCKED_HOSTNAMES:
        return False, f"Hostname '{hostname}' is blocked"

    # Check for blocked IP prefixes
    for prefix in BLOCKED_IP_PREFIXES:
        if hostname.startswith(prefix):
            return False, f"IP address '{hostname}' is in a blocked range"

    return True, ""


def submit_video_generation(
    source_image_url: str,
    motion_reference_url: str,
    db: Session,
    character_orientation: str = "video",
    tier: str = MOTION_CONTROL_DEFAULT_TIER,
    prompt: str | None = None,
    keep_original_sound: bool = True,
    face_image_url: str | None = None,
) -> dict:
    """Submit an async Motion Control job to FAL on a tier's endpoint.

    Args:
        source_image_url: URL or base64 data URL of the character image
        motion_reference_url: URL of the motion reference video (hosted URL)
        character_orientation: "video" to match the reference video (complex
                               motion, up to 30 s), "image" to match the
                               character image (camera-led shots, up to 10 s)
        tier: "v3-standard" (default), "v3-pro" or "v2.6"
        prompt: Optional scene description
        keep_original_sound: Carry the reference video's audio through
        face_image_url: Optional face element (V3 tiers, orientation "video")

    Returns:
        dict with request_id and model (the endpoint, to store on the job)
    """
    # SECURITY: Validate source image URL
    is_valid, error = validate_url(source_image_url)
    if not is_valid:
        raise ValueError(f"Invalid source image URL: {error}")

    # SECURITY: Validate motion reference URL (must be hosted video)
    is_valid, error = validate_video_url(motion_reference_url)
    if not is_valid:
        raise ValueError(f"Invalid motion reference URL: {error}")

    if face_image_url:
        is_valid, error = validate_url(face_image_url, allow_data_urls=False)
        if not is_valid:
            raise ValueError(f"Invalid face image URL: {error}")

    arguments = build_motion_control_arguments(
        source_image_url,
        motion_reference_url,
        character_orientation,
        tier=tier,
        prompt=prompt,
        keep_original_sound=keep_original_sound,
        face_image_url=face_image_url,
    )
    endpoint = MOTION_CONTROL_TIERS[tier]["endpoint"]

    _logger.debug("\n=== Video Generation (Motion Control) ===")
    _logger.debug(f"Model: {endpoint}")
    _logger.debug(f"Image URL: {source_image_url[:100]}...")
    _logger.debug(f"Video URL: {motion_reference_url[:100]}...")
    _logger.debug(f"Character orientation: {character_orientation}")
    _logger.debug(f"Face element: {'yes' if face_image_url else 'no'}, keep sound: {arguments['keep_original_sound']}")

    try:
        handler = fal_submit(endpoint, arguments, db)
        _logger.debug(f"Job submitted successfully. Request ID: {handler.request_id}")
        return {
            "request_id": handler.request_id,
            "model": endpoint,
        }
    except Exception as e:
        _logger.warning(f"FAL submit error: {e}")
        raise


def get_video_generation_status(request_id: str, db: Session, model: str | None = None) -> dict:
    """Check status of a Motion Control job on the endpoint it was submitted
    to (``model``, the job's stored endpoint; NULL for older rows is v2.6).

    Returns:
        dict with status, logs, and progress info
    """
    client = get_sync_client(db)

    try:
        status = client.status(motion_control_endpoint(model), request_id, with_logs=True)

        # Parse status - FAL returns status objects like InQueue, InProgress, Completed
        status_str = "pending"
        status_type = type(status).__name__

        # Check by class name
        if status_type == "Completed" or status_type == "CompletedStatus":
            status_str = "COMPLETED"
        elif status_type == "InProgress" or status_type == "InProgressStatus":
            status_str = "IN_PROGRESS"
        elif status_type == "InQueue" or status_type == "InQueueStatus" or status_type == "Queued":
            status_str = "IN_QUEUE"

        # Also check if there's a status attribute
        if hasattr(status, "status"):
            attr_status = str(status.status).upper()
            if "COMPLETE" in attr_status:
                status_str = "COMPLETED"
            elif "PROGRESS" in attr_status:
                status_str = "IN_PROGRESS"
            elif "QUEUE" in attr_status:
                status_str = "IN_QUEUE"

        logs = []
        if hasattr(status, "logs") and status.logs:
            logs = [log.get("message", "") if isinstance(log, dict) else str(log) for log in status.logs]

        return {
            "status": status_str,
            "logs": logs,
            "in_queue": status_str == "IN_QUEUE",
            "in_progress": status_str == "IN_PROGRESS",
            "completed": status_str == "COMPLETED",
        }
    except Exception as e:
        return _status_check_failed(request_id, e)


def get_video_generation_result(request_id: str, db: Session, model: str | None = None) -> dict:
    """Fetch the result of a completed Motion Control job from the endpoint it
    was submitted to (``model``; NULL for older rows is v2.6).

    Returns:
        dict with video URL and metadata
    """
    return get_sync_client(db).result(motion_control_endpoint(model), request_id)


# Ceiling for a downloaded result video; well above a 15s 720p clip.
VIDEO_DOWNLOAD_MAX_BYTES = 500 * 1024 * 1024


def _probe_and_thumbnail(video_content: bytes) -> dict:
    """ffprobe the video and take its first frame as a thumbnail. Blocking; both are
    optional, so a failure leaves that part empty."""
    import subprocess
    import tempfile

    duration = None
    width = None
    height = None
    fps = None
    thumb_content = None

    # We need a temp file for ffprobe/ffmpeg to extract metadata and thumbnail
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(video_content)
        tmp_path = tmp.name

    try:
        try:
            probe_result = subprocess.run([
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-show_format",
                tmp_path
            ], capture_output=True, text=True, timeout=30, env=scrubbed_env())

            if probe_result.returncode == 0:
                probe_data = json.loads(probe_result.stdout)

                # Get format duration
                if "format" in probe_data:
                    duration = float(probe_data["format"].get("duration", 0))

                # Get video stream info
                for stream in probe_data.get("streams", []):
                    if stream.get("codec_type") == "video":
                        width = stream.get("width")
                        height = stream.get("height")
                        # Parse fps from r_frame_rate (e.g., "30/1")
                        fps_str = stream.get("r_frame_rate", "")
                        if "/" in fps_str:
                            num, denom = fps_str.split("/")
                            if int(denom) > 0:
                                fps = int(int(num) / int(denom))
                        break

                _logger.debug(f"Video metadata: {width}x{height}, {duration:.2f}s, {fps}fps")
        except Exception as e:
            _logger.warning(f"Failed to get video metadata: {e}")

        # Generate thumbnail (first frame) using ffmpeg
        thumb_tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as thumb_tmp:
                thumb_tmp_path = thumb_tmp.name

            subprocess.run([
                "ffmpeg", "-y", "-i", tmp_path,
                "-vframes", "1",
                "-q:v", "2",
                thumb_tmp_path
            ], capture_output=True, check=True, timeout=30, env=scrubbed_env())

            with open(thumb_tmp_path, "rb") as f:
                thumb_content = f.read()
        except Exception as e:
            _logger.warning(f"Failed to generate thumbnail: {e}")
        finally:
            if thumb_tmp_path and os.path.exists(thumb_tmp_path):
                os.unlink(thumb_tmp_path)

    finally:
        # Cleanup temp video file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return {"duration": duration, "width": width, "height": height, "fps": fps, "thumbnail": thumb_content}


async def download_and_save_video(result: dict, user_id: int | None = None) -> dict:
    """Download video from FAL result and save to storage.

    Also generates a thumbnail from the first frame using ffmpeg.

    Args:
        result: FAL API result containing video
        user_id: User ID for organizing files by user folder

    Returns:
        dict with filename, url, thumbnail_filename, thumbnail_url,
        duration_seconds, width, height, file_size_bytes
    """
    from app.services.storage_service import storage_service
    from app.services.url_fetch import afetch_bytes

    # FAL returns video in result.video.url
    video_data = result.get("video", {})
    video_url = video_data.get("url") if isinstance(video_data, dict) else None

    if not video_url:
        raise ValueError("No video URL in result")

    # Generate unique filenames
    filename = f"motion_{uuid.uuid4()}.mp4"
    thumbnail_filename = f"thumb_{uuid.uuid4()}.jpg"

    _logger.debug(f"Downloading video from FAL...")

    # Download video with longer timeout for large files
    video_content = await afetch_bytes(video_url, max_bytes=VIDEO_DOWNLOAD_MAX_BYTES, timeout=300)  # 5 min timeout

    file_size = len(video_content)
    _logger.debug(f"Video downloaded: {filename} ({file_size / 1024 / 1024:.2f} MB)")

    # Blocking subprocesses: off the event loop.
    probed = await asyncio.to_thread(_probe_and_thumbnail, video_content)
    duration, width, height, fps = probed["duration"], probed["width"], probed["height"], probed["fps"]
    thumb_content = probed["thumbnail"]
    if thumb_content is None:
        thumbnail_filename = None

    # Upload video to storage (organized by user folder)
    video_url = await storage_service.upload_file(
        file_data=video_content,
        filename=filename,
        storage_type="videos",
        content_type="video/mp4",
        user_id=user_id,
    )

    # Upload thumbnail to storage (organized by user folder)
    thumbnail_url = None
    if thumb_content and thumbnail_filename:
        thumbnail_url = await storage_service.upload_file(
            file_data=thumb_content,
            filename=thumbnail_filename,
            storage_type="thumbnails",
            content_type="image/jpeg",
            user_id=user_id,
        )

    return {
        "filename": filename,
        "url": video_url,
        "thumbnail_filename": thumbnail_filename,
        "thumbnail_url": thumbnail_url,
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "file_size_bytes": file_size,
    }


# =============================================================================
# STORY GENERATION - MiniMax H3 Max, Seedance 2.5 US, Kling v4, FLUX 3 Max,
# Gemini Omni Flash 1.1 (Text / Image / Reference / Keyframes to Video)
# =============================================================================

STORY_TEXT_TO_VIDEO_MODEL = "bytedance/seedance-2.5/us/text-to-video"
STORY_IMAGE_TO_VIDEO_MODEL = "bytedance/seedance-2.5/us/image-to-video"
STORY_REFERENCE_TO_VIDEO_MODEL = "bytedance/seedance-2.5/us/reference-to-video"

# Seedance 2.5 endpoints by app mode (the default family).
STORY_MODELS = {
    "text-to-video": STORY_TEXT_TO_VIDEO_MODEL,
    "image-to-video": STORY_IMAGE_TO_VIDEO_MODEL,
    "reference-to-video": STORY_REFERENCE_TO_VIDEO_MODEL,
}

# Jobs submitted before StoryGenerationJob.model existed all went to Seedance
# 2.0 Fast, and must be polled on the endpoint that accepted them.
LEGACY_STORY_MODELS = {
    "text-to-video": "bytedance/seedance-2.0/fast/text-to-video",
    "image-to-video": "bytedance/seedance-2.0/fast/image-to-video",
    "reference-to-video": "bytedance/seedance-2.0/fast/reference-to-video",
}


def story_model_for_job(job) -> str:
    """The FAL endpoint a story job was submitted to."""
    if getattr(job, "model", None):
        return job.model
    return LEGACY_STORY_MODELS.get(job.mode or "text-to-video", LEGACY_STORY_MODELS["text-to-video"])


# Requests without video_model use this family (the fastest).
DEFAULT_STORY_VIDEO_MODEL = "h3-max"

_SEEDANCE_ASPECTS = ["auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]
_KLING_ASPECTS = ["16:9", "9:16", "1:1", "21:9"]
_FLUX_MAX_ASPECTS = ["auto", "21:9", "2:1", "16:9", "4:3", "1:1", "3:4", "9:16"]
_H3_ASPECTS = ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]

# Video model families offered by Stories. Every family has three app modes:
# text-to-video, image-to-video (first frame plus optional last frame) and a
# third that differs per family: reference-to-video for H3 Max, Seedance,
# Kling and Omni Flash, keyframes for FLUX 3 Max.
#   label                 name shown to users and given to the prompt enhancer
#   pricing_family        family id for pricing.video_key()
#   endpoints             app mode -> fal endpoint
#   durations             accepted durations as the app sends them (strings)
#   duration_type         "string", "integer" or "number": how fal wants it
#   default_duration      used when a request leaves duration out
#   auto_reserve_seconds  seconds estimated for "auto"; the recorded cost follows
#                         the real length of the result
#   resolutions           accepted resolutions, lowercase as in the price keys
#   resolution_values     app resolution -> fal value, when fal spells it
#                         differently (H3 Max wants "768P")
#   default_resolution    used when a request leaves resolution out; always
#                         sent explicitly because fal defaults differ
#   aspect_ratios         app mode -> accepted values, None when the endpoint
#                         has no aspect_ratio field
#   audio / seed / end_user_id   whether those fields are sent (audio: the
#                         generate_audio switch)
#   native_audio          the clip comes with sound and speech; the prompt
#                         enhancer may write dialogue
#   extra                 constant fields sent with every request
#   prompt_expansion_field  the model's prompt rewriting switch (H3 Max):
#                         "balanced" or "disabled", see build_story_arguments
#   start_field, end_field       first and last frame fields (image-to-video)
#   start_required        image-to-video needs the first frame; otherwise
#                         either frame will do
#   target_audio_field    soundtrack pinned to the clip (text and image modes)
#   reference_fields      reference kind -> field name (reference-to-video)
#   reference_start_field optional first frame in reference mode; counts as
#                         an image reference
#   max_references        reference kind -> count, "total" across kinds
#   requires_reference    reference mode needs at least one reference
#   audio_needs_visual    reference audio needs an image or video reference
#   reference_tokens      reference-token pricing (H3 Max): tokens included per
#                         request and the worst-case tokens per input, used for
#                         the estimate; the recorded cost uses the tokens fal reports
#   video_reference_pricing  reference videos change the bill (Kling v4,
#                         Seedance): the per-second rate of
#                         pricing.video_ref_key on the input plus the
#                         output length, at least min_output_multiple times the
#                         output; unmeasured inputs count as max_input_seconds
#   keyframes_fps, max_keyframes  keyframes mode
# Schemas: https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<endpoint>
STORY_VIDEO_MODELS = {
    "h3-max": {
        "label": "MiniMax H3 Max",
        "pricing_family": "h3-max",
        "endpoints": {
            "text-to-video": "minimax/h3-max/text-to-video",
            "image-to-video": "minimax/h3-max/image-to-video",
            "reference-to-video": "minimax/h3-max/reference-to-video",
        },
        # fal takes 0.92 to 15 s; the app offers whole seconds from 2 (the
        # minimum with a pinned soundtrack). The clip can run up to 0.7 s
        # longer; fal bills the requested length and so does the app.
        "durations": [str(n) for n in range(2, 16)],
        "duration_type": "number",
        "default_duration": "5",
        "auto_reserve_seconds": None,
        "resolutions": ["480p", "768p", "1080p"],
        "resolution_values": {"480p": "480P", "768p": "768P", "1080p": "1080P"},
        "default_resolution": "768p",
        "aspect_ratios": {
            "text-to-video": _H3_ASPECTS,
            "image-to-video": None,
            "reference-to-video": ["adaptive"] + _H3_ASPECTS,
        },
        "audio": False,
        "native_audio": True,
        "seed": True,
        "end_user_id": False,
        "extra": {},
        # fal requires the field. Engineered prompts (enhanced, Story Room,
        # Faceless) must reach the model verbatim, so it is "disabled" unless
        # the caller asks for rewriting (build_story_arguments).
        "prompt_expansion_field": "prompt_expansion_mode",
        "start_field": "image_url",
        "end_field": "end_image_url",
        "start_required": False,
        "target_audio_field": "target_audio_url",
        "reference_fields": {
            "images": "reference_image_urls",
            "videos": "reference_video_urls",
            "audios": "reference_audio_urls",
        },
        "reference_start_field": None,
        # Videos and audio are also limited to 2 to 15 s each and 15 s
        # combined per kind; fal enforces that.
        "max_references": {"images": 9, "videos": 3, "audios": 3, "total": 12},
        "requires_reference": True,
        "audio_needs_visual": False,
        # Each request includes 4,096 reference tokens; more cost $0.02 per
        # 1,000 (pricing key video:h3-max:reference-1k-tokens). fal's
        # table: an image is 1,024 tokens square, up to 2,560 at 5:2 (the
        # widest accepted); a 16:9 video reference is 39,780 tokens for 15 s
        # at 480p and 102,816 at 768p or 1080p (about 2,652 and 6,855 per
        # second, in steps); audio about 80 per second. The estimate uses
        # those worst cases, over the measured length of signed uploads or the
        # 15 s combined maximum of each kind; the recorded cost uses the tokens
        # fal reports.
        "reference_tokens": {
            "included": 4096,
            "per_image": 2560,
            "per_video_second": {"480p": 2652, "768p": 6855, "1080p": 6855},
            "per_audio_second": 256,
            "max_video_seconds": 15,
            "max_audio_seconds": 15,
        },
    },
    "seedance-2.5": {
        "label": "Seedance 2.5",
        "pricing_family": "seedance-2.5",
        "endpoints": dict(STORY_MODELS),
        # 2.5 also offers 1080p and explicit lengths up to 30s; they stay off
        # until they are priced and offered in the UI.
        "durations": ["auto"] + [str(n) for n in range(4, 16)],
        "duration_type": "string",
        "default_duration": "auto",
        # fal publishes no cap for "auto", which can run to the model's 30s.
        "auto_reserve_seconds": 30,
        "resolutions": ["480p", "720p"],
        "default_resolution": "720p",
        "aspect_ratios": {
            "text-to-video": _SEEDANCE_ASPECTS,
            # fal's schema allows only "auto": the clip follows the start frame.
            "image-to-video": None,
            "reference-to-video": _SEEDANCE_ASPECTS,
        },
        "audio": True,
        "seed": False,
        "end_user_id": True,
        "extra": {},
        "start_field": "image_url",
        "end_field": "end_image_url",
        "reference_fields": {"images": "image_urls", "videos": "video_urls", "audios": "audio_urls"},
        "reference_start_field": None,
        "max_references": {"images": 9, "videos": 3, "audios": 3, "total": 12},
        "requires_reference": False,
        # 2.5 takes reference audio alone (fal's schema requires no visual).
        "audio_needs_visual": False,
        # With reference videos fal bills 0.6x the rate on the input plus the
        # output length; the inputs may total 30.2 s.
        "video_reference_pricing": {"max_input_seconds": 31, "min_output_multiple": 1},
    },
    "kling-v4": {
        "label": "Kling v4",
        "pricing_family": "kling-v4",
        "endpoints": {
            "text-to-video": "kling/v4/text-to-video",
            "image-to-video": "kling/v4/image-to-video",
            "reference-to-video": "kling/v4/reference-to-video",
        },
        "durations": [str(n) for n in range(3, 31)],
        "duration_type": "integer",
        "default_duration": "5",
        "auto_reserve_seconds": None,
        "resolutions": ["720p", "1080p"],
        "default_resolution": "1080p",
        "aspect_ratios": {
            "text-to-video": _KLING_ASPECTS,
            "image-to-video": None,
            "reference-to-video": ["auto"] + _KLING_ASPECTS,
        },
        "audio": False,
        "seed": False,
        "end_user_id": False,
        "extra": {},
        "start_field": "start_image_url",
        "end_field": "end_image_url",
        "reference_fields": {"images": "image_urls", "videos": "video_urls"},
        "reference_start_field": "start_image_url",
        # Videos are also limited to 3 to 30s each and 30s combined; fal
        # enforces that, the app cannot measure remote files cheaply.
        "max_references": {"images": 10, "videos": 5, "audios": 0, "total": 15},
        "requires_reference": True,
        # With reference videos fal bills a lower rate on the input plus the
        # output length, at least twice the output; the inputs total 30 s at most.
        "video_reference_pricing": {"max_input_seconds": 30, "min_output_multiple": 2},
    },
    "flux-3-max": {
        "label": "FLUX 3 Max",
        "pricing_family": "flux-3-max",
        "endpoints": {
            "text-to-video": "blackforestlabs/flux-3-max/text-to-video",
            "image-to-video": "blackforestlabs/flux-3-max/image-to-video",
            "keyframes": "blackforestlabs/flux-3-max/keyframes-to-video",
        },
        "durations": [str(n) for n in range(5, 21)],
        "duration_type": "integer",
        "default_duration": "5",
        "auto_reserve_seconds": None,
        "resolutions": ["720p", "1080p"],
        "default_resolution": "720p",
        "aspect_ratios": {
            "text-to-video": _FLUX_MAX_ASPECTS,
            "image-to-video": _FLUX_MAX_ASPECTS,
            "keyframes": _FLUX_MAX_ASPECTS,
        },
        "audio": True,
        "seed": True,
        "end_user_id": False,
        # The quality setting: more reasoning about the prompt, slower render.
        "extra": {"reasoning_level": "high"},
        "start_field": "image_url",
        "end_field": "end_image_url",
        "keyframes_fps": 24,
        "max_keyframes": 10,
    },
    "omni-flash": {
        "label": "Gemini Omni Flash",
        "pricing_family": "omni-flash",
        "endpoints": {
            "text-to-video": "google/gemini-omni-flash/v1.1/text-to-video",
            "image-to-video": "google/gemini-omni-flash/v1.1/image-to-video",
            "reference-to-video": "google/gemini-omni-flash/v1.1/reference-to-video",
        },
        # fal bills output seconds; with a fixed length that is the request.
        "durations": [str(n) for n in range(3, 11)],
        "duration_type": "integer",
        "default_duration": "8",
        "auto_reserve_seconds": None,
        "resolutions": ["360p", "720p", "1080p", "4k"],
        "default_resolution": "720p",
        "aspect_ratios": {
            "text-to-video": ["16:9", "9:16"],
            "image-to-video": ["16:9", "9:16"],
            "reference-to-video": ["16:9", "9:16"],
        },
        # No generate_audio switch, but every clip has synchronized audio.
        "audio": False,
        "native_audio": True,
        "seed": False,
        "end_user_id": False,
        "extra": {},
        "start_field": "image_url",
        "end_field": "end_image_url",
        "reference_fields": {"images": "image_urls", "videos": "reference_video_urls"},
        "reference_start_field": None,
        # Reference videos are also limited to 10 s each; fal enforces that.
        # The prompt names references as <IMAGE_REF_0>, <VIDEO_REF_0>.
        "max_references": {"images": 10, "videos": 3, "audios": 0, "total": 13},
        "requires_reference": True,
    },
}


def story_family_config(video_model: str | None) -> dict:
    """Config for a Stories video model family; ValueError when unknown."""
    family = video_model or DEFAULT_STORY_VIDEO_MODEL
    cfg = STORY_VIDEO_MODELS.get(family)
    if cfg is None:
        raise ValueError(
            f"Unknown video model '{family}'. Choose one of: {', '.join(STORY_VIDEO_MODELS)}"
        )
    return cfg


def story_family_for_endpoint(endpoint: str | None) -> str | None:
    """The Stories family an endpoint belongs to (None for retired endpoints)."""
    for family, cfg in STORY_VIDEO_MODELS.items():
        if endpoint in cfg["endpoints"].values():
            return family
    return None


def _describe_durations(cfg: dict) -> str:
    seconds = [int(d) for d in cfg["durations"] if d != "auto"]
    text = f"{min(seconds)} to {max(seconds)} seconds"
    return f"auto or {text}" if "auto" in cfg["durations"] else text


def resolve_story_options(
    video_model: str | None,
    mode: str | None,
    duration: str | int | None,
    resolution: str | None,
    aspect_ratio: str | None,
) -> dict:
    """Validate a request's options against its family and fill in defaults.

    Raises ValueError with a message fit for a 400 response.
    """
    family = video_model or DEFAULT_STORY_VIDEO_MODEL
    cfg = story_family_config(family)
    label = cfg["label"]

    mode = mode or "text-to-video"
    if mode not in cfg["endpoints"]:
        raise ValueError(
            f"{label} does not support mode '{mode}'. Supported modes: {', '.join(cfg['endpoints'])}"
        )

    duration = cfg["default_duration"] if duration in (None, "") else str(duration).strip()
    if duration not in cfg["durations"]:
        if duration == "auto":
            raise ValueError(f"{label} does not support auto duration. Choose {_describe_durations(cfg)}.")
        raise ValueError(f"Duration for {label} must be {_describe_durations(cfg)}.")

    resolution = resolution or cfg["default_resolution"]
    if resolution not in cfg["resolutions"]:
        raise ValueError(f"Resolution for {label} must be one of: {', '.join(cfg['resolutions'])}")

    aspects = cfg["aspect_ratios"][mode]
    if aspects is None:
        # The endpoint follows the start image; nothing to send.
        aspect_ratio = None
    else:
        if not aspect_ratio:
            aspect_ratio = next((a for a in ("auto", "adaptive", "16:9") if a in aspects), aspects[0])
        if aspect_ratio not in aspects:
            raise ValueError(
                f"Aspect ratio for {label} {mode} must be one of: {', '.join(aspects)}"
            )

    return {
        "family": family,
        "label": label,
        "mode": mode,
        "endpoint": cfg["endpoints"][mode],
        "duration": duration,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
    }


def story_keyframes_to_frames(keyframes: list[dict], duration_seconds: int, fps: int, max_count: int) -> list[dict]:
    """Turn [{image_url, time_seconds}] into fal keyframes [{image_url, frame_index}].

    frame_index = round(seconds * fps). The first keyframe defaults to 0s;
    every later one needs a time. Indexes must be unique and at most
    duration * fps.
    """
    if not keyframes:
        raise ValueError("Keyframes mode needs at least one keyframe image")
    if len(keyframes) > max_count:
        raise ValueError(f"Maximum {max_count} keyframes allowed")

    frames: list[dict] = []
    seen: dict[int, int] = {}
    last_frame = duration_seconds * fps
    for i, kf in enumerate(keyframes, start=1):
        url = (kf or {}).get("image_url")
        if not url:
            raise ValueError(f"Keyframe {i} has no image")
        seconds = kf.get("time_seconds")
        if seconds is None:
            if i != 1:
                raise ValueError(f"Keyframe {i} needs a time in seconds")
            seconds = 0
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            raise ValueError(f"Keyframe {i} time must be a number of seconds")
        if seconds < 0 or seconds > duration_seconds:
            raise ValueError(
                f"Keyframe {i} at {seconds:g}s is outside the {duration_seconds}s video"
            )
        frame_index = min(int(round(seconds * fps)), last_frame)
        if frame_index in seen:
            raise ValueError(
                f"Keyframes {seen[frame_index]} and {i} land on the same frame; "
                f"space them at least 1/{fps} s apart"
            )
        seen[frame_index] = i
        frames.append({"image_url": url, "frame_index": frame_index})

    frames.sort(key=lambda f: f["frame_index"])
    return frames


def build_story_arguments(
    options: dict,
    prompt: str,
    generate_audio: bool = True,
    image_url: str | None = None,
    end_image_url: str | None = None,
    image_urls: list[str] | None = None,
    video_urls: list[str] | None = None,
    audio_urls: list[str] | None = None,
    keyframes: list[dict] | None = None,
    end_user_id: str | None = None,
    seed: int | None = None,
    target_audio_url: str | None = None,
    prompt_expansion: bool | None = None,
) -> dict:
    """fal arguments for a resolved story request (see resolve_story_options).

    Sends only the fields the family's endpoint lists. Raises ValueError for
    missing or excess inputs. ``prompt_expansion`` lets a family that
    rewrites prompts (H3 Max) do so; only True turns it on, so internal
    callers that leave it out send their wording verbatim.
    """
    cfg = STORY_VIDEO_MODELS[options["family"]]
    label = cfg["label"]
    mode = options["mode"]
    duration = options["duration"]

    resolution = cfg.get("resolution_values", {}).get(options["resolution"], options["resolution"])
    arguments: dict = {"prompt": prompt, "resolution": resolution}
    if cfg["duration_type"] in ("integer", "number") and duration != "auto":
        arguments["duration"] = int(duration)
    else:
        arguments["duration"] = duration
    if options["aspect_ratio"] is not None:
        arguments["aspect_ratio"] = options["aspect_ratio"]
    if cfg["audio"]:
        arguments["generate_audio"] = bool(generate_audio)
    if cfg["seed"] and seed is not None:
        arguments["seed"] = seed
    arguments.update(cfg["extra"])
    if cfg.get("prompt_expansion_field"):
        arguments[cfg["prompt_expansion_field"]] = "balanced" if prompt_expansion is True else "disabled"

    if target_audio_url:
        if not cfg.get("target_audio_field") or mode not in ("text-to-video", "image-to-video"):
            raise ValueError(f"{label} {mode} does not take a soundtrack (target_audio_url)")
        arguments[cfg["target_audio_field"]] = target_audio_url

    if mode == "image-to-video":
        if cfg.get("start_required", True):
            if not image_url:
                raise ValueError("A start image (image_url) is required for image-to-video mode")
        elif not (image_url or end_image_url):
            raise ValueError(f"{label} image-to-video needs a start image, an end image, or both")
        if image_url:
            arguments[cfg["start_field"]] = image_url
        if end_image_url:
            arguments[cfg["end_field"]] = end_image_url

    elif mode == "reference-to-video":
        refs = {"images": image_urls or [], "videos": video_urls or [], "audios": audio_urls or []}
        limits = cfg["max_references"]
        start = image_url if cfg.get("reference_start_field") else None
        image_count = len(refs["images"]) + (1 if start else 0)
        if image_count > limits["images"]:
            extra = " including the start image" if start else ""
            raise ValueError(f"{label} accepts at most {limits['images']} reference images{extra}")
        if len(refs["videos"]) > limits["videos"]:
            raise ValueError(f"{label} accepts at most {limits['videos']} reference videos")
        if refs["audios"] and not limits.get("audios"):
            raise ValueError(f"{label} does not accept reference audio")
        if len(refs["audios"]) > limits.get("audios", 0):
            raise ValueError(f"{label} accepts at most {limits['audios']} reference audio files")
        if cfg.get("audio_needs_visual", True) and refs["audios"] and not (refs["images"] or refs["videos"]):
            raise ValueError("Audio references require at least one image or video reference")
        if image_count + len(refs["videos"]) + len(refs["audios"]) > limits["total"]:
            raise ValueError(f"{label} accepts at most {limits['total']} reference files in total")
        if cfg.get("requires_reference") and not (image_count or refs["videos"] or refs["audios"]):
            kinds = "image, video or audio clip" if limits.get("audios") else "image or video"
            raise ValueError(f"{label} reference mode needs at least one reference {kinds}")
        for kind, field in cfg["reference_fields"].items():
            if refs.get(kind):
                arguments[field] = list(refs[kind])
        if start:
            arguments[cfg["reference_start_field"]] = start

    elif mode == "keyframes":
        arguments["keyframes"] = story_keyframes_to_frames(
            keyframes or [], int(duration), cfg["keyframes_fps"], cfg["max_keyframes"]
        )

    if cfg["end_user_id"] and end_user_id:
        arguments["end_user_id"] = end_user_id
    return arguments


def submit_story_job(
    endpoint: str,
    arguments: dict,
    db: Session,
) -> str:
    """Submit a story job to fal and return its request id."""
    refs = {k: len(v) for k, v in arguments.items() if isinstance(v, list)}
    _logger.debug(f"\n=== Story Generation ({endpoint}) ===")
    _logger.debug(f"Prompt: {str(arguments.get('prompt', ''))[:100]}...")
    _logger.debug(
        f"Duration: {arguments.get('duration')}, Resolution: {arguments.get('resolution')}, "
        f"Aspect: {arguments.get('aspect_ratio')}, Audio: {arguments.get('generate_audio')}, Inputs: {refs}"
    )

    try:
        handler = fal_submit(endpoint, arguments, db)
        _logger.debug(f"Job submitted. Request ID: {handler.request_id}")
        return handler.request_id
    except Exception as e:
        _logger.warning(f"FAL submit error: {e}")
        raise


# -----------------------------------------------------------------------------
# Story pricing: USD per second of video, by family and resolution, from
# app.services.pricing.
# -----------------------------------------------------------------------------

def story_reserved_seconds(family: str, duration: str) -> int:
    """Seconds a job is estimated at: the length, or the longest auto length."""
    cfg = story_family_config(family)
    if duration == "auto":
        return int(cfg["auto_reserve_seconds"])
    return int(duration)


def story_usd_per_second(family: str, resolution: str) -> float:
    cfg = story_family_config(family)
    return usd_for(video_key(cfg["pricing_family"], resolution))


def story_reference_tokens_key(family: str) -> str:
    """Price key for reference tokens beyond a request's allowance (per 1,000)."""
    return f"video:{story_family_config(family)['pricing_family']}:reference-1k-tokens"


def _measured_seconds(seconds: list[float | None] | None, count: int, cap: float) -> float:
    """Combined length of `count` reference clips for an estimate: the sum
    of the measured lengths, or `cap` when any is unknown; never above `cap`."""
    if count <= 0:
        return 0.0
    known = [float(s) for s in (seconds or []) if isinstance(s, (int, float)) and s and s > 0]
    if len(known) < count:
        return float(cap)
    return min(float(cap), sum(known))


def story_reference_token_budget(
    family: str,
    mode: str,
    image_count: int = 0,
    video_count: int = 0,
    audio_count: int = 0,
    resolution: str | None = None,
    video_seconds: list[float | None] | None = None,
    audio_seconds: list[float | None] | None = None,
) -> int:
    """Worst-case reference tokens beyond the included allowance (0 if none).

    Only families with reference-token pricing in reference mode have any.
    Videos and audio are budgeted over their measured combined length, or
    the combined maximum when a length is unknown. Video tokens depend on the
    output resolution (unknown resolutions take the highest rate).
    """
    rt = story_family_config(family).get("reference_tokens")
    if not rt or mode != "reference-to-video":
        return 0
    tokens = image_count * rt["per_image"]
    per_video = rt["per_video_second"]
    if isinstance(per_video, dict):
        per_video = per_video.get(resolution or "", max(per_video.values()))
    if video_count:
        tokens += per_video * _measured_seconds(video_seconds, video_count, rt["max_video_seconds"])
    if audio_count:
        tokens += rt["per_audio_second"] * _measured_seconds(audio_seconds, audio_count, rt["max_audio_seconds"])
    return max(0, int(math.ceil(tokens)) - rt["included"])


def story_reference_token_usd(family: str, extra_tokens: int | float) -> float:
    """USD for reference tokens beyond the allowance."""
    if not extra_tokens or extra_tokens <= 0:
        return 0.0
    per_1k = usd_for(story_reference_tokens_key(family))
    return round(extra_tokens / 1000 * per_1k, 4)


def story_video_input_seconds(family: str, video_count: int, video_seconds: list[float | None] | None = None) -> int:
    """Whole seconds of reference video a family bills on (0 without
    video-reference pricing or videos): the measured total rounded up, or the
    family's maximum when a length is unknown."""
    vr = story_family_config(family).get("video_reference_pricing")
    if not vr or video_count <= 0:
        return 0
    total = _measured_seconds(video_seconds, video_count, vr["max_input_seconds"])
    return min(int(vr["max_input_seconds"]), max(1, math.ceil(round(total, 1))))


def story_video_ref_usd(family: str, resolution: str, output_seconds: int, input_seconds: int) -> float:
    """USD for a clip made with reference videos: the family's video-ref
    rate times the billed length (input plus output, at least
    min_output_multiple times the output)."""
    cfg = story_family_config(family)
    vr = cfg["video_reference_pricing"]
    billed = max(int(input_seconds) + int(output_seconds), int(vr["min_output_multiple"]) * int(output_seconds))
    return round(usd_for(video_ref_key(cfg["pricing_family"], resolution)) * billed, 4)


def story_usd_cost(
    family: str,
    resolution: str,
    duration: str,
    mode: str | None = None,
    image_count: int = 0,
    video_count: int = 0,
    audio_count: int = 0,
    video_seconds: list[float | None] | None = None,
    audio_seconds: list[float | None] | None = None,
) -> float:
    """The estimate for a story job.

    Per-second price times the seconds, plus (H3 Max reference mode) the
    reference tokens the inputs can use beyond the included allowance. Kling
    v4 and Seedance with reference videos are priced on their video-reference
    rate over the input plus the output length instead.
    `video_seconds` and `audio_seconds` are the measured lengths of the
    reference clips (None for an unknown one, which assumes the maximum).
    """
    seconds = story_reserved_seconds(family, duration)
    cfg = story_family_config(family)
    if mode == "reference-to-video" and video_count > 0 and cfg.get("video_reference_pricing"):
        inputs = story_video_input_seconds(family, video_count, video_seconds)
        base = story_video_ref_usd(family, resolution, seconds, inputs)
    else:
        base = story_usd_per_second(family, resolution) * seconds
    extra = story_reference_token_budget(
        family, mode or "", image_count, video_count, audio_count,
        resolution=resolution, video_seconds=video_seconds, audio_seconds=audio_seconds,
    )
    return round(base + story_reference_token_usd(family, extra), 4)


def story_output_seconds(fal_result: dict | None, probed_seconds: float | None = None) -> float | None:
    """Length of a story result: fal's video.duration, else the probed length."""
    video = (fal_result or {}).get("video") if isinstance(fal_result, dict) else None
    seconds = video.get("duration") if isinstance(video, dict) else None
    if not seconds:
        seconds = probed_seconds
    try:
        seconds = float(seconds) if seconds else None
    except (TypeError, ValueError):
        seconds = None
    return seconds if seconds and seconds > 0 else None


def story_actual_usd(
    job,
    fal_result: dict | None,
    probed_seconds: float | None = None,
) -> tuple[float, int | None]:
    """USD to record for a finished story job, and the seconds billed.

    A fixed-length job costs its estimate, except that a job with reference-token
    pricing (H3 Max reference mode) costs the seconds plus the tokens fal reports
    beyond the allowance. An "auto" job costs its real length (whole seconds, rounded
    up after ignoring container padding under 0.05s). Never above the estimate. Jobs
    whose price cannot be recomputed (retired endpoints, unknown length or tokens)
    keep the estimate.
    """
    estimated = float(job.estimated_usd or 0)
    if job.duration_seconds:
        family = story_family_for_endpoint(story_model_for_job(job))
        rt = STORY_VIDEO_MODELS[family].get("reference_tokens") if family else None
        tokens = (fal_result or {}).get("reference_tokens") if isinstance(fal_result, dict) else None
        if rt and job.mode == "reference-to-video" and isinstance(tokens, (int, float)) and not isinstance(tokens, bool):
            try:
                base = story_usd_per_second(family, job.resolution) * int(job.duration_seconds)
                extra = story_reference_token_usd(family, max(0, tokens - rt["included"]))
            except ValueError:
                return estimated, int(job.duration_seconds)
            return round(min(base + extra, estimated), 4), int(job.duration_seconds)
        return estimated, int(job.duration_seconds)

    family = story_family_for_endpoint(story_model_for_job(job))
    seconds = story_output_seconds(fal_result, probed_seconds)
    if family is None or seconds is None or "auto" not in STORY_VIDEO_MODELS[family]["durations"]:
        return estimated, None

    billed = min(max(1, math.ceil(round(seconds, 1))), story_reserved_seconds(family, "auto"))
    stored = getattr(job, "result", None)
    pricing = stored.get("pricing") if isinstance(stored, dict) else None
    input_seconds = (pricing or {}).get("video_input_seconds")
    try:
        if input_seconds:
            # Reference videos: the video-ref rate on input plus output.
            if not STORY_VIDEO_MODELS[family].get("video_reference_pricing"):
                return estimated, None
            actual = story_video_ref_usd(family, job.resolution or "720p", billed, int(input_seconds))
        else:
            actual = story_usd_per_second(family, job.resolution or "720p") * billed
    except (ValueError, TypeError):
        return estimated, None
    return round(min(actual, estimated), 4), billed


def get_story_generation_status(request_id: str, db: Session, model: str | None = None) -> dict:
    """Check status of a story generation job.

    Args:
        request_id: FAL request ID
        db: Database session
        model: FAL model endpoint (defaults to text-to-video)

    Returns:
        dict with status, logs, and progress info
    """
    client = get_sync_client(db)
    fal_model = model or STORY_TEXT_TO_VIDEO_MODEL

    try:
        status = client.status(fal_model, request_id, with_logs=True)

        # Parse status - FAL returns status objects like InQueue, InProgress, Completed
        status_str = "pending"
        status_type = type(status).__name__

        if status_type == "Completed" or status_type == "CompletedStatus":
            status_str = "COMPLETED"
        elif status_type == "InProgress" or status_type == "InProgressStatus":
            status_str = "IN_PROGRESS"
        elif status_type == "InQueue" or status_type == "InQueueStatus" or status_type == "Queued":
            status_str = "IN_QUEUE"

        if hasattr(status, "status"):
            attr_status = str(status.status).upper()
            if "COMPLETE" in attr_status:
                status_str = "COMPLETED"
            elif "PROGRESS" in attr_status:
                status_str = "IN_PROGRESS"
            elif "QUEUE" in attr_status:
                status_str = "IN_QUEUE"

        logs = []
        if hasattr(status, "logs") and status.logs:
            logs = [log.get("message", "") if isinstance(log, dict) else str(log) for log in status.logs]

        return {
            "status": status_str,
            "logs": logs,
            "in_queue": status_str == "IN_QUEUE",
            "in_progress": status_str == "IN_PROGRESS",
            "completed": status_str == "COMPLETED",
        }
    except Exception as e:
        return _status_check_failed(request_id, e)


def get_story_generation_result(request_id: str, db: Session, model: str | None = None) -> dict:
    """Fetch result of a completed story generation job.

    Args:
        request_id: FAL request ID
        db: Database session
        model: FAL model endpoint (defaults to text-to-video)

    Returns:
        dict with video URL and metadata
    """
    fal_model = model or STORY_TEXT_TO_VIDEO_MODEL
    return get_sync_client(db).result(fal_model, request_id)


# =============================================================================
# SUBTITLE GENERATION - Auto-subtitle for videos
# =============================================================================

SUBTITLE_MODEL = "fal-ai/workflow-utilities/auto-subtitle"

# Valid color names for FAL auto-subtitle API
VALID_SUBTITLE_COLORS = {
    "white", "black", "red", "green", "blue", "yellow",
    "orange", "purple", "pink", "brown", "gray", "cyan", "magenta"
}


def subtitle_usd(duration_seconds: float | None) -> float:
    """The estimate for a video: whole minutes, rounded up, at least one."""
    minutes = max(1, math.ceil(float(duration_seconds or 0) / 60))
    return round(usd_for(SUBTITLES_MINUTE_KEY) * minutes, 4)


def subtitle_actual_usd(duration_seconds: float | None, estimated: float | None) -> float:
    """USD to record for a finished job: the output's length at the per minute rate,
    never above the estimate. The output can be a little longer than the probed
    upload, and rounding up would then pass to the next minute."""
    actual = subtitle_usd(duration_seconds)
    if estimated is None:
        return actual
    if not duration_seconds:
        return float(estimated)
    return round(min(actual, float(estimated)), 4)


def submit_subtitle_generation(
    video_url: str,
    db: Session,
    font_color: str = "white",
    stroke_color: str = "black",
    highlight_color: str | None = None,
    background_color: str | None = None,
    position: str = "bottom",
    font_size: int = 100,
    font_name: str = "Montserrat",
    font_weight: str = "bold",
    stroke_width: int = 3,
    y_offset: int = 75,
    words_per_subtitle: int = 3,
    enable_animation: bool = True,
    language: str = "en",
) -> dict:
    """Submit async subtitle generation job to FAL.

    Args:
        video_url: URL of the video to add subtitles to
        font_color: Color name for subtitle text (white, black, red, green, blue, etc.)
        stroke_color: Color name for text stroke/outline
        highlight_color: Color name for word highlight animation (optional)
        background_color: Color name for subtitle background (optional)
        position: Subtitle position (top, center, bottom)
        font_size: Font size in pixels
        font_name: Font family name (Montserrat, Arial, etc.)
        font_weight: Font weight (bold, normal)
        stroke_width: Width of text stroke in pixels
        y_offset: Vertical offset from position in pixels
        words_per_subtitle: Number of words per subtitle chunk
        enable_animation: Enable word-by-word highlight animation
        language: Language code for transcription (en, es, fr, etc.)

    Returns:
        dict with request_id
    """
    # Validate video URL
    is_valid, error = validate_video_url(video_url)
    if not is_valid:
        raise ValueError(f"Invalid video URL: {error}")

    # Validate position
    valid_positions = {"top", "center", "bottom"}
    if position not in valid_positions:
        raise ValueError(f"Position must be one of: {valid_positions}")

    # Validate color names
    if font_color not in VALID_SUBTITLE_COLORS:
        raise ValueError(f"font_color must be one of: {VALID_SUBTITLE_COLORS}")
    if stroke_color not in VALID_SUBTITLE_COLORS:
        raise ValueError(f"stroke_color must be one of: {VALID_SUBTITLE_COLORS}")
    if highlight_color and highlight_color not in VALID_SUBTITLE_COLORS:
        raise ValueError(f"highlight_color must be one of: {VALID_SUBTITLE_COLORS}")
    if background_color and background_color not in VALID_SUBTITLE_COLORS:
        raise ValueError(f"background_color must be one of: {VALID_SUBTITLE_COLORS}")

    arguments = {
        "video_url": video_url,
        "language": language,
        "font_name": font_name,
        "font_size": font_size,
        "font_weight": font_weight,
        "font_color": font_color,
        "stroke_width": stroke_width,
        "stroke_color": stroke_color,
        "position": position,
        "y_offset": y_offset,
        "words_per_subtitle": words_per_subtitle,
        "enable_animation": enable_animation,
    }

    # Add optional colors if provided
    if highlight_color:
        arguments["highlight_color"] = highlight_color
    if background_color:
        arguments["background_color"] = background_color

    _logger.debug(f"\n=== Subtitle Generation ===")
    _logger.debug(f"Model: {SUBTITLE_MODEL}")
    _logger.debug(f"Video URL: {video_url[:100]}...")
    _logger.debug(f"Position: {position}, Font: {font_name} {font_size}px")
    _logger.debug(f"Colors: font={font_color}, stroke={stroke_color}")

    try:
        handler = fal_submit(SUBTITLE_MODEL, arguments, db)
        _logger.debug(f"Job submitted successfully. Request ID: {handler.request_id}")
        return {
            "request_id": handler.request_id,
        }
    except Exception as e:
        _logger.warning(f"FAL submit error: {e}")
        raise


def get_subtitle_generation_status(request_id: str, db: Session) -> dict:
    """Check status of a subtitle generation job.

    Returns:
        dict with status, logs, and progress info
    """
    client = get_sync_client(db)

    try:
        status = client.status(SUBTITLE_MODEL, request_id, with_logs=True)

        # Parse status
        status_str = "pending"
        status_type = type(status).__name__

        if status_type == "Completed" or status_type == "CompletedStatus":
            status_str = "COMPLETED"
        elif status_type == "InProgress" or status_type == "InProgressStatus":
            status_str = "IN_PROGRESS"
        elif status_type == "InQueue" or status_type == "InQueueStatus" or status_type == "Queued":
            status_str = "IN_QUEUE"

        if hasattr(status, "status"):
            attr_status = str(status.status).upper()
            if "COMPLETE" in attr_status:
                status_str = "COMPLETED"
            elif "PROGRESS" in attr_status:
                status_str = "IN_PROGRESS"
            elif "QUEUE" in attr_status:
                status_str = "IN_QUEUE"

        logs = []
        if hasattr(status, "logs") and status.logs:
            logs = [log.get("message", "") if isinstance(log, dict) else str(log) for log in status.logs]

        return {
            "status": status_str,
            "logs": logs,
            "in_queue": status_str == "IN_QUEUE",
            "in_progress": status_str == "IN_PROGRESS",
            "completed": status_str == "COMPLETED",
        }
    except Exception as e:
        return _status_check_failed(request_id, e)


def get_subtitle_generation_result(request_id: str, db: Session) -> dict:
    """Fetch result of a completed subtitle generation job.

    Returns:
        dict with subtitled video URL, transcript, and metadata
    """
    return get_sync_client(db).result(SUBTITLE_MODEL, request_id)
