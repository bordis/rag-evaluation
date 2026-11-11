"""Linha de base parametrica do estudo: metricas RAGAS que dispensam resposta de referencia.

O juiz e configurado a parte do modelo de geracao: julgar com o mesmo modelo que gerou a resposta
introduz vies de autopromocao.
"""

import asyncio
import os
from dataclasses import dataclass
from functools import lru_cache

# Precisa valer antes do import: o RAGAS envia telemetria de uso por padrao.
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

from openai import AsyncOpenAI  # noqa: E402
from ragas.embeddings import embedding_factory  # noqa: E402
from ragas.llms import llm_factory  # noqa: E402
from ragas.metrics.collections import (  # noqa: E402
    AnswerRelevancy,
    ContextPrecisionWithoutReference,
    Faithfulness,
)

from app.core.config import Settings, get_settings  # noqa: E402

# Temperatura zero porque a nota precisa ser o mais reprodutivel possivel; o limite de tokens evita
# truncar a extracao de afirmacoes de respostas longas, o que faria a fidelidade falhar.
TEMPERATURA_JUIZ = 0
MAX_TOKENS_JUIZ = 4096


@dataclass(frozen=True)
class MetricasRagas:
    fidelidade: Faithfulness
    relevancia_resposta: AnswerRelevancy
    precisao_contexto: ContextPrecisionWithoutReference


@dataclass(frozen=True)
class AvaliacaoRagas:
    fidelidade: float
    relevancia_resposta: float
    precisao_contexto: float


def cliente_do_juiz(settings: Settings) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.ragas_llm_key or settings.chat_api_key,
        base_url=settings.ragas_llm_url,
        timeout=settings.ragas_timeout_seconds,
    )


def argumentos_do_juiz(settings: Settings) -> dict:
    """Vao direto para `chat.completions.create`: o ragas repassa o que nao reconhece."""
    argumentos: dict = {"temperature": TEMPERATURA_JUIZ, "max_tokens": MAX_TOKENS_JUIZ}
    if settings.ragas_llm_sem_raciocinio:
        argumentos["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    return argumentos


@lru_cache
def criar_metricas() -> MetricasRagas:
    settings = get_settings()
    llm = llm_factory(
        settings.ragas_llm_model,
        client=cliente_do_juiz(settings),
        **argumentos_do_juiz(settings),
    )
    embeddings = embedding_factory(
        "openai",
        model=settings.embedding_model,
        client=AsyncOpenAI(api_key=settings.chat_api_key, base_url=settings.embedding_url),
        interface="modern",
    )
    return MetricasRagas(
        fidelidade=Faithfulness(llm=llm),
        relevancia_resposta=AnswerRelevancy(llm=llm, embeddings=embeddings),
        precisao_contexto=ContextPrecisionWithoutReference(llm=llm),
    )


async def avaliar_resposta(
    pergunta: str,
    resposta: str,
    contextos: list[str],
    *,
    metricas: MetricasRagas | None = None,
) -> AvaliacaoRagas:
    metricas = metricas or criar_metricas()
    fidelidade, relevancia, precisao = await asyncio.gather(
        metricas.fidelidade.ascore(
            user_input=pergunta, response=resposta, retrieved_contexts=contextos
        ),
        metricas.relevancia_resposta.ascore(user_input=pergunta, response=resposta),
        metricas.precisao_contexto.ascore(
            user_input=pergunta, response=resposta, retrieved_contexts=contextos
        ),
    )
    return AvaliacaoRagas(
        fidelidade=fidelidade.value,
        relevancia_resposta=relevancia.value,
        precisao_contexto=precisao.value,
    )
