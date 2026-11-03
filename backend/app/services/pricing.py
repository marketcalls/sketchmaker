"""What every paid generation costs in USD, from a built-in table.

Each priced option has a key (see the *_key helpers) and the provider's published
price for it. These are estimates: the owner's fal invoice is the real number. The
quotes, the amounts recorded in usage_log and GET /api/pricing/costs all read this
table, so they cannot drift apart.

usd_for raises ValueError for an unknown key, which is also how routers validate a
model name, and USD_COSTS doubles as the Faceless model list.

Units: images, edits, explainers and logos are priced per output; video keys
(Stories, Motion Control and Lip Sync) per second of output; voices per 1,000
characters; music, renders and subtitles per minute.
"""

import math

# Results are rounded to this many decimals: the cheapest options cost fractions
# of a cent per second.
USD_DECIMALS = 4

# Video families offered by Stories.
VIDEO_FAMILIES = {
    "h3-max": "MiniMax H3 Max",
    "seedance-2.5": "Seedance 2.5",
    "kling-v4": "Kling v4",
    "flux-3-max": "FLUX 3 Max",
    "omni-flash": "Gemini Omni Flash 1.1",
}


def image_key(model: str, resolution: str) -> str:
    return f"image:{model}:{(resolution or '1k').lower()}"


def edit_key(model: str, resolution: str | None = None) -> str:
    """Price key for one edit output. 1K (the default) keeps the plain
    "edit:<model>" key; 2K and 4K add a suffix: "edit:<model>:2k"."""
    res = (resolution or "1k").lower()
    return f"edit:{model}" if res == "1k" else f"edit:{model}:{res}"


def video_key(family: str, resolution: str) -> str:
    return f"video:{family}:{resolution}"


# Suffix of the per-second keys for reference-to-video with reference videos,
# where fal bills a different rate on the input plus the output length
# (Kling v4, Seedance 2.5). The suffix keeps them out of the Stories range.
VIDEO_REF_SUFFIX = ":video-ref"


def video_ref_key(family: str, resolution: str) -> str:
    return f"{video_key(family, resolution)}{VIDEO_REF_SUFFIX}"


def logo_text_key(quality: str, with_references: bool = False) -> str:
    return "logo:text:high_ref" if with_references and quality == "high" else f"logo:text:{quality}"


LOGO_VECTORIZE_KEY = "logo:vectorize"


# Explainer resolutions (GPT Image 2.5 Sunburst at quality high). Anything else falls
# back to 2K, exactly as fal_client.generate_explainer_image does.
EXPLAINER_RESOLUTIONS = ("1k", "2k", "4k")
EXPLAINER_DEFAULT_RESOLUTION = "2k"


def explainer_resolution(resolution: str | None) -> str:
    res = (resolution or EXPLAINER_DEFAULT_RESOLUTION).lower()
    return res if res in EXPLAINER_RESOLUTIONS else EXPLAINER_DEFAULT_RESOLUTION


def explainer_key(resolution: str | None, with_references: bool = False) -> str:
    """Price key for one explainer image. With reference images the request
    goes to the edit endpoint, which also bills the input images, so it has
    its own key per resolution: "explainer:edit:<res>"."""
    res = explainer_resolution(resolution)
    return f"explainer:edit:{res}" if with_references else f"explainer:{res}"


# Motion Control (Kling motion transfer). Three tiers, each priced per second
# of output, which follows the reference video up to a cap set by
# character_orientation. The family names end in "-motion": the frontend keeps
# them out of the Stories price range. The endpoints live in
# fal_client.MOTION_CONTROL_TIERS.
MOTION_CONTROL_KEYS = {
    "v3-standard": "video:kling-v3-motion:standard",
    "v3-pro": "video:kling-v3-motion:pro",
    "v2.6": "video:kling-2.6-motion:any",
}
MOTION_CONTROL_DEFAULT_TIER = "v3-standard"
# The v2.6 key, which every job before the tier choice was priced on.
MOTION_CONTROL_KEY = MOTION_CONTROL_KEYS["v2.6"]
MOTION_CONTROL_MAX_SECONDS = {"image": 10, "video": 30}

