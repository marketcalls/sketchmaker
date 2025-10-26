"""Add credit security constraints to prevent race condition exploits

Revision ID: add_credit_security_constraints
Revises: add_centralized_api_management
Create Date: 2025-01-26

This migration adds critical security constraints to prevent credit bypass attacks:
1. CHECK constraint to prevent negative credits
2. NOT NULL constraints on credit columns
3. Fixes any existing negative credit balances
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_credit_security_constraints'
down_revision = 'add_centralized_api_management'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: Fix any existing negative credits by setting them to 0
    # This ensures the CHECK constraint won't fail on existing data
    op.execute("""
        UPDATE user_subscriptions
        SET credits_remaining = 0
        WHERE credits_remaining < 0
    """)

    op.execute("""
        UPDATE user_subscriptions
        SET credits_used_this_month = 0
        WHERE credits_used_this_month < 0
    """)

    # Step 2: Add NOT NULL constraints to credit columns
    # SQLite doesn't support ALTER COLUMN directly, so we need to handle this differently
    # For SQLite, the constraint is already in the model and will be applied on table recreation
    # For other databases (PostgreSQL, MySQL), we can alter the column
    try:
        # Try to alter column (works for PostgreSQL, MySQL)
        op.alter_column('user_subscriptions', 'credits_remaining',
                       existing_type=sa.Integer(),
                       nullable=False,
                       server_default='0')

        op.alter_column('user_subscriptions', 'credits_used_this_month',
                       existing_type=sa.Integer(),
                       nullable=False,
                       server_default='0')
    except Exception as e:
        # SQLite: constraints will be applied through model definition
        print(f"Note: Column alteration not supported on this database: {e}")
        print("Constraints will be enforced by the ORM model")

    # Step 3: Add CHECK constraint to prevent negative credits
    # This is the critical security fix
    try:
        op.create_check_constraint(
            'check_credits_non_negative',
            'user_subscriptions',
            'credits_remaining >= 0'
        )
    except Exception as e:
        # If constraint already exists or database doesn't support it
        print(f"Note: CHECK constraint may already exist or not supported: {e}")
        print("Constraint is defined in the ORM model")


def downgrade():
    # Remove the CHECK constraint
    try:
        op.drop_constraint('check_credits_non_negative', 'user_subscriptions', type_='check')
    except Exception as e:
        print(f"Note: Constraint removal not supported or doesn't exist: {e}")

    # Revert NOT NULL constraints (make columns nullable again)
    try:
        op.alter_column('user_subscriptions', 'credits_remaining',
                       existing_type=sa.Integer(),
                       nullable=True)

        op.alter_column('user_subscriptions', 'credits_used_this_month',
                       existing_type=sa.Integer(),
                       nullable=True)
    except Exception as e:
        print(f"Note: Column alteration not supported on downgrade: {e}")
