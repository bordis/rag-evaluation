"""Estudos, CRUD dos pipelines e a visao do pesquisador, de ponta a ponta na API."""

import uuid
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.models.document import Document, StatusDocumento
from app.models.pipeline import Pipeline
from app.models.telemetry import EtapaChunk, RagasScore, RetrievedChunk
from app.rag.pipeline import RespostaDePipeline
from app.rag.retrieval.base import Candidato
from app.seed import semear_pipelines
from app.services import evaluation as servico
from app.services.ragas_rodadas import _estudos_em_calculo, calcular_notas, reservar_calculo
from tests.fakes import PipelineFalso, dependencias_falsas


class PipelineComEtapas(PipelineFalso):
    def __call__(self, pipeline, document_id, pergunta, *, cliente_milvus=None):
        base = super().__call__(pipeline, document_id, pergunta, cliente_milvus=cliente_milvus)
        densos = [Candidato(milvus_id=9, chunk_index=9, texto="so na busca", score_final=0.1)]
        return RespostaDePipeline(
            texto=base.texto,
            metricas=base.metricas,
            chunks=base.chunks,
            etapas={EtapaChunk.DENSO: densos, EtapaChunk.CONTEXTO_FINAL: base.chunks},
        )


@pytest.fixture(autouse=True)
def preparar(sessao: Session, monkeypatch):
    semear_pipelines(sessao)
    monkeypatch.setattr("app.services.studies.reordenador_no_ar", lambda: True)

    async def criar(sessao, session_id, document_id, pergunta):
        return await servico.criar_rodada(
            sessao,
            session_id,
            document_id,
            pergunta,
            dependencias=dependencias_falsas(PipelineComEtapas()),
        )

    monkeypatch.setattr("app.api.routers.evaluation.criar_rodada", criar)


@pytest.fixture(name="documento")
def documento_fixture(sessao: Session) -> Document:
    documento = Document(
        slug="lgpd",
        titulo="LGPD",
        area="Direito",
        nome_arquivo_original="lgpd.pdf",
        mime_type="application/pdf",
        tamanho_bytes=10,
        sha256="c" * 64,
        status=StatusDocumento.PRONTO,
    )
    sessao.add(documento)
    sessao.commit()
    sessao.refresh(documento)
    return documento


def _abrir(cliente, nome: str = "Piloto") -> dict:
    resposta = cliente.post("/api/studies", json={"nome": nome})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _rodada_decidida(cliente, documento, rotulo: str | None = "A") -> tuple[str, dict]:
    sessao_id = cliente.post("/api/sessions", json={"aceite": True, "termo_versao": "v1"}).json()[
        "id"
    ]
    rodada = cliente.post(
        f"/api/sessions/{sessao_id}/documents/{documento.slug}/questions",
        json={"pergunta": "O que a lei diz?"},
    ).json()
    cliente.post(f"/api/rounds/{rodada['id']}/choice", json={"rotulo": rotulo})
    return sessao_id, rodada


# Estudos


def test_um_estudo_aberto_por_vez(cliente):
    _abrir(cliente)

    assert cliente.post("/api/studies", json={"nome": "Outro"}).status_code == 409


def test_nao_abre_com_o_reordenador_fora_do_ar(cliente, monkeypatch):
    monkeypatch.setattr("app.services.studies.reordenador_no_ar", lambda: False)

    resposta = cliente.post("/api/studies", json={"nome": "Piloto"})

    assert resposta.status_code == 409
    assert "rag-reranker" in resposta.json()["detail"]


def test_novo_estudo_comeca_zerado(cliente, documento):
    estudo = _abrir(cliente)
    _rodada_decidida(cliente, documento)
    assert cliente.get("/api/studies/atual").json()["rodadas_decididas"] == 1

    assert cliente.post(f"/api/studies/{estudo['id']}/encerrar").status_code == 200
    assert cliente.get("/api/studies/atual").json() is None
    novo = _abrir(cliente, "Coleta")

    assert novo["rodadas_decididas"] == 0
    assert novo["sessoes"] == 0
    antigo = next(i for i in cliente.get("/api/studies").json() if i["id"] == estudo["id"])
    assert antigo["rodadas_decididas"] == 1
    assert antigo["status"] == "encerrado"


def test_encerrar_duas_vezes_responde_409(cliente):
    estudo = _abrir(cliente)
    cliente.post(f"/api/studies/{estudo['id']}/encerrar")

    assert cliente.post(f"/api/studies/{estudo['id']}/encerrar").status_code == 409


# Pipelines


def _pipeline(sessao: Session, codigo: str) -> Pipeline:
    return sessao.exec(select(Pipeline).where(Pipeline.codigo == codigo)).one()


