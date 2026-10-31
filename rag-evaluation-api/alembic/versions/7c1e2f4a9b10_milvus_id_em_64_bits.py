"""milvus_id em 64 bits

Revision ID: 7c1e2f4a9b10
Revises: 3bbef0bf5d2b
Create Date: 2026-10-30 18:05:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7c1e2f4a9b10'
down_revision: Union[str, Sequence[str], None] = '3bbef0bf5d2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('retrieved_chunks', 'milvus_id', type_=sa.BigInteger(), existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('retrieved_chunks', 'milvus_id', type_=sa.Integer(), existing_nullable=False)
