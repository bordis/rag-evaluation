import { DatePipe, JsonPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { AnaliseCartao } from '../../components/analise-cartao/analise-cartao';
import {
  GraficoDispersao,
  type PontoDispersao,
} from '../../components/grafico-dispersao/grafico-dispersao';
import {
  GraficoIntervalos,
  type LinhaIntervalo,
} from '../../components/grafico-intervalos/grafico-intervalos';
import { GraficoLinha, type PontoLinha } from '../../components/grafico-linha/grafico-linha';
import {
  ApiAdmin,
  type CausaErro,
  type ClasseErro,
  type Estatisticas,
  type Intervalo,
  type RagasSituacao,
} from '../../services/api-admin';
import { AJUDA } from './resultados-ajuda';

const INTERVALO_RAGAS_MS = 3000;
const ALFA = 0.05;

const ABAS = [
  { id: 'panorama', rotulo: 'Panorama' },
  { id: 'preferencia', rotulo: 'Preferência humana' },
  { id: 'validade', rotulo: 'Validade da coleta' },
  { id: 'ragas', rotulo: 'RAGAS × pessoas' },
  { id: 'custo', rotulo: 'Custo-benefício' },
  { id: 'erros', rotulo: 'Erros' },
] as const;
type AbaId = (typeof ABAS)[number]['id'];

const ROTULOS_PIPELINE: Record<string, string> = {
  'pipeline-1': 'P1 · bruto, básica',
  'pipeline-2': 'P2 · Docling, básica',
  'pipeline-3': 'P3 · bruto, avançada',
  'pipeline-4': 'P4 · Docling, avançada',
};
const ROTULOS_EFEITO: Record<string, string> = {
  ingestao: 'Ingestão: Docling',
  recuperacao: 'Recuperação avançada',
  interacao: 'Interação: diagonal 1 e 4',
};
const ROTULOS_METRICA: Record<string, string> = {
  media: 'Média',
  fidelidade: 'Fidelidade',
  relevancia_resposta: 'Relevância da resposta',
  precisao_contexto: 'Precisão do contexto',
};
const ROTULOS_PROPORCAO: Record<string, string> = {
  nenhuma: '"Nenhuma está correta"',
  posicao_1: 'Escolheu a posição 1',
  avancado: 'Escolheu recuperação avançada',
  viu_todas: 'Viu as quatro respostas',
};
const ETAPAS = [
  { id: 'hyde', rotulo: 'HyDE', cor: 'var(--grafico-4)' },
  { id: 'embedding_query', rotulo: 'Embedding da pergunta', cor: 'var(--grafico-2)' },
  { id: 'retrieval', rotulo: 'Busca', cor: 'var(--grafico-5)' },
  { id: 'reranking', rotulo: 'Reordenação', cor: 'var(--grafico-3)' },
  { id: 'window_expansion', rotulo: 'Vizinhos', cor: 'var(--grafico-6)' },
  { id: 'generation', rotulo: 'Geração', cor: 'var(--grafico-1)' },
];
const CLASSES_ERRO: Array<{ id: ClasseErro; rotulo: string }> = [
  { id: 'recuperacao', rotulo: 'Recuperação' },
  { id: 'geracao', rotulo: 'Geração' },
  { id: 'divergencia', rotulo: 'Divergência' },
  { id: 'sem_nota', rotulo: 'Sem nota' },
];

const CAUSAS_ERRO: Array<{ id: CausaErro; rotulo: string }> = [
  { id: 'sem_resposta_no_documento', rotulo: 'Documento não responde' },
  { id: 'conversao', rotulo: 'Conversão do documento' },
  { id: 'recuperacao', rotulo: 'Trecho não recuperado' },
  { id: 'selecao', rotulo: 'Trecho perdido na seleção' },
  { id: 'geracao', rotulo: 'Geração' },
  { id: 'avaliador', rotulo: 'Resposta estava certa' },
  { id: 'outra', rotulo: 'Outra' },
];

type Veredito = 'a favor' | 'contra' | 'inconclusivo' | 'sem evidência' | 'sem dados';

interface Leitura {
  pergunta: string;
  veredito: string;
  detalhe: string;
  aba: AbaId;
}

function inclui(ic: Intervalo | null, valor: number): boolean {
  return ic === null || (ic[0] <= valor && valor <= ic[1]);
}

function ms(valor: number | null): string {
  return valor === null
    ? '—'
    : `${(valor / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} s`;
}

/** Resultados de um estudo, em abas: o que as pessoas preferem, se dá para confiar e quanto custa. */
@Component({
  selector: 'app-admin-resultados',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    DatePipe,
    JsonPipe,
    AnaliseCartao,
    GraficoIntervalos,
    GraficoLinha,
    GraficoDispersao,
  ],
  templateUrl: './resultados.html',
  styleUrl: './resultados.css',
})
export class AdminResultados {
  private readonly api = inject(ApiAdmin);

