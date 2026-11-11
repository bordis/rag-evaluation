"""Analise de um estudo: H1 a H3, validade da coleta, custo, concordancia com o RAGAS e erros.

Cada efeito do 2x2 vira uma pergunta binaria sobre a rodada, com 50% como hipotese nula:
- ingestao (H1): a resposta vencedora veio de um pipeline com Docling?
- recuperacao (H2): veio de um pipeline com recuperacao avancada?
- interacao (H3): veio da diagonal 1/4, em vez de 2/3? Sem interacao, as diagonais empatam.

Os tres contrastes sao ortogonais, e a escolha de um vencedor por rodada elimina a dependencia que
apareceria ao tratar as quatro respostas como quatro observacoes. Rodadas "nenhuma" nao tem vencedor
e ficam fora desses testes, reportadas a parte. O IC por bootstrap reamostra avaliadores, porque as
rodadas de um mesmo avaliador nao sao independentes. O modelo misto com efeito aleatorio de
avaliador e documento esta em `analise/modelo_misto.R`, sobre o CSV exportado.

Fontes dos complementos: Holm/Bonferroni, tamanho de efeito e efeitos de ordem (van der Lee et al.,
2021); poder para uma faixa de efeitos e erro Type-M, nunca post hoc (Card et al., 2020); faixas
de posicao com correcao de multiplicidade (Chiang et al., 2024); confiabilidade split-half
(Kiritchenko e Mohammad, 2017); vies de tamanho e concordancia pela distancia entre os sistemas
(Zheng et al., 2023); leitura diagnostica retriever x gerador (Friel et al., 2024).
"""

import math
import random
import uuid
from collections import defaultdict
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass, field
from statistics import fmean, median

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.config import get_settings
from app.models.document import Document, DocumentIngestion
from app.models.evaluation import (
    EvaluationSession,
    PipelineAnswer,
    QuestionRound,
    RoundFailure,
)
from app.models.pipeline import ParserType, Pipeline
from app.models.study import Study
from app.models.telemetry import (
    AnswerAnnotation,
    AnswerStageMetric,
    EtapaChunk,
    RagasScore,
    RetrievedChunk,
)

ITERACOES_BOOTSTRAP = 2000
SEMENTE_BOOTSTRAP = 20260
ACASO = 0.25
METRICAS_RAGAS = ("media", "fidelidade", "relevancia_resposta", "precisao_contexto")
ALFA = 0.05
PODER_ALVO = 0.8
# Efeitos plausiveis, nao observados: calcular o poder com o efeito medido e a armadilha post hoc.
TAXAS_PLAUSIVEIS = (0.55, 0.60, 0.65, 0.70)
# Faixas previstas no protocolo do estudo.
META_AVALIADORES = (10, 30)
META_RODADAS = (100, 300)
RODADAS_POR_CICLO = 10
ULTIMA_ORDEM_DA_PRIMEIRA_METADE = 5
DIVISOES_SPLIT_HALF = 100
# Convencao desta triagem, nao um valor da literatura: abaixo disso a nota do RAGAS e "baixa".
LIMIAR_NOTA_BAIXA = 0.5
Z_SIMULTANEO_4 = 2.498  # Bonferroni para 4 intervalos: alfa/4 bicaudal.
PIPELINE_REFERENCIA = "pipeline-1"
DOCLING = {"pipeline-2", "pipeline-4"}
AVANCADOS = {"pipeline-3", "pipeline-4"}
# (a favor, contra, fator, condicao): cada par muda um so fator.
COMPARACOES_SIMPLES = (
    ("pipeline-2", "pipeline-1", "ingestao", "com recuperação básica"),
    ("pipeline-4", "pipeline-3", "ingestao", "com recuperação avançada"),
    ("pipeline-3", "pipeline-1", "recuperacao", "com texto bruto"),
    ("pipeline-4", "pipeline-2", "recuperacao", "com Docling"),
)


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
    pergunta: str = ""
    # Por codigo de pipeline: tamanho da resposta e posicao em que foi exibida.
    tamanhos: dict[str, int] = field(default_factory=dict)
    posicoes: dict[str, int] = field(default_factory=dict)
    tempo_pergunta_ms: int | None = None
    respostas_vistas: int | None = None
    recarregamentos: int | None = None
    # Codigos dos pipelines cuja resposta foi cortada pelo limite de tokens.
    truncadas: tuple[str, ...] = ()
    # Por codigo de pipeline, para ligar a rodada as anotacoes do pesquisador.
    respostas_ids: dict[str, uuid.UUID] = field(default_factory=dict)


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
    return _cauda_bicaudal(massa_binomial(total, p), sucessos)


def massa_binomial(total: int, p: float) -> list[float]:
    """Em log: `math.comb` estoura o float por volta de mil rodadas."""
    log_p, log_q = math.log(p), math.log1p(-p)
    log_total = math.lgamma(total + 1)
    return [
        math.exp(
            log_total
            - math.lgamma(k + 1)
            - math.lgamma(total - k + 1)
            + k * log_p
            + (total - k) * log_q
        )
        for k in range(total + 1)
    ]


def _cauda_bicaudal(massa: list[float], k: int) -> float:
    return min(1.0, sum(valor for valor in massa if valor <= massa[k] * (1 + 1e-9)))


def holm(valores: list[float | None]) -> list[float | None]:
    """Ajuste de Holm: controla o erro de familia e perde menos poder que Bonferroni puro."""
    validos = sorted((p, i) for i, p in enumerate(valores) if p is not None)
    ajustados: list[float | None] = [None] * len(valores)
    maior = 0.0
    for posto, (p, indice) in enumerate(validos):
        maior = max(maior, min(1.0, p * (len(validos) - posto)))
        ajustados[indice] = maior
    return ajustados


