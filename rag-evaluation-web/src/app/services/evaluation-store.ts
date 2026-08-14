import { computed, inject, Injectable, signal } from '@angular/core';

import {
  MAX_PERGUNTAS,
  type PerfilAvaliador,
  type ProgressoDocumento,
  type QuestionRound,
  type RagDocument,
  type RotuloCego,
} from '../models/evaluation-model';
import { ApiRag } from './api-rag';

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
    return this.rounds(slug).some((round) => !round.escolhaRotulo);
  }

  /**
   * Garante uma sessão no servidor. Chamada pela tela de perfil com os dados informados e,
   * como rede de segurança, por quem entrar direto numa URL profunda — nesse caso a sessão
   * nasce anônima, sem perfil.
   */
  async garantirSessao(perfil: PerfilAvaliador = {}): Promise<string | null> {
    const atual = this._sessionId();
    if (atual) {
      return atual;
    }
    return this.executar(async () => {
      const id = await this.api.criarSessao(perfil);
      this._sessionId.set(id);
      sessionStorage.setItem(CHAVE_SESSAO, id);
      return id;
    });
  }

  /** Carrega documentos e progresso. Usada na entrada da tela de seleção. */
  async carregarCatalogo(): Promise<void> {
    this._carregando.set(true);
    try {
      await this.garantirSessao();
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
      await this.garantirSessao();
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
    const sessionId = await this.garantirSessao();
    if (!sessionId) {
      return undefined;
    }

    this._gerando.set(true);
    try {
      const rodada = await this.executar(async () => {
        const gerada = await this.api.perguntar(sessionId, slug, pergunta);
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

  /** Registra a escolha do avaliador e atualiza o progresso com o número vindo do servidor. */
  async chooseAnswer(slug: string, roundId: string, rotulo: RotuloCego): Promise<void> {
    const rodada = this.rounds(slug).find((item) => item.id === roundId);
    if (!rodada || rodada.escolhaRotulo) {
      return;
    }

    await this.executar(async () => {
      const decidida = await this.api.escolher(roundId, rotulo);
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
