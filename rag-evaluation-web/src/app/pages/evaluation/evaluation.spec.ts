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

  it('clears the screen and moves to the next question after a choice', async () => {
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
    expect(compiled.querySelector('.answer')).toBeNull();
    expect(compiled.querySelector('.composer')).not.toBeNull();
    expect(compiled.querySelector('.etapas__contagem')?.textContent).toContain('1 de 10');
  });

  it('shows progress without letting the evaluator go back', async () => {
    // Arrange
    await store.carregarCatalogo();
    const round = (await store.askQuestion(docId, 'Primeira pergunta'))!;
    await store.chooseAnswer(docId, round.id, 'B');
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
