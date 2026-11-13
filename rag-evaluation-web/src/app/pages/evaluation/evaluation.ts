import {
  afterNextRender,
  afterRenderEffect,
  ChangeDetectionStrategy,
  Component,
  computed,
  type ElementRef,
  effect,
  inject,
  Injector,
  type OnDestroy,
  input,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { DomSanitizer, type SafeResourceUrl } from '@angular/platform-browser';
import { Router, RouterLink } from '@angular/router';

import { AnswerChoice, type EnvioRodada } from '../../components/answer-choice/answer-choice';
import { ChatMessage } from '../../components/chat-message/chat-message';
import { ProgressoEtapas } from '../../components/progresso-etapas/progresso-etapas';
import { aguardaMarcacao, rodadaCompleta, type RotuloCego } from '../../models/evaluation-model';
import { ApiRag } from '../../services/api-rag';
import { CronometroRodada } from '../../services/cronometro-rodada';
import { EvaluationStore } from '../../services/evaluation-store';

/** Tamanho mínimo da pergunta — o mesmo que a API valida (`min_length=3`). */
const MIN_PERGUNTA = 3;

/**
 * Tela principal: uma etapa por pergunta do documento. Cada pergunta é respondida por todos os
 * pipelines e apresentada às cegas (A/B/C/D); o avaliador escolhe a melhor ou indica que nenhuma
 * está correta. Se escolheu uma, na mesma tela indica quais das outras também estão corretas; só
 * então a tela passa para a próxima pergunta, sem volta. O passo vem da rodada vinda do servidor,
 * então um F5 entre a escolha e a marcação retoma na marcação. O limite de perguntas é imposto
 * pelo servidor.
 */
@Component({
  selector: 'app-evaluation',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, ChatMessage, AnswerChoice, ProgressoEtapas],
  templateUrl: './evaluation.html',
  styleUrl: './evaluation.css',
})
export class Evaluation implements OnDestroy {
  private readonly store = inject(EvaluationStore);
  private readonly router = inject(Router);
  private readonly cronometro = inject(CronometroRodada);
  private readonly injector = inject(Injector);
  private readonly api = inject(ApiRag);
  private readonly sanitizer = inject(DomSanitizer);

  private readonly topo = viewChild<ElementRef<HTMLElement>>('topo');
  private readonly etapa = viewChild<ElementRef<HTMLElement>>('etapa');
  private readonly campoPergunta = viewChild<ElementRef<HTMLTextAreaElement>>('campoPergunta');

  /**
   * Trava contra duplo envio, na escolha e na confirmação da marcação. Guarda o que foi clicado
   * (o rótulo, `'nenhuma'` ou `'confirmar'`) para o spinner aparecer naquele botão.
   */
  protected readonly envio = signal<EnvioRodada | null>(null);
  /** Para onde a navegação pedida por um botão está indo, enquanto a outra tela carrega. */
  protected readonly navegandoPara = signal<'proximo' | 'documentos' | null>(null);

  /** Vem do parâmetro de rota `:docId` via componentInputBinding — é o `slug` do documento. */
  readonly docId = input.required<string>();

  protected readonly rascunho = signal('');
  /** Mantém a pergunta na tela enquanto as respostas são geradas. */
  protected readonly perguntaEnviada = signal('');

  protected readonly maxPerguntas = this.store.maxPerguntas;
  protected readonly carregando = this.store.carregando;
  protected readonly gerando = this.store.gerando;
  protected readonly erro = this.store.erro;

  protected readonly documento = computed(() => this.store.getDocument(this.docId()));
  /** Abre na mesma aba: em outra, a consulta sairia do tempo de leitura como tempo oculto. */
  protected readonly pdfAberto = signal(false);
  /**
   * O PDF chega como blob pelo `HttpClient`, que leva o token do login: um `<iframe>` apontando
   * para a API não mandaria o cabeçalho. A URL `blob:` é local, criada aqui, nunca texto do usuário.
   */
  protected readonly urlDoPdf = signal<SafeResourceUrl | null>(null);
  protected readonly erroPdf = signal(false);
  private urlBlob: string | null = null;
  private readonly rounds = computed(() => this.store.rounds(this.docId()));
  /** Rodadas encerradas: com a escolha e, quando houve vencedora, com a marcação das outras. */
  protected readonly completas = computed(() => this.rounds().filter(rodadaCompleta));
  /** Sem escolha ou esperando a marcação: as duas ficam na mesma tela das respostas. */
  protected readonly rodadaPendente = computed(() =>
    this.rounds().find((item) => !rodadaCompleta(item)),
  );
  protected readonly concluido = computed(() => this.store.isComplete(this.docId()));

  protected readonly tela = computed(() => {
    // Antes do "concluído": a última rodada já conta no limite, mas ainda pode faltar a marcação.
    if (this.rodadaPendente()) {
      return 'respostas';
    }
    if (this.concluido()) {
      return 'concluido';
    }
    if (this.gerando()) {
      return 'gerando';
    }
    return this.carregando() ? 'carregando' : 'pergunta';
  });

  // A escolha não muda a chave: o segundo passo é a mesma tela, sem a animação de entrada.
  private readonly chaveDaTela = computed(() => `${this.tela()}-${this.completas().length}`);

  /** Só é possível perguntar com texto suficiente, na tela de pergunta. */
  protected readonly podePerguntar = computed(
    () => this.rascunho().trim().length >= MIN_PERGUNTA && this.tela() === 'pergunta',
  );

