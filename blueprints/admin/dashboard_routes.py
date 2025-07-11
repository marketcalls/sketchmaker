from flask import render_template
from flask_login import login_required, current_user
from .decorators import admin_required
from models import User, APIProvider, APISettings, UserSubscription, SubscriptionPlanModel, SystemSettings, db
from models.subscription import UsageHistory
from models.api_settings import APISettings
from datetime import datetime, timedelta
from services.scheduler import subscription_scheduler
import json


@admin_required
@login_required
def dashboard():
    """Admin dashboard with system overview and statistics"""
    
    # Initialize stats with default values
    stats = {
        'total_users': 0,
        'new_users_today': 0,
        'active_subscriptions': 0,
        'subscription_plans': 0,
        'total_images': 0,
        'images_today': 0,
        'credits_used_today': 0,
        'credits_used_this_month': 0,
        'api_status': False,
        'api_providers_active': 0,
        'api_providers_total': 0
    }
    
    try:
        # Calculate stats with error handling
        stats['total_users'] = User.query.count()
        
        # Handle potential timezone issues with date filtering
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        stats['new_users_today'] = User.query.filter(
            User.created_at >= today
        ).count()
        
        stats['active_subscriptions'] = UserSubscription.query.filter_by(is_active=True).count()
        stats['subscription_plans'] = SubscriptionPlanModel.query.filter_by(is_active=True).count()
        stats['total_images'] = UsageHistory.query.filter_by(action='images').count()
        stats['images_today'] = UsageHistory.query.filter(
            UsageHistory.created_at >= today,
            UsageHistory.action == 'images'
        ).count()
        
        # Credit usage statistics
        stats['credits_used_today'] = db.session.query(
            db.func.sum(UsageHistory.credits_used)
        ).filter(
            UsageHistory.created_at >= today
        ).scalar() or 0
        
        # Current month start
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        stats['credits_used_this_month'] = db.session.query(
            db.func.sum(UsageHistory.credits_used)
        ).filter(
            UsageHistory.created_at >= month_start
        ).scalar() or 0
        
    except Exception as e:
        print(f"Error calculating dashboard stats: {e}")
        # Stats will use default values if there's an error
    
    # API status with error handling
    try:
        api_settings = APISettings.get_settings()
        providers = APIProvider.query.all()
        api_providers_active = 0
        
        for provider in providers:
            provider_key_attr = f'{provider.name.lower()}_api_key'
            if provider.name.lower() == 'google gemini':
                provider_key_attr = 'google_api_key'
            
            if hasattr(api_settings, provider_key_attr) and getattr(api_settings, provider_key_attr):
                api_providers_active += 1
        
        api_providers_total = len(providers)
        
        stats['api_status'] = api_providers_active > 0
        stats['api_providers_active'] = api_providers_active
        stats['api_providers_total'] = api_providers_total
        
    except Exception as e:
        print(f"Error checking API status: {e}")
        # API status will remain as default values
    
    # Recent activity
    recent_activities = []
    try:
        # Get recent users (last 5)
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        for user in recent_users:
            time_diff = datetime.utcnow() - user.created_at
            if time_diff.days == 0:
                time_ago = f"{time_diff.seconds // 3600}h ago" if time_diff.seconds >= 3600 else f"{time_diff.seconds // 60}m ago"
            else:
                time_ago = f"{time_diff.days}d ago"
            
            recent_activities.append({
                'description': f"New user registered: {user.username}",
                'time_ago': time_ago
            })
        
        # Get recent feature usage (last 5)
        recent_usage = UsageHistory.query.order_by(UsageHistory.created_at.desc()).limit(5).all()
        for usage in recent_usage:
            time_diff = datetime.utcnow() - usage.created_at
            if time_diff.days == 0:
                time_ago = f"{time_diff.seconds // 3600}h ago" if time_diff.seconds >= 3600 else f"{time_diff.seconds // 60}m ago"
            else:
                time_ago = f"{time_diff.days}d ago"
            
            # Map action to readable names
            action_names = {
                'images': 'AI Image',
                'banners': 'Banner',
                'magix': 'Magix Edit',
                'lora_training': 'LoRA Training'
            }
            action_name = action_names.get(usage.action, usage.action.title())
            
            recent_activities.append({
                'description': f"{action_name} created by {usage.user.username} ({usage.credits_used} credits)",
                'time_ago': time_ago
            })
        
        # Sort by most recent
        recent_activities.sort(key=lambda x: x['time_ago'])
        recent_activities = recent_activities[:10]  # Limit to 10 items
        
    except Exception as e:
        print(f"Error getting recent activities: {e}")
        recent_activities = []
    
    # System alerts with error handling
    alerts = []
    
    try:
        # Check API key configuration
        api_settings = APISettings.get_settings()
        if not api_settings.has_required_keys():
            alerts.append({
                'type': 'warning',
                'title': 'API Configuration Required',
                'message': 'Some AI providers are not configured. Configure API keys to enable all features.'
            })
    except Exception as e:
        print(f"Error checking API configuration: {e}")
        alerts.append({
            'type': 'error',
            'title': 'Configuration Check Failed',
            'message': 'Unable to verify API configuration. Please check system logs.'
        })
    
    try:
        # Check for users without subscriptions
        users_without_sub = User.query.filter(
            ~User.id.in_(
                db.session.query(UserSubscription.user_id).filter_by(is_active=True)
            )
        ).count()
        
        if users_without_sub > 0:
            alerts.append({
                'type': 'info',
                'title': 'Users Without Subscriptions',
                'message': f'{users_without_sub} users do not have active subscriptions.'
            })
    except Exception as e:
        print(f"Error checking user subscriptions: {e}")
    
    # Check scheduler status with error handling
    try:
        scheduler_running = False
        if subscription_scheduler.scheduler:
            scheduler_running = subscription_scheduler.scheduler.running
        
        if not scheduler_running:
            alerts.append({
                'type': 'error',
                'title': 'Scheduler Not Running',
                'message': 'The background job scheduler is not running. Credit resets may not work properly.'
            })
    except Exception as e:
        print(f"Error checking scheduler status: {e}")
        alerts.append({
            'type': 'warning',
            'title': 'Scheduler Status Unknown',
            'message': 'Unable to verify scheduler status. Please check system logs.'
        })
    
    # System status with error handling
    system_status = {
        'api_services': [],
        'scheduler_running': False,
        'scheduled_jobs': 0,
        'db_size': 0
    }
    
    # Credit breakdown by feature
    credit_breakdown = {
        'images': 0,
        'banners': 0,
        'magix': 0,
        'lora_training': 0
    }
    
    try:
        # Get scheduler status (consistent with alerts checking above)
        scheduler_running = False
        if subscription_scheduler.scheduler:
            scheduler_running = subscription_scheduler.scheduler.running
        system_status['scheduler_running'] = scheduler_running
        
        # Get database size
        system_status['db_size'] = User.query.count() + UsageHistory.query.count() + UserSubscription.query.count()
        
        # Get credit breakdown by feature for today
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        feature_usage = db.session.query(
            UsageHistory.action,
            db.func.sum(UsageHistory.credits_used).label('total_credits')
        ).filter(
            UsageHistory.created_at >= today,
            UsageHistory.action.in_(['images', 'banners', 'magix', 'lora_training'])
        ).group_by(UsageHistory.action).all()
        
        for action, total_credits in feature_usage:
            credit_breakdown[action] = total_credits or 0
        
        # Check each API service status
        api_settings = APISettings.get_settings()
        providers = APIProvider.query.all()
        
        for provider in providers:
            try:
                provider_key_attr = f'{provider.name.lower()}_api_key'
                if provider.name.lower() == 'google gemini':
                    provider_key_attr = 'google_api_key'
                
                has_key = hasattr(api_settings, provider_key_attr) and getattr(api_settings, provider_key_attr)
                system_status['api_services'].append({
                    'name': provider.name,
                    'status': bool(has_key)
                })
            except Exception as e:
                print(f"Error checking status for provider {provider.name}: {e}")
                system_status['api_services'].append({
                    'name': provider.name,
                    'status': False
                })
                
    except Exception as e:
        print(f"Error building system status: {e}")
        # Default values will be used
    
    # Get system settings for dynamic credit costs
    system_settings = SystemSettings.get_settings()
    
    return render_template('admin/dashboard.html', 
                         stats=stats,
                         recent_activities=recent_activities,
                         alerts=alerts,
                         system_status=system_status,
                         credit_breakdown=credit_breakdown,
                         system_settings=system_settings)