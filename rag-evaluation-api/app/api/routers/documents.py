"""Gestao do acervo. Uso exclusivo do pesquisador, pelo Swagger — nao ha UI de administracao."""

import hashlib
import pathlib
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile, status
from sqlmodel import select

from app.core.config import get_settings
from app.core.db import SessionDep
from app.core.milvus import construir_cliente
from app.models.document import Document, DocumentIngestion, StatusDocumento
from app.models.pipeline import Pipeline
from app.rag.indexing import remover_documento
from app.rag.parsing.base import EXTENSOES_SUPORTADAS, MIMES_SUPORTADOS
from app.schemas.document import (
    DocumentoAceito,
    DocumentoDetalhe,
    DocumentoResumo,
    IngestaoResumo,
)
from app.services.ingestion import executar_ingestao

router = APIRouter(prefix="/api/documents", tags=["documentos"])

SlugForm = Annotated[str, Form(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")]


def _resolver_mime(arquivo: UploadFile) -> str:
    """O Swagger manda `application/octet-stream` para .md; a extensao desempata."""
    if arquivo.content_type in MIMES_SUPORTADOS:
        return arquivo.content_type
    extensao = pathlib.PurePath(arquivo.filename or "").suffix.lower()
    mime = EXTENSOES_SUPORTADAS.get(extensao)
    if mime is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Tipo não suportado. Aceitos: {', '.join(sorted(MIMES_SUPORTADOS))}.",
        )
    return mime


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def enviar_documento(
    sessao: SessionDep,
    tarefas: BackgroundTasks,
    arquivo: Annotated[UploadFile, File()],
    slug: SlugForm,
    titulo: Annotated[str, Form(min_length=2, max_length=200)],
    area: Annotated[str, Form(min_length=2, max_length=120)],
    descricao: Annotated[str, Form(max_length=1000)] = "",
    icone: Annotated[str, Form(max_length=16)] = "",
) -> DocumentoAceito:
    """Aceita o arquivo e agenda a ingestao nos 4 pipelines. O arquivo nao e guardado."""
    mime_type = _resolver_mime(arquivo)
    limite = get_settings().max_upload_mb * 1024 * 1024
    conteudo = arquivo.file.read()
    if len(conteudo) > limite:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"O arquivo excede o limite de {get_settings().max_upload_mb} MB.",
        )

    if sessao.exec(select(Document).where(Document.slug == slug)).first() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"Já existe documento com slug '{slug}'."
        )

    sha256 = hashlib.sha256(conteudo).hexdigest()
    existente = sessao.exec(select(Document).where(Document.sha256 == sha256)).first()
    if existente is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Este arquivo já foi enviado como '{existente.slug}'.",
        )

    documento = Document(
        slug=slug,
        titulo=titulo,
        area=area,
        descricao=descricao,
        icone=icone,
        nome_arquivo_original=arquivo.filename or slug,
        mime_type=mime_type,
        tamanho_bytes=len(conteudo),
        sha256=sha256,
    )
    sessao.add(documento)
    sessao.commit()
    sessao.refresh(documento)

    # As 4 linhas nascem pendentes para o endpoint de telemetria ja mostrar o quadro completo.
    for pipeline in sessao.exec(select(Pipeline).order_by(Pipeline.codigo)).all():
        sessao.add(DocumentIngestion(document_id=documento.id, pipeline_id=pipeline.id))
    sessao.commit()

    tarefas.add_task(
        executar_ingestao, documento.id, conteudo, mime_type, documento.nome_arquivo_original
    )
    return DocumentoAceito(
        id=documento.id,
        slug=documento.slug,
        status=documento.status,
        mensagem="Documento aceito. A ingestão nos 4 pipelines roda em segundo plano.",
    )


@router.get("")
def listar_documentos(
    sessao: SessionDep,
    status_documento: Annotated[StatusDocumento | None, Query(alias="status")] = None,
) -> list[DocumentoResumo]:
    """Sem filtro devolve tudo; o frontend chama sempre com `status=pronto`."""
    consulta = select(Document).order_by(Document.criado_em)
    if status_documento is not None:
        consulta = consulta.where(Document.status == status_documento)
    return [
        DocumentoResumo.model_validate(item, from_attributes=True)
        for item in sessao.exec(consulta).all()
    ]


@router.get("/{documento_id}")
def obter_documento(sessao: SessionDep, documento_id: uuid.UUID) -> DocumentoDetalhe:
    documento = sessao.get(Document, documento_id)
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Documento não encontrado.")
    return DocumentoDetalhe.model_validate(documento, from_attributes=True)


@router.get("/{documento_id}/ingestions")
def listar_ingestoes(sessao: SessionDep, documento_id: uuid.UUID) -> list[IngestaoResumo]:
    """Telemetria por pipeline. Endpoint do pesquisador — o frontend nunca o chama."""
    if sessao.get(Document, documento_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Documento não encontrado.")

    linhas = sessao.exec(
        select(DocumentIngestion, Pipeline)
        .join(Pipeline, Pipeline.id == DocumentIngestion.pipeline_id)  # type: ignore[arg-type]
        .where(DocumentIngestion.document_id == documento_id)
        .order_by(Pipeline.codigo)  # type: ignore[arg-type]
    ).all()
    return [
        IngestaoResumo(
            pipeline_codigo=pipeline.codigo,
            pipeline_nome=pipeline.nome,
            status=ingestao.status,
            erro=ingestao.erro,
            total_caracteres=ingestao.total_caracteres,
            total_chunks=ingestao.total_chunks,
            tokens_embedding=ingestao.tokens_embedding,
            duracao_parsing_ms=ingestao.duracao_parsing_ms,
            duracao_chunking_ms=ingestao.duracao_chunking_ms,
            duracao_embedding_ms=ingestao.duracao_embedding_ms,
            duracao_indexacao_ms=ingestao.duracao_indexacao_ms,
            duracao_total_ms=ingestao.duracao_total_ms,
            iniciado_em=ingestao.iniciado_em,
            concluido_em=ingestao.concluido_em,
        )
        for ingestao, pipeline in linhas
    ]


@router.delete("/{documento_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_documento(sessao: SessionDep, documento_id: uuid.UUID) -> None:
    documento = sessao.get(Document, documento_id)
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Documento não encontrado.")

    # Milvus primeiro: se ele falhar, a linha continua no Postgres e a exclusao pode ser
    # repetida. Na ordem inversa, os vetores ficariam orfaos sem ninguem para apaga-los.
    cliente = construir_cliente()
    for pipeline in sessao.exec(select(Pipeline).order_by(Pipeline.codigo)).all():
        try:
            remover_documento(cliente, pipeline.collection_name, documento_id)
        except Exception as erro:  # noqa: BLE001
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail=f"Falha ao remover do Milvus ({pipeline.collection_name}): {erro}",
            ) from erro

    sessao.delete(documento)
    sessao.commit()
