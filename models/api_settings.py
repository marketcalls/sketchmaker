from extensions import db
from datetime import datetime
from cryptography.fernet import Fernet
import os
import base64

class APISettings(db.Model):
    """Centralized API key management - Admin only"""
    __tablename__ = 'api_settings'

    id = db.Column(db.Integer, primary_key=True)

    # AI Provider API Keys (encrypted)
    openai_api_key = db.Column(db.Text)
    anthropic_api_key = db.Column(db.Text)
    gemini_api_key = db.Column(db.Text)
    groq_api_key = db.Column(db.Text)
    xai_api_key = db.Column(db.Text)  # xAI (Grok)
    cerebras_api_key = db.Column(db.Text)  # Cerebras
    openrouter_api_key = db.Column(db.Text)  # OpenRouter
    fal_key = db.Column(db.Text)

    # Default provider and model selection
    default_provider_id = db.Column(db.Integer, db.ForeignKey('api_provider.id'))
    default_model_id = db.Column(db.Integer, db.ForeignKey('ai_model.id'))

    # Encryption key for API keys
    encryption_key = db.Column(db.Text)

    # Settings metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    def __init__(self):
        super().__init__()
        if not self.encryption_key:
            self.encryption_key = base64.urlsafe_b64encode(Fernet.generate_key()).decode()

    def _get_cipher(self):
        """Get encryption cipher"""
        key = base64.urlsafe_b64decode(self.encryption_key.encode())
        return Fernet(key)

    def _encrypt_key(self, api_key):
        """Encrypt API key"""
        if not api_key:
            return None
        cipher = self._get_cipher()
        return cipher.encrypt(api_key.encode()).decode()

    def _decrypt_key(self, encrypted_key):
        """Decrypt API key"""
        if not encrypted_key:
            return None
        try:
            cipher = self._get_cipher()
            return cipher.decrypt(encrypted_key.encode()).decode()
        except:
            return None

    # OpenAI
    def set_openai_key(self, api_key):
        """Set encrypted OpenAI API key"""
        self.openai_api_key = self._encrypt_key(api_key)

    def get_openai_key(self):
        """Get decrypted OpenAI API key"""
        return self._decrypt_key(self.openai_api_key)

    # Anthropic
    def set_anthropic_key(self, api_key):
        """Set encrypted Anthropic API key"""
        self.anthropic_api_key = self._encrypt_key(api_key)

    def get_anthropic_key(self):
        """Get decrypted Anthropic API key"""
        return self._decrypt_key(self.anthropic_api_key)

    # Google Gemini
    def set_gemini_key(self, api_key):
        """Set encrypted Google Gemini API key"""
        self.gemini_api_key = self._encrypt_key(api_key)

    def get_gemini_key(self):
        """Get decrypted Google Gemini API key"""
        return self._decrypt_key(self.gemini_api_key)

    # Groq
    def set_groq_key(self, api_key):
        """Set encrypted Groq API key"""
        self.groq_api_key = self._encrypt_key(api_key)

    def get_groq_key(self):
        """Get decrypted Groq API key"""
        return self._decrypt_key(self.groq_api_key)

    # xAI (Grok)
    def set_xai_key(self, api_key):
        """Set encrypted xAI API key"""
        self.xai_api_key = self._encrypt_key(api_key)

    def get_xai_key(self):
        """Get decrypted xAI API key"""
        return self._decrypt_key(self.xai_api_key)

    # Cerebras
    def set_cerebras_key(self, api_key):
        """Set encrypted Cerebras API key"""
        self.cerebras_api_key = self._encrypt_key(api_key)

    def get_cerebras_key(self):
        """Get decrypted Cerebras API key"""
        return self._decrypt_key(self.cerebras_api_key)

    # OpenRouter
    def set_openrouter_key(self, api_key):
        """Set encrypted OpenRouter API key"""
        self.openrouter_api_key = self._encrypt_key(api_key)

    def get_openrouter_key(self):
        """Get decrypted OpenRouter API key"""
        return self._decrypt_key(self.openrouter_api_key)

    # FAL (Image Generation)
    def set_fal_key(self, api_key):
        """Set encrypted FAL API key"""
        self.fal_key = self._encrypt_key(api_key)

    def get_fal_key(self):
        """Get decrypted FAL API key"""
        return self._decrypt_key(self.fal_key)

    def get_all_keys(self):
        """Get all decrypted API keys"""
        return {
            'openai_api_key': self.get_openai_key(),
            'anthropic_api_key': self.get_anthropic_key(),
            'gemini_api_key': self.get_gemini_key(),
            'groq_api_key': self.get_groq_key(),
            'xai_api_key': self.get_xai_key(),
            'cerebras_api_key': self.get_cerebras_key(),
            'openrouter_api_key': self.get_openrouter_key(),
            'fal_key': self.get_fal_key()
        }

    def get_provider_key(self, provider_name):
        """Get API key for specific provider"""
        keys_map = {
            'OpenAI': self.get_openai_key(),
            'Anthropic': self.get_anthropic_key(),
            'Google Gemini': self.get_gemini_key(),
            'Groq': self.get_groq_key(),
            'xAI': self.get_xai_key(),
            'Cerebras': self.get_cerebras_key(),
            'OpenRouter': self.get_openrouter_key()
        }
        return keys_map.get(provider_name)

    def has_required_keys(self):
        """Check if system has the minimum required API keys"""
        return bool(self.get_fal_key() and (
            self.get_openai_key() or
            self.get_anthropic_key() or
            self.get_gemini_key() or
            self.get_groq_key() or
            self.get_xai_key() or
            self.get_cerebras_key() or
            self.get_openrouter_key()
        ))

    def get_available_providers(self):
        """Get list of providers with configured API keys"""
        from .api import APIProvider

        available = []
        providers = APIProvider.query.filter_by(is_active=True).all()

        for provider in providers:
            if self.get_provider_key(provider.name):
                available.append(provider)

        return available

    @staticmethod
    def get_settings():
        """Get or create API settings singleton"""
        settings = APISettings.query.first()
        if not settings:
            settings = APISettings()
            db.session.add(settings)
            db.session.commit()
        return settings
