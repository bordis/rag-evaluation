# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

`rag-evaluation-api` is the backend for the sibling `rag-evaluation-web` Angular app — a study
where human evaluators **blindly** pick the best answer among four RAG-pipeline configurations.

The API covers ingestion, the four pipelines, studies, blind rounds, the researcher views (`/api/admin`), the
`/api/pipelines` CRUD, RAGAS on demand and the analysis. Setup and document-upload instructions live in the
repo-root `README.md`.

**The four pipelines are a 2×2 factorial design** — this is the point of the whole study, so don't collapse it:

| Code | Parser | Retrieval |
|---|---|---|
| `pipeline-1` | raw | fixed (dense, top-k) |
| `pipeline-2` | Docling | fixed (dense, top-k) |
| `pipeline-3` | raw | advanced (HyDE, hybrid RRF, cross-encoder re-rank, neighbours) |
| `pipeline-4` | Docling | advanced |

Comparing 1↔2 and 3↔4 isolates the parser; comparing 1↔3 and 2↔4 isolates advanced retrieval. **Pipelines 1 and
2 are the control arm** — the API must reject changes to their four retrieval flags. Chunking and generation are
identical across all four on purpose; varying them would confound the variables.

**Non-obvious decisions:**
- **Blind evaluation is enforced server-side:** no output schema may contain a `pipeline` field. Not "hidden in
  the UI" — absent from the JSON.
- **One Milvus collection per pipeline**, not one collection filtered by `pipeline_id`. BM25 computes IDF and
  average document length over the *collection*; a shared collection would index each source document four times
  and let one experimental arm's statistics contaminate another's.
- **The BM25 `Function` is declared at collection creation** because Milvus has no API to add it later. All four
  collections carry the sparse field even where hybrid search is off.
- **Analyzer is Portuguese-specific** (`asciifolding` + stemmer + stopwords). There is no `{"type": "portuguese"}`
  shortcut; without the explicit form, "proteção" and "protecao" would be distinct terms.
- **`gpt-4.1-mini`, not a reasoning model.** Reasoning models reject custom `temperature` and spend reasoning
  tokens, which would contaminate the per-pipeline token telemetry the study measures.
- **The uploaded file is never persisted** — no disk, no column. Only `sha256` is kept, to detect duplicates.
- **Enum columns store the enum *value*, not the member name** (`app/models/_types.py`). SQLAlchemy defaults to
  the name, which would put `ATE_2_ANOS` in the database while the API serializes `ate-2-anos`.
- **Alembic's `script.py.mako` adds `import sqlmodel`** — autogenerate emits `sqlmodel.sql.sqltypes.AutoString()`
  without importing it, so generated migrations fail with `NameError` otherwise.
- **Every pipeline re-does all the work.** Pipelines 1 and 3 produce identical chunks, and reusing them would
  halve the embedding cost — but it would record zero parsing time for pipeline 3 and corrupt the comparative
  telemetry the study measures. The ingestion orchestrator runs all four arms from scratch, deliberately.
- **`sparse_vector` is never sent on insert.** The collection's BM25 `Function` derives it from `text`; supplying
  it makes Milvus reject the row.
- **Raw `.docx` parsing reads `word/document.xml` directly** (zip + `defusedxml`) instead of using `python-docx`.
  A library would recover structure, which is exactly what the raw arm must *not* have. `defusedxml` because
  `xml.etree` is vulnerable to billion-laughs on uploaded XML.
- **Docling runs with OCR off** (`DOCLING_DO_OCR=false`). The study's documents are digital PDFs; OCR would load
  vision models and make ingestion time incomparable to the raw parser's.
- **`app/__init__.py` injects `truststore`:** the antivirus intercepts HTTPS intermittently, and with `certifi` OpenAI
  calls fail at random (`APIConnectionError`), which invalidates rounds. The Windows store already trusts its root.
- **Docling reports `success` when the VLM fails.** `_imagens_sem_descricao` turns a large picture with no description
  into an ingestion error; otherwise factor A would silently change. The compose needs
  `DOCLING_SERVE_ENABLE_REMOTE_SERVICES` and, behind an HTTPS-inspecting antivirus, `DOCLING_CA_BUNDLE`.
