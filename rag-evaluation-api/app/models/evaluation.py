import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel, UniqueConstraint


class EvaluationSession(SQLModel, table=True):
    """Avaliador anonimo em um estudo. TODO: identificar por login entre sessoes (decisao 16)."""

    __tablename__ = "evaluation_sessions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    study_id: uuid.UUID = Field(foreign_key="studies.id", index=True, ondelete="CASCADE")
    termo_versao: str = Field(max_length=32)
    aceito_em: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
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
    # Posicao no ciclo (sessao + documento). Coluna explicita: derivar de `criado_em` e fragil.
    ordem: int
    # Decidida quando `escolhido_em` esta preenchido: com a resposta, ou com `nenhuma_correta`.
    escolha_answer_id: uuid.UUID | None = Field(default=None)
    nenhuma_correta: bool = Field(default=False)
    # Medidos no navegador. Total: do fim da rodada anterior (ou da abertura) ate a escolha.
    tempo_total_ms: int | None = Field(default=None)
    tempo_geracao_ms: int | None = Field(default=None)
    tempo_oculto_ms: int | None = Field(default=None)
    # `criado_em` e o inicio da transacao, antes da geracao; este marco e o fim dela.
    respondido_em: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
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
    round_id: uuid.UUID = Field(foreign_key="question_rounds.id", index=True, ondelete="CASCADE")
    pipeline_id: int = Field(foreign_key="pipelines.id", index=True)
    rotulo_cego: str = Field(max_length=1)
    posicao_exibida: int
    texto: str
    # Foto da configuracao usada: editar o pipeline depois nao reescreve o que ja foi coletado.
    config_snapshot: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
