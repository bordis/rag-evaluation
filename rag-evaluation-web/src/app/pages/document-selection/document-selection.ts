import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Router } from '@angular/router';

import { DocumentCard } from '../../components/document-card/document-card';
import { EvaluationStore } from '../../services/evaluation-store';

/** Grid de documentos disponíveis, cada um com seu progresso de avaliação. */
@Component({
  selector: 'app-document-selection',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DocumentCard],
  templateUrl: './document-selection.html',
  styleUrl: './document-selection.css',
})
export class DocumentSelection {
  private readonly store = inject(EvaluationStore);
  private readonly router = inject(Router);

  protected readonly documentos = this.store.documents;
  protected readonly totalConcluidos = this.store.totalConcluidos;

  protected respondidas(docId: string): number {
    return this.store.answeredCount(docId);
  }

  protected abrir(docId: string): void {
    this.router.navigate(['/avaliacao', docId]);
  }
}
