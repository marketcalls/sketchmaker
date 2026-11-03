"""My Assets routes: upload, list, rename and delete reusable files, and
generate voices with ElevenLabs. See app/services/assets.py."""

import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.dependencies import CurrentUser, DbSession
from app.models.asset import UserAsset
from app.schemas.asset import (
    AssetListResponse,
    AssetRenameRequest,
    AssetResponse,
    VoiceCatalogResponse,
    VoiceGenerateRequest,
    VoiceGenerateResponse,
    VoiceSampleResponse,
)
from app.services import assets as asset_service
from app.services import voice_samples

logger = logging.getLogger(__name__)

router = APIRouter()


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")


@router.get("", response_model=AssetListResponse)
async def list_assets(
    current_user: CurrentUser,
    db: DbSession,
    kind: Optional[str] = Query(None, description="One kind or several, comma separated: image,logo,video,audio"),
    q: Optional[str] = Query(None, max_length=100, description="Name contains"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=60),
):
    """The user's assets, newest first."""
    query = db.query(UserAsset).filter(UserAsset.user_id == current_user.id)
    if kind:
        kinds = [k.strip() for k in kind.split(",") if k.strip()]
        if any(k not in asset_service.KINDS for k in kinds):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown asset type")
        query = query.filter(UserAsset.kind.in_(kinds))
    if q and q.strip():
        pattern = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.filter(UserAsset.name.ilike(pattern, escape="\\"))
    total = query.count()
    rows = (
        query.order_by(UserAsset.created_at.desc(), UserAsset.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return AssetListResponse(
        assets=[AssetResponse(**asset_service.to_dict(a)) for a in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total else 0,
    )


@router.get("/voices", response_model=VoiceCatalogResponse)
async def list_voices(current_user: CurrentUser, db: DbSession):
    """Voice providers and their voices: ElevenLabs stock voices, and Sarvam
    Bulbul v4 voices for Indian languages once its key is saved."""
    return VoiceCatalogResponse(**asset_service.voice_catalog(db))


@router.get("/voices/{provider}/{voice}/sample", response_model=VoiceSampleResponse)
async def voice_sample(provider: str, voice: str, current_user: CurrentUser, db: DbSession):
    """A short sample of a voice, so people can listen before they pick one.
    Each sample is made once and kept (see voice_samples)."""
    try:
        url = await voice_samples.sample_url(db, provider, voice)
    except voice_samples.VoiceSampleError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return VoiceSampleResponse(url=url)


@router.post("/upload", response_model=AssetResponse)
async def upload_asset(
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    kind: Optional[str] = Form(None, description="'logo' to file a still as a logo; otherwise the bytes decide"),
    name: Optional[str] = Form(None, max_length=200),
):
    """Upload an image (PNG, JPG, WebP), a logo (also SVG), a video (MP4, MOV,
    WebM, M4V) or audio (MP3, WAV, M4A, AAC, OGG). The type is recognised from
    the file's bytes, and the file is measured before it is stored."""
    content = await file.read(asset_service.UPLOAD_MAX_BYTES + 1)
    if len(content) > asset_service.UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"The file is too large. The limit is {asset_service.UPLOAD_MAX_BYTES // (1024 * 1024)} MB.",
        )
    try:
        asset_service.check_room(db, current_user.id)
        info = await run_in_threadpool(asset_service.inspect_upload, content, (kind or None))
    except asset_service.AssetError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    fallback = f"{info['kind'].capitalize()} {len(content) // 1024} KB"
    asset = await asset_service.store(
        db, current_user.id, info, asset_service.clean_name(name or file.filename, fallback)
    )
    logger.info(f"Asset {asset.id} uploaded by user {current_user.id}: {asset.kind}, {asset.file_size_bytes} bytes")
    return AssetResponse(**asset_service.to_dict(asset))


@router.post("/voice", response_model=VoiceGenerateResponse)
async def generate_voice(
    body: VoiceGenerateRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Generate a voice track with ElevenLabs (Eleven v4) or Sarvam (Bulbul v4,
    Indian languages) and save it to My Assets. Priced per character at the
    provider's voice price."""
    try:
        asset, estimated_usd = await asset_service.generate_voice(
            db, current_user.id,
            text=body.text, voice=body.voice, stability=body.stability, name=body.name,
            provider=body.provider, pace=body.pace,
        )
    except asset_service.AssetError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except asset_service.VoiceGenerationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"{e}.")
    except ValueError:
        logger.exception(f"Voice generation failed for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The voice could not be generated. Please try again.",
        )
    logger.info(f"Voice asset {asset.id} generated for user {current_user.id}: ~${estimated_usd:g}")
    return VoiceGenerateResponse(asset=AssetResponse(**asset_service.to_dict(asset)), estimated_usd=estimated_usd)


@router.get("/{asset_id}/file")
async def asset_file(asset_id: int, current_user: CurrentUser, db: DbSession):
    """The asset's bytes, same-origin, for the owner only. The "From My Assets"
    buttons fetch this and hand the file to a page's ordinary upload, so every
    tool keeps its own checks. Streamed: videos can be 100 MB."""
    import os

    from fastapi.responses import FileResponse

    from app.services.storage_service import storage_service

    try:
        asset = asset_service.owned(db, current_user.id, asset_id)
    except asset_service.AssetNotFound:
        raise _not_found()
    media_type = asset.content_type or "application/octet-stream"
    # attachment: opened directly, an SVG or anything else is downloaded, never rendered on our origin.
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="{asset.filename}"',
    }

    local = storage_service.get_local_path(asset.filename, asset.storage_type, user_id=asset.user_id)
    if not os.path.isfile(local):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The file is missing. Upload it again.")
    return FileResponse(local, media_type=media_type, headers=headers)


@router.patch("/{asset_id}", response_model=AssetResponse)
async def rename_asset(asset_id: int, body: AssetRenameRequest, current_user: CurrentUser, db: DbSession):
    try:
        asset = asset_service.owned(db, current_user.id, asset_id)
    except asset_service.AssetNotFound:
        raise _not_found()
    name = asset_service.clean_name(body.name, "")
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Give the asset a name.")
    asset.name = name
    db.commit()
    db.refresh(asset)
    return AssetResponse(**asset_service.to_dict(asset))


@router.delete("/{asset_id}")
async def delete_asset(asset_id: int, current_user: CurrentUser, db: DbSession):
    """Delete an asset and its file. Videos already made from it are kept."""
    try:
        asset = asset_service.owned(db, current_user.id, asset_id, lock=True)
    except asset_service.AssetNotFound:
        raise _not_found()
    if asset_service.in_use(db, asset):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A video that is still being made uses this asset. Delete it once the video is ready.",
        )
    await asset_service.delete(db, asset)
    return {"message": "Asset deleted"}
