"""API keys, the default and fallback model, and the LiteLLM model list.

Keys are write-only. Nothing here returns one: GET reports whether a key is stored,
whether it can be read, and a mask of its last four characters. There is deliberately
no way to set a provider's base_url, which would send a stored key to another server.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.dependencies import CurrentUser, DbSession
from app.middleware.rate_limiter import limiter
from app.models.api import LLM_KEY_BY_PROVIDER, AIModel, APIProvider, APISettings
from app.models.user import User
from app.schemas.common import MessageResponse
from app.services import model_catalog
from app.utils.secret_box import canary_status, looks_masked, make_canary, mask_key

router = APIRouter()

# Name in the API -> column.
KEY_COLUMN_BY_PROVIDER = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "gemini": "gemini_api_key",
    "groq": "groq_api_key",
    "xai": "xai_api_key",
    "cerebras": "cerebras_api_key",
    "baseten": "baseten_api_key",
    "openrouter": "openrouter_api_key",
    "fal": "fal_key",
    "sarvam": "sarvam_api_key",
}


class APIKeyUpdate(BaseModel):
    """Anything left out stays as it is. A mask sent back is ignored. An explicit null
    on a model field clears that choice."""

    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    xai_api_key: Optional[str] = None
    cerebras_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    baseten_api_key: Optional[str] = None
    fal_key: Optional[str] = None
    sarvam_api_key: Optional[str] = None
    default_model_id: Optional[int] = None
    fallback_model_id: Optional[int] = None


class ProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_active: bool


class ModelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    display_name: Optional[str]
    description: Optional[str]
    provider_id: int
    provider_name: Optional[str] = None
    context_window: Optional[int]
    is_latest: bool
    is_active: bool
    capabilities: Optional[Dict[str, Any]]


class ModelCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    provider_id: int
    context_window: Optional[int] = None
    is_latest: bool = False
    is_active: bool = True
    capabilities: Optional[Dict[str, Any]] = None


class OfferedModelAdd(BaseModel):
    """A model from Refresh models that the owner chose to add."""

    provider_id: int
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    context_window: Optional[int] = None


class OfferedModelsAdd(BaseModel):
    models: list[OfferedModelAdd] = Field(max_length=200)


class ModelUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    context_window: Optional[int] = None
    is_latest: Optional[bool] = None
    is_active: Optional[bool] = None
    capabilities: Optional[Dict[str, Any]] = None


def _settings_row(db: Session) -> APISettings:
    row = db.query(APISettings).first()
    if row is None:
        row = APISettings(secrets_canary=make_canary())
        db.add(row)
    return row


def _key_status(row: APISettings | None, column: str) -> dict:
    stored = bool(row and row.has_key(column))
    plaintext = row.get_key(column) if stored else None
    return {
        "is_configured": stored,
        "unreadable": stored and plaintext is None,
        "masked_key": mask_key(plaintext),
    }


def _model_response(model: AIModel) -> ModelResponse:
    response = ModelResponse.model_validate(model)
    response.provider_name = model.provider.name if model.provider else None
    return response


def _adopt_usable_default(db: Session, row: APISettings) -> None:
    """Move the default model to a provider with a key when its own provider has none.

    The seeded default is one provider's model. Without this, an owner who only has a key
    for another provider would see every language model feature fail after adding it.
    """
    provider = db.query(APIProvider).filter(APIProvider.id == row.default_provider_id).first()
    if provider is not None and row.get_provider_key(provider.name):
        return
    for name in LLM_KEY_BY_PROVIDER:
        if not row.get_provider_key(name):
            continue
        model = (
            db.query(AIModel)
            .join(APIProvider)
            .filter(APIProvider.name == name, AIModel.is_active.is_(True))
            .order_by(AIModel.sort_order, AIModel.id)
            .first()
        )
        if model is not None:
            row.default_model_id = model.id
            row.default_provider_id = model.provider_id
            return


@router.get("/api-keys")
def get_api_keys_status(_user: CurrentUser, db: DbSession):
    row = db.query(APISettings).first()
    return {
        "keys": {name: _key_status(row, column) for name, column in KEY_COLUMN_BY_PROVIDER.items()},
        # The database was encrypted with a different SECRET_KEY or ENCRYPTION_SALT.
        "secrets_unreadable": bool(row) and canary_status(row.secrets_canary) == "unreadable",
        "default_provider_id": row.default_provider_id if row else None,
        "default_model_id": row.default_model_id if row else None,
        "fallback_provider_id": row.fallback_provider_id if row else None,
        "fallback_model_id": row.fallback_model_id if row else None,
    }


@router.put("/api-keys", response_model=MessageResponse)
def update_api_keys(updates: APIKeyUpdate, _user: CurrentUser, db: DbSession):
    row = _settings_row(db)

    for column in KEY_COLUMN_BY_PROVIDER.values():
        value = getattr(updates, column)
        if value and value.strip() and not looks_masked(value):
            row.set_key(column, value.strip())
            # New values use the current secrets, so stop reporting the database as unreadable.
            # Older keys that still cannot be read are reported one by one.
            row.secrets_canary = make_canary()

    # A model belongs to one provider, so the provider follows the model.
    for field, provider_field in (("default_model_id", "default_provider_id"),
                                  ("fallback_model_id", "fallback_provider_id")):
        if field not in updates.model_fields_set:
            continue
        model_id = getattr(updates, field)
        if model_id is None:
            setattr(row, field, None)
            setattr(row, provider_field, None)
            continue
        model = db.query(AIModel).filter(AIModel.id == model_id).first()
        if model is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Model not found")
        setattr(row, field, model.id)
        setattr(row, provider_field, model.provider_id)

    if "default_model_id" not in updates.model_fields_set:
        _adopt_usable_default(db, row)

    db.commit()
    return MessageResponse(message="API keys updated successfully")


@router.delete("/api-keys/{provider}", response_model=MessageResponse)
def clear_api_key(provider: str, _user: CurrentUser, db: DbSession):
    column = KEY_COLUMN_BY_PROVIDER.get(provider)
    if column is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid provider")
    row = db.query(APISettings).first()
    if row is not None:
        row.set_key(column, None)
        db.commit()
    return MessageResponse(message=f"{provider} API key cleared")


@router.get("/providers")
def list_providers(_user: CurrentUser, db: DbSession):
    return [ProviderResponse.model_validate(p) for p in db.query(APIProvider).all()]


@router.get("/models")
def list_models(_user: CurrentUser, db: DbSession):
    models = db.query(AIModel).order_by(AIModel.provider_id, AIModel.sort_order, AIModel.id).all()
    return [_model_response(m) for m in models]


@router.post("/models/refresh")
@limiter.limit("6/minute")
def refresh_models(request: Request, _user: CurrentUser, db: DbSession):
    """Ask each provider with a key what it offers now. Adds nothing: the owner chooses."""
    row = db.query(APISettings).first()
    keys = {}
    for name in LLM_KEY_BY_PROVIDER:
        key = row.get_provider_key(name) if row else None
        if key:
            keys[name] = key
    provider_ids = {p.name: p.id for p in db.query(APIProvider).filter(APIProvider.name.in_(keys)).all()} if keys else {}
    models = [(m.provider_id, m.name, bool(m.is_active)) for m in db.query(AIModel).all()]
    # Nothing stays open across the network calls.
    db.commit()

    offers = model_catalog.fetch_offers({name: key for name, key in keys.items() if name in provider_ids})

    providers = []
    for name, offer in offers.items():
        provider_id = provider_ids[name]
        known = {model for pid, model, _active in models if pid == provider_id}
        gone = sorted(model for pid, model, active in models
                      if pid == provider_id and active and offer.status == model_catalog.STATUS_OK
                      and model not in offer.listed)
        providers.append({
            "provider_id": provider_id,
            "provider": name,
            "status": offer.status,
            "new_models": [m.as_dict() for m in model_catalog.new_models_for(offer, known)],
            "no_longer_listed": gone,
        })
    return {"providers": providers}


@router.post("/models/add-offered")
def add_offered_models(payload: OfferedModelsAdd, _user: CurrentUser, db: DbSession):
    """Add what the owner ticked in Refresh models. A model already there is left as it is."""
    allowed = {p.id for p in db.query(APIProvider).filter(APIProvider.name.in_(LLM_KEY_BY_PROVIDER)).all()}
    added = 0
    # Backwards, each going above the last, so the top of the list stays in the order shown.
    for item in reversed(payload.models):
        name = item.name.strip()
        if item.provider_id not in allowed:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider not found")
        if not model_catalog.valid_model_name(name):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That is not a valid model name")
        exists = db.query(AIModel.id).filter(AIModel.provider_id == item.provider_id, AIModel.name == name).first()
        if exists:
            continue
        lowest = db.query(func.min(AIModel.sort_order)).filter(AIModel.provider_id == item.provider_id).scalar() or 0
        db.add(AIModel(
            name=name,
            display_name=(item.display_name or "").strip()[:model_catalog.MAX_DISPLAY_NAME] or None,
            description=(item.description or "").strip()[:model_catalog.MAX_DESCRIPTION] or None,
            provider_id=item.provider_id,
            context_window=item.context_window if item.context_window and item.context_window > 0 else None,
            is_latest=True,
            is_active=True,
            sort_order=lowest - 1,
        ))
        db.flush()
        added += 1
    db.commit()
    return {"added": added}


@router.post("/models")
def create_model(model_data: ModelCreate, _user: CurrentUser, db: DbSession):
    if db.query(APIProvider.id).filter(APIProvider.id == model_data.provider_id).first() is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider not found")
    model = AIModel(**model_data.model_dump())
    db.add(model)
    db.commit()
    db.refresh(model)
    return _model_response(model)


@router.patch("/models/{model_id}")
def update_model(model_id: int, updates: ModelUpdate, _user: CurrentUser, db: DbSession):
    model = db.query(AIModel).filter(AIModel.id == model_id).first()
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    for field, value in updates.model_dump(exclude_none=True).items():
        setattr(model, field, value)
    db.commit()
    db.refresh(model)
    return _model_response(model)


@router.delete("/models/{model_id}", response_model=MessageResponse)
def delete_model(model_id: int, _user: CurrentUser, db: DbSession):
    model = db.query(AIModel).filter(AIModel.id == model_id).first()
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    # Clear whatever still points at it, so foreign keys do not refuse the delete.
    row = db.query(APISettings).first()
    if row is not None:
        if row.default_model_id == model_id:
            row.default_model_id = row.default_provider_id = None
        if row.fallback_model_id == model_id:
            row.fallback_model_id = row.fallback_provider_id = None
    db.query(User).filter(User.selected_model_id == model_id).update(
        {User.selected_model_id: None}, synchronize_session=False,
    )
    db.delete(model)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stored images refer to this model. Turn it off instead of deleting it.",
        )
    return MessageResponse(message="Model deleted successfully")
