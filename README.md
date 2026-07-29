# RAG Evaluation Web

Front-end de um estudo de mestrado em que avaliadores humanos escolhem, **às cegas**, a
melhor resposta entre três configurações de pipeline RAG. Todo o conteúdo é
atualmente **mockado** — um protótipo navegável para iterar no fluxo e no visual antes de
conectar um backend real.

Aplicação [Angular](https://angular.dev/) (CLI v21.2.8), componentes standalone e estado
baseado em Signals. UI em **Português (BR)**.

## Fluxo

1. **Boas-vindas / instruções** — apresentação do estudo.
2. **Seleção de documento** — o avaliador escolhe o documento que conhece melhor
   (pode trocar de documento livremente).
3. **Avaliação (estilo ChatGPT)** — para cada pergunta, três respostas anônimas rotuladas
   **A / B / C**; o avaliador escolhe a melhor.

Até **10 perguntas avaliadas por documento** (`MAX_PERGUNTAS`); a conclusão é **por documento**.

### Avaliação às cegas

As respostas são embaralhadas nos rótulos A/B/C. O pipeline verdadeiro
(`pipeline-a` / `pipeline-b` / `pipeline-c`) que gerou cada resposta fica registrado
**apenas internamente** em cada rodada, nunca exibido ao avaliador.

> **Estado somente em memória:** `EvaluationStore` usa Signals sem persistência — recarregar
> a página reinicia o progresso. Trocar para `localStorage` caso um fluxo de "retomar após
> reload" seja necessário no futuro.

## Estrutura (`src/app/`)

| Caminho | Responsabilidade |
| --- | --- |
| `models/evaluation-model.ts` | Tipos de domínio (`RagDocument`, `QuestionRound`, `PipelineAnswer`, …) e `MAX_PERGUNTAS`. |
| `services/mock-rag.ts` | Lista mockada de documentos + geração e embaralhamento das 3 respostas candidatas. |
| `services/evaluation-store.ts` | Signal store (`providedIn: 'root'`): `askQuestion`, `chooseAnswer`, e derivados como `answeredCount` / `isComplete` / `totalConcluidos`. |
| `pages/` | `welcome/`, `document-selection/`, `evaluation/` — uma rota lazy por página. |
| `components/` | `progress-badge/`, `document-card/`, `chat-message/`, `answer-choice/` — reutilizáveis, `OnPush`. |

**Roteamento** (`app.routes.ts`, lazy `loadComponent`): `''` → welcome, `documentos` →
seleção de documento, `avaliacao/:docId` → avaliação, `**` → redireciona para a home. O
parâmetro `:docId` é vinculado direto ao input signal via `withComponentInputBinding()`.

## Sistema visual

Segue `DESIGN.md` (estilo Claude/Anthropic: canvas creme + coral + navy, serifa editorial).
Tokens espelhados como CSS custom properties em `src/styles.css` (nunca hex inline). Fontes:
Cormorant Garamond / Inter / JetBrains Mono, carregadas do Google Fonts em `src/index.html`.
Estilização com Tailwind CSS v4 via `@tailwindcss/postcss`.

## Comandos

```bash
npm start        # ou `ng serve` — dev server em http://localhost:4200/ (auto-reload)
ng build         # build de produção em dist/
npm run watch    # build de desenvolvimento com --watch
ng test          # testes unitários (Vitest via @angular/build:unit-test)
```

Rodar um único arquivo de teste:

```bash
ng test -- src/app/app.spec.ts
```

Não há framework de e2e configurado.

## Tooling

- **TypeScript** em `strict` + flags extras; compilador Angular com `strictTemplates`.
- **Componentes** standalone (sem `NgModule`s), `input()` / `output()`, `inject()`.
- **Testes** com Vitest (`describe` / `it` / `expect` + `TestBed`), não Karma/Jasmine.
- **Formatação** via Prettier (aspas simples, largura 100).
