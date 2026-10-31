import { Injectable } from '@angular/core';

import type { TemposDaRodada } from '../models/evaluation-model';

interface EstadoCronometro {
  inicio: number;
  geracaoMs: number;
  ocultoMs: number;
  /** Instante em que saiu da tela ou da aba; `null` enquanto está contando. */
  pausadoEm: number | null;
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
    this.slugAtual = slug;
    const agora = Date.now();
    const estado = this.lerEstado(slug);
    if (!estado) {
      this.gravar(slug, { inicio: agora, geracaoMs: 0, ocultoMs: 0, pausadoEm: null });
    } else if (estado.pausadoEm !== null) {
      this.gravar(slug, {
        ...estado,
        ocultoMs: estado.ocultoMs + (agora - estado.pausadoEm),
        pausadoEm: null,
      });
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
