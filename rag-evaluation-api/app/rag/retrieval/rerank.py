"""Re-ranking dos candidatos por LLM. Ligado so nos pipelines 3 e 4.

O modelo recebe a pergunta original — nao a reescrita. A reescrita e uma string de busca; a
relevancia se julga contra o que o avaliador de fato perguntou.
"""

import json

from openai import OpenAI

from app.models.telemetry import EtapaPipeline
from app.rag.llm import conversar
from app.rag.retrieval.base import Candidato, MetricaEtapa, metrica_de_llm
from app.telemetry.recorder import Cronometro

# O re-rank ve ate RERANK_CANDIDATES trechos de uma vez; sem truncar, o prompt custaria mais
# tokens que a propria geracao e distorceria a comparacao de custo entre os pipelines.
TAMANHO_MAXIMO_DO_TRECHO = 600

INSTRUCAO = (
    "Você ordena trechos de um documento por relevância para uma pergunta. "
    "Receberá trechos numerados a partir de 1. Responda em JSON, no formato "
    '{"ordem": [n, n, ...]}, listando os números dos trechos do mais relevante para o menos '
    "relevante. Inclua todos os números recebidos, sem repetir nenhum, e não escreva mais nada."
)


def _montar_prompt(pergunta: str, candidatos: list[Candidato]) -> str:
    trechos = "\n\n".join(
        f"[{posicao}] {candidato.texto[:TAMANHO_MAXIMO_DO_TRECHO]}"
        for posicao, candidato in enumerate(candidatos, start=1)
    )
    return f"Pergunta: {pergunta}\n\nTrechos:\n\n{trechos}"


def _ordem_do_modelo(texto: str, total: int) -> list[int] | None:
    """Converte a resposta em posicoes 0-based validas, ou None se ela nao for aproveitavel."""
    try:
        bruto = json.loads(texto)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(bruto, dict) or not isinstance(bruto.get("ordem"), list):
        return None

    vistos: list[int] = []
    for valor in bruto["ordem"]:
        if not isinstance(valor, int):
            continue
        posicao = valor - 1
        if 0 <= posicao < total and posicao not in vistos:
            vistos.append(posicao)
    return vistos or None


def reordenar(
    pergunta: str,
    candidatos: list[Candidato],
    *,
    manter: int,
    cliente: OpenAI | None = None,
) -> tuple[list[Candidato], MetricaEtapa]:
    if not candidatos:
        return [], MetricaEtapa(
            etapa=EtapaPipeline.RERANKING,
            duracao_ms=0,
            detalhes={"candidatos": 0, "mantidos": 0, "fallback": False},
        )

    with Cronometro() as relogio:
        resposta = conversar(
            [
                {"role": "system", "content": INSTRUCAO},
                {"role": "user", "content": _montar_prompt(pergunta, candidatos)},
            ],
            cliente=cliente,
            resposta_json=True,
        )

    ordem = _ordem_do_modelo(resposta.texto, len(candidatos))
    fallback = ordem is None
    if ordem is None:
        ordenados = list(candidatos)
    else:
        # Os nao citados vao para o fim em vez de sumir: um candidato omitido pelo modelo ainda
        # e melhor que trecho nenhum, se o corte alcancar.
        restantes = [posicao for posicao in range(len(candidatos)) if posicao not in ordem]
        ordenados = [candidatos[posicao] for posicao in [*ordem, *restantes]]

    mantidos = ordenados[:manter]
    detalhes = {
        "candidatos": len(candidatos),
        "mantidos": len(mantidos),
        "fallback": fallback,
    }
    return mantidos, metrica_de_llm(EtapaPipeline.RERANKING, relogio.ms, resposta, detalhes)
