import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import Keycloak from 'keycloak-js';

import { App } from './app';
import { routes } from './app.routes';
import { ROLE_ADMIN, ROLE_AVALIADOR } from './auth/autenticacao';
import { keycloakFake } from './testing/keycloak-fake';

async function montar(roles: string[]) {
  const fake = keycloakFake(roles, 'maria.souza');
  await TestBed.configureTestingModule({
    imports: [App],
    providers: [provideRouter(routes), { provide: Keycloak, useValue: fake.keycloak }],
  }).compileComponents();
  const fixture = TestBed.createComponent(App);
  await fixture.whenStable();
  const compiled = fixture.nativeElement as HTMLElement;
  const clicar = async (seletor: string) => {
    compiled.querySelector<HTMLElement>(seletor)!.click();
    await fixture.whenStable();
  };
  return { compiled, clicar, saidas: fake.saidas };
}

function links(compiled: HTMLElement, seletor: string): (string | null)[] {
  return [...compiled.querySelectorAll(seletor)].map((el) => el.getAttribute('href'));
}

describe('App', () => {
  it('renders the brand and the account initials', async () => {
    const { compiled } = await montar([ROLE_AVALIADOR]);

    expect(compiled.querySelector('.brand__text')?.textContent).toContain('Avaliação RAG');
    expect(compiled.querySelector('.avatar')?.textContent?.trim()).toBe('MS');
  });

  it('shows only the evaluator links to evaluators', async () => {
    const { compiled } = await montar([ROLE_AVALIADOR]);

    expect(links(compiled, '.trilho a')).toEqual(['/', '/documentos']);
    expect(compiled.querySelector('.trilho__gatilho')).toBeNull();
  });

  it('opens the researcher panel for admins', async () => {
    const { compiled, clicar } = await montar([ROLE_ADMIN]);
    expect(compiled.querySelector('.painel')).toBeNull();

    await clicar('.trilho__gatilho');

    expect(compiled.querySelector('.trilho__gatilho')?.getAttribute('aria-expanded')).toBe('true');
    expect(links(compiled, '.painel__item')).toEqual([
      '/admin/estudos',
      '/admin/documentos',
      '/admin/pipelines',
    ]);
  });

  it('closes an open panel on Escape', async () => {
    const { compiled, clicar } = await montar([ROLE_ADMIN]);
    await clicar('.trilho__gatilho');

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    TestBed.tick();

    expect(compiled.querySelector('.painel')).toBeNull();
  });

  it('logs out from the account panel back to the app origin', async () => {
    const { compiled, clicar, saidas } = await montar([ROLE_AVALIADOR]);

    await clicar('.avatar');
    expect(compiled.querySelector('.painel__nome')?.textContent).toContain('maria.souza');
    await clicar('.painel__acao');

    expect(saidas).toEqual([{ redirectUri: window.location.origin }]);
  });
});
