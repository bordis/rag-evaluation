/**
 * Ambiente de produção (`ng build`). Em desenvolvimento, `ng serve` troca este arquivo por
 * `environment.development.ts` (veja `fileReplacements` no `angular.json`): os dois precisam ter
 * as mesmas chaves.
 *
 * Na imagem Docker, as URLs vêm de `window.__env`, que o nginx gera em `/env.js` na subida do
 * container (`docker/nginx.conf.template`): a mesma imagem roda em qualquer ambiente. Fora do
 * container, `public/env.js` deixa o objeto vazio e valem os padrões abaixo.
 *
 * `apiBaseUrl` aponta para o `rag-evaluation-api` **incluindo o prefixo `/api`**. Relativo, supõe a
 * API publicada no mesmo host do front; a origem precisa constar em `CORS_ORIGINS` no backend.
 *
 * Keycloak: o cliente `smartgen` é público (PKCE) e traz as roles `user` (avaliador) e `admin`
 * (pesquisador). O `keycloakUrl` inclui o `/auth` das versões antigas do servidor.
 */
const env: Partial<Record<string, string>> =
  (globalThis as { __env?: Partial<Record<string, string>> }).__env ?? {};

export const environment = {
  environment: 'producao',
  production: true,
  apiBaseUrl: env['apiUrl'] || '/api',
  keycloakUrl: env['keycloakUrl'] || 'https://sso-pmpa.procempa.com.br/auth',
  keycloakRealm: env['keycloakRealm'] || 'pmpa',
  keycloakClientId: env['keycloakClientId'] || 'smartgen',
};
