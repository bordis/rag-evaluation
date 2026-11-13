import uuid

import pytest
from sqlmodel import Session, select

from app.models.document import Document, StatusDocumento
from app.models.evaluation import EvaluationSession, PipelineAnswer, QuestionRound
from app.models.pipeline import Pipeline
from app.models.study import StatusEstudo, Study
from app.seed import semear_pipelines
from app.services import evaluation as servico
from tests.conftest import entrar_como
from tests.fakes import PipelineFalso, dependencias_falsas


@pytest.fixture(name="pipelines", autouse=True)
def pipelines_fixture(sessao: Session):
    semear_pipelines(sessao)


@pytest.fixture(name="rodada_falsa", autouse=True)
def rodada_falsa_fixture(monkeypatch):
    """Troca a geracao real por pipelines falsos — os testes de contrato nao chamam a OpenAI."""

    async def criar(sessao, session_id, document_id, pergunta):
        return await servico.criar_rodada(
            sessao,
            session_id,
            document_id,
            pergunta,
            dependencias=dependencias_falsas(PipelineFalso()),
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
        sha256="b" * 64,
        status=StatusDocumento.PRONTO,
    )
    sessao.add(documento)
    sessao.commit()
    sessao.refresh(documento)
    return documento


@pytest.fixture(name="estudo", autouse=True)
def estudo_fixture(sessao: Session) -> Study:
    estudo = Study(nome="Coleta")
    sessao.add(estudo)
    sessao.commit()
    sessao.refresh(estudo)
    return estudo


def _encerrar(sessao: Session, estudo: Study) -> None:
    estudo.status = StatusEstudo.ENCERRADO
    sessao.add(estudo)
    sessao.commit()


def _criar_sessao(cliente) -> str:
    resposta = cliente.post("/api/sessions", json={"aceite": True, "termo_versao": "v1"})
    assert resposta.status_code == 201
    return resposta.json()["id"]


def _perguntar(cliente, session_id: str, slug: str, pergunta: str = "O que a lei diz?"):
    return cliente.post(
        f"/api/sessions/{session_id}/documents/{slug}/questions", json={"pergunta": pergunta}
    )


def _marcar(cliente, round_id: str, rotulos: list[str] | None = None, **tempos):
    return cliente.post(
        f"/api/rounds/{round_id}/also-correct",
        json={"rotulos": rotulos if rotulos is not None else [], **tempos},
    )


def _concluir(cliente, round_id: str, rotulo: str | None = "A") -> None:
    """Os dois passos da rodada: escolha e, havendo vencedora, a marcacao das outras."""
    escolha = cliente.post(f"/api/rounds/{round_id}/choice", json={"rotulo": rotulo})
    assert escolha.status_code == 200
    if rotulo is not None:
        assert _marcar(cliente, round_id).status_code == 200


def _chaves(dado, encontradas: set[str] | None = None) -> set[str]:
    encontradas = encontradas if encontradas is not None else set()
    if isinstance(dado, dict):
        for chave, valor in dado.items():
            encontradas.add(chave)
            _chaves(valor, encontradas)
    elif isinstance(dado, list):
        for item in dado:
            _chaves(item, encontradas)
    return encontradas


def test_sessao_exige_o_aceite_do_termo(cliente):
    assert cliente.post("/api/sessions").status_code == 422
    assert (
        cliente.post("/api/sessions", json={"aceite": False, "termo_versao": "v1"}).status_code
        == 422
    )


def test_sessao_grava_o_aceite_e_nasce_no_estudo_aberto(cliente, sessao, estudo):
    resposta = cliente.post("/api/sessions", json={"aceite": True, "termo_versao": "v1"})

    assert resposta.status_code == 201
    avaliador = sessao.get(EvaluationSession, uuid.UUID(resposta.json()["id"]))
    assert avaliador.study_id == estudo.id
    assert avaliador.termo_versao == "v1"
    assert avaliador.aceito_em is not None


def test_minha_sessao_diz_se_o_login_ja_aceitou_o_termo(cliente, sessao, estudo):
    assert cliente.get("/api/sessions/me").json() is None

    session_id = _criar_sessao(cliente)

    minha = cliente.get("/api/sessions/me").json()
    assert minha["id"] == session_id
    assert minha["study_id"] == str(estudo.id)


def test_minha_sessao_nao_enxerga_o_aceite_de_outro_login(cliente):
    _criar_sessao(cliente)

    entrar_como(f"outro-{uuid.uuid4()}")

    assert cliente.get("/api/sessions/me").json() is None


