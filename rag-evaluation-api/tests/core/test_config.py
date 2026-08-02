import pytest
from pydantic import ValidationError

from app.core.config import Settings

# Atencao: o construtor do pydantic-settings aceita nomes de CAMPO (minusculos), nao nomes de
# variavel de ambiente. Passar CHAT_API_KEY= aqui seria descartado por extra="ignore".
BASE = {
    "chat_api_key": "sk-teste",
    "db_url": "postgresql://localhost:5432",
    "db_name": "rag-evaluation",
    "db_username": "postgres",
    "db_password": "admin",
}


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **{**BASE, **overrides})


def test_compoe_url_do_sqlalchemy_a_partir_das_quatro_variaveis():
    assert (
        _settings().sqlalchemy_url
        == "postgresql+psycopg://postgres:admin@localhost:5432/rag-evaluation"
    )


def test_remove_prefixo_jdbc_herdado_do_formato_java():
    settings = _settings(db_url="jdbc:postgresql://localhost:5432")
    assert settings.sqlalchemy_url.startswith("postgresql+psycopg://")
    assert "jdbc" not in settings.sqlalchemy_url


def test_monta_uri_do_milvus():
    assert _settings(milvus_host="localhost", milvus_port=19530).milvus_uri == (
        "http://localhost:19530"
    )


def test_mapeia_cada_codigo_de_pipeline_para_sua_collection():
    assert _settings().collection_por_codigo == {
        "pipeline-1": "evaluation1",
        "pipeline-2": "evaluation2",
        "pipeline-3": "evaluation3",
        "pipeline-4": "evaluation4",
    }


def test_divide_origens_de_cors_separadas_por_virgula():
    settings = _settings(cors_origins="http://localhost:4200, http://localhost:4300")
    assert settings.cors_origin_list == ["http://localhost:4200", "http://localhost:4300"]


def test_falta_de_chave_da_openai_impede_a_subida(monkeypatch):
    # O conftest define CHAT_API_KEY no ambiente; sem remover, o Settings a encontraria e
    # o teste passaria a nao verificar nada.
    monkeypatch.delenv("CHAT_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, db_url="postgresql://localhost:5432")
