import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { ApiRag } from '../../services/api-rag';
import { EvaluationStore } from '../../services/evaluation-store';
import { ApiRagFake } from '../../testing/api-rag-fake';
import { Evaluation } from './evaluation';

/**
 * O app é zoneless: `whenStable()` não espera as promises do store (o carregamento dispara num
 * `effect`). Ceder o event loop uma vez deixa as chamadas do dublê resolverem antes da asserção.
 */
async function estabilizar(fixture: { whenStable(): Promise<unknown> }): Promise<void> {
  await fixture.whenStable();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await fixture.whenStable();
}

describe('Evaluation', () => {
  let store: EvaluationStore;
  let api: ApiRagFake;
  const docId = 'lgpd';

  beforeEach(async () => {
    sessionStorage.clear();
    // O jsdom não implementa URLs de blob.
    URL.createObjectURL = vi.fn(() => 'blob:pdf-de-teste');
    URL.revokeObjectURL = vi.fn();
    api = new ApiRagFake();
    await TestBed.configureTestingModule({
      imports: [Evaluation],
      providers: [provideRouter([]), { provide: ApiRag, useValue: api }],
    }).compileComponents();
    store = TestBed.inject(EvaluationStore);
    await store.iniciarSessao('v1');
  });

  it('shows the empty state before any question', async () => {
    // Arrange
    await store.carregarCatalogo();
    const fixture = TestBed.createComponent(Evaluation);
    fixture.componentRef.setInput('docId', docId);

    // Act
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;

    // Assert
    expect(compiled.querySelector('.empty__text')).not.toBeNull();
    expect(compiled.querySelector('.composer')).not.toBeNull();
  });

  it('opens and closes the PDF panel without leaving the pending round', async () => {
    // Arrange
    await store.carregarCatalogo();
    await store.askQuestion(docId, 'O que a lei diz?');
    const fixture = TestBed.createComponent(Evaluation);
    fixture.componentRef.setInput('docId', docId);
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;

    // Act
    compiled.querySelector<HTMLButtonElement>('.head__pdf')!.click();
    await estabilizar(fixture);

    // Assert
    expect(api.pdfsBaixados).toEqual(['11111111-1111-1111-1111-111111111111']);
    expect(compiled.querySelector('iframe')?.getAttribute('src')).toBe('blob:pdf-de-teste');
    expect(compiled.querySelectorAll('.answer__label').length).toBe(4);

    // Act
    compiled.querySelector<HTMLButtonElement>('.pdf .head__pdf')!.click();
    await estabilizar(fixture);

    // Assert
    expect(compiled.querySelector('iframe')).toBeNull();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:pdf-de-teste');
    expect(compiled.querySelectorAll('.answer__label').length).toBe(4);
  });

  it('hides the PDF button when the document has no stored file', async () => {
    // Arrange
    await store.carregarCatalogo();
    const fixture = TestBed.createComponent(Evaluation);
    fixture.componentRef.setInput('docId', 'kubernetes');

    // Act
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;

    // Assert
    expect(compiled.querySelector('.head__title')).not.toBeNull();
    expect(compiled.querySelector('.head__pdf')).toBeNull();
  });

  it('renders the four blind answers of an answered round', async () => {
    // Arrange
    await store.carregarCatalogo();
    await store.askQuestion(docId, 'O que a lei diz?');
    const fixture = TestBed.createComponent(Evaluation);
    fixture.componentRef.setInput('docId', docId);

    // Act
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;

    // Assert
    const rotulos = [...compiled.querySelectorAll('.answer__label')].map((el) => el.textContent);
    expect(rotulos).toEqual(['Resposta A', 'Resposta B', 'Resposta C', 'Resposta D']);
  });

  it('shows the completion banner and hides the composer when the document is done', async () => {
    // Arrange
    api.maxPerguntas = 2;
    await store.carregarCatalogo();
    for (let i = 0; i < 2; i++) {
      const round = (await store.askQuestion(docId, `P${i}`))!;
      await store.chooseAnswer(docId, round.id, 'A');
      await store.confirmarTambemCorretas(docId, round.id, []);
    }
    const fixture = TestBed.createComponent(Evaluation);
    fixture.componentRef.setInput('docId', docId);

    // Act
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;

    // Assert
    expect(compiled.querySelector('.done')?.textContent).toContain('concluído');
    expect(compiled.querySelector('.composer')).toBeNull();
  });

  it('keeps the answers after a choice and asks which others are also correct', async () => {
    // Arrange
    await store.carregarCatalogo();
    await store.askQuestion(docId, 'Primeira pergunta');
    const fixture = TestBed.createComponent(Evaluation);
    fixture.componentRef.setInput('docId', docId);
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;

    // Act
    compiled.querySelector<HTMLButtonElement>('.answer__btn')!.click();
    await estabilizar(fixture);

    // Assert
    expect(api.ultimoRotulo).toBe('A');
    expect(compiled.querySelectorAll('.answer')).toHaveLength(4);
    expect(compiled.querySelector('.answer--chosen .answer__label')?.textContent).toBe(
      'Resposta A',
    );
    expect(compiled.querySelector('.answer__btn')).toBeNull();
    expect(compiled.querySelector('legend')?.textContent).toContain(
      'Alguma das outras respostas também está correta?',
    );
    expect(compiled.querySelectorAll('.answer__marca input[type=checkbox]')).toHaveLength(3);
    expect(compiled.querySelector('.composer')).toBeNull();
    expect(compiled.querySelector('.etapas__contagem')?.textContent).toContain('0 de 10');
  });

  it('moves to the next question only after confirming the marking', async () => {
    // Arrange
    await store.carregarCatalogo();
    await store.askQuestion(docId, 'Primeira pergunta');
    const fixture = TestBed.createComponent(Evaluation);
    fixture.componentRef.setInput('docId', docId);
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;
    compiled.querySelector<HTMLButtonElement>('.answer__btn')!.click();
    await estabilizar(fixture);

    // Act
    compiled.querySelectorAll<HTMLInputElement>('.answer__marca input')[1].click();
    await estabilizar(fixture);
    compiled.querySelector<HTMLButtonElement>('.confirmar')!.click();
    await estabilizar(fixture);

    // Assert
    expect(api.ultimaMarcacao?.rotulos).toEqual(['C']);
    expect(compiled.querySelector('.answer')).toBeNull();
    expect(compiled.querySelector('.composer')).not.toBeNull();
    expect(compiled.querySelector('.etapas__contagem')?.textContent).toContain('1 de 10');
  });

  it('resumes on the marking step after a reload between the two steps', async () => {
    // Arrange: a escolha foi aceita pelo servidor, e a página recarregou antes da marcação.
    await store.carregarCatalogo();
    const round = (await store.askQuestion(docId, 'Primeira pergunta'))!;
    await store.chooseAnswer(docId, round.id, 'C');
    TestBed.resetTestingModule();
    await TestBed.configureTestingModule({
      imports: [Evaluation],
      providers: [provideRouter([]), { provide: ApiRag, useValue: api }],
    }).compileComponents();
    const fixture = TestBed.createComponent(Evaluation);
    fixture.componentRef.setInput('docId', docId);

    // Act
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;

    // Assert
    expect(compiled.querySelector('.answer--chosen .answer__label')?.textContent).toBe(
      'Resposta C',
    );
    expect(compiled.querySelector('legend')).not.toBeNull();
    expect(compiled.querySelector('.composer')).toBeNull();
  });

  it('goes straight to the next question when none is correct, with no second step', async () => {
    // Arrange
    await store.carregarCatalogo();
    await store.askQuestion(docId, 'Primeira pergunta');
    const fixture = TestBed.createComponent(Evaluation);
    fixture.componentRef.setInput('docId', docId);
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;

    // Act
    compiled.querySelector<HTMLButtonElement>('.nenhuma')!.click();
    await estabilizar(fixture);

    // Assert
    expect(api.ultimoRotulo).toBeNull();
    expect(api.ultimaMarcacao).toBeNull();
    expect(compiled.querySelector('legend')).toBeNull();
    expect(compiled.querySelector('.composer')).not.toBeNull();
    expect(compiled.querySelector('.etapas__contagem')?.textContent).toContain('1 de 10');
  });

  it('shows the marking step instead of the completion banner on the last question', async () => {
    // Arrange
    api.maxPerguntas = 1;
    await store.carregarCatalogo();
    const round = (await store.askQuestion(docId, 'Única'))!;
    await store.chooseAnswer(docId, round.id, 'B');
    const fixture = TestBed.createComponent(Evaluation);
    fixture.componentRef.setInput('docId', docId);
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.done')).toBeNull();
    expect(compiled.querySelector('legend')).not.toBeNull();

    // Act
    compiled.querySelector<HTMLInputElement>('.nenhuma-outra input')!.click();
    await estabilizar(fixture);
    compiled.querySelector<HTMLButtonElement>('.confirmar')!.click();
    await estabilizar(fixture);

    // Assert
    expect(api.ultimaMarcacao?.rotulos).toEqual([]);
    expect(compiled.querySelector('.done')?.textContent).toContain('concluído');
  });

  it('shows progress without letting the evaluator go back', async () => {
    // Arrange
    await store.carregarCatalogo();
    const round = (await store.askQuestion(docId, 'Primeira pergunta'))!;
    await store.chooseAnswer(docId, round.id, 'B');
    await store.confirmarTambemCorretas(docId, round.id, ['D']);
    const fixture = TestBed.createComponent(Evaluation);
    fixture.componentRef.setInput('docId', docId);

    // Act
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;

    // Assert
    expect(compiled.querySelectorAll('.no')).toHaveLength(10);
    expect(compiled.querySelectorAll('.no--feita')).toHaveLength(1);
    expect(compiled.querySelector('.etapas button')).toBeNull();
    expect(compiled.querySelector('.etapas__titulo')?.textContent).toContain('Pergunta 2 de 10');
  });

  it('renders a not-found message for an unknown document', async () => {
    // Arrange
    const fixture = TestBed.createComponent(Evaluation);
    fixture.componentRef.setInput('docId', 'inexistente');

    // Act
    await estabilizar(fixture);
    const compiled = fixture.nativeElement as HTMLElement;

    // Assert
    expect(compiled.querySelector('.missing__title')?.textContent).toContain('não encontrado');
  });
});
