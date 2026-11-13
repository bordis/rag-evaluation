import io
import zipfile
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.rag.parsing.base import MIMES_SUPORTADOS, ErroDeParsing
from app.rag.parsing.raw import extrair_texto_raw

NAMESPACE_WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx(paragrafos: list[str]) -> bytes:
    """Monta um .docx minimo de verdade: zip com word/document.xml."""
    corpo = "".join(f"<w:p><w:r><w:t>{texto}</w:t></w:r></w:p>" for texto in paragrafos)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{NAMESPACE_WORD}"><w:body>{corpo}</w:body></w:document>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as arquivo:
        arquivo.writestr("word/document.xml", xml)
    return buffer.getvalue()


def test_texto_puro_e_decodificado():
    resultado = extrair_texto_raw(b"Dado pessoal e informacao", "text/plain", "lgpd.txt")
    assert resultado.texto == "Dado pessoal e informacao"
    assert resultado.metadados["parser"] == "raw"


def test_markdown_e_decodificado_sem_interpretar():
    resultado = extrair_texto_raw(b"# Titulo\n\nCorpo", "text/markdown", "lgpd.md")
    assert resultado.texto == "# Titulo\n\nCorpo"


def test_bytes_invalidos_em_utf8_nao_derrubam_a_ingestao():
    resultado = extrair_texto_raw(b"Prote\xe7\xe3o de dados", "text/plain", "lgpd.txt")
    assert "de dados" in resultado.texto


def test_docx_concatena_paragrafos():
    resultado = extrair_texto_raw(
        _docx(["Primeiro paragrafo", "Segundo paragrafo"]), MIME_DOCX, "lgpd.docx"
    )
    assert resultado.texto == "Primeiro paragrafo\nSegundo paragrafo"


def test_os_quatro_mimes_da_spec_sao_aceitos():
    assert set(MIMES_SUPORTADOS) == {
        "application/pdf",
        "text/plain",
        "text/markdown",
        MIME_DOCX,
    }


def test_docx_sem_texto_e_erro():
    with pytest.raises(ErroDeParsing, match="nao produziu texto"):
        extrair_texto_raw(_docx(["   ", ""]), MIME_DOCX, "vazio.docx")


def test_pdf_junta_as_paginas_e_conta_quantas_sao(monkeypatch):
    """Testa a costura entre pypdf e o nosso contrato, nao o pypdf."""
    paginas = [
        SimpleNamespace(extract_text=lambda: "Pagina um"),
        SimpleNamespace(extract_text=lambda: "Pagina dois"),
        SimpleNamespace(extract_text=lambda: None),
    ]
    monkeypatch.setattr("app.rag.parsing.raw.PdfReader", lambda _: SimpleNamespace(pages=paginas))
    resultado = extrair_texto_raw(b"%PDF-1.4", "application/pdf", "lgpd.pdf")
    assert resultado.texto == "Pagina um\nPagina dois"
    assert resultado.metadados == {"parser": "raw", "paginas": 3}


def _pdf_com_conteudo(*conteudos: bytes) -> bytes:
    """PDF de verdade com uma pagina por content stream, fonte Helvetica como /F1."""
    escritor = PdfWriter()
    fonte = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    for conteudo in conteudos:
        pagina = escritor.add_blank_page(width=612, height=792)
        pagina[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): fonte})}
        )
        stream = DecodedStreamObject()
        stream.set_data(conteudo)
        pagina[NameObject("/Contents")] = escritor._add_object(stream)
    buffer = io.BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


def test_pdf_do_dompdf_com_nulos_fora_das_strings_e_reparado():
    """Export do BookStack (dompdf, texto justificado) grava \\x00 entre os itens do TJ."""
    integra = b"BT /F1 12 Tf 72 720 Td [(Pagina) -100 (integra)] TJ ET"
    defeituosa = b"BT /F1 12 Tf 72 720 Td [(Texto)\x00 -321\x00 (justificado)\x00 ] TJ ET"
    resultado = extrair_texto_raw(
        _pdf_com_conteudo(integra, defeituosa), "application/pdf", "bookstack.pdf"
    )
    assert "Texto" in resultado.texto
    assert "justificado" in resultado.texto
    assert "integra" in resultado.texto
    assert resultado.metadados == {"parser": "raw", "paginas": 2, "paginas_reparadas": [2]}


def test_reparo_preserva_nulos_dentro_das_strings():
    from app.rag.parsing.raw import _remover_nulos_fora_de_strings

    # Parentese escapado e parenteses aninhados nao encerram a string.
    conteudo = b"[(\x00A\\)\x00(\x00B)\x00)\x00 -5\x00 (C)] TJ"
    assert _remover_nulos_fora_de_strings(conteudo) == b"[(\x00A\\)\x00(\x00B)\x00) -5 (C)] TJ"


def test_pdf_corrompido_vira_erro_de_parsing():
    with pytest.raises(ErroDeParsing):
        extrair_texto_raw(b"isto nao e um pdf", "application/pdf", "quebrado.pdf")


def test_mime_nao_suportado_e_erro():
    with pytest.raises(ErroDeParsing, match="nao suportado"):
        extrair_texto_raw(b"conteudo", "image/png", "grafico.png")


def test_texto_vazio_e_erro():
    with pytest.raises(ErroDeParsing, match="nao produziu texto"):
        extrair_texto_raw(b"   \n  ", "text/plain", "vazio.txt")
