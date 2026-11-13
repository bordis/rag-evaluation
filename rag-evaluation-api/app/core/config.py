from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracao do backend, lida do .env. Falha na subida se faltar algo obrigatorio."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Chat: qualquer servico compativel com a API da OpenAI (a URL inclui o /v1)
    chat_model: str = "gpt-4.1-mini"
    chat_base_url: str = "https://api.openai.com/v1"
    chat_temperature: float = 0.3
    chat_api_key: str
    chat_max_tokens: int = 1024

    # Embeddings, tambem no formato da OpenAI. Modelos assimetricos usam um nome para indexar
    # trechos e outro para a consulta; nos simetricos os dois sao iguais.
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

    # MinIO — guarda os PDFs do acervo, em bucket separado do que o Milvus usa
    minio_url: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket_documentos: str = "documentos"

    # Docling
    docling_url: str = "http://localhost:5001"
    # Converter um PDF grande leva minutos; o timeout de consulta (60s) nao serve aqui.
    docling_timeout_seconds: int = 1800
    # OCR desligado: os documentos do estudo sao PDFs digitais. Ligado, o Docling carregaria
    # modelos de visao e o tempo de ingestao deixaria de ser comparavel ao do parser raw.
    docling_do_ocr: bool = False
    docling_pdf_backend: str = "pypdfium2"
    docling_table_mode: str = "accurate"
    docling_descrever_imagens: bool = True
    docling_imagem_area_minima: float = 0.05
    docling_imagem_modelo: str = "gpt-4.1-mini"

    # Reordenador dos pipelines 3 e 4. A URL e o endpoint completo, no formato /v1/rerank
    # (Jina/Cohere, o que o vLLM serve); a chave vai como Bearer. O nome do modelo vem da resposta.
    reranker_url: str = "http://localhost:8081/v1/rerank"
    reranker_key: str = ""

    # RAGAS: o juiz roda em servico proprio, separado do modelo de geracao. Sem chave propria,
    # vale a do chat.
    ragas_llm_model: str = "gpt-4.1"
    ragas_llm_url: str = "https://api.openai.com/v1"
    ragas_llm_key: str = ""
    # Juiz com raciocinio (DeepSeek, Qwen) gasta o max_tokens pensando e devolve conteudo vazio nas
    # respostas longas, alem de ficar varias vezes mais lento. Liga `enable_thinking=False` no
    # template do vLLM/SGLang; a API da OpenAI rejeita o parametro, por isso o padrao e desligado.
    ragas_llm_sem_raciocinio: bool = False
    # Por chamada ao juiz. Sem isso vale o padrao do SDK (600 s x 3 tentativas) e um lote parece
    # travado por meia hora quando o servico deixa uma chamada sem resposta.
    ragas_timeout_seconds: int = 120

    # RAG
    # Chunks entregues ao LLM nos 4 pipelines (decisao 4 da ficha). A busca e filtrada por
    # documento; um documento de 20-30 paginas da, por estimativa, 50-100 chunks de 256 tokens.
    # Com 15, o LLM via 15-30% do documento e a busca densa simples ja acertava quase sempre
    # (efeito teto). Com 6 (~1.500 tokens, 6-12% estimados) sobra espaco para o fator B. Custo:
    # perguntas de sintese ficam mais dificeis nos 4 pipelines. Mudar nao exige reingestao, mas
    # vale so na semeadura: pipelines ja semeados leem top_k/ancoras da propria config no banco.
    rag_search_limit: int = 6
    # Ancoras antes dos vizinhos nos pipelines 3 e 4. ancoras x (2 x janela + 1) = rag_search_limit:
    # 2 ancoras +-1 vizinho = 6.
    rag_ancoras: int = 2
    # Em tokens (cl100k_base), cortando em fim de frase. Sem sobreposicao: o que ela atenuaria e o
    # que os vizinhos do fator B tratam, e os vizinhos repetiriam o texto sobreposto no contexto.
    chunk_size: int = 256
    chunk_overlap: int = 0
    # A reordenacao escolhe as ancoras entre estes candidatos (2 entre 20: uma selecao de fato), e
    # os seguintes do ranking completam o contexto se os vizinhos faltarem. Em CPU, cada candidato
    # custa quase 1 s de espera para o avaliador, entao mais que isso pesa na coleta.
    rerank_candidates: int = 20
    sliding_window_size: int = 1
    # A reordenacao forma fila: com avaliadores simultaneos, a espera se soma.
    pipeline_timeout_seconds: int = 300
    max_perguntas: int = 10
    max_upload_mb: int = 25

    cors_origins: str = "http://localhost:4200"

    # SSO: a API so valida o access token do Keycloak (assinatura pelo JWKS do realm, emissor e
    # validade). As roles vem do cliente, em resource_access.<client_id>.roles.
    keycloak_url: str = "https://sso-pmpa.procempa.com.br/auth"
    keycloak_realm: str = "pmpa"
    keycloak_client_id: str = "smartgen"

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
    def reranker_health_url(self) -> str:
        """O /health fica na raiz do servico, nao sob o caminho do endpoint."""
        partes = urlsplit(self.reranker_url)
        return f"{partes.scheme}://{partes.netloc}/health"

    @computed_field
    @property
    def keycloak_issuer(self) -> str:
        return f"{self.keycloak_url.rstrip('/')}/realms/{self.keycloak_realm}"

    @computed_field
    @property
    def keycloak_jwks_url(self) -> str:
        return f"{self.keycloak_issuer}/protocol/openid-connect/certs"

    @computed_field
    @property
    def cors_origin_list(self) -> list[str]:
        return [origem.strip() for origem in self.cors_origins.split(",") if origem.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
