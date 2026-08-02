import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel

from app.models._types import coluna_enum


class StatusDocumento(StrEnum):
    PROCESSANDO = "processando"
    PRONTO = "pronto"
    ERRO_PARCIAL = "erro_parcial"


class StatusIngestao(StrEnum):
    PENDENTE = "pendente"
    PROCESSANDO = "processando"
    CONCLUIDA = "concluida"
    ERRO = "erro"


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    slug: str = Field(max_length=64, unique=True, index=True)
    titulo: str = Field(max_length=200)
    area: str = Field(max_length=120)
    descricao: str = Field(default="", max_length=1000)
    icone: str = Field(default="", max_length=16)
    nome_arquivo_original: str = Field(max_length=255)
    mime_type: str = Field(max_length=120)
    tamanho_bytes: int
    sha256: str = Field(max_length=64, index=True)
    status: StatusDocumento = Field(
        default=StatusDocumento.PROCESSANDO,
        sa_column=Column(
            coluna_enum(StatusDocumento, 20),
            nullable=False,
            server_default=StatusDocumento.PROCESSANDO.value,
        ),
    )
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


class DocumentIngestion(SQLModel, table=True):
    """Telemetria da ingestao de um documento em um pipeline. Quatro linhas por documento."""

    __tablename__ = "document_ingestions"

    id: int | None = Field(default=None, primary_key=True)
    document_id: uuid.UUID = Field(foreign_key="documents.id", index=True, ondelete="CASCADE")
    pipeline_id: int = Field(foreign_key="pipelines.id", index=True)
    status: StatusIngestao = Field(
        default=StatusIngestao.PENDENTE,
        sa_column=Column(
            coluna_enum(StatusIngestao, 20),
            nullable=False,
            server_default=StatusIngestao.PENDENTE.value,
        ),
    )
    erro: str | None = Field(default=None, max_length=2000)
    total_caracteres: int = Field(default=0)
    total_chunks: int = Field(default=0)
    tokens_embedding: int = Field(default=0)
    duracao_parsing_ms: int = Field(default=0)
    duracao_chunking_ms: int = Field(default=0)
    duracao_embedding_ms: int = Field(default=0)
    duracao_indexacao_ms: int = Field(default=0)
    duracao_total_ms: int = Field(default=0)
    iniciado_em: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    concluido_em: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
