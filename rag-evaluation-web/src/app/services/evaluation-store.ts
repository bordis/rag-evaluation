import { computed, inject, Injectable, signal } from '@angular/core';

import {
  MAX_PERGUNTAS,
  type ProgressoDocumento,
  type QuestionRound,
  type RagDocument,
  type RotuloCego,
} from '../models/evaluation-model';
import { ApiRag } from './api-rag';
import { CronometroRodada } from './cronometro-rodada';

/**
 * Chave do `sessionStorage`. É a **única** coisa persistida no navegador: o histórico das
 * rodadas vem sempre do servidor. Sem isso, um F5 criaria uma sessão nova a cada recarga e
 * deixaria respostas órfãs no banco.
 */
const CHAVE_SESSAO = 'rag-evaluation.session-id';

/**
 * Estado da avaliação: cache dos dados vindos da API + orquestração das chamadas.
 *
 * O store não gera mais conteúdo nenhum — quem responde é o backend. Ele mantém os signals de
 * documentos, rodadas e progresso, e expõe os estados de carregamento/erro que a UI precisa
 * mostrar enquanto os pipelines geram as respostas (alguns segundos por pergunta).
 */
@Injectable({ providedIn: 'root' })
export class EvaluationStore {
  private readonly api = inject(ApiRag);
  private readonly cronometro = inject(CronometroRodada);

  private readonly _sessionId = signal<string | null>(this.lerSessaoSalva());
  private readonly _documents = signal<RagDocument[]>([]);
  private readonly _roundsByDoc = signal<Record<string, QuestionRound[]>>({});
  private readonly _progressoBySlug = signal<Record<string, ProgressoDocumento>>({});
  private readonly _maxPerguntas = signal(MAX_PERGUNTAS);
  private readonly _carregando = signal(false);
  private readonly _gerando = signal(false);
  private readonly _erro = signal<string | null>(null);

  /** Documentos prontos para avaliação. */
  readonly documents = this._documents.asReadonly();
  readonly sessionId = this._sessionId.asReadonly();
  readonly maxPerguntas = this._maxPerguntas.asReadonly();
  /** Carregando documentos, progresso ou histórico. */
  readonly carregando = this._carregando.asReadonly();
  /** Aguardando a geração das respostas de uma pergunta. */
  readonly gerando = this._gerando.asReadonly();
  readonly erro = this._erro.asReadonly();

  readonly totalConcluidos = computed(
    () => Object.values(this._progressoBySlug()).filter((item) => item.concluido).length,
  );

  limparErro(): void {
    this._erro.set(null);
  }

  getDocument(slug: string): RagDocument | undefined {
    return this._documents().find((documento) => documento.slug === slug);
  }

  rounds(slug: string): QuestionRound[] {
    return this._roundsByDoc()[slug] ?? [];
  }

  answeredCount(slug: string): number {
    return this._progressoBySlug()[slug]?.respondidas ?? 0;
  }

  remaining(slug: string): number {
    return Math.max(0, this._maxPerguntas() - this.answeredCount(slug));
  }

  isComplete(slug: string): boolean {
    return this.answeredCount(slug) >= this._maxPerguntas();
  }

  hasPendingRound(slug: string): boolean {
    return this.rounds(slug).some((round) => !round.escolhidoEm);
  }

  /**
   * Cria a sessão a partir do aceite do termo, na tela de boas-vindas. O servidor guarda uma por
   * login e por estudo: se este login já aceitou, a mesma sessão volta.
   */
  async iniciarSessao(termoVersao: string): Promise<string | null> {
    const atual = this._sessionId();
    if (atual) {
      return atual;
    }
    return this.executar(async () => {
      const id = await this.api.criarSessao(termoVersao);
      this.guardarSessao(id);
      return id;
    });
  }

  /**
   * Há sessão no estudo aberto, isto é, o termo já foi aceito? Uma sessão de um estudo encerrado
   * não serve mais. Sem sessão no navegador, pergunta ao servidor: o aceite é do login, não da
   * aba, então quem aceitou em outro navegador (ou fechou a aba) não vê o termo de novo.
   */
  async sessaoValida(): Promise<boolean> {
    const sessionId = this._sessionId();
    if (sessionId) {
      try {
        const progresso = await this.api.obterProgresso(sessionId);
        if (progresso.estudoAberto) {
          return true;
        }
      } catch (erro) {
        // Só o servidor dizer que a sessão não existe a descarta; rede fora do ar não.
        if ((erro as { status?: number }).status !== 404) {
          return true;
        }
      }
      this.descartarSessao();
    }
    return this.recuperarSessao();
  }

  /**
   * Pedido de aceite: quem tenta ir aos documentos sem ter aceitado o termo é levado de volta a
   * ele, e a tela de boas-vindas rola até o termo e o destaca. A tela consome o pedido.
   */
  private pedidos = 0;
  private readonly _aceitePedido = signal(0);
  /** Pedido pendente (0 = nenhum). Cada pedido tem um número novo, para destacar de novo. */
  readonly aceitePedido = this._aceitePedido.asReadonly();

  pedirAceite(): void {
    this.pedidos += 1;
    this._aceitePedido.set(this.pedidos);
  }

