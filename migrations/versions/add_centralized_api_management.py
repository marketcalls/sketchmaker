"""Add centralized API management

Revision ID: add_centralized_api_management
Revises: add_subscription_system
Create Date: 2025-01-17

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_centralized_api_management'
down_revision = 'add_subscription_system'
branch_labels = None
depends_on = None


def upgrade():
    # Create api_settings table
    op.create_table('api_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('openai_api_key', sa.Text(), nullable=True),
        sa.Column('anthropic_api_key', sa.Text(), nullable=True),
        sa.Column('gemini_api_key', sa.Text(), nullable=True),
        sa.Column('groq_api_key', sa.Text(), nullable=True),
        sa.Column('fal_key', sa.Text(), nullable=True),
        sa.Column('default_provider_id', sa.Integer(), nullable=True),
        sa.Column('default_model_id', sa.Integer(), nullable=True),
        sa.Column('encryption_key', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['default_model_id'], ['ai_model.id'], ),
        sa.ForeignKeyConstraint(['default_provider_id'], ['api_provider.id'], ),
        sa.ForeignKeyConstraint(['updated_by_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('api_settings')