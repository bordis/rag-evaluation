import uuid
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models._types import coluna_enum


class EtapaPipeline(StrEnum):
    QUERY_REWRITING = "query_rewriting"
    EMBEDDING_QUERY = "embedding_query"
    RETRIEVAL = "retrieval"
    RERANKING = "reranking"
    WINDOW_EXPANSION = "window_expansion"
    GENERATION = "generation"


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
    milvus_id: int
    chunk_index: int
    score_denso: float | None = Field(default=None)
    score_esparso: float | None = Field(default=None)
    score_final: float
    posicao_final: int
    texto: str
