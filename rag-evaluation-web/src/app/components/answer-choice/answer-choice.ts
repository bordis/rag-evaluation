import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import type { QuestionRound, RotuloCego } from '../../models/evaluation-model';

/**
 * Apresenta as respostas candidatas ÀS CEGAS (rótulos A/B/C/D) e permite ao
 * avaliador escolher a preferida. Depois de decidida a rodada, destaca a
 * escolha e desabilita as ações. A identidade do pipeline nem chega ao
 * navegador — a API não a envia.
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

  protected readonly decidida = computed(() => !!this.round().escolhaRotulo);

  protected onEscolher(rotulo: RotuloCego): void {
    if (this.decidida()) {
      return;
    }
    this.escolher.emit(rotulo);
  }
}
