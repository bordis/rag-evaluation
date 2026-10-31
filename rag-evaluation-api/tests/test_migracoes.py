import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlmodel import SQLModel


@pytest.mark.integration
def test_migracoes_cobrem_todos_os_modelos(engine_teste):
    """Se um modelo mudar sem migracao correspondente, este teste acusa o diff."""
    with engine_teste.connect() as conexao:
        contexto = MigrationContext.configure(conexao)
        diferencas = compare_metadata(contexto, SQLModel.metadata)
    assert diferencas == []


@pytest.mark.integration
def test_todas_as_tabelas_esperadas_existem(engine_teste):
    from sqlalchemy import inspect

    tabelas = set(inspect(engine_teste).get_table_names())
    assert {
        "pipelines",
        "documents",
        "document_ingestions",
        "evaluation_sessions",
        "question_rounds",
        "pipeline_answers",
        "answer_stage_metrics",
        "retrieved_chunks",
    } <= tabelas
