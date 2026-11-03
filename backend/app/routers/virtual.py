"""Virtual try-on generation routes using a choice of image edit models."""

import logging

from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession
from app.models.content import Image
from app.models.api import APISettings, APIProvider, AIModel
from app.schemas.image import VirtualRequest, VirtualResponse
from app.clients.fal_client import edit_max_images, generate_virtual_tryon, validate_edit_model
from app.clients.litellm_client import enhance_tryon_prompt
from app.services.pricing import edit_usd
from app.services.usage import record_usage

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/generate", response_model=VirtualResponse)
async def generate_virtual(
    body: VirtualRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Generate a virtual try-on image with the chosen edit model.

    Takes a person image and a dress/garment image, then generates
    a realistic virtual try-on result.
    """
    if not validate_edit_model(body.model):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model '{body.model}' is not available for Virtual Try-On",
        )
    # Models that return one image per request are asked for one
    num_images = edit_max_images(body.model, body.num_images)

    # Priced per output image by edit model (app/services/pricing.py). Try-On
    # renders at the edit models' default 1K.
    per_image = edit_usd(body.model)

    try:
        # Parse user intent with LLM if prompt is provided (hybrid approach)
        user_intent_json = None
        if body.prompt and body.prompt.strip():
            try:
                # Get API settings to find configured LLM
                api_settings = db.query(APISettings).first()
                if api_settings and api_settings.default_provider_id and api_settings.default_model_id:
                    provider = db.query(APIProvider).filter(APIProvider.id == api_settings.default_provider_id).first()
                    model = db.query(AIModel).filter(AIModel.id == api_settings.default_model_id).first()

                    if provider and model:
                        logger.debug(f"[VirtualTryOn] Parsing user intent with {provider.name}/{model.name}")
                        logger.debug(f"[VirtualTryOn] User prompt: {body.prompt}")
                        user_intent_json = await enhance_tryon_prompt(
                            user_prompt=body.prompt,
                            mode=body.mode,
                            model_name=model.name,
                            provider_name=provider.name,
                            db=db,
                        )
                        logger.debug(f"[VirtualTryOn] User intent parsed successfully")
                        logger.debug(f"[VirtualTryOn] Intent keys: {list(user_intent_json.keys())}")
                        if user_intent_json.get("scene_override", {}).get("location"):
                            logger.debug(f"[VirtualTryOn] Location override: {user_intent_json['scene_override']['location']}")
                    else:
                        logger.debug(f"[VirtualTryOn] Intent parsing skipped - provider or model not found")
            except Exception as e:
                # If LLM parsing fails, continue without it (fallback to template only)
                logger.warning(f"[VirtualTryOn] Intent parsing failed, using template only: {e}")
                user_intent_json = None

        # Generate virtual try-on with hybrid JSON prompt
        result = await generate_virtual_tryon(
            person_image=body.person_image,
            dress_image=body.dress_image,
            db=db,
            prompt=body.prompt,
            mode=body.mode,
            aspect_ratio=body.aspect_ratio,
            use_dress_background=body.use_dress_background,
            num_images=num_images,
            temperature=body.temperature,
            seed=body.seed,
            user_intent_json=user_intent_json,
            user_id=current_user.id,
            model=body.model,
        )

        if not result.get("images"):
            raise ValueError("No images generated")

        # Save images to database (never more than were asked for)
        saved_images = []
        for img in result["images"][:num_images]:
            image = Image(
                filename=img["filename"],
                prompt=result.get("prompt", "Virtual try-on"),
                art_style="virtual_tryon",
                width=img.get("width", 1024),
                height=img.get("height", 1024),
                model=body.model,
                user_id=current_user.id,
            )
            db.add(image)
            db.flush()

            saved_images.append({
                "id": image.id,
                "url": img["url"],
                "width": img.get("width"),
                "height": img.get("height"),
            })

        # Recorded per image stored, so an image the model did not deliver costs
        # nothing. A try-on with no images raised above.
        usd = round(per_image * len(saved_images), 4)
        record_usage(
            db,
            feature="virtual",
            usd=usd,
            model=body.model,
            units=len(saved_images),
            unit="image",
            detail={
                "prompt": result.get("prompt", "")[:200],
                "images_requested": num_images,
                "seed": result.get("seed"),
            },
        )
        db.commit()

        return VirtualResponse(
            images=saved_images,
            metadata={
                "seed": result.get("seed"),
                "prompt": result.get("prompt"),
                "mode": "virtual_tryon",
            },
            estimated_usd=usd,
        )

    except ValueError:
        logger.exception(f"Virtual try-on failed for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="We could not create this try-on. Check the person and outfit photos and try again.",
        )
    except Exception:
        logger.exception(f"Virtual try-on failed for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="We could not create this try-on right now. Please try again in a moment.",
        )


@router.get("/history")
async def get_virtual_history(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = 20,
):
    """Get user's virtual try-on generation history."""
    images = (
        db.query(Image)
        .filter(
            Image.user_id == current_user.id,
            Image.art_style == "virtual_tryon",
        )
        .order_by(Image.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": img.id,
            "url": img.get_url(),
            "prompt": img.prompt,
            "width": img.width,
            "height": img.height,
            "created_at": img.created_at.isoformat(),
        }
        for img in images
    ]
