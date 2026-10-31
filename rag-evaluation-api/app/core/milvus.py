"""Acesso ao Milvus: uma collection por pipeline, com schema identico.

Cada pipeline tem collection propria porque o BM25 calcula IDF e comprimento medio sobre o corpus
da collection. Numa collection unica, o mesmo documento entraria quatro vezes (raw e Docling) e as
estatisticas de um braco experimental contaminariam as do outro.
"""

from pymilvus import DataType, Function, FunctionType, MilvusClient

from app.core.config import get_settings

CAMPO_DOCUMENTO = "document_id"
CAMPO_CHUNK = "chunk_index"
CAMPO_TEXTO = "text"
CAMPO_ESPARSO = "sparse_vector"
CAMPO_DENSO = "dense_vector"
CAMPO_METADADOS = "metadados"

NOME_FUNCAO_BM25 = "text_bm25"

# Nao existe atalho {"type": "portuguese"} — para linguas europeias e preciso a forma explicita.
ANALISADOR_PORTUGUES: dict = {
    "tokenizer": "standard",
    "filter": [
        "lowercase",
        "asciifolding",
        {"type": "stemmer", "language": "portuguese"},
        {"type": "stop", "stop_words": ["_portuguese_"]},
    ],
}


def construir_cliente() -> MilvusClient:
    settings = get_settings()
    return MilvusClient(
        uri=settings.milvus_uri,
        token=f"{settings.milvus_username}:{settings.milvus_password}",
        db_name=settings.milvus_database_name,
    )


def _montar_schema(cliente: MilvusClient):
    schema = cliente.create_schema(auto_id=True, enable_dynamic_field=False)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field(CAMPO_DOCUMENTO, DataType.VARCHAR, max_length=64)
    schema.add_field(CAMPO_CHUNK, DataType.INT64)
    schema.add_field(
        CAMPO_TEXTO,
        DataType.VARCHAR,
        max_length=8192,
        enable_analyzer=True,
        analyzer_params=ANALISADOR_PORTUGUES,
    )
    schema.add_field(CAMPO_ESPARSO, DataType.SPARSE_FLOAT_VECTOR)
    schema.add_field(CAMPO_DENSO, DataType.FLOAT_VECTOR, dim=get_settings().embedding_dimensions)
    schema.add_field(CAMPO_METADADOS, DataType.JSON)
    schema.add_function(
        Function(
            name=NOME_FUNCAO_BM25,
            function_type=FunctionType.BM25,
            input_field_names=[CAMPO_TEXTO],
            output_field_names=[CAMPO_ESPARSO],
        )
    )
    return schema


def _montar_indices(cliente: MilvusClient):
    indices = cliente.prepare_index_params()
    # FLAT: o filtro por documento descarta mais de 90% dos vetores, faixa em que a documentacao do
    # Milvus indica busca exata. Sem aproximacao, o indice nao entra como variavel do estudo.
    indices.add_index(field_name=CAMPO_DENSO, index_type="FLAT", metric_type="COSINE")
    indices.add_index(
        field_name=CAMPO_ESPARSO, index_type="SPARSE_INVERTED_INDEX", metric_type="BM25"
    )
    return indices


def garantir_collection(cliente: MilvusClient, nome: str) -> None:
    """Cria a collection de um pipeline novo com o mesmo schema e indice das demais."""
    if not cliente.has_collection(nome):
        cliente.create_collection(
            collection_name=nome,
            schema=_montar_schema(cliente),
            index_params=_montar_indices(cliente),
        )


def criar_collections(cliente: MilvusClient) -> list[str]:
    """Cria as collections que faltam. Devolve os nomes criados nesta chamada."""
    criadas: list[str] = []
    for nome in get_settings().collection_por_codigo.values():
        if cliente.has_collection(nome):
            continue
        cliente.create_collection(
            collection_name=nome,
            schema=_montar_schema(cliente),
            index_params=_montar_indices(cliente),
        )
        criadas.append(nome)
    return criadas


def remover_collections(cliente: MilvusClient) -> None:
    for nome in get_settings().collection_por_codigo.values():
        if cliente.has_collection(nome):
            cliente.drop_collection(nome)
