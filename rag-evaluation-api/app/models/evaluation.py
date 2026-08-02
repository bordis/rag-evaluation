import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel, UniqueConstraint


class Familiaridade(StrEnum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"


class TempoExperiencia(StrEnum):
    ATE_2_ANOS = "ate-2-anos"
    DE_2_A_5_ANOS = "2-5-anos"
    DE_5_A_10_ANOS = "5-10-anos"
    MAIS_10_ANOS = "mais-10-anos"


class EvaluationSession(SQLModel, table=True):
    """Avaliador anonimo. O perfil e inteiramente opcional."""

    __tablename__ = "evaluation_sessions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    area_atuacao: str | None = Field(default=None, max_length=120)
    familiaridade: Familiaridade | None = Field(
        default=None,
        sa_column=Column(SAEnum(Familiaridade, native_enum=False, length=10), nullable=True),
    )
    tempo_experiencia: TempoExperiencia | None = Field(
        default=None,
        sa_column=Column(SAEnum(TempoExperiencia, native_enum=False, length=16), nullable=True),
    )
    criado_em: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


class QuestionRound(SQLModel, table=True):
    __tablename__ = "question_rounds"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(
        foreign_key="evaluation_sessions.id", index=True, ondelete="CASCADE"
    )
    document_id: uuid.UUID = Field(foreign_key="documents.id", index=True, ondelete="CASCADE")
    pergunta: str = Field(max_length=500)
    escolha_answer_id: uuid.UUID | None = Field(default=None)
    criado_em: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    escolhido_em: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class PipelineAnswer(SQLModel, table=True):
    """Resposta de um pipeline numa rodada. O rotulo cego e o que o avaliador ve."""

    __tablename__ = "pipeline_answers"
    __table_args__ = (
        UniqueConstraint("round_id", "rotulo_cego", name="uq_rodada_rotulo"),
        UniqueConstraint("round_id", "pipeline_id", name="uq_rodada_pipeline"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    round_id: uuid.UUID = Field(
        foreign_key="question_rounds.id", index=True, ondelete="CASCADE"
    )
    pipeline_id: int = Field(foreign_key="pipelines.id", index=True)
    rotulo_cego: str = Field(max_length=1)
    texto: str
