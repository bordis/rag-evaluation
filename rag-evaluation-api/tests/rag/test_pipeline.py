import uuid

from app.models.pipeline import ParserType, Pipeline
from app.models.telemetry import EtapaChunk, EtapaPipeline
from app.rag.embedding import ResultadoEmbedding
from app.rag.pipeline import DependenciasDeConsulta, executar_pipeline
from app.rag.retrieval.base import Candidato, MetricaEtapa

DOCUMENTO = uuid.uuid4()
PERGUNTA = "O que e dado pessoal?"

CONFIG_CONTROLE = {
    "hyde": False,
    "reranking": False,
    "hybrid_search": False,
    "sliding_window": {"ativo": False, "tamanho": 1},
    "top_k": 15,
}

CONFIG_AVANCADA = {
    "hyde": True,
    "reranking": True,
    "hybrid_search": True,
    "sliding_window": {"ativo": True, "tamanho": 1},
    "top_k": 15,
    "ancoras": 5,
    "candidatos": 30,
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


def _candidatos(indices) -> list[Candidato]:
    return [
        Candidato(milvus_id=100 + numero, chunk_index=numero, texto=f"trecho {numero}")
        for numero in indices
    ]


class Espiao:
    """Substitui todas as etapas para o orquestrador rodar sem OpenAI nem Milvus."""

    def __init__(self, recuperados: list[int] | None = None, hipotetico: str | None = "hipotese"):
        self.recuperados = recuperados if recuperados is not None else list(range(0, 300, 10))
        self.hipotetico = hipotetico
        self.embutidos: list[list[str]] = []
        self.buscas: list[dict] = []
        self.reordenacoes: list[str] = []
        self.expansoes: list[dict] = []
        self.geracoes: list[dict] = []
        self.cliente = object()

    def gerar_hipotetico(self, pergunta, **_):
        return self.hipotetico, MetricaEtapa(EtapaPipeline.HYDE, 10)

    def embutir(self, textos):
        self.embutidos.append(textos)
        return ResultadoEmbedding(vetores=[[1.0, 3.0], [3.0, 5.0]][: len(textos)], tokens=9)

    def buscar(self, cliente, collection_name, document_id, query, vetor, *, limite, hibrido):
        self.buscas.append(
            {
                "collection": collection_name,
                "query": query,
                "vetor": vetor,
                "limite": limite,
                "hibrido": hibrido,
            }
        )
        return _candidatos(self.recuperados[:limite]), MetricaEtapa(EtapaPipeline.RETRIEVAL, 20)

    def buscar_parcelas(self, cliente, collection_name, document_id, query, vetor, *, limite):
        densos = _candidatos(self.recuperados[:2])
        densos[0].score_final = 0.9
        esparsos = _candidatos(self.recuperados[:1])
        esparsos[0].score_final = 7.5
        return densos, esparsos

    def reordenar(self, pergunta, candidatos):
        self.reordenacoes.append(pergunta)
        return list(reversed(candidatos)), MetricaEtapa(EtapaPipeline.RERANKING, 30)

    def expandir(self, cliente, collection_name, document_id, candidatos, *, tamanho):
        self.expansoes.append({"ancoras": list(candidatos), "tamanho": tamanho})
        vizinhos = [
            Candidato(
                milvus_id=900 + item.chunk_index + delta,
                chunk_index=item.chunk_index + delta,
                texto="vizinho",
                vizinho=True,
                origem="vizinho",
            )
            for item in candidatos
            for delta in (-1, 1)
        ]
        return [*candidatos, *vizinhos], MetricaEtapa(EtapaPipeline.WINDOW_EXPANSION, 40)

    def gerar(self, pergunta, candidatos):
        self.geracoes.append({"pergunta": pergunta, "contexto": candidatos})
        return "resposta", MetricaEtapa(EtapaPipeline.GENERATION, 50)

    def dependencias(self) -> DependenciasDeConsulta:
        return DependenciasDeConsulta(
            gerar_hipotetico=self.gerar_hipotetico,
            embutir=self.embutir,
            buscar=self.buscar,
            buscar_parcelas=self.buscar_parcelas,
            reordenar=self.reordenar,
            expandir=self.expandir,
            gerar=self.gerar,
            construir_cliente_milvus=lambda: self.cliente,
        )


def _executar(config: dict, espiao: Espiao):
    return executar_pipeline(
        _pipeline(config), DOCUMENTO, PERGUNTA, dependencias=espiao.dependencias()
    )


def _etapas(resposta) -> list[EtapaPipeline]:
    return [metrica.etapa for metrica in resposta.metricas]


def test_braco_de_controle_executa_exatamente_tres_etapas():
    resposta = _executar(CONFIG_CONTROLE, Espiao())

    assert _etapas(resposta) == [
        EtapaPipeline.EMBEDDING_QUERY,
        EtapaPipeline.RETRIEVAL,
        EtapaPipeline.GENERATION,
    ]


def test_braco_avancado_executa_as_seis_etapas_na_ordem():
    resposta = _executar(CONFIG_AVANCADA, Espiao())

    assert _etapas(resposta) == [
        EtapaPipeline.HYDE,
        EtapaPipeline.EMBEDDING_QUERY,
        EtapaPipeline.RETRIEVAL,
        EtapaPipeline.RERANKING,
        EtapaPipeline.WINDOW_EXPANSION,
        EtapaPipeline.GENERATION,
    ]


def test_controle_busca_e_entrega_exatamente_top_k():
    espiao = Espiao()

    resposta = _executar(CONFIG_CONTROLE, espiao)

    assert espiao.buscas[0]["limite"] == 15
    assert espiao.buscas[0]["hibrido"] is False
    assert len(resposta.chunks) == 15
    assert {item.origem for item in resposta.chunks} == {"busca"}


def test_hyde_faz_a_media_dos_vetores_e_mantem_a_pergunta_no_bm25():
    espiao = Espiao()

    _executar(CONFIG_AVANCADA, espiao)

    assert espiao.embutidos == [["hipotese", PERGUNTA]]
    assert espiao.buscas[0]["vetor"] == [2.0, 4.0]
    assert espiao.buscas[0]["query"] == PERGUNTA


def test_hipotetico_vazio_busca_so_com_a_pergunta():
    espiao = Espiao(hipotetico=None)

    _executar(CONFIG_AVANCADA, espiao)

    assert espiao.embutidos == [[PERGUNTA]]


def test_avancado_pede_candidatos_e_a_reordenacao_recebe_a_pergunta_original():
    espiao = Espiao()

    _executar(CONFIG_AVANCADA, espiao)

    assert espiao.buscas[0]["limite"] == 30
    assert espiao.reordenacoes == [PERGUNTA]
    assert espiao.geracoes[0]["pergunta"] == PERGUNTA


def test_janela_recebe_as_cinco_melhores_da_reordenacao_como_ancoras():
    espiao = Espiao()

    _executar(CONFIG_AVANCADA, espiao)

    expansao = espiao.expansoes[0]
    assert [item.chunk_index for item in expansao["ancoras"]] == [290, 280, 270, 260, 250]
    assert expansao["tamanho"] == 1
    assert {item.origem for item in expansao["ancoras"]} == {"ancora"}


def test_quinze_chunks_quando_ha_ancoras_e_vizinhos_sem_repeticao():
    resposta = _executar(CONFIG_AVANCADA, Espiao())

    assert len(resposta.chunks) == 15
    assert sum(item.origem == "ancora" for item in resposta.chunks) == 5
    assert sum(item.origem == "vizinho" for item in resposta.chunks) == 10


def test_completa_com_o_proximo_do_ranking_quando_faltam_vizinhos():
    espiao = Espiao()
    espiao.expandir = lambda c, n, d, ancoras, *, tamanho: (
        list(ancoras),
        MetricaEtapa(EtapaPipeline.WINDOW_EXPANSION, 1),
    )

    resposta = _executar(CONFIG_AVANCADA, espiao)

    assert len(resposta.chunks) == 15
    origens = [item.origem for item in resposta.chunks]
    assert origens.count("ancora") == 5
    assert origens.count("complemento") == 10
    indices = [item.chunk_index for item in resposta.chunks]
    assert len(set(indices)) == 15
    metrica = next(m for m in resposta.metricas if m.etapa is EtapaPipeline.WINDOW_EXPANSION)
    assert metrica.detalhes["complemento"] == 10
    assert metrica.detalhes["contexto_final"] == 15


def test_documento_pequeno_entrega_o_que_existe():
    resposta = _executar(CONFIG_AVANCADA, Espiao(recuperados=[1, 50]))

    assert len(resposta.chunks) == 6


def test_registra_cada_etapa_da_recuperacao_para_o_diagnostico():
    resposta = _executar(CONFIG_AVANCADA, Espiao())

    assert set(resposta.etapas) == {
        EtapaChunk.DENSO,
        EtapaChunk.ESPARSO,
        EtapaChunk.FUSAO,
        EtapaChunk.REORDENACAO,
        EtapaChunk.CONTEXTO_FINAL,
    }
    assert len(resposta.etapas[EtapaChunk.FUSAO]) == 30
    assert resposta.etapas[EtapaChunk.CONTEXTO_FINAL] == resposta.chunks


def test_fusao_recebe_as_parcelas_densa_e_esparsa():
    resposta = _executar(CONFIG_AVANCADA, Espiao())

    primeiro = resposta.etapas[EtapaChunk.FUSAO][0]
    assert primeiro.score_denso == 0.9
    assert primeiro.score_esparso == 7.5


def test_controle_so_registra_a_busca_densa_e_o_contexto():
    resposta = _executar(CONFIG_CONTROLE, Espiao())

    assert set(resposta.etapas) == {EtapaChunk.DENSO, EtapaChunk.CONTEXTO_FINAL}


def test_busca_na_collection_do_pipeline():
    espiao = Espiao()

    _executar(CONFIG_CONTROLE, espiao)

    assert espiao.buscas[0]["collection"] == "evaluation1"


def test_resposta_carrega_texto_e_contexto_entregue_ao_llm():
    espiao = Espiao()

    resposta = _executar(CONFIG_CONTROLE, espiao)

    assert resposta.texto == "resposta"
    assert espiao.geracoes[0]["contexto"] == resposta.chunks


def test_metrica_do_embedding_carrega_os_tokens():
    resposta = _executar(CONFIG_CONTROLE, Espiao())

    metrica = next(m for m in resposta.metricas if m.etapa is EtapaPipeline.EMBEDDING_QUERY)
    assert metrica.tokens_total == 9
    assert metrica.detalhes == {"textos": 1}
