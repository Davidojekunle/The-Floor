"""calls (C1): instant calls in a room or about a task, who's in them, and the calls notification switch

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-24 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0021'
down_revision: Union[str, Sequence[str], None] = '0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'calls',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('room_id', sa.Uuid(), nullable=False),
        sa.Column('task_id', sa.Uuid(), nullable=True),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('missed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ends_at_planned', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('hard_stop_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('empty_since', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('provider_room', sa.String(length=100), nullable=True),
        sa.Column('external_url', sa.String(length=2000), nullable=True),
        sa.Column('invite_everyone', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('reminded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_calls_room_status', 'calls', ['room_id', 'status'])
    op.create_index('uq_calls_live_room', 'calls', ['room_id'], unique=True,
                    postgresql_where=sa.text("status = 'live' AND task_id IS NULL"),
                    sqlite_where=sa.text("status = 'live' AND task_id IS NULL"))
    op.create_index('uq_calls_live_task', 'calls', ['task_id'], unique=True,
                    postgresql_where=sa.text("status = 'live' AND task_id IS NOT NULL"),
                    sqlite_where=sa.text("status = 'live' AND task_id IS NOT NULL"))

    op.create_table(
        'call_participants',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('call_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('session_id', sa.String(length=100), nullable=False),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('left_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id'),
    )
    op.create_index('ix_call_participants_call_open', 'call_participants', ['call_id', 'left_at'])

    with op.batch_alter_table('notification_settings') as batch:
        batch.add_column(sa.Column('calls', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table('notification_settings') as batch:
        batch.drop_column('calls')
    op.drop_index('ix_call_participants_call_open', table_name='call_participants')
    op.drop_table('call_participants')
    op.drop_index('uq_calls_live_task', table_name='calls')
    op.drop_index('uq_calls_live_room', table_name='calls')
    op.drop_index('ix_calls_room_status', table_name='calls')
    op.drop_table('calls')
