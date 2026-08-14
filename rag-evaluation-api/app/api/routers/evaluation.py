"""Perguntas, respostas cegas e escolha — o fluxo que o avaliador percorre.

Convencao de identificadores do design: `{slug}` identifica o documento aqui (e o valor que ja
viaja na rota Angular `/avaliacao/:docId`), enquanto as rotas administrativas usam o UUID.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, status
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.db import SessionDep
from app.models.document import Document, StatusDocumento
from app.models.evaluation import EvaluationSession, QuestionRound
from app.schemas.evaluation import EscolhaEntrada, RespostaCega, RodadaDetalhe
from app.services.evaluation import (
    ErroDeRodada,
    contar_respondidas,
    criar_rodada,
    listar_rodadas,
    registrar_escolha,
    respostas_da_rodada,
    rodada_pendente,
)

router = APIRouter(prefix="/api", tags=["avaliacao"])

PerguntaBody = Annotated[str, Body(min_length=3, max_length=500, embed=True)]


def _montar_rodada(sessao: Session, rodada: QuestionRound) -> RodadaDetalhe:
    respostas = respostas_da_rodada(sessao, rodada.id)
    escolhida = next(
        (item for item in respostas if item.id == rodada.escolha_answer_id),
        None,
    )
    return RodadaDetalhe(
        id=rodada.id,
        pergunta=rodada.pergunta,
        respostas=[
            RespostaCega(id=item.id, rotulo=item.rotulo_cego, texto=item.texto)
            for item in respostas
        ],
        escolha_rotulo=escolhida.rotulo_cego if escolhida else None,
        criado_em=rodada.criado_em,
        escolhido_em=rodada.escolhido_em,
    )


def _obter_sessao_avaliador(sessao: Session, session_id: uuid.UUID) -> EvaluationSession:
    avaliador = sessao.get(EvaluationSession, session_id)
    if avaliador is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada.")
    return avaliador


def _obter_documento(sessao: Session, slug: str) -> Document:
    documento = sessao.exec(select(Document).where(Document.slug == slug)).first()
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Documento não encontrado.")
    return documento


@router.post(
    "/sessions/{session_id}/documents/{slug}/questions", status_code=status.HTTP_201_CREATED
)
async def fazer_pergunta(
    sessao: SessionDep, session_id: uuid.UUID, slug: str, pergunta: PerguntaBody
) -> RodadaDetalhe:
    """Dispara os pipelines em paralelo e devolve as respostas ja embaralhadas nos rotulos."""
    _obter_sessao_avaliador(sessao, session_id)
    documento = _obter_documento(sessao, slug)
    if documento.status is not StatusDocumento.PRONTO:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="O documento ainda não está pronto para avaliação.",
        )

    max_perguntas = get_settings().max_perguntas
    if contar_respondidas(sessao, session_id, documento.id) >= max_perguntas:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Limite de {max_perguntas} perguntas atingido para este documento.",
        )
    if rodada_pendente(sessao, session_id, documento.id) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Escolha uma resposta da rodada anterior antes de perguntar de novo.",
        )

    try:
        rodada = await criar_rodada(sessao, session_id, documento.id, pergunta.strip())
    except ErroDeRodada as erro:
        # A falha de um unico pipeline invalida a rodada: escolher entre 3 respostas produziria um
        # dado que nao agrega com os das demais rodadas.
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail=f"Falha ao gerar as respostas: {erro}"
        ) from erro

    return _montar_rodada(sessao, rodada)


@router.get("/sessions/{session_id}/documents/{slug}/rounds")
def historico_de_rodadas(
    sessao: SessionDep, session_id: uuid.UUID, slug: str
) -> list[RodadaDetalhe]:
    """Historico completo do par sessao+documento, para reidratar o chat apos um reload."""
    _obter_sessao_avaliador(sessao, session_id)
    documento = _obter_documento(sessao, slug)
    return [
        _montar_rodada(sessao, rodada)
        for rodada in listar_rodadas(sessao, session_id, documento.id)
    ]


@router.post("/rounds/{round_id}/choice")
def escolher_resposta(
    sessao: SessionDep, round_id: uuid.UUID, escolha: EscolhaEntrada
) -> RodadaDetalhe:
    rodada = sessao.get(QuestionRound, round_id)
    if rodada is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rodada não encontrada.")
    if rodada.escolha_answer_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Esta rodada já foi decidida.")

    resposta = next(
        (
            item
            for item in respostas_da_rodada(sessao, rodada.id)
            if item.rotulo_cego == escolha.rotulo
        ),
        None,
    )
    if resposta is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"A rodada não tem resposta com o rótulo '{escolha.rotulo}'.",
        )

    registrar_escolha(sessao, rodada, resposta)
    return _montar_rodada(sessao, rodada)
