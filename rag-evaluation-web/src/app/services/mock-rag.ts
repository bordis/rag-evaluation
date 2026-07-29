import { Injectable } from '@angular/core';

import type { PipelineAnswer, PipelineId, RagDocument, RotuloCego } from '../models/evaluation-model';

/**
 * Fonte de dados MOCK. Substitui, por ora, o backend real do pipeline RAG:
 * expõe a lista de documentos e gera 3 respostas candidatas por pergunta, uma
 * por configuração de pipeline. As respostas são embaralhadas nos rótulos
 * cegos A/B/C para que a posição não revele qual pipeline as gerou.
 */
@Injectable({ providedIn: 'root' })
export class MockRag {
  private readonly documentos: readonly RagDocument[] = [
    {
      id: 'lgpd',
      titulo: 'Lei Geral de Proteção de Dados (LGPD)',
      area: 'Direito & Privacidade',
      icone: '⚖️',
      descricao:
        'Texto consolidado da Lei nº 13.709/2018, cobrindo bases legais, direitos do titular e sanções.',
    },
    {
      id: 'nutricao-esportiva',
      titulo: 'Guia de Nutrição Esportiva',
      area: 'Saúde & Bem-estar',
      icone: '🥗',
      descricao:
        'Manual sobre macronutrientes, hidratação e periodização alimentar para praticantes de exercício.',
    },
    {
      id: 'kubernetes',
      titulo: 'Fundamentos de Kubernetes',
      area: 'Tecnologia & Infraestrutura',
      icone: '☸️',
      descricao:
        'Documentação introdutória sobre pods, deployments, services e orquestração de contêineres.',
    },
    {
      id: 'historia-brasil',
      titulo: 'História do Brasil — Período Colonial',
      area: 'História',
      icone: '📜',
      descricao:
        'Panorama do Brasil colônia: ciclos econômicos, administração portuguesa e sociedade açucareira.',
    },
    {
      id: 'financas-pessoais',
      titulo: 'Manual de Finanças Pessoais',
      area: 'Economia & Finanças',
      icone: '💰',
      descricao:
        'Conceitos de orçamento, reserva de emergência, juros compostos e estratégias de investimento.',
    },
    {
      id: 'mudancas-climaticas',
      titulo: 'Relatório sobre Mudanças Climáticas',
      area: 'Meio Ambiente',
      icone: '🌍',
      descricao:
        'Síntese de dados sobre emissões, cenários de aquecimento e políticas de mitigação e adaptação.',
    },
  ];

  getDocuments(): RagDocument[] {
    return [...this.documentos];
  }

  getDocument(id: string): RagDocument | undefined {
    return this.documentos.find((doc) => doc.id === id);
  }

  /**
   * Gera 3 respostas candidatas (uma por pipeline) para a pergunta, com estilos
   * distintos — concisa, intermediária e detalhada — e as distribui de forma
   * aleatória entre os rótulos cegos A/B/C.
   */
  gerarRespostas(pergunta: string): PipelineAnswer[] {
    const trecho = pergunta.trim().replace(/\s+/g, ' ');

    const candidatas: Array<{ pipeline: PipelineId; texto: string }> = [
      {
        pipeline: 'pipeline-a',
        texto: this.respostaConcisa(trecho),
      },
      {
        pipeline: 'pipeline-b',
        texto: this.respostaIntermediaria(trecho),
      },
      {
        pipeline: 'pipeline-c',
        texto: this.respostaDetalhada(trecho),
      },
    ];

    const rotulos: RotuloCego[] = this.embaralhar(['A', 'B', 'C']);

    return candidatas.map((candidata, indice) => ({
      pipeline: candidata.pipeline,
      rotuloCego: rotulos[indice],
      texto: candidata.texto,
    }));
  }

  private respostaConcisa(pergunta: string): string {
    return (
      `Com base no documento, a resposta direta é: os pontos essenciais relacionados a ` +
      `"${this.tema(pergunta)}" estão descritos na seção correspondente. Em resumo, o texto ` +
      `apresenta a definição e os critérios principais, sem entrar em exceções.`
    );
  }

  private respostaIntermediaria(pergunta: string): string {
    return (
      `O documento aborda "${this.tema(pergunta)}" em mais de um trecho. De forma geral, ele ` +
      `estabelece os conceitos centrais e, em seguida, detalha como se aplicam na prática. ` +
      `Vale observar que há condições específicas que alteram o resultado conforme o contexto, ` +
      `então a interpretação depende do cenário apresentado na pergunta.`
    );
  }

  private respostaDetalhada(pergunta: string): string {
    return (
      `Analisando o conteúdo em profundidade, "${this.tema(pergunta)}" é tratado a partir de três ` +
      `perspectivas complementares. Primeiro, o documento define os fundamentos e a terminologia. ` +
      `Segundo, descreve os mecanismos e procedimentos envolvidos, com exemplos ilustrativos. ` +
      `Terceiro, discute limitações, exceções e implicações práticas. A conclusão sugere que a ` +
      `resposta completa combina esses três eixos, evitando simplificações que ignorem os casos de borda.`
    );
  }

  /** Extrai um "tema" curto da pergunta apenas para dar variedade ao texto mock. */
  private tema(pergunta: string): string {
    const limpo = pergunta.replace(/[?.!]/g, '').trim();
    if (!limpo) {
      return 'o tema consultado';
    }
    return limpo.length > 60 ? `${limpo.slice(0, 60)}…` : limpo;
  }

  private embaralhar<T>(itens: T[]): T[] {
    const copia = [...itens];
    for (let i = copia.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [copia[i], copia[j]] = [copia[j], copia[i]];
    }
    return copia;
  }
}