def test_lista_identifica_o_braco_de_controle(cliente):
    corpo = cliente.get("/api/pipelines").json()

    assert [item["controle"] for item in corpo] == [True, True, False, False]


def test_controle_nao_liga_recuperacao_avancada(cliente, sessao):
    pipeline = _pipeline(sessao, "pipeline-1")
    config = {**pipeline.config, "hyde": True}

    resposta = cliente.put(f"/api/pipelines/{pipeline.id}", json={"config": config})

    assert resposta.status_code == 422


def test_controle_tambem_nao_liga_a_janela(cliente, sessao):
    pipeline = _pipeline(sessao, "pipeline-2")
    config = {**pipeline.config, "sliding_window": {"ativo": True, "tamanho": 1}}

    assert cliente.put(f"/api/pipelines/{pipeline.id}", json={"config": config}).status_code == 422


def test_edita_o_pipeline_avancado_sem_estudo_aberto(cliente, sessao):
    pipeline = _pipeline(sessao, "pipeline-3")
    config = {**pipeline.config, "top_k": 12}

    resposta = cliente.put(
        f"/api/pipelines/{pipeline.id}", json={"config": config, "nome": "Novo nome"}
    )

    assert resposta.status_code == 200
    assert resposta.json()["config"]["top_k"] == 12
    assert resposta.json()["nome"] == "Novo nome"


def test_estudo_aberto_trava_os_pipelines(cliente, sessao):
    _abrir(cliente)
    pipeline = _pipeline(sessao, "pipeline-3")

    assert cliente.put(f"/api/pipelines/{pipeline.id}", json={"nome": "X y"}).status_code == 409
    assert cliente.delete(f"/api/pipelines/{pipeline.id}").status_code == 409


def test_criar_nasce_inativo_e_nao_passa_do_limite_do_desenho(cliente, monkeypatch):
    monkeypatch.setattr("app.api.routers.pipelines.construir_cliente", lambda: object())
    monkeypatch.setattr("app.api.routers.pipelines.garantir_collection", lambda *_: None)

    criado = cliente.post(
        "/api/pipelines",
        json={
            "codigo": "pipeline-5",
            "nome": "Quinto",
            "parser": "raw",
            "collection_name": "evaluation5",
            "config": {"top_k": 15},
        },
    )

    assert criado.status_code == 201
    assert criado.json()["ativo"] is False
    ativar = cliente.put(f"/api/pipelines/{criado.json()['id']}", json={"ativo": True})
    assert ativar.status_code == 409


def test_nao_exclui_pipeline_com_respostas(cliente, sessao, documento):
    estudo = _abrir(cliente)
    _rodada_decidida(cliente, documento)
    cliente.post(f"/api/studies/{estudo['id']}/encerrar")
    pipeline = _pipeline(sessao, "pipeline-1")

    assert cliente.delete(f"/api/pipelines/{pipeline.id}").status_code == 409


def test_config_gravada_na_resposta_nao_muda_com_edicao_posterior(cliente, sessao, documento):
    estudo = _abrir(cliente)
    sessao_id, _ = _rodada_decidida(cliente, documento)
    cliente.post(f"/api/studies/{estudo['id']}/encerrar")
    pipeline = _pipeline(sessao, "pipeline-3")
    cliente.put(f"/api/pipelines/{pipeline.id}", json={"config": {**pipeline.config, "top_k": 1}})

    detalhe = cliente.get(f"/api/admin/avaliacoes/{sessao_id}/{documento.id}").json()

    resposta = next(
        item
        for item in detalhe["rodadas"][0]["respostas"]
        if item["pipeline_codigo"] == "pipeline-3"
    )
    assert resposta["config_snapshot"]["top_k"] == 15


# Visao do pesquisador


def test_detalhe_revela_pipeline_escolha_e_chunks_por_etapa(cliente, documento):
    estudo = _abrir(cliente)
    sessao_id, _ = _rodada_decidida(cliente, documento, "B")

    lista = cliente.get(f"/api/admin/studies/{estudo['id']}/avaliacoes").json()
    assert lista[0]["session_id"] == sessao_id
    assert lista[0]["decididas"] == 1

    detalhe = cliente.get(f"/api/admin/avaliacoes/{sessao_id}/{documento.id}").json()
    respostas = detalhe["rodadas"][0]["respostas"]
    assert {item["pipeline_codigo"] for item in respostas} == {
        "pipeline-1",
        "pipeline-2",
        "pipeline-3",
        "pipeline-4",
    }
    assert [item["rotulo"] for item in respostas if item["escolhida"]] == ["B"]
    etapas = {chunk["etapa"] for chunk in respostas[0]["chunks"]}
    assert etapas == {"denso", "contexto_final"}
    contexto = [c for c in respostas[0]["chunks"] if c["etapa"] == "contexto_final"]
    assert [(c["posicao"], c["score_final"], c["texto"]) for c in contexto] == [
        (1, 0.9, "trecho um"),
        (2, 0.5, "trecho dois"),
    ]
    assert respostas[0]["metricas"][1]["custo_usd"] is not None