  readonly studyId = input.required<string>();
  /** Na URL (`?aba=`): recarregar a página ou compartilhar o link mantém a aba. */
  readonly aba = input<string>();

  protected readonly ajuda = AJUDA;
  protected readonly abas = ABAS;
  protected readonly etapas = ETAPAS;
  protected readonly classesErro = CLASSES_ERRO;
  protected readonly causasErro = CAUSAS_ERRO;

  protected readonly dados = signal<Estatisticas | null>(null);
  protected readonly ragas = signal<RagasSituacao | null>(null);
  protected readonly erro = signal<string | null>(null);
  protected readonly aviso = signal<string | null>(null);
  protected readonly atualizando = signal(false);
  protected readonly atualizadoEm = signal<Date | null>(null);
  protected readonly disparando = signal(false);
  protected readonly exportando = signal(false);

  protected readonly abaAtiva = computed<AbaId>(() => {
    const pedida = this.aba();
    return ABAS.find((aba) => aba.id === pedida)?.id ?? 'panorama';
  });

  protected readonly linhasVitoria = computed<LinhaIntervalo[]>(() =>
    (this.dados()?.por_pipeline ?? []).map((item) => ({
      rotulo: this.pipeline(item.codigo),
      valor: item.taxa,
      ic: item.ic95,
    })),
  );
  protected readonly linhasEfeitos = computed<LinhaIntervalo[]>(() =>
    (this.dados()?.efeitos ?? []).map((item) => ({
      rotulo: ROTULOS_EFEITO[item.efeito] ?? item.efeito,
      valor: item.taxa,
      ic: item.ic95_bootstrap,
    })),
  );
  protected readonly linhasSimples = computed<LinhaIntervalo[]>(() =>
    (this.dados()?.comparacoes_simples ?? []).map((item) => ({
      rotulo: `${this.curto(item.a_favor)} × ${this.curto(item.contra)} (${item.condicao})`,
      valor: item.taxa,
      ic: item.ic95_bootstrap,
    })),
  );
  protected readonly linhasPosicao = computed<LinhaIntervalo[]>(() =>
    (this.dados()?.por_posicao ?? []).map((item) => ({
      rotulo: `Posição ${item.posicao}`,
      valor: item.taxa,
      ic: item.ic95,
    })),
  );
  /** As quatro respostas de uma rodada não são independentes: o traço é o bootstrap por avaliador. */
  protected readonly linhasCorrecao = computed<LinhaIntervalo[]>(() =>
    (this.dados()?.taxa_correcao.por_pipeline ?? []).map((item) => ({
      rotulo: this.pipeline(item.codigo),
      valor: item.taxa,
      ic: item.ic95_bootstrap,
    })),
  );
  protected readonly linhasMarcacaoPosicao = computed<LinhaIntervalo[]>(() =>
    (this.dados()?.marcacao_por_posicao.por_posicao ?? []).map((item) => ({
      rotulo: `Posição ${item.posicao}`,
      valor: item.taxa,
      ic: item.ic95,
    })),
  );
  /** Taxa média de marcação entre as não escolhidas: a referência do gráfico por posição. */
  protected readonly marcacaoMedia = computed(() => {
    const posicoes = this.dados()?.marcacao_por_posicao.por_posicao ?? [];
    const total = posicoes.reduce((soma, item) => soma + item.total, 0);
    return total ? posicoes.reduce((soma, item) => soma + item.sucessos, 0) / total : null;
  });
  protected readonly linhasConcordancia = computed<LinhaIntervalo[]>(() =>
    (this.dados()?.ragas.concordancia ?? []).map((item) => ({
      rotulo: this.metrica(item.metrica),
      valor: item.concordancia,
      ic: item.ic95,
    })),
  );

