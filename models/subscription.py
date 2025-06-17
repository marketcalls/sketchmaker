from extensions import db
from datetime import datetime, timedelta
from enum import Enum

class SubscriptionPlan(Enum):
    FREE = "free"
    PREMIUM = "premium"
    PRO = "pro"

class SubscriptionPlanModel(db.Model):
    __tablename__ = 'subscription_plans'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    monthly_credits = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text)
    features = db.Column(db.JSON)  # Store feature list as JSON
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    subscriptions = db.relationship('UserSubscription', backref='plan', lazy=True)
    
    @staticmethod
    def initialize_default_plans():
        """Create default subscription plans if they don't exist"""
        plans = [
            {
                'name': SubscriptionPlan.FREE.value,
                'display_name': 'Free Plan',
                'monthly_credits': 10,
                'description': 'Perfect for trying out our AI image generation',
                'features': [
                    '10 images per month',
                    'Access to basic models',
                    'Standard resolution',
                    'Community support'
                ]
            },
            {
                'name': SubscriptionPlan.PREMIUM.value,
                'display_name': 'Premium Plan',
                'monthly_credits': 100,
                'description': 'Great for regular users and small projects',
                'features': [
                    '100 images per month',
                    'Access to all models',
                    'High resolution',
                    'Priority support',
                    'Custom LoRA training',
                    'Batch processing'
                ]
            },
            {
                'name': SubscriptionPlan.PRO.value,
                'display_name': 'Pro Plan',
                'monthly_credits': 1000,
                'description': 'For professionals and businesses',
                'features': [
                    '1000 images per month',
                    'Access to all models',
                    'Ultra-high resolution',
                    'Dedicated support',
                    'Unlimited LoRA training',
                    'API access',
                    'Advanced features'
                ]
            }
        ]
        
        for plan_data in plans:
            existing = SubscriptionPlanModel.query.filter_by(name=plan_data['name']).first()
            if not existing:
                plan = SubscriptionPlanModel(**plan_data)
                db.session.add(plan)
        
        db.session.commit()

class UserSubscription(db.Model):
    __tablename__ = 'user_subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.id'), nullable=False)
    credits_remaining = db.Column(db.Integer, default=0)
    credits_used_this_month = db.Column(db.Integer, default=0)
    subscription_start = db.Column(db.DateTime, default=datetime.utcnow)
    subscription_end = db.Column(db.DateTime)  # NULL for active subscriptions
    last_credit_reset = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Admin management fields
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # Admin who assigned the plan
    notes = db.Column(db.Text)  # Admin notes
    
    def should_reset_credits(self):
        """Check if monthly credits should be reset based on subscription start date"""
        if not self.subscription_start:
            return True
        
        now = datetime.utcnow()
        
        # Calculate next reset date based on subscription start date
        # Reset happens monthly on the same day the subscription started
        next_reset_date = self.get_next_reset_date()
        
        return now >= next_reset_date
    
    def get_next_reset_date(self):
        """Get the next credit reset date based on subscription start date"""
        if not self.subscription_start:
            return datetime.utcnow()
        
        now = datetime.utcnow()
        start_date = self.subscription_start
        
        # Calculate how many months have passed since subscription started
        months_passed = (now.year - start_date.year) * 12 + (now.month - start_date.month)
        
        # Calculate next reset date (same day next month)
        if now.day >= start_date.day and now.hour >= start_date.hour:
            months_passed += 1
        
        # Add months to the start date to get next reset
        next_reset_year = start_date.year + (start_date.month + months_passed - 1) // 12
        next_reset_month = ((start_date.month + months_passed - 1) % 12) + 1
        
        try:
            next_reset_date = start_date.replace(year=next_reset_year, month=next_reset_month)
        except ValueError:
            # Handle edge case for end-of-month dates (e.g., Jan 31 -> Feb 28)
            import calendar
            last_day = calendar.monthrange(next_reset_year, next_reset_month)[1]
            day = min(start_date.day, last_day)
            next_reset_date = start_date.replace(year=next_reset_year, month=next_reset_month, day=day)
        
        return next_reset_date
    
    def days_until_reset(self):
        """Get days until next credit reset"""
        next_reset = self.get_next_reset_date()
        now = datetime.utcnow()
        delta = next_reset - now
        return max(0, delta.days)
    
    def reset_monthly_credits(self):
        """Reset credits for the new month"""
        self.credits_remaining = self.plan.monthly_credits
        self.credits_used_this_month = 0
        self.last_credit_reset = datetime.utcnow()
        db.session.commit()
    
    def use_credit(self, amount=1):
        """Use credits for image generation"""
        if self.credits_remaining >= amount:
            self.credits_remaining -= amount
            self.credits_used_this_month += amount
            db.session.commit()
            return True
        return False
    
    def has_credits(self, amount=1):
        """Check if user has enough credits"""
        return self.credits_remaining >= amount

class UsageHistory(db.Model):
    __tablename__ = 'usage_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subscription_id = db.Column(db.Integer, db.ForeignKey('user_subscriptions.id'))
    action = db.Column(db.String(50), nullable=False)  # 'image_generation', 'training', etc.
    credits_used = db.Column(db.Integer, default=1)
    extra_data = db.Column(db.JSON)  # Store additional info like model used, parameters, etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='usage_history')
    subscription = db.relationship('UserSubscription', backref='usage_history')