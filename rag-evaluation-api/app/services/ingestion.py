"""Orquestracao da ingestao: parsing -> chunking -> embedding -> indexacao, por pipeline.

O orquestrador nao sabe qual pipeline executa. Ele le `parser` e `collection_name` do banco e
monta o fluxo — um quinto pipeline seria uma linha na tabela, nao codigo novo.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.db import engine
from app.core.milvus import construir_cliente
from app.models.document import Document, DocumentIngestion, StatusDocumento, StatusIngestao
from app.models.pipeline import Pipeline
from app.rag.chunking import Chunk, dividir_em_chunks
from app.rag.embedding import ResultadoEmbedding, embutir_textos
from app.rag.indexing import indexar_chunks
from app.rag.parsing import obter_parser
from app.rag.parsing.base import ErroDeParsing
from app.telemetry.recorder import Cronometro


@dataclass
class DependenciasDeIngestao:
    """Pontos de injecao. Com falsos aqui, o fluxo inteiro roda sem OpenAI, Milvus nem Docling."""

    obter_parser: Callable = field(default=obter_parser)
    embutir: Callable[[list[str]], ResultadoEmbedding] = field(default=embutir_textos)
    indexar: Callable[..., int] = field(default=indexar_chunks)
    construir_cliente_milvus: Callable[[], object] = field(default=construir_cliente)


def _ingerir_em_pipeline(
    sessao: Session,
    cliente_milvus: object,
    documento: Document,
    pipeline: Pipeline,
    conteudo: bytes,
    mime_type: str,
    nome_arquivo: str,
    dependencias: DependenciasDeIngestao,
) -> None:
    ingestao = sessao.exec(
        select(DocumentIngestion).where(
            DocumentIngestion.document_id == documento.id,
            DocumentIngestion.pipeline_id == pipeline.id,
        )
    ).one()
    ingestao.status = StatusIngestao.PROCESSANDO
    ingestao.iniciado_em = datetime.now(UTC)
    sessao.add(ingestao)
    sessao.commit()

    settings = get_settings()
    total = Cronometro()
    parsing, chunking, embedding, indexacao = (
        Cronometro(),
        Cronometro(),
        Cronometro(),
        Cronometro(),
    )
    chunks: list[Chunk] = []
    embeddings = ResultadoEmbedding(vetores=[], tokens=0)
    caracteres = 0

    try:
        with total:
            with parsing:
                parsear = dependencias.obter_parser(pipeline.parser)
                resultado = parsear(conteudo, mime_type, nome_arquivo)
            caracteres = len(resultado.texto)

            with chunking:
                chunks = dividir_em_chunks(
                    resultado.texto, settings.chunk_size, settings.chunk_overlap
                )
            if not chunks:
                raise ErroDeParsing("O texto extraido nao rendeu nenhum chunk.")

            with embedding:
                embeddings = dependencias.embutir([chunk.texto for chunk in chunks])

            with indexacao:
                dependencias.indexar(
                    cliente_milvus,
                    pipeline.collection_name,
                    documento.id,
                    chunks,
                    embeddings.vetores,
                    {**resultado.metadados, "slug": documento.slug},
                )
    except Exception as erro:  # noqa: BLE001 — a falha de um pipeline nao derruba os outros
        ingestao.status = StatusIngestao.ERRO
        ingestao.erro = f"{type(erro).__name__}: {erro}"[:2000]
    else:
        ingestao.status = StatusIngestao.CONCLUIDA
        ingestao.erro = None

    ingestao.total_caracteres = caracteres
    ingestao.total_chunks = len(chunks)
    ingestao.tokens_embedding = embeddings.tokens
    ingestao.duracao_parsing_ms = parsing.ms
    ingestao.duracao_chunking_ms = chunking.ms
    ingestao.duracao_embedding_ms = embedding.ms
    ingestao.duracao_indexacao_ms = indexacao.ms
    ingestao.duracao_total_ms = total.ms
    ingestao.concluido_em = datetime.now(UTC)
    sessao.add(ingestao)
    # Commit por pipeline para `GET /documents/{id}/ingestions` mostrar o progresso durante a
    # ingestao, em vez de tudo aparecer de uma vez no fim.
    sessao.commit()


def _concluir(sessao: Session, documento: Document) -> None:
    """Publica o documento so quando os 4 pipelines concluem — o desenho exige as 4 respostas."""
    ingestoes = sessao.exec(
        select(DocumentIngestion).where(DocumentIngestion.document_id == documento.id)
    ).all()
    completo = bool(ingestoes) and all(
        item.status == StatusIngestao.CONCLUIDA for item in ingestoes
    )
    documento.status = StatusDocumento.PRONTO if completo else StatusDocumento.ERRO_PARCIAL
    sessao.add(documento)
    sessao.commit()


def ingerir_documento(
    sessao: Session,
    document_id: uuid.UUID,
    conteudo: bytes,
    mime_type: str,
    nome_arquivo: str,
    *,
    dependencias: DependenciasDeIngestao | None = None,
) -> None:
    dependencias = dependencias or DependenciasDeIngestao()
    documento = sessao.get(Document, document_id)
    if documento is None:
        return

    cliente_milvus = dependencias.construir_cliente_milvus()
    pipelines = sessao.exec(select(Pipeline).order_by(Pipeline.codigo)).all()  # type: ignore[arg-type]
    for pipeline in pipelines:
        _ingerir_em_pipeline(
            sessao,
            cliente_milvus,
            documento,
            pipeline,
            conteudo,
            mime_type,
            nome_arquivo,
            dependencias,
        )

    _concluir(sessao, documento)


def executar_ingestao(
    document_id: uuid.UUID, conteudo: bytes, mime_type: str, nome_arquivo: str
) -> None:
    """Ponto de entrada do BackgroundTasks: a sessao da requisicao ja foi fechada aqui."""
    with Session(engine) as sessao:
        ingerir_documento(sessao, document_id, conteudo, mime_type, nome_arquivo)
