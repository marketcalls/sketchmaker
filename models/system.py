from extensions import db
from datetime import datetime

class SystemSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    require_manual_approval = db.Column(db.Boolean, default=False)
    
    # Credit configuration
    credit_cost_images = db.Column(db.Float, default=1.0)
    credit_cost_banners = db.Column(db.Float, default=0.5)
    credit_cost_magix = db.Column(db.Float, default=1.0)
    credit_cost_lora_training = db.Column(db.Float, default=40.0)
    
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
    
    def get_credit_cost(self, feature_type):
        """Get credit cost for a specific feature"""
        feature_map = {
            'images': self.credit_cost_images,
            'banners': self.credit_cost_banners,
            'magix': self.credit_cost_magix,
            'lora_training': self.credit_cost_lora_training
        }
        return feature_map.get(feature_type, 1.0)
    
    def get_all_credit_costs(self):
        """Get all credit costs as a dictionary"""
        return {
            'images': self.credit_cost_images,
            'banners': self.credit_cost_banners,
            'magix': self.credit_cost_magix,
            'lora_training': self.credit_cost_lora_training
        }
    
    def update_credit_costs(self, credit_costs):
        """Update credit costs from a dictionary"""
        if 'images' in credit_costs:
            self.credit_cost_images = float(credit_costs['images'])
        if 'banners' in credit_costs:
            self.credit_cost_banners = float(credit_costs['banners'])
        if 'magix' in credit_costs:
            self.credit_cost_magix = float(credit_costs['magix'])
        if 'lora_training' in credit_costs:
            self.credit_cost_lora_training = float(credit_costs['lora_training'])
        
        self.updated_at = datetime.utcnow()
        db.session.commit()
