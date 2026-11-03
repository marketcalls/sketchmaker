"""Content types and readable model names for gallery payloads.

The gallery shows what each item
is (a logo, an explainer, a story video, a lip sync...) and which model made
it. Image rows carry the tool in `art_style`, video rows in `video_type`; this
module turns both into stable ids, labels and query filters so every router
agrees on them. Keep MODEL_NAMES in step with frontend/src/utils/models.ts.
"""

from __future__ import annotations

import os

from sqlalchemy import and_, or_

# ---------------------------------------------------------------------------
# Image content types
# ---------------------------------------------------------------------------

# Source type id -> art_style prefix or exact value. "image" is everything else.
_IMAGE_PREFIXES = {
    "logo": "logo_",
    "explainer": "explainer_",
    "magix": "magix_",
}
_IMAGE_EXACT = {
    "virtual_tryon": "virtual_tryon",
    "remove_bg": "remove_bg",
}

IMAGE_SOURCE_TYPES = ("image", "logo", "explainer", "magix", "virtual_tryon", "remove_bg")

IMAGE_SOURCE_LABELS = {
    "image": "Image",
    "logo": "Logo",
    "explainer": "Explainer",
    "magix": "Magix",
    "virtual_tryon": "Virtual Try-On",
    "remove_bg": "Remove BG",
}


def image_source_type(art_style: str | None) -> str:
    """The content type of an Image row, from its art_style."""
    if art_style:
        for source_type, prefix in _IMAGE_PREFIXES.items():
            if art_style.startswith(prefix):
                return source_type
        for source_type, value in _IMAGE_EXACT.items():
            if art_style == value:
                return source_type
    return "image"


def image_source_filter(art_style_column, source_type: str):
    """SQL condition matching Image rows of one content type.

    startswith(autoescape=True) keeps the underscore in "logo_" literal; a bare
    LIKE 'logo_%' would also match "logos..." or "logoX".
    """
    if source_type in _IMAGE_PREFIXES:
        return art_style_column.startswith(_IMAGE_PREFIXES[source_type], autoescape=True)
    if source_type in _IMAGE_EXACT:
        return art_style_column == _IMAGE_EXACT[source_type]
    # Plain images: no art_style, or one that belongs to no other tool.
    others = [
        art_style_column.startswith(prefix, autoescape=True) for prefix in _IMAGE_PREFIXES.values()
    ] + [art_style_column == value for value in _IMAGE_EXACT.values()]
    return or_(art_style_column.is_(None), and_(*[~cond for cond in others]))


def is_vector_filename(filename: str | None) -> bool:
    """Whether a stored image is an SVG (logos are; everything else is raster)."""
    return bool(filename) and os.path.splitext(filename)[1].lower() == ".svg"


# ---------------------------------------------------------------------------
# Video content types
# ---------------------------------------------------------------------------

VIDEO_TYPE_LABELS = {
    "story": "Story",
    "motion": "Motion Control",
    "lipsync": "Lip Sync",
    "subtitle": "Subtitles",
    "faceless": "Faceless Studio",
    "motion_graphics": "Motion Graphics",
}

VIDEO_TYPES = tuple(VIDEO_TYPE_LABELS)


def video_type_of(video_type: str | None) -> str:
    """Normalised video type. Rows from before the column existed are motion."""
    return video_type if video_type in VIDEO_TYPE_LABELS else "motion"


def video_type_label(video_type: str | None) -> str:
    return VIDEO_TYPE_LABELS[video_type_of(video_type)]


# ---------------------------------------------------------------------------
# Model display names
# ---------------------------------------------------------------------------

