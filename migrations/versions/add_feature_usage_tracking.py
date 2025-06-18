"""Add feature usage tracking

Revision ID: add_feature_usage_tracking
Revises: 
Create Date: 2025-06-18 01:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_feature_usage_tracking'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Add feature usage tracking columns to user_subscriptions table
    with op.batch_alter_table('user_subscriptions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('images_used_this_month', sa.Integer(), default=0))
        batch_op.add_column(sa.Column('banners_used_this_month', sa.Integer(), default=0))
        batch_op.add_column(sa.Column('magix_used_this_month', sa.Integer(), default=0))
        batch_op.add_column(sa.Column('lora_training_used_this_month', sa.Integer(), default=0))

def downgrade():
    # Remove feature usage tracking columns from user_subscriptions table
    with op.batch_alter_table('user_subscriptions', schema=None) as batch_op:
        batch_op.drop_column('lora_training_used_this_month')
        batch_op.drop_column('magix_used_this_month')
        batch_op.drop_column('banners_used_this_month')
        batch_op.drop_column('images_used_this_month')