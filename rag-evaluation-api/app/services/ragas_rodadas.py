"""Calcula o RAGAS sobre rodadas ja gravadas. Fica fora do fluxo do avaliador: e lento e custa caro.

Com 15 trechos, a precisao de contexto faz uma chamada ao juiz por trecho, entao uma rodada
consome dezenas de chamadas. Por isso o disparo e sempre uma acao explicita do administrador.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from statistics import fmean

from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.db import engine
from app.models.evaluation import EvaluationSession, PipelineAnswer, QuestionRound
from app.models.telemetry import EtapaChunk, RagasScore, RetrievedChunk
from app.schemas.admin import RagasSituacao
from app.telemetry.recorder import Cronometro

RESPOSTAS_SIMULTANEAS = 4

# Em memoria porque a API roda em um unico processo; reiniciar a API interrompe o calculo mesmo.
_estudos_em_calculo: set[uuid.UUID] = set()


async def _avaliar_padrao(pergunta: str, resposta: str, contextos: list[str]):
    # Importado aqui: o ragas leva segundos para carregar e so este caminho precisa dele.
    from app.rag.metricas_ragas import avaliar_resposta

    return await avaliar_resposta(pergunta, resposta, contextos)


def _pendentes(sessao: Session, rodadas: list[QuestionRound]) -> list[tuple[str, PipelineAnswer]]:
    """Respostas sem nota valida: uma tentativa que falhou pode ser repetida."""
    pendentes: list[tuple[str, PipelineAnswer]] = []
    for rodada in rodadas:
        respostas = sessao.exec(
            select(PipelineAnswer).where(PipelineAnswer.round_id == rodada.id)
        ).all()
        for resposta in respostas:
            nota = sessao.get(RagasScore, resposta.id)
            if nota is None or nota.erro:
                pendentes.append((rodada.pergunta, resposta))
    return pendentes


def rodadas_do_estudo(sessao: Session, study_id: uuid.UUID) -> list[QuestionRound]:
    return list(
        sessao.exec(
            select(QuestionRound)
            .join(EvaluationSession, EvaluationSession.id == QuestionRound.session_id)  # type: ignore[arg-type]
            .where(
                EvaluationSession.study_id == study_id,
                QuestionRound.escolhido_em.is_not(None),  # type: ignore[union-attr]
            )
        ).all()
    )


def contar_pendentes(sessao: Session, rodadas: list[QuestionRound]) -> int:
    return len(_pendentes(sessao, rodadas))


async def calcular_notas(
    sessao: Session,
    rodadas: list[QuestionRound],
    *,
    avaliar: Callable[..., Awaitable] = _avaliar_padrao,
) -> None:
    """Uma falha vira linha com `erro`, sem perder as demais notas."""
    limite = asyncio.Semaphore(RESPOSTAS_SIMULTANEAS)
    modelo = get_settings().ragas_llm_model
    pendentes = _pendentes(sessao, rodadas)

    entradas = []
    for pergunta, resposta in pendentes:
        contextos = sessao.exec(
            select(RetrievedChunk.texto)
            .where(
                RetrievedChunk.answer_id == resposta.id,
                RetrievedChunk.etapa == EtapaChunk.CONTEXTO_FINAL,
            )
            .order_by(RetrievedChunk.posicao)  # type: ignore[arg-type]
        ).all()
        entradas.append((pergunta, resposta.id, resposta.texto, list(contextos)))

    async def avaliar_uma(pergunta: str, answer_id: uuid.UUID, texto: str, contextos: list[str]):
        async with limite:
            with Cronometro() as relogio:
                try:
                    return answer_id, await avaliar(pergunta, texto, contextos), None, relogio
                except Exception as erro:  # noqa: BLE001 — uma falha nao derruba o lote
                    return answer_id, None, f"{type(erro).__name__}: {erro}"[:2000], relogio

    # Grava uma a uma: o pesquisador acompanha o andamento, e uma queda nao perde o que ja foi pago.
    for tarefa in asyncio.as_completed([avaliar_uma(*entrada) for entrada in entradas]):
        answer_id, notas, erro, relogio = await tarefa
        registro = sessao.get(RagasScore, answer_id) or RagasScore(
            answer_id=answer_id, modelo=modelo
        )
        registro.modelo = modelo
        registro.erro = erro
        registro.duracao_ms = relogio.ms
        if notas is not None:
            registro.fidelidade = notas.fidelidade
            registro.relevancia_resposta = notas.relevancia_resposta
            registro.precisao_contexto = notas.precisao_contexto
            registro.media = fmean(
                [notas.fidelidade, notas.relevancia_resposta, notas.precisao_contexto]
            )
        sessao.add(registro)
        sessao.commit()


def reservar_calculo(study_id: uuid.UUID) -> bool:
    """Falso se o estudo ja esta em calculo: dois lotes pagariam duas vezes pelas mesmas notas."""
    if study_id in _estudos_em_calculo:
        return False
    _estudos_em_calculo.add(study_id)
    return True


def situacao_do_estudo(sessao: Session, study_id: uuid.UUID) -> RagasSituacao:
    linhas = sessao.exec(
        select(PipelineAnswer.id, RagasScore.answer_id, RagasScore.erro)
        .join(QuestionRound, QuestionRound.id == PipelineAnswer.round_id)  # type: ignore[arg-type]
        .join(EvaluationSession, EvaluationSession.id == QuestionRound.session_id)  # type: ignore[arg-type]
        .outerjoin(RagasScore, RagasScore.answer_id == PipelineAnswer.id)  # type: ignore[arg-type]
        .where(
            EvaluationSession.study_id == study_id,
            QuestionRound.escolhido_em.is_not(None),  # type: ignore[union-attr]
        )
    ).all()
    erros = [erro for _, _, erro in linhas if erro]
    return RagasSituacao(
        em_andamento=study_id in _estudos_em_calculo,
        total=len(linhas),
        avaliadas=sum(1 for _, nota, erro in linhas if nota and not erro),
        com_erro=len(erros),
        ultimo_erro=erros[-1] if erros else None,
    )


def calcular_em_segundo_plano(study_id: uuid.UUID, rodada_ids: list[uuid.UUID]) -> None:
    """Ponto de entrada do BackgroundTasks: a sessao da requisicao ja foi fechada aqui."""
    try:
        with Session(engine) as sessao:
            rodadas = [sessao.get(QuestionRound, rodada_id) for rodada_id in rodada_ids]
            asyncio.run(calcular_notas(sessao, [item for item in rodadas if item is not None]))
    finally:
        _estudos_em_calculo.discard(study_id)
