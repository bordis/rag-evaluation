import uuid

from app.models.pipeline import ParserType, Pipeline
from app.models.telemetry import EtapaPipeline
from app.rag.embedding import ResultadoEmbedding
from app.rag.pipeline import DependenciasDeConsulta, executar_pipeline
from app.rag.retrieval.base import Candidato, MetricaEtapa

DOCUMENTO = uuid.uuid4()
PERGUNTA = "O que e dado pessoal?"

CONFIG_CONTROLE = {
    "query_rewriting": False,
    "reranking": False,
    "hybrid_search": False,
    "sliding_window": {"ativo": False, "tamanho": 1},
    "top_k": 5,
}

CONFIG_AVANCADA = {
    "query_rewriting": True,
    "reranking": True,
    "hybrid_search": True,
    "sliding_window": {"ativo": True, "tamanho": 2},
    "top_k": 3,
}


def _pipeline(config: dict, codigo: str = "pipeline-1") -> Pipeline:
    return Pipeline(
        id=1,
        codigo=codigo,
        nome=codigo,
        parser=ParserType.RAW,
        collection_name="evaluation1",
        config=config,
    )


def _candidatos(quantidade: int) -> list[Candidato]:
    return [
        Candidato(milvus_id=100 + numero, chunk_index=numero, texto=f"trecho {numero}")
        for numero in range(quantidade)
    ]


class Espiao:
    """Substitui todas as etapas para o orquestrador rodar sem OpenAI nem Milvus."""

    def __init__(self) -> None:
        self.reescritas: list[str] = []
        self.embutidos: list[list[str]] = []
        self.buscas: list[dict] = []
        self.reordenacoes: list[dict] = []
        self.expansoes: list[dict] = []
        self.geracoes: list[dict] = []
        self.cliente = object()

    def reescrever(self, pergunta, **_):
        self.reescritas.append(pergunta)
        return "query reescrita", MetricaEtapa(EtapaPipeline.QUERY_REWRITING, 10)

    def embutir(self, textos):
        self.embutidos.append(textos)
        return ResultadoEmbedding(vetores=[[0.1, 0.2]], tokens=9)

    def buscar(self, cliente, collection_name, document_id, query, vetor, *, limite, hibrido):
        self.buscas.append(
            {"collection": collection_name, "query": query, "limite": limite, "hibrido": hibrido}
        )
        return _candidatos(limite), MetricaEtapa(EtapaPipeline.RETRIEVAL, 20)

    def reordenar(self, pergunta, candidatos, *, manter, **_):
        self.reordenacoes.append({"pergunta": pergunta, "manter": manter})
        return candidatos[:manter], MetricaEtapa(EtapaPipeline.RERANKING, 30)

    def expandir(self, cliente, collection_name, document_id, candidatos, *, tamanho):
        self.expansoes.append({"tamanho": tamanho, "entraram": len(candidatos)})
        return candidatos, MetricaEtapa(EtapaPipeline.WINDOW_EXPANSION, 40)

    def gerar(self, pergunta, candidatos, **_):
        self.geracoes.append({"pergunta": pergunta, "trechos": len(candidatos)})
        return "resposta gerada", MetricaEtapa(EtapaPipeline.GENERATION, 50)

    def dependencias(self) -> DependenciasDeConsulta:
        return DependenciasDeConsulta(
            reescrever=self.reescrever,
            embutir=self.embutir,
            buscar=self.buscar,
            reordenar=self.reordenar,
            expandir=self.expandir,
            gerar=self.gerar,
            construir_cliente_milvus=lambda: self.cliente,
        )


def _etapas(resposta) -> list[EtapaPipeline]:
    return [metrica.etapa for metrica in resposta.metricas]


def test_braco_de_controle_executa_exatamente_tres_etapas():
    espiao = Espiao()
    resposta = executar_pipeline(
        _pipeline(CONFIG_CONTROLE), DOCUMENTO, PERGUNTA, dependencias=espiao.dependencias()
    )
    assert _etapas(resposta) == [
        EtapaPipeline.EMBEDDING_QUERY,
        EtapaPipeline.RETRIEVAL,
        EtapaPipeline.GENERATION,
    ]
    assert espiao.reescritas == []
    assert espiao.reordenacoes == []
    assert espiao.expansoes == []


def test_braco_avancado_executa_as_seis_etapas_na_ordem():
    espiao = Espiao()
    resposta = executar_pipeline(
        _pipeline(CONFIG_AVANCADA, "pipeline-4"),
        DOCUMENTO,
        PERGUNTA,
        dependencias=espiao.dependencias(),
    )
    assert _etapas(resposta) == [
        EtapaPipeline.QUERY_REWRITING,
        EtapaPipeline.EMBEDDING_QUERY,
        EtapaPipeline.RETRIEVAL,
        EtapaPipeline.RERANKING,
        EtapaPipeline.WINDOW_EXPANSION,
        EtapaPipeline.GENERATION,
    ]


