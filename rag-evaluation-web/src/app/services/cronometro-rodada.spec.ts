import { TestBed } from '@angular/core/testing';

import { CronometroRodada } from './cronometro-rodada';

describe('CronometroRodada', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.useFakeTimers();
    vi.setSystemTime(1_000_000);
    vi.stubGlobal('IntersectionObserver', class {});
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  function novo(): CronometroRodada {
    TestBed.resetTestingModule();
    return TestBed.inject(CronometroRodada);
  }

  it('separa o tempo de escrever a pergunta do tempo oculto', () => {
    const cronometro = novo();
    cronometro.retomar('doc');
    vi.advanceTimersByTime(1000);
    cronometro.pausar();
    vi.advanceTimersByTime(5000);
    cronometro.retomar('doc');
    vi.advanceTimersByTime(2000);

    cronometro.registrarPergunta('doc');

    const tempos = cronometro.ler('doc');
    expect(tempos?.perguntaMs).toBe(3000);
    expect(tempos?.ocultoMs).toBe(5000);
  });

  it('conta cada resposta vista uma vez só', () => {
    const cronometro = novo();
    cronometro.retomar('doc');

    cronometro.registrarVista('doc', 'A');
    cronometro.registrarVista('doc', 'A');
    cronometro.registrarVista('doc', 'C');

    expect(cronometro.ler('doc')?.respostasVistas).toBe(2);
  });

  it('sem o observador do navegador, a medida fica nula e não zero', () => {
    vi.stubGlobal('IntersectionObserver', undefined);
    const cronometro = novo();
    cronometro.retomar('doc');

    expect(cronometro.ler('doc')?.respostasVistas).toBeNull();
  });

  it('conta recarga da página, mas não a volta de outra aba', () => {
    const cronometro = novo();
    cronometro.retomar('doc');
    cronometro.pausar();
    cronometro.retomar('doc');
    expect(cronometro.ler('doc')?.recarregamentos).toBe(0);

    const depoisDoF5 = novo();
    depoisDoF5.retomar('doc');

    expect(depoisDoF5.ler('doc')?.recarregamentos).toBe(1);
  });

  it('a rodada seguinte começa com as medidas zeradas', () => {
    const cronometro = novo();
    cronometro.retomar('doc');
    cronometro.registrarPergunta('doc');
    cronometro.registrarVista('doc', 'A');

    cronometro.reiniciar('doc');

    const tempos = cronometro.ler('doc');
    expect(tempos?.perguntaMs).toBeNull();
    expect(tempos?.respostasVistas).toBe(0);
  });
});
