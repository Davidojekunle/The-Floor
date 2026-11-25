"""signup source: which ?ref= link brought someone in (counted on the admin page)

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-25 05:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0025'
down_revision: Union[str, Sequence[str], None] = '0024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('signup_source', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'signup_source')