def qui_quadrado_uniforme(contagens: list[int]) -> dict | None:
    """Aderencia a distribuicao uniforme, para 4 categorias (3 graus de liberdade)."""
    total = sum(contagens)
    if total == 0 or len(contagens) != 4:
        return None
    esperado = total / 4
    estatistica = sum((valor - esperado) ** 2 / esperado for valor in contagens)
    # Forma fechada da cauda da qui-quadrado com 3 graus de liberdade.
    p_valor = math.erfc(math.sqrt(estatistica / 2)) + math.sqrt(
        2 * estatistica / math.pi
    ) * math.exp(-estatistica / 2)
    return {"qui2": estatistica, "gl": 3, "p_valor": min(1.0, p_valor)}


def duas_proporcoes(s1: int, n1: int, s2: int, n2: int) -> float | None:
    """p bicaudal do teste z com variancia combinada."""
    if n1 == 0 or n2 == 0:
        return None
    combinada = (s1 + s2) / (n1 + n2)
    erro = math.sqrt(combinada * (1 - combinada) * (1 / n1 + 1 / n2))
    if erro == 0:
        return 1.0
    return math.erfc(abs(s1 / n1 - s2 / n2) / erro / math.sqrt(2))


def _menor_k_significativo(total: int) -> int | None:
    """Menor k acima de n/2 que rejeita 50% no teste exato."""
    massa = massa_binomial(total, 0.5)
    for k in range(total // 2, total + 1):
        if k > total - k and _cauda_bicaudal(massa, k) <= ALFA:
            return k
    return None


def poder_exato(total: int, taxa: float) -> dict:
    """Poder do teste contra 50% se a taxa real for `taxa`, e o exagero dos significativos."""
    return _poder_com_regiao(total, taxa, _menor_k_significativo(total))


def _poder_com_regiao(total: int, taxa: float, critico: int | None) -> dict:
    if critico is None:
        return {"taxa_real": taxa, "poder": 0.0, "exagero": None}
    massa = massa_binomial(total, taxa)
    # So conta com o sinal certo (Card et al., 2020, Fig. 2).
    poder = sum(massa[critico:])
    if poder == 0:
        return {"taxa_real": taxa, "poder": 0.0, "exagero": None}
    media = sum(k / total * massa[k] for k in range(critico, total + 1)) / poder
    return {"taxa_real": taxa, "poder": poder, "exagero": (media - 0.5) / (taxa - 0.5)}


def analisar_poder(total: int) -> dict | None:
    """Trata as rodadas como independentes; com avaliadores diferentes, e um teto otimista."""
    if total == 0:
        return None
    critico = _menor_k_significativo(total)
    # Taxa em milesimos: 0,505 a 0,995.
    taxa_minima = next(
        (
            milesimos / 1000
            for milesimos in range(505, 1000, 5)
            if _poder_com_regiao(total, milesimos / 1000, critico)["poder"] >= PODER_ALVO
        ),
        None,
    )
    return {
        "rodadas": total,
        "alfa": ALFA,
        "poder_alvo": PODER_ALVO,
        "taxa_minima_detectavel": taxa_minima,
        "cenarios": [_poder_com_regiao(total, taxa, critico) for taxa in TAXAS_PLAUSIVEIS],
    }


def bootstrap_por_grupo(
    rodadas: list[tuple[Hashable, bool]],
) -> tuple[float, float] | None:
    if not rodadas:
        return None
    por_grupo: dict[Hashable, list[bool]] = defaultdict(list)
    for grupo, acerto in rodadas:
        por_grupo[grupo].append(acerto)
    grupos = list(por_grupo.values())
    # Um grupo so nao tem o que reamostrar: daria um intervalo de largura zero, enganoso.
    if len(grupos) < 2:
        return None

    gerador = random.Random(SEMENTE_BOOTSTRAP)
    taxas: list[float] = []
    for _ in range(ITERACOES_BOOTSTRAP):
        amostra = [item for grupo in gerador.choices(grupos, k=len(grupos)) for item in grupo]
        taxas.append(sum(amostra) / len(amostra))
    taxas.sort()
    return taxas[int(0.025 * len(taxas))], taxas[int(0.975 * len(taxas)) - 1]


def bootstrap_media_por_grupo(
    valores: list[tuple[Hashable, float]],
) -> tuple[float, float] | None:
    if not valores:
        return None
    por_grupo: dict[Hashable, list[float]] = defaultdict(list)
    for grupo, valor in valores:
        por_grupo[grupo].append(valor)
    if len(por_grupo) < 2:
        return None
    somas = [(sum(itens), len(itens)) for itens in por_grupo.values()]

    gerador = random.Random(SEMENTE_BOOTSTRAP)
    medias: list[float] = []
    for _ in range(ITERACOES_BOOTSTRAP):
        sorteados = gerador.choices(somas, k=len(somas))
        medias.append(sum(s for s, _ in sorteados) / sum(n for _, n in sorteados))
    medias.sort()
    return medias[int(0.025 * len(medias))], medias[int(0.975 * len(medias)) - 1]


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


def postos(valores: list[float]) -> list[float]:
    """Postos medios, para empates."""
    ordenados = sorted(valores)
    return [ordenados.index(valor) + (ordenados.count(valor) - 1) / 2 + 1 for valor in valores]


def spearman(a: list[float], b: list[float]) -> float | None:
    """Pearson sobre postos. None quando uma das ordenacoes e constante."""
    if len(a) < 2:
        return None
    x, y = postos(a), postos(b)
    media_x, media_y = fmean(x), fmean(y)
    numerador = sum((i - media_x) * (j - media_y) for i, j in zip(x, y, strict=True))
    denominador = math.sqrt(sum((i - media_x) ** 2 for i in x) * sum((j - media_y) ** 2 for j in y))
    return numerador / denominador if denominador else None


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
                pergunta=rodada.pergunta,
                tamanhos={pip.codigo: len(res.texto) for res, pip in respostas},
                posicoes={pip.codigo: res.posicao_exibida for res, pip in respostas},
                tempo_pergunta_ms=rodada.tempo_pergunta_ms,
                respostas_vistas=rodada.respostas_vistas,
                recarregamentos=rodada.recarregamentos,
                truncadas=tuple(
                    pip.codigo for res, pip in respostas if res.motivo_parada == "length"
                ),
                respostas_ids={pip.codigo: res.id for res, pip in respostas},
                vencedor=vencedora[1].codigo if vencedora else None,
                posicao=vencedora[0].posicao_exibida if vencedora else None,
                docling=vencedora[1].parser is ParserType.DOCLING if vencedora else None,
                avancado=e_avancado(vencedora[0].config_snapshot) if vencedora else None,
            )
        )
    return rodadas


