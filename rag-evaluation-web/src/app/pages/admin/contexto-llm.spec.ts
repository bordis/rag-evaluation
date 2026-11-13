import { formatarContextoDocumento, formatarContextoIngestao } from './contexto-llm';

describe('formatarContextoDocumento', () => {
  it('mostra a faixa entre os pipelines com percentuais inteiros', () => {
    expect(
      formatarContextoDocumento({
        chunks: 6,
        tokens_estimados: 1480,
        percentual_min: 7.1,
        percentual_max: 9.4,
      }),
    ).toBe('6 chunks · ≈1.500 tokens · 7–9%');
  });

  it('mostra um valor só quando min e max arredondados coincidem', () => {
    expect(
      formatarContextoDocumento({
        chunks: 6,
        tokens_estimados: 900,
        percentual_min: 7.6,
        percentual_max: 8.4,
      }),
    ).toBe('6 chunks · ≈900 tokens · 8%');
  });

  it('usa ponto de milhar e singular para um chunk', () => {
    expect(
      formatarContextoDocumento({
        chunks: 1,
        tokens_estimados: 12345,
        percentual_min: 100,
        percentual_max: 100,
      }),
    ).toBe('1 chunk · ≈12.000 tokens · 100%');
  });

  it('mostra travessão sem ingestão concluída', () => {
    expect(formatarContextoDocumento(null)).toBe('—');
  });
});

describe('formatarContextoIngestao', () => {
  it('mostra chunks e percentual com uma casa', () => {
    expect(formatarContextoIngestao(6, 8.3)).toBe('6 (8,3%)');
    expect(formatarContextoIngestao(6, 50)).toBe('6 (50,0%)');
  });

  it('mostra travessão sem percentual', () => {
    expect(formatarContextoIngestao(6, null)).toBe('—');
  });
});
