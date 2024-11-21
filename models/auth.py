from extensions import db
from flask_login import UserMixin
from datetime import datetime, timedelta
import random
from .api import APIProvider  # Add this import

class AuthSettings(db.Model):
    __tablename__ = 'auth_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    regular_auth_enabled = db.Column(db.Boolean, default=True, nullable=False)
    google_auth_enabled = db.Column(db.Boolean, default=False, nullable=False)
    google_client_id = db.Column(db.String(255))
    google_client_secret = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get_settings():
        """Get or create auth settings"""
        settings = AuthSettings.query.first()
        if not settings:
            settings = AuthSettings(
                regular_auth_enabled=True,
                google_auth_enabled=False
            )
            db.session.add(settings)
            db.session.commit()
        return settings

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    role = db.Column(db.String(20), default='user')  # 'superadmin', 'admin' or 'user'
    is_active = db.Column(db.Boolean, default=True)
    is_approved = db.Column(db.Boolean, default=True)  # For manual approval process
    
    # Relationships
    images = db.relationship('Image', backref='user', lazy=True)
    training_history = db.relationship('TrainingHistory', backref='user', lazy=True)
    password_resets = db.relationship('PasswordResetOTP', backref='user', lazy=True)
    
    # API Provider settings
    selected_provider_id = db.Column(db.Integer, db.ForeignKey('api_provider.id'))
    selected_model_id = db.Column(db.Integer, db.ForeignKey('ai_model.id'))
    
    # API Keys for different providers
    openai_api_key = db.Column(db.String(255))
    anthropic_api_key = db.Column(db.String(255))
    gemini_api_key = db.Column(db.String(255))
    groq_api_key = db.Column(db.String(255))
    fal_key = db.Column(db.String(255))

    # Google OAuth info
    google_id = db.Column(db.String(255), unique=True)  # For Google OAuth users

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
        if not self.selected_provider_id:
            return None
            
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
        """Check if user is an admin or superadmin"""
        return self.role in ['admin', 'superadmin']

    def is_superadmin(self):
        """Check if user is a superadmin"""
        return self.role == 'superadmin'

    @staticmethod
    def get_first_user():
        """Get the first user in the database"""
        return User.query.order_by(User.id.asc()).first()

    @staticmethod
    def get_total_count():
        """Get total number of users"""
        return User.query.count()

    @staticmethod
    def search_users(query):
        """Search users by username or email"""
        return User.query.filter(
            (User.username.ilike(f'%{query}%')) |
            (User.email.ilike(f'%{query}%'))
        ).all()

class PasswordResetOTP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    otp = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    
    def __init__(self, user_id):
        self.user_id = user_id
        self.otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        self.expires_at = datetime.utcnow() + timedelta(minutes=15)
    
    def is_valid(self):
        """Check if OTP is valid and not expired"""
        return not self.is_used and datetime.utcnow() <= self.expires_at
    
    def use(self):
        """Mark OTP as used"""
        self.is_used = True
        db.session.commit()
    
    @staticmethod
    def generate_otp(user_id):
        """Generate new OTP for user"""
        # Invalidate any existing OTPs
        PasswordResetOTP.query.filter_by(
            user_id=user_id, 
            is_used=False
        ).update({
            'is_used': True
        })
        db.session.commit()
        
        # Create new OTP
        otp = PasswordResetOTP(user_id)
        db.session.add(otp)
        db.session.commit()
        return otp
    
    @staticmethod
    def verify_otp(user_id, otp_value):
        """Verify OTP for user"""
        otp = PasswordResetOTP.query.filter_by(
            user_id=user_id,
            otp=otp_value,
            is_used=False
        ).first()
        
        if otp and otp.is_valid():
            return otp
        return None
