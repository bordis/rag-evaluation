import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models.document import Document, StatusDocumento
from app.models.evaluation import EvaluationSession, PipelineAnswer, QuestionRound
from app.models.pipeline import ParserType, Pipeline


def _pipeline(sessao: Session, codigo: str) -> Pipeline:
    pipeline = Pipeline(
        codigo=codigo,
        nome=f"Pipeline {codigo}",
        parser=ParserType.RAW,
        collection_name=f"col_{codigo}",
        config={"top_k": 5},
    )
    sessao.add(pipeline)
    sessao.commit()
    sessao.refresh(pipeline)
    return pipeline


def _documento(sessao: Session) -> Document:
    documento = Document(
        slug="lgpd",
        titulo="LGPD",
        area="Direito",
        descricao="Lei 13.709/2018",
        icone="⚖️",
        nome_arquivo_original="lgpd.pdf",
        mime_type="application/pdf",
        tamanho_bytes=1024,
        sha256="a" * 64,
    )
    sessao.add(documento)
    sessao.commit()
    sessao.refresh(documento)
    return documento


def test_documento_nasce_em_processando(sessao: Session):
    assert _documento(sessao).status is StatusDocumento.PROCESSANDO


def test_slug_de_documento_e_unico(sessao: Session):
    _documento(sessao)
    with pytest.raises(IntegrityError):
        _documento(sessao)


def test_codigo_de_pipeline_e_unico(sessao: Session):
    _pipeline(sessao, "pipeline-1")
    with pytest.raises(IntegrityError):
        _pipeline(sessao, "pipeline-1")


def test_rodada_nasce_sem_escolha(sessao: Session):
    documento = _documento(sessao)
    avaliador = EvaluationSession()
    sessao.add(avaliador)
    sessao.commit()

    rodada = QuestionRound(
        session_id=avaliador.id, document_id=documento.id, pergunta="O que e dado pessoal?"
    )
    sessao.add(rodada)
    sessao.commit()

    assert rodada.escolha_answer_id is None
    assert rodada.escolhido_em is None


def test_rotulo_cego_nao_se_repete_na_mesma_rodada(sessao: Session):
    documento = _documento(sessao)
    avaliador = EvaluationSession()
    sessao.add(avaliador)
    sessao.commit()
    rodada = QuestionRound(
        session_id=avaliador.id, document_id=documento.id, pergunta="pergunta"
    )
    sessao.add(rodada)
    sessao.commit()

    p1 = _pipeline(sessao, "pipeline-1")
    p2 = _pipeline(sessao, "pipeline-2")
    sessao.add(PipelineAnswer(round_id=rodada.id, pipeline_id=p1.id, rotulo_cego="A", texto="x"))
    sessao.commit()

    sessao.add(PipelineAnswer(round_id=rodada.id, pipeline_id=p2.id, rotulo_cego="A", texto="y"))
    with pytest.raises(IntegrityError):
        sessao.commit()


def test_pipeline_nao_responde_duas_vezes_na_mesma_rodada(sessao: Session):
    documento = _documento(sessao)
    avaliador = EvaluationSession()
    sessao.add(avaliador)
    sessao.commit()
    rodada = QuestionRound(
        session_id=avaliador.id, document_id=documento.id, pergunta="pergunta"
    )
    sessao.add(rodada)
    sessao.commit()

    p1 = _pipeline(sessao, "pipeline-1")
    sessao.add(PipelineAnswer(round_id=rodada.id, pipeline_id=p1.id, rotulo_cego="A", texto="x"))
    sessao.commit()

    sessao.add(PipelineAnswer(round_id=rodada.id, pipeline_id=p1.id, rotulo_cego="B", texto="y"))
    with pytest.raises(IntegrityError):
        sessao.commit()


def test_config_em_jsonb_sobrevive_ao_roundtrip(sessao: Session):
    _pipeline(sessao, "pipeline-3")
    pipeline = sessao.exec(select(Pipeline).where(Pipeline.codigo == "pipeline-3")).one()
    pipeline.config = {"top_k": 8, "sliding_window": {"ativo": True, "tamanho": 2}}
    sessao.add(pipeline)
    sessao.commit()
    sessao.refresh(pipeline)
    assert pipeline.config["sliding_window"]["tamanho"] == 2


def test_id_de_documento_e_uuid(sessao: Session):
    assert isinstance(_documento(sessao).id, uuid.UUID)
