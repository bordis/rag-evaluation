import uuid

from pymilvus import AnnSearchRequest

from app.core.milvus import CAMPO_CHUNK, CAMPO_DENSO, CAMPO_DOCUMENTO, CAMPO_ESPARSO, CAMPO_TEXTO
from app.models.telemetry import EtapaPipeline
from app.rag.retrieval.search import buscar

DOCUMENTO = uuid.uuid4()
VETOR = [0.1, 0.2, 0.3]
QUERY = "consentimento do titular"


def _hits(quantidade: int) -> list[dict]:
    return [
        {
            "id": 1000 + numero,
            "distance": 0.9 - numero / 100,
            "entity": {CAMPO_CHUNK: numero, CAMPO_TEXTO: f"trecho {numero}"},
        }
        for numero in range(quantidade)
    ]


class ClienteFalso:
    def __init__(self, quantidade: int = 3) -> None:
        self.buscas: list[dict] = []
        self.hibridas: list[dict] = []
        self.quantidade = quantidade

    def search(self, **argumentos):
        self.buscas.append(argumentos)
        return [_hits(self.quantidade)]

    def hybrid_search(self, **argumentos):
        self.hibridas.append(argumentos)
        return [_hits(self.quantidade)]


def test_busca_densa_usa_search_e_nao_hybrid_search():
    cliente = ClienteFalso()
    buscar(cliente, "evaluation1", DOCUMENTO, QUERY, VETOR, limite=5, hibrido=False)
    assert len(cliente.buscas) == 1
    assert cliente.hibridas == []
    assert cliente.buscas[0]["anns_field"] == CAMPO_DENSO
    assert cliente.buscas[0]["data"] == [VETOR]
    assert cliente.buscas[0]["limit"] == 5


def test_busca_densa_filtra_pelo_documento():
    cliente = ClienteFalso()
    buscar(cliente, "evaluation1", DOCUMENTO, QUERY, VETOR, limite=5, hibrido=False)
    assert cliente.buscas[0]["filter"] == f'{CAMPO_DOCUMENTO} == "{DOCUMENTO}"'


def test_busca_hibrida_usa_hybrid_search_e_nao_search():
    cliente = ClienteFalso()
    buscar(cliente, "evaluation3", DOCUMENTO, QUERY, VETOR, limite=20, hibrido=True)
    assert len(cliente.hibridas) == 1
    assert cliente.buscas == []
    assert cliente.hibridas[0]["collection_name"] == "evaluation3"
    assert cliente.hibridas[0]["limit"] == 20


def test_busca_hibrida_manda_vetor_no_denso_e_texto_cru_no_esparso():
    """O BM25 e uma Function do servidor: ele recebe texto, nao vetor."""
    cliente = ClienteFalso()
    buscar(cliente, "evaluation3", DOCUMENTO, QUERY, VETOR, limite=20, hibrido=True)
    pedidos = cliente.hibridas[0]["reqs"]
    assert len(pedidos) == 2
    assert all(isinstance(pedido, AnnSearchRequest) for pedido in pedidos)
    assert pedidos[0].anns_field == CAMPO_DENSO
    assert pedidos[0].data == [VETOR]
    assert pedidos[1].anns_field == CAMPO_ESPARSO
    assert pedidos[1].data == [QUERY]


def test_busca_hibrida_funde_com_rrf():
    cliente = ClienteFalso()
    buscar(cliente, "evaluation3", DOCUMENTO, QUERY, VETOR, limite=20, hibrido=True)
    assert type(cliente.hibridas[0]["ranker"]).__name__ == "RRFRanker"


def test_hits_viram_candidatos_ordenados():
    cliente = ClienteFalso(quantidade=3)
    candidatos, _ = buscar(cliente, "evaluation1", DOCUMENTO, QUERY, VETOR, limite=5, hibrido=False)
    assert [candidato.chunk_index for candidato in candidatos] == [0, 1, 2]
    assert candidatos[0].texto == "trecho 0"
    assert candidatos[0].score_final == 0.9


def test_busca_densa_preenche_o_score_denso():
    cliente = ClienteFalso(quantidade=1)
    candidatos, _ = buscar(cliente, "evaluation1", DOCUMENTO, QUERY, VETOR, limite=5, hibrido=False)
    assert candidatos[0].score_denso == candidatos[0].score_final
    assert candidatos[0].score_esparso is None


def test_busca_hibrida_deixa_os_scores_individuais_nulos():
    """O RRF devolve so o score fundido; separar exigiria duas buscas e fusao manual."""
    cliente = ClienteFalso(quantidade=1)
    candidatos, _ = buscar(cliente, "evaluation3", DOCUMENTO, QUERY, VETOR, limite=20, hibrido=True)
    assert candidatos[0].score_denso is None
    assert candidatos[0].score_esparso is None
    assert candidatos[0].score_final == 0.9


def test_metrica_registra_o_modo_e_o_que_foi_recuperado():
    cliente = ClienteFalso(quantidade=3)
    _, metrica = buscar(cliente, "evaluation1", DOCUMENTO, QUERY, VETOR, limite=5, hibrido=False)
    assert metrica.etapa is EtapaPipeline.RETRIEVAL
    assert metrica.detalhes == {"modo": "denso", "limite": 5, "recuperados": 3}
    assert metrica.tokens_total is None


def test_metrica_da_busca_hibrida_registra_o_ranker():
    cliente = ClienteFalso(quantidade=2)
    _, metrica = buscar(cliente, "evaluation4", DOCUMENTO, QUERY, VETOR, limite=20, hibrido=True)
    assert metrica.detalhes == {
        "modo": "hibrido",
        "limite": 20,
        "recuperados": 2,
        "ranker": "rrf",
    }
