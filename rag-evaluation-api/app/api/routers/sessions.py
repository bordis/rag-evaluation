"""Sessao anonima do avaliador e seu progresso.

Nao ha autenticacao: a sessao e so um UUID que o frontend guarda no `sessionStorage`. Ela existe
para impor o limite de perguntas no servidor e para permitir cruzar preferencia com perfil na
analise — nunca para identificar a pessoa.
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func
from sqlmodel import select

from app.core.config import get_settings
from app.core.db import SessionDep
from app.models.document import Document
from app.models.evaluation import EvaluationSession, QuestionRound
from app.schemas.evaluation import (
    PerfilAvaliador,
    ProgressoDocumento,
    ProgressoSessao,
    SessaoCriada,
)

router = APIRouter(prefix="/api/sessions", tags=["sessoes"])


@router.post("", status_code=status.HTTP_201_CREATED)
def criar_sessao(sessao: SessionDep, perfil: PerfilAvaliador | None = None) -> SessaoCriada:
    """O corpo e opcional: quem nao quiser informar o perfil manda `{}` ou nada."""
    dados = perfil or PerfilAvaliador()
    avaliador = EvaluationSession(
        area_atuacao=dados.area_atuacao,
        familiaridade=dados.familiaridade,
        tempo_experiencia=dados.tempo_experiencia,
    )
    sessao.add(avaliador)
    sessao.commit()
    sessao.refresh(avaliador)
    return SessaoCriada(id=avaliador.id, criado_em=avaliador.criado_em)


@router.get("/{session_id}/progress")
def obter_progresso(sessao: SessionDep, session_id: uuid.UUID) -> ProgressoSessao:
    """Quantas perguntas ja foram respondidas por documento. Reidrata a UI apos um F5."""
    if sessao.get(EvaluationSession, session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada.")

    max_perguntas = get_settings().max_perguntas
    linhas = sessao.exec(
        select(Document.id, Document.slug, func.count(QuestionRound.id))  # type: ignore[arg-type]
        .join(QuestionRound, QuestionRound.document_id == Document.id)  # type: ignore[arg-type]
        .where(
            QuestionRound.session_id == session_id,
            QuestionRound.escolha_answer_id.is_not(None),  # type: ignore[union-attr]
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
        total_concluidos=sum(1 for item in documentos if item.concluido),
        documentos=documentos,
    )
