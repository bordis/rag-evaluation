"""Perguntas, respostas cegas e escolha — o fluxo que o avaliador percorre.

Convencao de identificadores do design: `{slug}` identifica o documento aqui (e o valor que ja
viaja na rota Angular `/avaliacao/:docId`), enquanto as rotas administrativas usam o UUID.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, status
from sqlmodel import Session, select

from app.core.auth import AvaliadorDep, Usuario
from app.core.config import get_settings
from app.core.db import SessionDep
from app.models.document import Document, StatusDocumento
from app.models.evaluation import EvaluationSession, QuestionRound
from app.models.study import StatusEstudo, Study
from app.schemas.evaluation import (
    EscolhaEntrada,
    MarcacaoEntrada,
    RespostaCega,
    RodadaDetalhe,
)
from app.services.evaluation import (
    ErroDeRodada,
    contar_respondidas,
    criar_rodada,
    listar_rodadas,
    registrar_escolha,
    registrar_falha,
    registrar_marcacao,
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
    tambem_corretas = (
        sorted(item.rotulo_cego for item in respostas if item.tambem_correta)
        if rodada.marcado_em is not None
        else None
    )
    return RodadaDetalhe(
        id=rodada.id,
        pergunta=rodada.pergunta,
        respostas=[
            RespostaCega(id=item.id, rotulo=item.rotulo_cego, texto=item.texto)
            for item in respostas
        ],
        ordem=rodada.ordem,
        escolha_rotulo=escolhida.rotulo_cego if escolhida else None,
        nenhuma_correta=rodada.nenhuma_correta,
        criado_em=rodada.criado_em,
        escolhido_em=rodada.escolhido_em,
        tambem_corretas=tambem_corretas,
        marcado_em=rodada.marcado_em,
    )


def obter_sessao_avaliador(
    sessao: Session, session_id: uuid.UUID, usuario: Usuario
) -> EvaluationSession:
    """A sessao de outro login responde 404, como se nao existisse: o UUID nao basta para agir."""
    avaliador = sessao.get(EvaluationSession, session_id)
    if avaliador is None or avaliador.usuario_sub != usuario.sub:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada.")
    return avaliador


def _exigir_estudo_aberto(sessao: Session, avaliador: EvaluationSession) -> None:
    """Encerrado o estudo, os dados dele ficam congelados."""
    estudo = sessao.get(Study, avaliador.study_id)
    if estudo is None or estudo.status is not StatusEstudo.ABERTO:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Esta avaliação já foi encerrada.")


def _obter_documento(sessao: Session, slug: str) -> Document:
    documento = sessao.exec(select(Document).where(Document.slug == slug)).first()
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Documento não encontrado.")
    return documento


@router.post(
    "/sessions/{session_id}/documents/{slug}/questions", status_code=status.HTTP_201_CREATED
)
async def fazer_pergunta(
    sessao: SessionDep,
    usuario: AvaliadorDep,
    session_id: uuid.UUID,
    slug: str,
    pergunta: PerguntaBody,
) -> RodadaDetalhe:
    """Dispara os pipelines em paralelo e devolve as respostas ja embaralhadas nos rotulos."""
    _exigir_estudo_aberto(sessao, obter_sessao_avaliador(sessao, session_id, usuario))
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
            detail="Conclua a rodada anterior antes de perguntar de novo.",
        )

    try:
        rodada = await criar_rodada(sessao, session_id, documento.id, pergunta.strip())
    except ErroDeRodada as erro:
        registrar_falha(sessao, session_id, documento.id, pergunta.strip(), str(erro))
        # A falha de um unico pipeline invalida a rodada: escolher entre 3 respostas produziria um
        # dado que nao agrega com os das demais rodadas.
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="Não foi possível gerar as respostas. Tente novamente em instantes.",
        ) from erro

    return _montar_rodada(sessao, rodada)


@router.get("/sessions/{session_id}/documents/{slug}/rounds")
def historico_de_rodadas(
    sessao: SessionDep, usuario: AvaliadorDep, session_id: uuid.UUID, slug: str
) -> list[RodadaDetalhe]:
    """Historico completo do par sessao+documento, para reidratar o chat apos um reload."""
    obter_sessao_avaliador(sessao, session_id, usuario)
    documento = _obter_documento(sessao, slug)
    return [
        _montar_rodada(sessao, rodada)
        for rodada in listar_rodadas(sessao, session_id, documento.id)
    ]


def _obter_rodada_do_avaliador(
    sessao: Session, round_id: uuid.UUID, usuario: Usuario
) -> tuple[QuestionRound, EvaluationSession]:
    rodada = sessao.get(QuestionRound, round_id)
    if rodada is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rodada não encontrada.")
    return rodada, obter_sessao_avaliador(sessao, rodada.session_id, usuario)


@router.post("/rounds/{round_id}/choice")
def escolher_resposta(
    sessao: SessionDep, usuario: AvaliadorDep, round_id: uuid.UUID, escolha: EscolhaEntrada
) -> RodadaDetalhe:
    rodada, avaliador = _obter_rodada_do_avaliador(sessao, round_id, usuario)
    if rodada.escolhido_em is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Esta rodada já foi decidida.")
    _exigir_estudo_aberto(sessao, avaliador)

    resposta = next(
        (
            item
            for item in respostas_da_rodada(sessao, rodada.id)
            if item.rotulo_cego == escolha.rotulo
        ),
        None,
    )
    if escolha.rotulo is not None and resposta is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"A rodada não tem resposta com o rótulo '{escolha.rotulo}'.",
        )

    registrar_escolha(
        sessao,
        rodada,
        resposta,
        tempo_total_ms=escolha.tempo_total_ms,
        tempo_geracao_ms=escolha.tempo_geracao_ms,
        tempo_oculto_ms=escolha.tempo_oculto_ms,
        tempo_pergunta_ms=escolha.tempo_pergunta_ms,
        respostas_vistas=escolha.respostas_vistas,
        recarregamentos=escolha.recarregamentos,
        largura_tela=escolha.largura_tela,
    )
    return _montar_rodada(sessao, rodada)


@router.post("/rounds/{round_id}/also-correct")
def marcar_tambem_corretas(
    sessao: SessionDep, usuario: AvaliadorDep, round_id: uuid.UUID, marcacao: MarcacaoEntrada
) -> RodadaDetalhe:
    """Segundo passo: das outras tres respostas, quais tambem estao corretas.

    Alimenta a taxa de correcao, uma medida secundaria; a vencedora da rodada nao muda.
    """
    rodada, avaliador = _obter_rodada_do_avaliador(sessao, round_id, usuario)
    if rodada.escolhido_em is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Escolha a melhor resposta antes de marcar as outras."
        )
    if rodada.nenhuma_correta:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Nesta rodada nenhuma resposta foi considerada correta.",
        )
    if rodada.marcado_em is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Esta rodada já foi marcada.")
    _exigir_estudo_aberto(sessao, avaliador)

    respostas = respostas_da_rodada(sessao, rodada.id)
    existentes = {item.rotulo_cego for item in respostas}
    escolhida = next(item.rotulo_cego for item in respostas if item.id == rodada.escolha_answer_id)
    for rotulo in marcacao.rotulos:
        if rotulo not in existentes:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"A rodada não tem resposta com o rótulo '{rotulo}'.",
            )
        if rotulo == escolhida:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="A resposta escolhida não entra na marcação das outras.",
            )

    registrar_marcacao(
        sessao,
        rodada,
        marcacao.rotulos,
        tempo_marcacao_ms=marcacao.tempo_marcacao_ms,
        tempo_marcacao_oculto_ms=marcacao.tempo_marcacao_oculto_ms,
    )
    return _montar_rodada(sessao, rodada)
