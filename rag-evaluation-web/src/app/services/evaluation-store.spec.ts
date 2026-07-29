import { TestBed } from '@angular/core/testing';

import { MAX_PERGUNTAS, type RotuloCego } from '../models/evaluation-model';
import { EvaluationStore } from './evaluation-store';

describe('EvaluationStore', () => {
  let store: EvaluationStore;
  let docId: string;

  beforeEach(() => {
    // Arrange
    TestBed.configureTestingModule({});
    store = TestBed.inject(EvaluationStore);
    docId = store.documents()[0].id;
  });

  it('askQuestion generates 3 blind answers with distinct A/B/C labels', () => {
    // Act
    const round = store.askQuestion(docId, 'O que é isto?');

    // Assert
    expect(round).toBeDefined();
    expect(round!.respostas).toHaveLength(3);
    const rotulos = round!.respostas.map((r) => r.rotuloCego).sort();
    expect(rotulos).toEqual(['A', 'B', 'C']);
    const pipelines = new Set(round!.respostas.map((r) => r.pipeline));
    expect(pipelines.size).toBe(3);
    expect(round!.escolhaPipeline).toBeUndefined();
  });

  it('blocks a new question while a round is pending choice', () => {
    // Arrange
    store.askQuestion(docId, 'Primeira?');

    // Act
    const segunda = store.askQuestion(docId, 'Segunda?');

    // Assert
    expect(segunda).toBeUndefined();
    expect(store.rounds(docId)).toHaveLength(1);
  });

  it('chooseAnswer records the true pipeline and increments progress', () => {
    // Arrange
    const round = store.askQuestion(docId, 'Pergunta?')!;
    const alvo: RotuloCego = 'B';
    const esperado = round.respostas.find((r) => r.rotuloCego === alvo)!.pipeline;

    // Act
    store.chooseAnswer(docId, round.id, alvo);

    // Assert
    const atualizado = store.rounds(docId)[0];
    expect(atualizado.escolhaRotulo).toBe(alvo);
    expect(atualizado.escolhaPipeline).toBe(esperado);
    expect(store.answeredCount(docId)).toBe(1);
    expect(store.hasPendingRound(docId)).toBe(false);
  });

  it('marks the document complete after MAX_PERGUNTAS answered rounds', () => {
    // Act
    for (let i = 0; i < MAX_PERGUNTAS; i++) {
      const round = store.askQuestion(docId, `Pergunta ${i}?`)!;
      store.chooseAnswer(docId, round.id, 'A');
    }

    // Assert
    expect(store.answeredCount(docId)).toBe(MAX_PERGUNTAS);
    expect(store.isComplete(docId)).toBe(true);
    expect(store.remaining(docId)).toBe(0);
    expect(store.totalConcluidos()).toBe(1);
  });

  it('does not allow more questions once the document is complete', () => {
    // Arrange
    for (let i = 0; i < MAX_PERGUNTAS; i++) {
      const round = store.askQuestion(docId, `P${i}`)!;
      store.chooseAnswer(docId, round.id, 'A');
    }

    // Act
    const extra = store.askQuestion(docId, 'Uma a mais?');

    // Assert
    expect(extra).toBeUndefined();
    expect(store.rounds(docId)).toHaveLength(MAX_PERGUNTAS);
  });

  it('keeps progress isolated per document', () => {
    // Arrange
    const outroDoc = store.documents()[1].id;
    const round = store.askQuestion(docId, 'Pergunta?')!;
    store.chooseAnswer(docId, round.id, 'A');

    // Assert
    expect(store.answeredCount(docId)).toBe(1);
    expect(store.answeredCount(outroDoc)).toBe(0);
    expect(store.isComplete(outroDoc)).toBe(false);
  });
});
