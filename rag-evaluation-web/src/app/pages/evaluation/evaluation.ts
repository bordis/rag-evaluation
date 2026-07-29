import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { AnswerChoice } from '../../components/answer-choice/answer-choice';
import { ChatMessage } from '../../components/chat-message/chat-message';
import { ProgressBadge } from '../../components/progress-badge/progress-badge';
import { MAX_PERGUNTAS, type RotuloCego } from '../../models/evaluation-model';
import { EvaluationStore } from '../../services/evaluation-store';

/**
 * Tela principal: chat estilo pergunta-e-resposta sobre um documento. Para cada
 * pergunta são geradas 3 respostas cegas (A/B/C); o avaliador escolhe a melhor.
 * Limite de {@link MAX_PERGUNTAS} perguntas respondidas por documento.
 */
@Component({
  selector: 'app-evaluation',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, ChatMessage, AnswerChoice, ProgressBadge],
  templateUrl: './evaluation.html',
  styleUrl: './evaluation.css',
})
export class Evaluation {
  private readonly store = inject(EvaluationStore);
  private readonly router = inject(Router);

  /** Vem do parâmetro de rota `:docId` via componentInputBinding. */
  readonly docId = input.required<string>();

  protected readonly maxPerguntas = MAX_PERGUNTAS;
  protected readonly rascunho = signal('');

  protected readonly documento = computed(() => this.store.getDocument(this.docId()));
  protected readonly rounds = computed(() => this.store.rounds(this.docId()));
  protected readonly respondidas = computed(() => this.store.answeredCount(this.docId()));
  protected readonly concluido = computed(() => this.store.isComplete(this.docId()));
  protected readonly pendente = computed(() => this.store.hasPendingRound(this.docId()));

  /** Só é possível perguntar com texto, sem rodada pendente e sem ter concluído. */
  protected readonly podePerguntar = computed(
    () => this.rascunho().trim().length > 0 && !this.pendente() && !this.concluido(),
  );

  /** Próximo documento ainda não concluído (para sugerir após finalizar). */
  protected readonly proximoDocumento = computed(() =>
    this.store.documents().find((doc) => doc.id !== this.docId() && !this.store.isComplete(doc.id)),
  );

  protected perguntar(): void {
    if (!this.podePerguntar()) {
      return;
    }
    this.store.askQuestion(this.docId(), this.rascunho());
    this.rascunho.set('');
  }

  protected onTextarea(evento: Event): void {
    this.rascunho.set((evento.target as HTMLTextAreaElement).value);
  }

  protected onKeydown(evento: KeyboardEvent): void {
    if (evento.key === 'Enter' && !evento.shiftKey) {
      evento.preventDefault();
      this.perguntar();
    }
  }

  protected escolher(roundId: string, rotulo: RotuloCego): void {
    this.store.chooseAnswer(this.docId(), roundId, rotulo);
  }

  protected irParaDocumentos(): void {
    this.router.navigate(['/documentos']);
  }

  protected irParaProximo(): void {
    const proximo = this.proximoDocumento();
    if (proximo) {
      this.router.navigate(['/avaliacao', proximo.id]);
      this.rascunho.set('');
    }
  }
}
