"""Reescrita da pergunta em uma frase de busca. Ligada so nos pipelines 3 e 4."""

from openai import OpenAI

from app.models.telemetry import EtapaPipeline
from app.rag.llm import conversar
from app.rag.retrieval.base import MetricaEtapa, metrica_de_llm
from app.telemetry.recorder import Cronometro

INSTRUCAO = (
    "Você reescreve perguntas para melhorar a busca em uma base de documentos em português. "
    "Reescreva a pergunta do usuário como uma única frase de busca, preservando todos os termos "
    "técnicos, números de artigos e nomes próprios, e explicitando referências vagas como "
    "'aquela parte' ou 'esse trecho'. Responda apenas com a frase reescrita, sem aspas, sem "
    "prefixo e sem explicação."
)


def reescrever_query(pergunta: str, *, cliente: OpenAI | None = None) -> tuple[str, MetricaEtapa]:
    with Cronometro() as relogio:
        resposta = conversar(
            [
                {"role": "system", "content": INSTRUCAO},
                {"role": "user", "content": pergunta},
            ],
            cliente=cliente,
        )

    # Uma reescrita vazia nao pode custar a rodada: a pergunta original ja e uma query valida.
    reescrita = resposta.texto.strip()
    fallback = not reescrita
    query = pergunta if fallback else reescrita

    detalhes = {"original": pergunta, "reescrita": query, "fallback": fallback}
    return query, metrica_de_llm(EtapaPipeline.QUERY_REWRITING, relogio.ms, resposta, detalhes)