- **Every pipeline delivers the same 15 chunks.** Advanced arms: 20 candidates → re-rank → 5 anchors + neighbours, then
  `_completar_contexto` fills up with the next ranked candidates. Documents with fewer chunks deliver what exists.
- **HyDE only touches the dense leg.** The vector is the mean of hypothetical + question; BM25 and the re-ranker see the question.
- **The re-ranker has no fallback.** `BAAI/bge-reranker-v2-m3` runs locally in the `rag-reranker` TEI container, called
  over HTTP so the API stays free of torch. Falling back to search order would mix two treatments under one pipeline,
  so its failure fails the round, and a study won't open while it is down.
- **Re-rank latency is contention-sensitive on CPU** (~1 s per 256-token candidate, queued). `duracao_ms`
  includes queue time and TEI's `inferencia_ms`/`fila_ms` headers don't add up to it, so measure the re-rank cost
  in isolation. TEI's default batch size exhausted Docker's
  memory during warm-up and took Milvus down: keep `--max-batch-tokens` low and `mem_limit` set.
- **`buscar_parcelas` repeats the dense and sparse searches** outside the retrieval stopwatch, only to record each
  stage: `hybrid_search` doesn't return the RRF parts.
- **`FLAT` index:** the per-document filter discards over 90% of vectors. `criar_collections` never alters an existing
  collection, so changing the index or chunking means dropping collections and re-ingesting.
- **`milvus_id` is `BigInteger`:** Milvus auto IDs use all 64 bits. Doubles must use real-sized IDs.
- **A round is decided when `escolhido_em` is set**, not when `escolha_answer_id` is: "none is correct" has no answer.
- **Effects are binary tests on the winning answer** (`services/analise.py`), which avoids the dependence between the
  four answers of a round.
- **The study RAGAS batch commits per answer** and `reservar_calculo` blocks a second batch while one runs (in-memory:
  the API is a single process). That is what lets `GET /api/admin/studies/{id}/ragas` report progress.
- **The blind rule is scoped to evaluation schemas.** `GET /api/documents/{id}/ingestions` exposes
  `pipeline_codigo` on purpose — it's the researcher's telemetry, and the frontend never calls it. Do not write
  a global "no schema has a pipeline field" test.
- **Chunk metadata carries no page or section.** Chunking is token-based, by whole sentences, over the whole text and
  identical across all four pipelines; making it page-aware would break that parity. Known, accepted limitation.
- **One failing pipeline invalidates the whole round (502).** Offering a choice among three answers would
  produce a data point that doesn't aggregate with the others. Nothing is persisted in that case.
- **Only a *decided* round counts toward `MAX_PERGUNTAS`** — asking and walking away doesn't burn the quota.
- **`services/evaluation.py` flushes between levels.** No table declares a `Relationship`, so the unit of work
  doesn't know `question_rounds` must precede `pipeline_answers`; without the explicit `flush()` the insert
  order is undefined and the foreign key blows up.
- **Threads get a transient copy of the `Pipeline` row** (`_copia_transiente`): `asyncio.to_thread` runs the
  four pipelines in parallel and the SQLAlchemy `Session` is not thread-safe.

## Architecture (`app/`)

- `core/config.py` — `Settings` via pydantic-settings; composes the SQLAlchemy URL from the four `DB_*` vars
  (stripping the `jdbc:` prefix inherited from the requirements) and the Milvus URI.
- `core/db.py` — engine, `get_session`, `SessionDep`, and `rodar_migracoes()` (called from the lifespan).
- `core/milvus.py` — client, collection schema, idempotent `criar_collections`.
- `models/` — ten SQLModel tables: `pipeline`, `study`, `document` (documents + ingestions), `evaluation` (sessions,
  rounds, answers), `telemetry` (per-stage metrics, retrieved chunks per stage, RAGAS scores).
- `schemas/` — Pydantic request/response models, kept **separate** from table models; that separation is what
  guarantees the blind.
