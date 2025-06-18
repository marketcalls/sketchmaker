from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, User, SubscriptionPlanModel, UserSubscription, UsageHistory, SubscriptionPlan, SystemSettings
from .decorators import admin_required, superadmin_required
from services.scheduler import subscription_scheduler
from datetime import datetime, timezone
import json

admin_subscription_bp = Blueprint('admin_subscription', __name__, url_prefix='/admin/subscriptions')

@admin_subscription_bp.route('/')
@login_required
@admin_required
def manage_subscriptions():
    """Manage user subscriptions"""
    users = User.query.all()
    plans = SubscriptionPlanModel.query.filter_by(is_active=True).all()
    
    # Get subscription info for all users
    user_subscriptions = []
    for user in users:
        sub = user.get_subscription()
        user_subscriptions.append({
            'user': user,
            'subscription': sub,
            'plan_name': sub.plan.display_name if sub else 'No Plan',
            'credits_remaining': sub.credits_remaining if sub else 0,
            'credits_used': sub.credits_used_this_month if sub else 0
        })
    
    return render_template('admin/subscriptions.html', 
                         user_subscriptions=user_subscriptions,
                         plans=plans)

@admin_subscription_bp.route('/assign', methods=['POST'])
@login_required
@admin_required
def assign_subscription():
    """Assign subscription plan to user"""
    data = request.get_json()
    user_id = data.get('user_id')
    plan_id = data.get('plan_id')
    notes = data.get('notes', '')
    
    user = User.query.get(user_id)
    plan = SubscriptionPlanModel.query.get(plan_id)
    
    if not user or not plan:
        return jsonify({'success': False, 'message': 'Invalid user or plan'}), 400
    
    # Check if user is trying to modify a superadmin and they're not a superadmin
    if user.is_superadmin() and not current_user.is_superadmin():
        return jsonify({'success': False, 'message': 'Only superadmins can modify other superadmins'}), 403
    
    # Deactivate existing subscription
    existing = UserSubscription.query.filter_by(user_id=user_id, is_active=True).first()
    if existing:
        existing.is_active = False
        existing.subscription_end = datetime.utcnow()
    
    # Create new subscription
    new_sub = UserSubscription(
        user_id=user_id,
        plan_id=plan_id,
        credits_remaining=plan.monthly_credits,
        credits_used_this_month=0,
        assigned_by_id=current_user.id,
        notes=notes
    )
    
    db.session.add(new_sub)
    db.session.commit()
    
    # Schedule automatic credit reset for this user
    subscription_scheduler.schedule_user_reset(new_sub.id)
    
    return jsonify({
        'success': True, 
        'message': f'Successfully assigned {plan.display_name} to {user.username}'
    })

@admin_subscription_bp.route('/modify-credits', methods=['POST'])
@login_required
@admin_required
def modify_credits():
    """Manually adjust user credits"""
    data = request.get_json()
    user_id = data.get('user_id')
    credits = data.get('credits')
    action = data.get('action')  # 'add' or 'set'
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'Invalid user'}), 400
    
    sub = user.get_subscription()
    if not sub:
        return jsonify({'success': False, 'message': 'User has no active subscription'}), 400
    
    if action == 'add':
        sub.credits_remaining += credits
    elif action == 'set':
        sub.credits_remaining = credits
    else:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400
    
    # Log the manual adjustment
    usage = UsageHistory(
        user_id=user_id,
        subscription_id=sub.id,
        action='manual_adjustment',
        credits_used=credits if action == 'add' else sub.credits_remaining - credits,
        extra_data={
            'adjusted_by': current_user.username,
            'action': action,
            'amount': credits
        }
    )
    
    db.session.add(usage)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Credits updated for {user.username}',
        'credits_remaining': sub.credits_remaining
    })

