import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { firstValueFrom, type Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import type {
  EstudoAtual,
  ProgressoDocumento,
  QuestionRound,
  RagDocument,
  RotuloCego,
  TemposDaRodada,
} from '../models/evaluation-model';

/** Formatos exatos do JSON da API (snake_case). Convertidos para o domínio logo abaixo. */
interface DocumentoDTO {
  id: string;
  slug: string;
  titulo: string;
  area: string;
  descricao: string;
  icone: string;
}

interface RespostaDTO {
  id: string;
  rotulo: RotuloCego;
  texto: string;
}

interface RodadaDTO {
  id: string;
  ordem: number;
  pergunta: string;
  respostas: RespostaDTO[];
  escolha_rotulo: RotuloCego | null;
  nenhuma_correta: boolean;
  escolhido_em: string | null;
}

interface ProgressoDTO {
  session_id: string;
  max_perguntas: number;
  estudo_aberto: boolean;
  total_concluidos: number;
  documentos: Array<{ slug: string; respondidas: number; concluido: boolean }>;
}

export interface ProgressoSessao {
  maxPerguntas: number;
  estudoAberto: boolean;
  documentos: ProgressoDocumento[];
}

/** Erro já traduzido para uma mensagem exibível ao avaliador. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Único ponto de contato com o `rag-evaluation-api`. Concentra a tradução snake_case → domínio
 * e a de erro HTTP → mensagem em português, para que o store cuide só de estado.
 */
@Injectable({ providedIn: 'root' })
export class ApiRag {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  /** `null` quando não há estudo aberto: ninguém pode começar. */
  async obterEstudoAtual(): Promise<EstudoAtual | null> {
    return this.executar(this.http.get<EstudoAtual | null>(`${this.base}/studies/atual`));
  }

  /** A sessão só nasce com o aceite do termo, e dentro do estudo aberto. */
  async criarSessao(termoVersao: string): Promise<string> {
    const criada = await this.executar(
      this.http.post<{ id: string }>(`${this.base}/sessions`, {
        aceite: true,
        termo_versao: termoVersao,
      }),
    );
    return criada.id;
  }

  /** Só documentos `pronto`: os demais têm ingestão incompleta em pelo menos um pipeline. */
  async listarDocumentos(): Promise<RagDocument[]> {
    const documentos = await this.executar(
      this.http.get<DocumentoDTO[]>(`${this.base}/documents`, { params: { status: 'pronto' } }),
    );
    return documentos.map((item) => ({ ...item }));
  }

  async obterProgresso(sessionId: string): Promise<ProgressoSessao> {
    const progresso = await this.executar(
      this.http.get<ProgressoDTO>(`${this.base}/sessions/${sessionId}/progress`),
    );
    return {
      maxPerguntas: progresso.max_perguntas,
      estudoAberto: progresso.estudo_aberto,
      documentos: progresso.documentos.map((item) => ({
        slug: item.slug,
        respondidas: item.respondidas,
        concluido: item.concluido,
      })),
    };
  }

  async listarRodadas(sessionId: string, slug: string): Promise<QuestionRound[]> {
    const rodadas = await this.executar(
      this.http.get<RodadaDTO[]>(`${this.base}/sessions/${sessionId}/documents/${slug}/rounds`),
    );
    return rodadas.map((rodada) => this.paraRodada(rodada));
  }

  /** Espera a geração das respostas nos pipelines — pode levar cerca de um minuto. */
  async perguntar(sessionId: string, slug: string, pergunta: string): Promise<QuestionRound> {
    const rodada = await this.executar(
      this.http.post<RodadaDTO>(`${this.base}/sessions/${sessionId}/documents/${slug}/questions`, {
        pergunta,
      }),
    );
    return this.paraRodada(rodada);
  }

  /** `rotulo` nulo registra que nenhuma resposta está correta. */
  async escolher(
    roundId: string,
    rotulo: RotuloCego | null,
    tempos?: TemposDaRodada,
  ): Promise<QuestionRound> {
    const rodada = await this.executar(
      this.http.post<RodadaDTO>(`${this.base}/rounds/${roundId}/choice`, {
        rotulo,
        tempo_total_ms: tempos?.totalMs ?? null,
        tempo_geracao_ms: tempos?.geracaoMs ?? null,
        tempo_oculto_ms: tempos?.ocultoMs ?? null,
      }),
    );
    return this.paraRodada(rodada);
  }

  private paraRodada(rodada: RodadaDTO): QuestionRound {
    return {
      id: rodada.id,
      ordem: rodada.ordem,
      pergunta: rodada.pergunta,
      respostas: rodada.respostas.map((resposta) => ({
        id: resposta.id,
        rotuloCego: resposta.rotulo,
        texto: resposta.texto,
      })),
      escolhaRotulo: rodada.escolha_rotulo ?? undefined,
      nenhumaCorreta: rodada.nenhuma_correta,
      escolhidoEm: rodada.escolhido_em ?? undefined,
    };
  }

  private executar<T>(requisicao: Observable<T>): Promise<T> {
    return chamarApi(requisicao);
  }
}

/** Aguarda a resposta e converte qualquer falha em {@link ApiError}. */
export async function chamarApi<T>(requisicao: Observable<T>): Promise<T> {
  try {
    return await firstValueFrom(requisicao);
  } catch (erro) {
    throw traduzirErro(erro);
  }
}

function traduzirErro(erro: unknown): ApiError {
  if (!(erro instanceof HttpErrorResponse)) {
    return new ApiError('Não foi possível concluir a operação.', 0);
  }
  // status 0 = a requisição nem chegou ao servidor (API fora do ar ou CORS bloqueando).
  if (erro.status === 0) {
    return new ApiError('Não foi possível falar com o servidor. Verifique se a API está no ar.', 0);
  }
  const detalhe = (erro.error as { detail?: unknown } | null)?.detail;
  if (typeof detalhe === 'string') {
    return new ApiError(detalhe, erro.status);
  }
  return new ApiError(`Falha na comunicação com o servidor (HTTP ${erro.status}).`, erro.status);
}
