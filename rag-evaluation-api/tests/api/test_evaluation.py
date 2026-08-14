import uuid

import pytest
from sqlmodel import Session

from app.models.document import Document, StatusDocumento
from app.models.evaluation import EvaluationSession, QuestionRound
from app.seed import semear_pipelines
from app.services import evaluation as servico
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


def _criar_sessao(cliente) -> str:
    resposta = cliente.post("/api/sessions", json={})
    assert resposta.status_code == 201
    return resposta.json()["id"]


def _perguntar(cliente, session_id: str, slug: str, pergunta: str = "O que a lei diz?"):
    return cliente.post(
        f"/api/sessions/{session_id}/documents/{slug}/questions", json={"pergunta": pergunta}
    )


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


def test_sessao_sem_corpo_e_criada_anonima(cliente, sessao):
    resposta = cliente.post("/api/sessions")

    assert resposta.status_code == 201
    avaliador = sessao.get(EvaluationSession, uuid.UUID(resposta.json()["id"]))
    assert avaliador is not None
    assert avaliador.area_atuacao is None


def test_sessao_grava_o_perfil_opcional(cliente, sessao):
    resposta = cliente.post(
        "/api/sessions",
        json={
            "area_atuacao": "Direito digital",
            "familiaridade": "alta",
            "tempo_experiencia": "5-10-anos",
        },
    )

    assert resposta.status_code == 201
    avaliador = sessao.get(EvaluationSession, uuid.UUID(resposta.json()["id"]))
    assert avaliador is not None
    assert avaliador.familiaridade == "alta"
    assert avaliador.tempo_experiencia == "5-10-anos"


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
    historico = cliente.get(f"/api/sessions/{session_id}/documents/{documento.slug}/rounds").json()

    for corpo in (rodada, escolha, historico):
        assert not any("pipeline" in chave for chave in _chaves(corpo))
        assert "pipeline" not in str(corpo).lower()


def test_escolha_registra_o_rotulo_e_libera_a_proxima_pergunta(cliente, sessao, documento):
    session_id = _criar_sessao(cliente)
    rodada = _perguntar(cliente, session_id, documento.slug).json()

    resposta = cliente.post(f"/api/rounds/{rodada['id']}/choice", json={"rotulo": "C"})

    assert resposta.status_code == 200
    assert resposta.json()["escolha_rotulo"] == "C"
    assert resposta.json()["escolhido_em"] is not None
    persistida = sessao.get(QuestionRound, uuid.UUID(rodada["id"]))
    assert persistida is not None
    assert persistida.escolha_answer_id is not None
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
        cliente.post(f"/api/rounds/{rodada['id']}/choice", json={"rotulo": "A"})

    excedente = _perguntar(cliente, session_id, documento.slug, "Uma a mais?")

    assert excedente.status_code == 409


def test_pergunta_vazia_ou_longa_demais_e_rejeitada(cliente, documento):
    session_id = _criar_sessao(cliente)

    assert _perguntar(cliente, session_id, documento.slug, "  ").status_code == 422
    assert _perguntar(cliente, session_id, documento.slug, "x" * 501).status_code == 422


def test_historico_reidrata_as_rodadas_na_ordem(cliente, documento):
    session_id = _criar_sessao(cliente)
    primeira = _perguntar(cliente, session_id, documento.slug, "Primeira?").json()
    cliente.post(f"/api/rounds/{primeira['id']}/choice", json={"rotulo": "A"})
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
