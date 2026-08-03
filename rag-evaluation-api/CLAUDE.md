# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

`rag-evaluation-api` is the backend for the sibling `rag-evaluation-web` Angular app — a Master's-thesis study
where human evaluators **blindly** pick the best answer among four RAG-pipeline configurations.

**Slices 1 (foundation) and 2 (ingestion) are done.** Config, infrastructure, database schema, pipeline seeding,
Milvus collections, `GET /api/health` and the full ingestion path (`POST /api/documents` → parsing → chunking →
embedding → indexing, per pipeline, in the background) all work. **No retrieval or evaluation endpoints exist
yet** — see `docs/superpowers/plans/` at the repo root for the remaining slices (3: query, 4: evaluation,
5: frontend). Design rationale lives in `docs/superpowers/specs/2026-08-02-rag-evaluation-api-design.md`.

**The four pipelines are a 2×2 factorial design** — this is the point of the whole study, so don't collapse it:

| Code | Parser | Retrieval |
|---|---|---|
| `pipeline-1` | raw | fixed (dense, top-k) |
| `pipeline-2` | Docling | fixed (dense, top-k) |
| `pipeline-3` | raw | configurable (rewriting, re-rank, hybrid, window) |
| `pipeline-4` | Docling | configurable |

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
  tokens, which would contaminate the per-pipeline token telemetry the thesis measures.
- **The uploaded file is never persisted** — no disk, no column. Only `sha256` is kept, to detect duplicates.
- **Enum columns store the enum *value*, not the member name** (`app/models/_types.py`). SQLAlchemy defaults to
  the name, which would put `ATE_2_ANOS` in the database while the API serializes `ate-2-anos`.
- **Alembic's `script.py.mako` adds `import sqlmodel`** — autogenerate emits `sqlmodel.sql.sqltypes.AutoString()`
  without importing it, so generated migrations fail with `NameError` otherwise.
- **Every pipeline re-does all the work.** Pipelines 1 and 3 produce identical chunks, and reusing them would
  halve the embedding cost — but it would record zero parsing time for pipeline 3 and corrupt the comparative
  telemetry the thesis measures. The ingestion orchestrator runs all four arms from scratch, deliberately.
- **`sparse_vector` is never sent on insert.** The collection's BM25 `Function` derives it from `text`; supplying
  it makes Milvus reject the row.
- **Raw `.docx` parsing reads `word/document.xml` directly** (zip + `defusedxml`) instead of using `python-docx`.
  A library would recover structure, which is exactly what the raw arm must *not* have. `defusedxml` because
  `xml.etree` is vulnerable to billion-laughs on uploaded XML.
- **Docling runs with OCR off** (`DOCLING_DO_OCR=false`). The study's documents are digital PDFs; OCR would load
  vision models and make ingestion time incomparable to the raw parser's.
- **The blind rule is scoped to evaluation schemas.** `GET /api/documents/{id}/ingestions` exposes
  `pipeline_codigo` on purpose — it's the researcher's telemetry, and the frontend never calls it. Do not write
  a global "no schema has a pipeline field" test.
- **Chunk metadata carries no page or section.** Chunking is character-based over the whole text and identical
  across all four pipelines; making it page-aware would break that parity. Known, accepted limitation.

## Architecture (`app/`)

- `core/config.py` — `Settings` via pydantic-settings; composes the SQLAlchemy URL from the four `DB_*` vars
  (stripping the `jdbc:` prefix inherited from the requirements) and the Milvus URI.
- `core/db.py` — engine, `get_session`, `SessionDep`, and `rodar_migracoes()` (called from the lifespan).
- `core/milvus.py` — client, collection schema, idempotent `criar_collections`.
- `models/` — eight SQLModel tables: `pipeline`, `document` (documents + ingestions), `evaluation` (sessions,
  rounds, answers), `telemetry` (per-stage metrics, retrieved chunks).
- `schemas/` — Pydantic request/response models, kept **separate** from table models; that separation is what
  guarantees the blind.
- `api/routers/` — one router per domain. `health.py` and `documents.py` exist; the rest come with later slices.
- `rag/` — one file per ingestion stage: `chunking.py`, `parsing/` (`base.py`, `raw.py`, `docling.py`),
  `embedding.py`, `indexing.py`. Each is testable on its own with no infrastructure running.
- `services/ingestion.py` — the orchestrator. It reads `parser` and `collection_name` from the database and never
  names a pipeline; a fifth pipeline would be a table row, not new code. `DependenciasDeIngestao` is the
  injection point that lets the whole flow be tested with fakes.
- `telemetry/recorder.py` — `Cronometro`, the per-stage stopwatch.
- `seed.py` — idempotent seeding of the four pipelines; never overwrites an edited config.

## Commands

- `uv sync` — install/refresh dependencies (uses `.venv/`).
- `docker compose up -d` — etcd, MinIO, Milvus Standalone, docling-serve. **PostgreSQL is not in the compose** —
  it runs natively on 5432 (service `postgresql-x64-17`). Milvus takes ~90s to report healthy.
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
- `.env` is gitignored; `.env.example` is versioned with an empty `CHAT_API_KEY`.