def tempo_ativo_ms(rodada: Rodada) -> int | None:
    """Tempo de leitura e decisao: tira a pergunta, a espera pela geracao e a aba oculta."""
    if rodada.tempo_total_ms is None:
        return None
    return max(
        0,
        rodada.tempo_total_ms
        - (rodada.tempo_geracao_ms or 0)
        - (rodada.tempo_oculto_ms or 0)
        - (rodada.tempo_pergunta_ms or 0),
    )


def resumo_da_coleta(rodadas: list[Rodada], codigos: Iterable[str], falhas: int) -> dict:
    """O que pode ter atrapalhado a escolha: leitura incompleta, recarga, corte e falha."""
    medidas = [rodada for rodada in rodadas if rodada.respostas_vistas is not None]
    pergunta = [r.tempo_pergunta_ms for r in rodadas if r.tempo_pergunta_ms is not None]
    return {
        "viu_todas": _taxa(sum(r.respostas_vistas == 4 for r in medidas), len(medidas)),
        "tempo_pergunta_mediano_ms": median(pergunta) if pergunta else None,
        "rodadas_recarregadas": sum(bool(r.recarregamentos) for r in rodadas),
        "falhas_de_rodada": falhas,
        "truncadas_por_pipeline": [
            {"codigo": codigo, "respostas": sum(codigo in r.truncadas for r in rodadas)}
            for codigo in codigos
        ],
    }


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
    total = len(acertos)
    return {
        "efeito": nome,
        "descricao": descricao,
        **_taxa(sucessos, total),
        "ic95_bootstrap": bootstrap_por_grupo(acertos),
        "ic95_bootstrap_documento": bootstrap_por_grupo(
            [(rodada.documento, bool(criterio(rodada))) for rodada in rodadas]
        ),
        "p_valor": binomial_bicaudal(sucessos, total),
        "pontos_acima_de_50": (sucessos / total - 0.5) * 100 if total else None,
        # Correcao de Haldane: com 0 derrotas, a razao nao explode.
        "razao_chances": (sucessos + 0.5) / (total - sucessos + 0.5) if total else None,
    }


def _com_holm(efeitos: list[dict]) -> list[dict]:
    ajustados = holm([efeito["p_valor"] for efeito in efeitos])
    return [
        {**efeito, "p_holm": ajustado} for efeito, ajustado in zip(efeitos, ajustados, strict=True)
    ]


def faixas_de_posicao(taxas: dict[str, tuple[int, int]]) -> dict[str, tuple[int, int] | None]:
    """Um pipeline so fica a frente de outro se os intervalos simultaneos nao se sobrepoem."""
    intervalos = {
        codigo: wilson(sucessos, total, Z_SIMULTANEO_4)
        for codigo, (sucessos, total) in taxas.items()
    }
    faixas: dict[str, tuple[int, int] | None] = {}
    for codigo, intervalo in intervalos.items():
        if intervalo is None:
            faixas[codigo] = None
            continue
        outros = [valor for chave, valor in intervalos.items() if chave != codigo and valor]
        melhor = 1 + sum(outro[0] > intervalo[1] for outro in outros)
        pior = 1 + len(outros) - sum(outro[1] < intervalo[0] for outro in outros)
        faixas[codigo] = (melhor, pior)
    return faixas


def comparacoes_simples(rodadas: list[Rodada]) -> list[dict]:
    """Cada par so olha as rodadas vencidas por um dos dois; Bonferroni pelas quatro comparacoes."""
    saida = []
    for favor, contra, fator, condicao in COMPARACOES_SIMPLES:
        grupo = [rodada for rodada in rodadas if rodada.vencedor in (favor, contra)]
        acertos = [(rodada.avaliador, rodada.vencedor == favor) for rodada in grupo]
        sucessos = sum(acerto for _, acerto in acertos)
        p_valor = binomial_bicaudal(sucessos, len(grupo))
        saida.append(
            {
                "a_favor": favor,
                "contra": contra,
                "fator": fator,
                "condicao": condicao,
                **_taxa(sucessos, len(grupo)),
                "ic95_bootstrap": bootstrap_por_grupo(acertos),
                "p_valor": p_valor,
                "p_bonferroni": min(1.0, p_valor * 4) if p_valor is not None else None,
            }
        )
    return saida


