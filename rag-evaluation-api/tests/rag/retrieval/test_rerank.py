import json
from types import SimpleNamespace

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
        )
        for numero in range(quantidade)
    ]


class ClienteFalso:
    def __init__(self, texto: str) -> None:
        self.chamadas: list[dict] = []
        self.texto = texto
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **argumentos):
        self.chamadas.append(argumentos)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.texto))],
            usage=SimpleNamespace(prompt_tokens=400, completion_tokens=20, total_tokens=420),
            model="gpt-4.1-mini-2025-04-14",
        )


def _cliente_com_ordem(ordem: list[int]) -> ClienteFalso:
    return ClienteFalso(json.dumps({"ordem": ordem}))


def test_reordena_conforme_a_resposta_do_modelo():
    candidatos, _ = reordenar(
        PERGUNTA, _candidatos(4), manter=4, cliente=_cliente_com_ordem([3, 1, 4, 2])
    )
    assert [candidato.chunk_index for candidato in candidatos] == [2, 0, 3, 1]


def test_corta_na_quantidade_pedida():
    candidatos, _ = reordenar(
        PERGUNTA, _candidatos(6), manter=2, cliente=_cliente_com_ordem([5, 2, 1, 3, 4, 6])
    )
    assert [candidato.chunk_index for candidato in candidatos] == [4, 1]


def test_candidatos_nao_citados_pelo_modelo_vao_para_o_fim():
    """Nada pode sumir: um candidato omitido ainda e melhor que nenhum, se o corte alcancar."""
    candidatos, _ = reordenar(
        PERGUNTA, _candidatos(4), manter=4, cliente=_cliente_com_ordem([2, 1])
    )
    assert [candidato.chunk_index for candidato in candidatos] == [1, 0, 2, 3]


def test_indices_fora_da_faixa_sao_ignorados_sem_quebrar():
    candidatos, _ = reordenar(
        PERGUNTA, _candidatos(3), manter=3, cliente=_cliente_com_ordem([9, 2, 0, -1, 1])
    )
    assert [candidato.chunk_index for candidato in candidatos] == [1, 0, 2]


def test_indice_repetido_nao_duplica_o_candidato():
    candidatos, _ = reordenar(
        PERGUNTA, _candidatos(3), manter=3, cliente=_cliente_com_ordem([2, 2, 1])
    )
    assert [candidato.chunk_index for candidato in candidatos] == [1, 0, 2]


def test_json_invalido_mantem_a_ordem_original_e_marca_fallback():
    candidatos, metrica = reordenar(
        PERGUNTA, _candidatos(3), manter=2, cliente=ClienteFalso("nao sou json")
    )
    assert [candidato.chunk_index for candidato in candidatos] == [0, 1]
    assert metrica.detalhes["fallback"] is True


def test_json_sem_a_chave_ordem_marca_fallback():
    candidatos, metrica = reordenar(
        PERGUNTA, _candidatos(3), manter=3, cliente=ClienteFalso('{"resultado": [1]}')
    )
    assert [candidato.chunk_index for candidato in candidatos] == [0, 1, 2]
    assert metrica.detalhes["fallback"] is True


def test_lista_vazia_nao_chama_o_modelo():
    cliente = _cliente_com_ordem([1])
    candidatos, metrica = reordenar(PERGUNTA, [], manter=5, cliente=cliente)
    assert candidatos == []
    assert cliente.chamadas == []
    assert metrica.tokens_total is None


def test_metrica_registra_quantos_entraram_e_quantos_sairam():
    _, metrica = reordenar(
        PERGUNTA, _candidatos(6), manter=2, cliente=_cliente_com_ordem([1, 2, 3, 4, 5, 6])
    )
    assert metrica.etapa is EtapaPipeline.RERANKING
    assert metrica.detalhes["candidatos"] == 6
    assert metrica.detalhes["mantidos"] == 2
    assert metrica.detalhes["fallback"] is False
    assert metrica.tokens_total == 420


def test_pede_json_ao_modelo():
    cliente = _cliente_com_ordem([1])
    reordenar(PERGUNTA, _candidatos(1), manter=1, cliente=cliente)
    assert cliente.chamadas[0]["response_format"] == {"type": "json_object"}


def test_trechos_longos_sao_truncados_no_prompt():
    """O re-rank ve ate 20 candidatos; sem truncar, o prompt explodiria em tokens."""
    from app.rag.retrieval.rerank import TAMANHO_MAXIMO_DO_TRECHO

    longo = [Candidato(milvus_id=1, chunk_index=0, texto="x" * 5000)]
    cliente = _cliente_com_ordem([1])
    reordenar(PERGUNTA, longo, manter=1, cliente=cliente)
    conteudo = cliente.chamadas[0]["messages"][-1]["content"]
    assert "x" * (TAMANHO_MAXIMO_DO_TRECHO + 1) not in conteudo
