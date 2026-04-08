# Ebook Niche Research Engine Backend

This repository contains the initial FastAPI backend skeleton for the Ebook Niche Research Engine. The backend is designed around `research_runs` as the central entity and is structured to support local synchronous development first, with room for asynchronous production execution later.

## Stack

- Python 3.12
- FastAPI
- Pydantic v2
- SQLAlchemy 2.0
- Alembic
- PostgreSQL via `psycopg`
- Redis
- HTTP clients via `httpx`
- Browser automation via Playwright
- Data processing via pandas
- Testing via pytest

## Project Layout

```text
app/
  __init__.py
  main.py
  core/
    __init__.py
tests/
  __init__.py
pyproject.toml
.env.example
README.md
```

## Local Startup

1. Create and activate a Python 3.12 virtual environment.

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install the project in editable mode with development dependencies:

   ```powershell
   .\.venv\Scripts\python -m pip install -e .[dev]
   ```

3. Copy `.env.example` to `.env` and fill in the required values for your local environment.
4. Start the API server:

   ```powershell
   .\.venv\Scripts\python -m uvicorn app.main:app --reload
   ```

5. Open `http://127.0.0.1:8000/docs` for the Swagger UI or `http://127.0.0.1:8000/health` for a simple health check.

## Notes

- No business logic is included yet.
- No database models or migrations are defined yet.
- No async worker implementation is included yet.
- Playwright browser binaries must be installed separately when browser automation is introduced:

  ```powershell
  .\.venv\Scripts\python -m playwright install
  ```
