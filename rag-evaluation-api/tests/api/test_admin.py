"""Estudos, CRUD dos pipelines e a visao do pesquisador, de ponta a ponta na API."""

import csv
import io
import uuid
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.models.document import Document, StatusDocumento
from app.models.evaluation import PipelineAnswer, QuestionRound, RoundFailure
from app.models.pipeline import Pipeline
from app.models.study import Study
from app.models.telemetry import EtapaChunk, RagasScore, RetrievedChunk
from app.rag.pipeline import RespostaDePipeline
from app.rag.retrieval.base import Candidato
from app.seed import semear_pipelines
from app.services import evaluation as servico
from app.services.ragas_rodadas import _estudos_em_calculo, calcular_notas, reservar_calculo
from tests.conftest import entrar_como
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


def _rodada_decidida(
    cliente, documento, rotulo: str | None = "A", marcar: list[str] | None = None, **tempos
) -> tuple[str, dict]:
    """Cada chamada e um avaliador novo, com login proprio. `marcar` faz o segundo passo."""
    entrar_como(f"avaliador-{uuid.uuid4()}")
    sessao_id = cliente.post("/api/sessions", json={"aceite": True, "termo_versao": "v1"}).json()[
        "id"
    ]
    rodada = cliente.post(
        f"/api/sessions/{sessao_id}/documents/{documento.slug}/questions",
        json={"pergunta": "O que a lei diz?"},
    ).json()
    cliente.post(f"/api/rounds/{rodada['id']}/choice", json={"rotulo": rotulo})
    if marcar is not None:
        marcacao = cliente.post(
            f"/api/rounds/{rodada['id']}/also-correct", json={"rotulos": marcar, **tempos}
        )
        assert marcacao.status_code == 200, marcacao.text
    return sessao_id, rodada


# Estudos


def test_um_estudo_aberto_por_vez(cliente):
    _abrir(cliente)

    assert cliente.post("/api/studies", json={"nome": "Outro"}).status_code == 409


def test_nao_abre_com_o_reordenador_fora_do_ar(cliente, monkeypatch):
    monkeypatch.setattr("app.services.studies.reordenador_no_ar", lambda: False)

    resposta = cliente.post("/api/studies", json={"nome": "Piloto"})

    assert resposta.status_code == 409
    assert "reordenador" in resposta.json()["detail"]


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
    assert "custo_usd" not in respostas[0]["metricas"][1]


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


def test_detalhe_mostra_a_marcacao_das_outras_respostas(cliente, documento):
    _abrir(cliente)
    sessao_id, _ = _rodada_decidida(
        cliente,
        documento,
        "A",
        marcar=["C"],
        tempo_marcacao_ms=4000,
        tempo_marcacao_oculto_ms=100,
    )

    rodada = cliente.get(f"/api/admin/avaliacoes/{sessao_id}/{documento.id}").json()["rodadas"][0]

    assert rodada["marcado_em"] is not None
    assert rodada["tempo_marcacao_ms"] == 4000
    assert rodada["tempo_marcacao_oculto_ms"] == 100
    assert {item["rotulo"]: item["tambem_correta"] for item in rodada["respostas"]} == {
        "A": None,
        "B": False,
        "C": True,
        "D": False,
    }


def test_detalhe_de_rodada_sem_marcacao_deixa_os_campos_nulos(cliente, documento):
    _abrir(cliente)
    sessao_id, _ = _rodada_decidida(cliente, documento, "A")

    rodada = cliente.get(f"/api/admin/avaliacoes/{sessao_id}/{documento.id}").json()["rodadas"][0]

    assert rodada["marcado_em"] is None
    assert rodada["tempo_marcacao_ms"] is None
    assert all(item["tambem_correta"] is None for item in rodada["respostas"])


