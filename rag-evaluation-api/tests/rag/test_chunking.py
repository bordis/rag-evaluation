import pytest

from app.rag.chunking import (
    TAMANHO_MAXIMO_CHUNK,
    contar_tokens,
    dividir_em_chunks,
    dividir_em_frases,
)


def contar_palavras(texto: str) -> int:
    return len(texto.split())


def test_texto_vazio_nao_gera_chunks():
    assert dividir_em_chunks("   \n  ", tamanho=256, sobreposicao=0) == []


def test_texto_curto_vira_um_chunk_unico():
    chunks = dividir_em_chunks("Lei Geral de Proteção de Dados.", tamanho=256, sobreposicao=0)

    assert [(item.indice, item.texto) for item in chunks] == [
        (0, "Lei Geral de Proteção de Dados.")
    ]


def test_frases_preservam_o_texto_original():
    texto = "Primeira frase. Segunda frase!\n| a | b |\n| 1 | 2 |\nTerceira?"

    assert "".join(dividir_em_frases(texto)) == texto


@pytest.mark.parametrize(
    "texto",
    [
        "Conforme o art. 5 da lei, vale a regra.",
        "O Sr. Silva e a Dra. Souza assinaram.",
        "Assinado por J. Silva na ocasião.",
        "1. Objeto do contrato firmado.",
    ],
)
def test_abreviacao_nao_encerra_frase(texto):
    assert dividir_em_frases(texto) == [texto]


def test_linhas_de_tabela_sao_fronteiras():
    assert dividir_em_frases("| a | b |\n| 1 | 2 |") == ["| a | b |\n", "| 1 | 2 |"]


def test_corta_entre_frases_sem_passar_do_limite():
    texto = "Um dois três quatro. Cinco seis sete. Oito nove dez onze."

    chunks = dividir_em_chunks(texto, tamanho=7, sobreposicao=0, contar=contar_palavras)

    assert [item.texto for item in chunks] == [
        "Um dois três quatro. Cinco seis sete.",
        "Oito nove dez onze.",
    ]


def test_frase_maior_que_o_limite_e_partida_entre_palavras():
    chunks = dividir_em_chunks("a b c d e", tamanho=2, sobreposicao=0, contar=contar_palavras)

    assert [item.texto for item in chunks] == ["a b", "c d", "e"]


def test_sobreposicao_repete_frases_inteiras():
    chunks = dividir_em_chunks(
        "Um dois. Três quatro. Cinco seis.", tamanho=4, sobreposicao=2, contar=contar_palavras
    )

    assert [item.texto for item in chunks] == ["Um dois. Três quatro.", "Três quatro. Cinco seis."]


def test_nenhum_chunk_real_passa_de_256_tokens():
    texto = " ".join(f"Esta é a frase número {numero} do documento." for numero in range(500))

    chunks = dividir_em_chunks(texto, tamanho=256, sobreposicao=0)

    assert len(chunks) > 1
    assert [item.indice for item in chunks] == list(range(len(chunks)))
    # A contagem de frases somadas e a do texto unido podem diferir por poucos tokens.
    assert all(contar_tokens(item.texto) <= 260 for item in chunks)
    assert all(item.texto.endswith(".") for item in chunks)


def test_sobreposicao_maior_que_o_tamanho_e_erro():
    with pytest.raises(ValueError):
        dividir_em_chunks("texto", tamanho=10, sobreposicao=10)


def test_tamanho_acima_do_limite_do_milvus_e_erro():
    with pytest.raises(ValueError):
        dividir_em_chunks("texto", tamanho=TAMANHO_MAXIMO_CHUNK + 1, sobreposicao=0)
