import uuid

import pytest

from app.core.milvus import (
    CAMPO_CHUNK,
    CAMPO_DENSO,
    CAMPO_DOCUMENTO,
    CAMPO_ESPARSO,
    CAMPO_METADADOS,
    CAMPO_TEXTO,
)
from app.rag.chunking import Chunk
from app.rag.indexing import LOTE_DE_INSERCAO, indexar_chunks, remover_documento


class ClienteFalso:
    def __init__(self) -> None:
        self.insercoes: list[tuple[str, list[dict]]] = []
        self.flushes: list[str] = []
        self.remocoes: list[tuple[str, str]] = []

    def insert(self, collection_name: str, data: list[dict]) -> dict:
        self.insercoes.append((collection_name, data))
        return {"insert_count": len(data)}

    def flush(self, collection_name: str) -> None:
        self.flushes.append(collection_name)

    def delete(self, collection_name: str, filter: str) -> dict:  # noqa: A002
        self.remocoes.append((collection_name, filter))
        return {"delete_count": 1}


def _chunks(quantidade: int) -> list[Chunk]:
    return [Chunk(indice=numero, texto=f"trecho {numero}") for numero in range(quantidade)]


def _vetores(quantidade: int) -> list[list[float]]:
    return [[float(numero), 0.5] for numero in range(quantidade)]


def test_linhas_nunca_carregam_o_vetor_esparso():
    """A Function BM25 gera o esparso no servidor; envia-lo faz o Milvus rejeitar a insercao."""
    cliente = ClienteFalso()
    indexar_chunks(cliente, "evaluation1", uuid.uuid4(), _chunks(3), _vetores(3), {})
    linhas = cliente.insercoes[0][1]
    assert all(CAMPO_ESPARSO not in linha for linha in linhas)


def test_cada_linha_carrega_documento_indice_texto_vetor_e_metadados():
    cliente = ClienteFalso()
    documento = uuid.uuid4()
    indexar_chunks(
        cliente, "evaluation2", documento, _chunks(2), _vetores(2), {"parser": "docling"}
    )
    primeira = cliente.insercoes[0][1][0]
    assert primeira[CAMPO_DOCUMENTO] == str(documento)
    assert primeira[CAMPO_CHUNK] == 0
    assert primeira[CAMPO_TEXTO] == "trecho 0"
    assert primeira[CAMPO_DENSO] == [0.0, 0.5]
    assert primeira[CAMPO_METADADOS] == {"parser": "docling"}


def test_indexa_na_collection_pedida():
    cliente = ClienteFalso()
    indexar_chunks(cliente, "evaluation3", uuid.uuid4(), _chunks(1), _vetores(1), {})
    assert cliente.insercoes[0][0] == "evaluation3"


def test_devolve_a_quantidade_indexada_e_faz_flush():
    cliente = ClienteFalso()
    total = indexar_chunks(cliente, "evaluation1", uuid.uuid4(), _chunks(5), _vetores(5), {})
    assert total == 5
    assert cliente.flushes == ["evaluation1"]


def test_muitos_chunks_viram_varios_lotes():
    cliente = ClienteFalso()
    quantidade = LOTE_DE_INSERCAO + 7
    total = indexar_chunks(
        cliente, "evaluation1", uuid.uuid4(), _chunks(quantidade), _vetores(quantidade), {}
    )
    assert total == quantidade
    assert len(cliente.insercoes) == 2
    assert len(cliente.insercoes[0][1]) == LOTE_DE_INSERCAO
    assert len(cliente.insercoes[1][1]) == 7


def test_chunks_sem_vetor_correspondente_e_erro():
    with pytest.raises(ValueError, match="vetores"):
        indexar_chunks(ClienteFalso(), "evaluation1", uuid.uuid4(), _chunks(3), _vetores(2), {})


def test_sem_chunks_nao_toca_no_milvus():
    cliente = ClienteFalso()
    assert indexar_chunks(cliente, "evaluation1", uuid.uuid4(), [], [], {}) == 0
    assert cliente.insercoes == []
    assert cliente.flushes == []


def test_remocao_filtra_pelo_documento():
    cliente = ClienteFalso()
    documento = uuid.uuid4()
    remover_documento(cliente, "evaluation4", documento)
    assert cliente.remocoes == [("evaluation4", f'{CAMPO_DOCUMENTO} == "{documento}"')]


@pytest.mark.integration
def test_ida_e_volta_contra_o_milvus_de_verdade():
    from app.core.milvus import construir_cliente, criar_collections

    cliente = construir_cliente()
    criar_collections(cliente)
    documento = uuid.uuid4()
    try:
        total = indexar_chunks(
            cliente,
            "evaluation1",
            documento,
            _chunks(4),
            [[0.1] * 1536 for _ in range(4)],
            {"parser": "raw"},
        )
        assert total == 4
        encontrados = cliente.query(
            collection_name="evaluation1",
            filter=f'{CAMPO_DOCUMENTO} == "{documento}"',
            output_fields=[CAMPO_CHUNK],
        )
        assert len(encontrados) == 4
    finally:
        remover_documento(cliente, "evaluation1", documento)
