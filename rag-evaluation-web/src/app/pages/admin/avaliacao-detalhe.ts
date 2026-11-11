import { DecimalPipe, JsonPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { MarkdownPipe } from '../../pipes/markdown-pipe';
import {
  ApiAdmin,
  type AvaliacaoDetalhe,
  type ChunkDetalhe,
  type RespostaDetalhe,
  type RodadaAdmin,
} from '../../services/api-admin';

const NOMES_DAS_ETAPAS: Record<string, string> = {
  contexto_final: 'Contexto entregue ao LLM',
  reordenacao: 'Após a reordenação',
  fusao: 'Após a fusão (RRF)',
  denso: 'Busca densa',
  esparso: 'Busca esparsa (BM25)',
};

function nomeDaResposta(resposta: RespostaDetalhe): string {
  return `${resposta.pipeline_codigo} (${resposta.rotulo})`;
}

/**
 * As respostas de maior média no RAGAS; mais de uma quando há empate. Como na análise do estudo,
 * só compara com todas as notas da rodada: com alguma faltando, o "melhor" seria enganoso.
 */
function melhoresNoRagas(rodada: RodadaAdmin): RespostaDetalhe[] {
  const notas = rodada.respostas.map((resposta) => resposta.ragas?.media ?? null);
  if (notas.length === 0 || notas.includes(null)) {
    return [];
  }
  const maior = Math.max(...(notas as number[]));
  return rodada.respostas.filter((resposta) => resposta.ragas?.media === maior);
}

function descreverEscolha(rodada: RodadaAdmin): string {
  if (rodada.nenhuma_correta) {
    return 'Nenhuma está correta';
  }
  const escolhida = rodada.respostas.find((resposta) => resposta.escolhida);
  return escolhida ? nomeDaResposta(escolhida) : 'Pendente';
}

function descreverMelhorNoRagas(rodada: RodadaAdmin): string {
  const melhores = melhoresNoRagas(rodada);
  if (melhores.length === 0) {
    return 'Sem notas completas';
  }
  const nomes = melhores.map(nomeDaResposta).join(', ');
  return melhores.length > 1 ? `Empate: ${nomes}` : nomes;
}

/** Navega nas perguntas de um ciclo: respostas, escolha, trechos por etapa, tempos e RAGAS. */
@Component({
  selector: 'app-admin-avaliacao-detalhe',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DecimalPipe, JsonPipe, MarkdownPipe],
  templateUrl: './avaliacao-detalhe.html',
})
export class AdminAvaliacaoDetalhe {
  private readonly api = inject(ApiAdmin);

  readonly sessionId = input.required<string>();
  readonly documentId = input.required<string>();

  protected readonly avaliacao = signal<AvaliacaoDetalhe | null>(null);
  protected readonly indice = signal(0);
  protected readonly calculando = signal(false);
  protected readonly erro = signal<string | null>(null);

  protected readonly rodada = computed(() => this.avaliacao()?.rodadas[this.indice()]);
  protected readonly comparacao = computed(() =>
    (this.avaliacao()?.rodadas ?? []).map((rodada) => ({
      id: rodada.id,
      ordem: rodada.ordem,
      pergunta: rodada.pergunta,
      escolha: descreverEscolha(rodada),
      melhorNoRagas: descreverMelhorNoRagas(rodada),
    })),
  );

  constructor() {
    effect(() => {
      this.api
        .obterAvaliacao(this.sessionId(), this.documentId())
        .then((dados) => this.avaliacao.set(dados))
        .catch((erro: Error) => this.erro.set(erro.message));
    });
  }

  protected melhorNoRagas(rodada: RodadaAdmin, resposta: RespostaDetalhe): boolean {
    return melhoresNoRagas(rodada).includes(resposta);
  }

  protected nomeEtapa(nome: string): string {
    return NOMES_DAS_ETAPAS[nome] ?? nome;
  }

  protected etapas(resposta: RespostaDetalhe): Array<{ nome: string; chunks: ChunkDetalhe[] }> {
    return Object.keys(NOMES_DAS_ETAPAS)
      .map((nome) => ({
        nome,
        chunks: resposta.chunks
          .filter((chunk) => chunk.etapa === nome)
          .sort((a, b) => a.posicao - b.posicao),
      }))
      .filter((etapa) => etapa.chunks.length > 0);
  }

  protected segundos(ms: number | null): string {
    return ms === null ? '—' : `${(ms / 1000).toFixed(1)} s`;
  }

  protected async calcularRagas(): Promise<void> {
    const atual = this.rodada();
    const dados = this.avaliacao();
    if (!atual || !dados) {
      return;
    }
    this.erro.set(null);
    this.calculando.set(true);
    try {
      const nova = await this.api.calcularRagasDaRodada(atual.id);
      this.avaliacao.set({
        ...dados,
        rodadas: dados.rodadas.map((item) => (item.id === nova.id ? nova : item)),
      });
    } catch (erro) {
      this.erro.set((erro as Error).message);
    } finally {
      this.calculando.set(false);
    }
  }
}
