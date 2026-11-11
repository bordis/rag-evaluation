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
  pdf_disponivel: boolean;
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

export type Intervalo = [number, number];

export interface TestePosicao {
  qui2: number;
  gl: number;
  p_valor: number;
}

export type ClasseErro = 'recuperacao' | 'geracao' | 'divergencia' | 'sem_nota';

export type CausaErro =
  | 'sem_resposta_no_documento'
  | 'conversao'
  | 'recuperacao'
  | 'selecao'
  | 'geracao'
  | 'avaliador'
  | 'outra';

export interface Estatisticas {
  rodadas_decididas: number;
  avaliadores: number;
  acaso: number;
  amostra: {
    meta_avaliadores: Intervalo;
    meta_rodadas: Intervalo;
    documentos: number;
    ciclos: number;
    ciclos_completos: number;
    rodadas_por_avaliador_min: number | null;
    rodadas_por_avaliador_mediana: number | null;
    rodadas_por_avaliador_max: number | null;
  };
  nenhuma: Taxa & { ic95_bootstrap: Intervalo | null };
  por_pipeline: Array<
    Taxa & {
      codigo: string;
      ic95_simultaneo: Intervalo | null;
      faixa_posicao: Intervalo | null;
    }
  >;
  comparacoes_simples: Array<
    Taxa & {
      a_favor: string;
      contra: string;
      fator: string;
      condicao: string;
      ic95_bootstrap: Intervalo | null;
      p_valor: number | null;
      p_bonferroni: number | null;
    }
  >;
  poder: {
    rodadas: number;
    alfa: number;
    poder_alvo: number;
    taxa_minima_detectavel: number | null;
    cenarios: Array<{ taxa_real: number; poder: number; exagero: number | null }>;
  } | null;
  efeitos: Array<
    Taxa & {
      efeito: string;
      descricao: string;
      ic95_bootstrap: Intervalo | null;
      ic95_bootstrap_documento: Intervalo | null;
      p_valor: number | null;
      p_holm: number | null;
      pontos_acima_de_50: number | null;
      razao_chances: number | null;
    }
  >;
  por_documento: Array<{
    documento: string;
    rodadas: number;
    nenhuma: number;
    avaliadores: number;
    taxa_docling: number | null;
    taxa_avancado: number | null;
    vitorias: Record<string, number>;
  }>;
  por_posicao: Array<Taxa & { posicao: number }>;
  teste_posicao: TestePosicao | null;
  balanceamento: Array<{ codigo: string; posicoes: number[]; teste: TestePosicao | null }>;
  por_ordem: Array<{
    ordem: number;
    rodadas: number;
    nenhuma: number;
    tempo_ativo_mediano_ms: number | null;
    tempo_ativo_p25_ms: number | null;
    tempo_ativo_p75_ms: number | null;
    tamanho_medio_respostas: number;
    ms_por_mil_caracteres: number | null;
    taxa_posicao_1: number | null;
    taxa_avancado: number | null;
  }>;
  metades: {
    tempo_ativo_inicio_ms: number | null;
    tempo_ativo_fim_ms: number | null;
    proporcoes: Array<{
      metrica: string;
      inicio: number | null;
      fim: number | null;
      p_valor: number | null;
    }>;
  } | null;
  vies_tamanho: Taxa & {
    acaso: number;
    p_valor: number | null;
    por_pipeline: Array<{ codigo: string; caracteres_medio: number | null }>;
  };
  por_avaliador: Array<{
    numero: number;
    avaliador: string;
    rodadas: number;
    documentos: number;
    nenhuma: number;
    posicao_preferida: number | null;
    taxa_posicao_preferida: number | null;
    p_ajustado: number | null;
    tempo_ativo_mediano_ms: number | null;
    revisar: boolean;
  }>;
  confiabilidade: {
    divisoes: number;
    spearman_medio: number | null;
    mesmo_primeiro: number;
  } | null;
  custo: {
    por_pipeline: Array<{
      codigo: string;
      respostas: number;
      ms_medio: number | null;
      ms_p50: number | null;
      ms_p95: number | null;
      ms_p50_sem_concorrencia: number | null;
      tokens_medio: number | null;
      usd_medio: number | null;
      usd_total: number;
    }>;
    por_etapa: Array<{
      codigo: string;
      etapa: string;
      execucoes: number;
      ms_medio: number;
      ms_p50: number | null;
      ms_p95: number | null;
      tokens_medio: number | null;
      usd_medio: number | null;
    }>;
    ingestao: Array<{
      codigo: string;
      documentos: number;
      parsing_ms_medio: number;
      parsing_participacao: number | null;
      total_ms_medio: number;
      chunks_medio: number;
      tokens_embedding_total: number;
    }>;
  };
  custo_beneficio: Array<{
    codigo: string;
    taxa: number | null;
    ic95: Intervalo | null;
    usd_medio: number;
    usd_por_mil_perguntas: number;
    ms_p50: number | null;
    tokens_medio: number | null;
    delta_pontos: number | null;
    multiplo_usd: number | null;
    multiplo_latencia: number | null;
    dominado_por: string[];
  }>;
  contexto: {
    por_pipeline: Array<{
      codigo: string;
      respostas: number;
      chunks_medio: number | null;
      caracteres_medio: number | null;
    }>;
    sobreposicao: Array<{ a: string; b: string; rodadas: number; jaccard_medio: number | null }>;
  };
  ragas: {
    respostas_avaliadas: number;
    kendall_tau_ordenacao: number | null;
    concordancia: Array<{
      metrica: string;
      rodadas: number;
      concordancia: number | null;
      ic95: Intervalo | null;
      p_valor: number | null;
      acaso: number;
    }>;
    media_por_pipeline: Array<{
      codigo: string;
      media: number | null;
      fidelidade: number | null;
      relevancia_resposta: number | null;
      precisao_contexto: number | null;
    }>;
    vitorias_comparadas: Array<{
      codigo: string;
      rodadas: number;
      humano: number | null;
      ragas: number | null;
    }>;
    por_margem: Array<{
      faixa: string;
      rodadas: number;
      margem_mediana: number | null;
      concordancia: number | null;
    }>;
    efeitos_fatoriais: Array<{
      metrica: string;
      efeito: string;
      rodadas: number;
      diferenca: number | null;
      ic95_bootstrap: Intervalo | null;
    }>;
    rejeitadas: {
      rodadas_rejeitadas: number;
      rodadas_decididas: number;
      melhor_nota_rejeitadas: number | null;
      melhor_nota_decididas: number | null;
    };
  };
  coleta: {
    viu_todas: Taxa;
    tempo_pergunta_mediano_ms: number | null;
    rodadas_recarregadas: number;
    falhas_de_rodada: number;
    truncadas_por_pipeline: Array<{ codigo: string; respostas: number }>;
  };
  ambiente: Record<string, unknown>;
  erros: {
    limiar: number;
    rodadas: number;
    por_pipeline: Array<{ codigo: string } & Record<ClasseErro, number>>;
    causas_confirmadas: Array<{ codigo: string; causas: Record<string, number> }>;
    casos: Array<{
      rodada: string;
      avaliador: string;
      documento: string;
      documento_id: string | null;
      ordem: number;
      pergunta: string;
      classes: Record<string, ClasseErro>;
      respostas: Record<string, string>;
      anotacoes: Record<string, { causa: CausaErro; nota: string }>;
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

  anexarPdf(id: string, arquivo: File): Promise<unknown> {
    const dados = new FormData();
    dados.append('arquivo', arquivo);
    return chamarApi(this.http.put(`${this.base}/documents/${id}/arquivo`, dados));
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

  anotarResposta(answerId: string, causa: CausaErro): Promise<unknown> {
    return chamarApi(this.http.put(`${this.base}/admin/answers/${answerId}/anotacao`, { causa }));
  }

  removerAnotacao(answerId: string): Promise<unknown> {
    return chamarApi(this.http.delete(`${this.base}/admin/answers/${answerId}/anotacao`));
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
