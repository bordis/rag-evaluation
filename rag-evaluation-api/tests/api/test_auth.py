"""SSO: validacao do token do Keycloak, roles do cliente e posse da sessao."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.core.auth import ROLE_ADMIN, ROLE_AVALIADOR, Usuario, decodificar_token, usuario_atual
from app.core.config import get_settings
from app.main import app
from app.models.study import StatusEstudo, Study

CHAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(**sobrescritas) -> str:
    settings = get_settings()
    dados = {
        "sub": "pessoa-1",
        "iss": settings.keycloak_issuer,
        "azp": settings.keycloak_client_id,
        "exp": int(time.time()) + 300,
        "resource_access": {settings.keycloak_client_id: {"roles": [ROLE_AVALIADOR]}},
    }
    dados.update(sobrescritas)
    return jwt.encode(dados, CHAVE, algorithm="RS256")


def _decodificar(token: str) -> Usuario:
    return decodificar_token(token, chave=CHAVE.public_key())


def _como(*roles: str, sub: str = "pessoa-1") -> None:
    usuario = Usuario(sub=sub, roles=frozenset(roles))
    app.dependency_overrides[usuario_atual] = lambda: usuario


@pytest.fixture(name="estudo")
def estudo_fixture(sessao) -> Study:
    estudo = Study(nome="Piloto", status=StatusEstudo.ABERTO)
    sessao.add(estudo)
    sessao.commit()
    return estudo


# Token


def test_token_valido_traz_o_sub_e_as_roles_do_cliente():
    usuario = _decodificar(_token())

    assert usuario.sub == "pessoa-1"
    assert usuario.roles == {ROLE_AVALIADOR}
    assert not usuario.admin


def test_roles_de_outro_cliente_nao_contam():
    usuario = _decodificar(_token(resource_access={"outro": {"roles": [ROLE_ADMIN]}}))

    assert usuario.roles == frozenset()


@pytest.mark.parametrize(
    "sobrescritas",
    [
        {"exp": int(time.time()) - 10},
        {"iss": "https://outro-sso/realms/pmpa"},
        {"azp": "outro-sistema"},
    ],
    ids=["expirado", "outro-emissor", "outro-cliente"],
)
def test_token_recusado(sobrescritas):
    with pytest.raises(HTTPException) as erro:
        _decodificar(_token(**sobrescritas))

    assert erro.value.status_code == 401


def test_assinatura_de_outra_chave_e_recusada():
    outra = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(jwt.decode(_token(), options={"verify_signature": False}), outra, "RS256")

    with pytest.raises(HTTPException) as erro:
        _decodificar(token)

    assert erro.value.status_code == 401


# Rotas


def test_sem_token_responde_401(cliente):
    app.dependency_overrides.pop(usuario_atual)

    resposta = cliente.get("/api/studies/atual")

    assert resposta.status_code == 401
    assert resposta.headers["www-authenticate"] == "Bearer"


def test_saude_dispensa_login(cliente):
    app.dependency_overrides.pop(usuario_atual)

    assert cliente.get("/api/health").status_code != 401


def test_avaliador_nao_entra_na_area_do_pesquisador(cliente, estudo):
    _como(ROLE_AVALIADOR)

    assert cliente.get("/api/studies/atual").status_code == 200
    assert cliente.get("/api/studies").status_code == 403
    assert cliente.get("/api/pipelines").status_code == 403
    assert cliente.get(f"/api/admin/studies/{estudo.id}/stats").status_code == 403
    assert cliente.post("/api/studies", json={"nome": "Outro"}).status_code == 403


def test_sem_role_do_estudo_nao_avalia(cliente, estudo):
    _como()

    assert cliente.get("/api/studies/atual").status_code == 403


# Sessao


def test_mesmo_login_retoma_a_mesma_sessao(cliente, estudo):
    _como(ROLE_AVALIADOR)
    aceite = {"aceite": True, "termo_versao": "v1"}

    primeira = cliente.post("/api/sessions", json=aceite).json()["id"]
    segunda = cliente.post("/api/sessions", json=aceite).json()["id"]

    assert primeira == segunda


def test_sessao_de_outro_login_nao_existe(cliente, estudo):
    _como(ROLE_AVALIADOR, sub="pessoa-1")
    sessao_id = cliente.post("/api/sessions", json={"aceite": True, "termo_versao": "v1"}).json()[
        "id"
    ]

    _como(ROLE_AVALIADOR, ROLE_ADMIN, sub="pessoa-2")

    assert cliente.get(f"/api/sessions/{sessao_id}/progress").status_code == 404
    assert cliente.get(f"/api/sessions/{sessao_id}/documents/lgpd/rounds").status_code == 404
