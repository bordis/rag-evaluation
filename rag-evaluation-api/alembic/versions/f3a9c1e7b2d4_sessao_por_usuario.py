"""sessao por usuario

Com o SSO, a sessao do avaliador fica ligada ao `sub` do Keycloak: uma por login e por estudo.
Sessoes anteriores, anonimas, ficam com nulo.

Revision ID: f3a9c1e7b2d4
Revises: e5b8d0a3c7f1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'f3a9c1e7b2d4'
down_revision: Union[str, Sequence[str], None] = 'e5b8d0a3c7f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'evaluation_sessions',
        sa.Column('usuario_sub', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
    )
    op.create_unique_constraint(
        'uq_estudo_usuario', 'evaluation_sessions', ['study_id', 'usuario_sub']
    )


def downgrade() -> None:
    op.drop_constraint('uq_estudo_usuario', 'evaluation_sessions', type_='unique')
    op.drop_column('evaluation_sessions', 'usuario_sub')
