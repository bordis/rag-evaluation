import { computed, signal } from '@angular/core';

/**
 * Ações em andamento, por chave (`'excluir:' + id`, `'criar'`…). Serve para o botão clicado
 * mostrar o spinner e recusar um segundo clique enquanto o servidor não responde.
 */
export class Ocupado {
  private readonly chaves = signal<ReadonlySet<string>>(new Set());

  /** Alguma ação ainda está rodando. */
  readonly algum = computed(() => this.chaves().size > 0);

  em(chave: string): boolean {
    return this.chaves().has(chave);
  }

  /** Roda `acao` marcando a chave; um segundo pedido com a mesma chave é ignorado. */
  async durante<T>(chave: string, acao: () => Promise<T>): Promise<T | undefined> {
    if (this.em(chave)) {
      return undefined;
    }
    this.chaves.update((atuais) => new Set(atuais).add(chave));
    try {
      return await acao();
    } finally {
      this.chaves.update((atuais) => {
        const proximas = new Set(atuais);
        proximas.delete(chave);
        return proximas;
      });
    }
  }
}
