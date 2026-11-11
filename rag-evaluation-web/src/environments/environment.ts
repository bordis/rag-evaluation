/**
 * Ambiente de produção (`ng build`). Em desenvolvimento, `ng serve` troca este arquivo por
 * `environment.development.ts` (veja `fileReplacements` no `angular.json`): os dois precisam ter
 * as mesmas chaves.
 *
 * `apiBaseUrl` aponta para o `rag-evaluation-api` **incluindo o prefixo `/api`**. Relativo, supõe a
 * API publicada no mesmo host do front; a origem precisa constar em `CORS_ORIGINS` no backend.
 *
 * Keycloak: o cliente `smartgen` é público (PKCE) e traz as roles `user` (avaliador) e `admin`
 * (pesquisador). O `keycloakUrl` inclui o `/auth` das versões antigas do servidor.
 */
export const environment = {
  environment: 'producao',
  production: true,
  apiBaseUrl: '/api',
  keycloakUrl: 'https://sso-pmpa.procempa.com.br/auth',
  keycloakRealm: 'pmpa',
  keycloakClientId: 'smartgen',
};