# Multi-character motion transfer: MiniMax H3 Max Recast replaces up to four
# people in a source video with reference photos. Per second of output (the
# source video's length) by resolution. Its tiers share the Motion Control
# job pipeline (VideoGenerationJob.options["tier"]) but live in their own map,
# so the Kling price ranges shown on the pages do not include them.
RECAST_KEYS = {
    "recast-768p": "video:h3-max-recast:768p",
    "recast-1080p": "video:h3-max-recast:1080p",
}
RECAST_TIER_BY_RESOLUTION = {"768p": "recast-768p", "1080p": "recast-1080p"}
# fal takes 5 to 30 seconds with no single shot over 15 seconds; this
# release caps the whole video at 15.
RECAST_MIN_SECONDS = 5.0
RECAST_MAX_SECONDS = 15.0
RECAST_MAX_REFERENCES = 4


def motion_control_key(tier: str | None) -> str:
    """Price key of a Motion Control tier (Kling, or an H3 Max Recast
    resolution); raises ValueError for an unknown tier."""
    key = MOTION_CONTROL_KEYS.get(tier or MOTION_CONTROL_DEFAULT_TIER) or RECAST_KEYS.get(tier or "")
    if key is None:
        raise ValueError(f"Unknown Motion Control model '{tier}'")
    return key


# Lip Sync (MiniMax H3 Max). Priced per second of output, which is exactly
# the length of the supplied audio. fal adds a 1.2x multiplier to the whole
# video when it is over 15 seconds; lipsync_usd applies it, so the multiplier
# lives in one place.
LIPSYNC_RESOLUTIONS = ("480p", "768p", "1080p", "2k")
LIPSYNC_DEFAULT_RESOLUTION = "768p"
LIPSYNC_LONG_AFTER_SECONDS = 15
LIPSYNC_LONG_MULTIPLIER = 1.2
LIPSYNC_KEY_PREFIX = "video:h3-max-lipsync:"


def lipsync_key(resolution: str | None) -> str:
    return f"{LIPSYNC_KEY_PREFIX}{(resolution or LIPSYNC_DEFAULT_RESOLUTION).lower()}"


# Faceless Studio (/faceless). Voices are Eleven v4 (per 1,000 characters
# sent, audio tags included), music is ElevenLabs Music (per output minute,
# rounded up per track by fal), and the final render is local ffmpeg work, so it
# costs nothing. Stills and clips reuse the image, edit and H3 Max video keys above.
ELEVEN_V4_KEY = "audio:eleven-v4:1k-chars"
ELEVEN_MUSIC_KEY = "audio:elevenlabs-music:minute"
RENDER_MINUTE_KEY = "render:minute"
# Voices for Lip Sync and My Assets in Indian languages: Sarvam Bulbul v4
# (bulbul:v4-flash), billed by Sarvam per character sent.
SARVAM_BULBUL_KEY = "audio:sarvam-bulbul-v4:1k-chars"
# Background removal (per image) and auto subtitles (per minute of video).
REMOVE_BG_KEY = "utility:remove-bg"
SUBTITLES_MINUTE_KEY = "utility:subtitles:minute"


# Story Room (/stories). One AI director reply is an LLM call on the default
# model, shown as an estimate of its token spend: about 12k input tokens (system
# prompt, library, the story document, memory and the last 12 messages) and up to
# 6k output tokens (reply plus the whole updated document and treatment) on a
# frontier model, roughly $0.04. The Quick clip prompt enhancer is one short call,
# roughly $0.01. These keys only quote a price before the call: the real tokens go
# to llm_usage (litellm_client), so never pass them to usage.record_usage.
STORY_CHAT_TURN_KEY = "story:chat-turn"
STORY_PROMPT_ENHANCE_KEY = "story:prompt-enhance"

# Quality checks (app/services/quality_gate.py). One vision call on the default
# model that reads a finished image (or three frames of a clip) against its brief,
# shown as an estimate of its token spend: about 2.5k input tokens (rubric, schema
# and the downscaled images) and 300 output tokens on a frontier model, roughly
# $0.01. Quote only, like the Story Room keys.
QA_VISION_CHECK_KEY = "qa:vision-check"


