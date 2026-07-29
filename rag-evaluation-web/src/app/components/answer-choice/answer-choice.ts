import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import type { QuestionRound, RotuloCego } from '../../models/evaluation-model';

/**
 * Apresenta as 3 respostas candidatas ÀS CEGAS (rótulos A/B/C) e permite ao
 * avaliador escolher a preferida. Depois de decidida a rodada, destaca a
 * escolha e desabilita as ações. Nunca revela o pipeline verdadeiro.
 */
@Component({
  selector: 'app-answer-choice',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './answer-choice.html',
  styleUrl: './answer-choice.css',
})
export class AnswerChoice {
  readonly round = input.required<QuestionRound>();

  readonly escolher = output<RotuloCego>();

  protected readonly decidida = computed(() => !!this.round().escolhaPipeline);

  protected onEscolher(rotulo: RotuloCego): void {
    if (this.decidida()) {
      return;
    }
    this.escolher.emit(rotulo);
  }
}
