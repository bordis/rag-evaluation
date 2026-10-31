"""Parsing estruturado via docling-serve.

O Docling devolve Markdown com titulos e tabelas preservados e, com o VLM ligado, uma descricao de
cada imagem. Comparar este parser com o raw (pipelines 1<->2 e 3<->4) e uma das duas medidas do
estudo.

Usa os endpoints assincronos: o sincrono tem limite de espera curto no servidor, e descrever imagens
leva minutos em um PDF grande.
"""

import json
import time

import httpx

from app.core.config import get_settings
from app.rag.parsing.base import ErroDeParsing, ResultadoParsing

CAMINHO_CONVERSAO = "/v1/convert/file/async"
STATUS_ACEITOS = ("success", "partial_success")
INTERVALO_POLL_SEGUNDOS = 3
URL_DESCRICAO_IMAGENS = "https://api.openai.com/v1/chat/completions"
PROMPT_DESCRICAO_IMAGENS = (
    "Descreva esta imagem em português e até 2 frases, destacando os elementos visuais mais "
    "relevantes. Seja objetivo e conciso."
)


def _opcoes() -> dict:
    settings = get_settings()
    opcoes = {
        "to_formats": ["md", "json"],
        "do_ocr": str(settings.docling_do_ocr).lower(),
        "pdf_backend": settings.docling_pdf_backend,
        "table_mode": settings.docling_table_mode,
        "abort_on_error": "false",
        "image_export_mode": "placeholder",
        "do_picture_description": str(settings.docling_descrever_imagens).lower(),
    }
    if settings.docling_descrever_imagens:
        opcoes["picture_description_area_threshold"] = str(settings.docling_imagem_area_minima)
        opcoes["picture_description_api"] = json.dumps(
            {
                "url": URL_DESCRICAO_IMAGENS,
                "headers": {"Authorization": f"Bearer {settings.chat_api_key}"},
                "params": {"model": settings.docling_imagem_modelo},
                "prompt": PROMPT_DESCRICAO_IMAGENS,
                "timeout": 60,
            }
        )
    return opcoes


def _imagens_sem_descricao(estrutura: dict) -> list[str]:
    """Imagens acima do limiar de area que voltaram sem descricao.

    O Docling so registra a falha do VLM no log e responde `success`. Aceitar isso faria parte do
    acervo chegar sem as descricoes, sem rastro, e mudaria o que o fator A entrega.
    """
    limiar = get_settings().docling_imagem_area_minima
    paginas = estrutura.get("pages") or {}
    ausentes: list[str] = []
    for imagem in estrutura.get("pictures") or []:
        if any(item.get("text") for item in imagem.get("annotations") or []):
            continue
        for origem in imagem.get("prov") or []:
            caixa = origem.get("bbox") or {}
            tamanho = (paginas.get(str(origem.get("page_no"))) or {}).get("size") or {}
            area_pagina = tamanho.get("width", 0) * tamanho.get("height", 0)
            area = abs(caixa.get("r", 0) - caixa.get("l", 0)) * abs(
                caixa.get("t", 0) - caixa.get("b", 0)
            )
            if area_pagina and area / area_pagina > limiar:
                ausentes.append(imagem.get("self_ref", "?"))
                break
    return ausentes


def _aguardar_resultado(cliente: httpx.Client, tarefa: str, *, intervalo: float) -> dict:
    limite = time.monotonic() + get_settings().docling_timeout_seconds
    while time.monotonic() < limite:
        status = cliente.get(f"/v1/status/poll/{tarefa}").raise_for_status().json()["task_status"]
        if status == "success":
            return cliente.get(f"/v1/result/{tarefa}").raise_for_status().json()
        if status in ("failure", "revoked"):
            raise ErroDeParsing(f"A tarefa do docling-serve terminou com status {status}.")
        time.sleep(intervalo)
    raise ErroDeParsing("O docling-serve não terminou a conversão dentro do limite de tempo.")


def extrair_texto_docling(
    conteudo: bytes,
    mime_type: str,
    nome_arquivo: str,
    *,
    cliente: httpx.Client | None = None,
    intervalo: float = INTERVALO_POLL_SEGUNDOS,
) -> ResultadoParsing:
    settings = get_settings()
    proprio = cliente is None
    if cliente is None:
        cliente = httpx.Client(base_url=settings.docling_url, timeout=120)

    try:
        resposta = cliente.post(
            CAMINHO_CONVERSAO,
            files={"files": (nome_arquivo, conteudo, mime_type)},
            data=_opcoes(),
        )
        if resposta.status_code != httpx.codes.OK:
            raise ErroDeParsing(
                f"docling-serve respondeu {resposta.status_code}: {resposta.text[:300]}"
            )
        corpo = _aguardar_resultado(cliente, resposta.json()["task_id"], intervalo=intervalo)
    except httpx.HTTPError as erro:
        raise ErroDeParsing(f"Falha ao falar com o docling-serve: {erro}") from erro
    finally:
        if proprio:
            cliente.close()

    status = corpo.get("status", "failure")
    if status not in STATUS_ACEITOS:
        raise ErroDeParsing(f"docling-serve falhou ({status}): {corpo.get('errors')}")

    documento = corpo.get("document") or {}
    texto = documento.get("md_content") or ""
    if not texto.strip():
        raise ErroDeParsing(f"O Docling nao produziu texto para {nome_arquivo}.")

    estrutura = documento.get("json_content") or {}
    if settings.docling_descrever_imagens:
        ausentes = _imagens_sem_descricao(estrutura)
        if ausentes:
            raise ErroDeParsing(
                f"O VLM não descreveu {len(ausentes)} imagens ({', '.join(ausentes)}). "
                "Veja os logs do container rag-docling; com antivírus, confira DOCLING_CA_BUNDLE."
            )
    return ResultadoParsing(
        texto=texto.strip(),
        metadados={
            "parser": "docling",
            "status": status,
            "paginas": len(estrutura.get("pages") or {}),
            "tabelas": len(estrutura.get("tables") or []),
            "imagens": len(estrutura.get("pictures") or []),
        },
    )
