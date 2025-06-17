from extensions import db
from datetime import datetime

class APIProvider(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # e.g. "OpenAI", "Anthropic", "Google Gemini", "Groq"
    is_active = db.Column(db.Boolean, default=True)
    models = db.relationship('AIModel', backref='provider', lazy=True)

class AIModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # e.g. "gpt-4", "claude-3-sonnet", "llama-3.1-8b-instant"
    display_name = db.Column(db.String(200))  # User-friendly name
    provider_id = db.Column(db.Integer, db.ForeignKey('api_provider.id'), nullable=False)
    description = db.Column(db.Text)  # Model description
    context_window = db.Column(db.Integer)  # Token limit
    is_latest = db.Column(db.Boolean, default=False)  # Mark latest models
    release_date = db.Column(db.Date)  # When the model was released
    deprecation_date = db.Column(db.Date)  # When the model will be deprecated
    capabilities = db.Column(db.JSON)  # JSON array of capabilities
    sort_order = db.Column(db.Integer, default=0)  # For custom ordering
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
