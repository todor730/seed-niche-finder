# Project Memory

## Project

- Name: `Ebook Niche Research Engine`
- Workspace: `D:\Ebook Niche Research\Book Funnel`
- Stack: FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, pandas, httpx, Playwright-ready
- Main goal: backend bot for ebook niche research with `research_runs` as the central orchestration entity

## Current State

- The API is bootable and tested locally.
- The app runs with a local SQLite database by default for development.
- `research_runs`, `keywords`, `opportunities`, and `exports` are persisted.
- The route layer is implemented for:
  - `health`
  - `research-runs`
  - `keywords`
  - `opportunities`
  - `exports`
- Structured logging and standard error envelopes are in place.
- OpenAPI structure has already been aligned at the FastAPI layer.

## Important Reality Check

- This is now a working local research backend, not just a stub API.
- The current research pipeline is evidence-first and uses public book-market signals.
- It is still not a true Amazon/Goodreads/KDP-grade deep research engine.
- The biggest remaining quality gap is provider depth, not API plumbing.

## Key Runtime Behavior

- App entrypoint: `app.main:app`
- App factory: `create_app()`
- On startup the app:
  - loads settings from environment
  - creates the SQLAlchemy engine/session factory
  - runs `Base.metadata.create_all(...)`
  - creates the export storage directory
  - wires real services into `app.state`

## Main Files To Know

- `app/main.py`
  - app bootstrap, CORS, logging, exception handlers, service wiring
- `app/core/config.py`
  - environment-driven settings
- `app/core/errors.py`
  - app exceptions and standard error envelope handling
- `app/core/logging.py`
  - structured JSON-friendly logging with request ID support
- `app/db/base.py`
  - SQLAlchemy declarative base and metadata
- `app/db/session.py`
  - engine/session creation and FastAPI session dependency support
- `app/db/models/*`
  - ORM models for users, runs, keywords, metrics, competitors, opportunities, exports
- `app/db/repositories/*`
  - thin persistence layer for common DB access paths
- `app/api/routes/*`
  - thin FastAPI route handlers using response models and service calls
- `app/services/research_service.py`
  - synchronous local research orchestration and persistence
- `app/services/providers.py`
  - public signal providers and query expansion logic
- `app/services/ranking.py`
  - keyword discovery and opportunity scoring logic
- `app/services/export_service.py`
  - local export generation for `json`, `csv`, `xlsx`
- `tests/test_research_api.py`
  - main integration-style tests for research and export flows

## Database Notes

- Default local DB: `sqlite:///./ebook_niche_research.db`
- Schema is designed to stay PostgreSQL-ready later.
- `research_runs` is the central table.
- Relationships:
  - `users -> research_runs`
  - `research_runs -> keyword_candidates`
  - `research_runs -> exports`
  - `keyword_candidates -> keyword_metrics`
  - `keyword_candidates -> trend_metrics`
  - `keyword_candidates -> competitors`
  - `keyword_candidates -> opportunities`

## Research Pipeline Notes

- The current research flow:
  1. create and persist a `research_run`
  2. collect public book signals through providers
  3. build keyword blueprints
  4. materialize keywords, metrics, competitors, and opportunities
  5. mark the run as completed or failed
- Public provider path currently uses:
  - Google Books
  - Open Library
- The old curated romance-only default path was removed from normal execution.
- The current ranking is no longer based on a fixed hardcoded romance shortlist as the main discovery path.

## Known Limitation

- `romance` still tends to surface familiar tropes because:
  - public book APIs expose broad consumer-book signals
  - trope clustering for romance is naturally repetitive
  - there is not yet a deep marketplace provider layer
- If the user asks for "real deep research", the next real milestone is:
  - Amazon/KDP-compatible provider integration behind credentials
  - Playwright-based marketplace adapters
  - stronger evidence clustering and deduplication
  - richer ranking based on source agreement and competition density

## API Contract Conventions

- Success envelope:
  - `data`
  - `meta`
  - `error: null`
- Error envelope:
  - `data: null`
  - `meta`
  - `error.code`
  - `error.message`
  - `error.details`
- API prefix: `/api/v1`

## Useful Local Commands

- Install:
  - `python -m pip install -e .[dev]`
- Run API:
  - `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Run tests:
  - `python -m pytest -q -p no:cacheprovider`
- Swagger:
  - `http://127.0.0.1:8000/docs`
- Health:
  - `http://127.0.0.1:8000/api/v1/health`

## What Has Been Verified

- FastAPI app boots successfully.
- Core route groups register cleanly.
- Research flow persists runs in the database.
- Export flow creates real local files.
- `pytest` passes for the current API-level regression checks.

## Recommended Next Step

- Improve research depth rather than adding more route scaffolding.
- Priority order:
  1. deeper providers
  2. stronger evidence clustering
  3. better ranking model
  4. richer research summaries for end users

## Notes For The Next Session

- Be honest with the user about the current quality level.
- Do not present the current romance output as true deep research.
- Prefer improving provider quality over adding more placeholder endpoints.
- Keep the route layer thin and push logic into services/providers/ranking.
