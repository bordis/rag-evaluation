"""Fracao do documento que vai ao LLM: conta pura, sem banco."""

from app.models.document import StatusIngestao
from app.services.contexto_llm import (
    IngestaoDoContexto,
    contexto_da_ingestao,
    resumir_contexto,
    top_k_do_pipeline,
)


def _ingestao(**substituicoes) -> IngestaoDoContexto:
    campos = {
        "status": StatusIngestao.CONCLUIDA,
        "total_chunks": 80,
        "tokens_embedding": 19_200,
        "top_k": 6,
        "chunk_size": 256,
    }
    campos.update(substituicoes)
    return IngestaoDoContexto(**campos)


def test_fracao_e_tokens_pela_media_do_proprio_documento():
    contexto = contexto_da_ingestao(_ingestao())

    assert contexto.chunks == 6
    assert contexto.percentual == 7.5
    assert contexto.tokens_estimados == 1440


def test_percentual_com_uma_casa_decimal():
    assert contexto_da_ingestao(_ingestao(total_chunks=64)).percentual == 9.4


def test_top_k_maior_que_o_documento_entrega_o_documento_inteiro():
    contexto = contexto_da_ingestao(_ingestao(top_k=15, total_chunks=4, tokens_embedding=900))

    assert contexto.chunks == 4
    assert contexto.percentual == 100.0
    assert contexto.tokens_estimados == 900


def test_sem_tokens_de_embedding_estima_pelo_tamanho_do_chunk():
    contexto = contexto_da_ingestao(_ingestao(tokens_embedding=0, chunk_size=256))

    assert contexto.tokens_estimados == 6 * 256


def test_ingestao_nao_concluida_nao_tem_fracao():
    for status in (StatusIngestao.ERRO, StatusIngestao.PENDENTE, StatusIngestao.PROCESSANDO):
        contexto = contexto_da_ingestao(_ingestao(status=status))
        assert contexto.chunks == 0
        assert contexto.percentual is None


def test_concluida_sem_chunks_nao_tem_fracao():
    assert contexto_da_ingestao(_ingestao(total_chunks=0)).percentual is None


def test_faixa_entre_pipelines_com_parsers_de_contagens_diferentes():
    resumo = resumir_contexto(
        [
            _ingestao(total_chunks=85, tokens_embedding=20_400),  # raw: 7,1%, 1440 tokens
            _ingestao(total_chunks=64, tokens_embedding=14_080),  # docling: 9,4%, 1320 tokens
        ]
    )

    assert resumo is not None
    assert resumo.chunks == 6
    assert resumo.percentual_min == 7.1
    assert resumo.percentual_max == 9.4
    assert resumo.tokens_estimados == 1380


def test_ingestao_em_erro_fica_fora_da_faixa():
    resumo = resumir_contexto(
        [_ingestao(total_chunks=60), _ingestao(status=StatusIngestao.ERRO, total_chunks=10)]
    )

    assert resumo is not None
    assert resumo.percentual_min == resumo.percentual_max == 10.0


def test_chunks_e_o_maior_entre_os_pipelines():
    resumo = resumir_contexto([_ingestao(total_chunks=3), _ingestao(total_chunks=50)])

    assert resumo is not None
    assert resumo.chunks == 6
    assert resumo.percentual_max == 100.0


def test_nenhuma_concluida_da_none():
    assert resumir_contexto([]) is None
    assert resumir_contexto([_ingestao(status=StatusIngestao.ERRO)]) is None
    assert resumir_contexto([_ingestao(total_chunks=0)]) is None


def test_top_k_da_config_vence_o_env():
    from app.core.config import get_settings

    assert top_k_do_pipeline({"top_k": 9}) == 9
    assert top_k_do_pipeline({}) == get_settings().rag_search_limit
