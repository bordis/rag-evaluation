import { TestBed } from '@angular/core/testing';

import type { QuestionRound, RotuloCego } from '../../models/evaluation-model';
import { AnswerChoice } from './answer-choice';

const ROTULOS: RotuloCego[] = ['A', 'B', 'C', 'D'];

function rodada(extras: Partial<QuestionRound> = {}): QuestionRound {
  return {
    id: 'rodada-1',
    ordem: 1,
    pergunta: 'O que a lei diz?',
    nenhumaCorreta: false,
    respostas: ROTULOS.map((rotulo) => ({
      id: `resposta-${rotulo}`,
      rotuloCego: rotulo,
      texto: `Texto ${rotulo}`,
    })),
    ...extras,
  };
}

const DECIDIDA = { escolhaRotulo: 'B' as RotuloCego, escolhidoEm: '2026-11-13T10:00:00Z' };

/** Zoneless: cede o event loop para os efeitos e a renderização terminarem. */
async function estabilizar(fixture: { whenStable(): Promise<unknown> }): Promise<void> {
  await fixture.whenStable();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await fixture.whenStable();
}

async function montar(round: QuestionRound) {
  TestBed.configureTestingModule({ imports: [AnswerChoice] });
  const fixture = TestBed.createComponent(AnswerChoice);
  fixture.componentRef.setInput('round', round);
  const escolhas: Array<RotuloCego | null> = [];
  const marcacoes: RotuloCego[][] = [];
  fixture.componentInstance.escolher.subscribe((rotulo) => escolhas.push(rotulo));
  fixture.componentInstance.confirmarMarcacao.subscribe((rotulos) => marcacoes.push(rotulos));
  document.body.appendChild(fixture.nativeElement);
  await estabilizar(fixture);
  return { fixture, tela: fixture.nativeElement as HTMLElement, escolhas, marcacoes };
}

describe('AnswerChoice', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('no primeiro passo, oferece escolher cada resposta ou nenhuma', async () => {
    const { tela, escolhas } = await montar(rodada());

    expect(tela.querySelectorAll('.answer__btn')).toHaveLength(4);
    expect(tela.querySelector('fieldset')).toBeNull();

    tela.querySelectorAll<HTMLButtonElement>('.answer__btn')[2].click();
    tela.querySelector<HTMLButtonElement>('.nenhuma')!.click();

    expect(escolhas).toEqual(['C', null]);
  });

  it('no segundo passo, trava a escolhida e mostra uma caixa por resposta restante', async () => {
    const { tela } = await montar(rodada(DECIDIDA));

    const legenda = tela.querySelector('fieldset > legend');
    expect(legenda?.textContent).toContain('Alguma das outras respostas também está correta?');
    expect(tela.querySelector('.answer__btn')).toBeNull();
    expect(tela.querySelector('.nenhuma')).toBeNull();
    expect(tela.querySelector('.answer--chosen .answer__label')?.textContent).toBe('Resposta B');
    expect(tela.querySelector('.answer--chosen input')).toBeNull();

    const rotulos = Array.from(tela.querySelectorAll<HTMLLabelElement>('.answer__marca')).map(
      (label) => label.textContent!.trim(),
    );
    expect(rotulos).toEqual([
      'Resposta A também está correta',
      'Resposta C também está correta',
      'Resposta D também está correta',
    ]);
    // Cada caixa tem um label associado.
    tela.querySelectorAll<HTMLInputElement>('.answer__marca input').forEach((caixa) => {
      expect(tela.querySelector(`label[for="${caixa.id}"]`)).not.toBeNull();
    });
  });

  it('leva o foco à pergunta ao entrar no segundo passo', async () => {
    const { tela } = await montar(rodada(DECIDIDA));

    expect(document.activeElement).toBe(tela.querySelector('legend'));
  });

  it('deixa "Confirmar" desabilitado até haver alguma marcação', async () => {
    const { fixture, tela, marcacoes } = await montar(rodada(DECIDIDA));
    const confirmar = tela.querySelector<HTMLButtonElement>('.confirmar')!;
    expect(confirmar.disabled).toBe(true);

    confirmar.click();
    expect(marcacoes).toEqual([]);

    tela.querySelectorAll<HTMLInputElement>('.answer__marca input')[2].click();
    await estabilizar(fixture);
    expect(confirmar.disabled).toBe(false);
  });

  it('envia as marcadas na ordem exibida', async () => {
    const { fixture, tela, marcacoes } = await montar(rodada(DECIDIDA));
    const caixas = tela.querySelectorAll<HTMLInputElement>('.answer__marca input');

    caixas[2].click();
    caixas[0].click();
    await estabilizar(fixture);
    tela.querySelector<HTMLButtonElement>('.confirmar')!.click();

    expect(marcacoes).toEqual([['A', 'D']]);
  });

  it('"Nenhuma das outras" é exclusiva: desmarca as caixas e vice-versa', async () => {
    const { fixture, tela, marcacoes } = await montar(rodada(DECIDIDA));
    const caixas = tela.querySelectorAll<HTMLInputElement>('.answer__marca input');
    const nenhumaOutra = tela.querySelector<HTMLInputElement>('.nenhuma-outra input')!;

    caixas[0].click();
    caixas[1].click();
    await estabilizar(fixture);
    nenhumaOutra.click();
    await estabilizar(fixture);

    expect(nenhumaOutra.checked).toBe(true);
    expect(Array.from(caixas).some((caixa) => caixa.checked)).toBe(false);

    caixas[2].click();
    await estabilizar(fixture);
    expect(nenhumaOutra.checked).toBe(false);
    expect(caixas[2].checked).toBe(true);

    nenhumaOutra.click();
    await estabilizar(fixture);
    tela.querySelector<HTMLButtonElement>('.confirmar')!.click();
    expect(marcacoes).toEqual([[]]);
  });

  it('a rodada "nenhuma está correta" não tem segundo passo', async () => {
    const { tela } = await montar(
      rodada({ nenhumaCorreta: true, escolhidoEm: '2026-11-13T10:00:00Z' }),
    );

    expect(tela.querySelector('fieldset')).toBeNull();
    expect(tela.querySelector('.answer__btn')).toBeNull();
    expect(tela.querySelector('.intro__text')?.textContent).toContain('nenhuma resposta');
  });

  it('a rodada completa mostra a escolhida e as também corretas, sem ações', async () => {
    const { tela } = await montar(
      rodada({ ...DECIDIDA, tambemCorretas: ['D'], marcadoEm: '2026-11-13T10:01:00Z' }),
    );

    expect(tela.querySelector('fieldset')).toBeNull();
    expect(tela.querySelector('input')).toBeNull();
    expect(tela.querySelector('.answer__chip--tambem')?.closest('li')?.dataset['rotulo']).toBe('D');
  });
});
