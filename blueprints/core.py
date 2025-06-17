from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from models import db, User, APIProvider, AIModel, APISettings
from datetime import datetime
from extensions import limiter, get_rate_limit_string

core_bp = Blueprint('core', __name__)

@core_bp.route('/')
@limiter.limit(get_rate_limit_string())
def index():
    return render_template('index.html', current_year=datetime.now().year)

@core_bp.route('/dashboard')
@limiter.limit(get_rate_limit_string())
@login_required
def dashboard():
    # Get user's subscription info
    subscription = current_user.get_subscription()
    
    # Check if credits need to be reset
    if subscription and subscription.should_reset_credits():
        subscription.reset_monthly_credits()
    
    # Get system API settings to check if centralized keys are configured
    api_settings = APISettings.get_settings()
    
    return render_template('dashboard.html', 
                         subscription=subscription,
                         api_settings=api_settings)

@core_bp.route('/subscription')
@limiter.limit(get_rate_limit_string())
@login_required
def subscription():
    # Get user's subscription info
    subscription = current_user.get_subscription()
    
    # Check if credits need to be reset
    if subscription and subscription.should_reset_credits():
        subscription.reset_monthly_credits()
    
    return render_template('subscription.html', subscription=subscription)

@core_bp.route('/settings')
@limiter.limit(get_rate_limit_string())
@login_required
def settings():
    # Get API settings and available providers
    api_settings = APISettings.get_settings()
    available_providers = api_settings.get_available_providers()
    
    # Get all providers and models for display
    providers = APIProvider.query.filter_by(is_active=True).all()
    models = AIModel.query.filter_by(is_active=True).all()
    
    # Get user's subscription info
    subscription = current_user.get_subscription()
    
    # Check if credits need to be reset
    if subscription and subscription.should_reset_credits():
        subscription.reset_monthly_credits()
    
    return render_template('settings.html', 
                         api_settings=api_settings,
                         available_providers=available_providers,
                         providers=providers,
                         models=models,
                         subscription=subscription)

