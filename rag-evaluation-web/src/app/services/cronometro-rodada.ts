import { Injectable } from '@angular/core';

import type { TemposDaRodada } from '../models/evaluation-model';

interface EstadoCronometro {
  inicio: number;
  geracaoMs: number;
  ocultoMs: number;
  /** Instante em que saiu da tela ou da aba; `null` enquanto está contando. */
  pausadoEm: number | null;
  /** Do início até enviar a pergunta, sem o tempo oculto. */
  perguntaMs?: number | null;
  /** Rótulos das respostas que já apareceram na tela. */
  vistas?: string[];
  recarregamentos?: number;
}

const PREFIXO = 'rag-evaluation.cronometro.';

/**
 * Mede o tempo de cada rodada no navegador. Conta da abertura do documento (primeira pergunta) ou
 * da escolha anterior até a escolha seguinte, e separa o que não é trabalho do avaliador: a espera
 * pela geração e o tempo com a aba oculta ou fora da tela. Fica no `sessionStorage` para um F5 no
 * meio da rodada não zerar a conta.
 */
@Injectable({ providedIn: 'root' })
export class CronometroRodada {
  private slugAtual: string | null = null;

  constructor() {
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
          this.pausar();
        } else if (this.slugAtual) {
          this.retomar(this.slugAtual);
        }
      });
    }
  }

  /** Começa a contar, ou volta a contar depois de uma pausa. */
  retomar(slug: string): void {
    const slugAnterior = this.slugAtual;
    this.slugAtual = slug;
    const agora = Date.now();
    // Sem cronômetro ativo nesta carga da página e com estado salvo: o avaliador recarregou.
    const voltou = slugAnterior !== slug;
    const estado = this.lerEstado(slug);
    if (!estado) {
      this.gravar(slug, { inicio: agora, geracaoMs: 0, ocultoMs: 0, pausadoEm: null });
    } else if (estado.pausadoEm !== null || voltou) {
      this.gravar(slug, {
        ...estado,
        ocultoMs: estado.ocultoMs + (estado.pausadoEm === null ? 0 : agora - estado.pausadoEm),
        pausadoEm: null,
        recarregamentos: (estado.recarregamentos ?? 0) + (voltou ? 1 : 0),
      });
    }
  }

  /** Chamado ao enviar a pergunta: o resto da rodada é espera, leitura e decisão. */
  registrarPergunta(slug: string): void {
    const estado = this.lerEstado(slug);
    if (estado) {
      const agora = Date.now();
      const pausa = estado.pausadoEm === null ? 0 : agora - estado.pausadoEm;
      this.gravar(slug, {
        ...estado,
        perguntaMs: Math.max(0, agora - estado.inicio - estado.ocultoMs - pausa),
      });
    }
  }

  registrarVista(slug: string, rotulo: string): void {
    const estado = this.lerEstado(slug);
    if (estado && !estado.vistas?.includes(rotulo)) {
      this.gravar(slug, { ...estado, vistas: [...(estado.vistas ?? []), rotulo] });
    }
  }

  pausar(): void {
    if (!this.slugAtual) {
      return;
    }
    const estado = this.lerEstado(this.slugAtual);
    if (estado && estado.pausadoEm === null) {
      this.gravar(this.slugAtual, { ...estado, pausadoEm: Date.now() });
    }
  }

  registrarGeracao(slug: string, ms: number): void {
    const estado = this.lerEstado(slug);
    if (estado) {
      this.gravar(slug, { ...estado, geracaoMs: estado.geracaoMs + ms });
    }
  }

  /** Sem medição (ex.: `sessionStorage` bloqueado), a escolha segue e o tempo fica nulo no banco. */
  ler(slug: string): TemposDaRodada | undefined {
    const estado = this.lerEstado(slug);
    if (!estado) {
      return undefined;
    }
    const agora = Date.now();
    const pausa = estado.pausadoEm === null ? 0 : agora - estado.pausadoEm;
    return {
      totalMs: agora - estado.inicio,
      geracaoMs: estado.geracaoMs,
      ocultoMs: estado.ocultoMs + pausa,
      perguntaMs: estado.perguntaMs ?? null,
      // Sem o observador não há medição, o que é diferente de nenhuma resposta vista.
      respostasVistas:
        typeof IntersectionObserver === 'undefined' ? null : (estado.vistas?.length ?? 0),
      recarregamentos: estado.recarregamentos ?? 0,
      larguraTela: typeof window === 'undefined' ? null : window.innerWidth,
    };
  }

  /** A escolha foi registrada: a próxima rodada conta a partir de agora. */
  reiniciar(slug: string): void {
    this.gravar(slug, { inicio: Date.now(), geracaoMs: 0, ocultoMs: 0, pausadoEm: null });
  }

  limpar(): void {
    this.slugAtual = null;
    try {
      for (const chave of Object.keys(sessionStorage)) {
        if (chave.startsWith(PREFIXO)) {
          sessionStorage.removeItem(chave);
        }
      }
    } catch {
      // Sem acesso ao armazenamento não há nada para limpar.
    }
  }

  private lerEstado(slug: string): EstadoCronometro | null {
    try {
      const bruto = sessionStorage.getItem(PREFIXO + slug);
      return bruto ? (JSON.parse(bruto) as EstadoCronometro) : null;
    } catch {
      return null;
    }
  }

  private gravar(slug: string, estado: EstadoCronometro): void {
    try {
      sessionStorage.setItem(PREFIXO + slug, JSON.stringify(estado));
    } catch {
      // Falhar aqui não pode impedir a avaliação: o tempo da rodada fica sem registro.
    }
  }
}
