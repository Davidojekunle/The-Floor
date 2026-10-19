"""chat mentions and message notification switches

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-19 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('messages', sa.Column('mentions', sa.JSON(), nullable=True))
    # existing rows get the defaults: mentions on, every-message pushes off
    op.add_column('notification_settings', sa.Column('mentions', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('notification_settings', sa.Column('all_messages', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('notification_settings', 'all_messages')
    op.drop_column('notification_settings', 'mentions')
    op.drop_column('messages', 'mentions')
