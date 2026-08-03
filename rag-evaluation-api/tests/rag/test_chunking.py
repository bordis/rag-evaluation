import pytest

from app.rag.chunking import TAMANHO_MAXIMO_CHUNK, dividir_em_chunks

# Palavras distintas para que "este trecho aparece no anterior" seja uma afirmacao real,
# e nao um acidente de texto repetido.
TEXTO_LONGO = " ".join(f"palavra{numero}" for numero in range(400))


def test_texto_vazio_nao_gera_chunks():
    assert dividir_em_chunks("   \n  ", tamanho=800, sobreposicao=150) == []


def test_texto_menor_que_o_tamanho_vira_um_chunk_unico():
    chunks = dividir_em_chunks("Lei Geral de Protecao de Dados", tamanho=800, sobreposicao=150)
    assert len(chunks) == 1
    assert chunks[0].indice == 0
    assert chunks[0].texto == "Lei Geral de Protecao de Dados"


def test_indices_sao_sequenciais_a_partir_de_zero():
    chunks = dividir_em_chunks(TEXTO_LONGO, tamanho=800, sobreposicao=150)
    assert [chunk.indice for chunk in chunks] == list(range(len(chunks)))


def test_nenhum_chunk_excede_o_tamanho_pedido():
    chunks = dividir_em_chunks(TEXTO_LONGO, tamanho=800, sobreposicao=150)
    assert chunks
    assert all(len(chunk.texto) <= 800 for chunk in chunks)


def test_chunks_consecutivos_se_sobrepoem():
    chunks = dividir_em_chunks(TEXTO_LONGO, tamanho=800, sobreposicao=150)
    assert len(chunks) > 1
    # strict=False explicito (B905): `chunks[1:]` e propositalmente um item mais curto.
    for anterior, seguinte in zip(chunks, chunks[1:], strict=False):
        assert seguinte.texto[:80] in anterior.texto


def test_o_texto_e_coberto_ate_o_fim():
    chunks = dividir_em_chunks(TEXTO_LONGO, tamanho=800, sobreposicao=150)
    assert chunks[-1].texto.endswith("palavra399")


def test_nao_corta_palavras_no_meio():
    chunks = dividir_em_chunks(TEXTO_LONGO, tamanho=800, sobreposicao=150)
    for chunk in chunks[:-1]:
        assert chunk.texto.split()[-1] in TEXTO_LONGO.split()


def test_sobreposicao_maior_ou_igual_ao_tamanho_e_erro():
    with pytest.raises(ValueError, match="sobreposicao"):
        dividir_em_chunks(TEXTO_LONGO, tamanho=200, sobreposicao=200)


def test_tamanho_acima_do_limite_do_milvus_e_erro():
    with pytest.raises(ValueError, match="Milvus"):
        dividir_em_chunks(TEXTO_LONGO, tamanho=TAMANHO_MAXIMO_CHUNK + 1, sobreposicao=150)