@admin_subscription_bp.route('/plans', methods=['GET', 'POST'])
@login_required
@superadmin_required
def manage_plans():
    """Manage subscription plans (superadmin only)"""
    if request.method == 'POST':
        data = request.get_json()
        
        if data.get('action') == 'create':
            plan = SubscriptionPlanModel(
                name=data['name'],
                display_name=data['display_name'],
                monthly_credits=data['monthly_credits'],
                description=data.get('description', ''),
                features=data.get('features', [])
            )
            db.session.add(plan)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Plan created successfully'})
        
        elif data.get('action') == 'update':
            plan = SubscriptionPlanModel.query.get(data['plan_id'])
            if plan:
                plan.display_name = data['display_name']
                plan.monthly_credits = data['monthly_credits']
                plan.description = data.get('description', plan.description)
                plan.features = data.get('features', plan.features)
                db.session.commit()
                return jsonify({'success': True, 'message': 'Plan updated successfully'})
        
        elif data.get('action') == 'toggle':
            plan = SubscriptionPlanModel.query.get(data['plan_id'])
            if plan:
                plan.is_active = not plan.is_active
                db.session.commit()
                return jsonify({'success': True, 'message': 'Plan status updated'})
    
    plans = SubscriptionPlanModel.query.all()
    return render_template('admin/subscription_plans.html', plans=plans)

@admin_subscription_bp.route('/usage/<int:user_id>')
@login_required
@admin_required
def view_usage(user_id):
    """View user's usage history"""
    user = User.query.get_or_404(user_id)
    
    # Get usage history for the last 30 days
    usage_history = UsageHistory.query.filter_by(user_id=user_id)\
        .order_by(UsageHistory.created_at.desc())\
        .limit(100).all()
    
    # Calculate usage statistics
    total_credits_used = sum(u.credits_used for u in usage_history)
    
    return render_template('admin/usage_history.html',
                         user=user,
                         usage_history=usage_history,
                         total_credits_used=total_credits_used)