  protected readonly seriesFadiga = computed(() => {
    const ordem = this.dados()?.por_ordem ?? [];
    const serie = (
      valor: (item: Estatisticas['por_ordem'][number]) => number | null,
      formato: (v: number) => string,
    ): PontoLinha[] =>
      ordem.map((item) => {
        const y = valor(item);
        return {
          x: item.ordem,
          y,
          dica: `Rodada ${item.ordem}: ${y === null ? '—' : formato(y)} (${item.rodadas} rodadas)`,
        };
      });
    const segundos = (v: number) => `${Math.round(v)} s`;
    const porcento = (v: number) => `${Math.round(v * 100)}%`;
    const tempos = serie(
      (i) => (i.tempo_ativo_mediano_ms === null ? null : i.tempo_ativo_mediano_ms / 1000),
      segundos,
    );
    return {
      tempos,
      maiorTempo: Math.max(0, ...tempos.map((p) => p.y ?? 0)),
      nenhuma: serie((i) => (i.rodadas ? i.nenhuma / i.rodadas : null), porcento),
      posicao: serie((i) => i.taxa_posicao_1, porcento),
      avancada: serie((i) => i.taxa_avancado, porcento),
      segundos,
      porcento,
    };
  });

  protected readonly pontosCusto = computed<PontoDispersao[]>(() =>
    (this.dados()?.custo_beneficio ?? [])
      .filter((item) => item.taxa !== null && item.ms_p50 !== null)
      .map((item) => ({
        rotulo: this.curto(item.codigo),
        x: item.ms_p50 as number,
        y: item.taxa as number,
        ic: item.ic95,
        dica: `${this.pipeline(item.codigo)}: ${this.pct(item.taxa)} de vitórias, ${this.segundos(item.ms_p50)} de latência e ${this.num(item.tokens_medio)} tokens por resposta`,
      })),
  );
  protected readonly formatarLatencia = (valor: number): string => this.segundos(valor);

  protected readonly etapasPorPipeline = computed(() => {
    const dados = this.dados();
    if (!dados) {
      return [];
    }
    return dados.por_pipeline.map(({ codigo }) => {
      const itens = dados.custo.por_etapa.filter((item) => item.codigo === codigo);
      const total = itens.reduce((soma, item) => soma + item.ms_medio, 0);
      return {
        codigo,
        total,
        partes: ETAPAS.flatMap((etapa) => {
          const item = itens.find((linha) => linha.etapa === etapa.id);
          return item
            ? [{ ...etapa, ms: item.ms_medio, fracao: total ? item.ms_medio / total : 0 }]
            : [];
        }),
      };
    });
  });

  protected readonly efeitosRagasPorMetrica = computed(() => {
    const linhas = this.dados()?.ragas.efeitos_fatoriais ?? [];
    return Object.keys(ROTULOS_METRICA).map((metrica) => ({
      metrica,
      efeitos: ['ingestao', 'recuperacao', 'interacao'].map((efeito) =>
        linhas.find((linha) => linha.metrica === metrica && linha.efeito === efeito),
      ),
    }));
  });

  protected readonly maiorVitoriaDocumento = computed(() =>
    Math.max(
      1,
      ...(this.dados()?.por_documento ?? []).flatMap((doc) => Object.values(doc.vitorias)),
    ),
  );

  protected readonly avaliadoresParaRevisar = computed(
    () => this.dados()?.por_avaliador.filter((item) => item.revisar).length ?? 0,
  );

