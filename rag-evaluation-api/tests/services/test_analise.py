import uuid
from dataclasses import replace

import pytest

from app.services.analise import (
    Rodada,
    analisar_erros,
    analisar_escolhas,
    analisar_poder,
    analisar_ragas,
    binomial_bicaudal,
    bootstrap_por_grupo,
    classificar_erro,
    comparacoes_simples,
    comparar_metades,
    confiabilidade_split_half,
    custo_beneficio,
    custo_usd,
    faixas_de_posicao,
    holm,
    kendall_tau,
    percentil,
    poder_exato,
    qui_quadrado_uniforme,
    resumir_contexto,
    resumo_avaliadores,
    resumo_da_coleta,
    spearman,
    tempo_ativo_ms,
    vies_de_tamanho,
    wilson,
)

CODIGOS = ["pipeline-1", "pipeline-2", "pipeline-3", "pipeline-4"]
FATORES = {
    "pipeline-1": (False, False),
    "pipeline-2": (True, False),
    "pipeline-3": (False, True),
    "pipeline-4": (True, True),
}
AVALIADOR = uuid.uuid4()


def _rodada(vencedor: str | None, *, ordem: int = 1, posicao: int = 1, avaliador=AVALIADOR):
    docling, avancado = FATORES.get(vencedor, (None, None))
    return Rodada(
        id=uuid.uuid4(),
        avaliador=avaliador,
        documento="lgpd",
        ordem=ordem,
        nenhuma=vencedor is None,
        tempo_total_ms=60000,
        tempo_geracao_ms=10000,
        tempo_oculto_ms=5000,
        tamanho_respostas=1000,
        vencedor=vencedor,
        posicao=posicao if vencedor else None,
        docling=docling,
        avancado=avancado,
    )


def _efeito(resultado: dict, nome: str) -> dict:
    return next(item for item in resultado["efeitos"] if item["efeito"] == nome)


def test_efeitos_do_fatorial_contam_as_margens_certas():
    rodadas = [_rodada("pipeline-4")] * 2 + [_rodada("pipeline-2"), _rodada("pipeline-1")]

    resultado = analisar_escolhas(rodadas, CODIGOS)

    assert _efeito(resultado, "ingestao")["sucessos"] == 3
    assert _efeito(resultado, "recuperacao")["sucessos"] == 2
    assert _efeito(resultado, "interacao")["sucessos"] == 3


def test_nenhuma_fica_fora_dos_efeitos_e_e_reportada_a_parte():
    resultado = analisar_escolhas([_rodada("pipeline-4"), _rodada(None)], CODIGOS)

    assert resultado["nenhuma"]["sucessos"] == 1
    assert resultado["nenhuma"]["total"] == 2
    assert _efeito(resultado, "ingestao")["total"] == 1


def test_taxa_por_pipeline_usa_so_rodadas_com_vencedor():
    resultado = analisar_escolhas([_rodada("pipeline-2"), _rodada(None)], CODIGOS)

    taxa = next(i for i in resultado["por_pipeline"] if i["codigo"] == "pipeline-2")
    assert taxa["taxa"] == 1.0


def test_vies_de_posicao_e_fadiga_por_ordem():
    rodadas = [
        _rodada("pipeline-1", ordem=1, posicao=1),
        _rodada("pipeline-3", ordem=1, posicao=2),
        _rodada("pipeline-4", ordem=2, posicao=1),
    ]

    resultado = analisar_escolhas(rodadas, CODIGOS)

    assert resultado["por_posicao"][0]["sucessos"] == 2
    primeira, segunda = resultado["por_ordem"]
    assert primeira["taxa_posicao_1"] == 0.5
    assert segunda["taxa_avancado"] == 1.0
    assert primeira["tempo_ativo_mediano_ms"] == 45000


def test_tempo_ativo_tira_a_geracao_e_a_aba_oculta():
    assert tempo_ativo_ms(_rodada("pipeline-1")) == 45000


def test_wilson_contem_a_proporcao():
    baixo, alto = wilson(5, 10)

    assert baixo < 0.5 < alto
    assert wilson(0, 0) is None


def test_binomial_conhecida():
    assert binomial_bicaudal(5, 10) == pytest.approx(1.0)
    assert binomial_bicaudal(10, 10) == pytest.approx(2 / 1024)
    assert binomial_bicaudal(0, 0) is None


def test_bootstrap_reamostra_avaliadores_e_e_reprodutivel():
    a, b = uuid.uuid4(), uuid.uuid4()
    rodadas = [(a, True)] * 10 + [(b, False)] * 10

    primeiro = bootstrap_por_grupo(rodadas)

    # Com dois avaliadores opostos, a reamostra por avaliador produz taxas de 0 a 1.
    assert primeiro == (0.0, 1.0)
    assert primeiro == bootstrap_por_grupo(rodadas)