def test_csv_traz_a_marcacao_e_a_correcao_no_fim_do_cabecalho(cliente, documento):
    estudo = _abrir(cliente)
    _, marcada = _rodada_decidida(cliente, documento, "A", marcar=["B"], tempo_marcacao_ms=3000)
    _, nenhuma = _rodada_decidida(cliente, documento, None)
    _, sem_marcacao = _rodada_decidida(cliente, documento, "D")

    texto = cliente.get(f"/api/admin/studies/{estudo['id']}/export.csv").text
    linhas = list(csv.DictReader(io.StringIO(texto)))
    cabecalho = texto.splitlines()[0].split(",")

    assert cabecalho[:2] == ["rodada", "avaliador"]
    assert cabecalho[-6:] == [
        "pergunta",
        "tambem_correta",
        "correta",
        "marcado_em",
        "tempo_marcacao_ms",
        "tempo_marcacao_oculto_ms",
    ]

    def por_rotulo(rodada: dict) -> dict[str, dict]:
        return {linha["rotulo"]: linha for linha in linhas if linha["rodada"] == rodada["id"]}

    m = por_rotulo(marcada)
    assert [m[r]["correta"] for r in "ABCD"] == ["1", "1", "0", "0"]
    assert [m[r]["tambem_correta"] for r in "ABCD"] == ["", "1", "0", "0"]
    assert m["A"]["tempo_marcacao_ms"] == "3000"
    assert m["A"]["marcado_em"]
    n = por_rotulo(nenhuma)
    assert [n[r]["correta"] for r in "ABCD"] == ["0", "0", "0", "0"]
    assert n["A"]["marcado_em"] == ""
    s = por_rotulo(sem_marcacao)
    assert [s[r]["correta"] for r in "ABCD"] == ["", "", "", ""]
    assert [s[r]["tambem_correta"] for r in "ABCD"] == ["", "", "", ""]


def test_estatisticas_trazem_a_taxa_de_correcao(cliente, documento):
    estudo = _abrir(cliente)
    _rodada_decidida(cliente, documento, "A", marcar=["B", "C", "D"], tempo_marcacao_ms=2000)
    _rodada_decidida(cliente, documento, None)
    _rodada_decidida(cliente, documento, "B")

    stats = cliente.get(f"/api/admin/studies/{estudo['id']}/stats").json()

    correcao = stats["taxa_correcao"]
    assert correcao["rodadas_completas"] == 2
    assert correcao["decididas_sem_marcacao"] == 1
    assert [item["total"] for item in correcao["por_pipeline"]] == [2, 2, 2, 2]
    assert [item["sucessos"] for item in correcao["por_pipeline"]] == [1, 1, 1, 1]
    assert stats["marcacao_por_posicao"]["respostas"] == 3
    assert stats["marcacao_por_avaliador"][0]["todas_marcadas"] == 1
    assert stats["rodadas_decididas"] == 3
    assert "tempo_marcacao_ativo_mediano_ms" in stats["por_ordem"][0]


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


def test_estudo_congela_modelos_prompts_e_pipelines(cliente, sessao):
    estudo = _abrir(cliente)

    registro = sessao.get(Study, uuid.UUID(estudo["id"]))

    assert registro.config_snapshot["geracao"]["prompt"]
    assert "precos_por_milhao_de_tokens" not in registro.config_snapshot
    assert set(registro.config_snapshot["pipelines"]) == {
        f"pipeline-{numero}" for numero in (1, 2, 3, 4)
    }


def test_rodada_grava_as_medidas_da_coleta_e_elas_chegam_ao_csv(cliente, sessao, documento):
    estudo = _abrir(cliente)
    sessao_id = cliente.post("/api/sessions", json={"aceite": True, "termo_versao": "v1"}).json()[
        "id"
    ]
    rodada = cliente.post(
        f"/api/sessions/{sessao_id}/documents/{documento.slug}/questions",
        json={"pergunta": "Qual o prazo?"},
    ).json()

    cliente.post(
        f"/api/rounds/{rodada['id']}/choice",
        json={
            "rotulo": "A",
            "tempo_total_ms": 60000,
            "tempo_pergunta_ms": 8000,
            "respostas_vistas": 4,
            "recarregamentos": 1,
            "largura_tela": 390,
        },
    )

    registro = sessao.get(QuestionRound, uuid.UUID(rodada["id"]))
    assert registro.tempo_pergunta_ms == 8000
    assert registro.respostas_vistas == 4
    assert registro.ordem_na_sessao == 1
    assert registro.rodadas_simultaneas == 1
    csv_texto = cliente.get(f"/api/admin/studies/{estudo['id']}/export.csv").text
    assert "tempo_pergunta_ms" in csv_texto.splitlines()[0]
    estatisticas = cliente.get(f"/api/admin/studies/{estudo['id']}/stats").json()
    assert estatisticas["coleta"]["viu_todas"]["sucessos"] == 1
    assert estatisticas["ambiente"]["geracao"]["modelo"]


