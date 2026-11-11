"""Regras dos estudos: um aberto por vez, e so com o desenho completo pronto para responder."""

import httpx
from sqlmodel import Session, select

from app.core.config import get_settings
from app.models.pipeline import Pipeline
from app.models.study import StatusEstudo, Study
from app.rag.generation import INSTRUCAO_SISTEMA
from app.rag.retrieval.hyde import INSTRUCAO as INSTRUCAO_HYDE

PIPELINES_DO_DESENHO = 4


def reordenador_no_ar() -> bool:
    try:
        httpx.get(get_settings().reranker_health_url, timeout=5).raise_for_status()
    except httpx.HTTPError:
        return False
    return True


def estudo_aberto(sessao: Session) -> Study | None:
    return sessao.exec(select(Study).where(Study.status == StatusEstudo.ABERTO)).first()


def impedimento_para_abrir(sessao: Session) -> str | None:
    """Uma rodada que falharia na primeira pergunta deve impedir a abertura, nao o avaliador."""
    if estudo_aberto(sessao) is not None:
        return "Já existe um estudo aberto. Encerre-o antes de iniciar outro."
    ativos = sessao.exec(select(Pipeline).where(Pipeline.ativo)).all()
    if len(ativos) != PIPELINES_DO_DESENHO:
        return f"O desenho exige {PIPELINES_DO_DESENHO} pipelines ativos; há {len(ativos)}."
    precisa_reordenar = any((pipeline.config or {}).get("reranking") for pipeline in ativos)
    if precisa_reordenar and not reordenador_no_ar():
        return "O reordenador não está no ar: confira RERANKER_URL e o serviço de reordenação."
    return None


def retrato_do_ambiente(sessao: Session) -> dict:
    """O que a tabela de configuracao da dissertacao precisa, como estava ao abrir o estudo."""
    settings = get_settings()
    pipelines = sessao.exec(select(Pipeline).order_by(Pipeline.codigo)).all()  # type: ignore[arg-type]
    return {
        "geracao": {
            "modelo": settings.chat_model,
            "temperatura": settings.chat_temperature,
            "max_tokens": settings.chat_max_tokens,
            "prompt": INSTRUCAO_SISTEMA,
            "prompt_hyde": INSTRUCAO_HYDE,
        },
        "embedding": settings.embedding_model,
        "embedding_consulta": settings.embedding_model_query,
        "embedding_dimensoes": settings.embedding_dimensions,
        "reordenador": settings.reranker_url,
        "juiz_ragas": settings.ragas_llm_model,
        "limite_perguntas": settings.max_perguntas,
        "pipelines": {pipeline.codigo: pipeline.config for pipeline in pipelines},
    }