def test_percentil_interpola():
    assert percentil([0, 10], 0.5) == 5
    assert percentil([], 0.5) is None


def test_kendall():
    assert kendall_tau([1, 2, 3, 4], [1, 2, 3, 4]) == 1
    assert kendall_tau([1, 2, 3, 4], [4, 3, 2, 1]) == -1


def test_custo_casa_o_snapshot_com_o_preco_e_nao_inventa_sem_tokens():
    assert custo_usd("gpt-4.1-mini-2025-04-14", 1_000_000, 0) == pytest.approx(0.40)
    assert custo_usd("gpt-4.1-2025-04-14", 0, 1_000_000) == pytest.approx(12.0)
    assert custo_usd("BAAI/bge-reranker-v2-m3", None, None) is None
    assert custo_usd("modelo-desconhecido", 10, 10) is None


def _notas(rodada: Rodada, maior: str) -> list[dict]:
    return [
        {
            "rodada": rodada.id,
            "codigo": codigo,
            "media": 0.9 if codigo == maior else 0.1,
            "fidelidade": 0.5,
            "relevancia_resposta": 0.9 if codigo == maior else 0.1,
            "precisao_contexto": None,
        }
        for codigo in CODIGOS
    ]


def test_ragas_concorda_quando_aponta_a_escolha_humana():
    acerto, erro = _rodada("pipeline-4"), _rodada("pipeline-1")
    linhas = [*_notas(acerto, "pipeline-4"), *_notas(erro, "pipeline-2")]

    resultado = analisar_ragas(linhas, [acerto, erro], CODIGOS)

    media = next(i for i in resultado["concordancia"] if i["metrica"] == "media")
    assert media["concordancia"] == 0.5
    assert media["rodadas"] == 2


def test_empate_no_ragas_reparte_o_acerto():
    rodada = _rodada("pipeline-4")

    resultado = analisar_ragas(_notas(rodada, "pipeline-4"), [rodada], CODIGOS)

    fidelidade = next(i for i in resultado["concordancia"] if i["metrica"] == "fidelidade")
    assert fidelidade["concordancia"] == 0.25


def test_rodada_nenhuma_e_metrica_sem_nota_ficam_fora_da_concordancia():
    rodada = _rodada(None)

    resultado = analisar_ragas(_notas(rodada, "pipeline-4"), [rodada], CODIGOS)

    assert all(item["rodadas"] == 0 for item in resultado["concordancia"])


def test_holm_ajusta_pela_ordem_e_mantem_monotonia():
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm([None, 0.5]) == [None, 0.5]


def test_binomial_nao_estoura_com_muitas_rodadas():
    assert binomial_bicaudal(1500, 3000) == pytest.approx(1.0)


def test_qui_quadrado_uniforme_bate_com_a_tabela():
    assert qui_quadrado_uniforme([10, 10, 10, 10])["p_valor"] == pytest.approx(1.0)
    assert qui_quadrado_uniforme([0, 0, 0, 0]) is None
    # Tabela da qui-quadrado com 3 graus de liberdade: 8,0 da p = 0,046.
    teste = qui_quadrado_uniforme([35, 15, 25, 25])
    assert teste["qui2"] == pytest.approx(8.0)
    assert teste["p_valor"] == pytest.approx(0.046, abs=0.001)


def test_poder_bate_com_o_exemplo_de_card():
    # Card et al. (2020): 65% de preferencia, n = 100 passa de 80%; n = 25, cerca de 30%.
    assert poder_exato(100, 0.65)["poder"] > 0.8
    assert 0.2 < poder_exato(25, 0.65)["poder"] < 0.4


def test_poder_baixo_exagera_o_efeito():
    assert poder_exato(25, 0.55)["exagero"] > poder_exato(400, 0.55)["exagero"]


def test_taxa_minima_detectavel_diminui_com_a_amostra():
    assert (
        analisar_poder(500)["taxa_minima_detectavel"] < analisar_poder(50)["taxa_minima_detectavel"]
    )
    assert analisar_poder(0) is None


def test_faixa_so_separa_quando_os_intervalos_nao_se_sobrepoem():
    separadas = faixas_de_posicao({"a": (90, 100), "b": (10, 100)})
    assert separadas == {"a": (1, 1), "b": (2, 2)}
    empatadas = faixas_de_posicao({"a": (6, 10), "b": (4, 10)})
    assert empatadas == {"a": (1, 2), "b": (1, 2)}


