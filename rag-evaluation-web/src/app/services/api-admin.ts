import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';

import { environment } from '../../environments/environment';
import { chamarApi } from './api-rag';

/** Visão do pesquisador: estes tipos revelam o pipeline e nunca são usados no fluxo do avaliador. */
export interface Estudo {
  id: string;
  nome: string;
  descricao: string;
  status: 'aberto' | 'encerrado';
  iniciado_em: string | null;
  encerrado_em: string | null;
  sessoes: number;
  rodadas_decididas: number;
}

export interface DocumentoAdmin {
  id: string;
  slug: string;
  titulo: string;
  area: string;
  status: 'processando' | 'pronto' | 'erro_parcial';
  paginas: number | null;
  tabelas: number | null;
  imagens: number | null;
  criado_em: string;
}

export interface Ingestao {
  pipeline_codigo: string;
  status: string;
  erro: string | null;
  total_chunks: number;
  tokens_embedding: number;
  duracao_parsing_ms: number;
  duracao_total_ms: number;
}

export interface PipelineAdmin {
  id: number;
  codigo: string;
  nome: string;
  descricao: string;
  parser: 'raw' | 'docling';
  collection_name: string;
  ativo: boolean;
  config: Record<string, unknown>;
  controle: boolean;
}

export interface AvaliacaoResumo {
  session_id: string;
  document_id: string;
  documento_titulo: string;
  rodadas: number;
  decididas: number;
  nenhuma: number;
  inicio: string | null;
  fim: string | null;
}

export interface ChunkDetalhe {
  etapa: string;
  posicao: number;
  chunk_index: number;
  score_final: number;
  score_denso: number | null;
  score_esparso: number | null;
  origem: string | null;
  texto: string;
}

export interface MetricaDetalhe {
  etapa: string;
  duracao_ms: number;
  tokens_total: number | null;
  modelo: string | null;
  custo_usd: number | null;
  detalhes: Record<string, unknown>;
}

export interface RespostaDetalhe {
  id: string;
  rotulo: string;
  posicao_exibida: number;
  pipeline_codigo: string;
  pipeline_nome: string;
  escolhida: boolean;
  texto: string;
  config_snapshot: Record<string, unknown>;
  metricas: MetricaDetalhe[];
  chunks: ChunkDetalhe[];
  ragas: {
    fidelidade: number | null;
    relevancia_resposta: number | null;
    precisao_contexto: number | null;
    media: number | null;
    erro: string | null;
  } | null;
}

export interface RodadaAdmin {
  id: string;
  ordem: number;
  pergunta: string;
  nenhuma_correta: boolean;
  decidida: boolean;
  tempo_total_ms: number | null;
  tempo_geracao_ms: number | null;
  tempo_oculto_ms: number | null;
  respostas: RespostaDetalhe[];
}

export interface AvaliacaoDetalhe {
  session_id: string;
  documento_titulo: string;
  study_id: string;
  estudo_nome: string;
  termo_versao: string;
  aceito_em: string | null;
  rodadas: RodadaAdmin[];
}

export interface Taxa {
  sucessos: number;
  total: number;
  taxa: number | null;
  ic95: [number, number] | null;
}

export interface Estatisticas {
  rodadas_decididas: number;
  avaliadores: number;
  acaso: number;
  nenhuma: Taxa;
  por_pipeline: Array<Taxa & { codigo: string }>;
  efeitos: Array<
    Taxa & {
      efeito: string;
      descricao: string;
      ic95_bootstrap: [number, number] | null;
      p_valor: number | null;
    }
  >;
  por_documento: Array<{
    documento: string;
    rodadas: number;
    nenhuma: number;
    vitorias: Record<string, number>;
  }>;
  por_posicao: Array<Taxa & { posicao: number }>;
  por_ordem: Array<{
    ordem: number;
    rodadas: number;
    nenhuma: number;
    tempo_ativo_mediano_ms: number | null;
    taxa_posicao_1: number | null;
    taxa_avancado: number | null;
  }>;
  custo: {
    por_pipeline: Array<{
      codigo: string;
      respostas: number;
      ms_p50: number | null;
      ms_p95: number | null;
      tokens_medio: number | null;
      usd_medio: number | null;
      usd_total: number;
    }>;
    por_etapa: Array<{
      codigo: string;
      etapa: string;
      execucoes: number;
      ms_p50: number | null;
      ms_p95: number | null;
      tokens_medio: number | null;
      usd_medio: number | null;
    }>;
    ingestao: Array<{
      codigo: string;
      documentos: number;
      parsing_ms_medio: number;
      total_ms_medio: number;
      chunks_medio: number;
      tokens_embedding_total: number;
    }>;
  };
  ragas: {
    respostas_avaliadas: number;
    kendall_tau_ordenacao: number | null;
    concordancia: Array<{
      metrica: string;
      rodadas: number;
      concordancia: number | null;
      acaso: number;
    }>;
    media_por_pipeline: Array<{
      codigo: string;
      media: number | null;
      fidelidade: number | null;
      relevancia_resposta: number | null;
      precisao_contexto: number | null;
    }>;
  };
}

