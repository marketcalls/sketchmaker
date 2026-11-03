"""Logo studio: text to SVG logo, image to SVG, iterations and brand tools.

AI actions (generate, iterate, simplify, vectorize) call fal; their cost is estimated
by app/services/pricing.py per stored SVG and recorded on success. Edits, wordmark
lockups, the brand sheet and fonts are deterministic code with no provider cost;
their results are rebuilt by app/utils/svg_sanitize.py before they are stored or
returned.
"""

import asyncio
import logging
import random
from datetime import datetime
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator, model_validator

from app.dependencies import CurrentUser, DbSession
from app.models.content import Image
from app.services import logo_brandkit, logo_fonts, logo_service
from app.services.logo_service import (
    ASPECT_RATIOS,
    DIRECTION_STYLES,
    FONT_STYLE_DESCRIPTORS,
    IMAGE_TO_VECTOR,
    MAX_PALETTE,
    MAX_REFERENCES,
    PERSONALITY_AXES,
    QUALITIES,
    REFERENCE_MAX_BYTES,
    SHOWCASE_ASPECT,
    SHOWCASE_BACKGROUNDS,
    SHOWCASE_MAX,
    SHOWCASE_MODEL,
    SHOWCASE_RESOLUTION,
    STYLE_DESCRIPTORS,
    TEXT_TO_VECTOR,
    VECTORIZE_MAX_BYTES,
    VECTORIZE_MODES,
    LogoGenerationError,
    LogoInputError,
    PatternDirection,
)
from app.services.pricing import LOGO_VECTORIZE_KEY, edit_usd, logo_text_key, usd_for
from app.services.usage import record_usage
from app.utils.svg_sanitize import SVGSanitizeError

logger = logging.getLogger(__name__)

router = APIRouter()

ART_STYLE_TEXT = "logo_text"
ART_STYLE_VECTORIZE = "logo_vectorize"
ART_STYLE_EDIT = "logo_edit"
ART_STYLE_LOCKUP = "logo_lockup"
LOGO_ART_STYLES = (ART_STYLE_TEXT, ART_STYLE_VECTORIZE, ART_STYLE_EDIT, ART_STYLE_LOCKUP)
# Raster showcase images: gallery images, not logos (no history, no studio).
ART_STYLE_SHOWCASE = "logo_showcase"

MAX_CONCEPTS = 8
MAX_ITERATIONS = 4

# Encoded size cap for one image string (base64 grows data by 4/3).
_REFERENCE_FIELD_MAX = REFERENCE_MAX_BYTES * 4 // 3 + 1024
_VECTORIZE_FIELD_MAX = VECTORIZE_MAX_BYTES * 4 // 3 + 1024

StylePreset = Literal[tuple(STYLE_DESCRIPTORS.keys())]  # type: ignore[valid-type]
FontStyle = Literal[tuple(FONT_STYLE_DESCRIPTORS.keys())]  # type: ignore[valid-type]
FontKey = Literal[tuple(logo_fonts.LOGO_FONTS.keys())]  # type: ignore[valid-type]
AspectRatio = Literal[ASPECT_RATIOS]  # type: ignore[valid-type]
Quality = Literal[QUALITIES]  # type: ignore[valid-type]
VectorizeMode = Literal[VECTORIZE_MODES]  # type: ignore[valid-type]
ShowcaseBackgroundId = Literal[tuple(SHOWCASE_BACKGROUNDS.keys())]  # type: ignore[valid-type]
HexColor = str