def test_mais_de_quatro_respostas_vistas_e_recusado(cliente, documento):
    _, rodada = _rodada_pendente(cliente, documento)

    resposta = cliente.post(
        f"/api/rounds/{rodada['id']}/choice", json={"rotulo": "A", "respostas_vistas": 5}
    )

    assert resposta.status_code == 422


def _rodada_pendente(cliente, documento) -> tuple[dict, dict]:
    estudo = _abrir(cliente)
    sessao_id = cliente.post("/api/sessions", json={"aceite": True, "termo_versao": "v1"}).json()[
        "id"
    ]
    rodada = cliente.post(
        f"/api/sessions/{sessao_id}/documents/{documento.slug}/questions",
        json={"pergunta": "Qual o prazo?"},
    ).json()
    return estudo, rodada


def test_falha_de_rodada_fica_registrada_e_aparece_nas_estatisticas(
    cliente, sessao, documento, monkeypatch
):
    async def falhar(sessao, session_id, document_id, pergunta):
        raise servico.ErroDeRodada("RuntimeError: openai fora do ar")

    monkeypatch.setattr("app.api.routers.evaluation.criar_rodada", falhar)
    estudo = _abrir(cliente)
    sessao_id = cliente.post("/api/sessions", json={"aceite": True, "termo_versao": "v1"}).json()[
        "id"
    ]

    resposta = cliente.post(
        f"/api/sessions/{sessao_id}/documents/{documento.slug}/questions",
        json={"pergunta": "Qual o prazo?"},
    )

    assert resposta.status_code == 502
    falha = sessao.exec(select(RoundFailure)).one()
    assert falha.pergunta == "Qual o prazo?"
    estatisticas = cliente.get(f"/api/admin/studies/{estudo['id']}/stats").json()
    assert estatisticas["coleta"]["falhas_de_rodada"] == 1


def test_anotacao_de_erro_entra_nas_causas_confirmadas_e_pode_ser_refeita(
    cliente, sessao, documento
):
    estudo = _abrir(cliente)
    sessao_id = cliente.post("/api/sessions", json={"aceite": True, "termo_versao": "v1"}).json()[
        "id"
    ]
    rodada = cliente.post(
        f"/api/sessions/{sessao_id}/documents/{documento.slug}/questions",
        json={"pergunta": "Qual o prazo?"},
    ).json()
    cliente.post(f"/api/rounds/{rodada['id']}/choice", json={"rotulo": None})
    resposta_id = sessao.exec(
        select(PipelineAnswer.id).where(PipelineAnswer.round_id == uuid.UUID(rodada["id"]))
    ).first()

    url = f"/api/admin/answers/{resposta_id}/anotacao"
    assert cliente.put(url, json={"causa": "geracao"}).status_code == 200
    assert cliente.put(url, json={"causa": "conversao", "nota": "tabela"}).status_code == 200

    erros = cliente.get(f"/api/admin/studies/{estudo['id']}/stats").json()["erros"]
    causas = [item["causas"] for item in erros["causas_confirmadas"] if item["causas"]]
    assert causas == [{"conversao": 1}]

    assert cliente.delete(url).status_code == 204
    erros = cliente.get(f"/api/admin/studies/{estudo['id']}/stats").json()["erros"]
    assert all(not item["causas"] for item in erros["causas_confirmadas"])


def test_anotar_resposta_inexistente_responde_404(cliente):
    resposta = cliente.put(f"/api/admin/answers/{uuid.uuid4()}/anotacao", json={"causa": "outra"})

    assert resposta.status_code == 404


def test_causa_desconhecida_e_recusada(cliente):
    resposta = cliente.put(f"/api/admin/answers/{uuid.uuid4()}/anotacao", json={"causa": "x"})

    assert resposta.status_code == 422
