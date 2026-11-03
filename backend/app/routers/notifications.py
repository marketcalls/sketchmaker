"""Notification routes: the bell shows job results."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from app.dependencies import CurrentUser, DbSession
from app.models.notification import Notification

router = APIRouter()


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str
    message: str
    action_url: str | None
    is_read: bool
    created_at: datetime


class NotificationSummary(BaseModel):
    """Summary of notifications for the navbar."""

    unread_count: int
    recent: list[NotificationResponse]


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    total: int
    page: int
    page_size: int


@router.get("", response_model=NotificationSummary)
def get_notification_summary(current_user: CurrentUser, db: DbSession):
    """Unread count and the five most recent, for the navbar."""
    unread_count = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read.is_(False),
    ).count()

    recent = db.query(Notification).filter(
        Notification.user_id == current_user.id,
    ).order_by(Notification.created_at.desc()).limit(5).all()

    return NotificationSummary(
        unread_count=unread_count,
        recent=[NotificationResponse.model_validate(n) for n in recent],
    )


@router.get("/all", response_model=NotificationListResponse)
def get_all_notifications(
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    offset = (page - 1) * page_size

    total = db.query(Notification).filter(Notification.user_id == current_user.id).count()

    notifications = db.query(Notification).filter(
        Notification.user_id == current_user.id,
    ).order_by(Notification.created_at.desc()).offset(offset).limit(page_size).all()

    return NotificationListResponse(
        notifications=[NotificationResponse.model_validate(n) for n in notifications],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{notification_id}/read")
def mark_as_read(notification_id: int, current_user: CurrentUser, db: DbSession):
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    ).first()

    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    notification.mark_as_read()
    db.commit()
    return {"success": True}


@router.post("/read-all")
def mark_all_as_read(current_user: CurrentUser, db: DbSession):
    now = datetime.utcnow()
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read.is_(False),
    ).update({Notification.is_read: True, Notification.read_at: now})
    db.commit()
    return {"success": True}
