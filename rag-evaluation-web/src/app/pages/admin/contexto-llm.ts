import type { ContextoDocumento } from '../../services/api-admin';

/** Texto do cabeçalho "Contexto ao LLM" (no `title` e na nota sob a tabela). */
export const AJUDA_CONTEXTO_LLM =
  'Fração do documento entregue ao LLM em cada resposta: chunks do contexto ÷ chunks do documento. A faixa cobre os 4 pipelines. Valores altos indicam efeito teto: qualquer busca encontra o trecho certo.';

function inteiro(valor: number): string {
  return valor.toLocaleString('pt-BR', { maximumFractionDigits: 0 });
}

/** Estimativa: dois algarismos significativos bastam (1480 → "1.500"). */
function aproximado(valor: number): string {
  return valor.toLocaleString('pt-BR', { maximumSignificantDigits: 2 });
}

/**
 * Célula da listagem de documentos: `6 chunks · ≈1.500 tokens · 7–9%`. Percentuais inteiros;
 * quando min e max arredondados coincidem, um valor só (`8%`). `—` sem ingestão concluída.
 */
export function formatarContextoDocumento(contexto: ContextoDocumento | null): string {
  if (!contexto) {
    return '—';
  }
  const minimo = Math.round(contexto.percentual_min);
  const maximo = Math.round(contexto.percentual_max);
  const percentual =
    minimo === maximo ? `${inteiro(minimo)}%` : `${inteiro(minimo)}–${inteiro(maximo)}%`;
  const chunks = `${inteiro(contexto.chunks)} ${contexto.chunks === 1 ? 'chunk' : 'chunks'}`;
  return `${chunks} · ≈${aproximado(contexto.tokens_estimados)} tokens · ${percentual}`;
}

/** Célula da ingestão de um pipeline: `6 (8,3%)`; `—` quando o percentual não existe. */
export function formatarContextoIngestao(chunks: number, percentual: number | null): string {
  if (percentual === null) {
    return '—';
  }
  const texto = percentual.toLocaleString('pt-BR', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  return `${inteiro(chunks)} (${texto}%)`;
}
