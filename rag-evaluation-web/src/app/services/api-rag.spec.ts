import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../environments/environment';
import { ApiRag } from './api-rag';

describe('ApiRag', () => {
  let api: ApiRag;
  let http: HttpTestingController;
  const base = environment.apiBaseUrl;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(ApiRag);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('only asks for documents that finished ingestion in every pipeline', async () => {
    // Act
    const promessa = api.listarDocumentos();
    const requisicao = http.expectOne(`${base}/documents?status=pronto`);
    requisicao.flush([]);

    // Assert
    expect(requisicao.request.method).toBe('GET');
    await expect(promessa).resolves.toEqual([]);
  });

  it('converts the snake_case round into the domain shape', async () => {
    // Act
    const promessa = api.perguntar('sessao-1', 'lgpd', 'O que a lei diz?');
    const requisicao = http.expectOne(`${base}/sessions/sessao-1/documents/lgpd/questions`);
    requisicao.flush({
      id: 'rodada-1',
      pergunta: 'O que a lei diz?',
      respostas: [{ id: 'r-a', rotulo: 'A', texto: 'Texto A' }],
      escolha_rotulo: null,
      escolhido_em: null,
    });

    // Assert
    expect(requisicao.request.body).toEqual({ pergunta: 'O que a lei diz?' });
    await expect(promessa).resolves.toEqual({
      id: 'rodada-1',
      pergunta: 'O que a lei diz?',
      respostas: [{ id: 'r-a', rotuloCego: 'A', texto: 'Texto A' }],
      escolhaRotulo: undefined,
      escolhidoEm: undefined,
    });
  });

  it('sends null instead of empty strings when the profile is skipped', async () => {
    // Act
    const promessa = api.criarSessao({});
    const requisicao = http.expectOne(`${base}/sessions`);
    requisicao.flush({ id: 'sessao-1' });

    // Assert
    expect(requisicao.request.body).toEqual({
      area_atuacao: null,
      familiaridade: null,
      tempo_experiencia: null,
    });
    await expect(promessa).resolves.toBe('sessao-1');
  });

  it('turns the API detail into the message shown to the evaluator', async () => {
    // Act
    const promessa = api.escolher('rodada-1', 'A');
    http
      .expectOne(`${base}/rounds/rodada-1/choice`)
      .flush({ detail: 'Esta rodada já foi decidida.' }, { status: 409, statusText: 'Conflict' });

    // Assert
    await expect(promessa).rejects.toThrowError('Esta rodada já foi decidida.');
  });

  it('explains an unreachable server instead of leaking the HTTP failure', async () => {
    // Act
    const promessa = api.obterProgresso('sessao-1');
    http
      .expectOne(`${base}/sessions/sessao-1/progress`)
      .error(new ProgressEvent('error'), { status: 0 });

    // Assert
    await expect(promessa).rejects.toThrowError(/API está no ar/);
  });
});
