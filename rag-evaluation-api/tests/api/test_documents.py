import uuid

import pytest
from sqlmodel import Session, select

from app.models.document import Document, DocumentIngestion, StatusDocumento, StatusIngestao
from app.models.pipeline import Pipeline
from app.seed import semear_pipelines

MIME_PDF = "application/pdf"


@pytest.fixture(name="pipelines", autouse=True)
def pipelines_fixture(sessao: Session):
    semear_pipelines(sessao)


@pytest.fixture(name="agendadas")
def agendadas_fixture(monkeypatch):
    """Captura o que o BackgroundTasks executaria, sem rodar a ingestao de verdade."""
    chamadas: list[tuple] = []
    monkeypatch.setattr(
        "app.api.routers.documents.executar_ingestao",
        lambda *argumentos: chamadas.append(argumentos),
    )
    return chamadas


class MilvusFalso:
    def __init__(self) -> None:
        self.remocoes: list[tuple[str, str]] = []

    def delete(self, collection_name: str, filter: str) -> dict:  # noqa: A002
        self.remocoes.append((collection_name, filter))
        return {"delete_count": 1}


def _formulario(**substituicoes) -> dict:
    dados = {"slug": "lgpd", "titulo": "LGPD", "area": "Direito", "descricao": "", "icone": ""}
    dados.update(substituicoes)
    return dados


def _documento(sessao: Session, **substituicoes) -> Document:
    campos = {
        "slug": "lgpd",
        "titulo": "LGPD",
        "area": "Direito",
        "descricao": "",
        "icone": "",
        "nome_arquivo_original": "lgpd.pdf",
        "mime_type": MIME_PDF,
        "tamanho_bytes": 10,
        "sha256": "c" * 64,
    }
    campos.update(substituicoes)
    documento = Document(**campos)
    sessao.add(documento)
    sessao.commit()
    sessao.refresh(documento)
    return documento


def test_upload_aceito_responde_202_e_agenda_a_ingestao(cliente, sessao, agendadas):
    resposta = cliente.post(
        "/api/documents",
        data=_formulario(),
        files={"arquivo": ("lgpd.pdf", b"%PDF-1.4 conteudo", MIME_PDF)},
    )
    assert resposta.status_code == 202
    corpo = resposta.json()
    assert corpo["slug"] == "lgpd"
    assert corpo["status"] == "processando"

    documento = sessao.exec(select(Document).where(Document.slug == "lgpd")).one()
    assert documento.mime_type == MIME_PDF
    assert documento.tamanho_bytes == len(b"%PDF-1.4 conteudo")
    assert len(agendadas) == 1
    assert agendadas[0][0] == documento.id
    assert agendadas[0][1] == b"%PDF-1.4 conteudo"


def test_upload_cria_as_quatro_linhas_de_ingestao_pendentes(cliente, sessao, agendadas):
    cliente.post(
        "/api/documents",
        data=_formulario(),
        files={"arquivo": ("lgpd.pdf", b"%PDF-1.4", MIME_PDF)},
    )
    ingestoes = sessao.exec(select(DocumentIngestion)).all()
    assert len(ingestoes) == 4
    assert all(item.status == StatusIngestao.PENDENTE for item in ingestoes)


def test_pdf_sem_content_type_util_e_resolvido_pela_extensao(cliente, sessao, agendadas):
    resposta = cliente.post(
        "/api/documents",
        data=_formulario(slug="manual"),
        files={"arquivo": ("manual.pdf", b"%PDF-1.4", "application/octet-stream")},
    )
    assert resposta.status_code == 202
    documento = sessao.exec(select(Document).where(Document.slug == "manual")).one()
    assert documento.mime_type == "application/pdf"


def test_tipo_nao_suportado_responde_415(cliente, agendadas):
    resposta = cliente.post(
        "/api/documents",
        data=_formulario(),
        files={"arquivo": ("grafico.png", b"\x89PNG", "image/png")},
    )
    assert resposta.status_code == 415
    assert agendadas == []


def test_arquivo_acima_do_limite_responde_413(cliente, agendadas):
    from app.core.config import get_settings

    excesso = b"x" * (get_settings().max_upload_mb * 1024 * 1024 + 1)
    resposta = cliente.post(
        "/api/documents",
        data=_formulario(),
        files={"arquivo": ("grande.pdf", excesso, "application/pdf")},
    )
    assert resposta.status_code == 413
    assert agendadas == []


def test_slug_repetido_responde_409(cliente, sessao, agendadas):
    _documento(sessao)
    resposta = cliente.post(
        "/api/documents",
        data=_formulario(),
        files={"arquivo": ("outro.pdf", b"%PDF outro", MIME_PDF)},
    )
    assert resposta.status_code == 409
    assert "slug" in resposta.json()["detail"]


