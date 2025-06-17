from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, User, SubscriptionPlanModel, UserSubscription, UsageHistory, SubscriptionPlan
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
    
    monthly_usage = db.session.query(
        db.func.sum(UsageHistory.credits_used).label('total_credits')
    ).filter(
        UsageHistory.created_at >= current_month_start
    ).scalar() or 0
    
    # Get top users by usage
    top_users = db.session.query(
        User.username,
        db.func.sum(UsageHistory.credits_used).label('total_credits')
    ).join(
        UsageHistory, User.id == UsageHistory.user_id
    ).filter(
        UsageHistory.created_at >= current_month_start
    ).group_by(User.username)\
    .order_by(db.func.sum(UsageHistory.credits_used).desc())\
    .limit(10).all()
    
    return render_template('admin/subscription_reports.html',
                         total_users=total_users,
                         plan_stats=plan_stats,
                         monthly_usage=monthly_usage,
                         top_users=top_users)

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