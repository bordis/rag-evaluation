import json

import httpx
import pytest

from app.models.pipeline import ParserType
from app.rag.parsing import obter_parser
from app.rag.parsing.base import ErroDeParsing
from app.rag.parsing.docling import extrair_texto_docling
from app.rag.parsing.raw import extrair_texto_raw


def _resultado(md: str = "# Titulo\n\n| a | b |", status: str = "success") -> dict:
    return {
        "document": {
            "md_content": md,
            "json_content": {
                "pages": {"1": {}, "2": {}},
                "tables": [{}],
                "pictures": [{}, {}, {}],
            },
        },
        "status": status,
        "errors": [],
    }


def _cliente(
    resultado: dict | None = None,
    *,
    estados: list[str] | None = None,
    capturadas: list[httpx.Request] | None = None,
    envio: httpx.Response | None = None,
):
    pendentes = list(estados or ["success"])

    def responder(requisicao: httpx.Request) -> httpx.Response:
        if capturadas is not None:
            capturadas.append(requisicao)
        caminho = requisicao.url.path
        if caminho == "/v1/convert/file/async":
            return envio or httpx.Response(200, json={"task_id": "t1"})
        if caminho == "/v1/status/poll/t1":
            return httpx.Response(200, json={"task_status": pendentes.pop(0)})
        return httpx.Response(200, json=resultado or _resultado())

    # Host ficticio de proposito: um teste que escape do MockTransport falha em vez de alcancar
    # um servico de verdade.
    return httpx.Client(
        transport=httpx.MockTransport(responder), base_url="http://docling.invalido"
    )


def _converter(cliente: httpx.Client):
    return extrair_texto_docling(
        b"%PDF-1.4", "application/pdf", "lgpd.pdf", cliente=cliente, intervalo=0
    )


def test_devolve_o_markdown_e_as_contagens_do_documento():
    resultado = _converter(_cliente())

    assert resultado.texto == "# Titulo\n\n| a | b |"
    assert resultado.metadados == {
        "parser": "docling",
        "status": "success",
        "paginas": 2,
        "tabelas": 1,
        "imagens": 3,
    }


def test_aguarda_a_tarefa_terminar():
    capturadas: list[httpx.Request] = []

    _converter(_cliente(estados=["started", "started", "success"], capturadas=capturadas))

    caminhos = [item.url.path for item in capturadas]
    assert caminhos.count("/v1/status/poll/t1") == 3
    assert caminhos[-1] == "/v1/result/t1"


def test_envia_a_configuracao_da_dissertacao():
    capturadas: list[httpx.Request] = []

    _converter(_cliente(capturadas=capturadas))

    corpo = capturadas[0].content.decode("utf-8", errors="replace")
    assert "lgpd.pdf" in corpo
    for trecho in ("pypdfium2", "accurate", 'name="do_ocr"', "picture_description_api"):
        assert trecho in corpo
    assert "gpt-4.1-mini" in corpo


def test_sem_descricao_de_imagens_nao_envia_a_api(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "docling_descrever_imagens", False)
    capturadas: list[httpx.Request] = []

    _converter(_cliente(capturadas=capturadas))

    assert "picture_description_api" not in capturadas[0].content.decode(errors="replace")


def test_partial_success_e_aceito():
    resultado = _converter(_cliente(_resultado(status="partial_success")))

    assert resultado.metadados["status"] == "partial_success"


def test_status_de_falha_vira_erro_de_parsing():
    with pytest.raises(ErroDeParsing):
        _converter(_cliente(_resultado(status="failure")))


def test_tarefa_que_falha_vira_erro_de_parsing():
    with pytest.raises(ErroDeParsing):
        _converter(_cliente(estados=["failure"]))


def test_markdown_vazio_vira_erro_de_parsing():
    with pytest.raises(ErroDeParsing):
        _converter(_cliente(_resultado(md="   ")))


def test_status_http_de_erro_vira_erro_de_parsing():
    with pytest.raises(ErroDeParsing):
        _converter(_cliente(envio=httpx.Response(500, text="erro")))


def test_conexao_recusada_vira_erro_de_parsing():
    def recusar(requisicao: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("recusada", request=requisicao)

    cliente = httpx.Client(
        transport=httpx.MockTransport(recusar), base_url="http://docling.invalido"
    )
    with pytest.raises(ErroDeParsing):
        _converter(cliente)


def test_opcao_de_imagens_e_um_json_valido_com_autorizacao():
    capturadas: list[httpx.Request] = []

    _converter(_cliente(capturadas=capturadas))

    corpo = capturadas[0].content.decode("utf-8", errors="replace")
    inicio = corpo.index('name="picture_description_api"')
    trecho = corpo[corpo.index("{", inicio) : corpo.index("\r\n--", inicio)]
    assert "Authorization" in json.loads(trecho)["headers"]


def test_obter_parser_escolhe_pelo_tipo():
    assert obter_parser(ParserType.DOCLING) is extrair_texto_docling
    assert obter_parser(ParserType.RAW) is extrair_texto_raw


def _com_imagem(area_relativa: float, anotacoes: list[dict]) -> dict:
    resultado = _resultado()
    lado = 100 * area_relativa**0.5
    resultado["document"]["json_content"] = {
        "pages": {"1": {"size": {"width": 100, "height": 100}}},
        "tables": [],
        "pictures": [
            {
                "self_ref": "#/pictures/0",
                "annotations": anotacoes,
                "prov": [{"page_no": 1, "bbox": {"l": 0, "r": lado, "t": lado, "b": 0}}],
            }
        ],
    }
    return resultado


def test_imagem_grande_sem_descricao_derruba_a_ingestao():
    """O Docling responde `success` quando o VLM falha; a falha nao pode passar em silencio."""
    with pytest.raises(ErroDeParsing, match="#/pictures/0"):
        _converter(_cliente(_com_imagem(0.5, [])))


def test_imagem_abaixo_do_limiar_nao_precisa_de_descricao():
    assert _converter(_cliente(_com_imagem(0.01, []))).metadados["imagens"] == 1


def test_imagem_descrita_passa():
    anotacao = [{"kind": "description", "text": "Um grafico."}]

    assert _converter(_cliente(_com_imagem(0.5, anotacao))).metadados["imagens"] == 1
