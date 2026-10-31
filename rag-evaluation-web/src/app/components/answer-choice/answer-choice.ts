import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

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

  protected readonly decidida = computed(() => !!this.round().escolhidoEm);

  protected onEscolher(rotulo: RotuloCego | null): void {
    if (this.decidida()) {
      return;
    }
    this.escolher.emit(rotulo);
  }
}
