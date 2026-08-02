import pytest

from app.core.config import get_settings
from app.core.milvus import (
    ANALISADOR_PORTUGUES,
    CAMPO_DENSO,
    CAMPO_ESPARSO,
    CAMPO_TEXTO,
    construir_cliente,
    criar_collections,
    remover_collections,
)


def test_analisador_trata_acentos_e_stemming_do_portugues():
    """Sem asciifolding, 'protecao' e 'protecao' viram termos distintos no BM25."""
    assert "asciifolding" in ANALISADOR_PORTUGUES["filter"]
    filtros = ANALISADOR_PORTUGUES["filter"]
    stemmer = next(f for f in filtros if isinstance(f, dict) and f["type"] == "stemmer")
    assert stemmer["language"] == "portuguese"
    stop = next(f for f in filtros if isinstance(f, dict) and f["type"] == "stop")
    assert stop["stop_words"] == ["_portuguese_"]


@pytest.fixture
def cliente_limpo():
    cliente = construir_cliente()
    remover_collections(cliente)
    yield cliente
    remover_collections(cliente)


@pytest.mark.integration
def test_cria_uma_collection_por_pipeline(cliente_limpo):
    criadas = criar_collections(cliente_limpo)
    assert sorted(criadas) == ["evaluation1", "evaluation2", "evaluation3", "evaluation4"]


@pytest.mark.integration
def test_collections_tem_os_campos_do_schema(cliente_limpo):
    criar_collections(cliente_limpo)
    descricao = cliente_limpo.describe_collection("evaluation1")
    nomes = {campo["name"] for campo in descricao["fields"]}
    assert nomes == {
        "id",
        "document_id",
        "chunk_index",
        CAMPO_TEXTO,
        CAMPO_ESPARSO,
        CAMPO_DENSO,
        "metadados",
    }


@pytest.mark.integration
def test_funcao_bm25_declarada_na_criacao(cliente_limpo):
    """BM25 nao pode ser adicionado depois — se faltar aqui, so recriando a collection."""
    criar_collections(cliente_limpo)
    descricao = cliente_limpo.describe_collection("evaluation3")
    funcoes = descricao.get("functions", [])
    assert any(f["name"] == "text_bm25" for f in funcoes)


@pytest.mark.integration
def test_dimensao_do_vetor_denso_bate_com_a_configuracao(cliente_limpo):
    criar_collections(cliente_limpo)
    descricao = cliente_limpo.describe_collection("evaluation1")
    denso = next(c for c in descricao["fields"] if c["name"] == CAMPO_DENSO)
    assert denso["params"]["dim"] == get_settings().embedding_dimensions


@pytest.mark.integration
def test_criar_duas_vezes_nao_falha(cliente_limpo):
    criar_collections(cliente_limpo)
    assert criar_collections(cliente_limpo) == []