  protected readonly leituras = computed<Leitura[]>(() => {
    const dados = this.dados();
    if (!dados) {
      return [];
    }
    const textos: Record<string, [string, string]> = {
      ingestao: ['A extração estruturada aumenta a qualidade percebida?', 'Docling'],
      recuperacao: [
        'A recuperação avançada aumenta a qualidade percebida?',
        'Recuperação avançada',
      ],
      interacao: ['O efeito da recuperação depende da ingestão?', 'Diagonal 1 e 4'],
    };
    const linhas: Leitura[] = dados.efeitos.map((efeito) => {
      const [pergunta, nome] = textos[efeito.efeito] ?? [efeito.descricao, efeito.efeito];
      return {
        pergunta,
        veredito: this.textoVeredito(this.classificar(efeito)),
        detalhe:
          efeito.taxa === null
            ? 'Ainda sem rodadas com vencedor.'
            : `${nome}: ${this.pct(efeito.taxa)} das ${efeito.total} rodadas com vencedor (p de Holm ${this.p(efeito.p_holm)}).`,
        aba: 'preferencia',
      };
    });

    const concordancia = dados.ragas.concordancia.find((item) => item.metrica === 'media');
    linhas.push({
      pergunta: 'O RAGAS aponta a mesma resposta que as pessoas?',
      veredito: !concordancia?.rodadas
        ? 'sem dados'
        : (concordancia.p_valor ?? 1) < ALFA && (concordancia.concordancia ?? 0) > dados.acaso
          ? 'acima do acaso'
          : 'sem evidência de concordância',
      detalhe: concordancia?.rodadas
        ? `Concordância de ${this.pct(concordancia.concordancia)} em ${concordancia.rodadas} rodadas; o acaso daria 25%.`
        : 'Calcule o RAGAS na aba RAGAS × pessoas.',
      aba: 'ragas',
    });

    const melhor = [...dados.custo_beneficio].sort((a, b) => (b.taxa ?? 0) - (a.taxa ?? 0))[0];
    linhas.push({
      pergunta: 'O ganho compensa o custo?',
      veredito: melhor?.taxa === null || !melhor ? 'sem dados' : 'decisão sua',
      detalhe: melhor?.taxa
        ? `Mais vitórias: ${this.pipeline(melhor.codigo)}, com ${this.pct(melhor.taxa)} ${this.vezes(melhor.multiplo_latencia)} a latência e ${this.vezes(melhor.multiplo_tokens)} os tokens do pipeline 1.`
        : 'Sem dados de custo ainda.',
      aba: 'custo',
    });

    const metades = dados.metades;
    linhas.push({
      pergunta: 'Há sinal de fadiga ao longo do ciclo?',
      veredito: !metades
        ? 'sem dados'
        : metades.proporcoes.some((item) => (item.p_valor ?? 1) < ALFA)
          ? 'há sinal: investigar'
          : 'sem sinal',
      detalhe: metades
        ? `Tempo de leitura e decisão: ${ms(metades.tempo_ativo_inicio_ms)} nas rodadas 1 a 5 e ${ms(metades.tempo_ativo_fim_ms)} nas rodadas 6 a 10.`
        : 'Precisa de rodadas no início e no fim do ciclo.',
      aba: 'validade',
    });
    return linhas;
  });