def test_minha_sessao_some_quando_o_estudo_encerra(cliente, sessao, estudo):
    _criar_sessao(cliente)
    _encerrar(sessao, estudo)

    assert cliente.get("/api/sessions/me").json() is None


def test_sem_estudo_aberto_ninguem_comeca(cliente, sessao, estudo):
    _encerrar(sessao, estudo)

    resposta = cliente.post("/api/sessions", json={"aceite": True, "termo_versao": "v1"})

    assert resposta.status_code == 409


def test_estudo_encerrado_congela_perguntas_e_escolhas(cliente, sessao, documento, estudo):
    session_id = _criar_sessao(cliente)
    rodada = _perguntar(cliente, session_id, documento.slug).json()

    _encerrar(sessao, estudo)

    assert _perguntar(cliente, session_id, documento.slug, "Outra?").status_code == 409
    assert (
        cliente.post(f"/api/rounds/{rodada['id']}/choice", json={"rotulo": "A"}).status_code == 409
    )
    assert cliente.get(f"/api/sessions/{session_id}/progress").json()["estudo_aberto"] is False


def test_nenhuma_correta_conta_como_decisao_sem_vencedora(cliente, sessao, documento):
    session_id = _criar_sessao(cliente)
    rodada = _perguntar(cliente, session_id, documento.slug).json()

    resposta = cliente.post(f"/api/rounds/{rodada['id']}/choice", json={"rotulo": None})

    assert resposta.status_code == 200
    assert resposta.json()["nenhuma_correta"] is True
    assert resposta.json()["escolha_rotulo"] is None
    persistida = sessao.get(QuestionRound, uuid.UUID(rodada["id"]))
    assert persistida.escolha_answer_id is None
    assert (
        cliente.get(f"/api/sessions/{session_id}/progress").json()["documentos"][0]["respondidas"]
        == 1
    )
    assert _perguntar(cliente, session_id, documento.slug, "Segunda?").status_code == 201


def test_escolha_grava_os_tempos_medidos_no_navegador(cliente, sessao, documento):
    session_id = _criar_sessao(cliente)
    rodada = _perguntar(cliente, session_id, documento.slug).json()

    cliente.post(
        f"/api/rounds/{rodada['id']}/choice",
        json={
            "rotulo": "A",
            "tempo_total_ms": 90000,
            "tempo_geracao_ms": 12000,
            "tempo_oculto_ms": 3000,
        },
    )

    persistida = sessao.get(QuestionRound, uuid.UUID(rodada["id"]))
    assert persistida.tempo_total_ms == 90000
    assert persistida.tempo_geracao_ms == 12000
    assert persistida.tempo_oculto_ms == 3000


def test_ordem_da_rodada_e_a_posicao_exibida_ficam_gravadas(cliente, sessao, documento):
    session_id = _criar_sessao(cliente)
    primeira = _perguntar(cliente, session_id, documento.slug, "Primeira?").json()
    _concluir(cliente, primeira["id"])
    segunda = _perguntar(cliente, session_id, documento.slug, "Segunda?").json()

    assert primeira["ordem"] == 1
    assert segunda["ordem"] == 2
    respostas = servico.respostas_da_rodada(sessao, uuid.UUID(segunda["id"]))
    assert [item.posicao_exibida for item in respostas] == [1, 2, 3, 4]


def test_pergunta_devolve_quatro_respostas_com_rotulos_de_a_a_d(cliente, documento):
    session_id = _criar_sessao(cliente)

    resposta = _perguntar(cliente, session_id, documento.slug)

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["pergunta"] == "O que a lei diz?"
    assert [item["rotulo"] for item in corpo["respostas"]] == ["A", "B", "C", "D"]
    assert corpo["escolha_rotulo"] is None


def test_nenhuma_resposta_de_avaliacao_revela_o_pipeline(cliente, documento):
    """A trava do estudo: a identidade do pipeline nao existe no JSON que chega ao navegador."""
    session_id = _criar_sessao(cliente)
    rodada = _perguntar(cliente, session_id, documento.slug).json()
    escolha = cliente.post(f"/api/rounds/{rodada['id']}/choice", json={"rotulo": "B"}).json()
    marcacao = _marcar(cliente, rodada["id"], ["A", "D"]).json()
    historico = cliente.get(f"/api/sessions/{session_id}/documents/{documento.slug}/rounds").json()

    assert "tambem_corretas" in _chaves(marcacao)
    for corpo in (rodada, escolha, marcacao, historico):
        assert not any("pipeline" in chave for chave in _chaves(corpo))
        assert "pipeline" not in str(corpo).lower()


