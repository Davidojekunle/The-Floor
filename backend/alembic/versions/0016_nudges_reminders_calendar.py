"""nudges, automatic reminders and calendar feeds

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-19 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0016'
down_revision: Union[str, Sequence[str], None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('stages') as batch:
        batch.add_column(sa.Column('status_since', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
        batch.add_column(sa.Column('last_nudged_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('last_nudged_by', sa.Uuid(), nullable=True))
        batch.add_column(sa.Column('nudge_kind', sa.String(length=10), nullable=True))
        batch.add_column(sa.Column('nudge_note', sa.String(length=200), nullable=True))
        batch.add_column(sa.Column('nudge_open', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column('reminded_soon_for', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('reminded_overdue_for', sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key('fk_stages_last_nudged_by', 'users', ['last_nudged_by'], ['id'], ondelete='SET NULL')
    op.create_table('calendar_feeds',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('token', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('room_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token')
    )
    op.create_index('ix_calendar_feeds_user_id', 'calendar_feeds', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_calendar_feeds_user_id', table_name='calendar_feeds')
    op.drop_table('calendar_feeds')
    with op.batch_alter_table('stages') as batch:
        batch.drop_constraint('fk_stages_last_nudged_by', type_='foreignkey')
        for col in ('reminded_overdue_for', 'reminded_soon_for', 'nudge_open', 'nudge_note', 'nudge_kind',
                    'last_nudged_by', 'last_nudged_at', 'status_since'):
            batch.drop_column(col)