def test_avaliacao_inexistente_responde_404(cliente):
    assert cliente.get(f"/api/admin/avaliacoes/{uuid.uuid4()}/{uuid.uuid4()}").status_code == 404


def test_estatisticas_e_csv_do_estudo(cliente, documento):
    estudo = _abrir(cliente)
    _rodada_decidida(cliente, documento, "A")
    _rodada_decidida(cliente, documento, None)

    stats = cliente.get(f"/api/admin/studies/{estudo['id']}/stats").json()
    assert stats["rodadas_decididas"] == 2
    assert stats["avaliadores"] == 2
    assert stats["nenhuma"]["sucessos"] == 1
    assert [item["efeito"] for item in stats["efeitos"]] == [
        "ingestao",
        "recuperacao",
        "interacao",
    ]
    assert stats["custo"]["por_pipeline"][0]["respostas"] == 2

    csv = cliente.get(f"/api/admin/studies/{estudo['id']}/export.csv")
    assert csv.headers["content-type"].startswith("text/csv")
    linhas = csv.text.strip().splitlines()
    assert linhas[0].startswith("rodada,avaliador,documento,ordem,pipeline")
    assert len(linhas) == 1 + 8


def test_nao_exclui_documento_com_rodadas(cliente, documento):
    _abrir(cliente)
    _rodada_decidida(cliente, documento)

    assert cliente.delete(f"/api/documents/{documento.id}").status_code == 409


# RAGAS


async def test_ragas_grava_notas_com_o_contexto_final_e_repete_so_o_que_falhou(
    cliente, sessao, documento
):
    _abrir(cliente)
    _rodada_decidida(cliente, documento)
    rodada = sessao.exec(select(servico.QuestionRound)).one()
    contextos: list[list[str]] = []
    falhas = [RuntimeError("juiz fora")]

    async def avaliar(pergunta, resposta, ctx):
        contextos.append(ctx)
        if falhas:
            raise falhas.pop()
        return SimpleNamespace(fidelidade=1.0, relevancia_resposta=0.5, precisao_contexto=0.0)

    await calcular_notas(sessao, [rodada], avaliar=avaliar)

    notas = sessao.exec(select(RagasScore)).all()
    assert len(notas) == 4
    assert sum(item.erro is not None for item in notas) == 1
    assert {tuple(item) for item in contextos} == {("trecho um", "trecho dois")}
    valida = next(item for item in notas if item.erro is None)
    assert valida.media == pytest.approx(0.5)

    contextos.clear()
    await calcular_notas(sessao, [rodada], avaliar=avaliar)
    assert len(contextos) == 1
    sessao.expire_all()
    assert all(item.erro is None for item in sessao.exec(select(RagasScore)).all())


def test_situacao_do_ragas_conta_notas_e_erros(cliente, sessao, documento):
    estudo = _abrir(cliente)
    _rodada_decidida(cliente, documento)
    respostas = sessao.exec(select(servico.PipelineAnswer)).all()
    sessao.add(RagasScore(answer_id=respostas[0].id, modelo="m", media=0.5))
    sessao.add(RagasScore(answer_id=respostas[1].id, modelo="m", erro="ValueError: falhou"))
    sessao.commit()

    situacao = cliente.get(f"/api/admin/studies/{estudo['id']}/ragas").json()

    assert situacao == {
        "em_andamento": False,
        "total": 4,
        "avaliadas": 1,
        "com_erro": 1,
        "ultimo_erro": "ValueError: falhou",
    }


def test_nao_dispara_segundo_lote_de_ragas_com_um_em_andamento(cliente, documento):
    estudo = _abrir(cliente)
    _rodada_decidida(cliente, documento)
    study_id = uuid.UUID(estudo["id"])
    assert reservar_calculo(study_id) is True
    try:
        resposta = cliente.post(f"/api/admin/studies/{study_id}/ragas").json()
        situacao = cliente.get(f"/api/admin/studies/{study_id}/ragas").json()
    finally:
        _estudos_em_calculo.discard(study_id)

    assert "em andamento" in resposta["mensagem"]
    assert situacao["em_andamento"] is True


def test_chunks_ficam_gravados_com_a_etapa(cliente, sessao, documento):
    _abrir(cliente)
    _rodada_decidida(cliente, documento)

    etapas = {item.etapa for item in sessao.exec(select(RetrievedChunk)).all()}

    assert etapas == {EtapaChunk.DENSO, EtapaChunk.CONTEXTO_FINAL}
