import httpx
import pytest

from app.models.pipeline import ParserType
from app.rag.parsing import obter_parser
from app.rag.parsing.base import ErroDeParsing
from app.rag.parsing.docling import extrair_texto_docling
from app.rag.parsing.raw import extrair_texto_raw


def _cliente(resposta: httpx.Response, capturadas: list[httpx.Request] | None = None):
    def responder(requisicao: httpx.Request) -> httpx.Response:
        if capturadas is not None:
            capturadas.append(requisicao)
        return resposta

    # base_url e obrigatorio: sem ele a URL fica relativa e o httpx nao consegue processa-la.
    # Em producao ela vem de `settings.docling_url`; aqui o host e ficticio de proposito, para
    # que um teste que escape do MockTransport falhe em vez de alcancar um servico de verdade.
    return httpx.Client(
        transport=httpx.MockTransport(responder), base_url="http://docling.invalido"
    )


def _sucesso(md: str = "# Titulo\n\n| a | b |") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "document": {"md_content": md, "json_content": {}, "text_content": ""},
            "status": "success",
            "processing_time": 1.5,
            "errors": [],
        },
    )


def test_devolve_o_markdown_estruturado():
    resultado = extrair_texto_docling(
        b"%PDF-1.4", "application/pdf", "lgpd.pdf", cliente=_cliente(_sucesso())
    )
    assert resultado.texto == "# Titulo\n\n| a | b |"
    assert resultado.metadados == {"parser": "docling", "status": "success"}


def test_envia_o_arquivo_pedindo_markdown():
    capturadas: list[httpx.Request] = []
    extrair_texto_docling(
        b"%PDF-1.4",
        "application/pdf",
        "lgpd.pdf",
        cliente=_cliente(_sucesso(), capturadas),
    )
    requisicao = capturadas[0]
    corpo = requisicao.content.decode("utf-8", errors="replace")
    assert requisicao.url.path == "/v1/convert/file"
    assert 'name="to_formats"' in corpo
    assert "md" in corpo
    assert "lgpd.pdf" in corpo


def test_partial_success_e_aceito():
    resposta = httpx.Response(
        200,
        json={
            "document": {"md_content": "conteudo parcial"},
            "status": "partial_success",
            "errors": ["pagina 3 ilegivel"],
        },
    )
    resultado = extrair_texto_docling(
        b"%PDF-1.4", "application/pdf", "lgpd.pdf", cliente=_cliente(resposta)
    )
    assert resultado.texto == "conteudo parcial"
    assert resultado.metadados["status"] == "partial_success"


def test_status_de_falha_vira_erro_de_parsing():
    resposta = httpx.Response(
        200, json={"document": {"md_content": ""}, "status": "failure", "errors": ["quebrou"]}
    )
    with pytest.raises(ErroDeParsing, match="quebrou"):
        extrair_texto_docling(
            b"%PDF-1.4", "application/pdf", "lgpd.pdf", cliente=_cliente(resposta)
        )


def test_erro_http_vira_erro_de_parsing():
    resposta = httpx.Response(500, text="Internal Server Error")
    with pytest.raises(ErroDeParsing, match="500"):
        extrair_texto_docling(
            b"%PDF-1.4", "application/pdf", "lgpd.pdf", cliente=_cliente(resposta)
        )


def test_markdown_vazio_vira_erro_de_parsing():
    with pytest.raises(ErroDeParsing, match="nao produziu texto"):
        extrair_texto_docling(
            b"%PDF-1.4", "application/pdf", "lgpd.pdf", cliente=_cliente(_sucesso(md="   "))
        )


def test_docling_indisponivel_vira_erro_de_parsing():
    def recusar(_requisicao: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("conexao recusada")

    cliente = httpx.Client(
        transport=httpx.MockTransport(recusar), base_url="http://docling.invalido"
    )
    with pytest.raises(ErroDeParsing, match="docling"):
        extrair_texto_docling(b"%PDF-1.4", "application/pdf", "lgpd.pdf", cliente=cliente)


def test_a_fabrica_devolve_o_parser_de_cada_tipo():
    assert obter_parser(ParserType.RAW) is extrair_texto_raw
    assert obter_parser(ParserType.DOCLING) is extrair_texto_docling
