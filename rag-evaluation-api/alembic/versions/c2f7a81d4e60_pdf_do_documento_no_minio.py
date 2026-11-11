"""pdf do documento no minio

Revision ID: c2f7a81d4e60
Revises: 48cb2947be49
Create Date: 2026-11-01 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c2f7a81d4e60'
down_revision: Union[str, Sequence[str], None] = '48cb2947be49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Nula nos documentos ja enviados: o arquivo deles nao foi guardado."""
    op.add_column('documents', sa.Column('arquivo_chave', sa.String(length=128), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'arquivo_chave')
