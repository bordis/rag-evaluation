import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { ApiRag } from '../../services/api-rag';
import { ApiRagFake } from '../../testing/api-rag-fake';
import { Welcome } from './welcome';

async function estabilizar(fixture: { whenStable(): Promise<unknown> }): Promise<void> {
  await fixture.whenStable();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await fixture.whenStable();
}

describe('Welcome', () => {
  let api: ApiRagFake;

  beforeEach(async () => {
    sessionStorage.clear();
    api = new ApiRagFake();
    await TestBed.configureTestingModule({
      imports: [Welcome],
      providers: [provideRouter([]), { provide: ApiRag, useValue: api }],
    }).compileComponents();
  });

  it('renders the headline, the 3 steps and the consent term', async () => {
    // Arrange
    const fixture = TestBed.createComponent(Welcome);

    // Act
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;

    // Assert
    expect(compiled.querySelector('.hero__title')?.textContent).toContain('melhor');
    expect(compiled.querySelectorAll('.step')).toHaveLength(3);
    expect(compiled.querySelector('.termo__titulo')?.textContent).toContain('Termo');
  });

  it('keeps the start button disabled until the term is accepted', async () => {
    // Arrange
    const fixture = TestBed.createComponent(Welcome);
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;
    const botao = compiled.querySelector<HTMLButtonElement>('.cta')!;
    expect(botao.disabled).toBe(true);

    // Act
    compiled.querySelector<HTMLInputElement>('input[type=checkbox]')!.click();
    await estabilizar(fixture);

    // Assert
    expect(botao.disabled).toBe(false);
  });

  it('blocks the start when no study is open', async () => {
    // Arrange
    api.estudo = null;
    const fixture = TestBed.createComponent(Welcome);

    // Act
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;

    // Assert
    expect(compiled.querySelector('.cta')).toBeNull();
    expect(compiled.querySelector('.aviso')?.textContent).toContain('Não há estudo aberto');
  });
});