def test_comparacoes_simples_olham_so_o_par():
    rodadas = [_rodada("pipeline-2")] * 3 + [_rodada("pipeline-1"), _rodada("pipeline-4")]

    comparacao = comparacoes_simples(rodadas)[0]

    assert (comparacao["a_favor"], comparacao["contra"]) == ("pipeline-2", "pipeline-1")
    assert (comparacao["sucessos"], comparacao["total"]) == (3, 4)
    assert comparacao["p_bonferroni"] == min(1.0, comparacao["p_valor"] * 4)


def test_efeitos_trazem_tamanho_e_p_ajustado():
    rodadas = [_rodada("pipeline-4")] * 6 + [_rodada("pipeline-1")] * 2

    ingestao = _efeito(analisar_escolhas(rodadas, CODIGOS), "ingestao")

    assert ingestao["pontos_acima_de_50"] == pytest.approx(25)
    assert ingestao["razao_chances"] == pytest.approx(6.5 / 2.5)
    assert ingestao["p_holm"] >= ingestao["p_valor"]


def test_vies_de_tamanho_conta_a_mais_longa_e_ignora_empate():
    longa = {**dict.fromkeys(CODIGOS, 100), "pipeline-4": 500}
    empate = dict.fromkeys(CODIGOS, 100)
    rodadas = [
        replace(_rodada("pipeline-4"), tamanhos=longa),
        replace(_rodada("pipeline-1"), tamanhos=longa),
        replace(_rodada("pipeline-1"), tamanhos=empate),
    ]

    resultado = vies_de_tamanho(rodadas, CODIGOS)

    assert (resultado["sucessos"], resultado["total"]) == (1, 2)


def test_metades_comparam_inicio_e_fim_do_ciclo():
    metades = comparar_metades([_rodada("pipeline-1", ordem=1), _rodada(None, ordem=6)])

    nenhuma = next(p for p in metades["proporcoes"] if p["metrica"] == "nenhuma")
    assert (nenhuma["inicio"], nenhuma["fim"]) == (0, 1)
    assert comparar_metades([_rodada("pipeline-1", ordem=1)]) is None


def test_avaliador_que_so_escolhe_uma_posicao_fica_para_revisao():
    constante, variado = uuid.uuid4(), uuid.uuid4()
    rodadas = [_rodada("pipeline-1", posicao=1, avaliador=constante) for _ in range(30)]
    rodadas += [_rodada("pipeline-1", posicao=i % 4 + 1, avaliador=variado) for i in range(12)]

    por_avaliador = {item["avaliador"]: item for item in resumo_avaliadores(rodadas)}

    assert por_avaliador[constante]["revisar"] is True
    assert por_avaliador[variado]["revisar"] is False


def test_avaliador_so_com_nenhuma_nao_quebra_o_resumo():
    resumo = resumo_avaliadores([_rodada(None)])[0]

    assert resumo["posicao_preferida"] is None
    assert resumo["revisar"] is False


def test_split_half_exige_quatro_avaliadores_e_e_reprodutivel():
    assert confiabilidade_split_half([_rodada("pipeline-1")], CODIGOS) is None
    rodadas = [
        _rodada(codigo, avaliador=avaliador)
        for avaliador in [uuid.uuid4() for _ in range(6)]
        for codigo in ["pipeline-4"] * 5 + ["pipeline-3"] * 3 + ["pipeline-2", "pipeline-1"]
    ]

    resultado = confiabilidade_split_half(rodadas, CODIGOS)

    assert resultado == confiabilidade_split_half(rodadas, CODIGOS)
    assert resultado["mesmo_primeiro"] == 1.0
    assert resultado["spearman_medio"] == pytest.approx(1.0)


def test_spearman_com_empate_e_constante():
    assert spearman([1, 2, 3], [1, 2, 3]) == pytest.approx(1)
    assert spearman([1, 1, 2], [1, 2, 3]) is not None
    assert spearman([1, 1, 1], [1, 2, 3]) is None


def test_ragas_compara_vitorias_margem_e_efeitos():
    rodada = _rodada("pipeline-4")
    linhas = [
        {
            "rodada": rodada.id,
            "codigo": codigo,
            "media": nota,
            "fidelidade": nota,
            "relevancia_resposta": nota,
            "precisao_contexto": nota,
        }
        for codigo, nota in zip(CODIGOS, (0.1, 0.2, 0.3, 0.8), strict=True)
    ]

    resultado = analisar_ragas(linhas, [rodada], CODIGOS)

    quarto = next(i for i in resultado["vitorias_comparadas"] if i["codigo"] == "pipeline-4")
    assert (quarto["ragas"], quarto["humano"]) == (1, 1)
    efeito = next(
        i
        for i in resultado["efeitos_fatoriais"]
        if i["metrica"] == "media" and i["efeito"] == "recuperacao"
    )
    assert efeito["diferenca"] == pytest.approx(0.4)
    assert sum(item["rodadas"] for item in resultado["por_margem"]) == 1


