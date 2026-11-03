"""Magix - AI Image Enhancement using a choice of image edit models.

Allows users to upload images and describe modifications/additions.
Uses the FAL edit models in EDIT_MODEL_CONFIG (Nano Banana 2.1 by default).
Supports LLM-enhanced prompts for hyperrealistic output.
"""

import logging
from typing import Optional, List, Dict, Any, Literal
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.dependencies import CurrentUser, DbSession
from app.models.content import Image
from app.models.api import APISettings, APIProvider, AIModel
from app.schemas.image import ImageResponse
from app.clients.fal_client import DEFAULT_EDIT_MODEL, generate_magix_image, validate_edit_model
from app.clients.litellm_client import enhance_magix_prompt
from app.services.edit_prompts import clean_role
from app.services.pricing import edit_usd
from app.services.usage import record_usage

logger = logging.getLogger(__name__)

router = APIRouter()

# Previous edits passed to the LLM for context.
MAX_EDIT_HISTORY = 10


class EditHistoryItem(BaseModel):
    """Single edit in the conversation history."""
    prompt: str = Field(max_length=5000, description="The edit prompt that was applied")
    timestamp: Optional[str] = Field(default=None, description="When this edit was applied")


class MagixGenerateRequest(BaseModel):
    """Request schema for Magix generation."""
    prompt: str = Field(default="", max_length=5000, description="What to add or modify")
    image_url: Optional[str] = Field(default=None, description="Base64 data URL of single image (legacy)")
    image_urls: Optional[List[str]] = Field(default=None, description="Base64 data URLs - multiple images are combined into one output")
    mode: str = Field(default="studio_portrait", description="Portrait mode to apply")
    # Edit history for context (previous edits in this session)
    edit_history: Optional[List[EditHistoryItem]] = Field(default=None, description="Previous edits applied in this session for context")
    # Mode-specific options
    background: Optional[str] = Field(default=None, description="Background option for corporate_headshot")
    aesthetic: Optional[str] = Field(default=None, description="Aesthetic option for influencer")
    dating_vibe: Optional[str] = Field(default=None, description="Vibe option for dating")
    vibe: Optional[str] = Field(default=None, description="Vibe option for founder_headshot")
    style: Optional[str] = Field(default=None, description="Style option for avatar")
    # Product mode: the surface it stands on and the label copy to keep exact
    surface: Optional[str] = Field(default=None, max_length=40, description="Surface option for product")
    label_text: Optional[str] = Field(default=None, max_length=120, description="Exact label text for product")
    # One job per image (edit_prompts.IMAGE_ROLES), in image order: image 1 is
    # the photo being edited, every further image lends only its role.
    image_roles: Optional[List[str]] = Field(default=None, max_length=16, description="Role of each input image")
    # Generation settings
    model: str = Field(default=DEFAULT_EDIT_MODEL, max_length=100, description="Edit model (see EDIT_MODEL_CONFIG)")
    seed: Optional[int] = Field(default=None, description="Seed for reproducibility")
    aspect_ratio: Optional[str] = Field(default="auto", description="Output aspect ratio")
    resolution: str = Field(default="1K", description="Output resolution: 1K, 2K, or 4K")
    # Literal, not str: the value ends up in the stored filename.
    output_format: Literal["png", "jpeg", "webp"] = Field(default="png", description="Output format: png or jpeg")
    num_images: int = Field(default=1, ge=1, le=4, description="Number of images to generate")
    # Prompt enhancement
    enhance_prompt: bool = Field(default=True, description="Use LLM to enhance prompt for hyperrealistic output")


class MagixImageResult(BaseModel):
    """Single image result."""
    url: str
    seed: Optional[int] = None
    gallery_id: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None


class MagixGenerateResponse(BaseModel):
    """Response schema for Magix generation."""
    image_url: Optional[str] = None  # Legacy single image
    images: Optional[List[MagixImageResult]] = None  # Batch results
    seed: Optional[int] = None
    prompt: str
    gallery_id: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None


