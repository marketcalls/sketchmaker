from flask_sqlalchemy import SQLAlchemy
from extensions import db

# Import all models to make them available when importing from models package
from .api import APIProvider, AIModel
from .auth import User, PasswordResetOTP, AuthSettings
from .content import Image, TrainingHistory
from .email import EmailSettings
from .system import SystemSettings
from .subscription import SubscriptionPlanModel, UserSubscription, UsageHistory, SubscriptionPlan
from .api_settings import APISettings

# For backwards compatibility and ease of use, export all models at package level
__all__ = [
    'APIProvider',
    'AIModel',
    'User',
    'PasswordResetOTP',
    'AuthSettings',
    'Image',
    'TrainingHistory',
    'EmailSettings',
    'SystemSettings',
    'SubscriptionPlanModel',
    'UserSubscription',
    'UsageHistory',
    'SubscriptionPlan',
    'APISettings',
    'db'
]
