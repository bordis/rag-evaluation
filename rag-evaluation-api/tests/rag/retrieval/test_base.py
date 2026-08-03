from app.core.milvus import CAMPO_CHUNK, CAMPO_TEXTO
from app.models.telemetry import EtapaPipeline
from app.rag.llm import RespostaLLM
from app.rag.retrieval.base import Candidato, MetricaEtapa, candidato_de_hit, metrica_de_llm


def test_hit_do_milvus_vira_candidato():
    hit = {
        "id": 457280976,
        "distance": 0.87,
        "entity": {CAMPO_CHUNK: 12, CAMPO_TEXTO: "Dado pessoal e informacao"},
    }
    candidato = candidato_de_hit(hit)
    assert candidato.chunk_index == 12
    assert candidato.texto == "Dado pessoal e informacao"
    assert candidato.score_final == 0.87


def test_candidato_nasce_sem_marca_de_vizinho():
    assert Candidato(milvus_id=1, chunk_index=0, texto="x").vizinho is False


def test_metrica_de_llm_carrega_tokens_e_modelo():
    resposta = RespostaLLM(
        texto="ok", tokens_prompt=10, tokens_completion=4, tokens_total=14, modelo="m-1"
    )
    metrica = metrica_de_llm(EtapaPipeline.QUERY_REWRITING, 250, resposta, {"original": "pergunta"})
    assert metrica.etapa is EtapaPipeline.QUERY_REWRITING
    assert metrica.duracao_ms == 250
    assert metrica.tokens_total == 14
    assert metrica.modelo == "m-1"
    assert metrica.detalhes == {"original": "pergunta"}


def test_metrica_sem_llm_nao_tem_tokens():
    metrica = MetricaEtapa(etapa=EtapaPipeline.RETRIEVAL, duracao_ms=30)
    assert metrica.tokens_total is None
    assert metrica.modelo is None
    assert metrica.detalhes == {}
