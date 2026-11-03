"""LLM providers and models, and the stored API keys (encrypted, one row)."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database import AUTOINCREMENT, Base
from app.utils import secret_box

# Columns holding encrypted keys. The column name is also the encryption domain
# (secret_box), so a value copied into another column does not decrypt.
KEY_COLUMNS = (
    "openai_api_key",
    "anthropic_api_key",
    "gemini_api_key",
    "groq_api_key",
    "xai_api_key",
    "cerebras_api_key",
    "openrouter_api_key",
    "baseten_api_key",
    "fal_key",
    "sarvam_api_key",
)

LLM_KEY_BY_PROVIDER = {
    "OpenAI": "openai_api_key",
    "Anthropic": "anthropic_api_key",
    "Google Gemini": "gemini_api_key",
    "Groq": "groq_api_key",
    "xAI": "xai_api_key",
    "Cerebras": "cerebras_api_key",
    "OpenRouter": "openrouter_api_key",
    "Baseten": "baseten_api_key",
}


class APIProvider(Base):
    """An LLM provider."""

    __tablename__ = "api_provider"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    # OpenAI-compatible endpoints (Baseten) speak the same protocol at a different
    # address. Seeded only and never editable through the API: a client that could
    # change it could send the stored key to its own server.
    base_url = Column(String(255))

    models = relationship("AIModel", back_populates="provider", lazy="dynamic")


class AIModel(Base):
    """An LLM model."""

    __tablename__ = "ai_model"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    display_name = Column(String(150))
    description = Column(Text)
    provider_id = Column(Integer, ForeignKey("api_provider.id"), nullable=False)
    context_window = Column(Integer)
    is_latest = Column(Boolean, default=False)
    release_date = Column(DateTime)
    deprecation_date = Column(DateTime)
    capabilities = Column(JSON)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    provider = relationship("APIProvider", back_populates="models")


class APISettings(Base):
    """API keys, encrypted with app/utils/secret_box.py, and the default models."""

    __tablename__ = "api_settings"
    __table_args__ = AUTOINCREMENT

    id = Column(Integer, primary_key=True, index=True)

    openai_api_key = Column(Text)
    anthropic_api_key = Column(Text)
    gemini_api_key = Column(Text)
    groq_api_key = Column(Text)
    xai_api_key = Column(Text)
    cerebras_api_key = Column(Text)
    openrouter_api_key = Column(Text)
    baseten_api_key = Column(Text)
    fal_key = Column(Text)
    sarvam_api_key = Column(Text)

    # A known value encrypted with the same key, so a wrong SECRET_KEY can be told
    # apart from keys that were never configured.
    secrets_canary = Column(Text)

    default_provider_id = Column(Integer, ForeignKey("api_provider.id"))
    default_model_id = Column(Integer, ForeignKey("ai_model.id"))

    # Backup model used when the primary fails (outage, rate limit, bad output).
    fallback_provider_id = Column(Integer, ForeignKey("api_provider.id"))
    fallback_model_id = Column(Integer, ForeignKey("ai_model.id"))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_key(self, column: str) -> str | None:
        """Plaintext of one key column, or None when empty or unreadable."""
        if column not in KEY_COLUMNS:
            raise ValueError(f"Not an API key column: {column}")
        return secret_box.decrypt(getattr(self, column), column)

    def set_key(self, column: str, api_key: str | None) -> None:
        """Encrypt and store one key column. A falsy value clears it."""
        if column not in KEY_COLUMNS:
            raise ValueError(f"Not an API key column: {column}")
        setattr(self, column, secret_box.encrypt(api_key, column) if api_key else None)

    def has_key(self, column: str) -> bool:
        """Whether a key is stored, without decrypting it."""
        return bool(getattr(self, column))

    def get_fal_key(self) -> str | None:
        return self.get_key("fal_key")

    def get_sarvam_key(self) -> str | None:
        return self.get_key("sarvam_api_key")

    def get_all_keys(self) -> dict:
        return {column: self.get_key(column) for column in KEY_COLUMNS}

    def get_provider_key(self, provider_name: str) -> str | None:
        """The LLM key for a provider name."""
        column = LLM_KEY_BY_PROVIDER.get(provider_name)
        return self.get_key(column) if column else None

    def has_llm_key(self) -> bool:
        """At least one language model provider has a readable key."""
        return any(self.get_key(c) for c in LLM_KEY_BY_PROVIDER.values())

    def has_required_keys(self) -> bool:
        """fal for media plus at least one LLM provider."""
        return bool(self.get_fal_key() and self.has_llm_key())
