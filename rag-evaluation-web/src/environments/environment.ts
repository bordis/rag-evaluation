/**
 * Configuração de ambiente do front-end.
 *
 * `apiBaseUrl` precisa apontar para o `rag-evaluation-api` **incluindo o prefixo `/api`**.
 * A origem informada aqui também precisa constar em `CORS_ORIGINS` no `.env` do backend,
 * senão o navegador bloqueia as chamadas.
 */
export const environment = {
  apiBaseUrl: 'http://127.0.0.1:8000/api',
};
