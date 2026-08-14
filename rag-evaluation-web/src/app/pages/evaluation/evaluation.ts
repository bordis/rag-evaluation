import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { AnswerChoice } from '../../components/answer-choice/answer-choice';
import { ChatMessage } from '../../components/chat-message/chat-message';
import { ProgressBadge } from '../../components/progress-badge/progress-badge';
import type { RotuloCego } from '../../models/evaluation-model';
import { EvaluationStore } from '../../services/evaluation-store';

/** Tamanho mínimo da pergunta — o mesmo que a API valida (`min_length=3`). */
const MIN_PERGUNTA = 3;

/**
 * Tela principal: chat pergunta-e-resposta sobre um documento. Cada pergunta é respondida por
 * todos os pipelines e apresentada às cegas (A/B/C/D); o avaliador escolhe a melhor. O limite de
 * perguntas por documento é imposto pelo servidor.
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

  /** Vem do parâmetro de rota `:docId` via componentInputBinding — é o `slug` do documento. */
  readonly docId = input.required<string>();

  protected readonly rascunho = signal('');

  protected readonly maxPerguntas = this.store.maxPerguntas;
  protected readonly carregando = this.store.carregando;
  protected readonly gerando = this.store.gerando;
  protected readonly erro = this.store.erro;

  protected readonly documento = computed(() => this.store.getDocument(this.docId()));
  protected readonly rounds = computed(() => this.store.rounds(this.docId()));
  protected readonly respondidas = computed(() => this.store.answeredCount(this.docId()));
  protected readonly concluido = computed(() => this.store.isComplete(this.docId()));
  protected readonly pendente = computed(() => this.store.hasPendingRound(this.docId()));

  /** Só é possível perguntar com texto suficiente, sem rodada pendente e sem ter concluído. */
  protected readonly podePerguntar = computed(
    () =>
      this.rascunho().trim().length >= MIN_PERGUNTA &&
      !this.pendente() &&
      !this.concluido() &&
      !this.gerando(),
  );

  /** Próximo documento ainda não concluído (para sugerir após finalizar). */
  protected readonly proximoDocumento = computed(() =>
    this.store
      .documents()
      .find((doc) => doc.slug !== this.docId() && !this.store.isComplete(doc.slug)),
  );

  constructor() {
    // O documento pode mudar sem recriar o componente (navegação entre `/avaliacao/:docId`),
    // então a carga acompanha o input em vez de rodar uma vez na construção.
    effect(() => {
      const slug = this.docId();
      void this.store.abrirDocumento(slug);
    });
  }

  protected async perguntar(): Promise<void> {
    if (!this.podePerguntar()) {
      return;
    }
    const texto = this.rascunho();
    this.rascunho.set('');
    const rodada = await this.store.askQuestion(this.docId(), texto);
    if (!rodada) {
      // Falhou (rede, timeout de pipeline): devolve o texto para o avaliador não reescrever.
      this.rascunho.set(texto);
    }
  }

  protected onTextarea(evento: Event): void {
    this.rascunho.set((evento.target as HTMLTextAreaElement).value);
  }

  protected onKeydown(evento: KeyboardEvent): void {
    if (evento.key === 'Enter' && !evento.shiftKey) {
      evento.preventDefault();
      void this.perguntar();
    }
  }

  protected escolher(roundId: string, rotulo: RotuloCego): void {
    void this.store.chooseAnswer(this.docId(), roundId, rotulo);
  }

  protected irParaDocumentos(): void {
    this.router.navigate(['/documentos']);
  }

  protected irParaProximo(): void {
    const proximo = this.proximoDocumento();
    if (proximo) {
      this.router.navigate(['/avaliacao', proximo.slug]);
      this.rascunho.set('');
    }
  }
}
