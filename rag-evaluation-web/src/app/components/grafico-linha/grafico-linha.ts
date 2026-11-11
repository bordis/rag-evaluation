import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export interface PontoLinha {
  x: number;
  y: number | null;
  dica: string;
}

const LARGURA = 320;
const ALTURA = 150;
const ESQUERDA = 42;
const DIREITA = 10;
const TOPO = 10;
const BASE = 26;

/** Uma série pela ordem da rodada. Mais de uma medida vira mais de um gráfico, nunca dois eixos. */
@Component({
  selector: 'app-grafico-linha',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './grafico-linha.html',
  styleUrl: './grafico-linha.css',
})
export class GraficoLinha {
  readonly titulo = input.required<string>();
  readonly pontos = input.required<PontoLinha[]>();
  readonly maximo = input.required<number>();
  readonly formatarEixo = input<(valor: number) => string>((valor) => String(valor));
  readonly referencia = input<number | null>(null);

  protected readonly largura = LARGURA;
  protected readonly altura = ALTURA;
  protected readonly esquerda = ESQUERDA;
  protected readonly limiteDireito = LARGURA - DIREITA;
  protected readonly limiteBase = ALTURA - BASE;

  protected readonly desenho = computed(() => {
    const validos = this.pontos().filter((ponto) => ponto.y !== null);
    const xs = validos.map((ponto) => ponto.x);
    const menor = Math.min(1, ...xs);
    const maior = Math.max(10, ...xs);
    const topo = this.maximo() || 1;
    const px = (x: number) =>
      ESQUERDA + ((x - menor) / (maior - menor)) * (LARGURA - ESQUERDA - DIREITA);
    const py = (y: number) => TOPO + (1 - y / topo) * (ALTURA - TOPO - BASE);

    const pontos = validos.map((ponto) => ({
      ...ponto,
      cx: px(ponto.x),
      cy: py(ponto.y as number),
    }));
    return {
      pontos,
      caminho: pontos.map((p) => `${p.cx},${p.cy}`).join(' '),
      grades: [0, 0.5, 1].map((fracao) => ({
        y: py(topo * fracao),
        rotulo: this.formatarEixo()(topo * fracao),
      })),
      marcasX: [menor, Math.round((menor + maior) / 2), maior].map((x) => ({
        x: px(x),
        rotulo: x,
      })),
      referenciaY: this.referencia() === null ? null : py(this.referencia() as number),
    };
  });
}
