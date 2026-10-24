"""meetings (C2): repeating series, invites, calendar files on emails; one live INSTANT call per room or task

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-24 14:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0022'
down_revision: Union[str, Sequence[str], None] = '0021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _live_indexes(where_room: str, where_task: str) -> None:
    op.create_index('uq_calls_live_room', 'calls', ['room_id'], unique=True,
                    postgresql_where=sa.text(where_room), sqlite_where=sa.text(where_room))
    op.create_index('uq_calls_live_task', 'calls', ['task_id'], unique=True,
                    postgresql_where=sa.text(where_task), sqlite_where=sa.text(where_task))


def upgrade() -> None:
    with op.batch_alter_table('calls') as batch:
        batch.add_column(sa.Column('series_id', sa.Uuid(), nullable=True))
        batch.add_column(sa.Column('ics_sequence', sa.Integer(), nullable=False, server_default='0'))
    op.create_index('ix_calls_series', 'calls', ['series_id'])
    op.create_index('ix_calls_starts_at', 'calls', ['starts_at'])
    # a meeting may go live beside an instant call: the one-at-a-time rule is for instant calls
    op.drop_index('uq_calls_live_room', table_name='calls')
    op.drop_index('uq_calls_live_task', table_name='calls')
    _live_indexes("status = 'live' AND kind = 'instant' AND task_id IS NULL",
                  "status = 'live' AND kind = 'instant' AND task_id IS NOT NULL")

    op.create_table(
        'call_invites',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('call_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('tag_id', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_call_invites_call', 'call_invites', ['call_id'])

    with op.batch_alter_table('outbox_emails') as batch:
        batch.add_column(sa.Column('attachments', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('outbox_emails') as batch:
        batch.drop_column('attachments')
    op.drop_index('ix_call_invites_call', table_name='call_invites')
    op.drop_table('call_invites')
    op.drop_index('uq_calls_live_room', table_name='calls')
    op.drop_index('uq_calls_live_task', table_name='calls')
    _live_indexes("status = 'live' AND task_id IS NULL", "status = 'live' AND task_id IS NOT NULL")
    op.drop_index('ix_calls_starts_at', table_name='calls')
    op.drop_index('ix_calls_series', table_name='calls')
    with op.batch_alter_table('calls') as batch:
        batch.drop_column('ics_sequence')
        batch.drop_column('series_id')
