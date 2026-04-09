# Project Memory

## Project

- Name: `Ebook Niche Research Engine`
- Workspace: `D:\Ebook Niche Research\Book Funnel`
- Stack: FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, pandas, httpx, Playwright-ready
- Main goal: backend bot for ebook niche research with `research_runs` as the central orchestration entity

## Current State

- The API is bootable and tested locally.
- The app runs with a local SQLite database by default for development.
- The project has a full evidence-first deep-research backbone:
  - `source_items`
  - `extracted_signals`
  - `signal_clusters`
  - `niche_hypotheses`
  - `niche_scores`
  - `provider_failures`
  - `source_queries`
  - `source_item_query_links`
- `research_runs`, `keywords`, `opportunities`, and `exports` are persisted.
- `research_runs` now expose a runtime-computed `depth_score` snapshot derived from persisted evidence counts and failure context.
- Structured logging and standard error envelopes are in place.
- OpenAPI structure is aligned at the FastAPI layer.
- Hardening steps 1-10 were completed and locked by a dedicated release-gate test suite.

## Important Reality Check

- This is a working local research backend, not a stub API.
- The current research pipeline is evidence-first and uses public book-market signals.
- It is still not a true Amazon/Goodreads/KDP-grade deep research engine.
- The biggest remaining quality gap is provider depth and source breadth, not route/API plumbing.
- The system must stay honest:
  - no fabricated output on zero evidence
  - `completed_no_evidence` is the correct outcome when providers do not yield persisted evidence

## Key Runtime Behavior

- App entrypoint: `app.main:app`
- App factory: `create_app()`
- On startup the app:
  - loads settings from environment
  - creates the SQLAlchemy engine/session factory
  - auto-creates schema only in local dev SQLite mode
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
  - ORM models for users, runs, evidence, keywords, metrics, competitors, opportunities, exports
- `app/db/repositories/*`
  - thin persistence layer for common DB access paths
- `app/api/routes/*`
  - thin FastAPI route handlers using response models and service calls
- `app/services/research_service.py`
  - evidence-first orchestration and persistence
- `app/services/providers.py`
  - unified public providers, query expansion, and provider registry
- `app/services/extraction/*`
  - rule-based extraction and semantic normalization
- `app/services/clustering/*`
  - explainable signal clustering
- `app/services/hypotheses/*`
  - niche hypothesis generation
- `app/services/scoring/*`
  - explainable ranking and competition density scoring
- `app/services/summary_service.py`
  - decision-grade niche summaries and report output
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
  - `research_runs -> source_queries`
  - `research_runs -> source_items`
  - `research_runs -> extracted_signals`
  - `research_runs -> signal_clusters`
  - `research_runs -> niche_hypotheses`
  - `research_runs -> niche_scores`
  - `research_runs -> provider_failures`
  - `research_runs -> keyword_candidates`
  - `research_runs -> exports`
  - `keyword_candidates -> keyword_metrics`
  - `keyword_candidates -> trend_metrics`
  - `keyword_candidates -> competitors`
  - `keyword_candidates -> opportunities`

## Research Pipeline Notes

- The current research flow:
  1. create and persist a `research_run`
  2. expand queries and fan out to public providers
  3. persist raw `source_items` and provider/query traceability
  4. extract rule-based signals from persisted evidence
  5. normalize and cluster signals
  6. generate ranked `niche_hypotheses`
  7. materialize final `keywords` and `opportunities` from ranked hypotheses
  8. generate summaries and exports
  9. mark the run as completed, failed, or `completed_no_evidence`
- Public provider path currently uses:
  - Google Books
  - Open Library
- The old curated romance-only default path was removed from normal execution.
- Final output now comes from deep-path ranked `niche_hypotheses`, not the old legacy title/category blueprint path.
- Query-level traceability and partial provider failures are persisted.
- Fiction hypothesis generation no longer collapses to one assembly per subgenre anchor:
  - `NicheHypothesisService` now ranks top-N secondary candidates per type
  - branches multiple explainable fiction hypotheses per anchor
  - logs explicit reject reason codes for rejected branches
  - includes `assembly_version = "hypothesis_v2"` and `component_signature` in rationale payloads

## Known Limitation

- Public provider depth is still limited.
- `romance` can still have overlap between adjacent trope/subgenre opportunities.
- Rich `romance` evidence no longer collapses mechanically to only 2 hypotheses in the service layer; the current branching path can materialize broader fiction outputs such as:
  - `friends to lovers small town romance`
  - `humorous small town romance`
  - `opposites attract contemporary romance`
  - `steamy contemporary romance`
  - `sweet paranormal romance`
  - `young adults paranormal romance`
- Provider access on this exact machine has been inconsistent; when live HTTPS is blocked, honest runs end as `completed_no_evidence`.
- If the user asks for "real deep research", the next real milestone is:
  - Amazon/KDP-compatible provider integration behind credentials
  - Playwright-based marketplace adapters
  - stronger marketplace-backed competition evidence
  - broader provider coverage for self-help/nonfiction

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
- Windows launcher:
  - `start_api.bat`
- One-shot local launcher:
  - `launch_research.bat`
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
- Export flow creates real local files and repeated exports do not overwrite prior artifacts.
- `pytest` passes for the current regression suite, including the hardening release gate.
- Current full suite status after the latest hypothesis breadth patch:
  - `70 passed, 1 warning`
- A successful self-help run on this machine was validated from persisted live output:
  - `anxiety journal for young adults`
  - `codependency workbook`
- A successful romance run on this machine was validated from persisted live output:
  - `friends to lovers small town romance`
  - `friends to lovers contemporary romance`
- Rich romance regression coverage now proves:
  - at least 4 materially distinct fiction hypotheses survive when supported
  - near-duplicate spam is capped
  - breadth propagates through `ResearchService` into persisted keywords/opportunities
- Bad phrases that previously failed quality checks are now suppressed in validated runs:
  - `god help the child`
  - `self help`
  - `self help books`
  - `greatest self help book`
  - `the self help book`
  - `the self help compulsion`

## Recommended Next Step

- Run a fresh live `romance` validation on the current code and inspect whether the broader branch-based hypothesis generation now survives on real provider evidence, not only on regression fixtures.
- If live romance still compresses too hard after this patch, the next likely step is diversity-aware reranking, not more route/API work.
- Keep improving provider depth and discovery breadth rather than adding more route scaffolding.
- Priority order:
  1. live validation of branch-based romance breadth
  2. deeper providers / marketplace adapters
  3. stronger nonfiction breadth
  4. better competition realism from marketplace evidence
  5. richer report/export UX only after evidence quality improves

## Notes For The Next Session

- Be honest with the user about the current quality level.
- Do not present public-provider output as Amazon/KDP-grade deep research.
- Preserve all hardening guarantees.
- Prefer improving provider quality and evidence breadth over adding placeholder endpoints.
- Keep the route layer thin and push logic into services/providers/evidence/extraction/hypotheses/scoring.
- When debugging romance breadth, inspect `app/services/hypotheses/service.py` first:
  - reject reason logs
  - component candidate rankings
  - per-anchor branch caps
  - `component_signature` in persisted rationale JSON
