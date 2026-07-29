# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

Angular CLI (v21.2.8) application named `rag-evaluation-web`. It is the front-end for a Master's-thesis study that
has human evaluators **blindly** pick the best answer among three RAG-pipeline configurations. All content is
currently **mocked** — a navigable prototype to iterate on the flow and visuals before wiring a real backend.

**Flow:** welcome/instructions → pick one document (the one the evaluator knows best) → ChatGPT-style Q&A →
for each question, three anonymous answers (A/B/C) → choose the best. Up to **10 answered questions per
document**; completion is **per document**; evaluators can switch documents freely.

**Key design decisions (not obvious from code):**
- **Blind evaluation:** answers are shuffled into labels A/B/C; the true pipeline (`pipeline-a/b/c`) is stored
  only internally on each round (never shown to the evaluator).
- **In-memory state only** (by request): `EvaluationStore` uses signals with no persistence, so a page reload
  resets progress. Switch to `localStorage` if a "resume after reload" flow is ever needed.
- No authentication in this phase. UI copy is **Portuguese (BR)**.

**Architecture (`src/app/`):**
- `models/evaluation-model.ts` — domain types (`RagDocument`, `QuestionRound`, `PipelineAnswer`, …) and
  `MAX_PERGUNTAS = 10`.
- `services/mock-rag.ts` — mock document list + generates and shuffles the 3 candidate answers per question.
- `services/evaluation-store.ts` — `providedIn: 'root'` signal store (immutable updates, no RxJS): `askQuestion`,
  `chooseAnswer`, plus `answeredCount`/`isComplete`/`hasPendingRound`/`totalConcluidos`.
- `pages/` — `welcome/`, `document-selection/`, `evaluation/` (lazy-loaded, one route each).
- `components/` — `progress-badge/`, `document-card/`, `chat-message/`, `answer-choice/` (reusable, `OnPush`).

**Visual system:** follows `DESIGN.md` (Claude/Anthropic: cream canvas + coral + navy, editorial serif). Tokens
are mirrored as CSS custom properties in `src/styles.css` (never inline hex); fonts are the open substitutes
Cormorant Garamond / Inter / JetBrains Mono, loaded from Google Fonts in `src/index.html`.

As the codebase grows, prefer updating this file with real architectural notes over letting it go stale.

## Commands

- `npm start` / `ng serve` — run the dev server at `http://localhost:4200/` (auto-reloads on change).
- `ng build` — production build, output to `dist/`.
- `ng build --configuration development` (or `npm run watch`) — unoptimized build with source maps, `--watch` rebuilds on change.
- `ng test` — run unit tests via the Vitest-based Angular unit-test builder (`@angular/build:unit-test`).
  - To run a single spec file, pass it through to Vitest: `ng test -- src/app/app.spec.ts` (or use Vitest's `-t` filter for a single test name).
- `ng generate component <name>` — scaffold a new component (also `directive`, `pipe`, etc. via `ng generate --help`).
- There is no e2e framework configured.

## Tooling / conventions

- **TypeScript**: `strict` mode plus extra strictness flags (`noImplicitOverride`, `noImplicitReturns`,
  `noFallthroughCasesInSwitch`, `noPropertyAccessFromIndexSignature`). Angular compiler runs with
  `strictTemplates`, `strictInjectionParameters`, and `strictInputAccessModifiers` — template and DI type errors
  are treated strictly, not loosely.
- **Components**: Angular standalone components (no `NgModule`s) — see `src/app/app.ts` for the pattern
  (`imports: [...]` directly on the `@Component` decorator, `templateUrl`/`styleUrl` singular, not plural).
- **Styling**: Tailwind CSS v4 via `@tailwindcss/postcss`, imported globally in `src/styles.css` with
  `@import 'tailwindcss';`. No separate Tailwind config file exists (v4 defaults).
- **Formatting**: Prettier — single quotes, 100-char print width, Angular parser for `.html` files
  (see `.prettierrc`). `.editorconfig` enforces 2-space indent and single quotes in `.ts` files.
- **Testing**: Vitest (via `@angular/build:unit-test` and `jsdom`), not Karma/Jasmine. Specs use
  `describe`/`it`/`expect` globals (see `tsconfig.spec.json` → `types: ["vitest/globals"]`) with Angular's
  `TestBed` for component tests, following the pattern in `src/app/app.spec.ts`.
- **Routing**: `src/app/app.routes.ts` holds the `Routes` array (lazy `loadComponent` per page: `''` → welcome,
  `documentos` → document selection, `avaliacao/:docId` → evaluation, `**` → redirect home). Wired up in
  `app.config.ts` via `provideRouter(routes, withComponentInputBinding())` — the `:docId` route param is bound
  straight into the `Evaluation` component's `docId = input.required<string>()` signal.
- **Build budgets**: `anyComponentStyle` budget in `angular.json` was raised to 8kB warning / 16kB error.
