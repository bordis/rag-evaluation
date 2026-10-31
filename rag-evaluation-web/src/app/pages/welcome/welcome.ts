import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import type { EstudoAtual } from '../../models/evaluation-model';
import { TERMO_PARAGRAFOS, TERMO_VERSAO } from '../../models/termo';
import { ApiRag } from '../../services/api-rag';
import { EvaluationStore } from '../../services/evaluation-store';

/** Boas-vindas: explicação do processo e aceite do termo, que é o que cria a sessão. */
@Component({
  selector: 'app-welcome',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './welcome.html',
  styleUrl: './welcome.css',
})
export class Welcome {
  private readonly api = inject(ApiRag);
  private readonly store = inject(EvaluationStore);
  private readonly router = inject(Router);

  protected readonly termo = TERMO_PARAGRAFOS;
  protected readonly aceite = signal(false);
  protected readonly enviando = signal(false);
  protected readonly carregando = signal(true);
  protected readonly estudo = signal<EstudoAtual | null>(null);
  protected readonly erro = signal<string | null>(null);

  protected readonly passos = [
    {
      numero: '1',
      titulo: 'Escolha um documento',
      texto:
        'Selecione, entre os documentos disponíveis, aquele sobre o qual você tem mais conhecimento.',
    },
    {
      numero: '2',
      titulo: 'Faça perguntas',
      texto:
        'Converse com o documento como em um chat. Você pode fazer até 10 perguntas por documento.',
    },
    {
      numero: '3',
      titulo: 'Escolha a melhor resposta',
      texto:
        'Para cada pergunta, apresentamos 4 respostas anônimas (A, B, C e D). Escolha a melhor ou indique que nenhuma está correta.',
    },
  ];

  constructor() {
    void this.carregar();
  }

  private async carregar(): Promise<void> {
    try {
      this.estudo.set(await this.api.obterEstudoAtual());
    } catch (erro) {
      this.erro.set(erro instanceof Error ? erro.message : 'Falha inesperada.');
    } finally {
      this.carregando.set(false);
    }
  }

  protected onAceite(evento: Event): void {
    this.aceite.set((evento.target as HTMLInputElement).checked);
  }

  protected async comecar(): Promise<void> {
    if (!this.aceite() || this.enviando()) {
      return;
    }
    this.enviando.set(true);
    try {
      // Uma sessão guardada de um estudo já encerrado é descartada antes de criar a nova.
      await this.store.sessaoValida();
      const sessionId = await this.store.iniciarSessao(TERMO_VERSAO);
      if (sessionId) {
        await this.router.navigate(['/documentos']);
      } else {
        this.erro.set(this.store.erro());
      }
    } finally {
      this.enviando.set(false);
    }
  }
}
