"""Extracao ingenua de texto: sem tabelas, sem titulos, sem ordem de leitura.

E o contraste honesto com o Docling. Melhorar este parser descaracterizaria o braco de controle.
"""

import io
import zipfile

from defusedxml.ElementTree import fromstring
from pypdf import PdfReader

from app.rag.parsing.base import ErroDeParsing, ResultadoParsing

_NAMESPACE_WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_TAG_TEXTO_WORD = f"{_NAMESPACE_WORD}t"
_TAG_PARAGRAFO_WORD = f"{_NAMESPACE_WORD}p"

_MIME_PDF = "application/pdf"
_MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_MIMES_DE_TEXTO = ("text/plain", "text/markdown")


def _texto_de_pdf(conteudo: bytes) -> tuple[str, int]:
    try:
        leitor = PdfReader(io.BytesIO(conteudo))
        paginas = [pagina.extract_text() or "" for pagina in leitor.pages]
    except Exception as erro:  # noqa: BLE001 — qualquer falha do pypdf e falha de parsing
        raise ErroDeParsing(f"Nao foi possivel ler o PDF: {erro}") from erro
    return "\n".join(pagina for pagina in paginas if pagina.strip()), len(paginas)


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
        texto, paginas = _texto_de_pdf(conteudo)
        metadados["paginas"] = paginas
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
