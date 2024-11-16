from extensions import db
from datetime import datetime

class SystemSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    require_manual_approval = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get_settings():
        """Get or create system settings"""
        settings = SystemSettings.query.first()
        if not settings:
            settings = SystemSettings()
            db.session.add(settings)
            db.session.commit()
        return settings
