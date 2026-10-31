"""Reordenacao dos candidatos por cross-encoder local. Ligada so nos pipelines 3 e 4.

O modelo recebe a pergunta original, nao o documento hipotetico: a relevancia se julga contra o que
o avaliador de fato perguntou. Sem fallback para a ordem da busca: uma rodada reordenada e outra nao
misturariam dois tratamentos sob o mesmo pipeline, entao a falha derruba a rodada.
"""

from dataclasses import replace

import httpx

from app.core.config import get_settings
from app.models.telemetry import EtapaPipeline
from app.rag.retrieval.base import Candidato, MetricaEtapa
from app.telemetry.recorder import Cronometro


def _tempo_do_cabecalho(resposta: httpx.Response, nome: str) -> int | None:
    valor = resposta.headers.get(nome)
    return int(float(valor)) if valor else None


def reordenar(
    pergunta: str, candidatos: list[Candidato], *, cliente: httpx.Client | None = None
) -> tuple[list[Candidato], MetricaEtapa]:
    """Devolve todos em nova ordem, com o score do modelo; quem corta e o orquestrador."""
    settings = get_settings()
    detalhes: dict = {"candidatos": len(candidatos), "provedor": "tei"}
    if not candidatos:
        return [], MetricaEtapa(
            etapa=EtapaPipeline.RERANKING,
            duracao_ms=0,
            modelo=settings.reranker_model,
            detalhes=detalhes,
        )

    proprio = cliente is None
    if cliente is None:
        cliente = httpx.Client(
            base_url=settings.reranker_url, timeout=settings.pipeline_timeout_seconds
        )
    try:
        with Cronometro() as relogio:
            resposta = cliente.post(
                "/rerank",
                json={
                    "query": pergunta,
                    "texts": [candidato.texto for candidato in candidatos],
                    "raw_scores": False,
                },
            )
            resposta.raise_for_status()
    finally:
        if proprio:
            cliente.close()

    ordenados = [
        replace(candidatos[item["index"]], score_final=float(item["score"]))
        for item in resposta.json()
    ]
    # Os pipelines 3 e 4 disputam o mesmo servico, e `duracao_ms` inclui a fila. Os cabecalhos do
    # TEI sao por lote e nao somam a duracao: servem de indicio, nao de custo exato.
    detalhes["inferencia_ms"] = _tempo_do_cabecalho(resposta, "x-inference-time")
    detalhes["fila_ms"] = _tempo_do_cabecalho(resposta, "x-queue-time")
    return ordenados, MetricaEtapa(
        etapa=EtapaPipeline.RERANKING,
        duracao_ms=relogio.ms,
        modelo=settings.reranker_model,
        detalhes=detalhes,
    )