def _hex(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not logo_brandkit.HEX_COLOR.match(value):
        raise ValueError("Colors must be #RRGGBB hex values")
    return value.lower()


class LogoGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000, description="What the logo should show or convey")
    brand_name: Optional[str] = Field(default=None, max_length=60, description="Rendered exactly in the logo")
    style: Optional[StylePreset] = Field(default=None, description="Style preset")
    colors: Optional[str] = Field(default=None, max_length=120, description="Color palette in words or hex")
    aspect_ratio: AspectRatio = "1:1"
    quality: Quality = "medium"
    num_images: int = Field(default=2, ge=1, le=MAX_CONCEPTS)
    seed: Optional[int] = Field(default=None, ge=0, le=2147483647)
    reference_image_urls: Optional[List[str]] = Field(default=None, max_length=MAX_REFERENCES)
    # Guided brief
    tagline: Optional[str] = Field(default=None, max_length=80)
    include_tagline: bool = False
    industry: Optional[str] = Field(default=None, max_length=80)
    personality: Optional[Dict[str, int]] = None
    symbol_ideas: Optional[str] = Field(default=None, max_length=300)
    palette: Optional[List[HexColor]] = Field(default=None, max_length=MAX_PALETTE)
    font_style: Optional[FontStyle] = None
    avoid: Optional[str] = Field(default=None, max_length=300)
    symbol_only: bool = False
    # Explore directions: every concept follows a different pattern family.
    directions: bool = False

    @field_validator("prompt")
    @classmethod
    def _prompt_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Describe the logo you want")
        return value

    @model_validator(mode="after")
    def _directions_style(self) -> "LogoGenerateRequest":
        if self.directions and self.style not in DIRECTION_STYLES:
            raise ValueError("Explore directions works with the Minimal, Abstract or Geometric style, or no style")
        return self

    @field_validator("reference_image_urls")
    @classmethod
    def _reference_sizes(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value:
            for item in value:
                if len(item) > _REFERENCE_FIELD_MAX:
                    raise ValueError("Each reference image must be 10 MB or smaller")
        return value or None

    @field_validator("palette")
    @classmethod
    def _palette(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return [_hex(v) for v in value] if value else None

    @field_validator("personality")
    @classmethod
    def _personality(cls, value: Optional[Dict[str, int]]) -> Optional[Dict[str, int]]:
        if not value:
            return None
        for axis, level in value.items():
            if axis not in PERSONALITY_AXES:
                raise ValueError(f"Unknown personality axis '{axis}'")
            if not -2 <= level <= 2:
                raise ValueError("Personality values run from -2 to 2")
        return value


class LogoVectorizeRequest(BaseModel):
    image: str = Field(min_length=1, max_length=_VECTORIZE_FIELD_MAX, description="Data URL or https URL")
    mode: VectorizeMode = "default"


class LogoIterateRequest(BaseModel):
    reference_image: str = Field(min_length=1, max_length=_REFERENCE_FIELD_MAX,
                                 description="PNG of the logo rendered by the browser (data URL)")
    instruction: Optional[str] = Field(default=None, max_length=500, description="Empty for close variations")
    quality: Quality = "medium"
    num_images: int = Field(default=2, ge=1, le=MAX_ITERATIONS)
    aspect_ratio: Optional[AspectRatio] = None


class LogoSimplifyRequest(BaseModel):
    image: str = Field(min_length=1, max_length=_VECTORIZE_FIELD_MAX,
                       description="PNG of the logo rendered by the browser (data URL)")


class LogoShowcaseRequest(BaseModel):
    image: str = Field(min_length=1, max_length=_REFERENCE_FIELD_MAX,
                       description="PNG of the one-color mark rendered by the browser (data URL)")
    backgrounds: List[ShowcaseBackgroundId] = Field(min_length=1, max_length=SHOWCASE_MAX)
    typography: bool = True
    # Literal text set in the image, not prompt text: cleaned and quoted by
    # logo_service.build_showcase_prompt.
    brand_name: Optional[str] = Field(default=None, max_length=60)
    descriptor: Optional[str] = Field(default=None, max_length=48)

    @field_validator("backgrounds")
    @classmethod
    def _unique(cls, value: List[str]) -> List[str]:
        if len(set(value)) != len(value):
            raise ValueError("Pick each background once")
        return value


class ColorPair(BaseModel):
    source: HexColor
    target: HexColor

    @field_validator("source", "target")
    @classmethod
    def _color(cls, value: str) -> str:
        return _hex(value)


class LogoEditRequest(BaseModel):
    operation: Literal["recolor", "mono", "invert", "transparent"]
    mapping: Optional[List[ColorPair]] = Field(default=None, max_length=12)
    tolerance: int = Field(default=0, ge=0, le=100)
    color: Optional[HexColor] = None
    paper: Optional[HexColor] = None
    remove_background: bool = False
    knockout: bool = False
    save: bool = False

    @field_validator("color", "paper")
    @classmethod
    def _color(cls, value: Optional[str]) -> Optional[str]:
        return _hex(value)


class LogoLockupRequest(BaseModel):
    brand_name: str = Field(min_length=1, max_length=60)
    tagline: Optional[str] = Field(default=None, max_length=80)
    font: FontKey = logo_fonts.DEFAULT_FONT
    weight: Optional[int] = Field(default=None, ge=100, le=900)
    tagline_font: Optional[FontKey] = None
    tagline_weight: Optional[int] = Field(default=None, ge=100, le=900)
    layout: Literal["horizontal", "stacked", "text"] = "horizontal"
    text_color: HexColor = "#111111"
    tagline_color: Optional[HexColor] = None
    tracking: int = Field(default=0, ge=-100, le=400)
    uppercase: bool = False
    remove_background: bool = True
    knockout: bool = False
    save: bool = False

    @field_validator("text_color", "tagline_color")
    @classmethod
    def _color(cls, value: Optional[str]) -> Optional[str]:
        return _hex(value)

    @field_validator("brand_name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter the brand name")
        return value


class LogoBrandSheetRequest(BaseModel):
    brand_name: str = Field(min_length=1, max_length=60)
    tagline: Optional[str] = Field(default=None, max_length=80)
    heading_font: FontKey = "playfair"
    heading_weight: Optional[int] = Field(default=None, ge=100, le=900)
    body_font: FontKey = "inter"
    palette: Optional[List[HexColor]] = Field(default=None, max_length=6)

    @field_validator("palette")
    @classmethod
    def _palette(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return [_hex(v) for v in value] if value else None


class LogoItem(BaseModel):
    id: int
    url: str
    prompt: str
    art_style: Optional[str] = None
    model: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    seed: Optional[int] = None
    aspect_ratio: Optional[str] = None
    rendering: Optional[str] = None
    created_at: Optional[datetime] = None
    # Explore directions only (not stored): the pattern family and why.
    direction: Optional[str] = None
    rationale: Optional[str] = None


class LogoGenerateResponse(BaseModel):
    images: List[LogoItem]
    prompt: str
    seed: Optional[int] = None
    requested: int
    delivered: int
    estimated_usd: float


class ShowcaseItem(BaseModel):
    id: int
    url: str
    background: str
    background_name: str
    width: Optional[int] = None
    height: Optional[int] = None


class LogoShowcaseResponse(BaseModel):
    images: List[ShowcaseItem]
    requested: int
    delivered: int
    estimated_usd: float


class LogoHistoryResponse(BaseModel):
    items: List[LogoItem]
    total: int
    limit: int
    offset: int


class LogoSvgResponse(BaseModel):
    svg: str
    width: Optional[int] = None
    height: Optional[int] = None
    item: Optional[LogoItem] = None


class LogoColorsResponse(BaseModel):
    colors: List[dict]
    background: Optional[str] = None
    total_colors: int


def _item(image: Image) -> LogoItem:
    return LogoItem(
        id=image.id,
        url=image.get_url(),
        prompt=image.prompt,
        art_style=image.art_style,
        model=image.model,
        width=image.width,
        height=image.height,
        seed=image.seed,
        aspect_ratio=image.aspect_ratio,
        rendering=image.rendering,
        created_at=image.created_at,
    )


def _owned_logo(db, user_id: int, logo_id: int) -> Image:
    image = db.query(Image).filter(
        Image.id == logo_id,
        Image.user_id == user_id,
        Image.art_style.in_(LOGO_ART_STYLES),
    ).first()
    if image is None or not (image.filename or "").lower().endswith(".svg"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logo not found")
    return image


def _save_images(db, user_id: int, stored: list[dict], *, prompt: str, final_prompt: str,
                 art_style: str, model: str, seed: Optional[int], aspect_ratio: Optional[str],
                 rendering: str) -> list[Image]:
    rows = []
    for item in stored:
        row = Image(
            filename=item["filename"],
            prompt=prompt,
            magic_prompt=final_prompt,
            art_style=art_style,
            width=item.get("width"),
            height=item.get("height"),
            model=model,
            seed=seed,
            rendering=rendering,
            aspect_ratio=aspect_ratio,
            user_id=user_id,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def _raise_for(exc: Exception) -> None:
    """Map the errors of a logo request to HTTP responses."""
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, (LogoInputError, logo_brandkit.LogoEditError, logo_fonts.FontError)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, SVGSanitizeError):
        # Its message can quote the XML parser; keep that in the log.
        logger.warning(f"Logo SVG rejected: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The SVG could not be read. Export it again as a plain SVG, or upload a PNG.",
        )
    if isinstance(exc, LogoGenerationError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{exc}.",
        )
    if isinstance(exc, ValueError):
        logger.exception("Logo request failed")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Logo generation failed. Please try again.",
        )
    logger.exception("Logo request failed")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Logo generation failed. Please try again.",
    )


async def _text_to_vector(db, user_id: int, *, final_prompt: str,
                          label_prompt: str, quality: str, num_images: int, aspect_ratio: str,
                          seed: int, references: list[str], usage: dict) -> LogoGenerateResponse:
    """Check the references, call text-to-vector, store and record usage.

    Raises; the caller maps exceptions with _raise_for.
    """
    per_logo = usd_for(logo_text_key(quality, with_references=bool(references)))

    # Check and upload references before the model is called.
    fal_refs = [
        await logo_service.prepare_fal_image(db, ref, REFERENCE_MAX_BYTES, f"Reference image {i + 1}")
        for i, ref in enumerate(references)
    ]
    arguments = {
        "prompt": final_prompt,
        "aspect_ratio": aspect_ratio,
        "quality": quality,
        "num_images": num_images,
        "seed": seed,
    }
    if fal_refs:
        arguments["image_urls"] = fal_refs

    result = await logo_service.call_fal(db, TEXT_TO_VECTOR, arguments)
    stored = await logo_service.store_result_svgs(result, user_id, num_images)
    if not stored:
        raise LogoGenerationError("The logo model returned no usable SVG")

    result_seed = result.get("seed") if isinstance(result.get("seed"), int) else seed
    rows = _save_images(
        db, user_id, stored,
        prompt=label_prompt,
        final_prompt=final_prompt,
        art_style=ART_STYLE_TEXT,
        model=TEXT_TO_VECTOR,
        seed=result_seed,
        aspect_ratio=aspect_ratio,
        rendering=quality,
    )
    delivered = len(rows)
    estimated_usd = round(per_logo * delivered, 4)

    record_usage(
        db,
        feature="logo",
        usd=estimated_usd,
        model=TEXT_TO_VECTOR,
        units=delivered,
        unit="svg",
        detail={
            **usage,
            "quality": quality,
            "aspect_ratio": aspect_ratio,
            "num_requested": num_images,
            "num_references": len(fal_refs),
            "seed": result_seed,
        },
    )
    response = LogoGenerateResponse(
        images=[_item(row) for row in rows],
        prompt=final_prompt,
        seed=result_seed,
        requested=num_images,
        delivered=delivered,
        estimated_usd=estimated_usd,
    )
    db.commit()
    return response


async def _explore_directions(db, user_id: int, *,
                              concepts: list[tuple[PatternDirection, str]], base_prompt: str,
                              label_prompt: str, quality: str, aspect_ratio: str, seed: int,
                              references: list[str], usage: dict) -> LogoGenerateResponse:
    """Explore directions: one text-to-vector call per concept, each with its
    own pattern family prompt, run side by side. Priced like _text_to_vector
    (per stored SVG).

    Raises; the caller maps exceptions with _raise_for.
    """
    num_images = len(concepts)
    per_logo = usd_for(logo_text_key(quality, with_references=bool(references)))

    fal_refs = [
        await logo_service.prepare_fal_image(db, ref, REFERENCE_MAX_BYTES, f"Reference image {i + 1}")
        for i, ref in enumerate(references)
    ]

    async def one(index: int, prompt: str) -> tuple[int, list[dict]]:
        call_seed = (seed + index) % 2147483648
        arguments = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "quality": quality,
            "num_images": 1,
            "seed": call_seed,
        }
        if fal_refs:
            arguments["image_urls"] = fal_refs
        try:
            result = await logo_service.call_fal(db, TEXT_TO_VECTOR, arguments)
        except LogoGenerationError:
            return call_seed, []
        result_seed = result.get("seed") if isinstance(result.get("seed"), int) else call_seed
        return result_seed, await logo_service.store_result_svgs(result, user_id, 1)

    # return_exceptions: one failed concept must not discard the others.
    outcomes = await asyncio.gather(*(one(i, prompt) for i, (_, prompt) in enumerate(concepts)),
                                    return_exceptions=True)
    failures = [o for o in outcomes if isinstance(o, BaseException)]
    for failure in failures:
        logger.warning("An explore-directions concept failed: %r", failure)

    items: list[LogoItem] = []
    for (direction, prompt), outcome in zip(concepts, outcomes):
        if isinstance(outcome, BaseException):
            continue
        result_seed, stored = outcome
        if not stored:
            continue
        row = _save_images(
            db, user_id, stored[:1],
            prompt=label_prompt,
            final_prompt=prompt,
            art_style=ART_STYLE_TEXT,
            model=TEXT_TO_VECTOR,
            seed=result_seed,
            aspect_ratio=aspect_ratio,
            rendering=quality,
        )[0]
        items.append(_item(row).model_copy(update={
            "direction": direction.name,
            "rationale": direction.rationale(label_prompt),
        }))
    if not items:
        if failures:
            raise failures[0]
        raise LogoGenerationError("The logo model returned no usable SVG")

    delivered = len(items)
    estimated_usd = round(per_logo * delivered, 4)

    record_usage(
        db,
        feature="logo",
        usd=estimated_usd,
        model=TEXT_TO_VECTOR,
        units=delivered,
        unit="svg",
        detail={
            **usage,
            "quality": quality,
            "aspect_ratio": aspect_ratio,
            "num_requested": num_images,
            "num_references": len(fal_refs),
            "seed": seed,
            "directions": [d.family.key for d, _ in concepts],
        },
    )
    response = LogoGenerateResponse(
        images=items,
        prompt=base_prompt,
        seed=seed,
        requested=num_images,
        delivered=delivered,
        estimated_usd=estimated_usd,
    )
    db.commit()
    return response


async def _image_to_vector(db, user_id: int, *, image: str, mode: str,
                           label: str, final_prompt: str, usage: dict) -> LogoGenerateResponse:
    per_logo = usd_for(LOGO_VECTORIZE_KEY)
    fal_url = await logo_service.prepare_fal_image(db, image, VECTORIZE_MAX_BYTES, "Image")

    result = await logo_service.call_fal(db, IMAGE_TO_VECTOR, {"image_url": fal_url, "mode": mode})
    stored = await logo_service.store_result_svgs(result, user_id, 1)
    if not stored:
        raise LogoGenerationError("The vectorizer returned no usable SVG")

    result_seed = result.get("seed") if isinstance(result.get("seed"), int) else None
    rows = _save_images(
        db, user_id, stored,
        prompt=label,
        final_prompt=final_prompt,
        art_style=ART_STYLE_VECTORIZE,
        model=IMAGE_TO_VECTOR,
        seed=result_seed,
        aspect_ratio=None,
        rendering=mode,
    )
    record_usage(
        db,
        feature="logo",
        usd=per_logo,
        model=IMAGE_TO_VECTOR,
        units=1,
        unit="svg",
        detail={**usage, "vectorize_mode": mode},
    )
    response = LogoGenerateResponse(
        images=[_item(row) for row in rows],
        prompt=label,
        seed=result_seed,
        requested=1,
        delivered=len(rows),
        estimated_usd=per_logo,
    )
    db.commit()
    return response


def _derived_prompt(prefix: str, parent: Image) -> str:
    text = f"{prefix}: {parent.prompt}" if parent.prompt else prefix
    return text[:2000]


async def _store_derived(db, user_id: int, parent: Image, data: bytes, *, art_style: str,
                         label: str, rendering: str) -> Image:
    stored = await logo_service.store_svg(data, user_id)
    row = _save_images(
        db, user_id, [stored],
        prompt=_derived_prompt(label, parent),
        final_prompt=parent.magic_prompt or parent.prompt,
        art_style=art_style,
        model="sketchmaker/logo-studio",
        seed=parent.seed,
        aspect_ratio=parent.aspect_ratio if art_style == ART_STYLE_EDIT else None,
        rendering=rendering,
    )[0]
    db.commit()
    return row


def _svg_response(data: bytes, item: Optional[Image] = None) -> LogoSvgResponse:
    from app.utils.svg_sanitize import svg_dimensions
    from lxml import etree

    root = etree.fromstring(data, parser=logo_brandkit._parser())
    width, height = svg_dimensions(root)
    return LogoSvgResponse(svg=data.decode("utf-8"), width=width, height=height,
                           item=_item(item) if item is not None else None)


# ---------------------------------------------------------------------------
# AI actions
# ---------------------------------------------------------------------------

@router.post("/generate", response_model=LogoGenerateResponse)
async def generate_logo(
    body: LogoGenerateRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Generate SVG logo concepts from a brief with Ideogram Vector."""
    references = [r for r in (body.reference_image_urls or []) if r and r.strip()]

    final_prompt = logo_service.build_logo_prompt(
        body.prompt, body.brand_name, body.style, body.colors, has_references=bool(references),
        tagline=body.tagline, include_tagline=body.include_tagline, industry=body.industry,
        personality=body.personality, symbol_ideas=body.symbol_ideas, palette=body.palette,
        font_style=body.font_style, avoid=body.avoid, symbol_only=body.symbol_only,
    )
    seed = body.seed if body.seed is not None else random.randint(0, 2147483647)

    if body.directions:
        concepts = [
            (direction, logo_service.build_logo_prompt(
                body.prompt, body.brand_name, body.style, body.colors, has_references=bool(references),
                tagline=body.tagline, include_tagline=body.include_tagline, industry=body.industry,
                personality=body.personality, symbol_ideas=body.symbol_ideas, palette=body.palette,
                font_style=body.font_style, avoid=body.avoid, symbol_only=body.symbol_only,
                direction=direction,
            ))
            for direction in logo_service.pattern_directions(body.num_images, seed)
        ]
        try:
            return await _explore_directions(
                db, current_user.id,
                concepts=concepts,
                base_prompt=final_prompt,
                label_prompt=body.prompt.strip(),
                quality=body.quality,
                aspect_ratio=body.aspect_ratio,
                seed=seed,
                references=references,
                usage={
                    "mode": "directions",
                    "prompt": body.prompt[:200],
                    "brand_name": body.brand_name,
                    "style": body.style,
                    "industry": body.industry,
                    "font_style": body.font_style,
                    "symbol_only": body.symbol_only,
                    "palette": body.palette,
                },
            )
        except Exception as exc:
            _raise_for(exc)

    try:
        return await _text_to_vector(
            db, current_user.id,
            final_prompt=final_prompt,
            label_prompt=body.prompt.strip(),
            quality=body.quality,
            num_images=body.num_images,
            aspect_ratio=body.aspect_ratio,
            seed=seed,
            references=references,
            usage={
                "mode": "text",
                "prompt": body.prompt[:200],
                "brand_name": body.brand_name,
                "style": body.style,
                "industry": body.industry,
                "font_style": body.font_style,
                "symbol_only": body.symbol_only,
                "palette": body.palette,
            },
        )
    except Exception as exc:
        _raise_for(exc)


@router.post("/vectorize", response_model=LogoGenerateResponse)
async def vectorize_image(
    body: LogoVectorizeRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Convert an uploaded image into an SVG with Ideogram Vector."""
    label = f"Vectorized image ({body.mode} mode)"
    try:
        return await _image_to_vector(db, current_user.id, image=body.image, mode=body.mode,
                                      label=label, final_prompt=label, usage={"mode": "vectorize"})
    except Exception as exc:
        _raise_for(exc)


@router.post("/{logo_id}/iterate", response_model=LogoGenerateResponse)
async def iterate_logo(
    logo_id: int,
    body: LogoIterateRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Refine a logo with an instruction, or make close variations of it.

    The logo goes to text-to-vector as the reference image (the browser
    renders it to PNG, since the model reads raster references), so this is
    priced as generation with references.
    """
    parent = _owned_logo(db, current_user.id, logo_id)
    instruction = (body.instruction or "").strip()
    final_prompt = logo_service.build_iteration_prompt(parent.magic_prompt or parent.prompt, instruction)
    aspect = body.aspect_ratio or (parent.aspect_ratio if parent.aspect_ratio in ASPECT_RATIOS else "1:1")
    label = _derived_prompt(f"Refined ({instruction})" if instruction else "Variation", parent)
    try:
        return await _text_to_vector(
            db, current_user.id,
            final_prompt=final_prompt,
            label_prompt=label,
            quality=body.quality,
            num_images=body.num_images,
            aspect_ratio=aspect,
            seed=random.randint(0, 2147483647),
            references=[body.reference_image],
            usage={"mode": "refine" if instruction else "variations", "parent_id": parent.id,
                   "instruction": instruction[:200] or None},
        )
    except Exception as exc:
        _raise_for(exc)


@router.post("/{logo_id}/simplify", response_model=LogoGenerateResponse)
async def simplify_logo(
    logo_id: int,
    body: LogoSimplifyRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retrace a logo with fewer, flatter shapes (image-to-vector, simple mode)."""
    parent = _owned_logo(db, current_user.id, logo_id)
    try:
        return await _image_to_vector(
            db, current_user.id, image=body.image, mode="simple",
            label=_derived_prompt("Simplified", parent),
            final_prompt=parent.magic_prompt or parent.prompt,
            usage={"mode": "simplify", "parent_id": parent.id},
        )
    except Exception as exc:
        _raise_for(exc)


@router.post("/{logo_id}/showcase", response_model=LogoShowcaseResponse)
async def showcase_logo(
    logo_id: int,
    body: LogoShowcaseRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Showcase images: the one-color mark centred on curated 16:9 backdrops
    at 2K (Nano Banana 2.1 edit), one per chosen background.

    The browser renders the mark to PNG; the prompt comes only from the
    backdrop ids and the cleaned brand text. Results are raster gallery images.
    """
    parent = _owned_logo(db, current_user.id, logo_id)
    count = len(body.backgrounds)
    per_image = edit_usd(SHOWCASE_MODEL, SHOWCASE_RESOLUTION)

    prompts = [
        (bg, logo_service.build_showcase_prompt(bg, body.brand_name or "", body.descriptor or "", body.typography))
        for bg in body.backgrounds
    ]
    try:
        # Check and upload the mark before the model is called.
        mark_url = await logo_service.prepare_fal_image(db, body.image, REFERENCE_MAX_BYTES, "Logo image")

        # The brand text is drawn by the app, not the model (spelled exactly).
        overlay = logo_service.showcase_overlay(body.brand_name or "", body.descriptor or "", body.typography)
        outcomes = await asyncio.gather(
            *(logo_service.render_showcase(db, mark_url, prompt, current_user.id, overlay=overlay)
              for _, prompt in prompts),
            return_exceptions=True,
        )
        failures = [o for o in outcomes if isinstance(o, BaseException)]
        for failure in failures:
            logger.warning("A logo showcase image failed: %r", failure)

        items: list[ShowcaseItem] = []
        for (bg, prompt), stored in zip(prompts, outcomes):
            if not stored or isinstance(stored, BaseException):
                continue
            name = SHOWCASE_BACKGROUNDS[bg].name
            row = _save_images(
                db, current_user.id, [stored],
                prompt=_derived_prompt(f"Showcase, {name}", parent),
                final_prompt=prompt,
                art_style=ART_STYLE_SHOWCASE,
                model=SHOWCASE_MODEL,
                seed=None,
                aspect_ratio=SHOWCASE_ASPECT,
                rendering=bg,
            )[0]
            items.append(ShowcaseItem(id=row.id, url=row.get_url(), background=bg, background_name=name,
                                      width=row.width, height=row.height))
        if not items:
            if failures:
                raise failures[0]
            raise LogoGenerationError("The image model returned no showcase image")

        delivered = len(items)
        estimated_usd = round(per_image * delivered, 4)

        record_usage(
            db,
            feature="logo",
            usd=estimated_usd,
            model=SHOWCASE_MODEL,
            units=delivered,
            unit="image",
            detail={
                "mode": "showcase",
                "parent_id": parent.id,
                "backgrounds": list(body.backgrounds),
                "typography": body.typography,
                "num_requested": count,
                "resolution": SHOWCASE_RESOLUTION,
            },
        )
        response = LogoShowcaseResponse(
            images=items,
            requested=count,
            delivered=delivered,
            estimated_usd=estimated_usd,
        )
        db.commit()
        return response
    except Exception as exc:
        _raise_for(exc)


# ---------------------------------------------------------------------------
# Tools with no provider cost
# ---------------------------------------------------------------------------

_FONT_LIST_CACHE: list[dict] | None = None


def _font_list() -> list[dict]:
    """The font list with previews. The fonts are bundled files, so it is
    built once per worker instead of tracing every font on every request."""
    global _FONT_LIST_CACHE
    if _FONT_LIST_CACHE is None:
        fonts = []
        for font in logo_fonts.available_fonts():
            try:
                font["preview"] = logo_brandkit.font_preview(font["key"])
            except (logo_fonts.FontError, OSError):
                continue
            fonts.append(font)
        _FONT_LIST_CACHE = fonts
    return _FONT_LIST_CACHE


@router.get("/fonts")
async def logo_fonts_list(current_user: CurrentUser):
    """Wordmark fonts (bundled OFL families) with a vector preview of each name,
    and the heading/body pairing for each lettering style of the brief."""
    fonts = await run_in_threadpool(_font_list)
    return {"fonts": [dict(f) for f in fonts], "pairings": logo_fonts.FONT_PAIRINGS}


@router.get("/{logo_id}/colors", response_model=LogoColorsResponse)
async def logo_colors(logo_id: int, current_user: CurrentUser, db: DbSession):
    """Dominant colors of a logo (weighted by drawn area) and its background."""
    image = _owned_logo(db, current_user.id, logo_id)
    try:
        data = await logo_service.load_stored_svg(image.filename, image.user_id)
        root = await run_in_threadpool(logo_brandkit.load, data)
        result = await run_in_threadpool(logo_brandkit.palette, root)
        return LogoColorsResponse(**result)
    except Exception as exc:
        _raise_for(exc)


@router.post("/{logo_id}/edit", response_model=LogoSvgResponse)
async def edit_logo(logo_id: int, body: LogoEditRequest, current_user: CurrentUser, db: DbSession):
    """Recolor, one-color, inverted or transparent version of a logo.

    With save=false the sanitised SVG is only returned (live preview); with
    save=true it is also stored as a new logo.
    """
    image = _owned_logo(db, current_user.id, logo_id)
    try:
        data = await logo_service.load_stored_svg(image.filename, image.user_id)
        mapping = [(p.source, p.target) for p in (body.mapping or [])]
        out = await run_in_threadpool(
            lambda: logo_brandkit.apply_operation(
                data, body.operation, mapping=mapping, tolerance=body.tolerance, color=body.color,
                paper=body.paper, remove_bg=body.remove_background, knockout=body.knockout,
            )
        )
        row = None
        if body.save:
            labels = {"recolor": "Recolored", "mono": f"One color {body.color or '#111111'}",
                      "invert": "Inverted", "transparent": "Transparent"}
            row = await _store_derived(db, current_user.id, image, out, art_style=ART_STYLE_EDIT,
                                       label=labels[body.operation], rendering=body.operation)
        return _svg_response(out, row)
    except Exception as exc:
        _raise_for(exc)


def _lockup_spec(body: LogoLockupRequest) -> logo_brandkit.LockupSpec:
    return logo_brandkit.LockupSpec(
        brand_name=body.brand_name,
        tagline=body.tagline or "",
        font=body.font,
        weight=body.weight,
        tagline_font=body.tagline_font,
        tagline_weight=body.tagline_weight,
        layout=body.layout,
        text_color=body.text_color,
        tagline_color=body.tagline_color,
        tracking=body.tracking,
        uppercase=body.uppercase,
        remove_background=body.remove_background,
        knockout=body.knockout,
    )


@router.post("/{logo_id}/lockup", response_model=LogoSvgResponse)
async def lockup_logo(logo_id: int, body: LogoLockupRequest, current_user: CurrentUser, db: DbSession):
    """The symbol with the brand name set in a real font as vector paths
    (exact spelling). Layouts: horizontal, stacked, or text only."""
    image = _owned_logo(db, current_user.id, logo_id)
    try:
        data = None
        if body.layout != "text":
            data = await logo_service.load_stored_svg(image.filename, image.user_id)
        out = await run_in_threadpool(logo_brandkit.build_lockup, data, _lockup_spec(body))
        row = None
        if body.save:
            row = await _store_derived(db, current_user.id, image, out, art_style=ART_STYLE_LOCKUP,
                                       label=f"Wordmark {body.brand_name.strip()}", rendering=body.layout)
        return _svg_response(out, row)
    except Exception as exc:
        _raise_for(exc)


@router.post("/{logo_id}/brand-sheet", response_model=LogoSvgResponse)
async def brand_sheet(logo_id: int, body: LogoBrandSheetRequest, current_user: CurrentUser, db: DbSession):
    """A one-page brand sheet (logo and clear space, one-color variations,
    palette with hex and RGB, type specimens) as SVG. Not stored."""
    image = _owned_logo(db, current_user.id, logo_id)
    try:
        data = await logo_service.load_stored_svg(image.filename, image.user_id)
        out, width, height = await run_in_threadpool(
            lambda: logo_brandkit.build_brand_sheet(
                data, brand_name=body.brand_name.strip(), tagline=(body.tagline or "").strip(),
                heading_font=body.heading_font, heading_weight=body.heading_weight,
                body_font=body.body_font, colors=body.palette,
            )
        )
        return LogoSvgResponse(svg=out.decode("utf-8"), width=width, height=height)
    except Exception as exc:
        _raise_for(exc)


@router.get("/history", response_model=LogoHistoryResponse)
async def logo_history(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """The user's logos, newest first."""
    query = db.query(Image).filter(
        Image.user_id == current_user.id,
        Image.art_style.in_(LOGO_ART_STYLES),
    )
    total = query.count()
    rows = query.order_by(Image.created_at.desc(), Image.id.desc()).offset(offset).limit(limit).all()
    return LogoHistoryResponse(items=[_item(row) for row in rows], total=total, limit=limit, offset=offset)
