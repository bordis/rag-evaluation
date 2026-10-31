import { MarkdownPipe } from './markdown-pipe';

describe('MarkdownPipe', () => {
  const pipe = new MarkdownPipe();

  it('converts lists and emphasis to HTML', () => {
    const html = pipe.transform('**Prazo**\n\n- um\n- dois');

    expect(html).toContain('<strong>Prazo</strong>');
    expect(html).toContain('<li>um</li>');
  });

  it('keeps a single line break', () => {
    expect(pipe.transform('linha 1\nlinha 2')).toContain('<br>');
  });
});