def resumo_amostra(rodadas: list[Rodada]) -> dict:
    por_avaliador: dict[uuid.UUID, int] = defaultdict(int)
    ciclos: dict[tuple[uuid.UUID, str], int] = defaultdict(int)
    for rodada in rodadas:
        por_avaliador[rodada.avaliador] += 1
        ciclos[(rodada.avaliador, rodada.documento)] += 1
    contagens = list(por_avaliador.values())
    return {
        "meta_avaliadores": META_AVALIADORES,
        "meta_rodadas": META_RODADAS,
        "documentos": len({rodada.documento for rodada in rodadas}),
        "ciclos": len(ciclos),
        "ciclos_completos": sum(valor >= RODADAS_POR_CICLO for valor in ciclos.values()),
        "rodadas_por_avaliador_min": min(contagens, default=None),
        "rodadas_por_avaliador_mediana": median(contagens) if contagens else None,
        "rodadas_por_avaliador_max": max(contagens, default=None),
    }


def vies_de_tamanho(rodadas: list[Rodada], codigos: Iterable[str]) -> dict:
    """A resposta mais longa ganha mais do que os 25% do acaso? Empates exatos ficam de fora."""
    avaliaveis = []
    for rodada in rodadas:
        if rodada.nenhuma or not rodada.tamanhos:
            continue
        maior = max(rodada.tamanhos.values())
        if sum(valor == maior for valor in rodada.tamanhos.values()) == 1:
            avaliaveis.append(rodada.tamanhos.get(rodada.vencedor or "") == maior)
    sucessos = sum(avaliaveis)

    def caracteres(codigo: str) -> float | None:
        valores = [r.tamanhos[codigo] for r in rodadas if codigo in r.tamanhos]
        return fmean(valores) if valores else None

    return {
        **_taxa(sucessos, len(avaliaveis)),
        "acaso": ACASO,
        "p_valor": binomial_bicaudal(sucessos, len(avaliaveis), ACASO),
        "por_pipeline": [
            {"codigo": codigo, "caracteres_medio": caracteres(codigo)} for codigo in codigos
        ],
    }


def balanceamento_do_sorteio(rodadas: list[Rodada], codigos: Iterable[str]) -> list[dict]:
    """O sorteio simples pode desequilibrar com poucas rodadas; aqui isso fica visivel."""
    saida = []
    for codigo in codigos:
        contagens = [0, 0, 0, 0]
        for rodada in rodadas:
            posicao = rodada.posicoes.get(codigo)
            if posicao in (1, 2, 3, 4):
                contagens[posicao - 1] += 1
        saida.append(
            {"codigo": codigo, "posicoes": contagens, "teste": qui_quadrado_uniforme(contagens)}
        )
    return saida


def comparar_metades(rodadas: list[Rodada]) -> dict | None:
    """Inicio x fim do ciclo. Tempo e so descritivo; proporcoes ganham um teste z."""
    inicio = [r for r in rodadas if r.ordem <= ULTIMA_ORDEM_DA_PRIMEIRA_METADE]
    fim = [r for r in rodadas if r.ordem > ULTIMA_ORDEM_DA_PRIMEIRA_METADE]
    if not inicio or not fim:
        return None

    def decididas(grupo: list[Rodada]) -> list[Rodada]:
        return [rodada for rodada in grupo if not rodada.nenhuma]

    def proporcao(nome: str, filtro: Callable, criterio: Callable) -> dict:
        a, b = filtro(inicio), filtro(fim)
        s_a, s_b = sum(map(criterio, a)), sum(map(criterio, b))
        return {
            "metrica": nome,
            "inicio": s_a / len(a) if a else None,
            "fim": s_b / len(b) if b else None,
            "p_valor": duas_proporcoes(s_a, len(a), s_b, len(b)),
        }

    def mediana_ativa(grupo: list[Rodada]) -> float | None:
        tempos = [t for t in map(tempo_ativo_ms, grupo) if t is not None]
        return median(tempos) if tempos else None

    return {
        "tempo_ativo_inicio_ms": mediana_ativa(inicio),
        "tempo_ativo_fim_ms": mediana_ativa(fim),
        "proporcoes": [
            proporcao("nenhuma", list, lambda r: r.nenhuma),
            proporcao("posicao_1", decididas, lambda r: r.posicao == 1),
            proporcao("avancado", decididas, lambda r: bool(r.avancado)),
            proporcao(
                "viu_todas",
                lambda grupo: [r for r in grupo if r.respostas_vistas is not None],
                lambda r: r.respostas_vistas == 4,
            ),
        ],
    }


def resumo_avaliadores(rodadas: list[Rodada]) -> list[dict]:
    """Sinaliza quem so escolhe uma posicao. Revisar, nao excluir: excluir pede pre-registro."""
    grupos: dict[uuid.UUID, list[Rodada]] = defaultdict(list)
    for rodada in rodadas:
        grupos[rodada.avaliador].append(rodada)
    ordenados = sorted(grupos.items(), key=lambda item: (-len(item[1]), str(item[0])))

    saida = []
    for numero, (avaliador, grupo) in enumerate(ordenados, start=1):
        decididas = [item for item in grupo if not item.nenhuma]
        contagens = [sum(r.posicao == posicao for r in decididas) for posicao in (1, 2, 3, 4)]
        mais_escolhida = max(contagens)
        p_valor = binomial_bicaudal(mais_escolhida, len(decididas), ACASO)
        # Corrige pelas 4 posicoes olhadas e por todos os avaliadores da tabela.
        ajustado = min(1.0, p_valor * 4 * len(ordenados)) if p_valor is not None else None
        ativos = [t for t in map(tempo_ativo_ms, grupo) if t is not None]
        saida.append(
            {
                "numero": numero,
                "avaliador": avaliador,
                "rodadas": len(grupo),
                "documentos": len({item.documento for item in grupo}),
                "nenhuma": sum(item.nenhuma for item in grupo),
                "posicao_preferida": contagens.index(mais_escolhida) + 1 if decididas else None,
                "taxa_posicao_preferida": mais_escolhida / len(decididas) if decididas else None,
                "p_ajustado": ajustado,
                "tempo_ativo_mediano_ms": median(ativos) if ativos else None,
                "revisar": ajustado is not None and ajustado < ALFA,
            }
        )
    return saida


