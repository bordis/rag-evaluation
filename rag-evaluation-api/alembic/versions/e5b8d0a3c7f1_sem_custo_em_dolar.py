"""sem custo em dolar

Os modelos rodam em servicos internos: o custo do estudo se mede em tempo e tokens.

Revision ID: e5b8d0a3c7f1
Revises: c2f7a81d4e60
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5b8d0a3c7f1'
down_revision: Union[str, Sequence[str], None] = 'c2f7a81d4e60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('answer_stage_metrics', 'custo_usd')


def downgrade() -> None:
    op.add_column('answer_stage_metrics', sa.Column('custo_usd', sa.Float(), nullable=True))