def test_escolha_registra_o_rotulo_e_a_marcacao_libera_a_proxima_pergunta(
    cliente, sessao, documento
):
    session_id = _criar_sessao(cliente)
    rodada = _perguntar(cliente, session_id, documento.slug).json()

    resposta = cliente.post(f"/api/rounds/{rodada['id']}/choice", json={"rotulo": "C"})

    assert resposta.status_code == 200
    assert resposta.json()["escolha_rotulo"] == "C"
    assert resposta.json()["escolhido_em"] is not None
    assert resposta.json()["tambem_corretas"] is None
    assert resposta.json()["marcado_em"] is None
    persistida = sessao.get(QuestionRound, uuid.UUID(rodada["id"]))
    assert persistida is not None
    assert persistida.escolha_answer_id is not None
    # Entre a escolha e a marcacao, a rodada continua pendente.
    assert _perguntar(cliente, session_id, documento.slug, "Segunda?").status_code == 409
    assert _marcar(cliente, rodada["id"], ["A"]).status_code == 200
    assert _perguntar(cliente, session_id, documento.slug, "Segunda?").status_code == 201


def test_escolher_duas_vezes_na_mesma_rodada_responde_409(cliente, documento):
    session_id = _criar_sessao(cliente)
    rodada = _perguntar(cliente, session_id, documento.slug).json()
    cliente.post(f"/api/rounds/{rodada['id']}/choice", json={"rotulo": "A"})

    repetida = cliente.post(f"/api/rounds/{rodada['id']}/choice", json={"rotulo": "B"})

    assert repetida.status_code == 409


def test_rotulo_fora_do_intervalo_responde_422(cliente, documento):
    session_id = _criar_sessao(cliente)
    rodada = _perguntar(cliente, session_id, documento.slug).json()

    resposta = cliente.post(f"/api/rounds/{rodada['id']}/choice", json={"rotulo": "Z"})

    assert resposta.status_code == 422


def test_escolha_em_rodada_inexistente_responde_404(cliente):
    assert (
        cliente.post(f"/api/rounds/{uuid.uuid4()}/choice", json={"rotulo": "A"}).status_code == 404
    )


def test_perguntar_com_rodada_pendente_responde_409(cliente, documento):
    session_id = _criar_sessao(cliente)
    _perguntar(cliente, session_id, documento.slug)

    segunda = _perguntar(cliente, session_id, documento.slug, "E agora?")

    assert segunda.status_code == 409


def test_documento_em_processamento_nao_aceita_pergunta(cliente, sessao, documento):
    documento.status = StatusDocumento.PROCESSANDO
    sessao.add(documento)
    sessao.commit()
    session_id = _criar_sessao(cliente)

    resposta = _perguntar(cliente, session_id, documento.slug)

    assert resposta.status_code == 409


def test_sessao_ou_documento_inexistente_responde_404(cliente, documento):
    session_id = _criar_sessao(cliente)

    assert _perguntar(cliente, str(uuid.uuid4()), documento.slug).status_code == 404
    assert _perguntar(cliente, session_id, "inexistente").status_code == 404
    assert (
        cliente.get(f"/api/sessions/{session_id}/documents/inexistente/rounds").status_code == 404
    )


def test_limite_de_perguntas_por_documento_e_imposto_no_servidor(cliente, documento, monkeypatch):
    monkeypatch.setattr(
        "app.api.routers.evaluation.get_settings",
        lambda: type("SettingsFalso", (), {"max_perguntas": 2})(),
    )
    session_id = _criar_sessao(cliente)
    for numero in range(2):
        rodada = _perguntar(cliente, session_id, documento.slug, f"Pergunta {numero}?").json()
        _concluir(cliente, rodada["id"])

    excedente = _perguntar(cliente, session_id, documento.slug, "Uma a mais?")

    assert excedente.status_code == 409


def test_pergunta_vazia_ou_longa_demais_e_rejeitada(cliente, documento):
    session_id = _criar_sessao(cliente)

    assert _perguntar(cliente, session_id, documento.slug, "  ").status_code == 422
    assert _perguntar(cliente, session_id, documento.slug, "x" * 501).status_code == 422