# fal's USD cost per output (per second for video keys), from each model's fal
# page (https://fal.ai/models/<endpoint>/llms.txt) as of 2026-10-25, checked
# against fal's pricing API. Token or megapixel billed models use the worst
# case across the sizes this app sends.
# (label, unit, usd)
USD_COSTS: dict[str, tuple[str, str, float]] = {
    # /generate. Per image, worst case across the aspect ratios the app sends at
    # that resolution.
    image_key("blackforestlabs/flux-3/klein/text-to-image", "1k"): ("Flux 3 Klein 1K", "image", 0.009),
    image_key("blackforestlabs/flux-3/klein/text-to-image", "2k"): ("Flux 3 Klein 2K", "image", 0.045),
    image_key("blackforestlabs/flux-3/klein/text-to-image", "4k"): ("Flux 3 Klein 4K", "image", 0.081),
    image_key("fal-ai/z-image/turbo/lora", "1k"): ("Z-Image Turbo 1K", "image", 0.0085),
    image_key("fal-ai/z-image/turbo/lora", "2k"): ("Z-Image Turbo 2K", "image", 0.0085),
    image_key("fal-ai/z-image/turbo/lora", "4k"): ("Z-Image Turbo 4K", "image", 0.0085),
    image_key("blackforestlabs/flux-3/text-to-image", "1k"): ("Flux 3 1K", "image", 0.048),
    image_key("blackforestlabs/flux-3/text-to-image", "2k"): ("Flux 3 2K", "image", 0.24),
    image_key("blackforestlabs/flux-3/text-to-image", "4k"): ("Flux 3 4K", "image", 0.768),
    image_key("openai/gpt-image-2.5/sunburst/text-to-image", "1k"): ("GPT Image 2.5 1K", "image", 0.0527),
    image_key("openai/gpt-image-2.5/sunburst/text-to-image", "2k"): ("GPT Image 2.5 2K", "image", 0.090),
    image_key("openai/gpt-image-2.5/sunburst/text-to-image", "4k"): ("GPT Image 2.5 4K", "image", 0.1001),
    image_key("google/nano-banana-2.1", "1k"): ("Nano Banana 2.1 1K", "image", 0.050),
    image_key("google/nano-banana-2.1", "2k"): ("Nano Banana 2.1 2K", "image", 0.070),
    image_key("google/nano-banana-2.1", "4k"): ("Nano Banana 2.1 4K", "image", 0.145),
    image_key("ideogram/v4.5", "1k"): ("Ideogram V4.5 1K", "image", 0.060),
    image_key("ideogram/v4.5", "2k"): ("Ideogram V4.5 2K", "image", 0.060),
    image_key("ideogram/v4.5", "4k"): ("Ideogram V4.5 4K (renders 2K)", "image", 0.060),
    image_key("bytedance/seedream/v5/pro/text-to-image", "1k"): ("Seedream V5 Pro 1K", "image", 0.0675),
    image_key("bytedance/seedream/v5/pro/text-to-image", "2k"): ("Seedream V5 Pro 2K", "image", 0.135),
    image_key("bytedance/seedream/v5/pro/text-to-image", "4k"): ("Seedream V5 Pro 4K (renders 2K)", "image", 0.135),
    image_key("microsoft/mai-image-2.5", "1k"): ("MAI Image 2.5", "image", 0.050),
    image_key("microsoft/mai-image-2.5", "2k"): ("MAI Image 2.5 (no 2K)", "image", 0.050),
    image_key("microsoft/mai-image-2.5", "4k"): ("MAI Image 2.5 (no 4K)", "image", 0.050),
    image_key("xai/grok-imagine-image/v2.0/text-to-image", "1k"): ("Grok Imagine 2.0 1K", "image", 0.060),
    image_key("xai/grok-imagine-image/v2.0/text-to-image", "2k"): ("Grok Imagine 2.0 2K", "image", 0.080),
    image_key("xai/grok-imagine-image/v2.0/text-to-image", "4k"): ("Grok Imagine 2.0 4K (renders 2K)", "image", 0.080),
    # Magix and Virtual Try-On. Per output image, with two input images (what
    # Try-On sends). The UI edits at 1K; the 2K and 4K keys price what the API
    # also accepts, estimated as the 1K edit cost plus the model's text-to-image
    # step from 1K to that size (per megapixel for Flux 3, which is billed so).
    edit_key("google/nano-banana-2.1/edit"): ("Nano Banana 2.1 Edit 1K", "image", 0.055),
    edit_key("google/nano-banana-2.1/edit", "2k"): ("Nano Banana 2.1 Edit 2K", "image", 0.075),
    edit_key("google/nano-banana-2.1/edit", "4k"): ("Nano Banana 2.1 Edit 4K", "image", 0.155),
    edit_key("openai/gpt-image-2.5/sunburst/edit"): ("GPT Image 2.5 Edit 1K", "image", 0.069),
    edit_key("openai/gpt-image-2.5/sunburst/edit", "2k"): ("GPT Image 2.5 Edit 2K", "image", 0.106),
    edit_key("openai/gpt-image-2.5/sunburst/edit", "4k"): ("GPT Image 2.5 Edit 4K", "image", 0.117),
    edit_key("blackforestlabs/flux-3/edit-image"): ("Flux 3 Edit 1K", "image", 0.048),
    edit_key("blackforestlabs/flux-3/edit-image", "2k"): ("Flux 3 Edit 2K", "image", 0.24),
    edit_key("blackforestlabs/flux-3/edit-image", "4k"): ("Flux 3 Edit 4K", "image", 0.768),
    edit_key("xai/grok-imagine-image/v2.0/edit"): ("Grok Imagine 2.0 Edit 1K", "image", 0.080),
    edit_key("xai/grok-imagine-image/v2.0/edit", "2k"): ("Grok Imagine 2.0 Edit 2K", "image", 0.100),
    edit_key("xai/grok-imagine-image/v2.0/edit", "4k"): ("Grok Imagine 2.0 Edit 4K (renders 2K)", "image", 0.100),
    edit_key("ideogram/v4.5/edit"): ("Ideogram V4.5 Edit", "image", 0.060),
    edit_key("ideogram/v4.5/edit", "2k"): ("Ideogram V4.5 Edit (keeps source size)", "image", 0.060),
    edit_key("ideogram/v4.5/edit", "4k"): ("Ideogram V4.5 Edit (keeps source size)", "image", 0.060),
    # Logo generator. Per SVG.
    logo_text_key("low"): ("Logo, low quality", "svg", 0.13),
    logo_text_key("medium"): ("Logo, medium quality", "svg", 0.16),
    logo_text_key("high"): ("Logo, high quality", "svg", 0.20),
    logo_text_key("high", with_references=True): ("Logo, high quality with reference images", "svg", 0.32),
    LOGO_VECTORIZE_KEY: ("Image to vector", "svg", 0.10),
    # Stories. Per second of video, at fal's regular (non-promotional) rate.
    # H3 Max bills the requested duration (the clip can run 0.7 s longer).
    video_key("h3-max", "480p"): ("MiniMax H3 Max 480p", "second", 0.05),
    video_key("h3-max", "768p"): ("MiniMax H3 Max 768p", "second", 0.08),
    video_key("h3-max", "1080p"): ("MiniMax H3 Max 1080p", "second", 0.16),
    # H3 Max reference-to-video: reference tokens beyond the 4,096 each
    # request includes, per 1,000 tokens (fal prorates). Estimated at the worst
    # case of the inputs, recorded on the reference_tokens fal reports
    # (fal_client.story_actual_usd).
    "video:h3-max:reference-1k-tokens": ("MiniMax H3 Max reference tokens over 4,096", "1k tokens", 0.02),
    video_key("seedance-2.5", "480p"): ("Seedance 2.5 480p", "second", 0.2205),
    video_key("seedance-2.5", "720p"): ("Seedance 2.5 720p", "second", 0.4730),
    video_key("seedance-2.5", "1080p"): ("Seedance 2.5 1080p", "second", 1.164),
    # Reference-to-video with reference videos: Seedance multiplies its token
    # price by 0.6 and bills the input plus the output length; Kling v4 bills
    # its own rate on the input plus the output length, at least twice the
    # output. Priced per second of that billed length
    # (fal_client.story_usd_estimate).
    video_ref_key("seedance-2.5", "480p"): ("Seedance 2.5 480p, with reference videos (input plus output)", "second", 0.1323),
    video_ref_key("seedance-2.5", "720p"): ("Seedance 2.5 720p, with reference videos (input plus output)", "second", 0.2838),
    video_key("kling-v4", "720p"): ("Kling v4 720p", "second", 0.157),
    video_key("kling-v4", "1080p"): ("Kling v4 1080p", "second", 0.235),
    video_ref_key("kling-v4", "720p"): ("Kling v4 720p, with reference videos (input plus output)", "second", 0.094),
    video_ref_key("kling-v4", "1080p"): ("Kling v4 1080p, with reference videos (input plus output)", "second", 0.141),
    video_key("flux-3-max", "720p"): ("FLUX 3 Max 720p", "second", 0.17),
    video_key("flux-3-max", "1080p"): ("FLUX 3 Max 1080p", "second", 0.29),
    # Gemini Omni Flash 1.1 bills output seconds; Stories requests a fixed
    # length, so the requested seconds are the cost.
    video_key("omni-flash", "360p"): ("Gemini Omni Flash 1.1 360p", "second", 0.03),
    video_key("omni-flash", "720p"): ("Gemini Omni Flash 1.1 720p", "second", 0.10),
    video_key("omni-flash", "1080p"): ("Gemini Omni Flash 1.1 1080p", "second", 0.15),
    video_key("omni-flash", "4k"): ("Gemini Omni Flash 1.1 4K", "second", 0.30),
    # Motion Control. Per second of output at any resolution; fal bills the
    # output duration. A face element (V3 only) does not change the price.
    MOTION_CONTROL_KEYS["v3-standard"]: ("Motion Control, Kling V3 Standard", "second", 0.126),
    MOTION_CONTROL_KEYS["v3-pro"]: ("Motion Control, Kling V3 Pro", "second", 0.168),
    MOTION_CONTROL_KEYS["v2.6"]: ("Motion Control, Kling v2.6 Standard", "second", 0.07),
    # minimax/h3-max/recast, per second of output; reference photos are free.
    RECAST_KEYS["recast-768p"]: ("Multi-character Recast, H3 Max 768p", "second", 0.30),
    RECAST_KEYS["recast-1080p"]: ("Multi-character Recast, H3 Max 1080p", "second", 0.45),
    # Lip Sync (MiniMax H3 Max). Per second of output before fal's 1.2x
    # multiplier over 15 seconds (applied by lipsync_usd, not here).
    lipsync_key("480p"): ("Lip Sync 480p", "second", 0.05),
    lipsync_key("768p"): ("Lip Sync 768p", "second", 0.08),
    lipsync_key("1080p"): ("Lip Sync 1080p", "second", 0.16),
    lipsync_key("2k"): ("Lip Sync 2K", "second", 0.32),
    # Explainer (openai/gpt-image-2.5/sunburst, quality high). Per image,
    # worst case across the aspect ratios the page offers
    # (fal_client.GPT_IMAGE_25_SIZES), from fal's high-quality output table
    # (2026-10-30): 1024x1024 $0.05268, 2560x1440 $0.05529, 3840x2160
    # $0.10008. 2K square (1920x1920) is not listed: priced like the 2K image
    # key, $0.09. 4K square (2880x2880) is not listed either: $0.14, above the
    # 3840x2160 price because fal prices a square above a wide image of the
    # same area. Each key adds $0.01 of text input tokens for the brief. The
    # edit keys add the input images of the worst case the API accepts, 4
    # references and a mask, at about $0.012 each.
    explainer_key("1k"): ("Explainer 1K", "image", 0.063),
    explainer_key("2k"): ("Explainer 2K", "image", 0.10),
    explainer_key("4k"): ("Explainer 4K (2880x2880 estimated)", "image", 0.15),
    explainer_key("1k", with_references=True): ("Explainer 1K with references", "image", 0.123),
    explainer_key("2k", with_references=True): ("Explainer 2K with references", "image", 0.16),
    explainer_key("4k", with_references=True): ("Explainer 4K with references (estimated)", "image", 0.21),
    # Faceless Studio and Motion Graphics Studio. Voice per 1,000 characters
    # (elevenlabs/tts/eleven-v4), music per output minute rounded up per track
    # (fal-ai/elevenlabs/music). Renders run on the owner's machine, so they
    # have no provider cost.
    ELEVEN_V4_KEY: ("Eleven v4 voice", "1k characters", 0.08),
    ELEVEN_MUSIC_KEY: ("ElevenLabs Music", "minute", 0.60),
    # Sarvam Bulbul v4 Flash: Rs 10 per 10,000 characters pay as you go
    # (docs.sarvam.ai pricing, 2026-10-28), plus 18 percent GST, at about
    # Rs 88 to the dollar: Rs 1.18 per 1,000 characters, $0.0135. Not fal.
    SARVAM_BULBUL_KEY: ("Sarvam Bulbul v4 voice (Lip Sync, My Assets)", "1k characters", 0.0135),
    RENDER_MINUTE_KEY: ("Studio render, Faceless and Motion Graphics (runs on this machine)", "minute", 0.0),
    # Background removal and auto subtitles, fal's live prices read 2026-11-04.
    REMOVE_BG_KEY: ("Background removal", "image", 0.018),
    SUBTITLES_MINUTE_KEY: ("Auto subtitles", "minute", 0.03),
    # Story Room and Stories. LLM token estimates (see STORY_CHAT_TURN_KEY), not fal.
    STORY_CHAT_TURN_KEY: ("Story Room AI reply (LLM estimate)", "reply", 0.04),
    STORY_PROMPT_ENHANCE_KEY: ("Stories prompt enhancement (LLM estimate)", "prompt", 0.01),
    # Quality checks. LLM token estimate (see QA_VISION_CHECK_KEY), not fal.
    QA_VISION_CHECK_KEY: ("Quality check, one vision read of an image or clip (LLM estimate)", "check", 0.01),
}


