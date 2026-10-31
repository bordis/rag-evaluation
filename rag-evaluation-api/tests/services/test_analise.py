import uuid

import pytest

from app.services.analise import (
    Rodada,
    analisar_escolhas,
    analisar_ragas,
    binomial_bicaudal,
    bootstrap_por_avaliador,
    custo_usd,
    kendall_tau,
    percentil,
    tempo_ativo_ms,
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

    primeiro = bootstrap_por_avaliador(rodadas)

    # Com dois avaliadores opostos, a reamostra por avaliador produz taxas de 0 a 1.
    assert primeiro == (0.0, 1.0)
    assert primeiro == bootstrap_por_avaliador(rodadas)


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
