"""Visao do pesquisador: navegar nas avaliacoes, analisar e exportar.

**Revela o pipeline de cada resposta.** O avaliador nunca chama estas rotas, mas elas estao abertas
nesta fase, por decisao do estudo. TODO: proteger com o login previsto (decisao 16 da ficha).
"""

import csv
import io
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.db import SessionDep
from app.models.document import Document
from app.models.evaluation import EvaluationSession, PipelineAnswer, QuestionRound
from app.models.pipeline import ParserType, Pipeline
from app.models.study import Study
from app.models.telemetry import AnswerStageMetric, RagasScore, RetrievedChunk
from app.schemas.admin import (
    AvaliacaoDetalhe,
    AvaliacaoResumo,
    ChunkDetalhe,
    MetricaDetalhe,
    RagasDetalhe,
    RagasDisparado,
    RagasSituacao,
    RespostaDetalhe,
    RodadaAdmin,
)
from app.services.analise import analisar_estudo, custo_usd, e_avancado
from app.services.ragas_rodadas import (
    calcular_em_segundo_plano,
    calcular_notas,
    contar_pendentes,
    reservar_calculo,
    rodadas_do_estudo,
    situacao_do_estudo,
)

router = APIRouter(prefix="/api/admin", tags=["administracao"])


def _obter_estudo(sessao: Session, study_id: uuid.UUID) -> Study:
    estudo = sessao.get(Study, study_id)
    if estudo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Estudo não encontrado.")
    return estudo


@router.get("/studies/{study_id}/avaliacoes")
def listar_avaliacoes(sessao: SessionDep, study_id: uuid.UUID) -> list[AvaliacaoResumo]:
    _obter_estudo(sessao, study_id)
    linhas = sessao.exec(
        select(
            QuestionRound.session_id,
            Document.id,
            Document.slug,
            Document.titulo,
            func.count(QuestionRound.id),
            func.count(QuestionRound.escolhido_em),
            func.count(QuestionRound.id).filter(QuestionRound.nenhuma_correta),
            func.min(QuestionRound.criado_em),
            func.max(QuestionRound.escolhido_em),
        )
        .join(EvaluationSession, EvaluationSession.id == QuestionRound.session_id)  # type: ignore[arg-type]
        .join(Document, Document.id == QuestionRound.document_id)  # type: ignore[arg-type]
        .where(EvaluationSession.study_id == study_id)
        .group_by(QuestionRound.session_id, Document.id, Document.slug, Document.titulo)  # type: ignore[arg-type]
        .order_by(func.min(QuestionRound.criado_em).desc())
    ).all()
    return [
        AvaliacaoResumo(
            session_id=session_id,
            document_id=document_id,
            documento_slug=slug,
            documento_titulo=titulo,
            rodadas=rodadas,
            decididas=decididas,
            nenhuma=nenhuma,
            inicio=inicio,
            fim=fim,
        )
        for (
            session_id,
            document_id,
            slug,
            titulo,
            rodadas,
            decididas,
            nenhuma,
            inicio,
            fim,
        ) in linhas
    ]


