"""Schemas de saida dos documentos.

`IngestaoResumo` **expoe o pipeline de proposito**: e a telemetria de ingestao do pesquisador, e
o frontend nunca chama esse endpoint. A garantia do cego vale para os schemas de avaliacao.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, computed_field

from app.models.document import StatusDocumento, StatusIngestao


class DocumentoResumo(BaseModel):
    id: uuid.UUID
    slug: str
    titulo: str
    area: str
    descricao: str
    icone: str
    status: StatusDocumento
    paginas: int | None
    tabelas: int | None
    imagens: int | None
    criado_em: datetime
    # A chave do MinIO fica no servidor; o navegador so precisa saber se ha o que abrir.
    arquivo_chave: str | None = Field(default=None, exclude=True)

    @computed_field
    @property
    def pdf_disponivel(self) -> bool:
        return self.arquivo_chave is not None


class ContextoLLM(BaseModel):
    """Fracao do documento entregue ao LLM, calculada das ingestoes concluidas.

    `chunks` e o maior entre os pipelines, `tokens_estimados` a media, e a faixa de percentuais
    existe porque cada parser gera uma contagem de chunks diferente.
    """

    chunks: int
    tokens_estimados: int
    percentual_min: float
    percentual_max: float


class DocumentoAdmin(DocumentoResumo):
    """So em `GET /api/admin/documents`: a listagem do avaliador continua sem dados de ingestao."""

    contexto: ContextoLLM | None


class DocumentoDetalhe(DocumentoResumo):
    nome_arquivo_original: str
    mime_type: str
    tamanho_bytes: int
    sha256: str
    atualizado_em: datetime


class DocumentoAceito(BaseModel):
    id: uuid.UUID
    slug: str
    status: StatusDocumento
    mensagem: str


class IngestaoResumo(BaseModel):
    pipeline_codigo: str
    pipeline_nome: str
    status: StatusIngestao
    erro: str | None
    total_caracteres: int
    total_chunks: int
    tokens_embedding: int
    duracao_parsing_ms: int
    duracao_chunking_ms: int
    duracao_embedding_ms: int
    duracao_indexacao_ms: int
    duracao_total_ms: int
    iniciado_em: datetime | None
    concluido_em: datetime | None
    # min(top_k, total_chunks) e a fracao do documento que isso representa; 0 e None enquanto a
    # ingestao nao estiver concluida com chunks.
    contexto_chunks: int
    contexto_percentual: float | None
