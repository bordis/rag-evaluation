"""Sessao do avaliador e seu progresso.

Uma sessao por login e por estudo: aceitar o termo de novo, em outro navegador, devolve a mesma
sessao, e o avaliador retoma de onde parou. Da pessoa, so o `sub` do Keycloak fica no banco.
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func
from sqlmodel import select

from app.api.routers.evaluation import obter_sessao_avaliador
from app.core.auth import AvaliadorDep
from app.core.config import get_settings
from app.core.db import SessionDep
from app.models.document import Document
from app.models.evaluation import EvaluationSession, QuestionRound
from app.models.study import StatusEstudo, Study
from app.schemas.evaluation import (
    AceiteDoTermo,
    ProgressoDocumento,
    ProgressoSessao,
    SessaoCriada,
)
from app.services.studies import estudo_aberto

router = APIRouter(prefix="/api/sessions", tags=["sessoes"])


@router.post("", status_code=status.HTTP_201_CREATED)
def criar_sessao(sessao: SessionDep, usuario: AvaliadorDep, aceite: AceiteDoTermo) -> SessaoCriada:
    """A sessao nasce no estudo aberto: sem estudo aberto, ninguem responde.

    Se este login ja tem sessao no estudo, ela volta como esta: o aceite registrado e o primeiro.
    """
    estudo = estudo_aberto(sessao)
    if estudo is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Não há estudo aberto no momento.")
    existente = sessao.exec(
        select(EvaluationSession).where(
            EvaluationSession.study_id == estudo.id,
            EvaluationSession.usuario_sub == usuario.sub,
        )
    ).first()
    if existente is not None:
        return SessaoCriada(id=existente.id, study_id=estudo.id, criado_em=existente.criado_em)
    avaliador = EvaluationSession(
        study_id=estudo.id, usuario_sub=usuario.sub, termo_versao=aceite.termo_versao
    )
    sessao.add(avaliador)
    sessao.commit()
    sessao.refresh(avaliador)
    return SessaoCriada(id=avaliador.id, study_id=estudo.id, criado_em=avaliador.criado_em)


@router.get("/{session_id}/progress")
def obter_progresso(
    sessao: SessionDep, usuario: AvaliadorDep, session_id: uuid.UUID
) -> ProgressoSessao:
    """Quantas perguntas ja foram respondidas por documento. Reidrata a UI apos um F5."""
    avaliador = obter_sessao_avaliador(sessao, session_id, usuario)

    max_perguntas = get_settings().max_perguntas
    linhas = sessao.exec(
        select(Document.id, Document.slug, func.count(QuestionRound.id))  # type: ignore[arg-type]
        .join(QuestionRound, QuestionRound.document_id == Document.id)  # type: ignore[arg-type]
        .where(
            QuestionRound.session_id == session_id,
            QuestionRound.escolhido_em.is_not(None),  # type: ignore[union-attr]
        )
        .group_by(Document.id, Document.slug)  # type: ignore[arg-type]
    ).all()

    documentos = [
        ProgressoDocumento(
            document_id=document_id,
            slug=slug,
            respondidas=int(respondidas),
            concluido=int(respondidas) >= max_perguntas,
        )
        for document_id, slug, respondidas in linhas
    ]
    return ProgressoSessao(
        session_id=session_id,
        max_perguntas=max_perguntas,
        estudo_aberto=sessao.get(Study, avaliador.study_id).status is StatusEstudo.ABERTO,
        total_concluidos=sum(1 for item in documentos if item.concluido),
        documentos=documentos,
    )