  protected readonly alertas = computed<Array<{ texto: string; aba: AbaId }>>(() => {
    const dados = this.dados();
    if (!dados) {
      return [];
    }
    const alertas: Array<{ texto: string; aba: AbaId }> = [];
    if (dados.rodadas_decididas < dados.amostra.meta_rodadas[0]) {
      alertas.push({
        texto: `Só ${dados.rodadas_decididas} rodadas, abaixo do mínimo previsto de ${dados.amostra.meta_rodadas[0]}. Todo resultado é provisório.`,
        aba: 'validade',
      });
    }
    if (dados.avaliadores < dados.amostra.meta_avaliadores[0]) {
      alertas.push({
        texto: `Só ${dados.avaliadores} avaliadores, abaixo do mínimo previsto de ${dados.amostra.meta_avaliadores[0]}.`,
        aba: 'validade',
      });
    }
    if (dados.teste_posicao && dados.teste_posicao.p_valor < ALFA) {
      alertas.push({
        texto: `As escolhas dependem da posição exibida (p ${this.p(dados.teste_posicao.p_valor)}).`,
        aba: 'validade',
      });
    }
    const testeMarcacao = dados.marcacao_por_posicao.teste;
    if (testeMarcacao && testeMarcacao.p_valor < ALFA) {
      alertas.push({
        texto: `A marcação das outras respostas depende da posição exibida (p ${this.p(testeMarcacao.p_valor)}).`,
        aba: 'validade',
      });
    }
    const desequilibrados = dados.balanceamento.filter(
      (item) => item.teste && item.teste.p_valor < ALFA,
    );
    if (desequilibrados.length) {
      alertas.push({
        texto: `Sorteio de posições desequilibrado em ${desequilibrados.map((i) => this.curto(i.codigo)).join(', ')}.`,
        aba: 'validade',
      });
    }
    const tamanho = dados.vies_tamanho;
    if ((tamanho.p_valor ?? 1) < ALFA && (tamanho.taxa ?? 0) > tamanho.acaso) {
      alertas.push({
        texto: `A resposta mais longa venceu em ${this.pct(tamanho.taxa)} das rodadas (acaso: 25%).`,
        aba: 'validade',
      });
    }
    if (this.avaliadoresParaRevisar()) {
      alertas.push({
        texto: `${this.avaliadoresParaRevisar()} avaliador(es) com escolha concentrada em uma posição, para revisar.`,
        aba: 'validade',
      });
    }
    const truncadas = dados.coleta.truncadas_por_pipeline.filter((item) => item.respostas);
    if (truncadas.length) {
      alertas.push({
        texto: `Respostas cortadas pelo limite de tokens em ${truncadas.map((i) => `${this.curto(i.codigo)} (${i.respostas})`).join(', ')}.`,
        aba: 'validade',
      });
    }
    if (dados.coleta.falhas_de_rodada) {
      alertas.push({
        texto: `${dados.coleta.falhas_de_rodada} pergunta(s) falharam e não viraram rodada.`,
        aba: 'validade',
      });
    }
    if (dados.rodadas_decididas && !dados.ragas.respostas_avaliadas) {
      alertas.push({ texto: 'O RAGAS ainda não foi calculado para este estudo.', aba: 'ragas' });
    }
    return alertas;
  });

  private temporizador: ReturnType<typeof setTimeout> | undefined;

  constructor() {
    effect(() => {
      void this.buscar(this.studyId());
    });
    inject(DestroyRef).onDestroy(() => clearTimeout(this.temporizador));
  }

