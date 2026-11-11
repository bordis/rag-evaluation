"""PDFs do acervo no MinIO. O navegador nunca fala com o MinIO: recebe o arquivo pela API."""

import io
import uuid
from urllib.parse import urlsplit

from minio import Minio
from minio.error import S3Error
from urllib3 import BaseHTTPResponse

from app.core.config import get_settings

_MIME_PDF = "application/pdf"


class ArquivoAusente(Exception):
    """A chave registrada no banco nao tem objeto correspondente no bucket."""


def _cliente() -> Minio:
    settings = get_settings()
    # O cliente recebe host e TLS separados; o .env guarda uma URL, como DOCLING_URL e RERANKER_URL.
    url = urlsplit(settings.minio_url)
    return Minio(
        url.netloc,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=url.scheme == "https",
    )


def guardar_pdf(document_id: uuid.UUID, conteudo: bytes) -> str:
    """Grava o PDF e devolve a chave. O bucket nasce aqui: a API sobe mesmo com o MinIO fora."""
    cliente = _cliente()
    bucket = get_settings().minio_bucket_documentos
    if not cliente.bucket_exists(bucket_name=bucket):
        cliente.make_bucket(bucket_name=bucket)
    chave = f"{document_id}.pdf"
    cliente.put_object(
        bucket_name=bucket,
        object_name=chave,
        data=io.BytesIO(conteudo),
        length=len(conteudo),
        content_type=_MIME_PDF,
    )
    return chave


def abrir_pdf(chave: str) -> BaseHTTPResponse:
    """Devolve a resposta aberta do MinIO; quem chama deve fecha-la."""
    try:
        return _cliente().get_object(
            bucket_name=get_settings().minio_bucket_documentos, object_name=chave
        )
    except S3Error as erro:
        if erro.code == "NoSuchKey":
            raise ArquivoAusente(chave) from erro
        raise


def remover_pdf(chave: str) -> None:
    """Remover um objeto que nao existe nao e erro, entao a exclusao pode ser repetida."""
    _cliente().remove_object(bucket_name=get_settings().minio_bucket_documentos, object_name=chave)
