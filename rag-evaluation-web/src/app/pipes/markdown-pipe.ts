import { Pipe, type PipeTransform } from '@angular/core';
import { Marked } from 'marked';

// `breaks`: o modelo separa itens com uma quebra simples, que o Markdown puro juntaria num parágrafo.
const marked = new Marked({ gfm: true, breaks: true });

/**
 * Converte Markdown em HTML. O `marked` não sanitiza: use sempre com `[innerHTML]`, que passa o
 * resultado pelo sanitizador do Angular e remove scripts e atributos perigosos.
 */
@Pipe({ name: 'markdown' })
export class MarkdownPipe implements PipeTransform {
  transform(texto: string): string {
    return marked.parse(texto, { async: false });
  }
}