  consumirPedidoDeAceite(): void {
    this._aceitePedido.set(0);
  }

  private async recuperarSessao(): Promise<boolean> {
    try {
      const id = await this.api.obterMinhaSessao();
      if (id) {
        this.guardarSessao(id);
        return true;
      }
    } catch {
      // Sem resposta do servidor, não há como saber: segue como não aceito.
    }
    return false;
  }

  private guardarSessao(id: string): void {
    this._sessionId.set(id);
    sessionStorage.setItem(CHAVE_SESSAO, id);
  }

  private descartarSessao(): void {
    this._sessionId.set(null);
    this._roundsByDoc.set({});
    this._progressoBySlug.set({});
    sessionStorage.removeItem(CHAVE_SESSAO);
    this.cronometro.limpar();
  }

  /** Carrega documentos e progresso. Usada na entrada da tela de seleção. */
  async carregarCatalogo(): Promise<void> {
    this._carregando.set(true);
    try {
      await this.executar(async () => {
        this._documents.set(await this.api.listarDocumentos());
        await this.atualizarProgresso();
      });
    } finally {
      this._carregando.set(false);
    }
  }

  /** Entrada da tela de avaliação: catálogo (para o cabeçalho) + histórico do documento. */
  async abrirDocumento(slug: string): Promise<void> {
    this._carregando.set(true);
    try {
      await this.executar(async () => {
        if (this._documents().length === 0) {
          this._documents.set(await this.api.listarDocumentos());
        }
        const sessionId = this._sessionId();
        if (!sessionId || !this.getDocument(slug)) {
          return;
        }
        const rodadas = await this.api.listarRodadas(sessionId, slug);
        this._roundsByDoc.update((mapa) => ({ ...mapa, [slug]: rodadas }));
        await this.atualizarProgresso();
        if (!this.isComplete(slug)) {
          this.cronometro.retomar(slug);
        }
      });
    } finally {
      this._carregando.set(false);
    }
  }

  /**
   * Envia a pergunta e acrescenta a rodada gerada. As validações de limite e de rodada pendente
   * também existem no servidor — aqui elas só evitam uma ida e volta inútil.
   */
  async askQuestion(slug: string, texto: string): Promise<QuestionRound | undefined> {
    const pergunta = texto.trim();
    if (!pergunta || this.isComplete(slug) || this.hasPendingRound(slug) || this._gerando()) {
      return undefined;
    }
    const sessionId = this._sessionId();
    if (!sessionId) {
      return undefined;
    }

    this._gerando.set(true);
    this.cronometro.registrarPergunta(slug);
    const inicioGeracao = Date.now();
    try {
      const rodada = await this.executar(async () => {
        const gerada = await this.api.perguntar(sessionId, slug, pergunta);
        this.cronometro.registrarGeracao(slug, Date.now() - inicioGeracao);
        this._roundsByDoc.update((mapa) => ({
          ...mapa,
          [slug]: [...(mapa[slug] ?? []), gerada],
        }));
        return gerada;
      });
      return rodada ?? undefined;
    } finally {
      this._gerando.set(false);
    }
  }

  /**
   * Registra a escolha (`null` = nenhuma está correta) com o tempo da rodada. O cronômetro zera
   * só com a confirmação do servidor, e a próxima rodada começa a contar a partir daqui.
   */
  async chooseAnswer(slug: string, roundId: string, rotulo: RotuloCego | null): Promise<void> {
    const rodada = this.rounds(slug).find((item) => item.id === roundId);
    if (!rodada || rodada.escolhidoEm) {
      return;
    }

    await this.executar(async () => {
      const decidida = await this.api.escolher(roundId, rotulo, this.cronometro.ler(slug));
      this.cronometro.reiniciar(slug);
      this._roundsByDoc.update((mapa) => ({
        ...mapa,
        [slug]: (mapa[slug] ?? []).map((item) => (item.id === roundId ? decidida : item)),
      }));
      await this.atualizarProgresso();
    });
  }

  private async atualizarProgresso(): Promise<void> {
    const sessionId = this._sessionId();
    if (!sessionId) {
      return;
    }
    const progresso = await this.api.obterProgresso(sessionId);
    this._maxPerguntas.set(progresso.maxPerguntas);
    this._progressoBySlug.set(
      Object.fromEntries(progresso.documentos.map((item) => [item.slug, item])),
    );
  }

  /**
   * Executa a chamada guardando a mensagem de erro em vez de propagá-la: nenhuma tela sabe
   * tratar exceção de rede, e todas mostram o mesmo banner a partir de `erro()`.
   */
  private async executar<T>(acao: () => Promise<T>): Promise<T | null> {
    this._erro.set(null);
    try {
      return await acao();
    } catch (erro) {
      this._erro.set(erro instanceof Error ? erro.message : 'Falha inesperada.');
      return null;
    }
  }

  private lerSessaoSalva(): string | null {
    // O `sessionStorage` não existe em SSR nem no jsdom sem janela; a ausência não é erro.
    try {
      return sessionStorage.getItem(CHAVE_SESSAO);
    } catch {
      return null;
    }
  }
}