def test_historico_reidrata_as_rodadas_na_ordem(cliente, documento):
    session_id = _criar_sessao(cliente)
    primeira = _perguntar(cliente, session_id, documento.slug, "Primeira?").json()
    _concluir(cliente, primeira["id"])
    _perguntar(cliente, session_id, documento.slug, "Segunda?")

    historico = cliente.get(f"/api/sessions/{session_id}/documents/{documento.slug}/rounds").json()

    assert [item["pergunta"] for item in historico] == ["Primeira?", "Segunda?"]
    assert historico[0]["escolha_rotulo"] == "A"
    assert historico[1]["escolha_rotulo"] is None


def test_progresso_conta_apenas_rodadas_decididas(cliente, documento):
    session_id = _criar_sessao(cliente)
    rodada = _perguntar(cliente, session_id, documento.slug, "Primeira?").json()

    antes = cliente.get(f"/api/sessions/{session_id}/progress").json()
    cliente.post(f"/api/rounds/{rodada['id']}/choice", json={"rotulo": "A"})
    depois = cliente.get(f"/api/sessions/{session_id}/progress").json()

    assert antes["documentos"] == []
    assert depois["documentos"] == [
        {
            "document_id": str(documento.id),
            "slug": documento.slug,
            "respondidas": 1,
            "concluido": False,
        }
    ]
    assert depois["total_concluidos"] == 0


def test_progresso_de_sessao_inexistente_responde_404(cliente):
    assert cliente.get(f"/api/sessions/{uuid.uuid4()}/progress").status_code == 404


def test_falha_de_pipeline_devolve_502_e_nao_deixa_rodada_para_tras(
    cliente, documento, monkeypatch
):
    async def falhar(sessao, session_id, document_id, pergunta):
        raise servico.ErroDeRodada("RuntimeError: openai fora do ar")

    monkeypatch.setattr("app.api.routers.evaluation.criar_rodada", falhar)
    session_id = _criar_sessao(cliente)

    resposta = _perguntar(cliente, session_id, documento.slug)

    assert resposta.status_code == 502
    historico = cliente.get(f"/api/sessions/{session_id}/documents/{documento.slug}/rounds")
    assert historico.json() == []


# Segundo passo: as outras respostas que tambem estao corretas


def _respostas_por_rotulo(sessao: Session, round_id: str) -> dict[str, PipelineAnswer]:
    sessao.expire_all()
    return {
        item.rotulo_cego: item for item in servico.respostas_da_rodada(sessao, uuid.UUID(round_id))
    }


def _rodada_escolhida(cliente, documento, rotulo: str | None = "A") -> tuple[str, dict]:
    session_id = _criar_sessao(cliente)
    rodada = _perguntar(cliente, session_id, documento.slug).json()
    escolha = cliente.post(f"/api/rounds/{rodada['id']}/choice", json={"rotulo": rotulo})
    assert escolha.status_code == 200
    return session_id, rodada


