import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { ApiAdmin, type Estatisticas } from '../../services/api-admin';
import { AJUDA } from './resultados-ajuda';
import { AdminResultados } from './resultados';

const TAXA_VAZIA = { sucessos: 0, total: 0, taxa: null, ic95: null };

const ESTUDO_VAZIO: Estatisticas = {
  rodadas_decididas: 0,
  avaliadores: 0,
  acaso: 0.25,
  amostra: {
    meta_avaliadores: [20, 50],
    meta_rodadas: [200, 500],
    documentos: 0,
    ciclos: 0,
    ciclos_completos: 0,
    rodadas_por_avaliador_min: null,
    rodadas_por_avaliador_mediana: null,
    rodadas_por_avaliador_max: null,
  },
  nenhuma: { ...TAXA_VAZIA, ic95_bootstrap: null },
  por_pipeline: [],
  comparacoes_simples: [],
  poder: null,
  efeitos: [
    {
      ...TAXA_VAZIA,
      efeito: 'ingestao',
      descricao: 'H1',
      ic95_bootstrap: null,
      ic95_bootstrap_documento: null,
      p_valor: null,
      p_holm: null,
      pontos_acima_de_50: null,
      razao_chances: null,
    },
  ],
  por_documento: [],
  por_posicao: [],
  teste_posicao: null,
  balanceamento: [],
  por_ordem: [],
  metades: null,
  vies_tamanho: { ...TAXA_VAZIA, acaso: 0.25, p_valor: null, por_pipeline: [] },
  taxa_correcao: { rodadas_completas: 0, decididas_sem_marcacao: 0, por_pipeline: [] },
  marcacao_por_posicao: { respostas: 0, por_posicao: [], teste: null },
  marcacao_por_avaliador: [],
  por_avaliador: [],
  confiabilidade: null,
  custo: { por_pipeline: [], por_etapa: [], ingestao: [] },
  custo_beneficio: [],
  contexto: { por_pipeline: [], sobreposicao: [] },
  ragas: {
    respostas_avaliadas: 0,
    kendall_tau_ordenacao: null,
    concordancia: [],
    media_por_pipeline: [],
    vitorias_comparadas: [],
    por_margem: [],
    efeitos_fatoriais: [],
    rejeitadas: {
      rodadas_rejeitadas: 0,
      rodadas_decididas: 0,
      melhor_nota_rejeitadas: null,
      melhor_nota_decididas: null,
    },
  },
  coleta: {
    viu_todas: TAXA_VAZIA,
    tempo_pergunta_mediano_ms: null,
    rodadas_recarregadas: 0,
    falhas_de_rodada: 0,
    truncadas_por_pipeline: [],
  },
  ambiente: {},
  erros: { limiar: 0.5, rodadas: 0, por_pipeline: [], causas_confirmadas: [], casos: [] },
};

