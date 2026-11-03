"""In-app notifications for finished jobs."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationType

logger = logging.getLogger(__name__)


def create_notification(
    db: Session,
    user_id: int,
    notification_type: str,
    title: str,
    message: str,
    action_url: str | None = None,
) -> Notification:
    """Create a notification and commit."""
    notification = Notification(
        user_id=user_id,
        type=notification_type,
        title=title,
        message=message,
        action_url=action_url,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    logger.info(f"Created notification: {title}")
    return notification


def send_job_completion_notification(
    db: Session,
    user_id: int,
    job_type: str,  # "image" or "video"
    status: str,  # "completed" or "failed"
    result_id: int | None = None,
    error_message: str | None = None,
) -> Notification:
    """Tell the owner a generation job completed or failed."""
    if job_type == "image":
        if status == "completed":
            return create_notification(
                db=db,
                user_id=user_id,
                notification_type=NotificationType.IMAGE_COMPLETED.value,
                title="Image Generation Complete",
                message="Your image has been generated successfully.",
                action_url="/gallery",
            )
        return create_notification(
            db=db,
            user_id=user_id,
            notification_type=NotificationType.IMAGE_FAILED.value,
            title="Image Generation Failed",
            message=error_message[:200] if error_message else "Your image generation failed. Please try again.",
            action_url="/my-jobs",
        )

    if status == "completed":
        return create_notification(
            db=db,
            user_id=user_id,
            notification_type=NotificationType.VIDEO_COMPLETED.value,
            title="Video Generation Complete",
            message="Your video has been generated successfully.",
            action_url="/gallery?tab=videos",
        )
    return create_notification(
        db=db,
        user_id=user_id,
        notification_type=NotificationType.VIDEO_FAILED.value,
        title="Video Generation Failed",
        message=error_message[:200] if error_message else "Your video generation failed. Please try again.",
        action_url="/my-jobs",
    )
