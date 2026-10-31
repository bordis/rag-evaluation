"""Unico ponto de contato com o Chat Completions.

Reescrita de query, re-ranking e geracao fazem a mesma coisa: mandam mensagens e precisam do
texto mais a contagem de tokens. Centralizar garante que as tres registrem a telemetria do mesmo
jeito — o que e pre-requisito para comparar tokens entre etapas na analise.
"""

from dataclasses import dataclass
from functools import lru_cache

from openai import OpenAI

from app.core.config import get_settings


@dataclass(frozen=True)
class RespostaLLM:
    texto: str
    tokens_prompt: int
    tokens_completion: int
    tokens_total: int
    modelo: str


@lru_cache
def cliente_chat() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        api_key=settings.chat_api_key,
        base_url=settings.chat_base_url,
        max_retries=3,
    )


def conversar(
    mensagens: list[dict[str, str]],
    *,
    cliente: OpenAI | None = None,
    resposta_json: bool = False,
) -> RespostaLLM:
    settings = get_settings()
    cliente = cliente or cliente_chat()

    extras: dict = {}
    if resposta_json:
        extras["response_format"] = {"type": "json_object"}

    resposta = cliente.chat.completions.create(
        model=settings.chat_model,
        messages=mensagens,
        temperature=settings.chat_temperature,
        # max_tokens esta depreciado no SDK; max_completion_tokens e o parametro atual.
        max_completion_tokens=settings.chat_max_tokens,
        **extras,
    )

    uso = resposta.usage
    return RespostaLLM(
        texto=(resposta.choices[0].message.content or "").strip(),
        tokens_prompt=uso.prompt_tokens if uso else 0,
        tokens_completion=uso.completion_tokens if uso else 0,
        tokens_total=uso.total_tokens if uso else 0,
        # O modelo vem da resposta, nao da config: a API devolve o snapshot exato usado, que e o
        # que precisa constar na dissertacao para a medicao ser reproduzivel.
        modelo=resposta.model,
    )
