"""Orquestrador da consulta: le a config do pipeline e monta as etapas.

Ele nao sabe qual pipeline executa. Nao ha caminho especial para o braco de controle — o
comportamento de controle emerge de ter os quatro flags desligados. Um quinto pipeline seria uma
linha no banco, nao codigo novo.

Sincrona de proposito (decisao C1 do plano): a Fatia 4 obtem o paralelismo das 4 respostas com
`asyncio.gather` sobre `asyncio.to_thread`, sem exigir cliente assincrono de Milvus nem de OpenAI.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.milvus import construir_cliente
from app.models.pipeline import Pipeline
from app.models.telemetry import EtapaPipeline
from app.rag.embedding import embutir_textos
from app.rag.generation import gerar_resposta
from app.rag.retrieval.base import Candidato, MetricaEtapa
from app.rag.retrieval.rerank import reordenar
from app.rag.retrieval.rewrite import reescrever_query
from app.rag.retrieval.search import buscar
from app.rag.retrieval.window import expandir_janela
from app.telemetry.recorder import Cronometro


@dataclass
class RespostaDePipeline:
    texto: str
    metricas: list[MetricaEtapa]
    chunks: list[Candidato]


@dataclass
class DependenciasDeConsulta:
    """Pontos de injecao. Com falsos aqui, o fluxo inteiro roda sem OpenAI nem Milvus."""

    reescrever: Callable = field(default=reescrever_query)
    embutir: Callable = field(default=embutir_textos)
    buscar: Callable = field(default=buscar)
    reordenar: Callable = field(default=reordenar)
    expandir: Callable = field(default=expandir_janela)
    gerar: Callable = field(default=gerar_resposta)
    construir_cliente_milvus: Callable[[], object] = field(default=construir_cliente)


def executar_pipeline(
    pipeline: Pipeline,
    document_id: uuid.UUID,
    pergunta: str,
    *,
    dependencias: DependenciasDeConsulta | None = None,
    cliente_milvus: object | None = None,
) -> RespostaDePipeline:
    deps = dependencias or DependenciasDeConsulta()
    settings = get_settings()
    config = pipeline.config or {}
    metricas: list[MetricaEtapa] = []

    query = pergunta
    if config.get("query_rewriting"):
        query, metrica = deps.reescrever(pergunta)
        metricas.append(metrica)

    with Cronometro() as relogio:
        embutido = deps.embutir([query])
    metricas.append(
        MetricaEtapa(
            etapa=EtapaPipeline.EMBEDDING_QUERY,
            duracao_ms=relogio.ms,
            tokens_prompt=embutido.tokens,
            tokens_total=embutido.tokens,
            modelo=settings.embedding_model,
            detalhes={"query": query},
        )
    )

    top_k = int(config.get("top_k") or settings.rag_search_limit)
    reranking = bool(config.get("reranking"))
    # Com re-rank, a busca traz um pool maior para o modelo ter o que descartar; sem ele, o
    # resultado da busca ja e o contexto final.
    limite = settings.rerank_candidates if reranking else top_k

    cliente = cliente_milvus if cliente_milvus is not None else deps.construir_cliente_milvus()
    candidatos, metrica = deps.buscar(
        cliente,
        pipeline.collection_name,
        document_id,
        query,
        embutido.vetores[0],
        limite=limite,
        hibrido=bool(config.get("hybrid_search")),
    )
    metricas.append(metrica)

    if reranking:
        # Pergunta original, nao a reescrita: relevancia se julga contra o que foi perguntado.
        candidatos, metrica = deps.reordenar(pergunta, candidatos, manter=top_k)
        metricas.append(metrica)

    janela = config.get("sliding_window") or {}
    if janela.get("ativo"):
        candidatos, metrica = deps.expandir(
            cliente,
            pipeline.collection_name,
            document_id,
            candidatos,
            tamanho=int(janela.get("tamanho") or settings.sliding_window_size),
        )
        metricas.append(metrica)

    texto, metrica = deps.gerar(pergunta, candidatos)
    metricas.append(metrica)

    return RespostaDePipeline(texto=texto, metricas=metricas, chunks=candidatos)
