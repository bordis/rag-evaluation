import type {
  EstudoAtual,
  ProgressoDocumento,
  QuestionRound,
  RagDocument,
  RotuloCego,
  TemposDaRodada,
} from '../models/evaluation-model';
import type { ProgressoSessao } from '../services/api-rag';

const ROTULOS: RotuloCego[] = ['A', 'B', 'C', 'D'];

/**
 * Dublê do {@link ApiRag} usado nos testes: guarda o mesmo estado que o backend guardaria
 * (sessão, rodadas, progresso) para que os testes do store exercitem o fluxo real sem HTTP.
 *
 * Vive em `src/` e não num `.spec.ts` porque é compartilhado por mais de um arquivo de teste.
 */
export class ApiRagFake {
  termoRecebido: string | null = null;
  estudo: EstudoAtual | null = { id: 'estudo-1', nome: 'Coleta' };
  estudoAberto = true;
  temposRecebidos: TemposDaRodada | undefined;
  ultimoRotulo: RotuloCego | null | undefined;
  falha: Error | null = null;
  maxPerguntas = 10;

  documentos: RagDocument[] = [
    {
      id: '11111111-1111-1111-1111-111111111111',
      slug: 'lgpd',
      titulo: 'Lei Geral de Proteção de Dados',
      area: 'Direito',
      descricao: 'Texto consolidado da Lei nº 13.709/2018.',
      icone: '⚖️',
    },
    {
      id: '22222222-2222-2222-2222-222222222222',
      slug: 'kubernetes',
      titulo: 'Fundamentos de Kubernetes',
      area: 'Tecnologia',
      descricao: 'Pods, deployments e services.',
      icone: '☸️',
    },
  ];

  private sequencia = 0;
  private readonly rodadasPorSlug: Record<string, QuestionRound[]> = {};

  async obterEstudoAtual(): Promise<EstudoAtual | null> {
    this.checar();
    return this.estudo;
  }

  async criarSessao(termoVersao: string): Promise<string> {
    this.checar();
    this.termoRecebido = termoVersao;
    return 'sessao-de-teste';
  }

  async listarDocumentos(): Promise<RagDocument[]> {
    this.checar();
    return [...this.documentos];
  }

  async obterProgresso(): Promise<ProgressoSessao> {
    this.checar();
    const documentos: ProgressoDocumento[] = Object.entries(this.rodadasPorSlug).map(
      ([slug, rodadas]) => {
        const respondidas = rodadas.filter((rodada) => rodada.escolhidoEm).length;
        return { slug, respondidas, concluido: respondidas >= this.maxPerguntas };
      },
    );
    return { maxPerguntas: this.maxPerguntas, estudoAberto: this.estudoAberto, documentos };
  }

  async listarRodadas(_sessionId: string, slug: string): Promise<QuestionRound[]> {
    this.checar();
    return [...(this.rodadasPorSlug[slug] ?? [])];
  }

  async perguntar(_sessionId: string, slug: string, pergunta: string): Promise<QuestionRound> {
    this.checar();
    this.sequencia += 1;
    const rodada: QuestionRound = {
      id: `rodada-${this.sequencia}`,
      ordem: this.sequencia,
      nenhumaCorreta: false,
      pergunta,
      respostas: ROTULOS.map((rotulo) => ({
        id: `resposta-${this.sequencia}-${rotulo}`,
        rotuloCego: rotulo,
        texto: `Resposta ${rotulo} para "${pergunta}".`,
      })),
    };
    this.rodadasPorSlug[slug] = [...(this.rodadasPorSlug[slug] ?? []), rodada];
    return rodada;
  }

  async escolher(
    roundId: string,
    rotulo: RotuloCego | null,
    tempos?: TemposDaRodada,
  ): Promise<QuestionRound> {
    this.checar();
    this.ultimoRotulo = rotulo;
    this.temposRecebidos = tempos;
    for (const [slug, rodadas] of Object.entries(this.rodadasPorSlug)) {
      const alvo = rodadas.find((rodada) => rodada.id === roundId);
      if (!alvo) {
        continue;
      }
      const decidida: QuestionRound = {
        ...alvo,
        escolhaRotulo: rotulo ?? undefined,
        nenhumaCorreta: rotulo === null,
        escolhidoEm: new Date().toISOString(),
      };
      this.rodadasPorSlug[slug] = rodadas.map((rodada) =>
        rodada.id === roundId ? decidida : rodada,
      );
      return decidida;
    }
    throw new Error('Rodada não encontrada.');
  }

  private checar(): void {
    if (this.falha) {
      throw this.falha;
    }
  }
}