- `api/routers/` — one router per domain: `health.py`, `documents.py`, `sessions.py` (anonymous session +
  progress), `evaluation.py` (question, history, choice), `studies.py`, `pipelines.py` and `admin.py` (researcher views).
- `rag/` — one file per ingestion stage: `chunking.py`, `parsing/` (`base.py`, `raw.py`, `docling.py`),
  `embedding.py`, `indexing.py`. Each is testable on its own with no infrastructure running.
- `services/ingestion.py` — the orchestrator. It reads `parser` and `collection_name` from the database and never
  names a pipeline; a fifth pipeline would be a table row, not new code. `DependenciasDeIngestao` is the
  injection point that lets the whole flow be tested with fakes.
- `services/evaluation.py` — the round orchestrator: runs the active pipelines in parallel
  (`asyncio.gather` over `asyncio.to_thread`, one `wait_for` each), draws the A–D labels, and persists round,
  answers, per-stage metrics and retrieved chunks. `DependenciasDeAvaliacao` mirrors the ingestion pattern;
  `tests/fakes.py` holds the shared doubles.
- `telemetry/recorder.py` — `Cronometro`, the per-stage stopwatch.
- `services/analise.py` — pure analysis functions plus the study queries. `analise/modelo_misto.R` fits the mixed model.
- `seed.py` — idempotent seeding of the four pipelines; never overwrites an edited config.

## Commands

- `uv` may not be on PATH here; `.venv/Scripts/python.exe -m pytest` works too.
- `uv sync` — install/refresh dependencies (uses `.venv/`).
- `docker compose up -d` — PostgreSQL 17 (port 5432, named volume `postgres-data`), etcd, MinIO, Milvus Standalone,
  docling-serve. Milvus takes ~90s to report healthy. RAGAS is a library, not a service: `services/ragas_rodadas.py`
  scores stored rounds on the researcher's request and costs real money; the round flow never calls it.
- Python is pinned to 3.12 (`.python-version`) and capped below 3.14: `scikit-network`, required by `ragas`, has no
  3.14 wheel. `langchain-community<0.4` is required too, because `ragas` 0.4.3 imports a module removed in later versions.
- `uv run fastapi dev` — dev server at `http://127.0.0.1:8000`, Swagger at `/docs`.
  On Windows, prefix with `PYTHONIOENCODING=utf-8`: the CLI's `rich` banner crashes on the cp1252 console.
- `uv run pytest` — unit suite. Integration tests are **excluded by default** via `addopts = "-m 'not integration'"`.
- `uv run pytest -m integration` — requires the compose stack up and the `rag-evaluation-test` database to exist
  (`CREATE DATABASE "rag-evaluation-test"`). The fixture drops and recreates all tables.
- `uv run alembic revision --autogenerate -m "..."` then `uv run alembic upgrade head`. Migrations also run
  automatically in the app lifespan.
- `uv run ruff check . --fix` and `uv run ruff format .`. `alembic/versions/` is excluded — it's generated code.
- Integration tests that hit OpenAI cost real money (a few cents per run of
  `tests/api/test_ingestao_ponta_a_ponta.py`). They are excluded from the default suite.

## Conventions

- **Domain language is Portuguese (BR)**: table names, columns, function names, docstrings and error messages.
  Library and framework identifiers stay in English.
- **FastAPI**: follow `.claude/skills/fastapi/SKILL.md` — `Annotated` for dependencies, return-type annotations
  over `response_model`, no `...` defaults, one HTTP operation per function, router-level `prefix`/`tags`.
- **SQLModel over plain SQLAlchemy** (same skill). It sits on SQLAlchemy, so Alembic behaves identically.
- `.env` is gitignored and is the only env file; there is no versioned template.
- **`tests/conftest.py` injects a fake `CHAT_API_KEY` only when `.env` has no real one.** Environment variables
  outrank `.env` in pydantic-settings, so an unconditional `setdefault` would mask the real key and every
  integration test that calls OpenAI would fail with `AuthenticationError`.
