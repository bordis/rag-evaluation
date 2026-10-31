import { ChangeDetectionStrategy, Component, inject, type OnDestroy, signal } from '@angular/core';

import { ApiAdmin, type DocumentoAdmin, type Ingestao } from '../../services/api-admin';

const INTERVALO_ATUALIZACAO_MS = 5000;

/** Acervo: o admin envia os PDFs digitais e acompanha a ingestão nos quatro pipelines. */
@Component({
  selector: 'app-admin-documentos',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './documentos.html',
})
export class AdminDocumentos implements OnDestroy {
  private readonly api = inject(ApiAdmin);
  private readonly temporizador = setInterval(
    () => void this.atualizar(),
    INTERVALO_ATUALIZACAO_MS,
  );

  protected readonly documentos = signal<DocumentoAdmin[]>([]);
  protected readonly ingestoes = signal<Ingestao[]>([]);
  protected readonly aberto = signal<string | null>(null);
  protected readonly enviando = signal(false);
  protected readonly erro = signal<string | null>(null);

  constructor() {
    void this.atualizar();
  }

  ngOnDestroy(): void {
    clearInterval(this.temporizador);
  }

  /** A ingestão roda em segundo plano e leva minutos: a tabela acompanha sozinha. */
  private async atualizar(): Promise<void> {
    try {
      this.documentos.set(await this.api.listarDocumentos());
      const aberto = this.aberto();
      if (aberto) {
        this.ingestoes.set(await this.api.listarIngestoes(aberto));
      }
    } catch (erro) {
      this.erro.set((erro as Error).message);
    }
  }

  protected async enviar(evento: Event): Promise<void> {
    evento.preventDefault();
    const formulario = evento.target as HTMLFormElement;
    this.erro.set(null);
    this.enviando.set(true);
    try {
      await this.api.enviarDocumento(new FormData(formulario));
      formulario.reset();
      await this.atualizar();
    } catch (erro) {
      this.erro.set((erro as Error).message);
    } finally {
      this.enviando.set(false);
    }
  }

  protected async verIngestoes(documento: DocumentoAdmin): Promise<void> {
    if (this.aberto() === documento.id) {
      this.aberto.set(null);
      return;
    }
    this.aberto.set(documento.id);
    await this.atualizar();
  }

  protected async excluir(documento: DocumentoAdmin): Promise<void> {
    if (!confirm(`Excluir "${documento.titulo}" do acervo e do Milvus?`)) {
      return;
    }
    this.erro.set(null);
    try {
      await this.api.excluirDocumento(documento.id);
      await this.atualizar();
    } catch (erro) {
      this.erro.set((erro as Error).message);
    }
  }
}
