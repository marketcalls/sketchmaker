"""The owner's profile, password, and the LLM models they can pick from."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.dependencies import CurrentUser, DbSession, get_password_hash, set_session_cookie, verify_password
from app.middleware.rate_limiter import AUTH_LIMIT, limiter
from app.models.api import LLM_KEY_BY_PROVIDER, AIModel, APIProvider, APISettings
from app.schemas.auth import ChangePasswordRequest
from app.schemas.common import MessageResponse
from app.schemas.user import UserProfileResponse, UserUpdate

router = APIRouter()


@router.get("/profile", response_model=UserProfileResponse)
def get_profile(current_user: CurrentUser):
    return UserProfileResponse.model_validate(current_user)


@router.patch("/profile", response_model=UserProfileResponse)
def update_profile(updates: UserUpdate, current_user: CurrentUser, db: DbSession):
    if updates.username:
        current_user.username = updates.username

    if updates.selected_provider_id is not None:
        provider = db.query(APIProvider).filter(
            APIProvider.id == updates.selected_provider_id,
            APIProvider.is_active.is_(True),
        ).first()
        if not provider:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid provider")
        current_user.selected_provider_id = updates.selected_provider_id

    if updates.selected_model_id is not None:
        model = db.query(AIModel).filter(
            AIModel.id == updates.selected_model_id,
            AIModel.is_active.is_(True),
        ).first()
        if not model:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid model")
        current_user.selected_model_id = updates.selected_model_id

    db.commit()
    db.refresh(current_user)
    return UserProfileResponse.model_validate(current_user)


@router.post("/change-password", response_model=MessageResponse)
@limiter.limit(AUTH_LIMIT)
def change_password(
    request: Request,
    response: Response,
    payload: ChangePasswordRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Change the password. Every other session ends; this one is re-issued."""
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    current_user.password_hash = get_password_hash(payload.new_password)
    db.commit()
    db.refresh(current_user)

    set_session_cookie(response, request, current_user)
    return MessageResponse(message="Password changed successfully")


@router.get("/providers")
def get_available_providers(_user: CurrentUser, db: DbSession):
    """Active LLM providers with a key stored. Checks the columns, never decrypts."""
    api_settings = db.query(APISettings).first()
    if not api_settings:
        return []

    configured = [name for name, column in LLM_KEY_BY_PROVIDER.items() if api_settings.has_key(column)]
    if not configured:
        return []

    providers = db.query(APIProvider).filter(
        APIProvider.is_active.is_(True),
        APIProvider.name.in_(configured),
    ).all()
    return [{"id": p.id, "name": p.name, "is_active": p.is_active} for p in providers]


@router.get("/models")
def get_models(_user: CurrentUser, db: DbSession, provider_id: int | None = None):
    query = db.query(AIModel).filter(AIModel.is_active.is_(True))
    if provider_id:
        query = query.filter(AIModel.provider_id == provider_id)
    return [
        {
            "id": m.id,
            "name": m.name,
            "display_name": m.display_name,
            "provider_id": m.provider_id,
            "is_latest": m.is_latest,
        }
        for m in query.order_by(AIModel.provider_id, AIModel.sort_order, AIModel.id).all()
    ]
