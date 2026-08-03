"""Tipos compartilhados pelas etapas de consulta.

O que unifica as etapas nao e a assinatura — reescrita produz uma query, busca produz candidatos,
re-rank e janela transformam candidatos. O que unifica e a `MetricaEtapa`: e ela que permite
responder `SELECT etapa, AVG(duracao_ms) ... GROUP BY pipeline, etapa` na analise.
"""

from dataclasses import dataclass, field

from app.core.milvus import CAMPO_CHUNK, CAMPO_TEXTO
from app.models.telemetry import EtapaPipeline
from app.rag.llm import RespostaLLM


@dataclass
class Candidato:
    milvus_id: int
    chunk_index: int
    texto: str
    score_denso: float | None = None
    score_esparso: float | None = None
    score_final: float = 0.0
    # Chunks trazidos pela janela deslizante nao foram recuperados por merito proprio; herdam o
    # score da ancora. A marca distingue os dois casos na analise.
    vizinho: bool = False


@dataclass(frozen=True)
class MetricaEtapa:
    etapa: EtapaPipeline
    duracao_ms: int
    tokens_prompt: int | None = None
    tokens_completion: int | None = None
    tokens_total: int | None = None
    modelo: str | None = None
    detalhes: dict = field(default_factory=dict)


def candidato_de_hit(hit: dict) -> Candidato:
    """Converte um resultado do Milvus. `distance` e o score da metrica configurada no indice."""
    entidade = hit.get("entity") or {}
    return Candidato(
        milvus_id=int(hit["id"]),
        chunk_index=int(entidade[CAMPO_CHUNK]),
        texto=entidade[CAMPO_TEXTO],
        score_final=float(hit["distance"]),
    )


def metrica_de_llm(
    etapa: EtapaPipeline, duracao_ms: int, resposta: RespostaLLM, detalhes: dict
) -> MetricaEtapa:
    return MetricaEtapa(
        etapa=etapa,
        duracao_ms=duracao_ms,
        tokens_prompt=resposta.tokens_prompt,
        tokens_completion=resposta.tokens_completion,
        tokens_total=resposta.tokens_total,
        modelo=resposta.modelo,
        detalhes=detalhes,
    )
