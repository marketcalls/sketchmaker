from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import os
from PIL import Image as PILImage

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    openai_api_key = db.Column(db.String(255))
    fal_key = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    role = db.Column(db.String(20), default='user')  # 'admin' or 'user'
    is_active = db.Column(db.Boolean, default=True)
    images = db.relationship('Image', backref='user', lazy=True)

    def get_api_keys(self):
        """Get user's API keys"""
        return {
            'openai_api_key': self.openai_api_key,
            'fal_key': self.fal_key
        }

    def has_required_api_keys(self):
        """Check if user has both required API keys"""
        return bool(self.openai_api_key and self.fal_key)

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
                filepath = os.path.join('sketchmaker', 'static', 'images', self.filename)
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
