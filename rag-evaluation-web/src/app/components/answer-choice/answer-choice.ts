import { NgTemplateOutlet } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  afterRenderEffect,
  computed,
  inject,
  input,
  linkedSignal,
  output,
  viewChild,
} from '@angular/core';

import {
  aguardaMarcacao,
  type QuestionRound,
  type RotuloCego,
} from '../../models/evaluation-model';
import { MarkdownPipe } from '../../pipes/markdown-pipe';

/**
 * Apresenta as respostas candidatas ÀS CEGAS (rótulos A/B/C/D), em dois passos. No primeiro, o
 * avaliador escolhe a preferida ou indica que nenhuma está correta. Se escolheu uma, no segundo
 * ele indica quais das outras também estão corretas (ou que nenhuma outra está), com a escolhida
 * travada: a marcação complementa a escolha, não a troca. O passo vem da rodada (`escolhidoEm`,
 * `marcadoEm`), e não de estado local, para que um F5 entre os passos retome no segundo. A
 * identidade do pipeline nem chega ao navegador — a API não a envia.
 */
@Component({
  selector: 'app-answer-choice',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgTemplateOutlet, MarkdownPipe],
  templateUrl: './answer-choice.html',
  styleUrl: './answer-choice.css',
})
export class AnswerChoice {
  readonly round = input.required<QuestionRound>();

  /** `null` significa que nenhuma resposta está correta. */
  readonly escolher = output<RotuloCego | null>();
  /** As outras respostas que também estão corretas; lista vazia = nenhuma outra. */
  readonly confirmarMarcacao = output<RotuloCego[]>();
  /** A resposta apareceu na tela: mede se o avaliador chegou a ver as quatro antes de escolher. */
  readonly respostaVista = output<RotuloCego>();

  private readonly perguntaMarcacao = viewChild<ElementRef<HTMLElement>>('perguntaMarcacao');

  protected readonly decidida = computed(() => !!this.round().escolhidoEm);
  protected readonly etapa = computed<'escolha' | 'marcacao' | 'concluida'>(() => {
    const rodada = this.round();
    if (!rodada.escolhidoEm) {
      return 'escolha';
    }
    return aguardaMarcacao(rodada) ? 'marcacao' : 'concluida';
  });

  /** Recomeça vazia a cada rodada. */
  protected readonly marcadas = linkedSignal<string, ReadonlySet<RotuloCego>>({
    source: () => this.round().id,
    computation: () => new Set(),
  });
  protected readonly nenhumaOutra = linkedSignal<string, boolean>({
    source: () => this.round().id,
    computation: () => false,
  });
  protected readonly podeConfirmar = computed(
    () => this.nenhumaOutra() || this.marcadas().size > 0,
  );

  constructor() {
    const elemento = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
    const destruir = inject(DestroyRef);
    afterNextRender(() => {
      if (typeof IntersectionObserver === 'undefined' || this.decidida()) {
        return;
      }
      const observador = new IntersectionObserver(
        (entradas) => {
          for (const entrada of entradas.filter((item) => item.isIntersecting)) {
            this.respostaVista.emit(entrada.target.getAttribute('data-rotulo') as RotuloCego);
            observador.unobserve(entrada.target);
          }
        },
        // Um pedaço já mostra que a resposta entrou na tela; respostas longas nunca cabem inteiras.
        { threshold: 0.2 },
      );
      elemento.querySelectorAll('[data-rotulo]').forEach((item) => observador.observe(item));
      destruir.onDestroy(() => observador.disconnect());
    });

    // Ao entrar no segundo passo (ou retomá-lo depois de um F5), o foco vai para a pergunta, para
    // que o leitor de tela anuncie o que mudou e o teclado parta dali.
    afterRenderEffect(() => {
      if (this.etapa() === 'marcacao') {
        this.perguntaMarcacao()?.nativeElement.focus();
      }
    });
  }

  protected onEscolher(rotulo: RotuloCego | null): void {
    if (this.decidida()) {
      return;
    }
    this.escolher.emit(rotulo);
  }

  protected alternarMarcada(rotulo: RotuloCego, marcada: boolean): void {
    const proximas = new Set(this.marcadas());
    if (marcada) {
      proximas.add(rotulo);
    } else {
      proximas.delete(rotulo);
    }
    this.marcadas.set(proximas);
    if (marcada) {
      this.nenhumaOutra.set(false);
    }
  }

  protected alternarNenhumaOutra(marcada: boolean): void {
    this.nenhumaOutra.set(marcada);
    if (marcada) {
      this.marcadas.set(new Set());
    }
  }

  protected onConfirmar(): void {
    if (this.etapa() !== 'marcacao' || !this.podeConfirmar()) {
      return;
    }
    // Na ordem em que as respostas aparecem, não na ordem dos cliques.
    const rotulos = this.round()
      .respostas.map((resposta) => resposta.rotuloCego)
      .filter((rotulo) => this.marcadas().has(rotulo));
    this.confirmarMarcacao.emit(this.nenhumaOutra() ? [] : rotulos);
  }

  protected marcada(rotulo: RotuloCego): boolean {
    return this.marcadas().has(rotulo);
  }

  protected checado(evento: Event): boolean {
    return (evento.target as HTMLInputElement).checked;
  }
}