  /** Próximo documento ainda não concluído (para sugerir após finalizar). */
  protected readonly proximoDocumento = computed(() =>
    this.store
      .documents()
      .find((doc) => doc.slug !== this.docId() && !this.store.isComplete(doc.slug)),
  );

  constructor() {
    // O documento pode mudar sem recriar o componente (navegação entre `/avaliacao/:docId`),
    // então a carga acompanha o input em vez de rodar uma vez na construção.
    effect(() => {
      void this.store.abrirDocumento(this.docId());
      // O PDF aberto é do documento anterior.
      untracked(() => this.fecharPdf());
    });

    // A entrada de cada etapa. O `?.` cobre o jsdom, que não tem essas APIs.
    afterRenderEffect(() => {
      this.chaveDaTela();
      if (!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
        this.etapa()?.nativeElement.animate?.(
          [
            { opacity: 0, transform: 'translateX(16px)' },
            { opacity: 1, transform: 'none' },
          ],
          { duration: 350, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' },
        );
      }
    });
  }

  /** Fora desta tela o avaliador não está respondendo: o tempo conta como ausência. */
  ngOnDestroy(): void {
    this.cronometro.pausar();
    this.fecharPdf();
  }

  protected async perguntar(): Promise<void> {
    if (!this.podePerguntar()) {
      return;
    }
    const texto = this.rascunho();
    this.rascunho.set('');
    this.perguntaEnviada.set(texto.trim());
    const rodada = await this.store.askQuestion(this.docId(), texto);
    if (!rodada) {
      // Falhou (rede, timeout de pipeline): devolve o texto para o avaliador não reescrever.
      this.rascunho.set(texto);
    }
  }

  protected onTextarea(evento: Event): void {
    this.rascunho.set((evento.target as HTMLTextAreaElement).value);
  }

  protected onKeydown(evento: KeyboardEvent): void {
    if (evento.key === 'Enter' && !evento.shiftKey) {
      evento.preventDefault();
      void this.perguntar();
    }
  }

  protected registrarVista(rotulo: RotuloCego): void {
    this.cronometro.registrarVista(this.docId(), rotulo);
  }

  protected async escolher(roundId: string, rotulo: RotuloCego | null): Promise<void> {
    // Um segundo clique antes da resposta do servidor viraria um 409 na tela.
    if (this.envio()) {
      return;
    }
    this.envio.set(rotulo ?? 'nenhuma');
    try {
      await this.store.chooseAnswer(this.docId(), roundId, rotulo);
    } finally {
      this.envio.set(null);
    }
    // Com uma vencedora, a tela fica para a marcação, e o componente leva o foco à pergunta.
    const rodada = this.rounds().find((item) => item.id === roundId);
    if (!this.erro() && rodada && !aguardaMarcacao(rodada)) {
      this.irParaOTopo();
    }
  }

  protected async confirmarMarcacao(roundId: string, rotulos: RotuloCego[]): Promise<void> {
    if (this.envio()) {
      return;
    }
    this.envio.set('confirmar');
    try {
      await this.store.confirmarTambemCorretas(this.docId(), roundId, rotulos);
    } finally {
      this.envio.set(null);
    }
    if (!this.erro()) {
      this.irParaOTopo();
    }
  }

  protected async alternarPdf(): Promise<void> {
    if (this.pdfAberto()) {
      this.fecharPdf();
      return;
    }
    const documento = this.documento();
    if (!documento?.pdfDisponivel) {
      return;
    }
    this.pdfAberto.set(true);
    try {
      const pdf = await this.api.baixarPdf(documento.id);
      // Fechado (ou trocado de documento) enquanto baixava.
      if (!this.pdfAberto() || this.documento()?.id !== documento.id) {
        return;
      }
      this.urlBlob = URL.createObjectURL(pdf);
      this.urlDoPdf.set(this.sanitizer.bypassSecurityTrustResourceUrl(this.urlBlob));
    } catch {
      this.erroPdf.set(true);
    }
  }

  private fecharPdf(): void {
    this.pdfAberto.set(false);
    this.urlDoPdf.set(null);
    this.erroPdf.set(false);
    if (this.urlBlob) {
      URL.revokeObjectURL(this.urlBlob);
      this.urlBlob = null;
    }
  }

  protected irParaDocumentos(): void {
    void this.navegar('documentos', ['/documentos']);
  }

  protected irParaProximo(): void {
    const proximo = this.proximoDocumento();
    if (proximo) {
      void this.navegar('proximo', ['/avaliacao', proximo.slug]);
      this.rascunho.set('');
    }
  }

  private async navegar(destino: 'proximo' | 'documentos', rota: string[]): Promise<void> {
    if (this.navegandoPara()) {
      return;
    }
    this.navegandoPara.set(destino);
    try {
      await this.router.navigate(rota);
    } finally {
      // Ir ao próximo documento reaproveita este componente: o botão não pode ficar girando.
      this.navegandoPara.set(null);
    }
  }

  private irParaOTopo(): void {
    this.depoisDeRenderizar(() => {
      this.topo()?.nativeElement.scrollIntoView?.();
      this.campoPergunta()?.nativeElement.focus({ preventScroll: true });
    });
  }

  private depoisDeRenderizar(acao: () => void): void {
    afterNextRender(acao, { injector: this.injector });
  }
}
