"""Gravacao dos chunks na collection do pipeline.

Cada pipeline tem collection propria porque o BM25 calcula IDF e comprimento medio sobre o corpus
da collection — uma collection compartilhada faria o score do pipeline 3 depender do que o
pipeline 4 ingeriu.
"""

import uuid

from app.core.milvus import (
    CAMPO_CHUNK,
    CAMPO_DENSO,
    CAMPO_DOCUMENTO,
    CAMPO_METADADOS,
    CAMPO_TEXTO,
)
from app.rag.chunking import Chunk

LOTE_DE_INSERCAO = 200


def indexar_chunks(
    cliente,
    collection_name: str,
    document_id: uuid.UUID,
    chunks: list[Chunk],
    vetores: list[list[float]],
    metadados: dict,
) -> int:
    """Insere os chunks e devolve quantos foram gravados.

    As linhas nao carregam `sparse_vector`: ele e derivado de `text` pela Function BM25 declarada
    na criacao da collection, e envia-lo faz o Milvus recusar a insercao.
    """
    if len(chunks) != len(vetores):
        raise ValueError(
            f"Quantidade de chunks ({len(chunks)}) difere da de vetores ({len(vetores)})."
        )
    if not chunks:
        return 0

    linhas = [
        {
            CAMPO_DOCUMENTO: str(document_id),
            CAMPO_CHUNK: chunk.indice,
            CAMPO_TEXTO: chunk.texto,
            CAMPO_DENSO: vetor,
            CAMPO_METADADOS: metadados,
        }
        for chunk, vetor in zip(chunks, vetores, strict=True)
    ]

    for inicio in range(0, len(linhas), LOTE_DE_INSERCAO):
        cliente.insert(
            collection_name=collection_name, data=linhas[inicio : inicio + LOTE_DE_INSERCAO]
        )

    # Flush para o documento ficar consultavel assim que o status vira `pronto`. Custa um
    # selamento de segmento por pipeline, aceitavel no volume do estudo.
    cliente.flush(collection_name)
    return len(linhas)


def remover_documento(cliente, collection_name: str, document_id: uuid.UUID) -> None:
    """Apaga todas as entidades de um documento. O id e UUID, entao interpolar e seguro."""
    cliente.delete(collection_name=collection_name, filter=f'{CAMPO_DOCUMENTO} == "{document_id}"')
