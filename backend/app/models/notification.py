"""In-app notifications: the bell shows job results only."""

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import AUTOINCREMENT, Base


class NotificationType(str, Enum):
    IMAGE_COMPLETED = "image_completed"
    IMAGE_FAILED = "image_failed"
    VIDEO_COMPLETED = "video_completed"
    VIDEO_FAILED = "video_failed"


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)

    type = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    action_url = Column(String(500), nullable=True)

    is_read = Column(Boolean, default=False, index=True)
    read_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User", back_populates="notifications")

    def mark_as_read(self):
        self.is_read = True
        self.read_at = datetime.utcnow()
