import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';

import { MAX_PERGUNTAS } from '../../models/evaluation-model';
import { EvaluationStore } from '../../services/evaluation-store';
import { Evaluation } from './evaluation';

describe('Evaluation', () => {
  let store: EvaluationStore;
  let docId: string;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Evaluation],
      providers: [provideRouter([])],
    }).compileComponents();
    store = TestBed.inject(EvaluationStore);
    docId = store.documents()[0].id;
  });

  it('shows the empty state before any question', async () => {
    // Arrange
    const fixture = TestBed.createComponent(Evaluation);
    fixture.componentRef.setInput('docId', docId);

    // Act
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;

    // Assert
    expect(compiled.querySelector('.empty')).not.toBeNull();
    expect(compiled.querySelector('.composer')).not.toBeNull();
  });

  it('shows the completion banner and hides the composer when the document is done', async () => {
    // Arrange
    for (let i = 0; i < MAX_PERGUNTAS; i++) {
      const round = store.askQuestion(docId, `P${i}`)!;
      store.chooseAnswer(docId, round.id, 'A');
    }
    const fixture = TestBed.createComponent(Evaluation);
    fixture.componentRef.setInput('docId', docId);

    // Act
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;

    // Assert
    expect(compiled.querySelector('.done')?.textContent).toContain('concluído');
    expect(compiled.querySelector('.composer')).toBeNull();
  });

  it('renders a not-found message for an unknown document', async () => {
    // Arrange
    const fixture = TestBed.createComponent(Evaluation);
    fixture.componentRef.setInput('docId', 'inexistente');

    // Act
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;

    // Assert
    expect(compiled.querySelector('.missing__title')?.textContent).toContain('não encontrado');
  });
});
