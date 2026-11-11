import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  computed,
  inject,
  input,
  output,
} from '@angular/core';

import type { QuestionRound, RotuloCego } from '../../models/evaluation-model';
import { MarkdownPipe } from '../../pipes/markdown-pipe';

/**
 * Apresenta as respostas candidatas ÀS CEGAS (rótulos A/B/C/D) e permite ao
 * avaliador escolher a preferida ou indicar que nenhuma está correta. Depois de decidida a rodada, destaca a
 * escolha e desabilita as ações. A identidade do pipeline nem chega ao
 * navegador — a API não a envia.
 */
@Component({
  selector: 'app-answer-choice',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MarkdownPipe],
  templateUrl: './answer-choice.html',
  styleUrl: './answer-choice.css',
})
export class AnswerChoice {
  readonly round = input.required<QuestionRound>();

  /** `null` significa que nenhuma resposta está correta. */
  readonly escolher = output<RotuloCego | null>();
  /** A resposta apareceu na tela: mede se o avaliador chegou a ver as quatro antes de escolher. */
  readonly respostaVista = output<RotuloCego>();

  protected readonly decidida = computed(() => !!this.round().escolhidoEm);

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
  }

  protected onEscolher(rotulo: RotuloCego | null): void {
    if (this.decidida()) {
      return;
    }
    this.escolher.emit(rotulo);
  }
}
