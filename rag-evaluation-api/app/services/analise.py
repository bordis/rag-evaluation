"""Analise de um estudo: H1 a H3, vies de posicao, fadiga, custo e concordancia com o RAGAS.

Cada efeito do 2x2 vira uma pergunta binaria sobre a rodada, com 50% como hipotese nula:
- ingestao (H1): a resposta vencedora veio de um pipeline com Docling?
- recuperacao (H2): veio de um pipeline com recuperacao avancada?
- interacao (H3): veio da diagonal 1/4, em vez de 2/3? Sem interacao, as diagonais empatam.

Os tres contrastes sao ortogonais, e a escolha de um vencedor por rodada elimina a dependencia que
apareceria ao tratar as quatro respostas como quatro observacoes. Rodadas "nenhuma" nao tem vencedor
e ficam fora desses testes, reportadas a parte. O IC por bootstrap reamostra avaliadores, porque as
rodadas de um mesmo avaliador nao sao independentes. O modelo misto com efeito aleatorio de
avaliador e documento esta em `analise/modelo_misto.R`, sobre o CSV exportado.
"""

import math
import random
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from statistics import fmean, median

from sqlmodel import Session, select

from app.core.config import get_settings
from app.models.document import Document, DocumentIngestion
from app.models.evaluation import EvaluationSession, PipelineAnswer, QuestionRound
from app.models.pipeline import ParserType, Pipeline
from app.models.telemetry import AnswerStageMetric, RagasScore

ITERACOES_BOOTSTRAP = 2000
SEMENTE_BOOTSTRAP = 20260
ACASO = 0.25
METRICAS_RAGAS = ("media", "fidelidade", "relevancia_resposta", "precisao_contexto")


@dataclass(frozen=True)
class Rodada:
    id: uuid.UUID
    avaliador: uuid.UUID
    documento: str
    ordem: int
    nenhuma: bool
    tempo_total_ms: int | None
    tempo_geracao_ms: int | None
    tempo_oculto_ms: int | None
    tamanho_respostas: int
    # Do pipeline vencedor; nulos em "nenhuma".
    vencedor: str | None
    posicao: int | None
    docling: bool | None
    avancado: bool | None


def custo_usd(modelo: str | None, entrada: int | None, saida: int | None) -> float | None:
    """Sem preco ou sem tokens (reordenacao, busca), a etapa fica sem custo em vez de custo zero."""
    if modelo is None or (entrada is None and saida is None):
        return None
    precos = get_settings().precos_modelos
    # A API devolve o snapshot ("gpt-4.1-mini-2025-04-14"): vale o nome mais longo que casar.
    casados = [nome for nome in precos if modelo.startswith(nome)]
    if not casados:
        return None
    preco_entrada, preco_saida = precos[max(casados, key=len)]
    return ((entrada or 0) * preco_entrada + (saida or 0) * preco_saida) / 1_000_000


def wilson(sucessos: int, total: int, z: float = 1.96) -> tuple[float, float] | None:
    if total == 0:
        return None
    p = sucessos / total
    denominador = 1 + z**2 / total
    centro = (p + z**2 / (2 * total)) / denominador
    margem = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denominador
    return max(0.0, centro - margem), min(1.0, centro + margem)


def binomial_bicaudal(sucessos: int, total: int, p: float = 0.5) -> float | None:
    """Teste exato: soma as probabilidades dos resultados tao ou menos provaveis que o observado."""
    if total == 0:
        return None
    massa = [math.comb(total, k) * p**k * (1 - p) ** (total - k) for k in range(total + 1)]
    return min(1.0, sum(valor for valor in massa if valor <= massa[sucessos] * (1 + 1e-9)))


