"""HyDE: um LLM escreve uma resposta hipotetica, e a busca parte dela. So nos pipelines 3 e 4.

A resposta nunca chega ao avaliador: serve apenas para aproximar a consulta da forma e do
vocabulario dos trechos do documento.
"""

from openai import OpenAI

from app.models.telemetry import EtapaPipeline
from app.rag.llm import conversar
from app.rag.retrieval.base import MetricaEtapa, metrica_de_llm
from app.telemetry.recorder import Cronometro

INSTRUCAO = (
    "Escreva, em português do Brasil, um parágrafo curto que responda à pergunta do usuário como "
    "se fosse um trecho do documento em que a resposta aparece. Use a linguagem formal e os termos "
    "técnicos que esse documento usaria. Responda apenas com o parágrafo, sem aspas e sem prefixo."
)


def gerar_documento_hipotetico(
    pergunta: str, *, cliente: OpenAI | None = None
) -> tuple[str | None, MetricaEtapa]:
    """Devolve o paragrafo, ou None se vazio: a pergunta sozinha ainda e uma consulta valida."""
    with Cronometro() as relogio:
        resposta = conversar(
            [
                {"role": "system", "content": INSTRUCAO},
                {"role": "user", "content": pergunta},
            ],
            cliente=cliente,
        )

    hipotetico = resposta.texto.strip() or None
    detalhes = {"pergunta": pergunta, "hipotetico": hipotetico, "fallback": hipotetico is None}
    return hipotetico, metrica_de_llm(EtapaPipeline.HYDE, relogio.ms, resposta, detalhes)
