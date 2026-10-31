"""Geracao da resposta a partir dos trechos recuperados.

Identica nos 4 pipelines, de proposito: se o prompt variasse entre os bracos, uma diferenca de
qualidade nao poderia ser atribuida ao parser nem ao retrieval.
"""

from openai import OpenAI

from app.models.telemetry import EtapaPipeline
from app.rag.llm import conversar
from app.rag.retrieval.base import Candidato, MetricaEtapa, metrica_de_llm
from app.telemetry.recorder import Cronometro

INSTRUCAO_SISTEMA = (
    "Você responde perguntas sobre um documento específico, em português do Brasil. "
    "Use exclusivamente o contexto fornecido abaixo. Se o contexto não contiver a resposta, "
    "diga que o documento não trata do assunto. Não invente dados, não complete lacunas com "
    "conhecimento externo e não cite fontes que não estejam no contexto. Seja direto e objetivo."
)


def _montar_prompt(pergunta: str, candidatos: list[Candidato]) -> str:
    if not candidatos:
        return f"Contexto: (nenhum trecho recuperado)\n\nPergunta: {pergunta}"
    contexto = "\n\n".join(
        f"[trecho {posicao}]\n{candidato.texto}"
        for posicao, candidato in enumerate(candidatos, start=1)
    )
    return f"Contexto:\n\n{contexto}\n\nPergunta: {pergunta}"


def gerar_resposta(
    pergunta: str, candidatos: list[Candidato], *, cliente: OpenAI | None = None
) -> tuple[str, MetricaEtapa]:
    with Cronometro() as relogio:
        resposta = conversar(
            [
                {"role": "system", "content": INSTRUCAO_SISTEMA},
                {"role": "user", "content": _montar_prompt(pergunta, candidatos)},
            ],
            cliente=cliente,
        )

    detalhes = {
        "trechos": len(candidatos),
        "caracteres": sum(len(candidato.texto) for candidato in candidatos),
        "sem_contexto": not candidatos,
    }
    return resposta.texto, metrica_de_llm(EtapaPipeline.GENERATION, relogio.ms, resposta, detalhes)
