import json

import httpx
import pytest

from app.core.config import get_settings
from app.models.telemetry import EtapaPipeline
from app.rag.retrieval.base import Candidato
from app.rag.retrieval.rerank import reordenar

PERGUNTA = "O que e dado pessoal?"


def _candidatos(quantidade: int) -> list[Candidato]:
    return [
        Candidato(
            milvus_id=1000 + numero,
            chunk_index=numero,
            texto=f"trecho {numero}",
            score_final=0.5,
            score_denso=0.7,
        )
        for numero in range(quantidade)
    ]


def _cliente(ordem: list[int], capturadas: list[dict] | None = None) -> httpx.Client:
    def responder(requisicao: httpx.Request) -> httpx.Response:
        if capturadas is not None:
            capturadas.append(json.loads(requisicao.content))
        return httpx.Response(
            200,
            headers={"x-inference-time": "90", "x-queue-time": "10"},
            json=[
                {"index": indice, "score": 1 - posicao / 10} for posicao, indice in enumerate(ordem)
            ],
        )

    return httpx.Client(
        transport=httpx.MockTransport(responder), base_url="http://reordenador.invalido"
    )


def test_devolve_todos_na_ordem_do_modelo_com_o_score_dele():
    ordenados, _ = reordenar(PERGUNTA, _candidatos(3), cliente=_cliente([2, 0, 1]))

    assert [item.chunk_index for item in ordenados] == [2, 0, 1]
    assert [item.score_final for item in ordenados] == [1.0, 0.9, 0.8]


def test_preserva_os_demais_campos_sem_mutar_a_lista_da_fusao():
    candidatos = _candidatos(2)

    ordenados, _ = reordenar(PERGUNTA, candidatos, cliente=_cliente([1, 0]))

    assert ordenados[0].score_denso == 0.7
    assert candidatos[0].score_final == 0.5


def test_julga_contra_a_pergunta_e_o_texto_integral():
    capturadas: list[dict] = []

    reordenar(PERGUNTA, _candidatos(1), cliente=_cliente([0], capturadas))

    assert capturadas[0]["query"] == PERGUNTA
    assert capturadas[0]["texts"] == ["trecho 0"]


def test_lista_vazia_nao_chama_o_servico():
    capturadas: list[dict] = []

    ordenados, metrica = reordenar(PERGUNTA, [], cliente=_cliente([], capturadas))

    assert ordenados == []
    assert capturadas == []
    assert metrica.etapa is EtapaPipeline.RERANKING


def test_metrica_separa_a_inferencia_da_espera_na_fila():
    _, metrica = reordenar(PERGUNTA, _candidatos(2), cliente=_cliente([0, 1]))

    assert metrica.detalhes == {
        "candidatos": 2,
        "provedor": "tei",
        "inferencia_ms": 90,
        "fila_ms": 10,
    }
    assert metrica.modelo == get_settings().reranker_model


def test_falha_do_servico_sobe_em_vez_de_cair_para_a_ordem_da_busca():
    cliente = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(500)),
        base_url="http://reordenador.invalido",
    )

    with pytest.raises(httpx.HTTPStatusError):
        reordenar(PERGUNTA, _candidatos(2), cliente=cliente)
