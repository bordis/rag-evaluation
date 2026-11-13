"""Quanto de cada documento vai ao LLM, medido pelas ingestoes reais.

A busca e filtrada por documento, entao o que importa para o efeito teto e a fracao do documento
que cabe no contexto: `top_k` chunks sobre o total de chunks que a ingestao gerou. Os parsers geram
contagens diferentes, por isso a listagem mostra uma faixa entre os pipelines.
Funcoes puras: a consulta fica no router, aqui so a conta.
"""

from dataclasses import dataclass

from app.core.config import get_settings
from app.models.document import DocumentIngestion, StatusIngestao
from app.models.pipeline import Pipeline


@dataclass(frozen=True)
class IngestaoDoContexto:
    """O minimo de uma linha de `document_ingestions` + config do pipeline para a conta."""

    status: StatusIngestao
    total_chunks: int
    tokens_embedding: int
    top_k: int
    chunk_size: int


@dataclass(frozen=True)
class ContextoDaIngestao:
    chunks: int
    percentual: float | None
    tokens_estimados: int | None


@dataclass(frozen=True)
class ContextoDoDocumento:
    chunks: int
    tokens_estimados: int
    percentual_min: float
    percentual_max: float


def top_k_do_pipeline(config: dict) -> int:
    """Mesma regra de `app/rag/pipeline.py`: a config do pipeline vence o `.env`."""
    return int(config.get("top_k") or get_settings().rag_search_limit)


def chunk_size_da_ingestao(config_snapshot: dict) -> int:
    return int(config_snapshot.get("chunk_size") or get_settings().chunk_size)


def para_contexto(ingestao: DocumentIngestion, pipeline: Pipeline) -> IngestaoDoContexto:
    return IngestaoDoContexto(
        status=ingestao.status,
        total_chunks=ingestao.total_chunks,
        tokens_embedding=ingestao.tokens_embedding,
        top_k=top_k_do_pipeline(pipeline.config),
        chunk_size=chunk_size_da_ingestao(ingestao.config_snapshot),
    )


def contexto_da_ingestao(ingestao: IngestaoDoContexto) -> ContextoDaIngestao:
    """Chunks entregues, fracao do documento e tokens estimados de um pipeline.

    Sem ingestao concluida com chunks nao ha fracao: devolve 0 chunks e percentual None.
    """
    if ingestao.status != StatusIngestao.CONCLUIDA or ingestao.total_chunks <= 0:
        return ContextoDaIngestao(chunks=0, percentual=None, tokens_estimados=None)
    chunks = min(ingestao.top_k, ingestao.total_chunks)
    if ingestao.tokens_embedding > 0:
        # Media de tokens por chunk do proprio documento: o ultimo chunk e os cortes em fim de
        # frase deixam os chunks menores que `chunk_size`.
        tokens = chunks * ingestao.tokens_embedding / ingestao.total_chunks
    else:
        tokens = chunks * ingestao.chunk_size
    return ContextoDaIngestao(
        chunks=chunks,
        percentual=round(100 * chunks / ingestao.total_chunks, 1),
        tokens_estimados=round(tokens),
    )


def resumir_contexto(ingestoes: list[IngestaoDoContexto]) -> ContextoDoDocumento | None:
    """Faixa entre os pipelines com ingestao concluida; None se nenhum tiver chunks."""
    validos = [
        item
        for item in (contexto_da_ingestao(ingestao) for ingestao in ingestoes)
        if item.percentual is not None and item.tokens_estimados is not None
    ]
    if not validos:
        return None
    percentuais = [item.percentual for item in validos if item.percentual is not None]
    tokens = [item.tokens_estimados for item in validos if item.tokens_estimados is not None]
    return ContextoDoDocumento(
        chunks=max(item.chunks for item in validos),
        tokens_estimados=round(sum(tokens) / len(tokens)),
        percentual_min=min(percentuais),
        percentual_max=max(percentuais),
    )
