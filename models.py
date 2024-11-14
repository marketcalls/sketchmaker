from extensions import db
from flask_login import UserMixin
from datetime import datetime
import os
from PIL import Image as PILImage

class APIProvider(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # e.g. "OpenAI", "Anthropic", "Google Gemini", "Groq"
    is_active = db.Column(db.Boolean, default=True)
    models = db.relationship('AIModel', backref='provider', lazy=True)

class AIModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # e.g. "gpt-4o", "claude-3-sonnet", "llama-3.1-8b-instant"
    provider_id = db.Column(db.Integer, db.ForeignKey('api_provider.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    role = db.Column(db.String(20), default='user')  # 'admin' or 'user'
    is_active = db.Column(db.Boolean, default=True)
    images = db.relationship('Image', backref='user', lazy=True)
    training_history = db.relationship('TrainingHistory', backref='user', lazy=True)
    
    # API Provider settings
    selected_provider_id = db.Column(db.Integer, db.ForeignKey('api_provider.id'))
    selected_model_id = db.Column(db.Integer, db.ForeignKey('ai_model.id'))
    
    # API Keys for different providers
    openai_api_key = db.Column(db.String(255))
    anthropic_api_key = db.Column(db.String(255))
    gemini_api_key = db.Column(db.String(255))
    groq_api_key = db.Column(db.String(255))
    fal_key = db.Column(db.String(255))

    def get_api_keys(self):
        """Get user's API keys"""
        return {
            'openai_api_key': self.openai_api_key,
            'anthropic_api_key': self.anthropic_api_key,
            'gemini_api_key': self.gemini_api_key,
            'groq_api_key': self.groq_api_key,
            'fal_key': self.fal_key
        }

    def get_selected_provider_key(self):
        """Get the API key for the currently selected provider"""
        provider = APIProvider.query.get(self.selected_provider_id)
        if provider:
            if provider.name == 'OpenAI':
                return self.openai_api_key
            elif provider.name == 'Anthropic':
                return self.anthropic_api_key
            elif provider.name == 'Google Gemini':
                return self.gemini_api_key
            elif provider.name == 'Groq':
                return self.groq_api_key
        return None

    def has_required_api_keys(self):
        """Check if user has both required API keys"""
        return bool(self.get_selected_provider_key() and self.fal_key)

    def is_admin(self):
        """Check if user is an admin"""
        return self.role == 'admin'

    @staticmethod
    def get_first_user():
        """Get the first user in the database"""
        return User.query.order_by(User.id.asc()).first()

class Image(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    art_style = db.Column(db.String(100))
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    provider_id = db.Column(db.Integer, db.ForeignKey('api_provider.id'))
    model_id = db.Column(db.Integer, db.ForeignKey('ai_model.id'))

    @property
    def dimensions(self):
        return {
            'width': self.width,
            'height': self.height
        }

    def get_dimensions(self):
        """Get image dimensions from file if not stored in database"""
        if not self.width or not self.height:
            try:
                filepath = os.path.join('static', 'images', self.filename)
                with PILImage.open(filepath) as img:
                    self.width, self.height = img.size
                    db.session.commit()
            except Exception as e:
                print(f"Error getting image dimensions: {str(e)}")
        return self.dimensions

    @property
    def file_path(self):
        return os.path.join('static', 'images', self.filename)

    def get_url(self, format='png'):
        base_filename = os.path.splitext(self.filename)[0]
        return f'/static/images/{base_filename}.{format}'

class TrainingHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    training_id = db.Column(db.String(32), unique=True, nullable=False)
    queue_id = db.Column(db.String(100), unique=True)  # FAL queue ID
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    trigger_word = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed, failed
    logs = db.Column(db.Text)
    result = db.Column(db.JSON)
    config_url = db.Column(db.String(500))
    weights_url = db.Column(db.String(500))
    webhook_secret = db.Column(db.String(48))  # For webhook verification
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'training_id': self.training_id,
            'queue_id': self.queue_id,
            'trigger_word': self.trigger_word,
            'status': self.status,
            'logs': self.logs,
            'config_url': self.config_url,
            'weights_url': self.weights_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'result': self.result
        }
