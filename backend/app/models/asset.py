"""My Assets: files uploaded once and reused across tools.

Images, logos, videos and audio, plus generated voices. The files live in
images/{user_id}/ and videos/{user_id}/, named asset_*. See app/services/assets.py.
"""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Column, DateTime, Float, ForeignKey, Index, Integer, String

from app.database import AUTOINCREMENT, Base


class UserAsset(Base):
    __tablename__ = "user_assets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(16), nullable=False)  # image | logo | video | audio
    name = Column(String(200), nullable=False)
    filename = Column(String(255), nullable=False)
    storage_type = Column(String(16), nullable=False)  # StorageService type: images | videos
    content_type = Column(String(100))
    file_size_bytes = Column(BigInteger, nullable=False, default=0)
    width = Column(Integer)
    height = Column(Integer)
    duration_seconds = Column(Float)
    source = Column(String(16), nullable=False, default="upload")  # upload | voice
    # Voice assets: {"voice", "text", "characters", "estimated_usd", "model"}.
    extra = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_user_assets_user_kind_created", "user_id", "kind", "created_at"),
        AUTOINCREMENT,
    )
