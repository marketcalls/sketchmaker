#!/usr/bin/env python3
"""
Subscription System Setup Script

This script initializes the subscription system by:
1. Creating database tables
2. Initializing default subscription plans  
3. Assigning free plans to existing users

Run this after implementing the subscription system.
"""

import os
import sys
from datetime import datetime

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import db, User, SubscriptionPlanModel, UserSubscription


def setup_subscriptions():
    """Setup subscription system"""
    app = create_app()
    
    with app.app_context():
        print("Setting up subscription system...")
        print("=" * 50)
        
        # Create tables if they don't exist
        print("1. Creating database tables...")
        db.create_all()
        print("   ✓ Database tables created")
        
        # Initialize default plans
        print("2. Initializing subscription plans...")
        SubscriptionPlanModel.initialize_default_plans()
        
        plans = SubscriptionPlanModel.query.all()
        print(f"   ✓ {len(plans)} subscription plans initialized:")
        for plan in plans:
            print(f"     - {plan.display_name}: {plan.monthly_credits} credits/month")
        
        # Assign free plan to users without subscriptions
        print("3. Assigning free plans to existing users...")
        
        users_without_sub = User.query.filter(
            ~User.id.in_(
                db.session.query(UserSubscription.user_id).filter_by(is_active=True)
            )
        ).all()
        
        free_plan = SubscriptionPlanModel.query.filter_by(name='free').first()
        
        if free_plan and users_without_sub:
            assigned_count = 0
            for user in users_without_sub:
                subscription = UserSubscription(
                    user_id=user.id,
                    plan_id=free_plan.id,
                    credits_remaining=free_plan.monthly_credits,
                    credits_used_this_month=0
                )
                db.session.add(subscription)
                assigned_count += 1
            
            db.session.commit()
            print(f"   ✓ Assigned free plan to {assigned_count} users")
        else:
            print("   ✓ No users need plan assignment")
        
        # Summary
        print("\n4. Summary:")
        total_users = User.query.count()
        total_subscriptions = UserSubscription.query.filter_by(is_active=True).count()
        
        print(f"   - Total users: {total_users}")
        print(f"   - Active subscriptions: {total_subscriptions}")
        
        # Plan distribution
        for plan in plans:
            count = UserSubscription.query.filter_by(plan_id=plan.id, is_active=True).count()
            print(f"   - {plan.display_name}: {count} users")
        
        print("\n" + "=" * 50)
        print("✅ Subscription system setup completed successfully!")
        print("\nNext steps:")
        print("1. Run the application and test the subscription features")
        print("2. Use the admin panel to manage user subscriptions")
        print("3. Credit resets are automatically scheduled based on each user's subscription start date")
        print("4. Monitor scheduled jobs via Admin → Manage Subscriptions → Scheduled Jobs")


def main():
    try:
        setup_subscriptions()
    except Exception as e:
        print(f"❌ Error during setup: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()