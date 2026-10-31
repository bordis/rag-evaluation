import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

import type { RagDocument } from '../../models/evaluation-model';
import { ProgressBadge } from '../progress-badge/progress-badge';

/** Card selecionável de documento, com o progresso de avaliação (N/10). */
@Component({
  selector: 'app-document-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ProgressBadge],
  templateUrl: './document-card.html',
  styleUrl: './document-card.css',
})
export class DocumentCard {
  readonly documento = input.required<RagDocument>();
  readonly respondidas = input.required<number>();
  readonly total = input.required<number>();

  /** Emite o `slug`, que é o identificador usado na rota `/avaliacao/:docId`. */
  readonly selecionar = output<string>();

  protected onSelecionar(): void {
    this.selecionar.emit(this.documento().slug);
  }
}
