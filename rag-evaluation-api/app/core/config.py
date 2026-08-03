from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracao do backend, lida do .env. Falha na subida se faltar algo obrigatorio."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OpenAI — chat
    chat_model: str = "gpt-4.1-mini"
    chat_base_url: str = "https://api.openai.com/v1"
    chat_temperature: float = 0.3
    chat_api_key: str
    chat_max_tokens: int = 1024

    # OpenAI — embeddings
    embedding_model: str = "text-embedding-3-small"
    embedding_model_query: str = "text-embedding-3-small"
    embedding_url: str = "https://api.openai.com/v1"
    embedding_dimensions: int = 1536

    # PostgreSQL
    db_name: str = "rag-evaluation"
    db_url: str = "postgresql://localhost:5432"
    db_username: str = "postgres"
    db_password: str = "admin"

    # Milvus
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_username: str = "root"
    milvus_password: str = "Milvus"
    milvus_database_name: str = "default"
    milvus_collection_name_1: str = "evaluation1"
    milvus_collection_name_2: str = "evaluation2"
    milvus_collection_name_3: str = "evaluation3"
    milvus_collection_name_4: str = "evaluation4"

    # Docling
    docling_url: str = "http://localhost:5001"
    # Converter um PDF grande leva minutos; o timeout de consulta (60s) nao serve aqui.
    docling_timeout_seconds: int = 600
    # OCR desligado: os documentos do estudo sao PDFs digitais. Ligado, o Docling carregaria
    # modelos de visao e o tempo de ingestao deixaria de ser comparavel ao do parser raw.
    docling_do_ocr: bool = False

    # RAG
    rag_search_limit: int = 5
    chunk_size: int = 800
    chunk_overlap: int = 150
    rerank_candidates: int = 20
    sliding_window_size: int = 1
    pipeline_timeout_seconds: int = 60
    max_perguntas: int = 10
    max_upload_mb: int = 25

    cors_origins: str = "http://localhost:4200"

    @computed_field
    @property
    def sqlalchemy_url(self) -> str:
        """Converte o formato JDBC herdado dos requisitos para o dialeto do psycopg."""
        host_port = self.db_url.removeprefix("jdbc:").split("://", 1)[-1].rstrip("/")
        return (
            f"postgresql+psycopg://{self.db_username}:{self.db_password}@{host_port}/{self.db_name}"
        )

    @computed_field
    @property
    def milvus_uri(self) -> str:
        return f"http://{self.milvus_host}:{self.milvus_port}"

    @computed_field
    @property
    def collection_por_codigo(self) -> dict[str, str]:
        return {
            "pipeline-1": self.milvus_collection_name_1,
            "pipeline-2": self.milvus_collection_name_2,
            "pipeline-3": self.milvus_collection_name_3,
            "pipeline-4": self.milvus_collection_name_4,
        }

    @computed_field
    @property
    def cors_origin_list(self) -> list[str]:
        return [origem.strip() for origem in self.cors_origins.split(",") if origem.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