def _detalhar_resposta(
    sessao: Session, resposta: PipelineAnswer, pipeline: Pipeline, rodada: QuestionRound
) -> RespostaDetalhe:
    metricas = sessao.exec(
        select(AnswerStageMetric)
        .where(AnswerStageMetric.answer_id == resposta.id)
        .order_by(AnswerStageMetric.ordem)  # type: ignore[arg-type]
    ).all()
    chunks = sessao.exec(
        select(RetrievedChunk)
        .where(RetrievedChunk.answer_id == resposta.id)
        .order_by(RetrievedChunk.etapa, RetrievedChunk.posicao)  # type: ignore[arg-type]
    ).all()
    nota = sessao.get(RagasScore, resposta.id)
    return RespostaDetalhe(
        id=resposta.id,
        rotulo=resposta.rotulo_cego,
        posicao_exibida=resposta.posicao_exibida,
        pipeline_codigo=pipeline.codigo,
        pipeline_nome=pipeline.nome,
        escolhida=resposta.id == rodada.escolha_answer_id,
        texto=resposta.texto,
        config_snapshot=resposta.config_snapshot,
        metricas=[
            MetricaDetalhe(
                etapa=item.etapa,
                ordem=item.ordem,
                duracao_ms=item.duracao_ms,
                tokens_prompt=item.tokens_prompt,
                tokens_completion=item.tokens_completion,
                tokens_total=item.tokens_total,
                modelo=item.modelo,
                custo_usd=custo_usd(item.modelo, item.tokens_prompt, item.tokens_completion),
                detalhes=item.detalhes,
            )
            for item in metricas
        ],
        chunks=[ChunkDetalhe.model_validate(item, from_attributes=True) for item in chunks],
        ragas=RagasDetalhe.model_validate(nota, from_attributes=True) if nota else None,
    )


def _detalhar_rodada(sessao: Session, rodada: QuestionRound) -> RodadaAdmin:
    respostas = sessao.exec(
        select(PipelineAnswer, Pipeline)
        .join(Pipeline, Pipeline.id == PipelineAnswer.pipeline_id)  # type: ignore[arg-type]
        .where(PipelineAnswer.round_id == rodada.id)
        .order_by(PipelineAnswer.posicao_exibida)  # type: ignore[arg-type]
    ).all()
    tempo_decisao = (
        int((rodada.escolhido_em - rodada.respondido_em).total_seconds() * 1000)
        if rodada.escolhido_em and rodada.respondido_em
        else None
    )
    return RodadaAdmin(
        id=rodada.id,
        ordem=rodada.ordem,
        pergunta=rodada.pergunta,
        nenhuma_correta=rodada.nenhuma_correta,
        decidida=rodada.escolhido_em is not None,
        tempo_total_ms=rodada.tempo_total_ms,
        tempo_geracao_ms=rodada.tempo_geracao_ms,
        tempo_oculto_ms=rodada.tempo_oculto_ms,
        tempo_decisao_ms=tempo_decisao,
        criado_em=rodada.criado_em,
        respondido_em=rodada.respondido_em,
        escolhido_em=rodada.escolhido_em,
        respostas=[
            _detalhar_resposta(sessao, resposta, pipeline, rodada)
            for resposta, pipeline in respostas
        ],
    )


@router.get("/avaliacoes/{session_id}/{document_id}")
def obter_avaliacao(
    sessao: SessionDep, session_id: uuid.UUID, document_id: uuid.UUID
) -> AvaliacaoDetalhe:
    avaliador = sessao.get(EvaluationSession, session_id)
    documento = sessao.get(Document, document_id)
    if avaliador is None or documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Avaliação não encontrada.")
    estudo = _obter_estudo(sessao, avaliador.study_id)
    rodadas = sessao.exec(
        select(QuestionRound)
        .where(QuestionRound.session_id == session_id, QuestionRound.document_id == document_id)
        .order_by(QuestionRound.ordem)  # type: ignore[arg-type]
    ).all()
    return AvaliacaoDetalhe(
        session_id=session_id,
        document_id=document_id,
        documento_titulo=documento.titulo,
        study_id=estudo.id,
        estudo_nome=estudo.nome,
        termo_versao=avaliador.termo_versao,
        aceito_em=avaliador.aceito_em,
        rodadas=[_detalhar_rodada(sessao, rodada) for rodada in rodadas],
    )


@router.get("/studies/{study_id}/stats")
def obter_estatisticas(sessao: SessionDep, study_id: uuid.UUID) -> dict:
    _obter_estudo(sessao, study_id)
    return analisar_estudo(sessao, study_id)