def test_triagem_de_erro_separa_recuperacao_e_geracao():
    assert classificar_erro({"precisao_contexto": 0.2, "fidelidade": 0.9}) == "recuperacao"
    assert classificar_erro({"precisao_contexto": 0.8, "fidelidade": 0.2}) == "geracao"
    assert classificar_erro({"precisao_contexto": 0.8, "fidelidade": 0.8}) == "divergencia"
    assert classificar_erro(None) == "sem_nota"


def test_analise_de_erros_so_olha_as_rodadas_nenhuma():
    erros = analisar_erros([_rodada(None), _rodada("pipeline-1")], [], CODIGOS, {})

    assert erros["rodadas"] == 1
    assert erros["por_pipeline"][0]["sem_nota"] == 1


def test_contexto_mede_chunks_e_sobreposicao():
    rodada = uuid.uuid4()
    linhas = [
        (rodada, "pipeline-1", 1, 100),
        (rodada, "pipeline-1", 2, 100),
        (rodada, "pipeline-3", 2, 100),
        (rodada, "pipeline-3", 3, 100),
    ]

    contexto = resumir_contexto(linhas, CODIGOS)

    assert contexto["por_pipeline"][0]["chunks_medio"] == 2
    assert contexto["sobreposicao"][0]["jaccard_medio"] == pytest.approx(1 / 3)


def test_custo_beneficio_marca_dominados_e_incrementos():
    pipelines = [
        {"codigo": "pipeline-1", "taxa": 0.2, "ic95": None},
        {"codigo": "pipeline-4", "taxa": 0.4, "ic95": None},
        {"codigo": "pipeline-3", "taxa": 0.2, "ic95": None},
    ]
    custos = [
        {"codigo": "pipeline-1", "usd_medio": 0.001, "ms_p50": 1000, "tokens_medio": 10},
        {"codigo": "pipeline-4", "usd_medio": 0.002, "ms_p50": 2000, "tokens_medio": 20},
        {"codigo": "pipeline-3", "usd_medio": 0.002, "ms_p50": 2000, "tokens_medio": 20},
    ]

    linhas = {item["codigo"]: item for item in custo_beneficio(pipelines, custos)}

    assert linhas["pipeline-4"]["delta_pontos"] == pytest.approx(20)
    assert linhas["pipeline-4"]["multiplo_usd"] == pytest.approx(2)
    assert linhas["pipeline-4"]["dominado_por"] == []
    assert linhas["pipeline-3"]["dominado_por"] == ["pipeline-1", "pipeline-4"]


def test_bootstrap_com_um_grupo_so_nao_inventa_intervalo():
    assert bootstrap_por_grupo([("lgpd", True), ("lgpd", False)]) is None


def test_tempo_ativo_tambem_tira_a_escrita_da_pergunta():
    assert tempo_ativo_ms(replace(_rodada("pipeline-1"), tempo_pergunta_ms=15000)) == 30000


def test_resumo_da_coleta_conta_leitura_corte_e_falha():
    rodadas = [
        replace(_rodada("pipeline-1"), respostas_vistas=4, truncadas=("pipeline-3",)),
        replace(_rodada("pipeline-1"), respostas_vistas=2, recarregamentos=1),
        _rodada("pipeline-1"),
    ]

    coleta = resumo_da_coleta(rodadas, CODIGOS, falhas=3)

    assert (coleta["viu_todas"]["sucessos"], coleta["viu_todas"]["total"]) == (1, 2)
    assert coleta["rodadas_recarregadas"] == 1
    assert coleta["falhas_de_rodada"] == 3
    truncadas = {i["codigo"]: i["respostas"] for i in coleta["truncadas_por_pipeline"]}
    assert truncadas["pipeline-3"] == 1


def test_erros_separam_triagem_de_causa_confirmada():
    resposta = uuid.uuid4()
    rejeitada = replace(_rodada(None), respostas_ids={"pipeline-1": resposta})
    anotacoes = {resposta: {"causa": "conversao", "nota": ""}}

    erros = analisar_erros([rejeitada], [], CODIGOS, {}, anotacoes)

    assert erros["causas_confirmadas"][0]["causas"] == {"conversao": 1}
    assert erros["casos"][0]["anotacoes"]["pipeline-1"]["causa"] == "conversao"