@admin_subscription_bp.route('/reports')
@login_required
@admin_required
def subscription_reports():
    """View subscription and usage reports"""
    # Get subscription statistics
    total_users = User.query.count()
    
    # Count users by plan
    plan_stats = db.session.query(
        SubscriptionPlanModel.display_name,
        db.func.count(UserSubscription.id).label('count')
    ).join(
        UserSubscription, SubscriptionPlanModel.id == UserSubscription.plan_id
    ).filter(
        UserSubscription.is_active == True
    ).group_by(SubscriptionPlanModel.display_name).all()
    
    # Get usage statistics for current month
    current_month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
    
    # Total credits used this month
    total_credits_used = db.session.query(
        db.func.sum(UsageHistory.credits_used).label('total_credits')
    ).filter(
        UsageHistory.created_at >= current_month_start
    ).scalar() or 0
    
    # Get credit usage data
    total_credits_allocated = db.session.query(
        db.func.sum(SubscriptionPlanModel.monthly_credits).label('total_allocated')
    ).join(
        UserSubscription, SubscriptionPlanModel.id == UserSubscription.plan_id
    ).filter(
        UserSubscription.is_active == True
    ).scalar() or 0
    
    # Calculate utilization rate
    utilization_rate = (total_credits_used / total_credits_allocated * 100) if total_credits_allocated > 0 else 0
    
    # Get feature usage counts (from UsageHistory)
    feature_usage_counts = db.session.query(
        UsageHistory.action,
        db.func.count(UsageHistory.id).label('count')
    ).filter(
        UsageHistory.created_at >= current_month_start,
        UsageHistory.action.in_(['images', 'banners', 'magix', 'lora_training'])
    ).group_by(UsageHistory.action).all()
    
    # Convert to dictionary for easier access
    feature_counts = {action: count for action, count in feature_usage_counts}
    
    # Get feature usage stats object
    feature_usage = type('FeatureUsage', (), {
        'total_images': feature_counts.get('images', 0),
        'total_banners': feature_counts.get('banners', 0),
        'total_magix': feature_counts.get('magix', 0),
        'total_lora': feature_counts.get('lora_training', 0)
    })()
    
    # Credit usage object
    credit_usage = type('CreditUsage', (), {
        'total_credits': total_credits_used,
        'utilization_rate': utilization_rate
    })()
    
    # Get top users by feature usage (from UsageHistory)
    top_image_users = db.session.query(
        User.username,
        db.func.count(UsageHistory.id).label('usage_count')
    ).join(
        UsageHistory, User.id == UsageHistory.user_id
    ).filter(
        UsageHistory.created_at >= current_month_start,
        UsageHistory.action == 'images'
    ).group_by(User.username)\
    .order_by(db.func.count(UsageHistory.id).desc())\
    .limit(5).all()
    
    top_banner_users = db.session.query(
        User.username,
        db.func.count(UsageHistory.id).label('usage_count')
    ).join(
        UsageHistory, User.id == UsageHistory.user_id
    ).filter(
        UsageHistory.created_at >= current_month_start,
        UsageHistory.action == 'banners'
    ).group_by(User.username)\
    .order_by(db.func.count(UsageHistory.id).desc())\
    .limit(5).all()
    
    top_magix_users = db.session.query(
        User.username,
        db.func.count(UsageHistory.id).label('usage_count')
    ).join(
        UsageHistory, User.id == UsageHistory.user_id
    ).filter(
        UsageHistory.created_at >= current_month_start,
        UsageHistory.action == 'magix'
    ).group_by(User.username)\
    .order_by(db.func.count(UsageHistory.id).desc())\
    .limit(5).all()
    
    top_lora_users = db.session.query(
        User.username,
        db.func.count(UsageHistory.id).label('usage_count')
    ).join(
        UsageHistory, User.id == UsageHistory.user_id
    ).filter(
        UsageHistory.created_at >= current_month_start,
        UsageHistory.action == 'lora_training'
    ).group_by(User.username)\
    .order_by(db.func.count(UsageHistory.id).desc())\
    .limit(5).all()
    
    # Get top users by credits with plan info
    top_users_data = db.session.query(
        User.username,
        SubscriptionPlanModel.display_name.label('plan_name'),
        SubscriptionPlanModel.monthly_credits,
        UserSubscription.credits_used_this_month,
        db.func.sum(UsageHistory.credits_used).label('total_credits')
    ).join(
        UsageHistory, User.id == UsageHistory.user_id
    ).join(
        UserSubscription, User.id == UserSubscription.user_id
    ).join(
        SubscriptionPlanModel, UserSubscription.plan_id == SubscriptionPlanModel.id
    ).filter(
        UsageHistory.created_at >= current_month_start,
        UserSubscription.is_active == True
    ).group_by(User.username, SubscriptionPlanModel.display_name, SubscriptionPlanModel.monthly_credits, UserSubscription.credits_used_this_month)\
    .order_by(db.func.sum(UsageHistory.credits_used).desc())\
    .limit(10).all()
    
    # Transform to objects for template
    top_users = []
    for user_data in top_users_data:
        top_users.append(type('UserData', (), {
            'username': user_data.username,
            'plan_name': user_data.plan_name,
            'monthly_credits': user_data.monthly_credits,
            'credits_used': user_data.total_credits or 0
        })())
    
    # Get credit breakdown by plan
    plan_credit_breakdown = db.session.query(
        SubscriptionPlanModel.display_name.label('plan_name'),
        db.func.count(UserSubscription.id).label('user_count'),
        (SubscriptionPlanModel.monthly_credits * db.func.count(UserSubscription.id)).label('total_allocated'),
        db.func.sum(UserSubscription.credits_used_this_month).label('total_used'),
        db.func.sum(UserSubscription.credits_remaining).label('total_remaining')
    ).join(
        UserSubscription, SubscriptionPlanModel.id == UserSubscription.plan_id
    ).filter(
        UserSubscription.is_active == True
    ).group_by(SubscriptionPlanModel.display_name, SubscriptionPlanModel.monthly_credits).all()
    
    # Transform to objects for template
    plan_breakdown = []
    for plan_data in plan_credit_breakdown:
        plan_breakdown.append(type('PlanData', (), {
            'plan_name': plan_data.plan_name,
            'user_count': plan_data.user_count,
            'total_allocated': plan_data.total_allocated or 0,
            'total_used': plan_data.total_used or 0,
            'total_remaining': plan_data.total_remaining or 0
        })())
    
    # Get system settings for dynamic credit costs
    system_settings = SystemSettings.get_settings()
    
    return render_template('admin/subscription_reports.html',
                         total_users=total_users,
                         plan_stats=plan_stats,
                         credit_usage=credit_usage,
                         feature_usage=feature_usage,
                         top_users=top_users,
                         top_image_users=top_image_users,
                         top_banner_users=top_banner_users,
                         top_magix_users=top_magix_users,
                         top_lora_users=top_lora_users,
                         plan_credit_breakdown=plan_breakdown,
                         system_settings=system_settings)