def test_arquivo_duplicado_responde_409(cliente, sessao, agendadas):
    import hashlib

    conteudo = b"%PDF-1.4 identico"
    _documento(sessao, sha256=hashlib.sha256(conteudo).hexdigest())
    resposta = cliente.post(
        "/api/documents",
        data=_formulario(slug="outro-slug"),
        files={"arquivo": ("copia.pdf", conteudo, MIME_PDF)},
    )
    assert resposta.status_code == 409
    assert "enviado" in resposta.json()["detail"]


def test_slug_invalido_responde_422(cliente, agendadas):
    resposta = cliente.post(
        "/api/documents",
        data=_formulario(slug="LGPD Completa!"),
        files={"arquivo": ("lgpd.pdf", b"%PDF", MIME_PDF)},
    )
    assert resposta.status_code == 422


def test_listagem_sem_filtro_devolve_tudo(cliente, sessao):
    _documento(sessao, slug="um", sha256="1" * 64)
    _documento(sessao, slug="dois", sha256="2" * 64, status=StatusDocumento.PRONTO)
    resposta = cliente.get("/api/documents")
    assert resposta.status_code == 200
    assert {item["slug"] for item in resposta.json()} == {"um", "dois"}


def test_listagem_filtra_por_status(cliente, sessao):
    _documento(sessao, slug="um", sha256="1" * 64)
    _documento(sessao, slug="dois", sha256="2" * 64, status=StatusDocumento.PRONTO)
    resposta = cliente.get("/api/documents", params={"status": "pronto"})
    assert [item["slug"] for item in resposta.json()] == ["dois"]


def test_detalhe_traz_os_dados_do_arquivo(cliente, sessao):
    documento = _documento(sessao)
    resposta = cliente.get(f"/api/documents/{documento.id}")
    assert resposta.status_code == 200
    assert resposta.json()["sha256"] == "c" * 64
    assert resposta.json()["nome_arquivo_original"] == "lgpd.pdf"


def test_detalhe_de_documento_inexistente_responde_404(cliente):
    assert cliente.get(f"/api/documents/{uuid.uuid4()}").status_code == 404


def test_ingestions_devolvem_telemetria_por_pipeline(cliente, sessao):
    documento = _documento(sessao)
    for pipeline in sessao.exec(select(Pipeline).order_by(Pipeline.codigo)).all():
        sessao.add(
            DocumentIngestion(
                document_id=documento.id,
                pipeline_id=pipeline.id,
                status=StatusIngestao.CONCLUIDA,
                total_chunks=12,
                tokens_embedding=340,
                duracao_total_ms=980,
            )
        )
    sessao.commit()

    resposta = cliente.get(f"/api/documents/{documento.id}/ingestions")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [item["pipeline_codigo"] for item in corpo] == [
        "pipeline-1",
        "pipeline-2",
        "pipeline-3",
        "pipeline-4",
    ]
    assert corpo[0]["total_chunks"] == 12
    assert corpo[0]["tokens_embedding"] == 340


def test_exclusao_limpa_as_quatro_collections_e_o_banco(cliente, sessao, monkeypatch):
    documento = _documento(sessao)
    for pipeline in sessao.exec(select(Pipeline)).all():
        sessao.add(DocumentIngestion(document_id=documento.id, pipeline_id=pipeline.id))
    sessao.commit()

    milvus = MilvusFalso()
    monkeypatch.setattr("app.api.routers.documents.construir_cliente", lambda: milvus)

    resposta = cliente.delete(f"/api/documents/{documento.id}")
    assert resposta.status_code == 204
    assert [collection for collection, _ in milvus.remocoes] == [
        "evaluation1",
        "evaluation2",
        "evaluation3",
        "evaluation4",
    ]
    assert all(str(documento.id) in filtro for _, filtro in milvus.remocoes)
    assert sessao.get(Document, documento.id) is None
    assert sessao.exec(select(DocumentIngestion)).all() == []


def test_exclusao_de_documento_inexistente_responde_404(cliente, monkeypatch):
    monkeypatch.setattr("app.api.routers.documents.construir_cliente", lambda: MilvusFalso())
    assert cliente.delete(f"/api/documents/{uuid.uuid4()}").status_code == 404


def test_acervo_so_aceita_pdf(cliente):
    resposta = cliente.post(
        "/api/documents",
        files={"arquivo": ("notas.txt", b"texto", "text/plain")},
        data={"slug": "notas", "titulo": "Notas", "area": "Geral"},
    )

    assert resposta.status_code == 415
