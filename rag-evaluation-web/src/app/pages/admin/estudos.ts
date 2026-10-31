import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiAdmin, type Estudo } from '../../services/api-admin';

/** Abre e encerra estudos. Só com um estudo aberto o avaliador responde; cada um começa zerado. */
@Component({
  selector: 'app-admin-estudos',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DatePipe],
  templateUrl: './estudos.html',
})
export class AdminEstudos {
  private readonly api = inject(ApiAdmin);

  protected readonly estudos = signal<Estudo[]>([]);
  protected readonly erro = signal<string | null>(null);

  constructor() {
    void this.carregar();
  }

  protected temAberto(): boolean {
    return this.estudos().some((estudo) => estudo.status === 'aberto');
  }

  private async carregar(): Promise<void> {
    try {
      this.estudos.set(await this.api.listarEstudos());
    } catch (erro) {
      this.erro.set((erro as Error).message);
    }
  }

  protected async criar(evento: Event): Promise<void> {
    evento.preventDefault();
    const formulario = evento.target as HTMLFormElement;
    const dados = new FormData(formulario);
    this.erro.set(null);
    try {
      await this.api.criarEstudo(String(dados.get('nome')), String(dados.get('descricao') ?? ''));
      formulario.reset();
      await this.carregar();
    } catch (erro) {
      this.erro.set((erro as Error).message);
    }
  }

  protected async encerrar(estudo: Estudo): Promise<void> {
    if (!confirm(`Encerrar "${estudo.nome}"? Os avaliadores não poderão mais responder.`)) {
      return;
    }
    this.erro.set(null);
    try {
      await this.api.encerrarEstudo(estudo.id);
      await this.carregar();
    } catch (erro) {
      this.erro.set((erro as Error).message);
    }
  }
}
