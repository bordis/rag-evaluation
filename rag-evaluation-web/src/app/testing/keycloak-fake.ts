import type Keycloak from 'keycloak-js';

import { environment } from '../../environments/environment';

/** Keycloak já logado, com as roles dadas no cliente do estudo. Sem servidor nem redirect. */
export function keycloakFake(roles: string[], usuario = 'avaliador.teste') {
  const saidas: unknown[] = [];
  const falso = {
    authenticated: true,
    tokenParsed: { preferred_username: usuario },
    resourceAccess: { [environment.keycloakClientId]: { roles } },
    realmAccess: { roles: [] },
    hasResourceRole: (role: string, cliente?: string) =>
      cliente === environment.keycloakClientId && roles.includes(role),
    logout: async (opcoes?: unknown) => {
      saidas.push(opcoes);
    },
  };
  return { keycloak: falso as unknown as Keycloak, saidas };
}
