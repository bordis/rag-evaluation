import pytest
from sqlmodel import Session, select

from app.models.document import Document
from app.models.evaluation import EvaluationSession, PipelineAnswer, QuestionRound
from app.models.pipeline import Pipeline
from app.models.study import Study
from app.models.telemetry import AnswerStageMetric, RetrievedChunk
from app.seed import semear_pipelines
from app.services.evaluation import (
    ErroDeRodada,
    contar_respondidas,
    criar_rodada,
    registrar_escolha,
    respostas_da_rodada,
    rodada_pendente,
    sortear_rotulos,
)
from tests.fakes import PipelineFalso, dependencias_falsas


@pytest.fixture(name="cenario")
def cenario_fixture(sessao: Session):
    semear_pipelines(sessao)
    estudo = Study(nome="Coleta")
    sessao.add(estudo)
    sessao.commit()
    avaliador = EvaluationSession(study_id=estudo.id, termo_versao="v1")
    documento = Document(
        slug="lgpd",
        titulo="LGPD",
        area="Direito",
        nome_arquivo_original="lgpd.pdf",
        mime_type="application/pdf",
        tamanho_bytes=10,
        sha256="a" * 64,
    )
    sessao.add(avaliador)
    sessao.add(documento)
    sessao.commit()
    sessao.refresh(avaliador)
    sessao.refresh(documento)
    return avaliador, documento


def test_sorteio_nunca_repete_rotulo_e_cobre_todos():
    for _ in range(200):
        assert sorted(sortear_rotulos(4)) == ["A", "B", "C", "D"]


def test_sorteio_distribui_os_rotulos_ao_longo_de_muitas_execucoes():
    # Ordem fixa deixaria sempre a mesma letra na primeira posicao — e a posicao viraria pista.
    primeiras = {sortear_rotulos(4)[0] for _ in range(200)}
    assert len(primeiras) > 1


async def test_rodada_gera_uma_resposta_por_pipeline_com_rotulos_distintos(sessao, cenario):
    # Arrange
    avaliador, documento = cenario
    executor = PipelineFalso()

    # Act
    rodada = await criar_rodada(
        sessao,
        avaliador.id,
        documento.id,
        "O que a lei diz?",
        dependencias=dependencias_falsas(executor),
    )

    # Assert
    respostas = respostas_da_rodada(sessao, rodada.id)
    assert len(respostas) == 4
    assert [item.rotulo_cego for item in respostas] == ["A", "B", "C", "D"]
    assert len({item.pipeline_id for item in respostas}) == 4
    assert {codigo for codigo, _, _ in executor.chamadas} == {
        "pipeline-1",
        "pipeline-2",
        "pipeline-3",
        "pipeline-4",
    }
    assert {pergunta for _, _, pergunta in executor.chamadas} == {"O que a lei diz?"}


async def test_rodada_grava_metricas_e_chunks_de_cada_resposta(sessao, cenario):
    # Arrange
    avaliador, documento = cenario

    # Act
    rodada = await criar_rodada(
        sessao,
        avaliador.id,
        documento.id,
        "Pergunta?",
        dependencias=dependencias_falsas(PipelineFalso()),
    )

    # Assert
    ids = [item.id for item in respostas_da_rodada(sessao, rodada.id)]
    metricas = sessao.exec(
        select(AnswerStageMetric).where(AnswerStageMetric.answer_id.in_(ids))  # type: ignore[union-attr]
    ).all()
    chunks = sessao.exec(
        select(RetrievedChunk).where(RetrievedChunk.answer_id.in_(ids))  # type: ignore[union-attr]
    ).all()
    assert len(metricas) == 8  # 2 etapas x 4 pipelines
    assert {metrica.ordem for metrica in metricas} == {1, 2}
    assert len(chunks) == 8
    assert {chunk.posicao for chunk in chunks} == {1, 2}


async def test_falha_de_um_unico_pipeline_invalida_a_rodada_inteira(sessao, cenario):
    # Arrange
    avaliador, documento = cenario

    # Act / Assert
    with pytest.raises(ErroDeRodada):
        await criar_rodada(
            sessao,
            avaliador.id,
            documento.id,
            "Pergunta?",
            dependencias=dependencias_falsas(PipelineFalso(falhar_em="pipeline-3")),
        )

    # Nada persistido: escolher entre 3 respostas produziria um dado que nao agrega com os demais.
    assert sessao.exec(select(QuestionRound)).all() == []
    assert sessao.exec(select(PipelineAnswer)).all() == []


async def test_pipeline_inativo_fica_de_fora_da_rodada(sessao, cenario):
    # Arrange
    avaliador, documento = cenario
    pipeline = sessao.exec(select(Pipeline).where(Pipeline.codigo == "pipeline-4")).one()
    pipeline.ativo = False
    sessao.add(pipeline)
    sessao.commit()

    # Act
    rodada = await criar_rodada(
        sessao,
        avaliador.id,
        documento.id,
        "Pergunta?",
        dependencias=dependencias_falsas(PipelineFalso()),
    )

    # Assert
    assert [item.rotulo_cego for item in respostas_da_rodada(sessao, rodada.id)] == ["A", "B", "C"]


async def test_contagem_so_considera_rodada_decidida(sessao, cenario):
    # Arrange
    avaliador, documento = cenario
    rodada = await criar_rodada(
        sessao,
        avaliador.id,
        documento.id,
        "Pergunta?",
        dependencias=dependencias_falsas(PipelineFalso()),
    )

    # Assert — perguntar e abandonar nao consome a cota do documento
    assert contar_respondidas(sessao, avaliador.id, documento.id) == 0
    assert rodada_pendente(sessao, avaliador.id, documento.id) is not None

    # Act
    registrar_escolha(sessao, rodada, respostas_da_rodada(sessao, rodada.id)[0])

    # Assert
    assert contar_respondidas(sessao, avaliador.id, documento.id) == 1
    assert rodada_pendente(sessao, avaliador.id, documento.id) is None
    assert rodada.escolhido_em is not None
