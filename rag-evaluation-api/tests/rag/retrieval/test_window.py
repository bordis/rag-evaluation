import re
import uuid

from app.core.milvus import CAMPO_CHUNK, CAMPO_TEXTO
from app.models.telemetry import EtapaPipeline
from app.rag.retrieval.base import Candidato
from app.rag.retrieval.window import expandir_janela

DOCUMENTO = uuid.uuid4()


class ClienteFalso:
    """Simula uma collection com os chunks de `disponiveis`, devolvendo so os que o filtro pede."""

    def __init__(self, disponiveis: range = range(10)) -> None:
        self.consultas: list[dict] = []
        self.disponiveis = disponiveis

    def query(self, **argumentos):
        self.consultas.append(argumentos)
        # O filtro termina em `chunk_index in [3, 6]`; o split isola a lista do UUID do documento.
        lista = argumentos["filter"].split(" in ")[-1]
        pedidos = {int(numero) for numero in re.findall(r"-?\d+", lista)}
        return [
            {"id": 1000 + indice, CAMPO_CHUNK: indice, CAMPO_TEXTO: f"trecho {indice}"}
            for indice in sorted(pedidos.intersection(self.disponiveis))
        ]


def _candidato(indice: int, score: float = 0.8) -> Candidato:
    return Candidato(
        milvus_id=1000 + indice, chunk_index=indice, texto=f"trecho {indice}", score_final=score
    )


def test_tamanho_zero_nao_toca_no_milvus():
    cliente = ClienteFalso()
    candidatos, metrica = expandir_janela(
        cliente, "evaluation3", DOCUMENTO, [_candidato(5)], tamanho=0
    )
    assert [candidato.chunk_index for candidato in candidatos] == [5]
    assert cliente.consultas == []
    assert metrica.detalhes["vizinhos"] == 0


def test_lista_vazia_nao_toca_no_milvus():
    cliente = ClienteFalso()
    candidatos, _ = expandir_janela(cliente, "evaluation3", DOCUMENTO, [], tamanho=1)
    assert candidatos == []
    assert cliente.consultas == []


def test_vizinhos_entram_ao_redor_da_ancora_em_ordem_de_leitura():
    cliente = ClienteFalso()
    candidatos, _ = expandir_janela(cliente, "evaluation3", DOCUMENTO, [_candidato(5)], tamanho=1)
    assert [candidato.chunk_index for candidato in candidatos] == [4, 5, 6]


def test_vizinhos_sao_marcados_e_herdam_o_score_da_ancora():
    cliente = ClienteFalso()
    candidatos, _ = expandir_janela(
        cliente, "evaluation3", DOCUMENTO, [_candidato(5, score=0.77)], tamanho=1
    )
    por_indice = {candidato.chunk_index: candidato for candidato in candidatos}
    assert por_indice[5].vizinho is False
    assert por_indice[4].vizinho is True
    assert por_indice[6].vizinho is True
    assert por_indice[4].score_final == 0.77


def test_so_consulta_os_indices_que_faltam():
    """Os chunks 4 e 5 ja vieram da busca; so o 3 e o 6 precisam ser buscados."""
    cliente = ClienteFalso()
    expandir_janela(cliente, "evaluation3", DOCUMENTO, [_candidato(4), _candidato(5)], tamanho=1)
    filtro = cliente.consultas[0]["filter"]
    assert "3" in filtro and "6" in filtro
    assert str(DOCUMENTO) in filtro


def test_nao_duplica_chunk_que_ja_estava_na_lista():
    cliente = ClienteFalso()
    candidatos, _ = expandir_janela(
        cliente, "evaluation3", DOCUMENTO, [_candidato(4), _candidato(5)], tamanho=1
    )
    indices = [candidato.chunk_index for candidato in candidatos]
    assert indices == sorted(set(indices))
    assert indices == [3, 4, 5, 6]


def test_nao_pede_indice_negativo_ao_milvus():
    """Chunk 0 nao tem vizinho anterior; pedir -1 e -2 sujaria o filtro sem ganho nenhum."""
    cliente = ClienteFalso()
    candidatos, _ = expandir_janela(cliente, "evaluation3", DOCUMENTO, [_candidato(0)], tamanho=2)
    assert "-1" not in cliente.consultas[0]["filter"]
    assert [candidato.chunk_index for candidato in candidatos] == [0, 1, 2]


def test_vizinho_inexistente_no_fim_do_documento_e_ignorado():
    cliente = ClienteFalso(disponiveis=range(3))
    candidatos, metrica = expandir_janela(
        cliente, "evaluation3", DOCUMENTO, [_candidato(2)], tamanho=1
    )
    assert [candidato.chunk_index for candidato in candidatos] == [1, 2]
    assert metrica.detalhes["vizinhos"] == 1


def test_uma_unica_consulta_para_todos_os_vizinhos():
    """Uma consulta por candidato multiplicaria a latencia do pipeline por top_k."""
    cliente = ClienteFalso()
    expandir_janela(
        cliente,
        "evaluation3",
        DOCUMENTO,
        [_candidato(1), _candidato(5), _candidato(8)],
        tamanho=1,
    )
    assert len(cliente.consultas) == 1


def test_metrica_registra_a_expansao():
    cliente = ClienteFalso()
    _, metrica = expandir_janela(cliente, "evaluation3", DOCUMENTO, [_candidato(5)], tamanho=1)
    assert metrica.etapa is EtapaPipeline.WINDOW_EXPANSION
    assert metrica.detalhes == {"tamanho": 1, "ancoras": 1, "vizinhos": 2, "total": 3}
    assert metrica.tokens_total is None