def _rounded(usd: float) -> float:
    return round(float(usd), USD_DECIMALS)


def cost_table() -> dict[str, float]:
    """USD per key, as served by GET /api/pricing/costs."""
    return {key: usd for key, (_, _, usd) in USD_COSTS.items()}


def usd_for(key: str) -> float:
    """USD for one unit of ``key`` (one image, one SVG, one second of video)."""
    if key not in USD_COSTS:
        raise ValueError(f"No price for '{key}'")
    return USD_COSTS[key][2]


def image_usd(model: str, resolution: str | None, count: int = 1) -> float:
    """USD for ``count`` images from a text-to-image model at a resolution."""
    return _rounded(usd_for(image_key(model, resolution or "1k")) * max(0, int(count)))


def edit_usd(model: str, resolution: str | None = None, count: int = 1) -> float:
    """USD for ``count`` outputs of an edit model (Magix, Virtual Try-On)."""
    return _rounded(usd_for(edit_key(model, resolution)) * max(0, int(count)))


def explainer_usd(resolution: str | None, with_references: bool = False) -> float:
    """USD for one explainer image at a resolution, with or without references."""
    return _rounded(usd_for(explainer_key(resolution, with_references)))


def motion_control_reserved_seconds(orientation: str | None, probed_seconds: float | None) -> int:
    """Seconds a Motion Control job is estimated on: the reference video's length in
    whole seconds (rounded up, ignoring padding under 0.05s) capped at the
    orientation's maximum, or that maximum when the length is unknown."""
    cap = MOTION_CONTROL_MAX_SECONDS.get(orientation or "video", max(MOTION_CONTROL_MAX_SECONDS.values()))
    try:
        seconds = float(probed_seconds) if probed_seconds else 0.0
    except (TypeError, ValueError):
        seconds = 0.0
    if seconds <= 0:
        return cap
    return min(cap, max(1, math.ceil(round(seconds, 1))))


