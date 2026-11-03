"""Per-call LLM token accounting.

Input and output are stored separately because they are priced separately, often
by an order of magnitude. estimated_usd comes from litellm's price table and is
NULL when the model is not in it, so the Usage page always shows tokens and shows
dollars only where they are known.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String

from app.database import AUTOINCREMENT, Base


class LLMUsage(Base):
    __tablename__ = "llm_usage"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    user_id = Column(Integer, ForeignKey("user.id"), nullable=True, index=True)
    # What the call was for: image_prompt, magix, explainer, story...
    feature = Column(String(50), index=True)

    provider = Column(String(50), index=True)
    model = Column(String(120), index=True)

    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    estimated_usd = Column(Float, nullable=True)