/** Andamento do cálculo do RAGAS de um estudo, contado em respostas. */
export interface RagasSituacao {
  em_andamento: boolean;
  total: number;
  avaliadas: number;
  com_erro: number;
  ultimo_erro: string | null;
}

/** Rotas abertas nesta fase, por decisão do estudo. Serão protegidas pelo login previsto. */
@Injectable({ providedIn: 'root' })
export class ApiAdmin {
  private readonly http = inject(HttpClient);
  readonly base = environment.apiBaseUrl;

  listarEstudos(): Promise<Estudo[]> {
    return chamarApi(this.http.get<Estudo[]>(`${this.base}/studies`));
  }

  criarEstudo(nome: string, descricao: string): Promise<Estudo> {
    return chamarApi(this.http.post<Estudo>(`${this.base}/studies`, { nome, descricao }));
  }

  encerrarEstudo(id: string): Promise<Estudo> {
    return chamarApi(this.http.post<Estudo>(`${this.base}/studies/${id}/encerrar`, null));
  }

  listarDocumentos(): Promise<DocumentoAdmin[]> {
    return chamarApi(this.http.get<DocumentoAdmin[]>(`${this.base}/documents`));
  }

  enviarDocumento(dados: FormData): Promise<unknown> {
    return chamarApi(this.http.post(`${this.base}/documents`, dados));
  }

  excluirDocumento(id: string): Promise<unknown> {
    return chamarApi(this.http.delete(`${this.base}/documents/${id}`));
  }

  listarIngestoes(id: string): Promise<Ingestao[]> {
    return chamarApi(this.http.get<Ingestao[]>(`${this.base}/documents/${id}/ingestions`));
  }

  listarPipelines(): Promise<PipelineAdmin[]> {
    return chamarApi(this.http.get<PipelineAdmin[]>(`${this.base}/pipelines`));
  }

  criarPipeline(dados: Partial<PipelineAdmin>): Promise<PipelineAdmin> {
    return chamarApi(this.http.post<PipelineAdmin>(`${this.base}/pipelines`, dados));
  }

  atualizarPipeline(id: number, dados: Partial<PipelineAdmin>): Promise<PipelineAdmin> {
    return chamarApi(this.http.put<PipelineAdmin>(`${this.base}/pipelines/${id}`, dados));
  }

  excluirPipeline(id: number): Promise<unknown> {
    return chamarApi(this.http.delete(`${this.base}/pipelines/${id}`));
  }

  listarAvaliacoes(studyId: string): Promise<AvaliacaoResumo[]> {
    return chamarApi(
      this.http.get<AvaliacaoResumo[]>(`${this.base}/admin/studies/${studyId}/avaliacoes`),
    );
  }

  obterAvaliacao(sessionId: string, documentId: string): Promise<AvaliacaoDetalhe> {
    return chamarApi(
      this.http.get<AvaliacaoDetalhe>(`${this.base}/admin/avaliacoes/${sessionId}/${documentId}`),
    );
  }

  obterEstatisticas(studyId: string): Promise<Estatisticas> {
    return chamarApi(this.http.get<Estatisticas>(`${this.base}/admin/studies/${studyId}/stats`));
  }

  urlExportacao(studyId: string): string {
    return `${this.base}/admin/studies/${studyId}/export.csv`;
  }

  calcularRagasDoEstudo(studyId: string): Promise<{ mensagem: string }> {
    return chamarApi(
      this.http.post<{ mensagem: string }>(`${this.base}/admin/studies/${studyId}/ragas`, null),
    );
  }

  obterSituacaoRagas(studyId: string): Promise<RagasSituacao> {
    return chamarApi(this.http.get<RagasSituacao>(`${this.base}/admin/studies/${studyId}/ragas`));
  }

  calcularRagasDaRodada(roundId: string): Promise<RodadaAdmin> {
    return chamarApi(
      this.http.post<RodadaAdmin>(`${this.base}/admin/rounds/${roundId}/ragas`, null),
    );
  }
}
