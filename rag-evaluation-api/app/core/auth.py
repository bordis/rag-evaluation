"""SSO via Keycloak: a API valida o access token que o frontend obteve, sem guardar segredo.

A assinatura e conferida contra o JWKS do realm (as chaves publicas, em cache no `PyJWKClient`),
junto com emissor e validade. O token do Keycloak nao traz o cliente em `aud` por padrao, entao
quem identifica o cliente e o `azp` — o cliente que pediu o token. As roles do estudo sao do
cliente, em `resource_access.<client_id>.roles`: `user` avalia, `admin` tambem administra.

Da pessoa, a API so usa o `sub`: nome e e-mail nunca chegam ao banco da pesquisa.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

ROLE_AVALIADOR = "user"
ROLE_ADMIN = "admin"

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Usuario:
    sub: str
    roles: frozenset[str]

    @property
    def admin(self) -> bool:
        return ROLE_ADMIN in self.roles


@lru_cache
def _cliente_jwks() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(get_settings().keycloak_jwks_url, cache_keys=True, lifespan=3600)


def _nao_autenticado(detalhe: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail=detalhe, headers={"WWW-Authenticate": "Bearer"}
    )


def decodificar_token(token: str, chave: object | None = None) -> Usuario:
    """Valida o token e extrai o usuario. `chave` existe para os testes assinarem localmente."""
    settings = get_settings()
    try:
        if chave is None:
            chave = _cliente_jwks().get_signing_key_from_jwt(token).key
        dados = jwt.decode(
            token,
            chave,  # type: ignore[arg-type]
            algorithms=["RS256"],
            issuer=settings.keycloak_issuer,
            options={"verify_aud": False, "require": ["exp", "iss", "sub"]},
        )
    except jwt.PyJWKClientConnectionError as erro:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Servidor de login indisponível."
        ) from erro
    except jwt.InvalidTokenError as erro:
        raise _nao_autenticado("Sessão de login inválida ou expirada.") from erro

    if dados.get("azp") != settings.keycloak_client_id:
        raise _nao_autenticado("Token emitido para outro sistema.")
    cliente = (dados.get("resource_access") or {}).get(settings.keycloak_client_id) or {}
    return Usuario(sub=dados["sub"], roles=frozenset(cliente.get("roles") or []))


def usuario_atual(
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Usuario:
    if credenciais is None:
        raise _nao_autenticado("Faça login para continuar.")
    return decodificar_token(credenciais.credentials)


def exigir_avaliador(usuario: Annotated[Usuario, Depends(usuario_atual)]) -> Usuario:
    """O pesquisador tambem passa: ele precisa conseguir testar o fluxo do avaliador."""
    if not usuario.roles & {ROLE_AVALIADOR, ROLE_ADMIN}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Sem acesso a este estudo.")
    return usuario


def exigir_admin(usuario: Annotated[Usuario, Depends(usuario_atual)]) -> Usuario:
    if not usuario.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Acesso restrito ao pesquisador.")
    return usuario


AvaliadorDep = Annotated[Usuario, Depends(exigir_avaliador)]
AdminDep = Annotated[Usuario, Depends(exigir_admin)]
