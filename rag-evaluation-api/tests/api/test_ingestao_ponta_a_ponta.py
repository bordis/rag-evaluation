"""Ingestao real: OpenAI, Milvus e docling-serve no ar. Fora da suite padrao."""

import time
import uuid

import pytest
from sqlmodel import Session, select

from app.core.db import engine
from app.core.milvus import CAMPO_DOCUMENTO, construir_cliente, criar_collections
from app.models.document import Document, DocumentIngestion, StatusDocumento, StatusIngestao
from app.models.pipeline import Pipeline
from app.rag.indexing import remover_documento
from app.seed import semear_pipelines
from app.services.ingestion import ingerir_documento

TEXTO = (
    "A Lei Geral de Protecao de Dados regula o tratamento de dados pessoais. "
    "Dado pessoal e toda informacao relacionada a pessoa natural identificada ou identificavel. "
) * 20


@pytest.mark.integration
def test_documento_txt_percorre_os_quatro_pipelines():
    cliente_milvus = construir_cliente()
    criar_collections(cliente_milvus)

    with Session(engine) as sessao:
        semear_pipelines(sessao)
        documento = Document(
            slug=f"teste-{uuid.uuid4().hex[:8]}",
            titulo="Documento de teste",
            area="Direito",
            descricao="Gerado pelo teste de integracao",
            icone="T",
            nome_arquivo_original="teste.txt",
            mime_type="text/plain",
            tamanho_bytes=len(TEXTO),
            sha256=uuid.uuid4().hex * 2,
        )
        sessao.add(documento)
        sessao.commit()
        sessao.refresh(documento)
        pipelines = sessao.exec(select(Pipeline).order_by(Pipeline.codigo)).all()
        for pipeline in pipelines:
            sessao.add(DocumentIngestion(document_id=documento.id, pipeline_id=pipeline.id))
        sessao.commit()

        try:
            inicio = time.perf_counter()
            ingerir_documento(sessao, documento.id, TEXTO.encode(), "text/plain", "teste.txt")
            duracao = time.perf_counter() - inicio

            sessao.refresh(documento)
            ingestoes = sessao.exec(
                select(DocumentIngestion).where(DocumentIngestion.document_id == documento.id)
            ).all()

            assert documento.status == StatusDocumento.PRONTO, [item.erro for item in ingestoes]
            assert len(ingestoes) == 4
            assert all(item.status == StatusIngestao.CONCLUIDA for item in ingestoes)
            assert all(item.total_chunks > 0 for item in ingestoes)
            assert all(item.tokens_embedding > 0 for item in ingestoes)
            print(f"Ingestao completa em {duracao:.1f}s")

            for pipeline in pipelines:
                encontrados = cliente_milvus.query(
                    collection_name=pipeline.collection_name,
                    filter=f'{CAMPO_DOCUMENTO} == "{documento.id}"',
                    output_fields=[CAMPO_DOCUMENTO],
                    # O Milvus e eventualmente consistente por padrao: sem "Strong", uma leitura
                    # logo apos a escrita pode ver o estado anterior e o teste vira loteria.
                    consistency_level="Strong",
                )
                assert encontrados, f"{pipeline.collection_name} ficou vazia"
        finally:
            for pipeline in pipelines:
                remover_documento(cliente_milvus, pipeline.collection_name, documento.id)
            sessao.delete(documento)
            sessao.commit()
