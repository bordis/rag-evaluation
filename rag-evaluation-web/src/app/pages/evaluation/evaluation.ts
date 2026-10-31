import {
  afterNextRender,
  afterRenderEffect,
  ChangeDetectionStrategy,
  Component,
  computed,
  type ElementRef,
  effect,
  inject,
  Injector,
  type OnDestroy,
  input,
  signal,
  viewChild,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { AnswerChoice } from '../../components/answer-choice/answer-choice';
import { ChatMessage } from '../../components/chat-message/chat-message';
import { ProgressoEtapas } from '../../components/progresso-etapas/progresso-etapas';
import type { RotuloCego } from '../../models/evaluation-model';
import { CronometroRodada } from '../../services/cronometro-rodada';
import { EvaluationStore } from '../../services/evaluation-store';

/** Tamanho mínimo da pergunta — o mesmo que a API valida (`min_length=3`). */
const MIN_PERGUNTA = 3;

/**
 * Tela principal: uma etapa por pergunta do documento. Cada pergunta é respondida por todos os
 * pipelines e apresentada às cegas (A/B/C/D); o avaliador escolhe a melhor ou indica que nenhuma
 * está correta, e a tela passa para a próxima, sem volta. O limite de perguntas é imposto pelo
 * servidor.
 */
@Component({
  selector: 'app-evaluation',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, ChatMessage, AnswerChoice, ProgressoEtapas],
  templateUrl: './evaluation.html',
  styleUrl: './evaluation.css',
})
export class Evaluation implements OnDestroy {
  private readonly store = inject(EvaluationStore);
  private readonly router = inject(Router);
  private readonly cronometro = inject(CronometroRodada);
  private readonly injector = inject(Injector);

  private readonly topo = viewChild<ElementRef<HTMLElement>>('topo');
  private readonly etapa = viewChild<ElementRef<HTMLElement>>('etapa');
  private readonly campoPergunta = viewChild<ElementRef<HTMLTextAreaElement>>('campoPergunta');

  private escolhendo = false;

  /** Vem do parâmetro de rota `:docId` via componentInputBinding — é o `slug` do documento. */
  readonly docId = input.required<string>();

  protected readonly rascunho = signal('');
  /** Mantém a pergunta na tela enquanto as respostas são geradas. */
  protected readonly perguntaEnviada = signal('');

  protected readonly maxPerguntas = this.store.maxPerguntas;
  protected readonly carregando = this.store.carregando;
  protected readonly gerando = this.store.gerando;
  protected readonly erro = this.store.erro;

  protected readonly documento = computed(() => this.store.getDocument(this.docId()));
  private readonly rounds = computed(() => this.store.rounds(this.docId()));
  protected readonly decididas = computed(() => this.rounds().filter((item) => item.escolhidoEm));
  protected readonly rodadaPendente = computed(() =>
    this.rounds().find((item) => !item.escolhidoEm),
  );
  protected readonly concluido = computed(() => this.store.isComplete(this.docId()));

  protected readonly tela = computed(() => {
    if (this.concluido()) {
      return 'concluido';
    }
    if (this.rodadaPendente()) {
      return 'respostas';
    }
    if (this.gerando()) {
      return 'gerando';
    }
    return this.carregando() ? 'carregando' : 'pergunta';
  });

  private readonly chaveDaTela = computed(() => `${this.tela()}-${this.decididas().length}`);

  /** Só é possível perguntar com texto suficiente, na tela de pergunta. */
  protected readonly podePerguntar = computed(
    () => this.rascunho().trim().length >= MIN_PERGUNTA && this.tela() === 'pergunta',
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
      void this.store.abrirDocumento(this.docId());
    });

    // A entrada de cada etapa. O `?.` cobre o jsdom, que não tem essas APIs.
    afterRenderEffect(() => {
      this.chaveDaTela();
      if (!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
        this.etapa()?.nativeElement.animate?.(
          [
            { opacity: 0, transform: 'translateX(16px)' },
            { opacity: 1, transform: 'none' },
          ],
          { duration: 350, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' },
        );
      }
    });
  }

  /** Fora desta tela o avaliador não está respondendo: o tempo conta como ausência. */
  ngOnDestroy(): void {
    this.cronometro.pausar();
  }

  protected async perguntar(): Promise<void> {
    if (!this.podePerguntar()) {
      return;
    }
    const texto = this.rascunho();
    this.rascunho.set('');
    this.perguntaEnviada.set(texto.trim());
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

  protected async escolher(roundId: string, rotulo: RotuloCego | null): Promise<void> {
    // Um segundo clique antes da resposta do servidor viraria um 409 na tela.
    if (this.escolhendo) {
      return;
    }
    this.escolhendo = true;
    try {
      await this.store.chooseAnswer(this.docId(), roundId, rotulo);
    } finally {
      this.escolhendo = false;
    }
    if (!this.erro()) {
      this.irParaOTopo();
    }
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

  private irParaOTopo(): void {
    this.depoisDeRenderizar(() => {
      this.topo()?.nativeElement.scrollIntoView?.();
      this.campoPergunta()?.nativeElement.focus({ preventScroll: true });
    });
  }

  private depoisDeRenderizar(acao: () => void): void {
    afterNextRender(acao, { injector: this.injector });
  }
}
