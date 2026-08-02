from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.health import ComponenteSaude

client = TestClient(app)


def test_health_reporta_os_tres_componentes():
    with (
        patch("app.api.routers.health.verificar_postgres") as pg,
        patch("app.api.routers.health.verificar_milvus") as milvus,
        patch("app.api.routers.health.verificar_docling") as docling,
    ):
        pg.return_value = ComponenteSaude(nome="postgres", disponivel=True)
        milvus.return_value = ComponenteSaude(nome="milvus", disponivel=True)
        docling.return_value = ComponenteSaude(nome="docling", disponivel=True)

        resposta = client.get("/api/health")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["saudavel"] is True
    assert {c["nome"] for c in corpo["componentes"]} == {"postgres", "milvus", "docling"}


def test_health_fica_degradado_quando_um_componente_cai():
    with (
        patch("app.api.routers.health.verificar_postgres") as pg,
        patch("app.api.routers.health.verificar_milvus") as milvus,
        patch("app.api.routers.health.verificar_docling") as docling,
    ):
        pg.return_value = ComponenteSaude(nome="postgres", disponivel=True)
        milvus.return_value = ComponenteSaude(nome="milvus", disponivel=True)
        docling.return_value = ComponenteSaude(
            nome="docling", disponivel=False, erro="Connection refused"
        )

        resposta = client.get("/api/health")

    assert resposta.status_code == 503
    assert resposta.json()["saudavel"] is False


def test_swagger_esta_exposto():
    assert client.get("/docs").status_code == 200


def test_cors_permite_o_frontend_angular():
    resposta = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:4200",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resposta.headers["access-control-allow-origin"] == "http://localhost:4200"