def motion_control_usd(seconds: int, tier: str | None = MOTION_CONTROL_DEFAULT_TIER) -> float:
    """USD for ``seconds`` of Motion Control output on a tier (v3-standard, v3-pro,
    v2.6 or a Recast tier). Raises ValueError for an unknown tier."""
    return _rounded(usd_for(motion_control_key(tier)) * max(0, int(seconds)))


def motion_control_actual_usd(
    estimated: float, output_seconds: float | None, tier: str | None
) -> tuple[float, int | None]:
    """USD to record for a finished Motion Control job, and the seconds billed.

    The real output length in whole seconds at the job's tier, never more than the
    estimate. When the length is unknown the estimate stands.
    """
    estimated = float(estimated or 0)
    try:
        seconds = float(output_seconds) if output_seconds else 0.0
    except (TypeError, ValueError):
        seconds = 0.0
    if seconds <= 0:
        return estimated, None
    billed = max(1, math.ceil(round(seconds, 1)))
    try:
        actual = motion_control_usd(billed, tier)
    except ValueError:
        return estimated, None
    return min(actual, estimated), billed


def lipsync_seconds(duration_seconds: float | None) -> int:
    """Whole seconds a Lip Sync video is priced on: the length rounded up (0 when
    unknown). The rounding to 2 decimals only absorbs float noise, so 15.01s is 16
    seconds and takes the over-15-seconds multiplier, as fal bills it."""
    try:
        seconds = float(duration_seconds) if duration_seconds else 0.0
    except (TypeError, ValueError):
        seconds = 0.0
    if seconds <= 0:
        return 0
    return max(1, math.ceil(round(seconds, 2)))


