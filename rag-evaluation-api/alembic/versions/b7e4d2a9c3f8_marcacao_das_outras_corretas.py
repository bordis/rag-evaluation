"""marcacao das outras corretas

Segundo passo da rodada: depois de escolher a vencedora, o avaliador marca quais das outras
respostas tambem estao corretas. Alimenta a taxa de correcao; a analise principal nao muda.

Revision ID: b7e4d2a9c3f8
Revises: f3a9c1e7b2d4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7e4d2a9c3f8'
down_revision: Union[str, Sequence[str], None] = 'f3a9c1e7b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pipeline_answers', sa.Column('tambem_correta', sa.Boolean(), nullable=True))
    op.add_column(
        'question_rounds', sa.Column('marcado_em', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column('question_rounds', sa.Column('tempo_marcacao_ms', sa.Integer(), nullable=True))
    op.add_column(
        'question_rounds', sa.Column('tempo_marcacao_oculto_ms', sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('question_rounds', 'tempo_marcacao_oculto_ms')
    op.drop_column('question_rounds', 'tempo_marcacao_ms')
    op.drop_column('question_rounds', 'marcado_em')
    op.drop_column('pipeline_answers', 'tambem_correta')
