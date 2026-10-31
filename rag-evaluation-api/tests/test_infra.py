import httpx
import pytest
from pymilvus import MilvusClient

from app.core.config import get_settings


@pytest.mark.integration
def test_milvus_responde():
    settings = get_settings()
    client = MilvusClient(
        uri=settings.milvus_uri,
        token=f"{settings.milvus_username}:{settings.milvus_password}",
    )
    assert isinstance(client.list_collections(), list)


@pytest.mark.integration
def test_docling_responde():
    settings = get_settings()
    resposta = httpx.get(f"{settings.docling_url}/health", timeout=10)
    assert resposta.status_code == 200
