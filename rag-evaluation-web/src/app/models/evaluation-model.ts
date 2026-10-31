/**
 * Modelos de domínio da avaliação de pipelines RAG.
 *
 * A avaliação é ÀS CEGAS e a garantia é do servidor: a API **não envia** a identidade do
 * pipeline que gerou cada resposta — o campo não existe no JSON. Por isso não há, e não deve
 * voltar a haver, um tipo `PipelineId` aqui: o navegador não conhece essa informação.
 */

/**
 * Número máximo de perguntas avaliadas por documento. O limite verdadeiro é imposto pelo
 * servidor (`MAX_PERGUNTAS` no `.env` da API); este valor serve para a UI mostrar o progresso e
 * é sobrescrito pelo que vem em `GET /sessions/{id}/progress`.
 */
export const MAX_PERGUNTAS = 10;

/** Rótulos cegos apresentados ao avaliador — um por pipeline do desenho fatorial 2×2. */
export type RotuloCego = 'A' | 'B' | 'C' | 'D';

/** Documento sobre o qual o avaliador pode fazer perguntas. */
export interface RagDocument {
  /** UUID no banco. As rotas da avaliação usam o `slug`, não este id. */
  id: string;
  /** Identificador legível, usado na rota `/avaliacao/:docId`. */
  slug: string;
  titulo: string;
  area: string;
  descricao: string;
  icone: string;
}

/** Uma resposta candidata, exibida sob um rótulo cego. */
export interface PipelineAnswer {
  id: string;
  rotuloCego: RotuloCego;
  texto: string;
}

/** Uma rodada: pergunta do avaliador + as respostas candidatas + a escolha. */
export interface QuestionRound {
  id: string;
  /** Posição da rodada no ciclo do documento. */
  ordem: number;
  pergunta: string;
  respostas: PipelineAnswer[];
  /** Rótulo cego escolhido; fica vazio na rodada pendente e quando nenhuma está correta. */
  escolhaRotulo?: RotuloCego;
  nenhumaCorreta: boolean;
  /** Preenchido quando a rodada foi decidida, com uma resposta ou com "nenhuma". */
  escolhidoEm?: string;
}

/** Progresso do avaliador em um documento, conforme contabilizado pelo servidor. */
export interface ProgressoDocumento {
  slug: string;
  respondidas: number;
  concluido: boolean;
}

/** Estudo em andamento: só com um estudo aberto o avaliador pode responder. */
export interface EstudoAtual {
  id: string;
  nome: string;
}

/** Tempos medidos no navegador para uma rodada. */
export interface TemposDaRodada {
  totalMs: number;
  geracaoMs: number;
  ocultoMs: number;
}
