"""message replies

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-19 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0015'
down_revision: Union[str, Sequence[str], None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('messages') as batch:
        batch.add_column(sa.Column('reply_to_id', sa.Uuid(), nullable=True))
        batch.create_foreign_key('fk_messages_reply_to_id', 'messages', ['reply_to_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    with op.batch_alter_table('messages') as batch:
        batch.drop_constraint('fk_messages_reply_to_id', type_='foreignkey')
        batch.drop_column('reply_to_id')
