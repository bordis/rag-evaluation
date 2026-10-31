import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiAdmin, type AvaliacaoResumo } from '../../services/api-admin';

/** Os ciclos de um estudo: cada linha é um avaliador em um documento. */
@Component({
  selector: 'app-admin-avaliacoes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DatePipe],
  templateUrl: './avaliacoes.html',
})
export class AdminAvaliacoes {
  private readonly api = inject(ApiAdmin);

  readonly studyId = input.required<string>();

  protected readonly avaliacoes = signal<AvaliacaoResumo[]>([]);
  protected readonly erro = signal<string | null>(null);

  constructor() {
    effect(() => {
      this.api
        .listarAvaliacoes(this.studyId())
        .then((itens) => this.avaliacoes.set(itens))
        .catch((erro: Error) => this.erro.set(erro.message));
    });
  }
}