# Retired ids stay so older content keeps a readable name.
MODEL_NAMES = {
    # Text to image (/generate)
    "blackforestlabs/flux-3/klein/text-to-image": "Flux 3 Klein",
    "blackforestlabs/flux-3/text-to-image": "Flux 3",
    "openai/gpt-image-2.5/sunburst/text-to-image": "GPT Image 2.5",
    "google/nano-banana-2.1": "Nano Banana 2.1",
    "ideogram/v4.5": "Ideogram V4.5",
    "microsoft/mai-image-2.5": "MAI Image 2.5",
    "xai/grok-imagine-image/v2.0/text-to-image": "Grok Imagine 2.0",
    "fal-ai/z-image/turbo/lora": "Z-Image Turbo",
    "bytedance/seedream/v5/pro/text-to-image": "Seedream V5 Pro",
    # Image edit (Magix, Virtual Try-On)
    "google/nano-banana-2.1/edit": "Nano Banana 2.1",
    "openai/gpt-image-2.5/sunburst/edit": "GPT Image 2.5",
    "blackforestlabs/flux-3/edit-image": "Flux 3",
    "xai/grok-imagine-image/v2.0/edit": "Grok Imagine 2.0",
    "ideogram/v4.5/edit": "Ideogram V4.5",
    # Add text (Pillow, no provider)
    "sketchmaker/text-overlay": "Add text",
    # Explainer
    "openai/gpt-image-2": "GPT Image 2",
    "openai/gpt-image-2/edit": "GPT Image 2 (Edit)",
    # Logo
    "ideogram/vector/text-to-vector": "Ideogram Vector",
    "ideogram/vector/image-to-vector": "Ideogram Vectorize",
    # Stories
    "minimax/h3-max/text-to-video": "MiniMax H3 Max",
    "minimax/h3-max/image-to-video": "MiniMax H3 Max",
    "minimax/h3-max/reference-to-video": "MiniMax H3 Max",
    "bytedance/seedance-2.5/us/text-to-video": "Seedance 2.5",
    "bytedance/seedance-2.5/us/image-to-video": "Seedance 2.5",
    "bytedance/seedance-2.5/us/reference-to-video": "Seedance 2.5",
    "kling/v4/text-to-video": "Kling v4",
    "kling/v4/image-to-video": "Kling v4",
    "kling/v4/reference-to-video": "Kling v4",
    "blackforestlabs/flux-3-max/text-to-video": "FLUX 3 Max",
    "blackforestlabs/flux-3-max/image-to-video": "FLUX 3 Max",
    "blackforestlabs/flux-3-max/keyframes-to-video": "FLUX 3 Max",
    "google/gemini-omni-flash/v1.1/text-to-video": "Gemini Omni Flash 1.1",
    "google/gemini-omni-flash/v1.1/image-to-video": "Gemini Omni Flash 1.1",
    "google/gemini-omni-flash/v1.1/reference-to-video": "Gemini Omni Flash 1.1",
    # Lip sync
    "minimax/h3-max/lip-sync/image-to-video": "MiniMax H3 Max Lip Sync",
    # Studios (rendered by our own engine)
    "faceless-studio": "Faceless Studio",
    "motion-graphics-studio": "Motion Graphics Studio",
    # Motion control
    "fal-ai/kling-video/v2.6/standard/motion-control": "Kling 2.6 Motion Control",
    "fal-ai/kling-video/v3/standard/motion-control": "Kling 3 Motion Control",
    "fal-ai/kling-video/v3/pro/motion-control": "Kling 3 Pro Motion Control",
    # Subtitles
    "fal-ai/workflow-utilities/auto-subtitle": "Auto Subtitle",
    # Retired
    "bytedance/seedance-2.0/fast/text-to-video": "Seedance 2.0 Fast",
    "bytedance/seedance-2.0/fast/image-to-video": "Seedance 2.0 Fast",
    "bytedance/seedance-2.0/fast/reference-to-video": "Seedance 2.0 Fast",
    "fal-ai/gpt-image-1.5": "GPT Image 1.5",
    "fal-ai/bytedance/seedream/v4.5/text-to-image": "Seedream V4.5",
    "fal-ai/nano-banana-2": "Nano Banana 2",
    "fal-ai/nano-banana-2/edit": "Nano Banana 2",
    "fal-ai/flux-2-flex": "Flux 2 Flex",
    "fal-ai/flux-2-pro": "Flux 2 Pro",
    "fal-ai/flux-2-max": "Flux 2 Max",
    "fal-ai/flux-2/turbo": "Flux 2 Turbo",
    "fal-ai/flux-lora": "Flux LoRA",
    "ideogram/v4": "Ideogram V4",
    "fal-ai/imagen4/preview": "Imagen 4",
}


def model_display_name(model_id: str | None) -> str | None:
    """Readable name for a model id, or a tidied last path segment."""
    if not model_id:
        return None
    if model_id in MODEL_NAMES:
        return MODEL_NAMES[model_id]
    tail = model_id.rstrip("/").split("/")[-1]
    return tail.replace("-", " ") or model_id
