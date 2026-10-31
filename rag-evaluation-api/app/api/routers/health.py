from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import engine
from app.core.milvus import construir_cliente
from app.schemas.health import ComponenteSaude, RespostaSaude

router = APIRouter(prefix="/api", tags=["saude"])


def verificar_postgres() -> ComponenteSaude:
    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
        return ComponenteSaude(nome="postgres", disponivel=True)
    except Exception as erro:
        return ComponenteSaude(nome="postgres", disponivel=False, erro=str(erro)[:200])


def verificar_milvus() -> ComponenteSaude:
    try:
        construir_cliente().list_collections()
        return ComponenteSaude(nome="milvus", disponivel=True)
    except Exception as erro:
        return ComponenteSaude(nome="milvus", disponivel=False, erro=str(erro)[:200])


def verificar_docling() -> ComponenteSaude:
    import httpx

    try:
        resposta = httpx.get(f"{get_settings().docling_url}/health", timeout=5)
        resposta.raise_for_status()
        return ComponenteSaude(nome="docling", disponivel=True)
    except Exception as erro:
        return ComponenteSaude(nome="docling", disponivel=False, erro=str(erro)[:200])


def verificar_reordenador() -> ComponenteSaude:
    import httpx

    try:
        resposta = httpx.get(f"{get_settings().reranker_url}/health", timeout=5)
        resposta.raise_for_status()
        return ComponenteSaude(nome="reordenador", disponivel=True)
    except Exception as erro:
        return ComponenteSaude(nome="reordenador", disponivel=False, erro=str(erro)[:200])


@router.get("/health")
def verificar_saude(response: Response) -> RespostaSaude:
    componentes = [
        verificar_postgres(),
        verificar_milvus(),
        verificar_docling(),
        verificar_reordenador(),
    ]
    saudavel = all(componente.disponivel for componente in componentes)
    if not saudavel:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return RespostaSaude(saudavel=saudavel, componentes=componentes)
