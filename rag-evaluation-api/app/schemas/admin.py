"""Schemas do administrador. **Expoem o pipeline de proposito**: e a visao do pesquisador.

A garantia do cego vale para `schemas/evaluation.py`, que o fluxo do avaliador usa.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.pipeline import ParserType
from app.models.study import StatusEstudo
from app.models.telemetry import EtapaChunk, EtapaPipeline


class EstudoCriar(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    descricao: str = Field(default="", max_length=1000)


class EstudoResumo(BaseModel):
    id: uuid.UUID
    nome: str
    descricao: str
    status: StatusEstudo
    iniciado_em: datetime | None
    encerrado_em: datetime | None
    sessoes: int
    rodadas_decididas: int


class PipelineCriar(BaseModel):
    codigo: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9-]+$")
    nome: str = Field(min_length=2, max_length=120)
    descricao: str = Field(default="", max_length=500)
    parser: ParserType
    collection_name: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    config: dict = Field(default_factory=dict)


class PipelineAtualizar(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    descricao: str | None = Field(default=None, max_length=500)
    ativo: bool | None = None
    config: dict | None = None


class PipelineDetalhe(BaseModel):
    id: int
    codigo: str
    nome: str
    descricao: str
    parser: ParserType
    collection_name: str
    ativo: bool
    config: dict
    controle: bool
    atualizado_em: datetime | None


class AvaliacaoResumo(BaseModel):
    """Um ciclo: as rodadas de um avaliador sobre um documento em um estudo."""

    session_id: uuid.UUID
    document_id: uuid.UUID
    documento_slug: str
    documento_titulo: str
    rodadas: int
    decididas: int
    nenhuma: int
    inicio: datetime | None
    fim: datetime | None


class ChunkDetalhe(BaseModel):
    etapa: EtapaChunk
    posicao: int
    chunk_index: int
    score_final: float
    score_denso: float | None
    score_esparso: float | None
    origem: str | None
    texto: str


class MetricaDetalhe(BaseModel):
    etapa: EtapaPipeline
    ordem: int
    duracao_ms: int
    tokens_prompt: int | None
    tokens_completion: int | None
    tokens_total: int | None
    modelo: str | None
    custo_usd: float | None
    detalhes: dict


class RagasDetalhe(BaseModel):
    fidelidade: float | None
    relevancia_resposta: float | None
    precisao_contexto: float | None
    media: float | None
    modelo: str
    erro: str | None


class RespostaDetalhe(BaseModel):
    id: uuid.UUID
    rotulo: str
    posicao_exibida: int
    pipeline_codigo: str
    pipeline_nome: str
    escolhida: bool
    texto: str
    config_snapshot: dict
    metricas: list[MetricaDetalhe]
    chunks: list[ChunkDetalhe]
    ragas: RagasDetalhe | None


class RodadaAdmin(BaseModel):
    id: uuid.UUID
    ordem: int
    pergunta: str
    nenhuma_correta: bool
    decidida: bool
    tempo_total_ms: int | None
    tempo_geracao_ms: int | None
    tempo_oculto_ms: int | None
    tempo_decisao_ms: int | None
    criado_em: datetime | None
    respondido_em: datetime | None
    escolhido_em: datetime | None
    respostas: list[RespostaDetalhe]


class AvaliacaoDetalhe(BaseModel):
    session_id: uuid.UUID
    document_id: uuid.UUID
    documento_titulo: str
    study_id: uuid.UUID
    estudo_nome: str
    termo_versao: str
    aceito_em: datetime | None
    rodadas: list[RodadaAdmin]


class RagasDisparado(BaseModel):
    respostas_pendentes: int
    mensagem: str


class RagasSituacao(BaseModel):
    em_andamento: bool
    total: int
    avaliadas: int
    com_erro: int
    ultimo_erro: str | None
