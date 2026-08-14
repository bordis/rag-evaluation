import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Router } from '@angular/router';

import { DocumentCard } from '../../components/document-card/document-card';
import { EvaluationStore } from '../../services/evaluation-store';

/** Grid dos documentos prontos na API, cada um com o progresso da sessão atual. */
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
  protected readonly carregando = this.store.carregando;
  protected readonly erro = this.store.erro;
  protected readonly maxPerguntas = this.store.maxPerguntas;

  constructor() {
    void this.store.carregarCatalogo();
  }

  protected respondidas(slug: string): number {
    return this.store.answeredCount(slug);
  }

  protected abrir(slug: string): void {
    this.router.navigate(['/avaliacao', slug]);
  }

  protected recarregar(): void {
    void this.store.carregarCatalogo();
  }
}