def confiabilidade_split_half(rodadas: list[Rodada], codigos: list[str]) -> dict | None:
    """Duas metades de avaliadores ordenam os pipelines igual? Com 4 itens, so descritivo."""
    grupos: dict[uuid.UUID, list[Rodada]] = defaultdict(list)
    for rodada in rodadas:
        if not rodada.nenhuma:
            grupos[rodada.avaliador].append(rodada)
    if len(grupos) < 4 or len(codigos) < 2:
        return None

    def taxas(avaliadores: list[uuid.UUID]) -> list[float]:
        vitorias = [r.vencedor for a in avaliadores for r in grupos[a]]
        return [vitorias.count(codigo) / len(vitorias) for codigo in codigos]

    gerador = random.Random(SEMENTE_BOOTSTRAP)
    lista = sorted(grupos, key=str)
    correlacoes: list[float] = []
    mesmo_primeiro = 0
    for _ in range(DIVISOES_SPLIT_HALF):
        embaralhados = gerador.sample(lista, k=len(lista))
        meio = len(embaralhados) // 2
        a, b = taxas(embaralhados[:meio]), taxas(embaralhados[meio:])
        mesmo_primeiro += a.index(max(a)) == b.index(max(b))
        if (valor := spearman(a, b)) is not None:
            correlacoes.append(valor)
    return {
        "divisoes": DIVISOES_SPLIT_HALF,
        "spearman_medio": fmean(correlacoes) if correlacoes else None,
        "mesmo_primeiro": mesmo_primeiro / DIVISOES_SPLIT_HALF,
    }


