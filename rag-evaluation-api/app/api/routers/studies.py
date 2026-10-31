"""Estudos: o administrador abre e encerra; cada estudo comeca zerado."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.db import SessionDep
from app.models.evaluation import EvaluationSession, QuestionRound
from app.models.study import StatusEstudo, Study
from app.schemas.admin import EstudoCriar, EstudoResumo
from app.services.studies import estudo_aberto, impedimento_para_abrir

router = APIRouter(prefix="/api/studies", tags=["estudos"])


def _resumir(sessao: Session, estudo: Study) -> EstudoResumo:
    avaliadores = sessao.exec(
        select(func.count())
        .select_from(EvaluationSession)
        .where(EvaluationSession.study_id == estudo.id)
    ).one()
    rodadas = sessao.exec(
        select(func.count())
        .select_from(QuestionRound)
        .join(EvaluationSession, EvaluationSession.id == QuestionRound.session_id)  # type: ignore[arg-type]
        .where(
            EvaluationSession.study_id == estudo.id,
            QuestionRound.escolhido_em.is_not(None),  # type: ignore[union-attr]
        )
    ).one()
    return EstudoResumo(
        id=estudo.id,
        nome=estudo.nome,
        descricao=estudo.descricao,
        status=estudo.status,
        iniciado_em=estudo.iniciado_em,
        encerrado_em=estudo.encerrado_em,
        sessoes=int(avaliadores),
        rodadas_decididas=int(rodadas),
    )


@router.get("")
def listar_estudos(sessao: SessionDep) -> list[EstudoResumo]:
    estudos = sessao.exec(select(Study).order_by(Study.iniciado_em.desc())).all()  # type: ignore[union-attr]
    return [_resumir(sessao, estudo) for estudo in estudos]


@router.get("/atual")
def obter_estudo_atual(sessao: SessionDep) -> EstudoResumo | None:
    """A tela de boas-vindas consulta aqui para saber se o avaliador pode comecar."""
    estudo = estudo_aberto(sessao)
    return _resumir(sessao, estudo) if estudo else None


@router.post("", status_code=status.HTTP_201_CREATED)
def criar_estudo(sessao: SessionDep, dados: EstudoCriar) -> EstudoResumo:
    impedimento = impedimento_para_abrir(sessao)
    if impedimento:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=impedimento)
    estudo = Study(nome=dados.nome, descricao=dados.descricao)
    sessao.add(estudo)
    sessao.commit()
    sessao.refresh(estudo)
    return _resumir(sessao, estudo)


@router.post("/{study_id}/encerrar")
def encerrar_estudo(sessao: SessionDep, study_id: uuid.UUID) -> EstudoResumo:
    estudo = sessao.get(Study, study_id)
    if estudo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Estudo não encontrado.")
    if estudo.status is StatusEstudo.ENCERRADO:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Este estudo já foi encerrado.")
    estudo.status = StatusEstudo.ENCERRADO
    estudo.encerrado_em = datetime.now(UTC)
    sessao.add(estudo)
    sessao.commit()
    sessao.refresh(estudo)
    return _resumir(sessao, estudo)
