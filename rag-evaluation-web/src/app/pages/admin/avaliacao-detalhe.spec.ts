import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import {
  ApiAdmin,
  type AvaliacaoDetalhe,
  type RespostaDetalhe,
  type RodadaAdmin,
} from '../../services/api-admin';
import { AdminAvaliacaoDetalhe } from './avaliacao-detalhe';

function resposta(
  rotulo: string,
  codigo: string,
  media: number | null,
  escolhida = false,
): RespostaDetalhe {
  return {
    id: `resposta-${rotulo}`,
    rotulo,
    posicao_exibida: 1,
    pipeline_codigo: codigo,
    pipeline_nome: codigo,
    escolhida,
    texto: 'Texto',
    config_snapshot: {},
    metricas: [],
    chunks: [],
    ragas:
      media === null
        ? null
        : {
            fidelidade: media,
            relevancia_resposta: media,
            precisao_contexto: media,
            media,
            erro: null,
          },
  };
}

function rodada(ordem: number, extras: Partial<RodadaAdmin>): RodadaAdmin {
  return {
    id: `rodada-${ordem}`,
    ordem,
    pergunta: `Pergunta ${ordem}`,
    nenhuma_correta: false,
    decidida: true,
    tempo_total_ms: null,
    tempo_geracao_ms: null,
    tempo_oculto_ms: null,
    respostas: [],
    ...extras,
  };
}

const AVALIACAO: AvaliacaoDetalhe = {
  session_id: 'sessao-1',
  documento_titulo: 'Documento',
  study_id: 'estudo-1',
  estudo_nome: 'Estudo',
  termo_versao: 'v1',
  aceito_em: null,
  rodadas: [
    rodada(1, {
      respostas: [resposta('A', 'pipeline-1', 0.4, true), resposta('B', 'pipeline-3', 0.9)],
    }),
    rodada(2, {
      respostas: [resposta('A', 'pipeline-2', 0.7), resposta('B', 'pipeline-4', 0.7, true)],
    }),
    rodada(3, {
      nenhuma_correta: true,
      respostas: [resposta('A', 'pipeline-1', 0.8), resposta('B', 'pipeline-2', null)],
    }),
    rodada(4, { decidida: false, respostas: [resposta('A', 'pipeline-1', null)] }),
  ],
};

async function abrir(): Promise<HTMLElement> {
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      { provide: ApiAdmin, useValue: { obterAvaliacao: async () => AVALIACAO } },
    ],
  });
  const fixture = TestBed.createComponent(AdminAvaliacaoDetalhe);
  fixture.componentRef.setInput('sessionId', 'sessao-1');
  fixture.componentRef.setInput('documentId', 'documento-1');
  await fixture.whenStable();
  await new Promise((resolve) => setTimeout(resolve));
  await fixture.whenStable();
  return fixture.nativeElement as HTMLElement;
}

function celulas(tela: HTMLElement): string[][] {
  const linhas = tela.querySelectorAll('table.adm-tabela:not(.adm-tabela--interna) tbody tr');
  return Array.from(linhas).map((linha) =>
    Array.from(linha.querySelectorAll('td')).map((td) => td.textContent!.trim()),
  );
}

describe('AdminAvaliacaoDetalhe', () => {
  it('compara, por pergunta, a escolha do avaliador com o melhor no RAGAS', async () => {
    const tela = await abrir();

    expect(celulas(tela)).toEqual([
      ['1', 'Pergunta 1', 'pipeline-1 (A)', 'pipeline-3 (B)'],
      ['2', 'Pergunta 2', 'pipeline-4 (B)', 'Empate: pipeline-2 (A), pipeline-4 (B)'],
      ['3', 'Pergunta 3', 'Nenhuma está correta', 'Sem notas completas'],
      ['4', 'Pergunta 4', 'Pendente', 'Sem notas completas'],
    ]);
  });

  it('marca no cartão a resposta melhor no RAGAS', async () => {
    const tela = await abrir();

    const cartoes = Array.from(tela.querySelectorAll('article.adm-cartao'));
    expect(cartoes.map((cartao) => cartao.textContent!.includes('Melhor no RAGAS'))).toEqual([
      false,
      true,
    ]);
  });
});
