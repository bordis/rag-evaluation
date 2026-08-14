"""Orquestracao da rodada: os 4 pipelines em paralelo, rotulos sorteados, telemetria gravada.

O paralelismo vem de `asyncio.to_thread` sobre o orquestrador **sincrono** de `rag/pipeline.py`
(decisao C1 do plano da Fatia 3): sem isso seria preciso um cliente assincrono de Milvus e de
OpenAI, e as 4 geracoes rodariam em serie — dezenas de segundos de espera para o avaliador.

Se **um** pipeline falha, a rodada inteira falha. Pedir escolha entre 3 respostas quando o desenho
tem 4 produziria um dado que nao agrega com os demais.
"""

import asyncio
import random
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.milvus import construir_cliente
from app.models.evaluation import PipelineAnswer, QuestionRound
from app.models.pipeline import Pipeline
from app.models.telemetry import AnswerStageMetric, RetrievedChunk
from app.rag.pipeline import RespostaDePipeline, executar_pipeline

ROTULOS = ("A", "B", "C", "D")


class ErroDeRodada(Exception):
    """Pelo menos um pipeline falhou ou estourou o timeout; a rodada nao pode ser oferecida."""


def sortear_rotulos(quantidade: int) -> list[str]:
    """Permutacao dos rotulos. Sorteio por rodada — posicao fixa viraria pista sobre o pipeline."""
    return random.sample(ROTULOS[:quantidade], quantidade)


@dataclass
class DependenciasDeAvaliacao:
    """Pontos de injecao. Com falsos aqui, a rodada inteira roda sem OpenAI nem Milvus."""

    executar_pipeline: Callable[..., RespostaDePipeline] = field(default=executar_pipeline)
    construir_cliente_milvus: Callable[[], object] = field(default=construir_cliente)
    sortear_rotulos: Callable[[int], list[str]] = field(default=sortear_rotulos)


def _copia_transiente(pipeline: Pipeline) -> Pipeline:
    """A `Session` do SQLAlchemy nao e thread-safe; as threads recebem uma copia solta dela."""
    return Pipeline(
        id=pipeline.id,
        codigo=pipeline.codigo,
        nome=pipeline.nome,
        descricao=pipeline.descricao,
        parser=pipeline.parser,
        collection_name=pipeline.collection_name,
        ativo=pipeline.ativo,
        config=dict(pipeline.config or {}),
    )


def contar_respondidas(sessao: Session, session_id: uuid.UUID, document_id: uuid.UUID) -> int:
    """So conta rodada decidida: perguntar e abandonar nao consome a cota do documento."""
    total = sessao.exec(
        select(func.count())
        .select_from(QuestionRound)
        .where(
            QuestionRound.session_id == session_id,
            QuestionRound.document_id == document_id,
            QuestionRound.escolha_answer_id.is_not(None),  # type: ignore[union-attr]
        )
    ).one()
    return int(total)


def rodada_pendente(
    sessao: Session, session_id: uuid.UUID, document_id: uuid.UUID
) -> QuestionRound | None:
    return sessao.exec(
        select(QuestionRound)
        .where(
            QuestionRound.session_id == session_id,
            QuestionRound.document_id == document_id,
            QuestionRound.escolha_answer_id.is_(None),  # type: ignore[union-attr]
        )
        .order_by(QuestionRound.criado_em)  # type: ignore[arg-type]
    ).first()


def listar_rodadas(
    sessao: Session, session_id: uuid.UUID, document_id: uuid.UUID
) -> list[QuestionRound]:
    return list(
        sessao.exec(
            select(QuestionRound)
            .where(
                QuestionRound.session_id == session_id,
                QuestionRound.document_id == document_id,
            )
            .order_by(QuestionRound.criado_em)  # type: ignore[arg-type]
        ).all()
    )


def respostas_da_rodada(sessao: Session, round_id: uuid.UUID) -> list[PipelineAnswer]:
    """Ordenadas pelo rotulo: devolver na ordem de insercao entregaria a identidade do pipeline."""
    return list(
        sessao.exec(
            select(PipelineAnswer)
            .where(PipelineAnswer.round_id == round_id)
            .order_by(PipelineAnswer.rotulo_cego)  # type: ignore[arg-type]
        ).all()
    )


