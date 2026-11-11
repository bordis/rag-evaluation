import { type EnvironmentProviders, inject, type Provider } from '@angular/core';
import { type ActivatedRouteSnapshot, type CanActivateFn, Router } from '@angular/router';
import {
  type AuthGuardData,
  createAuthGuard,
  createInterceptorCondition,
  INCLUDE_BEARER_TOKEN_INTERCEPTOR_CONFIG,
  type IncludeBearerTokenCondition,
  provideKeycloak,
} from 'keycloak-angular';
import type Keycloak from 'keycloak-js';

import { environment } from '../../environments/environment';

/** Roles do cliente no Keycloak. `admin` também avalia: o pesquisador testa o fluxo. */
export const ROLE_AVALIADOR = 'user';
export const ROLE_ADMIN = 'admin';
export const ROLES_DO_ESTUDO = [ROLE_AVALIADOR, ROLE_ADMIN];

/** Só as roles do cliente do estudo contam; as do realm e de outros clientes, não. */
export function temRole(keycloak: Keycloak, role: string): boolean {
  return keycloak.hasResourceRole(role, environment.keycloakClientId);
}

function escaparRegex(texto: string): string {
  return texto.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Todo o app exige login (`login-required`): não há tela pública. O token vai só nas chamadas à
 * API do estudo, e o interceptor o renova antes de cada uma, se estiver perto de vencer.
 */
export function provideAutenticacao(): (Provider | EnvironmentProviders)[] {
  return [
    provideKeycloak({
      config: {
        url: environment.keycloakUrl,
        realm: environment.keycloakRealm,
        clientId: environment.keycloakClientId,
      },
      initOptions: {
        onLoad: 'login-required',
        pkceMethod: 'S256',
        // O iframe de checagem depende de cookie de terceiros, que os navegadores bloqueiam.
        checkLoginIframe: false,
      },
    }),
    {
      provide: INCLUDE_BEARER_TOKEN_INTERCEPTOR_CONFIG,
      useValue: [
        createInterceptorCondition<IncludeBearerTokenCondition>({
          urlPattern: new RegExp(`^${escaparRegex(environment.apiBaseUrl)}(/.*)?$`, 'i'),
        }),
      ],
    },
  ];
}

// `inject` antes de qualquer `await`: só a parte síncrona roda no contexto de injeção.
const acessoPorRole = async (route: ActivatedRouteSnapshot, _: unknown, auth: AuthGuardData) => {
  const aceitas = (route.data['roles'] as string[] | undefined) ?? [];
  const minhas = auth.grantedRoles.resourceRoles[environment.keycloakClientId] ?? [];
  if (auth.authenticated && aceitas.some((role) => minhas.includes(role))) {
    return true;
  }
  return inject(Router).parseUrl('/sem-acesso');
};

/** Exige uma das roles em `data.roles`. A API confere de novo: aqui só se evita a tela quebrada. */
export const exigeRole = createAuthGuard<CanActivateFn>(acessoPorRole);
