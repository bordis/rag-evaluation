import { ChangeDetectionStrategy, Component, input, signal } from '@angular/core';

/** Texto do "?": o que é, como ler, o que não concluir e de onde vem. */
export interface Ajuda {
  oQueE: string;
  comoLer: string[];
  cuidado?: string;
  fontes: string;
}

let proximoId = 0;

/** Bloco de uma análise: título, botão "?" com a explicação e o conteúdo projetado. */
@Component({
  selector: 'app-analise-cartao',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './analise-cartao.html',
  styleUrl: './analise-cartao.css',
})
export class AnaliseCartao {
  readonly titulo = input.required<string>();
  readonly ajuda = input.required<Ajuda>();
  readonly subtitulo = input<string>();

  protected readonly aberta = signal(false);
  protected readonly idAjuda = `analise-ajuda-${proximoId++}`;

  protected alternar(): void {
    this.aberta.update((valor) => !valor);
  }
}
