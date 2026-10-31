import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, Index, text
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel

from app.models._types import coluna_enum


class StatusEstudo(StrEnum):
    ABERTO = "aberto"
    ENCERRADO = "encerrado"


class Study(SQLModel, table=True):
    """Coleta delimitada (piloto, principal). Sessoes e rodadas pertencem a um estudo so."""

    __tablename__ = "studies"
    # O indice parcial impoe no banco a regra de um unico estudo aberto por vez.
    __table_args__ = (
        Index(
            "uq_um_estudo_aberto",
            "status",
            unique=True,
            postgresql_where=text("status = 'aberto'"),
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    nome: str = Field(max_length=120)
    descricao: str = Field(default="", max_length=1000)
    status: StatusEstudo = Field(
        default=StatusEstudo.ABERTO,
        sa_column=Column(coluna_enum(StatusEstudo, 16), nullable=False),
    )
    iniciado_em: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    encerrado_em: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
