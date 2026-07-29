import { computed, inject, Injectable, signal } from '@angular/core';

import {
  MAX_PERGUNTAS,
  type DocumentProgress,
  type QuestionRound,
  type RagDocument,
  type RotuloCego,
} from '../models/evaluation-model';
import { MockRag } from './mock-rag';

/**
 * Estado global da sessão de avaliação, mantido APENAS EM MEMÓRIA (reset ao
 * recarregar a página — decisão de projeto). Implementado com Angular Signals,
 * sem RxJS. Atualizações são imutáveis (cópia, nunca mutação in-place).
 */
@Injectable({ providedIn: 'root' })
export class EvaluationStore {
  private readonly mock = inject(MockRag);

  private readonly _documents = signal<RagDocument[]>(this.mock.getDocuments());
  private readonly _progressByDoc = signal<Record<string, DocumentProgress>>({});

  /** Documentos disponíveis para avaliação. */
  readonly documents = this._documents.asReadonly();

  /** Total de documentos cuja avaliação já foi concluída (10/10). */
  readonly totalConcluidos = computed(
    () =>
      Object.values(this._progressByDoc()).filter(
        (progresso) => this.contarRespondidas(progresso) >= MAX_PERGUNTAS,
      ).length,
  );

  getDocument(docId: string): RagDocument | undefined {
    return this.mock.getDocument(docId);
  }

  rounds(docId: string): QuestionRound[] {
    return this._progressByDoc()[docId]?.rounds ?? [];
  }

  /** Quantas perguntas já foram efetivamente respondidas (escolha feita). */
  answeredCount(docId: string): number {
    return this.contarRespondidas(this._progressByDoc()[docId]);
  }

  remaining(docId: string): number {
    return Math.max(0, MAX_PERGUNTAS - this.answeredCount(docId));
  }

  isComplete(docId: string): boolean {
    return this.answeredCount(docId) >= MAX_PERGUNTAS;
  }

  /** Existe uma rodada aguardando a escolha do avaliador? */
  hasPendingRound(docId: string): boolean {
    return this.rounds(docId).some((round) => !round.escolhaPipeline);
  }

  /**
   * Registra uma nova pergunta e gera as 3 respostas candidatas (cegas). Não é
   * permitido perguntar se o documento já atingiu o limite ou se há uma rodada
   * pendente de escolha. Retorna a rodada criada ou `undefined` se bloqueado.
   */
  askQuestion(docId: string, texto: string): QuestionRound | undefined {
    const pergunta = texto.trim();
    if (!pergunta || this.isComplete(docId) || this.hasPendingRound(docId)) {
      return undefined;
    }

    const round: QuestionRound = {
      id: this.gerarId(),
      pergunta,
      respostas: this.mock.gerarRespostas(pergunta),
    };

    this._progressByDoc.update((mapa) => {
      const atual = mapa[docId]?.rounds ?? [];
      return {
        ...mapa,
        [docId]: { documentId: docId, rounds: [...atual, round] },
      };
    });

    return round;
  }

  /**
   * Registra a escolha do avaliador (rótulo cego) numa rodada, resolvendo o
   * pipeline verdadeiro correspondente. Ignora se a rodada já foi decidida.
   */
  chooseAnswer(docId: string, roundId: string, rotulo: RotuloCego): void {
    this._progressByDoc.update((mapa) => {
      const progresso = mapa[docId];
      if (!progresso) {
        return mapa;
      }

      const rounds = progresso.rounds.map((round) => {
        if (round.id !== roundId || round.escolhaPipeline) {
          return round;
        }
        const escolhida = round.respostas.find((resposta) => resposta.rotuloCego === rotulo);
        if (!escolhida) {
          return round;
        }
        return {
          ...round,
          escolhaPipeline: escolhida.pipeline,
          escolhaRotulo: rotulo,
          escolhidoEm: new Date(),
        } satisfies QuestionRound;
      });

      return { ...mapa, [docId]: { ...progresso, rounds } };
    });
  }

  private contarRespondidas(progresso: DocumentProgress | undefined): number {
    if (!progresso) {
      return 0;
    }
    return progresso.rounds.filter((round) => !!round.escolhaPipeline).length;
  }

  private gerarId(): string {
    return `r-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }
}
