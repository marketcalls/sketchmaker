from extensions import db
from datetime import datetime, timedelta
from enum import Enum
from sqlalchemy import CheckConstraint
from contextlib import contextmanager

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
                'monthly_credits': 3,
                'description': 'Perfect for trying out our AI creativity tools',
                'features': {
                    'feature_list': [
                        '3 credits per month',
                        '3 AI images (1 credit each)',
                        '6 banners (0.5 credits each)',
                        '3 Magix edits (1 credit each)',
                        'Access to basic models',
                        'Standard resolution',
                        'Community support'
                    ],
                    'credit_costs': {
                        'images': 1.0,
                        'banners': 0.5,
                        'magix': 1.0,
                        'lora_training': 40.0
                    }
                }
            },
            {
                'name': SubscriptionPlan.PREMIUM.value,
                'display_name': 'Premium Plan',
                'monthly_credits': 100,
                'description': 'Great for regular users and creative projects',
                'features': {
                    'feature_list': [
                        '100 credits per month',
                        '100 AI images (1 credit each)',
                        '200 banners (0.5 credits each)',
                        '100 Magix edits (1 credit each)',
                        '2 LoRA trainings (40 credits each)',
                        'Access to all models',
                        'High resolution',
                        'Priority support'
                    ],
                    'credit_costs': {
                        'images': 1.0,
                        'banners': 0.5,
                        'magix': 1.0,
                        'lora_training': 40.0
                    }
                }
            },
            {
                'name': SubscriptionPlan.PRO.value,
                'display_name': 'Professional Plan',
                'monthly_credits': 1000,
                'description': 'For professionals and businesses',
                'features': {
                    'feature_list': [
                        '1000 credits per month',
                        '1000 AI images (1 credit each)',
                        '2000 banners (0.5 credits each)',
                        '1000 Magix edits (1 credit each)',
                        '25 LoRA trainings (40 credits each)',
                        'Access to all models',
                        'Ultra-high resolution',
                        'Dedicated support',
                        'API access',
                        'Advanced features'
                    ],
                    'credit_costs': {
                        'images': 1.0,
                        'banners': 0.5,
                        'magix': 1.0,
                        'lora_training': 40.0
                    }
                }
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
    __table_args__ = (
        CheckConstraint('credits_remaining >= 0', name='check_credits_non_negative'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.id'), nullable=False)
    credits_remaining = db.Column(db.Integer, default=0, nullable=False)
    credits_used_this_month = db.Column(db.Integer, default=0, nullable=False)
    subscription_start = db.Column(db.DateTime, default=datetime.utcnow)
    subscription_end = db.Column(db.DateTime)  # NULL for active subscriptions
    last_credit_reset = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Simplified credit tracking only
    # Individual feature usage is tracked in UsageHistory for reporting

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
    
    def get_credit_cost(self, feature_type):
        """Get the credit cost for a specific feature from system settings"""
        from .system import SystemSettings
        system_settings = SystemSettings.get_settings()
        return system_settings.get_credit_cost(feature_type)
    
    def can_use_feature(self, feature_type, amount=1):
        """Check if user has enough credits for a feature"""
        cost_per_use = self.get_credit_cost(feature_type)
        total_cost = cost_per_use * amount
        return self.credits_remaining >= total_cost

    @contextmanager
    def reserve_credits(self, feature_type, amount=1):
        """
        Context manager to atomically reserve credits before an operation.
        Credits are deducted immediately with row-level locking.
        If the operation fails, credits are automatically refunded.

        Usage:
            with user.get_subscription().reserve_credits('images', 1) as cost:
                # Perform expensive operation here
                result = call_external_api()
                # If this block completes successfully, credits stay deducted
                # If an exception occurs, credits are automatically refunded
        """
        from sqlalchemy.exc import IntegrityError

        cost_per_use = self.get_credit_cost(feature_type)
        total_cost = cost_per_use * amount

        # Start a nested transaction with pessimistic locking
        # This prevents concurrent requests from reading the same credit balance
        try:
            # Lock this row for update (prevents other transactions from reading/modifying)
            locked_subscription = db.session.query(UserSubscription).with_for_update().filter_by(
                id=self.id
            ).first()

            if not locked_subscription:
                raise ValueError("Subscription not found")

            # Re-check credits under lock
            if locked_subscription.credits_remaining < total_cost:
                raise ValueError(f"Insufficient credits. Required: {total_cost}, Available: {locked_subscription.credits_remaining}")

            # Deduct credits BEFORE the operation
            locked_subscription.credits_remaining -= total_cost
            locked_subscription.credits_used_this_month += total_cost

            # Commit the credit deduction immediately
            db.session.commit()

            # Refresh local instance to reflect the changes
            db.session.refresh(self)

            try:
                # Yield control to the calling code to perform the operation
                yield total_cost

                # If we get here, operation was successful
                # Credits remain deducted

            except Exception as e:
                # Operation failed - refund the credits
                refund_subscription = db.session.query(UserSubscription).with_for_update().filter_by(
                    id=self.id
                ).first()

                if refund_subscription:
                    refund_subscription.credits_remaining += total_cost
                    refund_subscription.credits_used_this_month -= total_cost
                    db.session.commit()
                    db.session.refresh(self)

                # Re-raise the exception
                raise e

        except IntegrityError as e:
            db.session.rollback()
            if 'check_credits_non_negative' in str(e):
                raise ValueError("Insufficient credits - this operation would result in negative credits")
            raise
        except Exception as e:
            db.session.rollback()
            raise

    def use_feature(self, feature_type, amount=1):
        """
        DEPRECATED: Use reserve_credits() context manager instead.
        This method is kept for backward compatibility but is vulnerable to race conditions.
        """
        cost_per_use = self.get_credit_cost(feature_type)
        total_cost = cost_per_use * amount

        if not self.can_use_feature(feature_type, amount):
            return False

        # Deduct credits
        self.credits_remaining -= total_cost
        self.credits_used_this_month += total_cost
        db.session.commit()
        return True
    
    def get_feature_usage_count(self, feature_type):
        """Get count of how many times a feature was used this month"""
        from datetime import datetime
        from sqlalchemy import func
        
        # Calculate start of current billing cycle
        current_month_start = self.get_current_billing_start()
        
        # Count usage from UsageHistory
        count = db.session.query(func.count(UsageHistory.id)).filter(
            UsageHistory.user_id == self.user_id,
            UsageHistory.action == feature_type,
            UsageHistory.created_at >= current_month_start
        ).scalar() or 0
        
        return count
    
    def get_current_billing_start(self):
        """Get the start date of the current billing cycle"""
        if not self.subscription_start:
            return datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        now = datetime.utcnow()
        start_date = self.subscription_start
        
        # Calculate how many months have passed since subscription started
        months_passed = (now.year - start_date.year) * 12 + (now.month - start_date.month)
        
        # If we're past the billing day this month, we're in the current cycle
        if now.day >= start_date.day and now.hour >= start_date.hour:
            # Current cycle
            pass
        else:
            # Previous cycle
            months_passed -= 1
        
        # Calculate current billing cycle start
        billing_year = start_date.year + (start_date.month + months_passed - 1) // 12
        billing_month = ((start_date.month + months_passed - 1) % 12) + 1
        
        try:
            billing_start = start_date.replace(year=billing_year, month=billing_month)
        except ValueError:
            # Handle edge case for end-of-month dates
            import calendar
            last_day = calendar.monthrange(billing_year, billing_month)[1]
            day = min(start_date.day, last_day)
            billing_start = start_date.replace(year=billing_year, month=billing_month, day=day)
        
        return billing_start

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