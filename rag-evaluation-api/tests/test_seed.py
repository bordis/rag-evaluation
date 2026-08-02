from sqlmodel import Session, func, select

from app.models.pipeline import ParserType, Pipeline
from app.seed import semear_pipelines


def test_cria_os_quatro_pipelines(sessao: Session):
    semear_pipelines(sessao)
    codigos = sessao.exec(select(Pipeline.codigo).order_by(Pipeline.codigo)).all()
    assert list(codigos) == ["pipeline-1", "pipeline-2", "pipeline-3", "pipeline-4"]


def test_desenho_fatorial_dos_parsers(sessao: Session):
    semear_pipelines(sessao)
    por_codigo = {p.codigo: p for p in sessao.exec(select(Pipeline)).all()}
    assert por_codigo["pipeline-1"].parser is ParserType.RAW
    assert por_codigo["pipeline-2"].parser is ParserType.DOCLING
    assert por_codigo["pipeline-3"].parser is ParserType.RAW
    assert por_codigo["pipeline-4"].parser is ParserType.DOCLING


def test_pipelines_de_controle_nascem_com_retrieval_desligado(sessao: Session):
    semear_pipelines(sessao)
    por_codigo = {p.codigo: p for p in sessao.exec(select(Pipeline)).all()}
    for codigo in ("pipeline-1", "pipeline-2"):
        config = por_codigo[codigo].config
        assert config["query_rewriting"] is False
        assert config["reranking"] is False
        assert config["hybrid_search"] is False
        assert config["sliding_window"]["ativo"] is False


def test_cada_pipeline_aponta_para_sua_propria_collection(sessao: Session):
    semear_pipelines(sessao)
    nomes = {p.collection_name for p in sessao.exec(select(Pipeline)).all()}
    assert nomes == {"evaluation1", "evaluation2", "evaluation3", "evaluation4"}


def test_semear_duas_vezes_nao_duplica(sessao: Session):
    semear_pipelines(sessao)
    semear_pipelines(sessao)
    total = sessao.exec(select(func.count()).select_from(Pipeline)).one()
    assert total == 4


def test_semear_de_novo_preserva_config_editada(sessao: Session):
    semear_pipelines(sessao)
    terceiro = sessao.exec(select(Pipeline).where(Pipeline.codigo == "pipeline-3")).one()
    terceiro.config = {**terceiro.config, "reranking": True}
    sessao.add(terceiro)
    sessao.commit()

    semear_pipelines(sessao)

    terceiro = sessao.exec(select(Pipeline).where(Pipeline.codigo == "pipeline-3")).one()
    assert terceiro.config["reranking"] is True
