"""init

Revision ID: 0001_init
Revises:
Create Date: 2026-03-28 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0001_init'
down_revision = None
branch_labels = None
depends_on = None

severity_enum = postgresql.ENUM('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NOT_RESCUE', name='severity_level', create_type=False)
accessibility_enum = postgresql.ENUM('EASY', 'MODERATE', 'HARD', name='accessibility_level', create_type=False)
geocode_enum = postgresql.ENUM('pending', 'success', 'failed', name='geocode_status', create_type=False)
rescue_enum = postgresql.ENUM('waiting', 'dispatched', 'rescued', 'false_alarm', name='rescue_status', create_type=False)
pipeline_job_enum = postgresql.ENUM(
    'pending', 'scraping', 'classifying', 'extracting', 'deduplicating', 'done', 'failed', name='pipeline_job_status', create_type=False
)
sync_status_enum = postgresql.ENUM('live', 'lagging', 'paused', name='sync_status', create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    severity_enum.create(bind, checkfirst=True)
    accessibility_enum.create(bind, checkfirst=True)
    geocode_enum.create(bind, checkfirst=True)
    rescue_enum.create(bind, checkfirst=True)
    pipeline_job_enum.create(bind, checkfirst=True)
    sync_status_enum.create(bind, checkfirst=True)

    op.create_table(
        'rescue_cases',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('source_post_id', sa.String(length=255), nullable=False),
        sa.Column('raw_comment', sa.Text(), nullable=False),
        sa.Column('commenter_name', sa.String(length=255), nullable=True),
        sa.Column('severity', severity_enum, nullable=False),
        sa.Column('location_description', sa.Text(), nullable=True),
        sa.Column('normalized_address', sa.String(length=500), nullable=True),
        sa.Column('district', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.Column('num_people', sa.Integer(), nullable=True),
        sa.Column('vulnerable_groups', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('accessibility', accessibility_enum, nullable=True),
        sa.Column('waiting_hours', sa.Float(), nullable=True),
        sa.Column('phone', sa.String(length=32), nullable=True),
        sa.Column('ai_confidence', sa.Float(), nullable=True),
        sa.Column('llm_confidence', sa.Float(), nullable=True),
        sa.Column('geocode_status', geocode_enum, nullable=False, server_default='pending'),
        sa.Column('rescue_status', rescue_enum, nullable=False, server_default='waiting'),
        sa.Column('current_score', sa.Float(), nullable=True),
        sa.Column('current_rank', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index(op.f('ix_rescue_cases_source_post_id'), 'rescue_cases', ['source_post_id'], unique=False)

    op.create_table(
        'pipeline_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('post_url', sa.String(length=1024), nullable=False),
        sa.Column('post_id', sa.String(length=255), nullable=True),
        sa.Column('status', pipeline_job_enum, nullable=False, server_default='pending'),
        sa.Column('progress', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('current_stage', sa.String(length=500), nullable=True),
        sa.Column('total_comments', sa.Integer(), nullable=True),
        sa.Column('classified_count', sa.Integer(), nullable=True),
        sa.Column('extracted_count', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    op.create_table(
        'monitored_posts',
        sa.Column('id', sa.String(length=255), primary_key=True, nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('source_name', sa.String(length=255), nullable=False, server_default='Facebook'),
        sa.Column('sync_status', sync_status_enum, nullable=False, server_default='live'),
        sa.Column('comment_volume', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('district_scope', postgresql.ARRAY(sa.String()), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('monitored_posts')
    op.drop_table('pipeline_jobs')
    op.drop_index(op.f('ix_rescue_cases_source_post_id'), table_name='rescue_cases')
    op.drop_table('rescue_cases')

    bind = op.get_bind()
    sync_status_enum.drop(bind, checkfirst=True)
    pipeline_job_enum.drop(bind, checkfirst=True)
    rescue_enum.drop(bind, checkfirst=True)
    geocode_enum.drop(bind, checkfirst=True)
    accessibility_enum.drop(bind, checkfirst=True)
    severity_enum.drop(bind, checkfirst=True)
