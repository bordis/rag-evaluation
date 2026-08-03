"""Parsing estruturado via docling-serve.

O Docling devolve Markdown com titulos e tabelas preservados. Comparar este parser com o raw
(pipelines 1<->2 e 3<->4) e uma das duas medidas do estudo.
"""

import httpx

from app.core.config import get_settings
from app.rag.parsing.base import ErroDeParsing, ResultadoParsing

CAMINHO_CONVERSAO = "/v1/convert/file"
STATUS_ACEITOS = ("success", "partial_success")


def extrair_texto_docling(
    conteudo: bytes,
    mime_type: str,
    nome_arquivo: str,
    *,
    cliente: httpx.Client | None = None,
) -> ResultadoParsing:
    settings = get_settings()
    proprio = cliente is None
    if cliente is None:
        cliente = httpx.Client(
            base_url=settings.docling_url, timeout=settings.docling_timeout_seconds
        )

    try:
        resposta = cliente.post(
            CAMINHO_CONVERSAO,
            files={"files": (nome_arquivo, conteudo, mime_type)},
            data={
                "to_formats": ["md"],
                "do_ocr": str(settings.docling_do_ocr).lower(),
                "abort_on_error": "false",
                "table_mode": "accurate",
                "image_export_mode": "placeholder",
            },
        )
    except httpx.HTTPError as erro:
        raise ErroDeParsing(f"Falha ao falar com o docling-serve: {erro}") from erro
    finally:
        if proprio:
            cliente.close()

    if resposta.status_code != httpx.codes.OK:
        raise ErroDeParsing(
            f"docling-serve respondeu {resposta.status_code}: {resposta.text[:300]}"
        )

    corpo = resposta.json()
    status = corpo.get("status", "failure")
    if status not in STATUS_ACEITOS:
        raise ErroDeParsing(f"docling-serve falhou ({status}): {corpo.get('errors')}")

    texto = (corpo.get("document") or {}).get("md_content") or ""
    if not texto.strip():
        raise ErroDeParsing(f"O Docling nao produziu texto para {nome_arquivo}.")

    return ResultadoParsing(texto=texto.strip(), metadados={"parser": "docling", "status": status})
