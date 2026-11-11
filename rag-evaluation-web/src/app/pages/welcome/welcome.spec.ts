import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { ApiRag } from '../../services/api-rag';
import { EvaluationStore } from '../../services/evaluation-store';
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
    expect(compiled.querySelector('.aviso')?.textContent).toContain('A avaliação não está aberta');
  });

  it('hides the term when this login already accepted it in the open study', async () => {
    // Arrange
    api.sessaoDoLogin = 'sessao-de-outro-navegador';
    const fixture = TestBed.createComponent(Welcome);

    // Act
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;

    // Assert
    expect(compiled.querySelector('input[type=checkbox]')).toBeNull();
    expect(compiled.querySelector('.aceito__titulo')?.textContent).toContain('já aceitou');
    expect(compiled.querySelector('a.cta')?.getAttribute('href')).toBe('/documentos');
    expect(sessionStorage.getItem('rag-evaluation.session-id')).toBe('sessao-de-outro-navegador');
  });

  it('highlights the term and focuses the checkbox when the documents were requested first', async () => {
    // Arrange
    TestBed.inject(EvaluationStore).pedirAceite();
    const fixture = TestBed.createComponent(Welcome);

    // Act
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;

    // Assert
    expect(compiled.querySelector('.termo')?.classList).toContain('termo--exigido');
    expect(compiled.querySelector('.termo__pedido')?.textContent).toContain('aceite o termo');
    expect(document.activeElement).toBe(compiled.querySelector('input[type=checkbox]'));
    expect(TestBed.inject(EvaluationStore).aceitePedido()).toBe(0);
  });

  it('drops the request message once the term is accepted', async () => {
    // Arrange
    TestBed.inject(EvaluationStore).pedirAceite();
    const fixture = TestBed.createComponent(Welcome);
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;

    // Act
    compiled.querySelector<HTMLInputElement>('input[type=checkbox]')!.click();
    await estabilizar(fixture);

    // Assert
    expect(compiled.querySelector('.termo__pedido')).toBeNull();
    expect(compiled.querySelector('.termo')?.classList).not.toContain('termo--exigido');
  });
});
