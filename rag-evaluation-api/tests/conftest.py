import os

import pytest
from sqlmodel import Session, SQLModel, create_engine

os.environ.setdefault("CHAT_API_KEY", "sk-teste")

# Importar os modulos de modelo registra as tabelas no metadata do SQLModel.
from app.models import document, evaluation, pipeline, telemetry  # noqa: E402,F401

TEST_DB_URL = os.environ.get(
    "TEST_DB_URL", "postgresql+psycopg://postgres:admin@localhost:5432/rag-evaluation-test"
)


@pytest.fixture(name="engine_teste", scope="session")
def engine_teste_fixture():
    engine = create_engine(TEST_DB_URL)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="sessao")
def sessao_fixture(engine_teste):
    """Sessao isolada: cada teste roda numa transacao que sofre rollback ao final."""
    conexao = engine_teste.connect()
    transacao = conexao.begin()
    with Session(bind=conexao) as sessao:
        yield sessao
    # Testes que provocam IntegrityError ja desfizeram a transacao no commit falho.
    if transacao.is_active:
        transacao.rollback()
    conexao.close()


@pytest.fixture(name="cliente")
def cliente_fixture(sessao: Session):
    """TestClient com a sessao de teste no lugar da real.

    `TestClient(app)` sem `with` nao dispara o lifespan — os testes de contrato nao rodam
    migracoes nem tocam no Milvus.
    """
    from fastapi.testclient import TestClient

    from app.core.db import get_session
    from app.main import app

    app.dependency_overrides[get_session] = lambda: sessao
    yield TestClient(app)
    app.dependency_overrides.clear()