async function montar(dados: Estatisticas, aba?: string) {
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      {
        provide: ApiAdmin,
        useValue: {
          obterEstatisticas: () => Promise.resolve(dados),
          obterSituacaoRagas: () =>
            Promise.resolve({
              em_andamento: false,
              total: 0,
              avaliadas: 0,
              com_erro: 0,
              ultimo_erro: null,
            }),
          baixarExportacao: () => Promise.resolve(new Blob(['a;b'])),
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(AdminResultados);
  fixture.componentRef.setInput('studyId', 'estudo');
  if (aba) {
    fixture.componentRef.setInput('aba', aba);
  }
  await fixture.whenStable();
  await new Promise((resolve) => setTimeout(resolve));
  await fixture.whenStable();
  return { fixture, elemento: fixture.nativeElement as HTMLElement };
}

describe('AdminResultados', () => {
  it('abre o panorama por padrão e também quando a aba da URL não existe', async () => {
    const { elemento } = await montar(ESTUDO_VAZIO, 'inexistente');

    expect(elemento.querySelector('.aba--ativa')?.textContent).toContain('Panorama');
    expect(elemento.textContent).toContain('O que os dados dizem até agora');
  });

  it('avisa no panorama que a amostra está abaixo do previsto', async () => {
    const { elemento } = await montar({
      ...ESTUDO_VAZIO,
      rodadas_decididas: 12,
      avaliadores: 2,
    });

    expect(elemento.querySelector('.alertas')?.textContent).toContain('Só 12 rodadas');
    expect(elemento.querySelector('.alertas')?.textContent).toContain('Só 2 avaliadores');
  });

  it.each(['panorama', 'preferencia', 'validade', 'ragas', 'custo', 'erros'])(
    'na aba %s, toda análise tem um botão de ajuda, mesmo sem dados',
    async (aba) => {
      const { elemento } = await montar(ESTUDO_VAZIO, aba);

      const cartoes = elemento.querySelectorAll('app-analise-cartao');
      expect(cartoes.length).toBeGreaterThan(0);
      cartoes.forEach((cartao) => {
        expect(cartao.querySelector('button[aria-expanded]')).not.toBeNull();
      });
    },
  );

  it('o botão "?" mostra e esconde a explicação', async () => {
    const { fixture, elemento } = await montar(ESTUDO_VAZIO, 'preferencia');
    const botao = elemento.querySelector<HTMLButtonElement>('button[aria-expanded]')!;
    const painel = elemento.querySelector<HTMLElement>('#' + botao.getAttribute('aria-controls'))!;
    expect(painel.hidden).toBe(true);

    botao.click();
    await fixture.whenStable();

    expect(botao.getAttribute('aria-expanded')).toBe('true');
    expect(painel.hidden).toBe(false);
    expect(painel.textContent).toContain('Chiang et al.');
  });

  it('mostra a taxa de correção por pipeline na aba de preferência', async () => {
    const { elemento } = await montar(
      {
        ...ESTUDO_VAZIO,
        taxa_correcao: {
          rodadas_completas: 12,
          decididas_sem_marcacao: 2,
          por_pipeline: [
            {
              codigo: 'pipeline-4',
              sucessos: 9,
              total: 12,
              taxa: 0.75,
              ic95: [0.47, 0.91],
              ic95_bootstrap: [0.5, 0.95],
            },
          ],
        },
      },
      'preferencia',
    );

    const cartao = Array.from(elemento.querySelectorAll('app-analise-cartao')).find((item) =>
      item.textContent!.includes('Taxa de correção'),
    )!;
    expect(cartao.textContent).toContain('P4 · Docling, avançada');
    expect(cartao.textContent).toContain('9 / 12');
    expect(cartao.textContent).toContain('75%');
    expect(cartao.textContent).toContain('2 rodada(s) com vencedora ainda sem a');
  });

  it('mostra marcação por posição e por avaliador na aba de validade', async () => {
    const { elemento } = await montar(
      {
        ...ESTUDO_VAZIO,
        marcacao_por_posicao: {
          respostas: 30,
          por_posicao: [1, 2, 3, 4].map((posicao) => ({
            posicao,
            sucessos: 3,
            total: 7,
            taxa: 3 / 7,
            ic95: [0.15, 0.75] as [number, number],
          })),
          teste: { qui2: 12.3, gl: 3, p_valor: 0.006 },
        },
        marcacao_por_avaliador: [
          {
            numero: 1,
            avaliador: 'sessao-1',
            rodadas_marcadas: 8,
            todas_marcadas: 8,
            nenhuma_marcada: 0,
            taxa_todas_marcadas: 1,
            taxa_nenhuma_marcada: 0,
            outras_marcadas_media: 3,
          },
        ],
      },
      'validade',
    );

    expect(elemento.textContent).toContain('Qui-quadrado de homogeneidade');
    expect(elemento.textContent).toContain('3 graus de');
    const tabela = Array.from(elemento.querySelectorAll('app-analise-cartao')).find((item) =>
      item.textContent!.includes('Marcação por avaliador'),
    )!;
    expect(tabela.textContent).toContain('Avaliador 1');
    expect(tabela.textContent).toContain('8 (100%)');
  });

  it('alerta no panorama quando a marcação depende da posição', async () => {
    const { elemento } = await montar({
      ...ESTUDO_VAZIO,
      marcacao_por_posicao: {
        respostas: 30,
        por_posicao: [],
        teste: { qui2: 12.3, gl: 3, p_valor: 0.006 },
      },
    });

    expect(elemento.querySelector('.alertas')?.textContent).toContain(
      'A marcação das outras respostas depende da posição',
    );
  });

  it('toda ajuda explica como ler e cita a fonte', () => {
    for (const ajuda of Object.values(AJUDA)) {
      expect(ajuda.oQueE.length).toBeGreaterThan(0);
      expect(ajuda.comoLer.length).toBeGreaterThan(0);
      expect(ajuda.fontes.length).toBeGreaterThan(0);
    }
  });
});
