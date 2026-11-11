import os
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

_ENV = Path(__file__).resolve().parents[1] / ".env"


def _env_tem_chave_real() -> bool:
    if not _ENV.exists():
        return False
    return any(
        linha.startswith("CHAT_API_KEY=") and linha.removeprefix("CHAT_API_KEY=").strip()
        for linha in (bruta.strip() for bruta in _ENV.read_text(encoding="utf-8").splitlines())
    )


# Sem chave nenhuma o Settings nem instancia e a suite unitaria inteira quebra. Mas a chave falsa
# so entra quando o .env nao traz uma de verdade: no pydantic-settings a variavel de ambiente tem
# prioridade sobre o .env, entao um setdefault incondicional mascararia a chave real e derrubaria
# os testes de integracao que chamam a OpenAI com AuthenticationError.
if not _env_tem_chave_real():
    os.environ.setdefault("CHAT_API_KEY", "sk-teste")

# Importar os modulos de modelo registra as tabelas no metadata do SQLModel.
from app.models import document, evaluation, pipeline, study, telemetry  # noqa: E402,F401

USUARIO_TESTE_SUB = "avaliador-teste"


def _usuario_teste():
    from app.core.auth import ROLE_ADMIN, ROLE_AVALIADOR, Usuario

    return Usuario(sub=USUARIO_TESTE_SUB, roles=frozenset({ROLE_AVALIADOR, ROLE_ADMIN}))


USUARIO_TESTE = _usuario_teste()


def entrar_como(sub: str) -> None:
    """Troca o login do `cliente`: cada login tem a propria sessao no estudo."""
    from app.core.auth import Usuario, usuario_atual
    from app.main import app

    usuario = Usuario(sub=sub, roles=USUARIO_TESTE.roles)
    app.dependency_overrides[usuario_atual] = lambda: usuario


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

    from app.core.auth import usuario_atual
    from app.core.db import get_session
    from app.main import app

    app.dependency_overrides[get_session] = lambda: sessao
    # O token do Keycloak e validado em tests/api/test_auth.py; aqui o login ja passou.
    app.dependency_overrides[usuario_atual] = lambda: USUARIO_TESTE
    yield TestClient(app)
    app.dependency_overrides.clear()
