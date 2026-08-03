"""Busca na collection do pipeline: densa nos pipelines 1 e 2, hibrida nos 3 e 4."""

import uuid

from pymilvus import AnnSearchRequest, RRFRanker

from app.core.milvus import CAMPO_CHUNK, CAMPO_DENSO, CAMPO_DOCUMENTO, CAMPO_ESPARSO, CAMPO_TEXTO
from app.models.telemetry import EtapaPipeline
from app.rag.retrieval.base import Candidato, MetricaEtapa, candidato_de_hit
from app.telemetry.recorder import Cronometro

CAMPOS_DE_SAIDA = [CAMPO_CHUNK, CAMPO_TEXTO]


def _busca_densa(cliente, collection_name: str, filtro: str, vetor: list[float], limite: int):
    return cliente.search(
        collection_name=collection_name,
        data=[vetor],
        anns_field=CAMPO_DENSO,
        search_params={"metric_type": "COSINE"},
        limit=limite,
        filter=filtro,
        output_fields=CAMPOS_DE_SAIDA,
    )


def _busca_hibrida(
    cliente, collection_name: str, filtro: str, query: str, vetor: list[float], limite: int
):
    """Funde denso e BM25 com Reciprocal Rank Fusion.

    O pedido esparso leva o texto cru: o BM25 e uma Function do servidor, que tokeniza e pontua
    com as estatisticas da propria collection. Mandar um vetor ali seria erro de tipo.
    """
    pedido_denso = AnnSearchRequest(
        data=[vetor],
        anns_field=CAMPO_DENSO,
        param={"metric_type": "COSINE"},
        limit=limite,
        expr=filtro,
    )
    pedido_esparso = AnnSearchRequest(
        data=[query],
        anns_field=CAMPO_ESPARSO,
        param={"metric_type": "BM25"},
        limit=limite,
        expr=filtro,
    )
    return cliente.hybrid_search(
        collection_name=collection_name,
        reqs=[pedido_denso, pedido_esparso],
        ranker=RRFRanker(),
        limit=limite,
        output_fields=CAMPOS_DE_SAIDA,
    )


def buscar(
    cliente,
    collection_name: str,
    document_id: uuid.UUID,
    query: str,
    vetor: list[float],
    *,
    limite: int,
    hibrido: bool,
) -> tuple[list[Candidato], MetricaEtapa]:
    # document_id e UUID, entao interpolar no filtro nao abre espaco para injecao.
    filtro = f'{CAMPO_DOCUMENTO} == "{document_id}"'

    with Cronometro() as relogio:
        if hibrido:
            resultados = _busca_hibrida(cliente, collection_name, filtro, query, vetor, limite)
        else:
            resultados = _busca_densa(cliente, collection_name, filtro, vetor, limite)

    candidatos = [candidato_de_hit(hit) for hit in (resultados[0] if resultados else [])]
    if not hibrido:
        # Na busca densa o score e a similaridade de cosseno; no RRF e um score fundido do qual
        # nao da para extrair as parcelas, entao la os dois campos ficam nulos.
        for candidato in candidatos:
            candidato.score_denso = candidato.score_final

    detalhes = {
        "modo": "hibrido" if hibrido else "denso",
        "limite": limite,
        "recuperados": len(candidatos),
    }
    if hibrido:
        detalhes["ranker"] = "rrf"

    return candidatos, MetricaEtapa(
        etapa=EtapaPipeline.RETRIEVAL, duracao_ms=relogio.ms, detalhes=detalhes
    )
