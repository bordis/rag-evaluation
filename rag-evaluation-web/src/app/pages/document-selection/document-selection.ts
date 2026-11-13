import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
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
  /** Documento clicado cuja tela ainda está carregando: o card mostra o spinner. */
  protected readonly abrindo = signal<string | null>(null);

  constructor() {
    void this.store.carregarCatalogo();
  }

  protected respondidas(slug: string): number {
    return this.store.answeredCount(slug);
  }

  protected async abrir(slug: string): Promise<void> {
    if (this.abrindo()) {
      return;
    }
    this.abrindo.set(slug);
    try {
      await this.router.navigate(['/avaliacao', slug]);
    } finally {
      // Navegação cancelada (guard) deixa o avaliador aqui: o card volta ao normal.
      this.abrindo.set(null);
    }
  }

  protected recarregar(): void {
    void this.store.carregarCatalogo();
  }
}
