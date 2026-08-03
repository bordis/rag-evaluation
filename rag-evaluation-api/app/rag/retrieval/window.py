"""Expansao de contexto na consulta: recupera o chunk e seus vizinhos por `chunk_index`.

Nao e sobreposicao de chunking. A decisao de tratar "sliding window" como etapa de consulta
(e nao de ingestao) e o que permite liga-la e desliga-la sem reingerir o acervo.
"""

import uuid

from app.core.milvus import CAMPO_CHUNK, CAMPO_DOCUMENTO, CAMPO_TEXTO
from app.models.telemetry import EtapaPipeline
from app.rag.retrieval.base import Candidato, MetricaEtapa
from app.telemetry.recorder import Cronometro


def _metrica(duracao_ms: int, tamanho: int, ancoras: int, vizinhos: int, total: int):
    return MetricaEtapa(
        etapa=EtapaPipeline.WINDOW_EXPANSION,
        duracao_ms=duracao_ms,
        detalhes={
            "tamanho": tamanho,
            "ancoras": ancoras,
            "vizinhos": vizinhos,
            "total": total,
        },
    )


def expandir_janela(
    cliente,
    collection_name: str,
    document_id: uuid.UUID,
    candidatos: list[Candidato],
    *,
    tamanho: int,
) -> tuple[list[Candidato], MetricaEtapa]:
    if tamanho <= 0 or not candidatos:
        return candidatos, _metrica(0, tamanho, len(candidatos), 0, len(candidatos))

    presentes = {candidato.chunk_index for candidato in candidatos}
    desejados = {
        indice
        for candidato in candidatos
        for indice in range(candidato.chunk_index - tamanho, candidato.chunk_index + tamanho + 1)
        if indice >= 0
    }
    faltantes = sorted(desejados - presentes)

    with Cronometro() as relogio:
        if faltantes:
            # Uma consulta so: uma por candidato multiplicaria a latencia do pipeline por top_k.
            linhas = cliente.query(
                collection_name=collection_name,
                filter=f'{CAMPO_DOCUMENTO} == "{document_id}" and {CAMPO_CHUNK} in {faltantes}',
                output_fields=[CAMPO_CHUNK, CAMPO_TEXTO],
            )
        else:
            linhas = []

    vizinhos_por_indice = {
        int(linha[CAMPO_CHUNK]): Candidato(
            milvus_id=int(linha["id"]),
            chunk_index=int(linha[CAMPO_CHUNK]),
            texto=linha[CAMPO_TEXTO],
            vizinho=True,
        )
        for linha in linhas
    }

    # Monta em ordem de leitura ao redor de cada ancora, na ordem de relevancia das ancoras.
    ancoras_por_indice = {candidato.chunk_index: candidato for candidato in candidatos}
    resultado: list[Candidato] = []
    emitidos: set[int] = set()
    for candidato in candidatos:
        for indice in range(candidato.chunk_index - tamanho, candidato.chunk_index + tamanho + 1):
            if indice in emitidos:
                continue
            proximo = ancoras_por_indice.get(indice)
            if proximo is None:
                proximo = vizinhos_por_indice.get(indice)
            if proximo is None:
                continue
            if proximo.vizinho:
                proximo.score_final = candidato.score_final
            resultado.append(proximo)
            emitidos.add(indice)

    quantidade_de_vizinhos = sum(1 for candidato in resultado if candidato.vizinho)
    return resultado, _metrica(
        relogio.ms, tamanho, len(candidatos), quantidade_de_vizinhos, len(resultado)
    )
