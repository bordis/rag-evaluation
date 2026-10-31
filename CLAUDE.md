# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

Angular CLI (v21.2.8) application named `rag-evaluation-web`. It is the front-end for a study that
has human evaluators **blindly** pick the best answer among **four** RAG-pipeline configurations. It is **wired to
the real backend** in `rag-evaluation-api/` — the old `MockRag` is gone. Setup and document-upload instructions
live in the repo-root `README.md`.

**Flow:** welcome + consent (creates the session, only while a study is open) → pick one document (the one the
evaluator knows best) → ChatGPT-style Q&A → for each question, four anonymous answers (A/B/C/D) → choose the best or
"none is correct". Up to **10 answered questions per document, per study**; evaluators can switch documents freely.
Researcher screens live under `/admin` (studies, documents, pipelines CRUD, round browser, results).

**Key design decisions (not obvious from code):**
- **The blind is enforced server-side:** the API's evaluation schemas have no `pipeline` field, so the identity
  never reaches the browser. There is deliberately **no `PipelineId` type here** — don't reintroduce one.
- **Only the `sessionId` is persisted** (`sessionStorage`). Round history always comes from
  `GET /sessions/{id}/documents/{slug}/rounds`, so a reload resumes instead of orphaning answers in the database.
- **`docId` in the route is the document's `slug`**, not its UUID. Admin routes use the UUID.
- **The server owns the rules** (question limit, pending round, document readiness). The store's checks only
  avoid a pointless round trip; a 409 from the API is the real answer.
- **Only study-open sessions work.** A closed study freezes its data; `sessaoValida()` discards a stored session
  from a closed study, and a route guard sends the evaluator back to consent.
- **Round timing is measured in the browser** (`services/cronometro-rodada.ts`) and survives F5. Generation wait and
  hidden-tab time are separate fields, not subtracted.
- **Each question is a step, one per screen, with no way back** (`components/progresso-etapas/` only shows progress).
  This was the researcher's decision after trying read-only review; the server doesn't allow a second choice either.
- **Answers are Markdown** (`pipes/markdown-pipe.ts`, always through `[innerHTML]`, whose sanitizer is the XSS filter).
- No authentication in this phase, including `/admin`, which reveals pipelines. The top menu links to it on every
  screen on purpose for now; hide those links from evaluators before collection. TODO: login. UI copy is **Portuguese (BR)**.

**Architecture (`src/app/`):**
- `models/evaluation-model.ts` — domain types (`RagDocument`, `QuestionRound`, `PipelineAnswer`, `PerfilAvaliador`,
  …), `RotuloCego = 'A'|'B'|'C'|'D'` and `MAX_PERGUNTAS = 10` (fallback; the real limit comes from `/progress`).
- `services/api-rag.ts` — the only place that talks HTTP. Converts snake_case → domain and `HttpErrorResponse` →
  a Portuguese message (`ApiError`).
- `services/evaluation-store.ts` — `providedIn: 'root'` signal store: cache + orchestration (`iniciarSessao`,
  `sessaoValida`, `carregarCatalogo`, `abrirDocumento`, `askQuestion`, `chooseAnswer`) plus `carregando`/`gerando`/`erro`.
  It never generates content and never throws: failures land in `erro()`.
- `services/api-admin.ts` — researcher API. Its types reveal the pipeline: never use them in the evaluator flow.
- `models/termo.ts` — consent text (draft) and its version, stored with each acceptance.
- `pages/` — `welcome/`, `document-selection/`, `evaluation/`, and `admin/` (shared `.adm-*` styles in `styles.css`).
- `components/` — `progress-badge/`, `progresso-etapas/`, `document-card/`, `chat-message/`, `answer-choice/` (reusable, `OnPush`).
- `testing/api-rag-fake.ts` — stateful `ApiRag` double shared by the specs (the app is **zoneless**, so specs
  must yield the event loop once before asserting — see `estabilizar()` in `evaluation.spec.ts`).
- `src/environments/environment.ts` — `apiBaseUrl` (must include `/api`).

**Visual system:** follows `DESIGN.md` (editorial serif layout, with the Procempa palette: white
canvas, blue primary `#4264cd` — not the `#557cf2` of Procempa's buttons, which fails AA with white text). Tokens
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
  `documentos` → document selection, `avaliacao/:docId` → evaluation, `admin/**` → researcher area, `**` → redirect home). Wired up in
  `app.config.ts` via `provideRouter(routes, withComponentInputBinding())` — the `:docId` route param is bound
  straight into the `Evaluation` component's `docId = input.required<string>()` signal.
- **Build budgets**: `anyComponentStyle` budget in `angular.json` was raised to 8kB warning / 16kB error.