async def _gerar_respostas(
    pipelines: Sequence[Pipeline],
    document_id: uuid.UUID,
    pergunta: str,
    dependencias: DependenciasDeAvaliacao,
) -> list[RespostaDePipeline]:
    cliente = dependencias.construir_cliente_milvus()
    timeout = get_settings().pipeline_timeout_seconds
    copias = [_copia_transiente(pipeline) for pipeline in pipelines]

    async def rodar(pipeline: Pipeline) -> RespostaDePipeline:
        return await asyncio.wait_for(
            asyncio.to_thread(
                dependencias.executar_pipeline,
                pipeline,
                document_id,
                pergunta,
                cliente_milvus=cliente,
            ),
            timeout=timeout,
        )

    try:
        return list(await asyncio.gather(*(rodar(pipeline) for pipeline in copias)))
    except Exception as erro:
        raise ErroDeRodada(f"{type(erro).__name__}: {erro}") from erro


def _persistir(
    sessao: Session,
    session_id: uuid.UUID,
    document_id: uuid.UUID,
    pergunta: str,
    pipelines: Sequence[Pipeline],
    resultados: Sequence[RespostaDePipeline],
    rotulos: Sequence[str],
) -> QuestionRound:
    rodada = QuestionRound(session_id=session_id, document_id=document_id, pergunta=pergunta)
    sessao.add(rodada)
    # Flush explicito entre os niveis: nenhuma das tabelas declara `Relationship`, e sem isso o
    # unit of work nao conhece a dependencia — as respostas iriam para o banco antes da rodada e a
    # chave estrangeira estouraria.
    sessao.flush()

    for pipeline, resultado, rotulo in zip(pipelines, resultados, rotulos, strict=True):
        resposta = PipelineAnswer(
            round_id=rodada.id,
            pipeline_id=pipeline.id,  # type: ignore[arg-type]
            rotulo_cego=rotulo,
            texto=resultado.texto,
        )
        sessao.add(resposta)
        sessao.flush()

        for ordem, metrica in enumerate(resultado.metricas, start=1):
            sessao.add(
                AnswerStageMetric(
                    answer_id=resposta.id,
                    etapa=metrica.etapa,
                    ordem=ordem,
                    duracao_ms=metrica.duracao_ms,
                    tokens_prompt=metrica.tokens_prompt,
                    tokens_completion=metrica.tokens_completion,
                    tokens_total=metrica.tokens_total,
                    modelo=metrica.modelo,
                    detalhes=metrica.detalhes,
                )
            )

        for posicao, candidato in enumerate(resultado.chunks, start=1):
            sessao.add(
                RetrievedChunk(
                    answer_id=resposta.id,
                    milvus_id=candidato.milvus_id,
                    chunk_index=candidato.chunk_index,
                    score_denso=candidato.score_denso,
                    score_esparso=candidato.score_esparso,
                    score_final=candidato.score_final,
                    posicao_final=posicao,
                    texto=candidato.texto,
                )
            )

    sessao.commit()
    sessao.refresh(rodada)
    return rodada


async def criar_rodada(
    sessao: Session,
    session_id: uuid.UUID,
    document_id: uuid.UUID,
    pergunta: str,
    *,
    dependencias: DependenciasDeAvaliacao | None = None,
) -> QuestionRound:
    """Gera as 4 respostas, sorteia os rotulos e grava rodada, metricas e chunks recuperados."""
    deps = dependencias or DependenciasDeAvaliacao()
    pipelines = list(
        sessao.exec(
            select(Pipeline).where(Pipeline.ativo).order_by(Pipeline.codigo)  # type: ignore[arg-type]
        ).all()
    )
    if not pipelines:
        raise ErroDeRodada("Nenhum pipeline ativo cadastrado.")

    resultados = await _gerar_respostas(pipelines, document_id, pergunta, deps)
    rotulos = deps.sortear_rotulos(len(pipelines))
    return _persistir(sessao, session_id, document_id, pergunta, pipelines, resultados, rotulos)


def registrar_escolha(sessao: Session, rodada: QuestionRound, resposta: PipelineAnswer) -> None:
    rodada.escolha_answer_id = resposta.id
    rodada.escolhido_em = datetime.now(UTC)
    sessao.add(rodada)
    sessao.commit()
    sessao.refresh(rodada)
