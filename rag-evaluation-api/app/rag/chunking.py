"""Divisao do texto em chunks. Identica nos 4 pipelines, de proposito.

Variar o chunking entre os bracos experimentais confundiria as variaveis do desenho fatorial:
uma diferenca de qualidade nao poderia mais ser atribuida ao parser nem ao retrieval.
"""

from dataclasses import dataclass

# O campo `text` das collections e VARCHAR(8192). Validar aqui transforma um erro obscuro de
# insercao no Milvus, no meio de uma ingestao em background, num ValueError na subida.
TAMANHO_MAXIMO_CHUNK = 8192


@dataclass(frozen=True)
class Chunk:
    indice: int
    texto: str


def _cortar_em_fronteira(texto: str, inicio: int, fim: int) -> int:
    """Recua o corte ate o ultimo espaco ou quebra de linha, sem passar da metade do chunk.

    Cortar no meio de uma palavra degrada tanto o embedding quanto o BM25. O piso na metade
    evita que um trecho sem espacos algum produza um chunk minusculo.
    """
    minimo = inicio + (fim - inicio) // 2
    corte = max(texto.rfind(" ", minimo, fim), texto.rfind("\n", minimo, fim))
    return corte if corte > minimo else fim


def dividir_em_chunks(texto: str, tamanho: int, sobreposicao: int) -> list[Chunk]:
    """Janela deslizante com sobreposicao, cortando em fronteira de palavra."""
    if sobreposicao >= tamanho:
        raise ValueError("A sobreposicao precisa ser menor que o tamanho do chunk.")
    if tamanho > TAMANHO_MAXIMO_CHUNK:
        raise ValueError(f"O tamanho excede o limite de {TAMANHO_MAXIMO_CHUNK} do Milvus.")

    limpo = texto.strip()
    if not limpo:
        return []

    chunks: list[Chunk] = []
    inicio = 0
    while inicio < len(limpo):
        fim = min(inicio + tamanho, len(limpo))
        if fim < len(limpo):
            fim = _cortar_em_fronteira(limpo, inicio, fim)

        trecho = limpo[inicio:fim].strip()
        if trecho:
            chunks.append(Chunk(indice=len(chunks), texto=trecho))

        if fim >= len(limpo):
            break
        # O max() garante progresso mesmo se a fronteira recuar muito.
        inicio = max(fim - sobreposicao, inicio + 1)

    return chunks
