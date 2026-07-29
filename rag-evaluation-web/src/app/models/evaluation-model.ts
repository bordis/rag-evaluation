/**
 * Modelos de domínio da avaliação de pipelines RAG.
 *
 * A avaliação é feita ÀS CEGAS: o avaliador vê apenas os rótulos A/B/C, enquanto
 * a identidade verdadeira do pipeline que gerou cada resposta fica registrada
 * internamente (campo `pipeline`) para análise posterior.
 */

/** Número máximo de perguntas avaliadas por documento. */
export const MAX_PERGUNTAS = 10;

/** Rótulos cegos apresentados ao avaliador. */
export type RotuloCego = 'A' | 'B' | 'C';

/** Identidade verdadeira (interna) de cada configuração de pipeline. */
export type PipelineId = 'pipeline-a' | 'pipeline-b' | 'pipeline-c';

/** Documento sobre o qual o avaliador pode fazer perguntas. */
export interface RagDocument {
  id: string;
  titulo: string;
  area: string;
  descricao: string;
  /** Emoji/ícone simples para o card (mock). */
  icone: string;
}

/** Uma resposta candidata gerada por um pipeline, exibida sob um rótulo cego. */
export interface PipelineAnswer {
  pipeline: PipelineId;
  rotuloCego: RotuloCego;
  texto: string;
}

/** Uma rodada: pergunta do avaliador + as 3 respostas candidatas + a escolha. */
export interface QuestionRound {
  id: string;
  pergunta: string;
  respostas: PipelineAnswer[];
  /** Pipeline verdadeiro escolhido; indefinido enquanto pendente de escolha. */
  escolhaPipeline?: PipelineId;
  /** Rótulo cego escolhido pelo avaliador (para destacar na UI). */
  escolhaRotulo?: RotuloCego;
  escolhidoEm?: Date;
}

/** Progresso acumulado de um documento (todas as rodadas iniciadas). */
export interface DocumentProgress {
  documentId: string;
  rounds: QuestionRound[];
}
