"""Add new LiteLLM provider API keys (xAI, Cerebras, OpenRouter)

Revision ID: add_new_litellm_providers
Revises: add_feature_usage_tracking
Create Date: 2025-12-10

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_new_litellm_providers'
down_revision = 'add_feature_usage_tracking'
branch_labels = None
depends_on = None


def upgrade():
    # Add new provider API key columns to api_settings table
    with op.batch_alter_table('api_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('xai_api_key', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('cerebras_api_key', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('openrouter_api_key', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('api_settings', schema=None) as batch_op:
        batch_op.drop_column('openrouter_api_key')
        batch_op.drop_column('cerebras_api_key')
        batch_op.drop_column('xai_api_key')
