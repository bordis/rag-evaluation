import { TestBed } from '@angular/core/testing';

import type { RotuloCego } from '../models/evaluation-model';
import { ApiRagFake } from '../testing/api-rag-fake';
import { ApiRag } from './api-rag';
import { EvaluationStore } from './evaluation-store';

describe('EvaluationStore', () => {
  let store: EvaluationStore;
  let api: ApiRagFake;
  const docId = 'lgpd';

  beforeEach(async () => {
    // Arrange
    sessionStorage.clear();
    api = new ApiRagFake();
    TestBed.configureTestingModule({
      providers: [{ provide: ApiRag, useValue: api }],
    });
    store = TestBed.inject(EvaluationStore);
    await store.iniciarSessao('v1');
    await store.carregarCatalogo();
  });

  it('creates the session on the server and keeps only its id in sessionStorage', () => {
    // Assert
    expect(store.sessionId()).toBe('sessao-de-teste');
    expect(sessionStorage.getItem('rag-evaluation.session-id')).toBe('sessao-de-teste');
    expect(store.documents().map((doc) => doc.slug)).toEqual(['lgpd', 'kubernetes']);
  });

  it('askQuestion appends a round with four blind A/B/C/D labels', async () => {
    // Act
    const round = await store.askQuestion(docId, 'O que é isto?');

    // Assert
    expect(round).toBeDefined();
    expect(round!.respostas).toHaveLength(4);
    expect(round!.respostas.map((r) => r.rotuloCego)).toEqual(['A', 'B', 'C', 'D']);
    expect(round!.escolhaRotulo).toBeUndefined();
    expect(store.rounds(docId)).toHaveLength(1);
  });

  it('blocks a new question while a round is pending choice', async () => {
    // Arrange
    await store.askQuestion(docId, 'Primeira?');

    // Act
    const segunda = await store.askQuestion(docId, 'Segunda?');

    // Assert
    expect(segunda).toBeUndefined();
    expect(store.rounds(docId)).toHaveLength(1);
  });

  it('chooseAnswer records the label and advances the progress reported by the server', async () => {
    // Arrange
    const round = (await store.askQuestion(docId, 'Pergunta?'))!;
    const alvo: RotuloCego = 'B';

    // Act
    await store.chooseAnswer(docId, round.id, alvo);

    // Assert: decidida conta no limite, mas a rodada só fica completa com a marcação.
    expect(store.rounds(docId)[0].escolhaRotulo).toBe(alvo);
    expect(store.answeredCount(docId)).toBe(1);
    expect(store.hasPendingRound(docId)).toBe(true);
    expect(await store.askQuestion(docId, 'Outra?')).toBeUndefined();
  });

  it('confirmarTambemCorretas completes the round and frees the next question', async () => {
    // Arrange
    const round = (await store.askQuestion(docId, 'Pergunta?'))!;
    await store.chooseAnswer(docId, round.id, 'B');

    // Act: a escolhida e repetições não vão no corpo.
    await store.confirmarTambemCorretas(docId, round.id, ['D', 'B', 'A', 'D']);

    // Assert
    expect(api.ultimaMarcacao?.roundId).toBe(round.id);
    expect(api.ultimaMarcacao?.rotulos).toEqual(['D', 'A']);
    expect(store.rounds(docId)[0].tambemCorretas).toEqual(['D', 'A']);
    expect(store.rounds(docId)[0].marcadoEm).toBeDefined();
    expect(store.hasPendingRound(docId)).toBe(false);
    expect(await store.askQuestion(docId, 'Próxima?')).toBeDefined();
  });

  it('sends an empty list when no other answer is correct', async () => {
    // Arrange
    const round = (await store.askQuestion(docId, 'Pergunta?'))!;
    await store.chooseAnswer(docId, round.id, 'A');

    // Act
    await store.confirmarTambemCorretas(docId, round.id, []);

    // Assert
    expect(api.ultimaMarcacao?.rotulos).toEqual([]);
    expect(store.rounds(docId)[0].tambemCorretas).toEqual([]);
    expect(store.hasPendingRound(docId)).toBe(false);
  });

  it('does not mark a round that is undecided, "none" or already marked', async () => {
    // Arrange
    const pendente = (await store.askQuestion(docId, 'Pergunta?'))!;

    // Act / Assert
    await store.confirmarTambemCorretas(docId, pendente.id, ['A']);
    expect(api.ultimaMarcacao).toBeNull();

    await store.chooseAnswer(docId, pendente.id, null);
    await store.confirmarTambemCorretas(docId, pendente.id, ['A']);
    expect(api.ultimaMarcacao).toBeNull();
  });

  it('surfaces a marking failure in erro() and keeps the round waiting', async () => {
    // Arrange
    const round = (await store.askQuestion(docId, 'Pergunta?'))!;
    await store.chooseAnswer(docId, round.id, 'A');
    api.falha = new Error('Esta rodada já foi marcada.');

    // Act
    await store.confirmarTambemCorretas(docId, round.id, ['B']);

    // Assert
    expect(store.erro()).toBe('Esta rodada já foi marcada.');
    expect(store.hasPendingRound(docId)).toBe(true);
  });

  it('sends the marking time apart from the round time', async () => {
    // Arrange
    await store.abrirDocumento(docId);
    const round = (await store.askQuestion(docId, 'Pergunta?'))!;
    await store.chooseAnswer(docId, round.id, 'C');

    // Act
    await store.confirmarTambemCorretas(docId, round.id, ['A']);

    // Assert
    expect(api.ultimaMarcacao?.tempos?.totalMs).toBeGreaterThanOrEqual(0);
    expect(api.ultimaMarcacao?.tempos?.ocultoMs).toBe(0);
  });

  it('marks the document complete once the server reports MAX_PERGUNTAS answers', async () => {
    // Arrange
    api.maxPerguntas = 3;

    // Act
    for (let i = 0; i < 3; i++) {
      const round = (await store.askQuestion(docId, `Pergunta ${i}?`))!;
      await store.chooseAnswer(docId, round.id, 'A');
      await store.confirmarTambemCorretas(docId, round.id, []);
    }

    // Assert
    expect(store.answeredCount(docId)).toBe(3);
    expect(store.isComplete(docId)).toBe(true);
    expect(store.remaining(docId)).toBe(0);
    expect(store.totalConcluidos()).toBe(1);
    expect(await store.askQuestion(docId, 'Uma a mais?')).toBeUndefined();
  });

  it('keeps progress isolated per document', async () => {
    // Arrange
    const round = (await store.askQuestion(docId, 'Pergunta?'))!;

    // Act
    await store.chooseAnswer(docId, round.id, 'A');

    // Assert
    expect(store.answeredCount(docId)).toBe(1);
    expect(store.answeredCount('kubernetes')).toBe(0);
    expect(store.isComplete('kubernetes')).toBe(false);
  });

  it('surfaces the API failure message instead of throwing', async () => {
    // Arrange
    api.falha = new Error('Não foi possível falar com o servidor.');

    // Act
    const round = await store.askQuestion(docId, 'Pergunta?');

    // Assert
    expect(round).toBeUndefined();
    expect(store.erro()).toBe('Não foi possível falar com o servidor.');
    expect(store.gerando()).toBe(false);
  });

  it('reuses the session id already stored instead of creating another one', async () => {
    // Arrange
    sessionStorage.setItem('rag-evaluation.session-id', 'sessao-anterior');
    const outraApi = new ApiRagFake();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ providers: [{ provide: ApiRag, useValue: outraApi }] });
    const outroStore = TestBed.inject(EvaluationStore);

    // Act
    const sessionId = await outroStore.iniciarSessao('v1');

    // Assert
    expect(sessionId).toBe('sessao-anterior');
    expect(outraApi.termoRecebido).toBeNull();
  });

  it('records "none is correct" as a decision without a chosen label', async () => {
    // Arrange
    const round = (await store.askQuestion(docId, 'Pergunta?'))!;

    // Act
    await store.chooseAnswer(docId, round.id, null);

    // Assert
    expect(api.ultimoRotulo).toBeNull();
    expect(store.rounds(docId)[0].nenhumaCorreta).toBe(true);
    expect(store.answeredCount(docId)).toBe(1);
    expect(store.hasPendingRound(docId)).toBe(false);
  });

  it('sends the round timing measured in the browser with the choice', async () => {
    // Arrange
    await store.abrirDocumento(docId);
    const round = (await store.askQuestion(docId, 'Pergunta?'))!;

    // Act
    await store.chooseAnswer(docId, round.id, 'A');

    // Assert
    expect(api.temposRecebidos?.totalMs).toBeGreaterThanOrEqual(0);
    expect(api.temposRecebidos?.geracaoMs).toBeGreaterThanOrEqual(0);
    expect(api.temposRecebidos?.ocultoMs).toBe(0);
  });

  it('discards a session whose study has closed', async () => {
    // Arrange
    api.estudoAberto = false;

    // Act
    const valida = await store.sessaoValida();

    // Assert
    expect(valida).toBe(false);
    expect(store.sessionId()).toBeNull();
    expect(sessionStorage.getItem('rag-evaluation.session-id')).toBeNull();
  });

  it('recovers the session this login already has on the server (term accepted elsewhere)', async () => {
    // Arrange
    sessionStorage.clear();
    const outraApi = new ApiRagFake();
    outraApi.sessaoDoLogin = 'sessao-do-login';
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ providers: [{ provide: ApiRag, useValue: outraApi }] });
    const outroStore = TestBed.inject(EvaluationStore);

    // Act
    const valida = await outroStore.sessaoValida();

    // Assert
    expect(valida).toBe(true);
    expect(outroStore.sessionId()).toBe('sessao-do-login');
    expect(sessionStorage.getItem('rag-evaluation.session-id')).toBe('sessao-do-login');
  });

  it('is not valid when this login never accepted the term', async () => {
    // Arrange
    sessionStorage.clear();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [{ provide: ApiRag, useValue: new ApiRagFake() }],
    });
    const outroStore = TestBed.inject(EvaluationStore);

    // Act / Assert
    expect(await outroStore.sessaoValida()).toBe(false);
    expect(outroStore.sessionId()).toBeNull();
  });
});