def test_config_parcial_monta_um_fluxo_intermediario():
    """Prova que o fluxo vem da config, e nao de dois caminhos codificados a mao."""
    espiao = Espiao()
    config = {**CONFIG_CONTROLE, "reranking": True}
    resposta = executar_pipeline(
        _pipeline(config), DOCUMENTO, PERGUNTA, dependencias=espiao.dependencias()
    )
    assert _etapas(resposta) == [
        EtapaPipeline.EMBEDDING_QUERY,
        EtapaPipeline.RETRIEVAL,
        EtapaPipeline.RERANKING,
        EtapaPipeline.GENERATION,
    ]


def test_top_k_vem_da_config_do_pipeline_e_nao_do_ambiente():
    """RAG_SEARCH_LIMIT e so a semente na criacao; mudar o .env nao pode afetar pipeline pronto."""
    espiao = Espiao()
    config = {**CONFIG_CONTROLE, "top_k": 2}
    executar_pipeline(_pipeline(config), DOCUMENTO, PERGUNTA, dependencias=espiao.dependencias())
    assert espiao.buscas[0]["limite"] == 2


def test_sem_reranking_a_busca_ja_pede_o_top_k_final():
    espiao = Espiao()
    executar_pipeline(
        _pipeline(CONFIG_CONTROLE), DOCUMENTO, PERGUNTA, dependencias=espiao.dependencias()
    )
    assert espiao.buscas[0]["limite"] == 5


def test_com_reranking_a_busca_pede_o_pool_maior_e_o_rerank_corta_no_top_k():
    espiao = Espiao()
    executar_pipeline(
        _pipeline(CONFIG_AVANCADA, "pipeline-3"),
        DOCUMENTO,
        PERGUNTA,
        dependencias=espiao.dependencias(),
    )
    assert espiao.buscas[0]["limite"] == 20
    assert espiao.reordenacoes[0]["manter"] == 3


def test_hybrid_search_so_e_pedido_quando_configurado():
    espiao = Espiao()
    executar_pipeline(
        _pipeline(CONFIG_CONTROLE), DOCUMENTO, PERGUNTA, dependencias=espiao.dependencias()
    )
    assert espiao.buscas[0]["hibrido"] is False

    outro = Espiao()
    executar_pipeline(
        _pipeline(CONFIG_AVANCADA, "pipeline-3"),
        DOCUMENTO,
        PERGUNTA,
        dependencias=outro.dependencias(),
    )
    assert outro.buscas[0]["hibrido"] is True


def test_a_busca_usa_a_query_reescrita():
    espiao = Espiao()
    executar_pipeline(
        _pipeline(CONFIG_AVANCADA, "pipeline-3"),
        DOCUMENTO,
        PERGUNTA,
        dependencias=espiao.dependencias(),
    )
    assert espiao.embutidos[0] == ["query reescrita"]
    assert espiao.buscas[0]["query"] == "query reescrita"


def test_rerank_e_geracao_recebem_a_pergunta_original():
    """A reescrita e uma string de busca; relevancia e resposta se julgam contra o que foi
    pedido."""
    espiao = Espiao()
    executar_pipeline(
        _pipeline(CONFIG_AVANCADA, "pipeline-3"),
        DOCUMENTO,
        PERGUNTA,
        dependencias=espiao.dependencias(),
    )
    assert espiao.reordenacoes[0]["pergunta"] == PERGUNTA
    assert espiao.geracoes[0]["pergunta"] == PERGUNTA


def test_tamanho_da_janela_vem_da_config():
    espiao = Espiao()
    executar_pipeline(
        _pipeline(CONFIG_AVANCADA, "pipeline-3"),
        DOCUMENTO,
        PERGUNTA,
        dependencias=espiao.dependencias(),
    )
    assert espiao.expansoes[0]["tamanho"] == 2


def test_busca_na_collection_do_pipeline():
    espiao = Espiao()
    pipeline = _pipeline(CONFIG_CONTROLE)
    pipeline.collection_name = "evaluation2"
    executar_pipeline(pipeline, DOCUMENTO, PERGUNTA, dependencias=espiao.dependencias())
    assert espiao.buscas[0]["collection"] == "evaluation2"


def test_resposta_carrega_texto_e_chunks_finais():
    espiao = Espiao()
    resposta = executar_pipeline(
        _pipeline(CONFIG_CONTROLE), DOCUMENTO, PERGUNTA, dependencias=espiao.dependencias()
    )
    assert resposta.texto == "resposta gerada"
    assert len(resposta.chunks) == 5
    assert espiao.geracoes[0]["trechos"] == 5


def test_metrica_do_embedding_carrega_os_tokens_da_query():
    espiao = Espiao()
    resposta = executar_pipeline(
        _pipeline(CONFIG_CONTROLE), DOCUMENTO, PERGUNTA, dependencias=espiao.dependencias()
    )
    embedding = resposta.metricas[0]
    assert embedding.etapa is EtapaPipeline.EMBEDDING_QUERY
    assert embedding.tokens_total == 9
    assert embedding.modelo == "text-embedding-3-small"
    assert embedding.detalhes["query"] == PERGUNTA
