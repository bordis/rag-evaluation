import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel, UniqueConstraint


class EvaluationSession(SQLModel, table=True):
    """O avaliador em um estudo: uma sessao por login e por estudo (decisao 16).

    Guarda so o `sub` do Keycloak, nunca nome ou e-mail. Sessoes de antes do SSO ficam com
    `usuario_sub` nulo; o Postgres nao compara nulos na unicidade, entao elas convivem.
    """

    __tablename__ = "evaluation_sessions"
    __table_args__ = (UniqueConstraint("study_id", "usuario_sub", name="uq_estudo_usuario"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    study_id: uuid.UUID = Field(foreign_key="studies.id", index=True, ondelete="CASCADE")
    usuario_sub: str | None = Field(default=None, max_length=64)
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
    # Parte de `tempo_total_ms` gasta escrevendo a pergunta: sem ela, fadiga se confunde com isso.
    tempo_pergunta_ms: int | None = Field(default=None)
    # Quantas das 4 respostas chegaram a aparecer na tela antes da escolha. Nulo: sem medicao.
    respostas_vistas: int | None = Field(default=None)
    recarregamentos: int | None = Field(default=None)
    # Com tela estreita as respostas empilham, e a ultima fica longe da primeira.
    largura_tela: int | None = Field(default=None)
    # `ordem` recomeca a cada documento; a fadiga acumula na sessao inteira.
    ordem_na_sessao: int | None = Field(default=None)
    # Incluindo esta. Em CPU, a latencia do reordenador cresce com a concorrencia.
    rodadas_simultaneas: int | None = Field(default=None)
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
    # Segundo passo: com vencedora, o avaliador marca quais das outras tambem estao corretas.
    # Completa = decidida e (`nenhuma_correta` ou `marcado_em`); so a completa libera a proxima.
    marcado_em: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # Fora de `tempo_total_ms`: a marcacao nao entra no tempo ativo da escolha.
    tempo_marcacao_ms: int | None = Field(default=None)
    tempo_marcacao_oculto_ms: int | None = Field(default=None)


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
    # `finish_reason`: "length" e resposta cortada, que perde por motivo alheio aos fatores.
    motivo_parada: str | None = Field(default=None, max_length=32)
    # Foto da configuracao usada: editar o pipeline depois nao reescreve o que ja foi coletado.
    config_snapshot: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    # Nulo: nao medido (a escolhida, rodada "nenhuma" ou ainda sem marcacao). Preenchido so nas
    # tres nao escolhidas, quando o avaliador marca as outras corretas.
    tambem_correta: bool | None = Field(default=None)


class RoundFailure(SQLModel, table=True):
    """Pergunta que nao virou rodada. Se so certas perguntas falham, a amostra fica enviesada."""

    __tablename__ = "round_failures"

    id: int | None = Field(default=None, primary_key=True)
    session_id: uuid.UUID = Field(
        foreign_key="evaluation_sessions.id", index=True, ondelete="CASCADE"
    )
    document_id: uuid.UUID = Field(foreign_key="documents.id", index=True, ondelete="CASCADE")
    pergunta: str = Field(max_length=500)
    erro: str = Field(max_length=2000)
    criado_em: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