@router.get("/studies/{study_id}/export.csv")
def exportar_csv(sessao: SessionDep, study_id: uuid.UUID) -> Response:
    """Uma linha por rodada x pipeline, no formato que `analise/modelo_misto.R` le."""
    _obter_estudo(sessao, study_id)
    linhas = sessao.exec(
        select(QuestionRound, PipelineAnswer, Pipeline, Document.slug)
        .join(EvaluationSession, EvaluationSession.id == QuestionRound.session_id)  # type: ignore[arg-type]
        .join(PipelineAnswer, PipelineAnswer.round_id == QuestionRound.id)  # type: ignore[arg-type]
        .join(Pipeline, Pipeline.id == PipelineAnswer.pipeline_id)  # type: ignore[arg-type]
        .join(Document, Document.id == QuestionRound.document_id)  # type: ignore[arg-type]
        .where(
            EvaluationSession.study_id == study_id,
            QuestionRound.escolhido_em.is_not(None),  # type: ignore[union-attr]
        )
        .order_by(QuestionRound.session_id, QuestionRound.ordem, PipelineAnswer.posicao_exibida)  # type: ignore[arg-type]
    ).all()

    saida = io.StringIO()
    escritor = csv.writer(saida)
    escritor.writerow(
        [
            "rodada",
            "avaliador",
            "documento",
            "ordem",
            "pipeline",
            "docling",
            "avancado",
            "rotulo",
            "posicao_exibida",
            "venceu",
            "nenhuma_correta",
            "tempo_total_ms",
            "tempo_geracao_ms",
            "tempo_oculto_ms",
            "tamanho_resposta",
            "pergunta",
        ]
    )
    for rodada, resposta, pipeline, slug in linhas:
        escritor.writerow(
            [
                rodada.id,
                rodada.session_id,
                slug,
                rodada.ordem,
                pipeline.codigo,
                int(pipeline.parser is ParserType.DOCLING),
                int(e_avancado(resposta.config_snapshot)),
                resposta.rotulo_cego,
                resposta.posicao_exibida,
                int(resposta.id == rodada.escolha_answer_id),
                int(rodada.nenhuma_correta),
                rodada.tempo_total_ms,
                rodada.tempo_geracao_ms,
                rodada.tempo_oculto_ms,
                len(resposta.texto),
                rodada.pergunta,
            ]
        )
    return Response(
        saida.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="estudo-{study_id}.csv"'},
    )


@router.post("/studies/{study_id}/ragas", status_code=status.HTTP_202_ACCEPTED)
def calcular_ragas_do_estudo(
    sessao: SessionDep, tarefas: BackgroundTasks, study_id: uuid.UUID
) -> RagasDisparado:
    """Roda em segundo plano e pula o que ja tem nota. Gasta creditos da OpenAI."""
    _obter_estudo(sessao, study_id)
    rodadas = rodadas_do_estudo(sessao, study_id)
    pendentes = contar_pendentes(sessao, rodadas)
    if not pendentes:
        return RagasDisparado(respostas_pendentes=0, mensagem="Nada pendente.")
    if not reservar_calculo(study_id):
        return RagasDisparado(
            respostas_pendentes=pendentes, mensagem="O cálculo deste estudo já está em andamento."
        )
    tarefas.add_task(calcular_em_segundo_plano, study_id, [rodada.id for rodada in rodadas])
    return RagasDisparado(
        respostas_pendentes=pendentes, mensagem=f"Cálculo iniciado para {pendentes} respostas."
    )


@router.get("/studies/{study_id}/ragas")
def obter_situacao_do_ragas(sessao: SessionDep, study_id: uuid.UUID) -> RagasSituacao:
    _obter_estudo(sessao, study_id)
    return situacao_do_estudo(sessao, study_id)


@router.post("/rounds/{round_id}/ragas")
async def calcular_ragas_da_rodada(sessao: SessionDep, round_id: uuid.UUID) -> RodadaAdmin:
    rodada = sessao.get(QuestionRound, round_id)
    if rodada is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rodada não encontrada.")
    await calcular_notas(sessao, [rodada])
    return _detalhar_rodada(sessao, rodada)
