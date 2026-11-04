"""Faceless Studio: series, projects, script versions and step runs.

Safe on existing data: it only adds new tables and one nullable column on
faceless_activity, added in place. faceless_character is not touched.

Revision ID: 0003_faceless_studio
Revises: 0002_latest_models
Create Date: 2026-11-04 05:47:51.928334

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003_faceless_studio'
down_revision: Union[str, Sequence[str], None] = '0002_latest_models'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('faceless_series',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('logline', sa.Text(), nullable=True),
    sa.Column('template_id', sa.String(length=60), nullable=True),
    sa.Column('style', sa.String(length=60), nullable=True),
    sa.Column('tone', sa.String(length=200), nullable=True),
    sa.Column('cast_ids', sa.JSON(), nullable=True),
    sa.Column('world_notes', sa.Text(), nullable=True),
    sa.Column('rules', sa.JSON(), nullable=True),
    sa.Column('episode_memory', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_faceless_series_user_id_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_faceless_series')),
    sqlite_autoincrement=True
    )
    with op.batch_alter_table('faceless_series', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_faceless_series_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_faceless_series_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_faceless_series_user_id'), ['user_id'], unique=False)

    op.create_table('faceless_project',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('series_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('idea', sa.Text(), nullable=True),
    sa.Column('template_id', sa.String(length=60), nullable=False),
    sa.Column('aspect', sa.String(length=10), nullable=False),
    sa.Column('length_seconds', sa.Integer(), nullable=False),
    sa.Column('language', sa.String(length=10), nullable=False),
    sa.Column('style', sa.String(length=60), nullable=True),
    sa.Column('narrator_voice', sa.String(length=60), nullable=True),
    sa.Column('voice_settings', sa.JSON(), nullable=True),
    sa.Column('caption_preset', sa.String(length=30), nullable=True),
    sa.Column('music_mood', sa.String(length=40), nullable=True),
    sa.Column('cast_ids', sa.JSON(), nullable=True),
    sa.Column('facts', sa.JSON(), nullable=True),
    sa.Column('settings', sa.JSON(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('script', sa.JSON(), nullable=True),
    sa.Column('script_version', sa.Integer(), nullable=False),
    sa.Column('scene_assets', sa.JSON(), nullable=True),
    sa.Column('music', sa.JSON(), nullable=True),
    sa.Column('render', sa.JSON(), nullable=True),
    sa.Column('output_video_id', sa.Integer(), nullable=True),
    sa.Column('packaging', sa.JSON(), nullable=True),
    sa.Column('thumbnails', sa.JSON(), nullable=True),
    sa.Column('compliance', sa.JSON(), nullable=True),
    sa.Column('originality', sa.JSON(), nullable=True),
    sa.Column('usd_by_step', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['series_id'], ['faceless_series.id'], name=op.f('fk_faceless_project_series_id_faceless_series'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_faceless_project_user_id_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_faceless_project')),
    sqlite_autoincrement=True
    )
    with op.batch_alter_table('faceless_project', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_faceless_project_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_faceless_project_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_faceless_project_series_id'), ['series_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_faceless_project_user_id'), ['user_id'], unique=False)

    op.create_table('faceless_script_version',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('script', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['faceless_project.id'], name=op.f('fk_faceless_script_version_project_id_faceless_project'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_faceless_script_version_user_id_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_faceless_script_version')),
    sa.UniqueConstraint('project_id', 'version', name='uq_faceless_script_version'),
    sqlite_autoincrement=True
    )
    with op.batch_alter_table('faceless_script_version', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_faceless_script_version_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_faceless_script_version_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_faceless_script_version_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_faceless_script_version_user_id'), ['user_id'], unique=False)

    op.create_table('faceless_step_run',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=True),
    sa.Column('character_id', sa.Integer(), nullable=True),
    sa.Column('step', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('idempotency_key', sa.String(length=80), nullable=False),
    sa.Column('scene_ids', sa.JSON(), nullable=True),
    sa.Column('options', sa.JSON(), nullable=True),
    sa.Column('quote', sa.JSON(), nullable=True),
    sa.Column('items', sa.JSON(), nullable=True),
    sa.Column('progress', sa.Integer(), nullable=True),
    sa.Column('estimated_usd', sa.Float(), nullable=False),
    sa.Column('usd_spent', sa.Float(), nullable=False),
    sa.Column('cancel_requested', sa.Boolean(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('heartbeat_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['character_id'], ['faceless_character.id'], name=op.f('fk_faceless_step_run_character_id_faceless_character'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['faceless_project.id'], name=op.f('fk_faceless_step_run_project_id_faceless_project'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_faceless_step_run_user_id_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_faceless_step_run')),
    sa.UniqueConstraint('user_id', 'idempotency_key', name='uq_faceless_step_run_idem'),
    sqlite_autoincrement=True
    )
    with op.batch_alter_table('faceless_step_run', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_faceless_step_run_character_id'), ['character_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_faceless_step_run_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_faceless_step_run_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_faceless_step_run_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_faceless_step_run_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_faceless_step_run_step'), ['step'], unique=False)
        batch_op.create_index(batch_op.f('ix_faceless_step_run_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('faceless_activity', schema=None) as batch_op:
        batch_op.add_column(sa.Column('project_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_faceless_activity_project_id'), ['project_id'], unique=False)



def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('faceless_activity', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_faceless_activity_project_id'))
        batch_op.drop_column('project_id')

    with op.batch_alter_table('faceless_step_run', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_faceless_step_run_user_id'))
        batch_op.drop_index(batch_op.f('ix_faceless_step_run_step'))
        batch_op.drop_index(batch_op.f('ix_faceless_step_run_status'))
        batch_op.drop_index(batch_op.f('ix_faceless_step_run_project_id'))
        batch_op.drop_index(batch_op.f('ix_faceless_step_run_id'))
        batch_op.drop_index(batch_op.f('ix_faceless_step_run_created_at'))
        batch_op.drop_index(batch_op.f('ix_faceless_step_run_character_id'))

    op.drop_table('faceless_step_run')
    with op.batch_alter_table('faceless_script_version', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_faceless_script_version_user_id'))
        batch_op.drop_index(batch_op.f('ix_faceless_script_version_project_id'))
        batch_op.drop_index(batch_op.f('ix_faceless_script_version_id'))
        batch_op.drop_index(batch_op.f('ix_faceless_script_version_created_at'))

    op.drop_table('faceless_script_version')
    with op.batch_alter_table('faceless_project', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_faceless_project_user_id'))
        batch_op.drop_index(batch_op.f('ix_faceless_project_series_id'))
        batch_op.drop_index(batch_op.f('ix_faceless_project_id'))
        batch_op.drop_index(batch_op.f('ix_faceless_project_created_at'))

    op.drop_table('faceless_project')
    with op.batch_alter_table('faceless_series', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_faceless_series_user_id'))
        batch_op.drop_index(batch_op.f('ix_faceless_series_id'))
        batch_op.drop_index(batch_op.f('ix_faceless_series_created_at'))

    op.drop_table('faceless_series')
