"""task assistant: one row per "describe your task" conversation (for the weekly limit)

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-25 06:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0026'
down_revision: Union[str, Sequence[str], None] = '0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'assistant_conversations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('room_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('turns', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_assistant_conversations_room_id', 'assistant_conversations', ['room_id'])
    op.create_index('ix_assistant_conversations_created_at', 'assistant_conversations', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_assistant_conversations_created_at', table_name='assistant_conversations')
    op.drop_index('ix_assistant_conversations_room_id', table_name='assistant_conversations')
    op.drop_table('assistant_conversations')
