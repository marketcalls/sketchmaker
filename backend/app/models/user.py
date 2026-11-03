"""The owner's account. One row, id 1: the CHECK and the primary key enforce it."""

from datetime import datetime
import hashlib
import hmac

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.config import settings
from app.database import AUTOINCREMENT, Base

OWNER_ID = 1


class User(Base):
    __tablename__ = "user"
    __table_args__ = (CheckConstraint("id = 1", name="single_owner"), AUTOINCREMENT)

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Login lockout, updated with one atomic UPDATE (routers/auth.py).
    failed_login_count = Column(Integer, nullable=False, default=0, server_default="0")
    failed_login_window_start = Column(DateTime, nullable=True)
    locked_until = Column(DateTime, nullable=True)

    # Bumped on logout. Part of password_fingerprint(), so every session issued
    # before the bump stops validating.
    token_version = Column(Integer, nullable=False, default=0, server_default="0")

    # Provider and model picked for prompt enhancement; falls back to APISettings.
    selected_provider_id = Column(Integer, ForeignKey("api_provider.id"))
    selected_model_id = Column(Integer, ForeignKey("ai_model.id"))

    images = relationship("Image", back_populates="user", lazy="dynamic")
    videos = relationship("Video", back_populates="user", lazy="dynamic")
    notifications = relationship("Notification", back_populates="user", lazy="dynamic")

    def password_fingerprint(self) -> str:
        """Keyed hash of the password hash and token_version, carried in the session.

        A password change or a logout changes it, so every session issued earlier
        fails its next request, a stolen cookie included.
        """
        material = f"{self.password_hash or ''}:v{int(self.token_version or 0)}"
        return hmac.new(settings.JWT_SECRET_KEY.encode(), material.encode(), hashlib.sha256).hexdigest()[:32]

    def is_locked_out(self, now: datetime | None = None) -> bool:
        """Whether failed logins have locked the account right now."""
        return bool(self.locked_until and self.locked_until > (now or datetime.utcnow()))
