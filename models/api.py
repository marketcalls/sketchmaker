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
    provider_id = db.Column(db.Integer, db.ForeignKey('api_provider.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
