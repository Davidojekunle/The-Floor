"""admin change log: who changed a site switch, who made or removed an admin

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-25 06:20:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0027'
down_revision: Union[str, Sequence[str], None] = '0026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'admin_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actor_id', sa.Uuid(), nullable=True),
        sa.Column('actor_name', sa.String(length=100), nullable=False),
        sa.Column('action', sa.String(length=40), nullable=False),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_admin_events_created_at', 'admin_events', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_admin_events_created_at', table_name='admin_events')
    op.drop_table('admin_events')
