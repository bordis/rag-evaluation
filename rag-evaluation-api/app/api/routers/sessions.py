"""Sessao anonima do avaliador e seu progresso.

Nao ha autenticacao: a sessao e so um UUID que o frontend guarda no `sessionStorage`. Ela existe
para impor o limite de perguntas no servidor e ligar as rodadas ao estudo — nunca para identificar
a pessoa.
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func
from sqlmodel import select

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
def criar_sessao(sessao: SessionDep, aceite: AceiteDoTermo) -> SessaoCriada:
    """A sessao nasce no estudo aberto: sem estudo aberto, ninguem responde."""
    estudo = estudo_aberto(sessao)
    if estudo is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Não há estudo aberto no momento.")
    avaliador = EvaluationSession(study_id=estudo.id, termo_versao=aceite.termo_versao)
    sessao.add(avaliador)
    sessao.commit()
    sessao.refresh(avaliador)
    return SessaoCriada(id=avaliador.id, study_id=estudo.id, criado_em=avaliador.criado_em)


@router.get("/{session_id}/progress")
def obter_progresso(sessao: SessionDep, session_id: uuid.UUID) -> ProgressoSessao:
    """Quantas perguntas ja foram respondidas por documento. Reidrata a UI apos um F5."""
    avaliador = sessao.get(EvaluationSession, session_id)
    if avaliador is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada.")

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
