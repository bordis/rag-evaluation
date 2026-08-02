# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

`rag-evaluation-api` is the backend counterpart to the sibling `rag-evaluation-web` Angular app (a Master's-thesis
study where human evaluators blindly pick the best answer among three RAG-pipeline configurations). Right now this
repo is an empty FastAPI scaffold: `hello.py` defines a single `FastAPI()` app with one `GET /` route. There is no
router structure, data layer, config, or tests yet — treat any architectural description beyond that as something
to build, not something already in place.

## Environment

- Python virtual environment lives in `.venv/` (Windows `Scripts/` layout). Installed: FastAPI 0.141.1,
  Uvicorn 0.52.0, Pydantic 2.13.4. No `requirements.txt` or `pyproject.toml` exists yet to pin these — add one
  before installing further dependencies.

## Commands

- Activate the venv (PowerShell): `.venv\Scripts\Activate.ps1`
- Run the dev server: `uvicorn hello:app --reload` (serves at `http://127.0.0.1:8000`, interactive docs at `/docs`).
