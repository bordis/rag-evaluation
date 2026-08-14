from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.api.routers import documents, evaluation, health, sessions
from app.core.config import get_settings
from app.core.db import engine, rodar_migracoes
from app.core.milvus import construir_cliente, criar_collections
from app.seed import semear_pipelines


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Sobe o schema, os pipelines e as collections antes de aceitar requisicoes."""
    rodar_migracoes()
    with Session(engine) as sessao:
        semear_pipelines(sessao)
    criar_collections(construir_cliente())
    yield


app = FastAPI(
    title="rag-evaluation-api",
    description="Backend do estudo de avaliacao cega de pipelines RAG.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(sessions.router)
app.include_router(evaluation.router)
