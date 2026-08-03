"""Schemas de saida dos documentos.

`IngestaoResumo` **expoe o pipeline de proposito**: e a telemetria de ingestao do pesquisador, e
o frontend nunca chama esse endpoint. A garantia do cego vale para os schemas de avaliacao.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.document import StatusDocumento, StatusIngestao


class DocumentoResumo(BaseModel):
    id: uuid.UUID
    slug: str
    titulo: str
    area: str
    descricao: str
    icone: str
    status: StatusDocumento
    criado_em: datetime


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
