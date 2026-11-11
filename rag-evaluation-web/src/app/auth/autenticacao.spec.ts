import { TestBed } from '@angular/core/testing';
import {
  type ActivatedRouteSnapshot,
  provideRouter,
  type RouterStateSnapshot,
  UrlTree,
} from '@angular/router';
import Keycloak from 'keycloak-js';

import { keycloakFake } from '../testing/keycloak-fake';
import { exigeRole, ROLE_ADMIN, ROLE_AVALIADOR, ROLES_DO_ESTUDO } from './autenticacao';

function guardar(rolesDoUsuario: string[], rolesDaRota: string[]) {
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      { provide: Keycloak, useValue: keycloakFake(rolesDoUsuario).keycloak },
    ],
  });
  const rota = { data: { roles: rolesDaRota } } as unknown as ActivatedRouteSnapshot;
  return TestBed.runInInjectionContext(() => exigeRole(rota, {} as RouterStateSnapshot));
}

describe('exigeRole', () => {
  it('lets an evaluator into the evaluation flow', async () => {
    expect(await guardar([ROLE_AVALIADOR], ROLES_DO_ESTUDO)).toBe(true);
  });

  it('lets the researcher into the evaluation flow too', async () => {
    expect(await guardar([ROLE_ADMIN], ROLES_DO_ESTUDO)).toBe(true);
  });

  it('sends an evaluator away from the researcher area', async () => {
    const resultado = await guardar([ROLE_AVALIADOR], [ROLE_ADMIN]);

    expect(resultado).toBeInstanceOf(UrlTree);
    expect(String(resultado)).toBe('/sem-acesso');
  });

  it('sends an account without any study role away', async () => {
    expect(String(await guardar([], ROLES_DO_ESTUDO))).toBe('/sem-acesso');
  });
});
