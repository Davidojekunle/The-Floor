"""stage results: a link to the finished work

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-20 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0018'
down_revision: Union[str, Sequence[str], None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('stages') as batch:
        batch.add_column(sa.Column('result_url', sa.String(length=2000), nullable=True))
        batch.add_column(sa.Column('result_note', sa.String(length=300), nullable=True))
        batch.add_column(sa.Column('result_by', sa.Uuid(), nullable=True))
        batch.add_column(sa.Column('result_at', sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key('fk_stages_result_by', 'users', ['result_by'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    with op.batch_alter_table('stages') as batch:
        batch.drop_constraint('fk_stages_result_by', type_='foreignkey')
        batch.drop_column('result_at')
        batch.drop_column('result_by')
        batch.drop_column('result_note')
        batch.drop_column('result_url')
