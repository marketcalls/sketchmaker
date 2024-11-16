from extensions import db
from datetime import datetime
import os
from PIL import Image as PILImage

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
