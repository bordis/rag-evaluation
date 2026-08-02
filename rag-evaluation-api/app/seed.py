"""Semeadura dos 4 pipelines do desenho fatorial 2x2.

Parser (raw/Docling) x retrieval (fixo/configuravel). Comparar 1<->2 e 3<->4 mede o efeito do
parser; comparar 1<->3 e 2<->4 mede o efeito do retrieval avancado.
"""

from sqlmodel import Session, select

from app.core.config import get_settings
from app.models.pipeline import ParserType, Pipeline

FLAGS_RETRIEVAL = ("query_rewriting", "reranking", "hybrid_search", "sliding_window")

CODIGOS_DE_CONTROLE = ("pipeline-1", "pipeline-2")


def _config(avancado: bool) -> dict:
    settings = get_settings()
    return {
        "query_rewriting": avancado,
        "reranking": avancado,
        "hybrid_search": avancado,
        "sliding_window": {"ativo": avancado, "tamanho": settings.sliding_window_size},
        "top_k": settings.rag_search_limit,
    }


CONFIG_PADRAO_CONTROLE = _config(avancado=False)


def _definicoes() -> list[dict]:
    collections = get_settings().collection_por_codigo
    return [
        {
            "codigo": "pipeline-1",
            "nome": "Raw + retrieval basico",
            "descricao": "Leitura raw do documento e busca vetorial densa. Braco de controle.",
            "parser": ParserType.RAW,
            "collection_name": collections["pipeline-1"],
            "config": _config(avancado=False),
        },
        {
            "codigo": "pipeline-2",
            "nome": "Docling + retrieval basico",
            "descricao": (
                "Parsing estruturado via Docling e busca vetorial densa. Braco de controle."
            ),
            "parser": ParserType.DOCLING,
            "collection_name": collections["pipeline-2"],
            "config": _config(avancado=False),
        },
        {
            "codigo": "pipeline-3",
            "nome": "Raw + retrieval avancado",
            "descricao": "Leitura raw com query rewriting, re-ranking, hybrid search e janela.",
            "parser": ParserType.RAW,
            "collection_name": collections["pipeline-3"],
            "config": _config(avancado=True),
        },
        {
            "codigo": "pipeline-4",
            "nome": "Docling + retrieval avancado",
            "descricao": "Docling com query rewriting, re-ranking, hybrid search e janela.",
            "parser": ParserType.DOCLING,
            "collection_name": collections["pipeline-4"],
            "config": _config(avancado=True),
        },
    ]


def semear_pipelines(sessao: Session) -> list[Pipeline]:
    """Cria os pipelines que faltam. Idempotente: nunca sobrescreve config ja editada."""
    criados: list[Pipeline] = []
    for definicao in _definicoes():
        existente = sessao.exec(
            select(Pipeline).where(Pipeline.codigo == definicao["codigo"])
        ).first()
        if existente is not None:
            continue
        pipeline = Pipeline(**definicao)
        sessao.add(pipeline)
        criados.append(pipeline)

    if criados:
        sessao.commit()
        for pipeline in criados:
            sessao.refresh(pipeline)
    return criados
