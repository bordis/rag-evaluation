"""Regras dos estudos: um aberto por vez, e so com o desenho completo pronto para responder."""

import httpx
from sqlmodel import Session, select

from app.core.config import get_settings
from app.models.pipeline import Pipeline
from app.models.study import StatusEstudo, Study

PIPELINES_DO_DESENHO = 4


def reordenador_no_ar() -> bool:
    try:
        httpx.get(f"{get_settings().reranker_url}/health", timeout=5).raise_for_status()
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
        return "O reordenador não está no ar: suba o container rag-reranker e aguarde ficar pronto."
    return None
