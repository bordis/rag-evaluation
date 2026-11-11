import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export interface PontoDispersao {
  rotulo: string;
  x: number;
  y: number;
  ic: [number, number] | null;
  dica: string;
}

const LARGURA = 560;
const ALTURA = 280;
const ESQUERDA = 46;
const DIREITA = 56;
const TOPO = 12;
const BASE = 40;

/** Custo no eixo x, preferência no eixo y. O canto superior esquerdo é o melhor negócio. */
@Component({
  selector: 'app-grafico-dispersao',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './grafico-dispersao.html',
  styleUrl: './grafico-dispersao.css',
})
export class GraficoDispersao {
  readonly pontos = input.required<PontoDispersao[]>();
  readonly rotuloX = input.required<string>();
  readonly referencia = input<number | null>(null);
  readonly formatarX = input<(valor: number) => string>((valor) => String(valor));

  protected readonly largura = LARGURA;
  protected readonly altura = ALTURA;
  protected readonly esquerda = ESQUERDA;
  protected readonly limiteDireito = LARGURA - DIREITA;
  protected readonly limiteBase = ALTURA - BASE;
  protected readonly centroX = (ESQUERDA + LARGURA - DIREITA) / 2;

  protected readonly desenho = computed(() => {
    const maiorX = Math.max(...this.pontos().map((ponto) => ponto.x), 0) * 1.1 || 1;
    // Arredonda para cima de 25 em 25 pontos, para o eixo ter marcas legíveis.
    const maiorY = Math.min(
      1,
      Math.ceil(Math.max(0.5, ...this.pontos().map((p) => p.ic?.[1] ?? p.y)) * 4) / 4,
    );
    const px = (x: number) => ESQUERDA + (x / maiorX) * (LARGURA - ESQUERDA - DIREITA);
    const py = (y: number) => TOPO + (1 - y / maiorY) * (ALTURA - TOPO - BASE);
    return {
      pontos: this.pontos().map((ponto) => ({
        ...ponto,
        cx: px(ponto.x),
        cy: py(ponto.y),
        baixo: ponto.ic ? py(ponto.ic[0]) : null,
        alto: ponto.ic ? py(ponto.ic[1]) : null,
      })),
      gradesY: [0, 0.5, 1].map((f) => ({
        y: py(maiorY * f),
        rotulo: `${Math.round(maiorY * f * 100)}%`,
      })),
      marcasX: [0, 0.5, 1].map((f) => ({
        x: px(maiorX * f),
        rotulo: this.formatarX()(maiorX * f),
      })),
      referenciaY: this.referencia() === null ? null : py(this.referencia() as number),
    };
  });
}