def _proporcao_entre_decididas(grupo: list[Rodada], criterio: Callable) -> float | None:
    decididas = [item for item in grupo if not item.nenhuma]
    return sum(bool(criterio(item)) for item in decididas) / len(decididas) if decididas else None


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
        tamanho_medio = fmean(item.tamanho_respostas for item in grupo)
        return {
            "ordem": ordem,
            "rodadas": len(grupo),
            "nenhuma": sum(item.nenhuma for item in grupo),
            "tempo_ativo_mediano_ms": median(ativos) if ativos else None,
            "tempo_ativo_p25_ms": percentil(ativos, 0.25),
            "tempo_ativo_p75_ms": percentil(ativos, 0.75),
            "tamanho_medio_respostas": tamanho_medio,
            # Respostas maiores levam mais tempo: sem isso, tamanho se confunde com fadiga.
            "ms_por_mil_caracteres": (
                median(ativos) / tamanho_medio * 1000 if ativos and tamanho_medio else None
            ),
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

    codigos = list(codigos)
    vitorias = {
        codigo: (sum(rodada.vencedor == codigo for rodada in com_vencedor), total)
        for codigo in codigos
    }
    faixas = faixas_de_posicao(vitorias)
    contagens_posicao = [
        sum(rodada.posicao == posicao for rodada in com_vencedor) for posicao in (1, 2, 3, 4)
    ]

    return {
        "rodadas_decididas": len(rodadas),
        "avaliadores": len({rodada.avaliador for rodada in rodadas}),
        "amostra": resumo_amostra(rodadas),
        "nenhuma": {
            **_taxa(sum(rodada.nenhuma for rodada in rodadas), len(rodadas)),
            "ic95_bootstrap": bootstrap_por_grupo(
                [(rodada.avaliador, rodada.nenhuma) for rodada in rodadas]
            ),
        },
        "acaso": ACASO,
        "por_pipeline": [
            {
                "codigo": codigo,
                **_taxa(*vitorias[codigo]),
                "ic95_simultaneo": wilson(*vitorias[codigo], Z_SIMULTANEO_4),
                "faixa_posicao": faixas[codigo],
            }
            for codigo in codigos
        ],
        "comparacoes_simples": comparacoes_simples(com_vencedor),
        "poder": analisar_poder(total),
        "efeitos": _com_holm(
            [
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
            ]
        ),
        "por_documento": [
            {
                "documento": documento,
                "rodadas": len(grupo),
                "nenhuma": sum(item.nenhuma for item in grupo),
                "vitorias": {
                    codigo: sum(item.vencedor == codigo for item in grupo) for codigo in codigos
                },
                "avaliadores": len({item.avaliador for item in grupo}),
                "taxa_docling": _proporcao_entre_decididas(grupo, lambda r: r.docling),
                "taxa_avancado": _proporcao_entre_decididas(grupo, lambda r: r.avancado),
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
        "teste_posicao": qui_quadrado_uniforme(contagens_posicao),
        "balanceamento": balanceamento_do_sorteio(rodadas, codigos),
        "por_ordem": [resumo_ordem(ordem, por_ordem[ordem]) for ordem in sorted(por_ordem)],
        "metades": comparar_metades(rodadas),
        "vies_tamanho": vies_de_tamanho(rodadas, codigos),
        "por_avaliador": resumo_avaliadores(rodadas),
        "confiabilidade": confiabilidade_split_half(rodadas, codigos),
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
        sucessos = sum(acertos)
        concordancia.append(
            {
                "metrica": metrica,
                "rodadas": len(acertos),
                "concordancia": fmean(acertos) if acertos else None,
                "ic95": wilson(sucessos, len(acertos)),
                # Empates repartem o acerto; o teste arredonda para o inteiro mais proximo.
                "p_valor": binomial_bicaudal(round(sucessos), len(acertos), ACASO),
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
        "vitorias_comparadas": _vitorias_comparadas(por_rodada, humanas, codigos),
        "por_margem": _concordancia_por_margem(por_rodada, humanas, codigos),
        "efeitos_fatoriais": _efeitos_fatoriais(por_rodada, humanas, codigos),
        "rejeitadas": _notas_das_rejeitadas(por_rodada, humanas, codigos),
    }


def _notas_completas(
    notas: list[dict], metrica: str, codigos: list[str]
) -> dict[str, float] | None:
    validas = {nota["codigo"]: nota[metrica] for nota in notas if nota.get(metrica) is not None}
    return validas if len(validas) == len(codigos) else None


def _vitorias_comparadas(por_rodada: dict, humanas: dict, codigos: list[str]) -> list[dict]:
    """Taxa de vitoria por juiz, nas mesmas rodadas. Empate no RAGAS reparte a vitoria."""
    humano = dict.fromkeys(codigos, 0)
    ragas = dict.fromkeys(codigos, 0.0)
    total = 0
    for rodada_id, notas in por_rodada.items():
        humana = humanas.get(rodada_id)
        completas = _notas_completas(notas, "media", codigos)
        if humana is None or humana.nenhuma or completas is None:
            continue
        total += 1
        humano[humana.vencedor] += 1
        maior = max(completas.values())
        topo = [codigo for codigo, valor in completas.items() if valor == maior]
        for codigo in topo:
            ragas[codigo] += 1 / len(topo)
    return [
        {
            "codigo": codigo,
            "rodadas": total,
            "humano": humano[codigo] / total if total else None,
            "ragas": ragas[codigo] / total if total else None,
        }
        for codigo in codigos
    ]


def _concordancia_por_margem(por_rodada: dict, humanas: dict, codigos: list[str]) -> list[dict]:
    """Em Zheng et al. (2023), juiz e humano concordam mais quando os sistemas sao distantes."""
    itens: list[tuple[float, float]] = []
    for rodada_id, notas in por_rodada.items():
        humana = humanas.get(rodada_id)
        completas = _notas_completas(notas, "media", codigos)
        if humana is None or humana.nenhuma or completas is None or len(completas) < 2:
            continue
        ordenadas = sorted(completas.values(), reverse=True)
        topo = [codigo for codigo, valor in completas.items() if valor == ordenadas[0]]
        acerto = 1 / len(topo) if humana.vencedor in topo else 0.0
        itens.append((ordenadas[0] - ordenadas[1], acerto))
    if not itens:
        return []
    itens.sort(key=lambda item: item[0])
    tercos = [itens[i * len(itens) // 3 : (i + 1) * len(itens) // 3] for i in range(3)]
    return [
        {
            "faixa": nome,
            "rodadas": len(grupo),
            "margem_mediana": median(margem for margem, _ in grupo) if grupo else None,
            "concordancia": fmean(acerto for _, acerto in grupo) if grupo else None,
        }
        for nome, grupo in zip(("pequena", "media", "grande"), tercos, strict=True)
    ]


def _efeitos_fatoriais(por_rodada: dict, humanas: dict, codigos: list[str]) -> list[dict]:
    """Diferenca pareada na mesma rodada: o RAGAS enxerga os mesmos efeitos que as pessoas?"""
    if not (DOCLING | AVANCADOS | {PIPELINE_REFERENCIA}) <= set(codigos):
        return []
    saida = []
    for metrica in METRICAS_RAGAS:
        valores: dict[str, list[tuple[Hashable, float]]] = defaultdict(list)
        for rodada_id, notas in por_rodada.items():
            humana = humanas.get(rodada_id)
            n = _notas_completas(notas, metrica, codigos)
            if humana is None or n is None:
                continue
            um, dois, tres, quatro = (n[f"pipeline-{i}"] for i in (1, 2, 3, 4))
            valores["ingestao"].append((humana.avaliador, (dois + quatro - um - tres) / 2))
            valores["recuperacao"].append((humana.avaliador, (tres + quatro - um - dois) / 2))
            valores["interacao"].append((humana.avaliador, (um + quatro - dois - tres) / 2))
        for efeito in ("ingestao", "recuperacao", "interacao"):
            itens = valores[efeito]
            saida.append(
                {
                    "metrica": metrica,
                    "efeito": efeito,
                    "rodadas": len(itens),
                    "diferenca": fmean(valor for _, valor in itens) if itens else None,
                    "ic95_bootstrap": bootstrap_media_por_grupo(itens),
                }
            )
    return saida


def _notas_das_rejeitadas(por_rodada: dict, humanas: dict, codigos: list[str]) -> dict:
    """A melhor nota do RAGAS e menor quando as pessoas rejeitam as quatro respostas?"""
    rejeitadas: list[float] = []
    decididas: list[float] = []
    for rodada_id, notas in por_rodada.items():
        humana = humanas.get(rodada_id)
        completas = _notas_completas(notas, "media", codigos)
        if humana is None or completas is None:
            continue
        (rejeitadas if humana.nenhuma else decididas).append(max(completas.values()))
    return {
        "rodadas_rejeitadas": len(rejeitadas),
        "rodadas_decididas": len(decididas),
        "melhor_nota_rejeitadas": fmean(rejeitadas) if rejeitadas else None,
        "melhor_nota_decididas": fmean(decididas) if decididas else None,
    }


def classificar_erro(nota: dict | None) -> str:
    """Triagem pelo RAGAS, a ser confirmada lendo os trechos (leitura de Friel et al., 2024)."""
    if nota is None or nota.get("precisao_contexto") is None or nota.get("fidelidade") is None:
        return "sem_nota"
    if nota["precisao_contexto"] < LIMIAR_NOTA_BAIXA:
        return "recuperacao"
    if nota["fidelidade"] < LIMIAR_NOTA_BAIXA:
        return "geracao"
    return "divergencia"


def analisar_erros(
    rodadas: list[Rodada],
    linhas: list[dict],
    codigos: list[str],
    documentos: dict[str, uuid.UUID],
    anotacoes: dict[uuid.UUID, dict] | None = None,
) -> dict:
    """So as rodadas "nenhuma": e onde a pessoa afirmou que todas as respostas estao erradas."""
    notas: dict[tuple[uuid.UUID, str], dict] = {
        (linha["rodada"], linha["codigo"]): linha for linha in linhas
    }
    rejeitadas = [rodada for rodada in rodadas if rodada.nenhuma]
    contagens = {
        codigo: dict.fromkeys(("recuperacao", "geracao", "divergencia", "sem_nota"), 0)
        for codigo in codigos
    }
    anotacoes = anotacoes or {}
    confirmadas: dict[str, dict[str, int]] = {codigo: defaultdict(int) for codigo in codigos}
    casos = []
    for rodada in rejeitadas:
        classes = {codigo: classificar_erro(notas.get((rodada.id, codigo))) for codigo in codigos}
        for codigo, classe in classes.items():
            contagens[codigo][classe] += 1
            anotada = anotacoes.get(rodada.respostas_ids.get(codigo))
            if anotada:
                confirmadas[codigo][anotada["causa"]] += 1
        casos.append(
            {
                "rodada": rodada.id,
                "avaliador": rodada.avaliador,
                "documento": rodada.documento,
                "documento_id": documentos.get(rodada.documento),
                "ordem": rodada.ordem,
                "pergunta": rodada.pergunta,
                "classes": classes,
                "respostas": rodada.respostas_ids,
                "anotacoes": {
                    codigo: anotacoes[answer_id]
                    for codigo, answer_id in rodada.respostas_ids.items()
                    if answer_id in anotacoes
                },
            }
        )
    return {
        "limiar": LIMIAR_NOTA_BAIXA,
        "rodadas": len(rejeitadas),
        "por_pipeline": [{"codigo": codigo, **contagens[codigo]} for codigo in codigos],
        "causas_confirmadas": [
            {"codigo": codigo, "causas": dict(confirmadas[codigo])} for codigo in codigos
        ],
        "casos": casos,
    }


def resumir_contexto(linhas: list[tuple[uuid.UUID, str, int, int]], codigos: list[str]) -> dict:
    """`linhas`: (rodada, codigo, chunk_index, tamanho) do contexto final.

    Verifica a manipulacao: mesma quantidade de contexto, e recuperacoes que de fato diferem.
    """
    por_resposta: dict[tuple[uuid.UUID, str], list[tuple[int, int]]] = defaultdict(list)
    for rodada, codigo, indice, tamanho in linhas:
        por_resposta[(rodada, codigo)].append((indice, tamanho))

    def sobreposicao(a: str, b: str) -> dict:
        valores = []
        for rodada in {rodada for rodada, _ in por_resposta}:
            x = {i for i, _ in por_resposta.get((rodada, a), [])}
            y = {i for i, _ in por_resposta.get((rodada, b), [])}
            if x and y:
                valores.append(len(x & y) / len(x | y))
        return {
            "a": a,
            "b": b,
            "rodadas": len(valores),
            "jaccard_medio": fmean(valores) if valores else None,
        }

    def resumo(codigo: str) -> dict:
        respostas = [v for (_, cod), v in por_resposta.items() if cod == codigo]
        return {
            "codigo": codigo,
            "respostas": len(respostas),
            "chunks_medio": fmean(len(v) for v in respostas) if respostas else None,
            "caracteres_medio": (
                fmean(sum(t for _, t in v) for v in respostas) if respostas else None
            ),
        }

    return {
        "por_pipeline": [resumo(codigo) for codigo in codigos],
        # Chunks so sao comparaveis entre pipelines do mesmo parser.
        "sobreposicao": [
            sobreposicao("pipeline-1", "pipeline-3"),
            sobreposicao("pipeline-2", "pipeline-4"),
        ],
    }


def linhas_contexto(
    sessao: Session, rodadas: list[Rodada]
) -> list[tuple[uuid.UUID, str, int, int]]:
    if not rodadas:
        return []
    registros = sessao.exec(
        select(RetrievedChunk, PipelineAnswer.round_id, Pipeline.codigo)
        .join(PipelineAnswer, PipelineAnswer.id == RetrievedChunk.answer_id)  # type: ignore[arg-type]
        .join(Pipeline, Pipeline.id == PipelineAnswer.pipeline_id)  # type: ignore[arg-type]
        .where(
            PipelineAnswer.round_id.in_([rodada.id for rodada in rodadas]),  # type: ignore[attr-defined]
            RetrievedChunk.etapa == EtapaChunk.CONTEXTO_FINAL,
        )
    ).all()
    return [
        (rodada_id, codigo, chunk.chunk_index, len(chunk.texto))
        for chunk, rodada_id, codigo in registros
    ]


def custo_beneficio(por_pipeline: list[dict], custo: list[dict]) -> list[dict]:
    """Incrementos contra o pipeline de referencia e dominancia de Pareto entre os quatro."""
    custos = {item["codigo"]: item for item in custo}
    referencia = custos.get(PIPELINE_REFERENCIA)
    taxas = {item["codigo"]: item["taxa"] for item in por_pipeline}

    def medidas(codigo: str) -> tuple[float, float, float] | None:
        linha = custos.get(codigo)
        if linha is None or None in (taxas.get(codigo), linha["usd_medio"], linha["ms_p50"]):
            return None
        return taxas[codigo], linha["usd_medio"], linha["ms_p50"]

    def domina(a: str, b: str) -> bool:
        x, y = medidas(a), medidas(b)
        if x is None or y is None:
            return False
        nao_pior = x[0] >= y[0] and x[1] <= y[1] and x[2] <= y[2]
        return nao_pior and x != y

    saida = []
    for item in por_pipeline:
        codigo = item["codigo"]
        linha = custos.get(codigo)
        if linha is None or linha["usd_medio"] is None:
            continue
        saida.append(
            {
                "codigo": codigo,
                "taxa": item["taxa"],
                "ic95": item["ic95"],
                "usd_medio": linha["usd_medio"],
                "usd_por_mil_perguntas": linha["usd_medio"] * 1000,
                "ms_p50": linha["ms_p50"],
                "tokens_medio": linha["tokens_medio"],
                "delta_pontos": (
                    (item["taxa"] - taxas[PIPELINE_REFERENCIA]) * 100
                    if item["taxa"] is not None and taxas.get(PIPELINE_REFERENCIA) is not None
                    else None
                ),
                "multiplo_usd": (
                    linha["usd_medio"] / referencia["usd_medio"]
                    if referencia and referencia["usd_medio"]
                    else None
                ),
                "multiplo_latencia": (
                    linha["ms_p50"] / referencia["ms_p50"]
                    if referencia and referencia["ms_p50"] and linha["ms_p50"] is not None
                    else None
                ),
                "dominado_por": sorted(
                    outro for outro in custos if outro != codigo and domina(outro, codigo)
                ),
            }
        )
    return saida


def analisar_custo(sessao: Session, study_id: uuid.UUID, codigos: list[str]) -> dict:
    linhas = sessao.exec(
        select(
            AnswerStageMetric, Pipeline.codigo, PipelineAnswer.id, QuestionRound.rodadas_simultaneas
        )
        .join(PipelineAnswer, PipelineAnswer.id == AnswerStageMetric.answer_id)  # type: ignore[arg-type]
        .join(Pipeline, Pipeline.id == PipelineAnswer.pipeline_id)  # type: ignore[arg-type]
        .join(QuestionRound, QuestionRound.id == PipelineAnswer.round_id)  # type: ignore[arg-type]
        .join(EvaluationSession, EvaluationSession.id == QuestionRound.session_id)  # type: ignore[arg-type]
        .where(EvaluationSession.study_id == study_id)
    ).all()

    por_etapa: dict[tuple[str, str], list[AnswerStageMetric]] = defaultdict(list)
    por_resposta: dict[tuple[str, uuid.UUID], dict] = defaultdict(
        lambda: {"ms": 0, "tokens": 0, "usd": 0.0, "sozinha": False}
    )
    for metrica, codigo, answer_id, simultaneas in linhas:
        por_etapa[(codigo, metrica.etapa.value)].append(metrica)
        acumulado = por_resposta[(codigo, answer_id)]
        acumulado["ms"] += metrica.duracao_ms
        acumulado["tokens"] += metrica.tokens_total or 0
        acumulado["usd"] += metrica.custo_usd or 0.0
        acumulado["sozinha"] = simultaneas == 1

    def resumo_etapa(codigo: str, etapa: str, itens: list[AnswerStageMetric]) -> dict:
        duracoes = [item.duracao_ms for item in itens]
        tokens = [item.tokens_total for item in itens if item.tokens_total is not None]
        custos = [item.custo_usd for item in itens if item.custo_usd is not None]
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
            # So rodadas sem concorrencia: e a latencia que se pode citar para o reordenador em CPU.
            "ms_p50_sem_concorrencia": percentil(
                [item["ms"] for item in itens if item["sozinha"]], 0.5
            ),
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
                "parsing_participacao": (
                    sum(item.duracao_parsing_ms for item in itens) / total_ms
                    if (total_ms := sum(item.duracao_total_ms for item in itens))
                    else None
                ),
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
    escolhas = analisar_escolhas(rodadas, codigos)
    custo = analisar_custo(sessao, study_id, codigos)
    notas = linhas_ragas(sessao, rodadas)
    documentos = {doc.slug: doc.id for doc in sessao.exec(select(Document)).all()}
    falhas = sessao.exec(
        select(func.count())
        .select_from(RoundFailure)
        .join(EvaluationSession, EvaluationSession.id == RoundFailure.session_id)  # type: ignore[arg-type]
        .where(EvaluationSession.study_id == study_id)
    ).one()
    anotacoes = {
        item.answer_id: {"causa": item.causa.value, "nota": item.nota}
        for item in sessao.exec(
            select(AnswerAnnotation).where(
                AnswerAnnotation.answer_id.in_(  # type: ignore[attr-defined]
                    [answer_id for rodada in rodadas for answer_id in rodada.respostas_ids.values()]
                )
            )
        ).all()
    }
    estudo = sessao.get(Study, study_id)
    return {
        **escolhas,
        "coleta": resumo_da_coleta(rodadas, codigos, int(falhas)),
        "ambiente": estudo.config_snapshot if estudo else {},
        "custo": custo,
        "custo_beneficio": custo_beneficio(escolhas["por_pipeline"], custo["por_pipeline"]),
        "contexto": resumir_contexto(linhas_contexto(sessao, rodadas), codigos),
        "ragas": analisar_ragas(notas, rodadas, codigos),
        "erros": analisar_erros(rodadas, notas, codigos, documentos, anotacoes),
    }
