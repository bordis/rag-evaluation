import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { firstValueFrom, type Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import type {
  PerfilAvaliador,
  ProgressoDocumento,
  QuestionRound,
  RagDocument,
  RotuloCego,
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
  pergunta: string;
  respostas: RespostaDTO[];
  escolha_rotulo: RotuloCego | null;
  escolhido_em: string | null;
}

interface ProgressoDTO {
  session_id: string;
  max_perguntas: number;
  total_concluidos: number;
  documentos: Array<{ slug: string; respondidas: number; concluido: boolean }>;
}

export interface ProgressoSessao {
  maxPerguntas: number;
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

  async criarSessao(perfil: PerfilAvaliador): Promise<string> {
    const corpo = {
      area_atuacao: perfil.areaAtuacao?.trim() || null,
      familiaridade: perfil.familiaridade ?? null,
      tempo_experiencia: perfil.tempoExperiencia ?? null,
    };
    const criada = await this.executar(
      this.http.post<{ id: string }>(`${this.base}/sessions`, corpo),
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

  /** Espera a geração das respostas nos pipelines — pode levar alguns segundos. */
  async perguntar(sessionId: string, slug: string, pergunta: string): Promise<QuestionRound> {
    const rodada = await this.executar(
      this.http.post<RodadaDTO>(`${this.base}/sessions/${sessionId}/documents/${slug}/questions`, {
        pergunta,
      }),
    );
    return this.paraRodada(rodada);
  }

  async escolher(roundId: string, rotulo: RotuloCego): Promise<QuestionRound> {
    const rodada = await this.executar(
      this.http.post<RodadaDTO>(`${this.base}/rounds/${roundId}/choice`, { rotulo }),
    );
    return this.paraRodada(rodada);
  }

  private paraRodada(rodada: RodadaDTO): QuestionRound {
    return {
      id: rodada.id,
      pergunta: rodada.pergunta,
      respostas: rodada.respostas.map((resposta) => ({
        id: resposta.id,
        rotuloCego: resposta.rotulo,
        texto: resposta.texto,
      })),
      escolhaRotulo: rodada.escolha_rotulo ?? undefined,
      escolhidoEm: rodada.escolhido_em ?? undefined,
    };
  }

  private async executar<T>(requisicao: Observable<T>): Promise<T> {
    try {
      return await firstValueFrom(requisicao);
    } catch (erro) {
      throw this.traduzir(erro);
    }
  }

  private traduzir(erro: unknown): ApiError {
    if (!(erro instanceof HttpErrorResponse)) {
      return new ApiError('Não foi possível concluir a operação.', 0);
    }
    // status 0 = a requisição nem chegou ao servidor (API fora do ar ou CORS bloqueando).
    if (erro.status === 0) {
      return new ApiError(
        'Não foi possível falar com o servidor. Verifique se a API está no ar.',
        0,
      );
    }
    const detalhe = (erro.error as { detail?: unknown } | null)?.detail;
    if (typeof detalhe === 'string') {
      return new ApiError(detalhe, erro.status);
    }
    return new ApiError(`Falha na comunicação com o servidor (HTTP ${erro.status}).`, erro.status);
  }
}
