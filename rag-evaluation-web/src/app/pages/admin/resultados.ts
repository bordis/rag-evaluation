import { DatePipe, DecimalPipe, PercentPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiAdmin, type Estatisticas, type RagasSituacao } from '../../services/api-admin';

const INTERVALO_RAGAS_MS = 3000;

/** Resultados de um estudo: H1 a H3, posição, fadiga, custo e concordância com o RAGAS. */
@Component({
  selector: 'app-admin-resultados',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DatePipe, DecimalPipe, PercentPipe],
  templateUrl: './resultados.html',
})
export class AdminResultados {
  private readonly api = inject(ApiAdmin);

  readonly studyId = input.required<string>();

  protected readonly dados = signal<Estatisticas | null>(null);
  protected readonly ragas = signal<RagasSituacao | null>(null);
  protected readonly erro = signal<string | null>(null);
  protected readonly aviso = signal<string | null>(null);
  protected readonly atualizando = signal(false);
  protected readonly atualizadoEm = signal<Date | null>(null);
  protected readonly disparando = signal(false);

  private temporizador: ReturnType<typeof setTimeout> | undefined;

  constructor() {
    effect(() => {
      void this.buscar(this.studyId());
    });
    inject(DestroyRef).onDestroy(() => clearTimeout(this.temporizador));
  }

  protected urlCsv(): string {
    return this.api.urlExportacao(this.studyId());
  }

  protected intervalo(ic: [number, number] | null): string {
    return ic ? `${(ic[0] * 100).toFixed(1)}% a ${(ic[1] * 100).toFixed(1)}%` : '—';
  }

  protected carregar(): void {
    void this.buscar(this.studyId());
  }

  private async buscar(studyId: string): Promise<void> {
    clearTimeout(this.temporizador);
    this.erro.set(null);
    this.atualizando.set(true);
    try {
      const [dados, ragas] = await Promise.all([
        this.api.obterEstatisticas(studyId),
        this.api.obterSituacaoRagas(studyId),
      ]);
      this.dados.set(dados);
      this.ragas.set(ragas);
      this.atualizadoEm.set(new Date());
      this.acompanharRagas(studyId);
    } catch (erro) {
      this.erro.set((erro as Error).message);
    } finally {
      this.atualizando.set(false);
    }
  }

  private acompanharRagas(studyId: string): void {
    if (!this.ragas()?.em_andamento) {
      return;
    }
    this.temporizador = setTimeout(async () => {
      try {
        const ragas = await this.api.obterSituacaoRagas(studyId);
        this.ragas.set(ragas);
        if (ragas.em_andamento) {
          this.acompanharRagas(studyId);
        } else {
          // Terminou: as tabelas de concordância só mudam agora.
          this.aviso.set(null);
          await this.buscar(studyId);
        }
      } catch (erro) {
        this.erro.set(
          `Não foi possível acompanhar o RAGAS: ${(erro as Error).message} Use "Atualizar".`,
        );
      }
    }, INTERVALO_RAGAS_MS);
  }

  protected async calcularRagas(): Promise<void> {
    if (
      !confirm('O RAGAS faz dezenas de chamadas pagas por rodada. Calcular para todo o estudo?')
    ) {
      return;
    }
    this.erro.set(null);
    this.disparando.set(true);
    try {
      const resposta = await this.api.calcularRagasDoEstudo(this.studyId());
      this.aviso.set(resposta.mensagem);
      await this.buscar(this.studyId());
    } catch (erro) {
      this.erro.set((erro as Error).message);
    } finally {
      this.disparando.set(false);
    }
  }
}