@admin_subscription_bp.route('/edit-limits/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user_limits(user_id):
    """Edit individual user's feature limits"""
    user = User.query.get_or_404(user_id)
    subscription = user.get_subscription()
    
    if not subscription:
        flash('User does not have an active subscription', 'error')
        return redirect(url_for('admin_subscription.manage_subscriptions'))
    
    if request.method == 'POST':
        try:
            # Get the form data
            data = request.get_json() or request.form
            
            # Update feature usage (reset usage)
            if data.get('action') == 'reset_usage':
                subscription.images_used_this_month = 0
                subscription.banners_used_this_month = 0
                subscription.magix_used_this_month = 0
                subscription.lora_training_used_this_month = 0
                subscription.credits_used_this_month = 0
                subscription.credits_remaining = subscription.plan.monthly_credits
                db.session.commit()
                
                return jsonify({'success': True, 'message': 'User usage reset successfully'})
            
            # Update custom limits (would require adding custom limit fields to UserSubscription model)
            elif data.get('action') == 'update_notes':
                subscription.notes = data.get('notes', '')
                db.session.commit()
                
                return jsonify({'success': True, 'message': 'Notes updated successfully'})
                
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})
    
    return render_template('admin/edit_user_limits.html', 
                         user=user, 
                         subscription=subscription)

