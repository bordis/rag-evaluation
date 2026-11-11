import pytest

from app.core import armazenamento


class ConfigFalsa:
    minio_access_key = "chave"
    minio_secret_key = "segredo"

    def __init__(self, minio_url: str) -> None:
        self.minio_url = minio_url


@pytest.mark.parametrize(
    ("url", "host", "seguro"),
    [
        ("http://localhost:9000", "localhost:9000", False),
        ("https://minio.exemplo.org", "minio.exemplo.org", True),
    ],
)
def test_cliente_separa_host_e_tls_da_url(monkeypatch, url, host, seguro):
    recebidos = {}

    def minio_falso(endpoint, **opcoes):
        recebidos.update(endpoint=endpoint, **opcoes)

    monkeypatch.setattr(armazenamento, "get_settings", lambda: ConfigFalsa(url))
    monkeypatch.setattr(armazenamento, "Minio", minio_falso)

    armazenamento._cliente()

    assert recebidos["endpoint"] == host
    assert recebidos["secure"] is seguro
