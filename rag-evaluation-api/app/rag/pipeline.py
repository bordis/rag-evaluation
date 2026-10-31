"""Orquestrador da consulta: le a config do pipeline e monta as etapas.

Ele nao sabe qual pipeline executa. Nao ha caminho especial para o braco de controle — o
comportamento de controle emerge de ter os flags desligados. Um quinto pipeline seria uma
linha no banco, nao codigo novo.

Sincrona de proposito (decisao C1 do plano): a Fatia 4 obtem o paralelismo das 4 respostas com
`asyncio.gather` sobre `asyncio.to_thread`, sem exigir cliente assincrono de Milvus nem de OpenAI.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from app.core.config import get_settings
from app.core.milvus import construir_cliente
from app.models.pipeline import Pipeline
from app.models.telemetry import EtapaChunk, EtapaPipeline
from app.rag.embedding import embutir_textos
from app.rag.generation import gerar_resposta
from app.rag.retrieval.base import Candidato, MetricaEtapa
from app.rag.retrieval.hyde import gerar_documento_hipotetico
from app.rag.retrieval.rerank import reordenar
from app.rag.retrieval.search import buscar, buscar_parcelas
from app.rag.retrieval.window import expandir_janela
from app.telemetry.recorder import Cronometro


@dataclass
class RespostaDePipeline:
    texto: str
    metricas: list[MetricaEtapa]
    chunks: list[Candidato]
    # O que cada etapa viu, para localizar onde um trecho se perdeu. `chunks` e o contexto final.
    etapas: dict[EtapaChunk, list[Candidato]] = field(default_factory=dict)


@dataclass
class DependenciasDeConsulta:
    """Pontos de injecao. Com falsos aqui, o fluxo inteiro roda sem OpenAI nem Milvus."""

    gerar_hipotetico: Callable = field(default=gerar_documento_hipotetico)
    embutir: Callable = field(default=embutir_textos)
    buscar: Callable = field(default=buscar)
    buscar_parcelas: Callable = field(default=buscar_parcelas)
    reordenar: Callable = field(default=reordenar)
    expandir: Callable = field(default=expandir_janela)
    gerar: Callable = field(default=gerar_resposta)
    construir_cliente_milvus: Callable[[], object] = field(default=construir_cliente)


def _media(vetores: list[list[float]]) -> list[float]:
    """Combina os vetores como em Gao et al. (2023): a media do hipotetico com o da pergunta."""
    return [sum(valores) / len(vetores) for valores in zip(*vetores, strict=True)]


def _preencher_parcelas(
    fundidos: list[Candidato], densos: list[Candidato], esparsos: list[Candidato]
) -> None:
    score_denso = {candidato.milvus_id: candidato.score_final for candidato in densos}
    score_esparso = {candidato.milvus_id: candidato.score_final for candidato in esparsos}
    for candidato in fundidos:
        candidato.score_denso = score_denso.get(candidato.milvus_id)
        candidato.score_esparso = score_esparso.get(candidato.milvus_id)


def _completar_contexto(
    contexto: list[Candidato], ordenados: list[Candidato], total: int
) -> list[Candidato]:
    """Vizinhos repetidos deixam o contexto abaixo do total; os proximos do ranking preenchem.

    A quantidade de chunks precisa ser igual nos 4 pipelines (Secao 2.5.5): a diferenca deve vir
    da qualidade dos trechos, nao da quantidade.
    """
    completo = list(contexto)
    presentes = {candidato.chunk_index for candidato in contexto}
    for candidato in ordenados:
        if len(completo) >= total:
            break
        if candidato.chunk_index not in presentes:
            completo.append(replace(candidato, origem="complemento"))
            presentes.add(candidato.chunk_index)
    return completo


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
    etapas: dict[EtapaChunk, list[Candidato]] = {}

    textos = [pergunta]
    if config.get("hyde"):
        hipotetico, metrica = deps.gerar_hipotetico(pergunta)
        metricas.append(metrica)
        if hipotetico:
            textos.insert(0, hipotetico)

    with Cronometro() as relogio:
        embutido = deps.embutir(textos)
    vetor = _media(embutido.vetores)
    metricas.append(
        MetricaEtapa(
            etapa=EtapaPipeline.EMBEDDING_QUERY,
            duracao_ms=relogio.ms,
            tokens_prompt=embutido.tokens,
            tokens_total=embutido.tokens,
            modelo=settings.embedding_model,
            detalhes={"textos": len(textos)},
        )
    )

    total = int(config.get("top_k") or settings.rag_search_limit)
    hibrido = bool(config.get("hybrid_search"))
    reranking = bool(config.get("reranking"))
    janela = config.get("sliding_window") or {}
    # Reordenar e completar o contexto pedem uma lista maior que o que vai ao LLM.
    selecao_em_dois_passos = reranking or janela.get("ativo")
    limite = (
        int(config.get("candidatos") or settings.rerank_candidates)
        if selecao_em_dois_passos
        else total
    )

    cliente = cliente_milvus if cliente_milvus is not None else deps.construir_cliente_milvus()
    # A parte lexical usa a pergunta original: o texto hipotetico inventaria numeros e siglas, que
    # sao justamente o que o BM25 precisa encontrar exatos.
    candidatos, metrica = deps.buscar(
        cliente,
        pipeline.collection_name,
        document_id,
        pergunta,
        vetor,
        limite=limite,
        hibrido=hibrido,
    )
    metricas.append(metrica)

    if hibrido:
        densos, esparsos = deps.buscar_parcelas(
            cliente, pipeline.collection_name, document_id, pergunta, vetor, limite=limite
        )
        _preencher_parcelas(candidatos, densos, esparsos)
        etapas[EtapaChunk.DENSO] = densos
        etapas[EtapaChunk.ESPARSO] = esparsos
        etapas[EtapaChunk.FUSAO] = list(candidatos)
    else:
        etapas[EtapaChunk.DENSO] = list(candidatos)

    if reranking:
        candidatos, metrica = deps.reordenar(pergunta, candidatos)
        metricas.append(metrica)
        etapas[EtapaChunk.REORDENACAO] = list(candidatos)

    if janela.get("ativo"):
        quantidade = int(config.get("ancoras") or settings.rag_ancoras)
        ancoras = [replace(item, origem="ancora") for item in candidatos[:quantidade]]
        expandidos, metrica = deps.expandir(
            cliente,
            pipeline.collection_name,
            document_id,
            ancoras,
            tamanho=int(janela.get("tamanho") or settings.sliding_window_size),
        )
        contexto = _completar_contexto(expandidos, candidatos[quantidade:], total)
        metrica.detalhes["complemento"] = len(contexto) - len(expandidos)
        metrica.detalhes["contexto_final"] = len(contexto)
        metricas.append(metrica)
    else:
        contexto = [replace(item, origem="busca") for item in candidatos[:total]]

    etapas[EtapaChunk.CONTEXTO_FINAL] = contexto

    texto, metrica = deps.gerar(pergunta, contexto)
    metricas.append(metrica)

    return RespostaDePipeline(texto=texto, metricas=metricas, chunks=contexto, etapas=etapas)
