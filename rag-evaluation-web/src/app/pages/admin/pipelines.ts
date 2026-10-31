import { JsonPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';

import { ApiAdmin, type PipelineAdmin } from '../../services/api-admin';

/**
 * CRUD dos pipelines. O servidor impõe as travas: braço de controle sem técnicas avançadas, nada
 * muda com estudo aberto, e pipeline com respostas não é excluído. Aqui só aparece a mensagem.
 */
@Component({
  selector: 'app-admin-pipelines',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [JsonPipe],
  templateUrl: './pipelines.html',
})
export class AdminPipelines {
  private readonly api = inject(ApiAdmin);

  protected readonly pipelines = signal<PipelineAdmin[]>([]);
  protected readonly editando = signal<number | null>(null);
  protected readonly erro = signal<string | null>(null);

  constructor() {
    void this.executar(async () => undefined);
  }

  private async executar(acao: () => Promise<unknown>): Promise<boolean> {
    this.erro.set(null);
    try {
      await acao();
      this.pipelines.set(await this.api.listarPipelines());
      return true;
    } catch (erro) {
      this.erro.set((erro as Error).message);
      return false;
    }
  }

  protected async salvar(pipeline: PipelineAdmin, texto: string): Promise<void> {
    let config: Record<string, unknown>;
    try {
      config = JSON.parse(texto) as Record<string, unknown>;
    } catch {
      this.erro.set('A configuração não é um JSON válido.');
      return;
    }
    if (await this.executar(() => this.api.atualizarPipeline(pipeline.id, { config }))) {
      this.editando.set(null);
    }
  }

  protected alternar(pipeline: PipelineAdmin): void {
    void this.executar(() => this.api.atualizarPipeline(pipeline.id, { ativo: !pipeline.ativo }));
  }

  protected excluir(pipeline: PipelineAdmin): void {
    if (confirm(`Excluir ${pipeline.codigo}?`)) {
      void this.executar(() => this.api.excluirPipeline(pipeline.id));
    }
  }

  protected async criar(evento: Event): Promise<void> {
    evento.preventDefault();
    const formulario = evento.target as HTMLFormElement;
    const dados = new FormData(formulario);
    const criado = await this.executar(() =>
      this.api.criarPipeline({
        codigo: String(dados.get('codigo')),
        nome: String(dados.get('nome')),
        parser: dados.get('parser') as PipelineAdmin['parser'],
        collection_name: String(dados.get('collection_name')),
        config: { top_k: 15 },
      }),
    );
    if (criado) {
      formulario.reset();
    }
  }
}
