import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { MAX_PERGUNTAS } from '../../models/evaluation-model';

/** Pill "N/total" reutilizável; fica verde (success) quando concluído. */
@Component({
  selector: 'app-progress-badge',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './progress-badge.html',
  styleUrl: './progress-badge.css',
})
export class ProgressBadge {
  readonly respondidas = input.required<number>();
  readonly total = input<number>(MAX_PERGUNTAS);

  protected readonly concluido = computed(() => this.respondidas() >= this.total());
}
