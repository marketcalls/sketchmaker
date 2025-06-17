"""
APScheduler service for managing subscription credit resets

This service handles automatic credit resets for each user based on their
individual subscription start dates.
"""

import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from flask import current_app
from models import db, UserSubscription, UsageHistory

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SubscriptionScheduler:
    def __init__(self, app=None):
        self.scheduler = None
        self.app = app
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize the scheduler with Flask app"""
        self.app = app
        
        # Configure scheduler
        self.scheduler = BackgroundScheduler(
            timezone='UTC',
            job_defaults={
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': 3600  # 1 hour grace time
            }
        )
        
        # Start scheduler when app starts
        with app.app_context():
            self.start()
            self.schedule_all_users()
    
    def start(self):
        """Start the scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Subscription scheduler started")
    
    def stop(self):
        """Stop the scheduler"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Subscription scheduler stopped")
    
    def schedule_user_reset(self, subscription_id):
        """Schedule credit reset for a specific user subscription"""
        try:
            with self.app.app_context():
                subscription = UserSubscription.query.get(subscription_id)
                if not subscription or not subscription.is_active:
                    return False
                
                next_reset_date = subscription.get_next_reset_date()
                
                # Remove existing job for this user if it exists
                job_id = f"credit_reset_{subscription_id}"
                try:
                    self.scheduler.remove_job(job_id)
                except:
                    pass  # Job doesn't exist, which is fine
                
                # Schedule new job
                self.scheduler.add_job(
                    func=self._reset_user_credits,
                    trigger=DateTrigger(run_date=next_reset_date),
                    args=[subscription_id],
                    id=job_id,
                    name=f"Credit reset for user {subscription.user.username}",
                    replace_existing=True
                )
                
                logger.info(f"Scheduled credit reset for user {subscription.user.username} at {next_reset_date}")
                return True
                
        except Exception as e:
            logger.error(f"Error scheduling credit reset for subscription {subscription_id}: {e}")
            return False
    
    def schedule_all_users(self):
        """Schedule credit resets for all active subscriptions"""
        try:
            with self.app.app_context():
                active_subscriptions = UserSubscription.query.filter_by(is_active=True).all()
                
                scheduled_count = 0
                for subscription in active_subscriptions:
                    if self.schedule_user_reset(subscription.id):
                        scheduled_count += 1
                
                logger.info(f"Scheduled credit resets for {scheduled_count} users")
                return scheduled_count
                
        except Exception as e:
            logger.error(f"Error scheduling credit resets for all users: {e}")
            return 0
    
    def _reset_user_credits(self, subscription_id):
        """Internal method to reset credits for a user"""
        try:
            with self.app.app_context():
                subscription = UserSubscription.query.get(subscription_id)
                if not subscription or not subscription.is_active:
                    logger.warning(f"Subscription {subscription_id} not found or inactive")
                    return
                
                old_credits = subscription.credits_remaining
                subscription.reset_monthly_credits()
                
                # Log the credit reset
                usage = UsageHistory(
                    user_id=subscription.user_id,
                    subscription_id=subscription.id,
                    action='monthly_reset',
                    credits_used=0,  # This is a reset, not usage
                    extra_data={
                        'old_credits': old_credits,
                        'new_credits': subscription.credits_remaining,
                        'reset_type': 'automatic_monthly',
                        'reset_date': datetime.utcnow().isoformat()
                    }
                )
                db.session.add(usage)
                db.session.commit()
                
                logger.info(f"Reset credits for user {subscription.user.username}: {old_credits} -> {subscription.credits_remaining}")
                
                # Schedule next reset
                self.schedule_user_reset(subscription_id)
                
        except Exception as e:
            logger.error(f"Error resetting credits for subscription {subscription_id}: {e}")
            # Rollback any partial changes
            try:
                db.session.rollback()
            except:
                pass
    
    def unschedule_user(self, subscription_id):
        """Remove scheduled credit reset for a user"""
        try:
            job_id = f"credit_reset_{subscription_id}"
            self.scheduler.remove_job(job_id)
            logger.info(f"Unscheduled credit reset for subscription {subscription_id}")
            return True
        except:
            return False
    
    def get_scheduled_jobs(self):
        """Get list of all scheduled credit reset jobs"""
        jobs = []
        for job in self.scheduler.get_jobs():
            if job.id.startswith('credit_reset_'):
                jobs.append({
                    'job_id': job.id,
                    'subscription_id': int(job.id.split('_')[-1]),
                    'next_run_time': job.next_run_time,
                    'name': job.name
                })
        return jobs
    
    def force_reset_user(self, subscription_id):
        """Manually trigger a credit reset for a user"""
        try:
            with self.app.app_context():
                self._reset_user_credits(subscription_id)
                return True
        except Exception as e:
            logger.error(f"Error forcing credit reset for subscription {subscription_id}: {e}")
            return False


# Global scheduler instance
subscription_scheduler = SubscriptionScheduler()