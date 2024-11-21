"""add google auth support

Revision ID: add_google_auth_support
Revises: 
Create Date: 2024-03-21 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_google_auth_support'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Create auth_settings table
    op.create_table('auth_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('regular_auth_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('google_auth_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('google_client_id', sa.String(length=255), nullable=True),
        sa.Column('google_client_secret', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create new user table with google_id column
    op.create_table('user_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('role', sa.String(length=20), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('is_approved', sa.Boolean(), nullable=True),
        sa.Column('selected_provider_id', sa.Integer(), nullable=True),
        sa.Column('selected_model_id', sa.Integer(), nullable=True),
        sa.Column('openai_api_key', sa.String(length=255), nullable=True),
        sa.Column('anthropic_api_key', sa.String(length=255), nullable=True),
        sa.Column('gemini_api_key', sa.String(length=255), nullable=True),
        sa.Column('groq_api_key', sa.String(length=255), nullable=True),
        sa.Column('fal_key', sa.String(length=255), nullable=True),
        sa.Column('google_id', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('google_id'),
        sa.UniqueConstraint('username'),
        sa.ForeignKeyConstraint(['selected_provider_id'], ['api_provider.id']),
        sa.ForeignKeyConstraint(['selected_model_id'], ['ai_model.id'])
    )

    # Copy data from old table to new table
    op.execute("""
        INSERT INTO user_new (
            id, username, email, password_hash, created_at, role, is_active, is_approved,
            selected_provider_id, selected_model_id, openai_api_key, anthropic_api_key,
            gemini_api_key, groq_api_key, fal_key
        )
        SELECT 
            id, username, email, password_hash, created_at, role, is_active, is_approved,
            selected_provider_id, selected_model_id, openai_api_key, anthropic_api_key,
            gemini_api_key, groq_api_key, fal_key
        FROM user
    """)

    # Drop old table and rename new table
    op.drop_table('user')
    op.rename_table('user_new', 'user')

    # Insert default auth settings
    op.execute("""
        INSERT INTO auth_settings (regular_auth_enabled, google_auth_enabled, created_at, updated_at)
        SELECT TRUE, FALSE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (SELECT 1 FROM auth_settings LIMIT 1)
    """)

def downgrade():
    # Create user table without google_id
    op.create_table('user_old',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('role', sa.String(length=20), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('is_approved', sa.Boolean(), nullable=True),
        sa.Column('selected_provider_id', sa.Integer(), nullable=True),
        sa.Column('selected_model_id', sa.Integer(), nullable=True),
        sa.Column('openai_api_key', sa.String(length=255), nullable=True),
        sa.Column('anthropic_api_key', sa.String(length=255), nullable=True),
        sa.Column('gemini_api_key', sa.String(length=255), nullable=True),
        sa.Column('groq_api_key', sa.String(length=255), nullable=True),
        sa.Column('fal_key', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('username'),
        sa.ForeignKeyConstraint(['selected_provider_id'], ['api_provider.id']),
        sa.ForeignKeyConstraint(['selected_model_id'], ['ai_model.id'])
    )

    # Copy data back
    op.execute("""
        INSERT INTO user_old (
            id, username, email, password_hash, created_at, role, is_active, is_approved,
            selected_provider_id, selected_model_id, openai_api_key, anthropic_api_key,
            gemini_api_key, groq_api_key, fal_key
        )
        SELECT 
            id, username, email, password_hash, created_at, role, is_active, is_approved,
            selected_provider_id, selected_model_id, openai_api_key, anthropic_api_key,
            gemini_api_key, groq_api_key, fal_key
        FROM user
    """)

    # Drop new table and rename old table
    op.drop_table('user')
    op.rename_table('user_old', 'user')

    # Drop auth_settings table
    op.drop_table('auth_settings')
