"""Rename banners to explainers

Revision ID: rename_banners_to_explainers
Revises: add_new_litellm_providers
Create Date: 2025-12-10 18:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'rename_banners_to_explainers'
down_revision = 'add_new_litellm_providers'
branch_labels = None
depends_on = None

def upgrade():
    # Rename credit_cost_banners to credit_cost_explainers in system_settings table
    with op.batch_alter_table('system_settings', schema=None) as batch_op:
        batch_op.alter_column('credit_cost_banners', new_column_name='credit_cost_explainers')

def downgrade():
    # Rename credit_cost_explainers back to credit_cost_banners
    with op.batch_alter_table('system_settings', schema=None) as batch_op:
        batch_op.alter_column('credit_cost_explainers', new_column_name='credit_cost_banners')
