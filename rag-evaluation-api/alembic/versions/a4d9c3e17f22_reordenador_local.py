"""reordenador local: menos candidatos e descricao dos pipelines

Revision ID: a4d9c3e17f22
Revises: 7c1e2f4a9b10
Create Date: 2026-10-30 19:00:00

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a4d9c3e17f22'
down_revision: Union[str, Sequence[str], None] = '7c1e2f4a9b10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Semeadura nunca sobrescreve config, entao os pipelines ja criados migram aqui."""
    op.execute(
        """
        UPDATE pipelines
        SET config = config || jsonb_build_object('candidatos', 20)
        WHERE config ? 'candidatos'
        """
    )
    op.execute("UPDATE pipelines SET descricao = replace(descricao, 'reordenacao Jev', 'reordenacao')")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        UPDATE pipelines
        SET config = config || jsonb_build_object('candidatos', 30)
        WHERE config ? 'candidatos'
        """
    )