def bootstrap_por_avaliador(
    rodadas: list[tuple[uuid.UUID, bool]],
) -> tuple[float, float] | None:
    if not rodadas:
        return None
    por_avaliador: dict[uuid.UUID, list[bool]] = defaultdict(list)
    for avaliador, acerto in rodadas:
        por_avaliador[avaliador].append(acerto)
    grupos = list(por_avaliador.values())

    gerador = random.Random(SEMENTE_BOOTSTRAP)
    taxas: list[float] = []
    for _ in range(ITERACOES_BOOTSTRAP):
        amostra = [item for grupo in gerador.choices(grupos, k=len(grupos)) for item in grupo]
        taxas.append(sum(amostra) / len(amostra))
    taxas.sort()
    return taxas[int(0.025 * len(taxas))], taxas[int(0.975 * len(taxas)) - 1]


def percentil(valores: list[float], fracao: float) -> float | None:
    """Interpolacao linear entre postos."""
    if not valores:
        return None
    ordenados = sorted(valores)
    posicao = (len(ordenados) - 1) * fracao
    baixo, alto = math.floor(posicao), math.ceil(posicao)
    return ordenados[baixo] + (ordenados[alto] - ordenados[baixo]) * (posicao - baixo)


def kendall_tau(a: list[float], b: list[float]) -> float | None:
    """Tau-a da ordenacao agregada. Com 4 itens e so descritivo: tem pouco poder."""
    pares = [(i, j) for i in range(len(a)) for j in range(i + 1, len(a))]
    if not pares:
        return None

    def sinal(valor: float) -> int:
        return (valor > 0) - (valor < 0)

    return sum(sinal(a[i] - a[j]) * sinal(b[i] - b[j]) for i, j in pares) / len(pares)


def e_avancado(config: dict) -> bool:
    janela = config.get("sliding_window") or {}
    return bool(
        config.get("hyde")
        or config.get("reranking")
        or config.get("hybrid_search")
        or janela.get("ativo")
    )


def carregar_rodadas(sessao: Session, study_id: uuid.UUID) -> list[Rodada]:
    linhas = sessao.exec(
        select(QuestionRound, Document.slug)
        .join(EvaluationSession, EvaluationSession.id == QuestionRound.session_id)  # type: ignore[arg-type]
        .join(Document, Document.id == QuestionRound.document_id)  # type: ignore[arg-type]
        .where(
            EvaluationSession.study_id == study_id,
            QuestionRound.escolhido_em.is_not(None),  # type: ignore[union-attr]
        )
    ).all()
    rodadas: list[Rodada] = []
    for rodada, slug in linhas:
        respostas = sessao.exec(
            select(PipelineAnswer, Pipeline)
            .join(Pipeline, Pipeline.id == PipelineAnswer.pipeline_id)  # type: ignore[arg-type]
            .where(PipelineAnswer.round_id == rodada.id)
        ).all()
        vencedora = next(
            ((res, pip) for res, pip in respostas if res.id == rodada.escolha_answer_id), None
        )
        rodadas.append(
            Rodada(
                id=rodada.id,
                avaliador=rodada.session_id,
                documento=slug,
                ordem=rodada.ordem,
                nenhuma=rodada.nenhuma_correta,
                tempo_total_ms=rodada.tempo_total_ms,
                tempo_geracao_ms=rodada.tempo_geracao_ms,
                tempo_oculto_ms=rodada.tempo_oculto_ms,
                tamanho_respostas=sum(len(res.texto) for res, _ in respostas),
                vencedor=vencedora[1].codigo if vencedora else None,
                posicao=vencedora[0].posicao_exibida if vencedora else None,
                docling=vencedora[1].parser is ParserType.DOCLING if vencedora else None,
                avancado=e_avancado(vencedora[0].config_snapshot) if vencedora else None,
            )
        )
    return rodadas


def tempo_ativo_ms(rodada: Rodada) -> int | None:
    """Tempo de pergunta, leitura e decisao: tira a espera pela geracao e a aba oculta."""
    if rodada.tempo_total_ms is None:
        return None
    return max(
        0, rodada.tempo_total_ms - (rodada.tempo_geracao_ms or 0) - (rodada.tempo_oculto_ms or 0)
    )


def _taxa(sucessos: int, total: int) -> dict:
    return {
        "sucessos": sucessos,
        "total": total,
        "taxa": sucessos / total if total else None,
        "ic95": wilson(sucessos, total),
    }


