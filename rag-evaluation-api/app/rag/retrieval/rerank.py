"""Reordenacao dos candidatos por cross-encoder, num servico a parte. Ligada so nos pipelines 3 e 4.

O modelo recebe a pergunta original, nao o documento hipotetico: a relevancia se julga contra o que
o avaliador de fato perguntou. Sem fallback para a ordem da busca: uma rodada reordenada e outra nao
misturariam dois tratamentos sob o mesmo pipeline, entao a falha derruba a rodada.

O servico fala o formato /v1/rerank (Jina/Cohere, o que o vLLM serve): recebe `documents` e devolve
`results` com `relevance_score`, alem do modelo e dos tokens consumidos.
"""

from dataclasses import replace

import httpx

from app.core.config import get_settings
from app.models.telemetry import EtapaPipeline
from app.rag.retrieval.base import Candidato, MetricaEtapa
from app.telemetry.recorder import Cronometro


def _cabecalhos(chave: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {chave}"} if chave else {}


def reordenar(
    pergunta: str, candidatos: list[Candidato], *, cliente: httpx.Client | None = None
) -> tuple[list[Candidato], MetricaEtapa]:
    """Devolve todos em nova ordem, com o score do modelo; quem corta e o orquestrador."""
    settings = get_settings()
    detalhes: dict = {"candidatos": len(candidatos)}
    if not candidatos:
        return [], MetricaEtapa(etapa=EtapaPipeline.RERANKING, duracao_ms=0, detalhes=detalhes)

    proprio = cliente is None
    if cliente is None:
        cliente = httpx.Client(timeout=settings.pipeline_timeout_seconds)
    try:
        with Cronometro() as relogio:
            resposta = cliente.post(
                settings.reranker_url,
                headers=_cabecalhos(settings.reranker_key),
                json={
                    "query": pergunta,
                    "documents": [candidato.texto for candidato in candidatos],
                },
            )
            resposta.raise_for_status()
    finally:
        if proprio:
            cliente.close()

    corpo = resposta.json()
    ordenados = sorted(corpo["results"], key=lambda item: item["relevance_score"], reverse=True)
    # O modelo e os tokens vem da resposta, como no chat: e o que o servico de fato usou. Os
    # pipelines 3 e 4 disputam o mesmo servico, entao `duracao_ms` inclui a espera na fila.
    tokens = (corpo.get("usage") or {}).get("total_tokens")
    return [
        replace(candidatos[item["index"]], score_final=float(item["relevance_score"]))
        for item in ordenados
    ], MetricaEtapa(
        etapa=EtapaPipeline.RERANKING,
        duracao_ms=relogio.ms,
        tokens_prompt=tokens,
        tokens_total=tokens,
        modelo=corpo.get("model"),
        detalhes=detalhes,
    )
