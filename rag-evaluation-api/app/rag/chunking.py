"""Divisao do texto em chunks. Identica nos 4 pipelines, de proposito.

Variar o chunking entre os bracos experimentais confundiria as variaveis do desenho fatorial:
uma diferenca de qualidade nao poderia mais ser atribuida ao parser nem ao retrieval. Por isso os
segmentadores do Docling nao sao usados, mesmo reconhecendo elementos do documento.

O limite e em tokens e o corte acontece em fim de frase. Quebra de linha tambem conta como
fronteira: e o que separa as linhas de uma tabela em Markdown, que nao tem pontuacao.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

import tiktoken

# O campo `text` das collections e VARCHAR(8192). Validar aqui transforma um erro obscuro de
# insercao no Milvus, no meio de uma ingestao em background, num ValueError na subida.
TAMANHO_MAXIMO_CHUNK = 8192

# Encoding do text-embedding-3-small, o modelo que recebe estes chunks.
ENCODING = "cl100k_base"

_FRONTEIRA = re.compile(r"(?<=[.!?…])\s+|\n+")
_ULTIMA_PALAVRA = re.compile(r"(\S+)\.$")
_PALAVRA = re.compile(r"\S+\s*")

# Sem isto, "art. 5" e "Sr. Silva" virariam fim de frase.
_ABREVIACOES = frozenset(
    "art arts inc §§ sr sra srs sras dr dra drs dras prof profa n nº no nos pág págs pag p pp fl "
    "fls ex av dec res cf vol cap".split()
)


@dataclass(frozen=True)
class Chunk:
    indice: int
    texto: str


@lru_cache
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(ENCODING)


def contar_tokens(texto: str) -> int:
    return len(_encoding().encode(texto, disallowed_special=()))


def _e_abreviacao(trecho: str) -> bool:
    achado = _ULTIMA_PALAVRA.search(trecho)
    if achado is None:
        return False
    palavra = achado.group(1)
    # Inicial de nome ("J. Silva") e numeracao ("1. Objeto") tambem nao encerram frase.
    return palavra.lower() in _ABREVIACOES or len(palavra) == 1 or palavra.isdigit()


def dividir_em_frases(texto: str) -> list[str]:
    """Fatia o texto preservando os separadores: juntar as frases devolve o texto original."""
    frases: list[str] = []
    inicio = 0
    for fronteira in _FRONTEIRA.finditer(texto):
        if "\n" not in fronteira.group() and _e_abreviacao(texto[inicio : fronteira.start()]):
            continue
        frases.append(texto[inicio : fronteira.end()])
        inicio = fronteira.end()
    if inicio < len(texto):
        frases.append(texto[inicio:])
    return frases


def _partir_frase_longa(frase: str, tamanho: int, contar: Callable[[str], int]) -> list[str]:
    """Uma frase maior que o chunk (ou linha de tabela) e cortada entre palavras."""
    partes: list[str] = []
    atual = ""
    for palavra in _PALAVRA.findall(frase):
        if atual and contar(atual + palavra) > tamanho:
            partes.append(atual)
            atual = ""
        atual += palavra
    if atual:
        partes.append(atual)
    return partes


def dividir_em_chunks(
    texto: str,
    tamanho: int,
    sobreposicao: int,
    *,
    contar: Callable[[str], int] = contar_tokens,
) -> list[Chunk]:
    """Agrupa frases inteiras ate `tamanho` tokens. A sobreposicao repete frases inteiras."""
    if sobreposicao >= tamanho:
        raise ValueError("A sobreposicao precisa ser menor que o tamanho do chunk.")
    if tamanho > TAMANHO_MAXIMO_CHUNK:
        raise ValueError(f"O tamanho excede o limite de {TAMANHO_MAXIMO_CHUNK} do Milvus.")

    limpo = texto.strip()
    if not limpo:
        return []

    unidades: list[tuple[str, int]] = []
    for frase in dividir_em_frases(limpo):
        tokens = contar(frase)
        if tokens > tamanho:
            unidades.extend(
                (parte, contar(parte)) for parte in _partir_frase_longa(frase, tamanho, contar)
            )
        else:
            unidades.append((frase, tokens))

    chunks: list[Chunk] = []
    atual: list[tuple[str, int]] = []
    total = 0

    def fechar() -> None:
        trecho = "".join(frase for frase, _ in atual).strip()
        if trecho:
            chunks.append(Chunk(indice=len(chunks), texto=trecho))

    for unidade in unidades:
        if atual and total + unidade[1] > tamanho:
            fechar()
            repetidas: list[tuple[str, int]] = []
            acumulado = 0
            for anterior in reversed(atual):
                if acumulado + anterior[1] > sobreposicao:
                    break
                repetidas.insert(0, anterior)
                acumulado += anterior[1]
            # A soma dos tokens de frases pode diferir um pouco do total real; o limite vale aqui.
            if acumulado + unidade[1] > tamanho:
                repetidas, acumulado = [], 0
            atual, total = repetidas, acumulado
        atual.append(unidade)
        total += unidade[1]
    fechar()
    return chunks