def _efeito(nome: str, descricao: str, rodadas: list[Rodada], criterio) -> dict:
    acertos = [(rodada.avaliador, bool(criterio(rodada))) for rodada in rodadas]
    sucessos = sum(acerto for _, acerto in acertos)
    return {
        "efeito": nome,
        "descricao": descricao,
        **_taxa(sucessos, len(acertos)),
        "ic95_bootstrap": bootstrap_por_avaliador(acertos),
        "p_valor": binomial_bicaudal(sucessos, len(acertos)),
    }


def analisar_escolhas(rodadas: list[Rodada], codigos: Iterable[str]) -> dict:
    """Pura de proposito: recebe as rodadas e so calcula."""
    com_vencedor = [rodada for rodada in rodadas if not rodada.nenhuma]
    total = len(com_vencedor)

    por_ordem: dict[int, list[Rodada]] = defaultdict(list)
    for rodada in rodadas:
        por_ordem[rodada.ordem].append(rodada)

    por_documento: dict[str, list[Rodada]] = defaultdict(list)
    for rodada in rodadas:
        por_documento[rodada.documento].append(rodada)

    def resumo_ordem(ordem: int, grupo: list[Rodada]) -> dict:
        ativos = [t for t in map(tempo_ativo_ms, grupo) if t is not None]
        decididas = [item for item in grupo if not item.nenhuma]
        return {
            "ordem": ordem,
            "rodadas": len(grupo),
            "nenhuma": sum(item.nenhuma for item in grupo),
            "tempo_ativo_mediano_ms": median(ativos) if ativos else None,
            "tamanho_medio_respostas": fmean(item.tamanho_respostas for item in grupo),
            # Convergindo para o acaso ou com a posicao 1 dominando no fim, ha sinal de fadiga.
            "taxa_posicao_1": (
                sum(item.posicao == 1 for item in decididas) / len(decididas) if decididas else None
            ),
            "taxa_avancado": (
                sum(bool(item.avancado) for item in decididas) / len(decididas)
                if decididas
                else None
            ),
        }

    return {
        "rodadas_decididas": len(rodadas),
        "avaliadores": len({rodada.avaliador for rodada in rodadas}),
        "nenhuma": _taxa(sum(rodada.nenhuma for rodada in rodadas), len(rodadas)),
        "acaso": ACASO,
        "por_pipeline": [
            {
                "codigo": codigo,
                **_taxa(sum(rodada.vencedor == codigo for rodada in com_vencedor), total),
            }
            for codigo in codigos
        ],
        "efeitos": [
            _efeito(
                "ingestao",
                "H1: vencedora veio de pipeline com Docling (2 ou 4)",
                com_vencedor,
                lambda r: r.docling,
            ),
            _efeito(
                "recuperacao",
                "H2: vencedora veio de pipeline com recuperação avançada (3 ou 4)",
                com_vencedor,
                lambda r: r.avancado,
            ),
            _efeito(
                "interacao",
                "H3: vencedora veio da diagonal 1 e 4, em vez de 2 e 3",
                com_vencedor,
                lambda r: r.docling == r.avancado,
            ),
        ],
        "por_documento": [
            {
                "documento": documento,
                "rodadas": len(grupo),
                "nenhuma": sum(item.nenhuma for item in grupo),
                "vitorias": {
                    codigo: sum(item.vencedor == codigo for item in grupo) for codigo in codigos
                },
            }
            for documento, grupo in sorted(por_documento.items())
        ],
        "por_posicao": [
            {
                "posicao": posicao,
                **_taxa(sum(rodada.posicao == posicao for rodada in com_vencedor), total),
            }
            for posicao in (1, 2, 3, 4)
        ],
        "por_ordem": [resumo_ordem(ordem, por_ordem[ordem]) for ordem in sorted(por_ordem)],
    }


