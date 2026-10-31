"""Embeddings via OpenAI, com lotes e contagem de tokens.

A contagem de tokens nao e detalhe operacional: e um dos dois numeros que a dissertacao compara
entre os pipelines. Por isso ela sobe junto com os vetores em vez de ficar num log.
"""

from dataclasses import dataclass
from functools import lru_cache

from openai import OpenAI

from app.core.config import get_settings

# A API aceita ate 2048 entradas por chamada, mas lotes menores mantem o payload pequeno e
# tornam o retry do SDK barato quando um 429 aparece no meio de um documento longo.
TAMANHO_DO_LOTE = 64


@dataclass(frozen=True)
class ResultadoEmbedding:
    vetores: list[list[float]]
    tokens: int


@lru_cache
def cliente_embedding() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        api_key=settings.chat_api_key,
        base_url=settings.embedding_url,
        max_retries=3,
    )


def embutir_textos(textos: list[str], *, cliente: OpenAI | None = None) -> ResultadoEmbedding:
    if not textos:
        return ResultadoEmbedding(vetores=[], tokens=0)

    settings = get_settings()
    cliente = cliente or cliente_embedding()

    vetores: list[list[float]] = []
    tokens = 0
    for inicio in range(0, len(textos), TAMANHO_DO_LOTE):
        lote = textos[inicio : inicio + TAMANHO_DO_LOTE]
        resposta = cliente.embeddings.create(
            model=settings.embedding_model,
            input=lote,
            dimensions=settings.embedding_dimensions,
        )
        # A API nao garante a ordem de `data`; alinhar pelo `index` evita associar o vetor
        # errado ao chunk errado — um bug que so apareceria como retrieval ruim.
        for item in sorted(resposta.data, key=lambda item: item.index):
            vetores.append(list(item.embedding))
        tokens += resposta.usage.prompt_tokens

    return ResultadoEmbedding(vetores=vetores, tokens=tokens)
