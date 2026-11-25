"""private DMs between people who share a room, and blocks

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-25 08:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0028'
down_revision: Union[str, Sequence[str], None] = '0027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'direct_threads',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_low_id', sa.Uuid(), nullable=False),
        sa.Column('user_high_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('low_read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('high_read_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_low_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_high_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_low_id', 'user_high_id', name='uq_direct_threads_pair'),
    )
    op.create_index('ix_direct_threads_user_low_id', 'direct_threads', ['user_low_id'])
    op.create_index('ix_direct_threads_user_high_id', 'direct_threads', ['user_high_id'])
    op.create_table(
        'direct_messages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('thread_id', sa.Uuid(), nullable=False),
        sa.Column('sender_id', sa.Uuid(), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['thread_id'], ['direct_threads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sender_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_direct_messages_thread_created', 'direct_messages', ['thread_id', 'created_at'])
    op.create_table(
        'user_blocks',
        sa.Column('blocker_id', sa.Uuid(), nullable=False),
        sa.Column('blocked_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['blocker_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['blocked_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('blocker_id', 'blocked_id'),
    )


def downgrade() -> None:
    op.drop_table('user_blocks')
    op.drop_index('ix_direct_messages_thread_created', table_name='direct_messages')
    op.drop_table('direct_messages')
    op.drop_index('ix_direct_threads_user_high_id', table_name='direct_threads')
    op.drop_index('ix_direct_threads_user_low_id', table_name='direct_threads')
    op.drop_table('direct_threads')
