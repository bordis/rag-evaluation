import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import type {
  Familiaridade,
  PerfilAvaliador,
  TempoExperiencia,
} from '../../models/evaluation-model';
import { EvaluationStore } from '../../services/evaluation-store';

/**
 * Perfil opcional do avaliador. É aqui que a sessão é criada no servidor — e é a única vez em
 * que esses dados são pedidos. Nada aqui é obrigatório: quem preferir pode simplesmente pular,
 * e a sessão nasce anônima.
 */
@Component({
  selector: 'app-profile',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './profile.html',
  styleUrl: './profile.css',
})
export class Profile {
  private readonly store = inject(EvaluationStore);
  private readonly router = inject(Router);

  protected readonly erro = this.store.erro;
  protected readonly enviando = signal(false);

  protected readonly areaAtuacao = signal('');
  protected readonly familiaridade = signal<Familiaridade | ''>('');
  protected readonly tempoExperiencia = signal<TempoExperiencia | ''>('');

  protected readonly familiaridades: ReadonlyArray<{ valor: Familiaridade; rotulo: string }> = [
    { valor: 'baixa', rotulo: 'Baixa — conheço pouco o assunto' },
    { valor: 'media', rotulo: 'Média — conheço o suficiente' },
    { valor: 'alta', rotulo: 'Alta — trabalho com isso' },
  ];

  protected readonly tempos: ReadonlyArray<{ valor: TempoExperiencia; rotulo: string }> = [
    { valor: 'ate-2-anos', rotulo: 'Até 2 anos' },
    { valor: '2-5-anos', rotulo: 'De 2 a 5 anos' },
    { valor: '5-10-anos', rotulo: 'De 5 a 10 anos' },
    { valor: 'mais-10-anos', rotulo: 'Mais de 10 anos' },
  ];

  protected onArea(evento: Event): void {
    this.areaAtuacao.set((evento.target as HTMLInputElement).value);
  }

  protected onFamiliaridade(evento: Event): void {
    this.familiaridade.set((evento.target as HTMLSelectElement).value as Familiaridade | '');
  }

  protected onTempo(evento: Event): void {
    this.tempoExperiencia.set((evento.target as HTMLSelectElement).value as TempoExperiencia | '');
  }

  protected async continuar(): Promise<void> {
    if (this.enviando()) {
      return;
    }
    const perfil: PerfilAvaliador = {
      areaAtuacao: this.areaAtuacao().trim() || undefined,
      familiaridade: this.familiaridade() || undefined,
      tempoExperiencia: this.tempoExperiencia() || undefined,
    };

    this.enviando.set(true);
    try {
      const sessionId = await this.store.garantirSessao(perfil);
      if (sessionId) {
        this.router.navigate(['/documentos']);
      }
    } finally {
      this.enviando.set(false);
    }
  }

  protected pular(): void {
    this.areaAtuacao.set('');
    this.familiaridade.set('');
    this.tempoExperiencia.set('');
    void this.continuar();
  }
}
