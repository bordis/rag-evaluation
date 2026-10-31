import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel

from app.models._types import coluna_enum


class EtapaPipeline(StrEnum):
    HYDE = "hyde"
    EMBEDDING_QUERY = "embedding_query"
    RETRIEVAL = "retrieval"
    RERANKING = "reranking"
    WINDOW_EXPANSION = "window_expansion"
    GENERATION = "generation"


class EtapaChunk(StrEnum):
    """Em que ponto do pipeline a lista foi observada; separa erro de recuperacao e de geracao."""

    DENSO = "denso"
    ESPARSO = "esparso"
    FUSAO = "fusao"
    REORDENACAO = "reordenacao"
    CONTEXTO_FINAL = "contexto_final"


class AnswerStageMetric(SQLModel, table=True):
    """Uma linha por etapa executada. Pipelines 1 e 2 geram 3; os 3 e 4, ate 6."""

    __tablename__ = "answer_stage_metrics"

    id: int | None = Field(default=None, primary_key=True)
    answer_id: uuid.UUID = Field(foreign_key="pipeline_answers.id", index=True, ondelete="CASCADE")
    etapa: EtapaPipeline = Field(sa_column=Column(coluna_enum(EtapaPipeline, 24), nullable=False))
    ordem: int
    duracao_ms: int
    tokens_prompt: int | None = Field(default=None)
    tokens_completion: int | None = Field(default=None)
    tokens_total: int | None = Field(default=None)
    modelo: str | None = Field(default=None, max_length=64)
    detalhes: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))


class RetrievedChunk(SQLModel, table=True):
    """O que o pipeline recuperou. Permite distinguir falha de retrieval de falha de geracao."""

    __tablename__ = "retrieved_chunks"

    id: int | None = Field(default=None, primary_key=True)
    answer_id: uuid.UUID = Field(foreign_key="pipeline_answers.id", index=True, ondelete="CASCADE")
    # O auto_id do Milvus usa os 64 bits inteiros.
    milvus_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    chunk_index: int
    score_denso: float | None = Field(default=None)
    score_esparso: float | None = Field(default=None)
    score_final: float
    etapa: EtapaChunk = Field(sa_column=Column(coluna_enum(EtapaChunk, 16), nullable=False))
    posicao: int
    # So no contexto final: ancora, vizinho, complemento ou busca.
    origem: str | None = Field(default=None, max_length=16)
    texto: str


class RagasScore(SQLModel, table=True):
    """Notas do RAGAS para uma resposta. Calculadas sob demanda, fora do fluxo do avaliador."""

    __tablename__ = "ragas_scores"

    answer_id: uuid.UUID = Field(
        foreign_key="pipeline_answers.id", primary_key=True, ondelete="CASCADE"
    )
    fidelidade: float | None = Field(default=None)
    relevancia_resposta: float | None = Field(default=None)
    precisao_contexto: float | None = Field(default=None)
    media: float | None = Field(default=None)
    modelo: str = Field(max_length=64)
    duracao_ms: int = Field(default=0)
    erro: str | None = Field(default=None, max_length=2000)
    criado_em: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
