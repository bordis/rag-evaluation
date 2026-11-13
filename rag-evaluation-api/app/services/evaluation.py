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

from sqlalchemy import and_, func, or_
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.milvus import construir_cliente
from app.models.evaluation import PipelineAnswer, QuestionRound, RoundFailure
from app.models.pipeline import Pipeline
from app.models.telemetry import AnswerStageMetric, EtapaChunk, EtapaPipeline, RetrievedChunk
from app.rag.pipeline import RespostaDePipeline, executar_pipeline

ROTULOS = ("A", "B", "C", "D")

# Em memoria porque a API roda em um unico processo.
_rodadas_em_geracao = 0


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
    """So conta rodada decidida, com resposta ou com "nenhuma": perguntar e abandonar nao conta."""
    total = sessao.exec(
        select(func.count())
        .select_from(QuestionRound)
        .where(
            QuestionRound.session_id == session_id,
            QuestionRound.document_id == document_id,
            QuestionRound.escolhido_em.is_not(None),  # type: ignore[union-attr]
        )
    ).one()
    return int(total)


def rodada_pendente(
    sessao: Session, session_id: uuid.UUID, document_id: uuid.UUID
) -> QuestionRound | None:
    """A rodada que ainda nao esta completa: sem escolha, ou com vencedora e sem a marcacao.

    "Nenhuma esta correta" completa a rodada na escolha: nao ha outras a marcar.
    """
    return sessao.exec(
        select(QuestionRound)
        .where(
            QuestionRound.session_id == session_id,
            QuestionRound.document_id == document_id,
            or_(
                QuestionRound.escolhido_em.is_(None),  # type: ignore[union-attr]
                and_(
                    QuestionRound.nenhuma_correta.is_(False),  # type: ignore[attr-defined]
                    QuestionRound.marcado_em.is_(None),  # type: ignore[union-attr]
                ),
            ),
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
    rodadas_simultaneas: int,
) -> QuestionRound:
    ordem = len(listar_rodadas(sessao, session_id, document_id)) + 1
    na_sessao = sessao.exec(
        select(func.count())
        .select_from(QuestionRound)
        .where(QuestionRound.session_id == session_id)
    ).one()
    rodada = QuestionRound(
        session_id=session_id,
        document_id=document_id,
        pergunta=pergunta,
        ordem=ordem,
        ordem_na_sessao=int(na_sessao) + 1,
        rodadas_simultaneas=rodadas_simultaneas,
        respondido_em=datetime.now(UTC),
    )
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
            # O front lista em ordem de rotulo; a posicao fica gravada caso o layout mude.
            posicao_exibida=ROTULOS.index(rotulo) + 1,
            texto=resultado.texto,
            motivo_parada=next(
                (
                    metrica.detalhes.get("motivo_parada")
                    for metrica in resultado.metricas
                    if metrica.etapa is EtapaPipeline.GENERATION
                ),
                None,
            ),
            config_snapshot=dict(pipeline.config or {}),
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

        etapas = resultado.etapas or {EtapaChunk.CONTEXTO_FINAL: resultado.chunks}
        for etapa, candidatos in etapas.items():
            for posicao, candidato in enumerate(candidatos, start=1):
                sessao.add(
                    RetrievedChunk(
                        answer_id=resposta.id,
                        milvus_id=candidato.milvus_id,
                        chunk_index=candidato.chunk_index,
                        score_denso=candidato.score_denso,
                        score_esparso=candidato.score_esparso,
                        score_final=candidato.score_final,
                        etapa=etapa,
                        posicao=posicao,
                        origem=candidato.origem,
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

    global _rodadas_em_geracao
    _rodadas_em_geracao += 1
    simultaneas = _rodadas_em_geracao
    try:
        resultados = await _gerar_respostas(pipelines, document_id, pergunta, deps)
        # A que chegou depois tambem disputou o reordenador com esta.
        simultaneas = max(simultaneas, _rodadas_em_geracao)
    finally:
        _rodadas_em_geracao -= 1
    rotulos = deps.sortear_rotulos(len(pipelines))
    return _persistir(
        sessao, session_id, document_id, pergunta, pipelines, resultados, rotulos, simultaneas
    )


def registrar_falha(
    sessao: Session, session_id: uuid.UUID, document_id: uuid.UUID, pergunta: str, erro: str
) -> None:
    sessao.add(
        RoundFailure(
            session_id=session_id, document_id=document_id, pergunta=pergunta, erro=erro[:2000]
        )
    )
    sessao.commit()


def registrar_escolha(
    sessao: Session,
    rodada: QuestionRound,
    resposta: PipelineAnswer | None,
    *,
    tempo_total_ms: int | None = None,
    tempo_geracao_ms: int | None = None,
    tempo_oculto_ms: int | None = None,
    tempo_pergunta_ms: int | None = None,
    respostas_vistas: int | None = None,
    recarregamentos: int | None = None,
    largura_tela: int | None = None,
) -> None:
    """Sem `resposta`, o avaliador marcou que nenhuma das quatro esta correta."""
    rodada.escolha_answer_id = resposta.id if resposta else None
    rodada.nenhuma_correta = resposta is None
    rodada.escolhido_em = datetime.now(UTC)
    rodada.tempo_total_ms = tempo_total_ms
    rodada.tempo_geracao_ms = tempo_geracao_ms
    rodada.tempo_oculto_ms = tempo_oculto_ms
    rodada.tempo_pergunta_ms = tempo_pergunta_ms
    rodada.respostas_vistas = respostas_vistas
    rodada.recarregamentos = recarregamentos
    rodada.largura_tela = largura_tela
    sessao.add(rodada)
    sessao.commit()
    sessao.refresh(rodada)


def registrar_marcacao(
    sessao: Session,
    rodada: QuestionRound,
    rotulos: Sequence[str],
    *,
    tempo_marcacao_ms: int | None = None,
    tempo_marcacao_oculto_ms: int | None = None,
) -> None:
    """Grava True/False nas respostas nao escolhidas; a escolhida continua nula (nao medida).

    Lista vazia: o avaliador confirmou que nenhuma das outras esta correta.
    """
    marcadas = set(rotulos)
    for resposta in respostas_da_rodada(sessao, rodada.id):
        if resposta.id == rodada.escolha_answer_id:
            continue
        resposta.tambem_correta = resposta.rotulo_cego in marcadas
        sessao.add(resposta)
    rodada.marcado_em = datetime.now(UTC)
    rodada.tempo_marcacao_ms = tempo_marcacao_ms
    rodada.tempo_marcacao_oculto_ms = tempo_marcacao_oculto_ms
    sessao.add(rodada)
    sessao.commit()
    sessao.refresh(rodada)
