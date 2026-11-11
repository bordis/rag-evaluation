import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export interface LinhaIntervalo {
  rotulo: string;
  valor: number | null;
  ic: [number, number] | null;
  /** Texto à direita; sem ele, mostra o valor em porcentagem. */
  texto?: string;
}

/** Pontos com intervalo de confiança sobre uma linha de referência (acaso ou hipótese nula). */
@Component({
  selector: 'app-grafico-intervalos',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './grafico-intervalos.html',
  styleUrl: './grafico-intervalos.css',
})
export class GraficoIntervalos {
  readonly linhas = input.required<LinhaIntervalo[]>();
  readonly referencia = input<number | null>(null);
  readonly rotuloReferencia = input('');

  protected readonly marcas = [0, 0.25, 0.5, 0.75, 1];

  protected readonly desenhadas = computed(() =>
    this.linhas().map((linha) => ({
      ...linha,
      legenda: linha.texto ?? (linha.valor === null ? '—' : porcentagem(linha.valor)),
      dica:
        linha.valor === null
          ? `${linha.rotulo}: sem dados`
          : `${linha.rotulo}: ${porcentagem(linha.valor)}` +
            (linha.ic
              ? ` (IC 95% de ${porcentagem(linha.ic[0])} a ${porcentagem(linha.ic[1])})`
              : ''),
    })),
  );

  protected pct(valor: number): string {
    return `${Math.min(1, Math.max(0, valor)) * 100}%`;
  }

  protected largura(ic: [number, number]): string {
    return `${(Math.min(1, ic[1]) - Math.max(0, ic[0])) * 100}%`;
  }
}

function porcentagem(valor: number): string {
  return `${(valor * 100).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`;
}