def analisar_ragas(linhas: list[dict], rodadas: list[Rodada], codigos: list[str]) -> dict:
    """`linhas`: uma por resposta com nota, com `rodada`, `codigo` e as metricas.

    Concordancia: o pipeline de maior nota e o que o avaliador escolheu? Empate reparte o acerto.
    """
    por_rodada: dict[uuid.UUID, list[dict]] = defaultdict(list)
    for linha in linhas:
        por_rodada[linha["rodada"]].append(linha)

    humanas = {rodada.id: rodada for rodada in rodadas}
    concordancia = []
    for metrica in METRICAS_RAGAS:
        acertos: list[float] = []
        for rodada_id, notas in por_rodada.items():
            humana = humanas.get(rodada_id)
            validas = [nota for nota in notas if nota.get(metrica) is not None]
            if humana is None or humana.nenhuma or len(validas) < len(codigos):
                continue
            maior = max(nota[metrica] for nota in validas)
            topo = {nota["codigo"] for nota in validas if nota[metrica] == maior}
            acertos.append(1 / len(topo) if humana.vencedor in topo else 0.0)
        concordancia.append(
            {
                "metrica": metrica,
                "rodadas": len(acertos),
                "concordancia": fmean(acertos) if acertos else None,
                "acaso": ACASO,
            }
        )

    medias = {
        codigo: {
            metrica: (
                fmean(valores)
                if (
                    valores := [
                        linha[metrica]
                        for linha in linhas
                        if linha["codigo"] == codigo and linha.get(metrica) is not None
                    ]
                )
                else None
            )
            for metrica in METRICAS_RAGAS
        }
        for codigo in codigos
    }
    vitorias = [
        sum(rodada.vencedor == codigo for rodada in rodadas if not rodada.nenhuma)
        for codigo in codigos
    ]
    notas_medias = [medias[codigo]["media"] for codigo in codigos]
    tau = (
        kendall_tau(vitorias, notas_medias)  # type: ignore[arg-type]
        if all(valor is not None for valor in notas_medias)
        else None
    )
    return {
        "respostas_avaliadas": len(linhas),
        "concordancia": concordancia,
        "media_por_pipeline": [{"codigo": c, **medias[c]} for c in codigos],
        "kendall_tau_ordenacao": tau,
    }


