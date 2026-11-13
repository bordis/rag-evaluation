"""Extracao ingenua de texto: sem tabelas, sem titulos, sem ordem de leitura.

E o contraste honesto com o Docling. Melhorar este parser descaracterizaria o braco de controle.
"""

import io
import zipfile

from defusedxml.ElementTree import fromstring
from pypdf import PageObject, PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import NameObject

from app.rag.parsing.base import ErroDeParsing, ResultadoParsing

_NAMESPACE_WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_TAG_TEXTO_WORD = f"{_NAMESPACE_WORD}t"
_TAG_PARAGRAFO_WORD = f"{_NAMESPACE_WORD}p"

_MIME_PDF = "application/pdf"
_MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_MIMES_DE_TEXTO = ("text/plain", "text/markdown")


def _remover_nulos_fora_de_strings(dados: bytes) -> bytes:
    """Apaga os bytes nulos que ficam fora das strings literais de um content stream.

    O dompdf (export PDF do BookStack), ao justificar texto com fonte Unicode, grava \\x00 entre
    os itens do operador TJ, o que o pypdf rejeita. Dentro das strings o \\x00 e legitimo (codigos
    de dois bytes da fonte Identity-H) e e preservado. Repara o arquivo, nao melhora a extracao.
    """
    saida = bytearray()
    profundidade = 0
    indice = 0
    while indice < len(dados):
        byte = dados[indice]
        if profundidade:
            saida.append(byte)
            if byte == 0x5C and indice + 1 < len(dados):  # "\": o proximo byte e escapado
                saida.append(dados[indice + 1])
                indice += 2
                continue
            if byte == 0x28:  # "(" aninhado
                profundidade += 1
            elif byte == 0x29:  # ")"
                profundidade -= 1
        elif byte != 0x00:
            saida.append(byte)
            if byte == 0x28:
                profundidade = 1
        indice += 1
    return bytes(saida)


def _texto_da_pagina_reparada(pagina: PageObject) -> str:
    conteudo = pagina.get_contents()
    if conteudo is None:
        raise ErroDeParsing("Pagina sem content stream.")
    conteudo.set_data(_remover_nulos_fora_de_strings(conteudo.get_data()))
    pagina[NameObject("/Contents")] = conteudo
    return pagina.extract_text() or ""


def _texto_de_pdf(conteudo: bytes) -> tuple[str, int, list[int]]:
    """Devolve o texto, o total de paginas e as paginas (base 1) que precisaram de reparo."""
    paginas: list[str] = []
    reparadas: list[int] = []
    try:
        leitor = PdfReader(io.BytesIO(conteudo))
        for numero, pagina in enumerate(leitor.pages, start=1):
            try:
                paginas.append(pagina.extract_text() or "")
            except PdfReadError:
                # So o defeito de sintaxe do content stream tem reparo; se persistir, cai abaixo.
                paginas.append(_texto_da_pagina_reparada(pagina))
                reparadas.append(numero)
    except Exception as erro:  # noqa: BLE001 — qualquer falha do pypdf e falha de parsing
        raise ErroDeParsing(f"Nao foi possivel ler o PDF: {erro}") from erro
    texto = "\n".join(pagina for pagina in paginas if pagina.strip())
    return texto, len(paginas), reparadas


def _texto_de_docx(conteudo: bytes) -> str:
    """Le word/document.xml e concatena os nos de texto — sem estrutura, de proposito."""
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as arquivo:
            xml = arquivo.read("word/document.xml")
        raiz = fromstring(xml)
    except Exception as erro:  # noqa: BLE001
        raise ErroDeParsing(f"Nao foi possivel ler o DOCX: {erro}") from erro

    paragrafos = [
        "".join(no.text or "" for no in paragrafo.iter(_TAG_TEXTO_WORD))
        for paragrafo in raiz.iter(_TAG_PARAGRAFO_WORD)
    ]
    return "\n".join(paragrafo for paragrafo in paragrafos if paragrafo.strip())


def extrair_texto_raw(conteudo: bytes, mime_type: str, nome_arquivo: str) -> ResultadoParsing:
    metadados: dict = {"parser": "raw"}

    if mime_type == _MIME_PDF:
        texto, paginas, reparadas = _texto_de_pdf(conteudo)
        metadados["paginas"] = paginas
        if reparadas:
            # Rastreabilidade para o estudo: quais paginas so foram lidas depois do reparo.
            metadados["paginas_reparadas"] = reparadas
    elif mime_type in _MIMES_DE_TEXTO:
        # errors="replace" porque um byte invalido nao justifica perder o documento inteiro.
        texto = conteudo.decode("utf-8", errors="replace")
    elif mime_type == _MIME_DOCX:
        texto = _texto_de_docx(conteudo)
    else:
        raise ErroDeParsing(f"Tipo de arquivo nao suportado pelo parser raw: {mime_type}")

    if not texto.strip():
        raise ErroDeParsing(f"O parser raw nao produziu texto para {nome_arquivo}.")

    return ResultadoParsing(texto=texto.strip(), metadados=metadados)