@admin_subscription_bp.route('/reset-usage/<int:user_id>', methods=['POST'])
@login_required
@admin_required  
def reset_user_usage(user_id):
    """Reset user's monthly usage"""
    user = User.query.get_or_404(user_id)
    subscription = user.get_subscription()
    
    if not subscription:
        return jsonify({'success': False, 'message': 'User does not have an active subscription'})
    
    try:
        subscription.reset_monthly_credits()
        return jsonify({'success': True, 'message': f'Usage reset for {user.username}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@admin_subscription_bp.route('/user-data/<int:user_id>')
@login_required
@admin_required
def get_user_data(user_id):
    """Get user's subscription data for the modal"""
    user = User.query.get_or_404(user_id)
    subscription = user.get_subscription()
    
    if not subscription:
        return jsonify({
            'credits_remaining': 0,
            'images_used_this_month': 0,
            'banners_used_this_month': 0,
            'magix_used_this_month': 0,
            'lora_training_used_this_month': 0
        })
    
    return jsonify({
        'credits_remaining': subscription.credits_remaining,
        'images_used_this_month': subscription.get_feature_usage_count('images'),
        'banners_used_this_month': subscription.get_feature_usage_count('banners'),
        'magix_used_this_month': subscription.get_feature_usage_count('magix'),
        'lora_training_used_this_month': subscription.get_feature_usage_count('lora_training')
    })

@admin_subscription_bp.route('/modify-features', methods=['POST'])
@login_required
@admin_required
def modify_user_features():
    """Modify user's feature usage or credits"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        modify_type = data.get('modify_type')
        action = data.get('action')
        amount = data.get('amount', 0)
        
        user = User.query.get_or_404(user_id)
        subscription = user.get_subscription()
        
        if not subscription:
            return jsonify({'success': False, 'message': 'User does not have an active subscription'})
        
        # Handle different modify types
        if modify_type == 'credits':
            if action == 'add':
                subscription.credits_remaining += amount
            elif action == 'set':
                subscription.credits_remaining = amount
            elif action == 'reset':
                subscription.credits_remaining = subscription.plan.monthly_credits
                subscription.credits_used_this_month = 0
                
        elif modify_type == 'images':
            if action == 'add':
                subscription.images_used_this_month = (subscription.images_used_this_month or 0) + amount
            elif action == 'set':
                subscription.images_used_this_month = amount
            elif action == 'reset':
                subscription.images_used_this_month = 0
                
        elif modify_type == 'banners':
            if action == 'add':
                subscription.banners_used_this_month = (subscription.banners_used_this_month or 0) + amount
            elif action == 'set':
                subscription.banners_used_this_month = amount
            elif action == 'reset':
                subscription.banners_used_this_month = 0
                
        elif modify_type == 'magix':
            if action == 'add':
                subscription.magix_used_this_month = (subscription.magix_used_this_month or 0) + amount
            elif action == 'set':
                subscription.magix_used_this_month = amount
            elif action == 'reset':
                subscription.magix_used_this_month = 0
                
        elif modify_type == 'lora_training':
            if action == 'add':
                subscription.lora_training_used_this_month = (subscription.lora_training_used_this_month or 0) + amount
            elif action == 'set':
                subscription.lora_training_used_this_month = amount
            elif action == 'reset':
                subscription.lora_training_used_this_month = 0
        
        else:
            return jsonify({'success': False, 'message': 'Invalid modify type'})
        
        # Ensure values don't go negative
        if modify_type == 'credits':
            subscription.credits_remaining = max(0, subscription.credits_remaining)
        else:
            # For usage counters, they can't be negative
            if modify_type == 'images':
                subscription.images_used_this_month = max(0, subscription.images_used_this_month or 0)
            elif modify_type == 'banners':
                subscription.banners_used_this_month = max(0, subscription.banners_used_this_month or 0)
            elif modify_type == 'magix':
                subscription.magix_used_this_month = max(0, subscription.magix_used_this_month or 0)
            elif modify_type == 'lora_training':
                subscription.lora_training_used_this_month = max(0, subscription.lora_training_used_this_month or 0)
        
        db.session.commit()
        
        # Create appropriate success message
        feature_names = {
            'credits': 'Credits',
            'images': 'AI Images',
            'banners': 'Banners', 
            'magix': 'Magix Edits',
            'lora_training': 'LoRA Training'
        }
        
        feature_name = feature_names.get(modify_type, modify_type)
        
        if action == 'reset':
            message = f'{feature_name} reset successfully for {user.username}'
        else:
            message = f'{feature_name} updated successfully for {user.username}'
        
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@admin_subscription_bp.route('/scheduled-jobs')
@login_required
@admin_required
def view_scheduled_jobs():
    """View all scheduled credit reset jobs"""
    jobs = subscription_scheduler.get_scheduled_jobs()
    
    # Check scheduler status
    scheduler_running = False
    scheduler_status = "Unknown"
    try:
        if subscription_scheduler.scheduler:
            scheduler_running = subscription_scheduler.scheduler.running
            scheduler_status = "Running" if scheduler_running else "Stopped"
        else:
            scheduler_status = "Not Initialized"
    except Exception as e:
        scheduler_status = "Error"
        print(f"Error checking scheduler status: {e}")
    
    # Enrich job data with user information
    enriched_jobs = []
    for job in jobs:
        subscription = UserSubscription.query.get(job['subscription_id'])
        if subscription:
            enriched_jobs.append({
                **job,
                'username': subscription.user.username,
                'plan_name': subscription.plan.display_name,
                'credits_remaining': subscription.credits_remaining
            })
    
    # Use timezone-aware datetime to match APScheduler's timezone-aware datetimes
    return render_template('admin/scheduled_jobs.html', 
                         jobs=enriched_jobs,
                         current_time=datetime.now(timezone.utc),
                         scheduler_running=scheduler_running,
                         scheduler_status=scheduler_status)

@admin_subscription_bp.route('/force-reset/<int:subscription_id>', methods=['POST'])
@login_required
@admin_required
def force_credit_reset(subscription_id):
    """Manually trigger credit reset for a user"""
    subscription = UserSubscription.query.get_or_404(subscription_id)
    
    if subscription_scheduler.force_reset_user(subscription_id):
        return jsonify({
            'success': True,
            'message': f'Credits reset for {subscription.user.username}'
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Failed to reset credits'
        }), 500