def test_marcacao_grava_as_outras_corretas_e_os_tempos(cliente, sessao, documento):
    _, rodada = _rodada_escolhida(cliente, documento, "A")

    resposta = _marcar(
        cliente,
        rodada["id"],
        ["D", "B"],
        tempo_marcacao_ms=7000,
        tempo_marcacao_oculto_ms=500,
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["tambem_corretas"] == ["B", "D"]
    assert corpo["marcado_em"] is not None
    assert corpo["escolha_rotulo"] == "A"
    respostas = _respostas_por_rotulo(sessao, rodada["id"])
    assert {rotulo: item.tambem_correta for rotulo, item in respostas.items()} == {
        "A": None,
        "B": True,
        "C": False,
        "D": True,
    }
    persistida = sessao.get(QuestionRound, uuid.UUID(rodada["id"]))
    assert persistida.tempo_marcacao_ms == 7000
    assert persistida.tempo_marcacao_oculto_ms == 500
    assert persistida.marcado_em is not None


def test_marcacao_vazia_confirma_que_nenhuma_outra_esta_correta(cliente, sessao, documento):
    _, rodada = _rodada_escolhida(cliente, documento, "C")

    resposta = _marcar(cliente, rodada["id"], [])

    assert resposta.status_code == 200
    assert resposta.json()["tambem_corretas"] == []
    respostas = _respostas_por_rotulo(sessao, rodada["id"])
    assert [respostas[r].tambem_correta for r in "ABCD"] == [False, False, None, False]


def test_marcacao_nao_mexe_nos_tempos_da_escolha(cliente, sessao, documento):
    session_id = _criar_sessao(cliente)
    rodada = _perguntar(cliente, session_id, documento.slug).json()
    cliente.post(
        f"/api/rounds/{rodada['id']}/choice",
        json={"rotulo": "A", "tempo_total_ms": 90000, "tempo_oculto_ms": 1000},
    )

    _marcar(cliente, rodada["id"], ["B"], tempo_marcacao_ms=5000, tempo_marcacao_oculto_ms=2000)

    sessao.expire_all()
    persistida = sessao.get(QuestionRound, uuid.UUID(rodada["id"]))
    assert persistida.tempo_total_ms == 90000
    assert persistida.tempo_oculto_ms == 1000


def test_tempo_de_marcacao_negativo_responde_422(cliente, documento):
    _, rodada = _rodada_escolhida(cliente, documento, "A")

    assert _marcar(cliente, rodada["id"], ["B"], tempo_marcacao_ms=-1).status_code == 422


def test_historico_traz_a_marcacao(cliente, documento):
    session_id, rodada = _rodada_escolhida(cliente, documento, "B")
    antes = cliente.get(f"/api/sessions/{session_id}/documents/{documento.slug}/rounds").json()
    _marcar(cliente, rodada["id"], ["C"])

    depois = cliente.get(f"/api/sessions/{session_id}/documents/{documento.slug}/rounds").json()

    assert antes[0]["tambem_corretas"] is None
    assert depois[0]["tambem_corretas"] == ["C"]
    assert depois[0]["marcado_em"] is not None


def test_marcar_antes_de_escolher_responde_409(cliente, documento):
    session_id = _criar_sessao(cliente)
    rodada = _perguntar(cliente, session_id, documento.slug).json()

    assert _marcar(cliente, rodada["id"], ["B"]).status_code == 409


def test_rodada_nenhuma_nao_tem_segundo_passo(cliente, documento):
    session_id, rodada = _rodada_escolhida(cliente, documento, None)

    assert _marcar(cliente, rodada["id"], []).status_code == 409
    assert _perguntar(cliente, session_id, documento.slug, "Segunda?").status_code == 201


def test_marcar_duas_vezes_responde_409(cliente, documento):
    _, rodada = _rodada_escolhida(cliente, documento, "A")
    assert _marcar(cliente, rodada["id"], ["B"]).status_code == 200

    assert _marcar(cliente, rodada["id"], ["C"]).status_code == 409


def test_marcar_com_estudo_encerrado_responde_409(cliente, sessao, documento, estudo):
    _, rodada = _rodada_escolhida(cliente, documento, "A")
    _encerrar(sessao, estudo)

    assert _marcar(cliente, rodada["id"], ["B"]).status_code == 409


@pytest.mark.parametrize(
    "rotulos",
    [["B", "B"], ["Z"], ["b"], ["A"], ["B", "A"]],
    ids=["repetido", "fora-de-a-d", "minusculo", "a-propria-escolhida", "inclui-a-escolhida"],
)
def test_marcacao_invalida_responde_422(cliente, sessao, documento, rotulos):
    _, rodada = _rodada_escolhida(cliente, documento, "A")

    assert _marcar(cliente, rodada["id"], rotulos).status_code == 422
    sessao.expire_all()
    assert sessao.get(QuestionRound, uuid.UUID(rodada["id"])).marcado_em is None


def test_marcacao_sem_o_campo_rotulos_responde_422(cliente, documento):
    _, rodada = _rodada_escolhida(cliente, documento, "A")

    resposta = cliente.post(f"/api/rounds/{rodada['id']}/also-correct", json={})

    assert resposta.status_code == 422


def test_rotulo_sem_resposta_na_rodada_responde_422(cliente, sessao, documento):
    pipeline = sessao.exec(select(Pipeline).where(Pipeline.codigo == "pipeline-4")).one()
    pipeline.ativo = False
    sessao.add(pipeline)
    sessao.commit()
    _, rodada = _rodada_escolhida(cliente, documento, "A")
    assert [item["rotulo"] for item in rodada["respostas"]] == ["A", "B", "C"]

    assert _marcar(cliente, rodada["id"], ["D"]).status_code == 422


def test_marcar_rodada_inexistente_ou_de_outro_login_responde_404(cliente, documento):
    _, rodada = _rodada_escolhida(cliente, documento, "A")

    assert _marcar(cliente, str(uuid.uuid4()), ["B"]).status_code == 404
    entrar_como(f"outro-{uuid.uuid4()}")
    assert _marcar(cliente, rodada["id"], ["B"]).status_code == 404


def test_escolha_sem_marcacao_ja_conta_no_progresso(cliente, documento):
    session_id, _ = _rodada_escolhida(cliente, documento, "A")

    progresso = cliente.get(f"/api/sessions/{session_id}/progress").json()

    assert progresso["documentos"][0]["respondidas"] == 1
