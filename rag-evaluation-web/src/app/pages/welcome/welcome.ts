import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  effect,
  ElementRef,
  inject,
  Injector,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import type { EstudoAtual } from '../../models/evaluation-model';
import { TERMO_PARAGRAFOS, TERMO_VERSAO } from '../../models/termo';
import { ApiRag } from '../../services/api-rag';
import { EvaluationStore } from '../../services/evaluation-store';

/** Pulso em volta do termo. A cor vem do token já resolvido: keyframes não resolvem `var()`. */
function pulso(cor: string): Keyframe[] {
  return [
    { boxShadow: `0 0 0 0 color-mix(in srgb, ${cor} 55%, transparent)` },
    { boxShadow: `0 0 0 14px color-mix(in srgb, ${cor} 0%, transparent)` },
  ];
}

/**
 * Boas-vindas: explicação do processo e aceite do termo, que é o que cria a sessão.
 * O aceite é do login, guardado no servidor: quem já aceitou neste estudo não vê o termo de novo.
 */
@Component({
  selector: 'app-welcome',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  templateUrl: './welcome.html',
  styleUrl: './welcome.css',
})
export class Welcome {
  private readonly api = inject(ApiRag);
  private readonly store = inject(EvaluationStore);
  private readonly router = inject(Router);
  private readonly injector = inject(Injector);

  protected readonly termo = TERMO_PARAGRAFOS;
  protected readonly aceite = signal(false);
  protected readonly enviando = signal(false);
  protected readonly carregando = signal(true);
  protected readonly estudo = signal<EstudoAtual | null>(null);
  protected readonly erro = signal<string | null>(null);
  /** Este login já tem sessão no estudo aberto, ou seja, já aceitou o termo. */
  protected readonly jaAceitou = signal(false);
  /** Tentou ir aos documentos sem aceitar: a borda e a mensagem ficam até o aceite. */
  protected readonly aceiteExigido = signal(false);

  private readonly alvo = viewChild<ElementRef<HTMLElement>>('alvo');
  private readonly caixaAceite = viewChild<ElementRef<HTMLInputElement>>('caixaAceite');

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
        'Para cada pergunta, apresentamos 4 respostas anônimas (A, B, C e D). Escolha a melhor ou indique que nenhuma está correta. Depois de escolher, marque as outras que também estiverem corretas.',
    },
  ];

  constructor() {
    void this.carregar();

    // O pedido vem do guard dos documentos; só é atendido com a tela já montada.
    effect(() => {
      const pedido = this.store.aceitePedido();
      if (!pedido || this.carregando()) {
        return;
      }
      untracked(() => {
        this.store.consumirPedidoDeAceite();
        if (!this.jaAceitou()) {
          this.destacarTermo();
        }
      });
    });
  }

  private async carregar(): Promise<void> {
    try {
      const estudo = await this.api.obterEstudoAtual();
      this.estudo.set(estudo);
      if (estudo) {
        this.jaAceitou.set(await this.store.sessaoValida());
      }
    } catch (erro) {
      this.erro.set(erro instanceof Error ? erro.message : 'Falha inesperada.');
    } finally {
      this.carregando.set(false);
    }
  }

  /** Rola até o termo (ou o aviso que impede começar), destaca e põe o foco no aceite. */
  private destacarTermo(): void {
    this.aceiteExigido.set(true);
    afterNextRender(
      () => {
        const alvo = this.alvo()?.nativeElement;
        if (!alvo) {
          return;
        }
        const reduzido = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
        alvo.scrollIntoView?.({ behavior: reduzido ? 'auto' : 'smooth', block: 'center' });
        this.caixaAceite()?.nativeElement.focus({ preventScroll: true });
        if (!reduzido && typeof alvo.animate === 'function') {
          // Web Animations recomeça a cada pedido, sem precisar desligar e religar uma classe.
          const cor = getComputedStyle(alvo).getPropertyValue('--color-primary').trim();
          alvo.animate(pulso(cor), { duration: 700, iterations: 2, easing: 'ease-out' });
        }
      },
      { injector: this.injector },
    );
  }

  protected onAceite(evento: Event): void {
    const marcado = (evento.target as HTMLInputElement).checked;
    this.aceite.set(marcado);
    if (marcado) {
      this.aceiteExigido.set(false);
    }
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