def analisar_custo(sessao: Session, study_id: uuid.UUID, codigos: list[str]) -> dict:
    linhas = sessao.exec(
        select(AnswerStageMetric, Pipeline.codigo, PipelineAnswer.id)
        .join(PipelineAnswer, PipelineAnswer.id == AnswerStageMetric.answer_id)  # type: ignore[arg-type]
        .join(Pipeline, Pipeline.id == PipelineAnswer.pipeline_id)  # type: ignore[arg-type]
        .join(QuestionRound, QuestionRound.id == PipelineAnswer.round_id)  # type: ignore[arg-type]
        .join(EvaluationSession, EvaluationSession.id == QuestionRound.session_id)  # type: ignore[arg-type]
        .where(EvaluationSession.study_id == study_id)
    ).all()

    por_etapa: dict[tuple[str, str], list[AnswerStageMetric]] = defaultdict(list)
    por_resposta: dict[tuple[str, uuid.UUID], dict] = defaultdict(
        lambda: {"ms": 0, "tokens": 0, "usd": 0.0}
    )
    for metrica, codigo, answer_id in linhas:
        por_etapa[(codigo, metrica.etapa.value)].append(metrica)
        acumulado = por_resposta[(codigo, answer_id)]
        acumulado["ms"] += metrica.duracao_ms
        acumulado["tokens"] += metrica.tokens_total or 0
        acumulado["usd"] += (
            custo_usd(metrica.modelo, metrica.tokens_prompt, metrica.tokens_completion) or 0.0
        )

    def resumo_etapa(codigo: str, etapa: str, itens: list[AnswerStageMetric]) -> dict:
        duracoes = [item.duracao_ms for item in itens]
        tokens = [item.tokens_total for item in itens if item.tokens_total is not None]
        custos = [
            valor
            for item in itens
            if (valor := custo_usd(item.modelo, item.tokens_prompt, item.tokens_completion))
            is not None
        ]
        return {
            "codigo": codigo,
            "etapa": etapa,
            "execucoes": len(itens),
            "ms_medio": fmean(duracoes),
            "ms_p50": percentil(duracoes, 0.5),
            "ms_p95": percentil(duracoes, 0.95),
            "tokens_medio": fmean(tokens) if tokens else None,
            "usd_medio": fmean(custos) if custos else None,
        }

    def resumo_pipeline(codigo: str) -> dict:
        itens = [valor for (cod, _), valor in por_resposta.items() if cod == codigo]
        duracoes = [item["ms"] for item in itens]
        return {
            "codigo": codigo,
            "respostas": len(itens),
            "ms_medio": fmean(duracoes) if duracoes else None,
            "ms_p50": percentil(duracoes, 0.5),
            "ms_p95": percentil(duracoes, 0.95),
            "tokens_medio": fmean(item["tokens"] for item in itens) if itens else None,
            "usd_medio": fmean(item["usd"] for item in itens) if itens else None,
            "usd_total": sum(item["usd"] for item in itens),
        }

    ingestoes = sessao.exec(
        select(DocumentIngestion, Pipeline.codigo).join(
            Pipeline,
            Pipeline.id == DocumentIngestion.pipeline_id,  # type: ignore[arg-type]
        )
    ).all()
    agrupadas: dict[str, list[DocumentIngestion]] = defaultdict(list)
    for ingestao, codigo in ingestoes:
        agrupadas[codigo].append(ingestao)

    return {
        "por_pipeline": [resumo_pipeline(codigo) for codigo in codigos],
        "por_etapa": [
            resumo_etapa(codigo, etapa, itens)
            for (codigo, etapa), itens in sorted(por_etapa.items())
        ],
        # O acervo e compartilhado entre estudos, entao a ingestao nao se divide por estudo.
        "ingestao": [
            {
                "codigo": codigo,
                "documentos": len(itens),
                "parsing_ms_medio": fmean(item.duracao_parsing_ms for item in itens),
                "total_ms_medio": fmean(item.duracao_total_ms for item in itens),
                "chunks_medio": fmean(item.total_chunks for item in itens),
                "tokens_embedding_total": sum(item.tokens_embedding for item in itens),
            }
            for codigo, itens in sorted(agrupadas.items())
        ],
    }


def linhas_ragas(sessao: Session, rodadas: list[Rodada]) -> list[dict]:
    if not rodadas:
        return []
    registros = sessao.exec(
        select(RagasScore, PipelineAnswer.round_id, Pipeline.codigo)
        .join(PipelineAnswer, PipelineAnswer.id == RagasScore.answer_id)  # type: ignore[arg-type]
        .join(Pipeline, Pipeline.id == PipelineAnswer.pipeline_id)  # type: ignore[arg-type]
        .where(PipelineAnswer.round_id.in_([rodada.id for rodada in rodadas]))  # type: ignore[attr-defined]
    ).all()
    return [
        {
            "rodada": rodada_id,
            "codigo": codigo,
            **{metrica: getattr(nota, metrica) for metrica in METRICAS_RAGAS},
        }
        for nota, rodada_id, codigo in registros
        if nota.erro is None
    ]


def analisar_estudo(sessao: Session, study_id: uuid.UUID) -> dict:
    codigos = sorted(
        {
            codigo
            for codigo in sessao.exec(
                select(Pipeline.codigo)
                .join(PipelineAnswer, PipelineAnswer.pipeline_id == Pipeline.id)  # type: ignore[arg-type]
                .join(QuestionRound, QuestionRound.id == PipelineAnswer.round_id)  # type: ignore[arg-type]
                .join(EvaluationSession, EvaluationSession.id == QuestionRound.session_id)  # type: ignore[arg-type]
                .where(EvaluationSession.study_id == study_id)
            ).all()
        }
    )
    rodadas = carregar_rodadas(sessao, study_id)
    return {
        **analisar_escolhas(rodadas, codigos),
        "custo": analisar_custo(sessao, study_id, codigos),
        "ragas": analisar_ragas(linhas_ragas(sessao, rodadas), rodadas, codigos),
    }
