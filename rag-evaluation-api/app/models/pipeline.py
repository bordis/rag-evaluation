from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel

from app.models._types import coluna_enum


class ParserType(StrEnum):
    RAW = "raw"
    DOCLING = "docling"


class Pipeline(SQLModel, table=True):
    __tablename__ = "pipelines"

    id: int | None = Field(default=None, primary_key=True)
    codigo: str = Field(max_length=32, unique=True, index=True)
    nome: str = Field(max_length=120)
    descricao: str = Field(default="", max_length=500)
    parser: ParserType = Field(sa_column=Column(coluna_enum(ParserType, 16), nullable=False))
    collection_name: str = Field(max_length=64)
    ativo: bool = Field(default=True)
    config: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    criado_em: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    atualizado_em: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        ),
    )
