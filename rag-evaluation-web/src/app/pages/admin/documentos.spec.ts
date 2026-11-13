import { TestBed } from '@angular/core/testing';

import { ApiAdmin, type DocumentoAdmin, type Ingestao } from '../../services/api-admin';
import { AdminDocumentos } from './documentos';

function documento(id: string, contexto: DocumentoAdmin['contexto']): DocumentoAdmin {
  return {
    id,
    slug: id,
    titulo: `Documento ${id}`,
    area: 'Área',
    status: contexto ? 'pronto' : 'processando',
    paginas: 10,
    tabelas: 2,
    imagens: 1,
    criado_em: '2026-11-13T10:00:00Z',
    pdf_disponivel: true,
    contexto,
  };
}

const DOCUMENTOS = [
  documento('a', { chunks: 6, tokens_estimados: 1480, percentual_min: 7.1, percentual_max: 9.4 }),
  documento('b', null),
];

const INGESTOES: Ingestao[] = [
  {
    pipeline_codigo: 'pipeline-1',
    status: 'concluida',
    erro: null,
    total_chunks: 72,
    tokens_embedding: 30000,
    duracao_parsing_ms: 100,
    duracao_total_ms: 900,
    contexto_chunks: 6,
    contexto_percentual: 8.3,
  },
  {
    pipeline_codigo: 'pipeline-2',
    status: 'processando',
    erro: null,
    total_chunks: 0,
    tokens_embedding: 0,
    duracao_parsing_ms: 0,
    duracao_total_ms: 0,
    contexto_chunks: 6,
    contexto_percentual: null,
  },
];

async function estabilizar(fixture: { whenStable(): Promise<unknown> }): Promise<void> {
  await fixture.whenStable();
  await new Promise((resolve) => setTimeout(resolve));
  await fixture.whenStable();
}

async function abrir() {
  TestBed.configureTestingModule({
    providers: [
      {
        provide: ApiAdmin,
        useValue: {
          listarDocumentos: async () => DOCUMENTOS,
          listarIngestoes: async () => INGESTOES,
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(AdminDocumentos);
  await estabilizar(fixture);
  return fixture;
}

function linhas(tela: HTMLElement, seletor: string): string[][] {
  return Array.from(tela.querySelectorAll(`${seletor} > tbody > tr`)).map((linha) =>
    Array.from(linha.querySelectorAll(':scope > td')).map((td) => td.textContent!.trim()),
  );
}

describe('AdminDocumentos', () => {
  afterEach(() => TestBed.resetTestingModule());

  it('mostra o contexto ao LLM entre Imagens e PDF, com a explicação no cabeçalho', async () => {
    const fixture = await abrir();
    const tela = fixture.nativeElement as HTMLElement;

    const cabecalhos = Array.from(tela.querySelectorAll('table.adm-tabela > thead th'));
    const nomes = cabecalhos.map((th) => th.textContent!.trim());
    expect(nomes.slice(5, 7)).toEqual(['Imagens', 'Contexto ao LLM']);
    expect(nomes[7]).toBe('PDF');
    const coluna = cabecalhos[6];
    expect(coluna.getAttribute('title')).toContain('efeito teto');
    const ajuda = tela.querySelector(`#${coluna.getAttribute('aria-describedby')}`);
    expect(ajuda!.textContent).toContain('chunks do contexto ÷ chunks do documento');

    const celulas = linhas(tela, 'table.adm-tabela:not(.adm-tabela--interna)');
    expect(celulas.map((linha) => linha[6])).toEqual(['6 chunks · ≈1.500 tokens · 7–9%', '—']);
    fixture.destroy();
  });

  it('mostra o contexto de cada pipeline nas ingestões, depois de Tokens', async () => {
    const fixture = await abrir();
    const tela = fixture.nativeElement as HTMLElement;

    const botao = Array.from(tela.querySelectorAll('button')).find((item) =>
      item.textContent!.includes('Exibir detalhes'),
    )!;
    botao.click();
    await estabilizar(fixture);

    const interna = tela.querySelector('table.adm-tabela--interna')!;
    expect(interna.closest('td')!.getAttribute('colspan')).toBe('9');
    const nomes = Array.from(interna.querySelectorAll('thead th')).map((th) =>
      th.textContent!.trim(),
    );
    expect(nomes.slice(3, 5)).toEqual(['Tokens', 'Contexto']);
    const celulas = linhas(tela, 'table.adm-tabela--interna');
    expect(celulas.map((linha) => linha[4])).toEqual(['6 (8,3%)', '—']);
    fixture.destroy();
  });
});