  protected async exportarCsv(): Promise<void> {
    if (this.exportando()) {
      return;
    }
    this.exportando.set(true);
    try {
      const csv = await this.api.baixarExportacao(this.studyId());
      const url = URL.createObjectURL(csv);
      const link = document.createElement('a');
      link.href = url;
      link.download = `estudo-${this.studyId()}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (erro) {
      this.erro.set((erro as Error).message);
    } finally {
      this.exportando.set(false);
    }
  }

  protected carregar(): void {
    void this.buscar(this.studyId());
  }

  protected pipeline(codigo: string): string {
    return ROTULOS_PIPELINE[codigo] ?? codigo;
  }

  protected curto(codigo: string): string {
    return codigo.replace('pipeline-', 'P');
  }

  protected metrica(nome: string): string {
    return ROTULOS_METRICA[nome] ?? nome;
  }

  protected proporcaoRotulo(nome: string): string {
    return ROTULOS_PROPORCAO[nome] ?? nome;
  }

  protected efeitoRotulo(nome: string): string {
    return ROTULOS_EFEITO[nome] ?? nome;
  }

  protected pct(valor: number | null | undefined, casas = 1): string {
    return valor === null || valor === undefined
      ? '—'
      : `${(valor * 100).toLocaleString('pt-BR', { maximumFractionDigits: casas })}%`;
  }

  protected ic(valor: Intervalo | null): string {
    return valor ? `${this.pct(valor[0])} a ${this.pct(valor[1])}` : '—';
  }

  protected p(valor: number | null | undefined): string {
    if (valor === null || valor === undefined) {
      return '—';
    }
    return valor < 0.001
      ? '< 0,001'
      : valor.toLocaleString('pt-BR', { maximumFractionDigits: 3, minimumFractionDigits: 3 });
  }

  protected num(valor: number | null | undefined, casas = 0): string {
    return valor === null || valor === undefined
      ? '—'
      : valor.toLocaleString('pt-BR', {
          maximumFractionDigits: casas,
          minimumFractionDigits: casas,
        });
  }

  protected segundos(valor: number | null): string {
    return ms(valor);
  }

  protected vezes(valor: number | null | undefined): string {
    return valor === null || valor === undefined ? '—' : `${this.num(valor, 1)}×`;
  }

  protected sinal(valor: number | null | undefined, casas = 1): string {
    if (valor === null || valor === undefined) {
      return '—';
    }
    return `${valor > 0 ? '+' : ''}${this.num(valor, casas)}`;
  }

  protected significativo(valor: number | null | undefined): boolean {
    return valor !== null && valor !== undefined && valor < ALFA;
  }

  protected excluiZero(ic: Intervalo | null | undefined): boolean {
    return !!ic && !inclui(ic, 0);
  }

  protected intensidade(vitorias: number): string {
    return `color-mix(in srgb, var(--grafico-1) ${Math.round((vitorias / this.maiorVitoriaDocumento()) * 55)}%, var(--color-canvas))`;
  }

  /** Atualiza sem recarregar a tela: o bootstrap do estudo inteiro não precisa rodar a cada anotação. */
  protected async anotar(answerId: string, causa: string): Promise<void> {
    this.erro.set(null);
    try {
      if (causa) {
        await this.api.anotarResposta(answerId, causa as CausaErro);
      } else {
        await this.api.removerAnotacao(answerId);
      }
      this.aviso.set('Anotação salva. Use "Atualizar" para recalcular as contagens.');
    } catch (erro) {
      this.erro.set((erro as Error).message);
    }
  }

  protected classeDoCaso(classe: ClasseErro): string {
    return CLASSES_ERRO.find((item) => item.id === classe)?.rotulo ?? classe;
  }

  private classificar(efeito: Estatisticas['efeitos'][number]): Veredito {
    if (efeito.taxa === null) {
      return 'sem dados';
    }
    if ((efeito.p_holm ?? 1) >= ALFA) {
      return 'sem evidência';
    }
    if (inclui(efeito.ic95_bootstrap, 0.5) || inclui(efeito.ic95_bootstrap_documento, 0.5)) {
      return 'inconclusivo';
    }
    return efeito.taxa > 0.5 ? 'a favor' : 'contra';
  }

  private textoVeredito(veredito: Veredito): string {
    return (
      { 'a favor': 'evidência a favor', contra: 'evidência contrária' }[veredito as string] ??
      veredito
    );
  }

  private async buscar(studyId: string): Promise<void> {
    clearTimeout(this.temporizador);
    this.erro.set(null);
    this.atualizando.set(true);
    try {
      const [dados, ragas] = await Promise.all([
        this.api.obterEstatisticas(studyId),
        this.api.obterSituacaoRagas(studyId),
      ]);
      this.dados.set(dados);
      this.ragas.set(ragas);
      this.atualizadoEm.set(new Date());
      this.acompanharRagas(studyId);
    } catch (erro) {
      this.erro.set((erro as Error).message);
    } finally {
      this.atualizando.set(false);
    }
  }

  private acompanharRagas(studyId: string): void {
    if (!this.ragas()?.em_andamento) {
      return;
    }
    this.temporizador = setTimeout(async () => {
      try {
        const ragas = await this.api.obterSituacaoRagas(studyId);
        this.ragas.set(ragas);
        if (ragas.em_andamento) {
          this.acompanharRagas(studyId);
        } else {
          // Terminou: as tabelas de concordância só mudam agora.
          this.aviso.set(null);
          await this.buscar(studyId);
        }
      } catch (erro) {
        this.erro.set(
          `Não foi possível acompanhar o RAGAS: ${(erro as Error).message} Use "Atualizar".`,
        );
      }
    }, INTERVALO_RAGAS_MS);
  }

  protected async calcularRagas(): Promise<void> {
    if (
      !confirm('O RAGAS faz dezenas de chamadas pagas por rodada. Calcular para todo o estudo?')
    ) {
      return;
    }
    this.erro.set(null);
    this.disparando.set(true);
    try {
      const resposta = await this.api.calcularRagasDoEstudo(this.studyId());
      this.aviso.set(resposta.mensagem);
      await this.buscar(this.studyId());
    } catch (erro) {
      this.erro.set((erro as Error).message);
    } finally {
      this.disparando.set(false);
    }
  }
}
