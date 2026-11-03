"""What fal and Sarvam work cost, estimated from the built-in price table.

One row per successful provider result (app/services/usage.py). LLM calls are not
here: litellm_client records them in llm_usage, and the Usage page adds the two.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String

from app.database import AUTOINCREMENT, Base


class UsageLog(Base):
    __tablename__ = "usage_log"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    feature = Column(String(50), nullable=False, index=True)  # generate, magix, story, faceless...
    model = Column(String(200), index=True)  # fal endpoint or Sarvam model
    usd = Column(Float, nullable=False, default=0)  # estimated
    units = Column(Float)  # how many of ``unit``: 3 images, 12.5 seconds
    unit = Column(String(30))
    job_type = Column(String(30))
    job_id = Column(String(64), index=True)
    detail = Column(JSON)
