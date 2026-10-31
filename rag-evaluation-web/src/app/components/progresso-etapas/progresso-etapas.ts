import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

interface Etapa {
  indice: number;
  feita: boolean;
  /** A primeira ainda sem escolha: é onde o avaliador está trabalhando. */
  atual: boolean;
}

/**
 * Trilha de progresso da avaliação: uma etapa por pergunta do documento. É só um indicador: por
 * decisão do estudo, o avaliador não volta às perguntas já respondidas.
 */
@Component({
  selector: 'app-progresso-etapas',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './progresso-etapas.html',
  styleUrl: './progresso-etapas.css',
})
export class ProgressoEtapas {
  readonly total = input.required<number>();
  readonly respondidas = input.required<number>();

  protected readonly concluido = computed(() => this.respondidas() >= this.total());

  protected readonly etapas = computed<Etapa[]>(() =>
    Array.from({ length: this.total() }, (_, indice) => ({
      indice,
      feita: indice < this.respondidas(),
      atual: indice === this.respondidas(),
    })),
  );

  /** A linha liga o centro da primeira etapa ao centro da última. */
  protected readonly avanco = computed(() => {
    const trechos = this.total() - 1;
    return trechos > 0 ? Math.min(this.respondidas(), trechos) / trechos : 1;
  });
}