def lipsync_usd(resolution: str | None, seconds: int) -> float:
    """USD for ``seconds`` of Lip Sync output at a resolution: the per-second price
    times the seconds, times 1.2 when the video is over 15 seconds. Raises ValueError
    for an unknown resolution."""
    seconds = max(0, int(seconds))
    total = usd_for(lipsync_key(resolution)) * seconds
    if seconds > LIPSYNC_LONG_AFTER_SECONDS:
        total *= LIPSYNC_LONG_MULTIPLIER
    return _rounded(total)


def lipsync_actual_usd(
    estimated: float, resolution: str | None, output_seconds: float | None
) -> tuple[float, int | None]:
    """USD to record for a finished Lip Sync job, and the seconds billed.

    The real output length, never more than the estimate (made on the audio length
    measured at upload). When the length is unknown the estimate stands.
    """
    estimated = float(estimated or 0)
    billed = lipsync_seconds(output_seconds)
    if billed <= 0:
        return estimated, None
    try:
        actual = lipsync_usd(resolution, billed)
    except ValueError:
        return estimated, None
    return min(actual, estimated), billed


def tts_usd(characters: int, key: str = ELEVEN_V4_KEY) -> float:
    """USD for sending ``characters`` to a voice model priced per 1,000 characters
    (Eleven v4 by default, SARVAM_BULBUL_KEY for Sarvam)."""
    characters = max(0, int(characters or 0))
    return _rounded(usd_for(key) * characters / 1000)


def music_minutes(seconds: float | None) -> int:
    """Minutes ElevenLabs Music bills for one track: the length rounded up."""
    try:
        seconds = float(seconds or 0)
    except (TypeError, ValueError):
        seconds = 0.0
    if seconds <= 0:
        return 0
    return max(1, math.ceil(round(seconds, 2) / 60))


def music_usd(seconds: float | None) -> float:
    """USD for one music track of ``seconds`` (per minute, rounded up)."""
    return _rounded(usd_for(ELEVEN_MUSIC_KEY) * music_minutes(seconds))


def render_minutes(seconds: float | None) -> int:
    """Output minutes of a render: the length rounded up."""
    return music_minutes(seconds)


def render_usd(seconds: float | None) -> float:
    """USD for rendering ``seconds`` of output. Local work, so 0.0 at today's price."""
    return _rounded(usd_for(RENDER_MINUTE_KEY) * render_minutes(seconds))