@router.post("/generate", response_model=MagixGenerateResponse)
async def generate_magix(
    body: MagixGenerateRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Generate a Magix-enhanced image with the chosen edit model.

    Upload one or more images and describe what you want to add or modify.
    The AI will intelligently enhance your images based on your prompt.

    IMPORTANT: When multiple images are uploaded, they are ALL combined into
    a SINGLE output image. This is great for creating group photos, family
    portraits, or merging different scenes together.
    """
    # Determine images to process - all will be combined into ONE output
    images_to_process = []
    if body.image_urls:
        images_to_process = body.image_urls
    elif body.image_url:
        images_to_process = [body.image_url]

    if not images_to_process:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No images provided. Please upload at least one image.",
        )

    num_input_images = len(images_to_process)

    if not validate_edit_model(body.model):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model '{body.model}' is not available for Magix",
        )

    resolution = (body.resolution or "1K").upper()
    if resolution not in ("1K", "2K", "4K"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resolution must be 1K, 2K or 4K",
        )

    # One output per request, however many input images are combined into it,
    # priced by edit model and resolution (app/services/pricing.py).
    per_edit = edit_usd(body.model, resolution)

    try:
        # Build mode options from the request
        mode_options: Dict[str, Any] = {}
        if body.background:
            mode_options["background"] = body.background
        if body.aesthetic:
            mode_options["aesthetic"] = body.aesthetic
        if body.dating_vibe:
            mode_options["dating_vibe"] = body.dating_vibe
        if body.vibe:
            mode_options["vibe"] = body.vibe
        if body.style:
            mode_options["style"] = body.style
        if body.surface:
            mode_options["surface"] = body.surface
        if body.label_text and body.label_text.strip():
            mode_options["label_text"] = body.label_text.strip()
        image_roles = [clean_role(r) for r in (body.image_roles or [])]

        # Mode display names
        mode_display_names = {
            "studio_portrait": "Studio Portrait",
            "cinematic": "Cinematic",
            "corporate_headshot": "Corporate Headshot",
            "fashion_editorial": "Fashion Editorial",
            "dating": "Dating Profile",
            "founder_headshot": "Founder Headshot",
            "influencer": "Influencer",
            "street_portrait": "Street Portrait",
            "environmental": "Environmental",
            "lifestyle": "Lifestyle",
            "low_key": "Low-Key Dramatic",
            "high_key": "High-Key Bright",
            "black_white": "Black & White",
            "beauty_closeup": "Beauty Close-Up",
            "athletic": "Athletic",
            "creative_color": "Creative Color",
            "vintage_retro": "Vintage Retro",
            "minimalist": "Minimalist",
            "cultural": "Cultural",
            "conceptual": "Conceptual Art",
            "luxury": "Luxury",
            "avatar": "Avatar",
            "restoration": "Restoration",
            "product": "Product",
        }
        rendering_name = mode_display_names.get(body.mode, body.mode.replace("_", " ").title())

        # Parse user intent using LLM for hybrid prompting
        user_intent_json = None

        if body.enhance_prompt and body.prompt:
            try:
                # Get API settings and default provider/model (same as /generate route)
                api_settings = db.query(APISettings).first()
                if api_settings and api_settings.default_provider_id and api_settings.default_model_id:
                    # Lookup provider and model from database
                    provider = db.query(APIProvider).filter(APIProvider.id == api_settings.default_provider_id).first()
                    model = db.query(AIModel).filter(AIModel.id == api_settings.default_model_id).first()

                    if provider and model:
                        logger.debug(f"[Magix] Parsing user intent with {provider.name}/{model.name}")
                        logger.debug(f"[Magix] User prompt: {body.prompt}")
                        # Build edit history for context
                        edit_history_list = None
                        if body.edit_history:
                            # Only the recent edits matter for context, and an
                            # uncapped list is an uncapped LLM bill.
                            edit_history_list = [
                                {"prompt": item.prompt, "timestamp": item.timestamp}
                                for item in body.edit_history[-MAX_EDIT_HISTORY:]
                            ]
                            logger.debug(f"[Magix] Edit history: {len(edit_history_list)} previous edits")
                        user_intent_json = await enhance_magix_prompt(
                            user_prompt=body.prompt,
                            mode=body.mode,
                            model_name=model.name,
                            provider_name=provider.name,
                            db=db,
                            num_images=num_input_images,
                            edit_history=edit_history_list,
                        )
                        logger.debug(f"[Magix] User intent parsed successfully")
                        logger.debug(f"[Magix] Edit type: {user_intent_json.get('edit_type', 'unknown')}")
                        if user_intent_json.get("scene_override", {}).get("location"):
                            logger.debug(f"[Magix] Location override: {user_intent_json['scene_override']['location']}")
                        if user_intent_json.get("framing_override", {}).get("shot_type"):
                            logger.debug(f"[Magix] Framing override: {user_intent_json['framing_override']['shot_type']}")
                    else:
                        logger.debug(f"[Magix] Intent parsing skipped - provider or model not found")
                else:
                    logger.debug(f"[Magix] Intent parsing skipped - default provider/model not configured")
            except Exception as e:
                logger.warning(f"[Magix] Intent parsing failed: {e}")
                import traceback
                traceback.print_exc()

        # Always pass ALL images together - the edit model combines them into one output
        # User intent will be MERGED with mode template for hybrid approach
        result = await generate_magix_image(
            prompt=body.prompt,
            db=db,
            image_urls=images_to_process,  # Pass all images - they are combined into ONE output
            mode=body.mode,
            mode_options=mode_options if mode_options else None,
            seed=body.seed,
            aspect_ratio=body.aspect_ratio,
            resolution=resolution,
            output_format=body.output_format,
            # Only the first image is kept, so asking FAL for more would pay
            # for images nobody receives.
            num_images=1,
            user_intent_json=user_intent_json,  # Pass user intent to merge with template
            user_id=current_user.id,  # Pass user ID for storage organization
            model=body.model,
            image_roles=image_roles,
        )

        # Save to database/gallery
        db_image = Image(
            filename=result["filename"],
            prompt=body.prompt or (f"{rendering_name} photo" if body.mode == "product" else f"{rendering_name} portrait"),
            magic_prompt=result.get("magic_prompt"),
            art_style=f"magix_{body.mode}",
            width=result.get("width"),
            height=result.get("height"),
            model=body.model,
            seed=result.get("seed"),
            rendering=rendering_name,
            aspect_ratio=body.aspect_ratio,
            user_id=current_user.id,
        )
        db.add(db_image)
        db.flush()

        results = [MagixImageResult(
            url=result["url"],
            seed=result.get("seed"),
            gallery_id=db_image.id,
            width=result.get("width"),
            height=result.get("height"),
        )]

        record_usage(
            db,
            feature="magix",
            usd=per_edit,
            model=body.model,
            units=1,
            unit="image",
            detail={
                "prompt": body.prompt[:200],
                "mode": body.mode,
                "seed": results[0].seed if results else None,
                "aspect_ratio": body.aspect_ratio,
                "resolution": resolution,
                "num_input_images": num_input_images,
            },
        )
        db.commit()

        # Return response (compatible with both single and batch)
        if len(results) == 1:
            return MagixGenerateResponse(
                image_url=results[0].url,
                images=results,
                seed=results[0].seed,
                prompt=body.prompt,
                gallery_id=results[0].gallery_id,
                width=results[0].width,
                height=results[0].height,
            )
        else:
            return MagixGenerateResponse(
                images=results,
                seed=results[0].seed if results else None,
                prompt=body.prompt,
            )

    except ValueError:
        logger.exception(f"Magix generation failed for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="We could not edit this photo. Check the images and try again.",
        )
    except Exception:
        logger.exception(f"Magix generation failed for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="We could not edit this photo right now. Please try again in a moment.",
        )


@router.get("/history")
async def get_magix_history(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = 20,
):
    """Get user's Magix generation history."""
    images = (
        db.query(Image)
        .filter(
            Image.user_id == current_user.id,
            Image.art_style.like("magix%"),  # Match all magix_* styles
        )
        .order_by(Image.created_at.desc())
        .limit(limit)
        .all()
    )

    return [ImageResponse.from_orm_with_urls(img) for img in images]
