#!/usr/bin/env python3
"""
Quick fix script to assign free subscriptions to users without them
"""

import os
import sys

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import db, User, SubscriptionPlanModel, UserSubscription
from datetime import datetime


def fix_subscriptions():
    """Assign free plans to users without subscriptions"""
    app = create_app()

    with app.app_context():
        print("Fixing user subscriptions...")
        print("=" * 50)

        # Initialize default plans if they don't exist
        print("1. Initializing subscription plans...")
        SubscriptionPlanModel.initialize_default_plans()
        print("   ✓ Subscription plans initialized")

        # Find users without active subscriptions
        users_without_sub = User.query.filter(
            ~User.id.in_(
                db.session.query(UserSubscription.user_id).filter_by(is_active=True)
            )
        ).all()

        if not users_without_sub:
            print("\n   ✓ All users already have active subscriptions!")
            print("=" * 50)
            return

        # Get the free plan
        free_plan = SubscriptionPlanModel.query.filter_by(name='free').first()

        if not free_plan:
            print("   ❌ Error: Free plan not found!")
            return

        print(f"\n2. Found {len(users_without_sub)} user(s) without subscriptions:")

        # Assign free plan to each user
        for user in users_without_sub:
            subscription = UserSubscription(
                user_id=user.id,
                plan_id=free_plan.id,
                credits_remaining=free_plan.monthly_credits,
                credits_used_this_month=0,
                subscription_start=datetime.utcnow(),
                is_active=True
            )
            db.session.add(subscription)
            print(f"   - Assigning free plan to {user.username} ({user.email})")

        db.session.commit()
        print("\n   ✓ Successfully assigned free plans!")

        # Summary
        print("\n3. Summary:")
        total_users = User.query.count()
        total_subscriptions = UserSubscription.query.filter_by(is_active=True).count()

        print(f"   - Total users: {total_users}")
        print(f"   - Active subscriptions: {total_subscriptions}")

        print("\n" + "=" * 50)
        print("✅ Subscription fix completed successfully!")
        print("\nYou can now use the application to generate images.")


def main():
    try:
        fix_subscriptions()
    except Exception as e:
        print(f"❌ Error during fix: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
