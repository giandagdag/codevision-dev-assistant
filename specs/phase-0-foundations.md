# Phase 0: Foundations

Status: APPROVED v1.0 (25 Oct 2026)
Depends on: nothing
Next phase: Phase 1, Rulebook core

## In plain words

Build the empty "engine room" of the Developer Assistant. No screens and no real AI features yet.
After this phase we can: read settings, switch between AI providers, save a request,
record what happened to it, and prove it all works with automated tests.

## 1. Goal

A runnable foundation for the Developer Assistant that:
- follows CodeVision's existing folder layout, so moving it to work is copy-and-paste
- has one switch to pick the AI provider (fake, Claude, or on-prem Qwen/Llama)
- stores requests and an append-only audit trail
- is fully covered by automated tests

## 2. In scope

### 2.1 Project setup
- Python 3.14, in a project-only virtual environment `.venv` (created with `py -V:3.14 -m venv .venv`)
- `requirements.txt` with pinned versions
- Dev tools: `pytest` (tests) and `ruff` (code style checks)
- `.gitignore` that excludes `.venv`, `.env`, `__pycache__`, and the local database file
- `.env.example` committed with placeholder values only

### 2.2 Folder layout (mirrors CodeVision `src/`)
All new files start with `da_` (Developer Assistant) so they are easy to spot and never clash
with existing CodeVision files.

```
devassist/
  src/
    configs/da_config.py              settings read from .env
    agents/da_llm_client.py           the AI provider switch
    pydantic_classes/da_models.py     data shapes: Request, AuditEvent
    db_table_functions/db_tbl_da_requests.py   save and read requests
    db_table_functions/db_tbl_da_audit.py      save and read audit events
    da_logging.py                     shared logger helper
    da_smoke_check.py                 one script that proves Phase 0 works
  tests/                              one test file per module above
  specs/                              phase specs (this file)
```

### 2.3 Settings (`configs/da_config.py`)
Read from `.env`:

| Setting | Allowed values | Default |
|---|---|---|
| `DA_LLM_PROVIDER` | `fake`, `claude`, `onprem` | `fake` |
| `DA_CLAUDE_GENERATOR_MODEL` | any model name | (none) |
| `DA_CLAUDE_REVIEWER_MODEL` | any model name | (none) |
| `ANTHROPIC_API_KEY` | secret | (none) |
| `DA_DB_PATH` | file path | `data/devassist.db` |

- Any value outside the allowed list stops the app at startup with a clear message listing the allowed values.

### 2.4 AI provider switch (`agents/da_llm_client.py`)
- One function the rest of the app uses: `get_llm_client(role)`
  - `role` is `generator` (Qwen at work) or `reviewer` (Llama or Qwen at work)
- Every client has the same method: `complete(prompt, system=None)` returning
  text, provider name, and model name
- Providers:
  - `fake`: returns a fixed, predictable reply. Never touches the network. Used by all tests.
  - `claude`: calls Claude through the official Anthropic Python library, using the model set for that role.
  - `onprem`: placeholder only in Phase 0. Returns a clear "on-prem provider not configured yet" error.
    Filled in later from the photos of how CodeVision calls Qwen and Llama.

### 2.5 Data shapes (`pydantic_classes/da_models.py`)
- **Request**: request ID, title, developer ID, status, version, created at, updated at, rulebook version (empty until Phase 1)
- **AuditEvent**: request ID, timestamp, actor (`developer`, `system`, or `llm`), event type, details

### 2.6 Storage (`db_table_functions/`)
- SQLite at home (built into Python, nothing to install)
- All database access goes through these files only, so switching to CodeVision's database later touches only this folder
- Request functions: create, get by ID, list
- Audit functions: add event, list events for a request
- Request IDs: `CVDA-YYYY-NNNN`, a running number per year, never reused
- New requests start with status `NEW`. Later phases add their own statuses.

### 2.7 Logging (`da_logging.py`)
- One `get_logger(name)` helper built on Python's standard logging

### 2.8 Smoke check (`da_smoke_check.py`)
Running it prints, in plain words:
1. which provider is active
2. a new request created, with its ID
3. two audit events recorded for it
4. one AI reply (from the active provider)

## 3. Out of scope (do NOT build in Phase 0)
- Any screen or Dash code
- The rulebook (Phase 1)
- Chat, questions, search, gates, code generation, reviews (Phases 2 to 7)
- The real on-prem Qwen and Llama connection
- SonarQube, Bitbucket, user login or access control (bank entitlement handles access)

## 4. Rules
- R1. Audit events are append-only. No function may edit or delete one.
- R2. No secrets in code, logs, or test files. API keys only come from `.env`.
- R3. Tests never call a real AI or the internet. Tests use the `fake` provider or a mocked library.
- R4. Error messages are plain sentences a developer can act on, not raw tracebacks.
- R5. Only Python 3.14 features. Nothing that needs 3.15.
- R6. Keep it simple: no extra libraries beyond what this spec needs (Anthropic library, Pydantic, python-dotenv, pytest, ruff).

## 5. Done when
- [ ] `pytest` passes with 0 failures
- [ ] `ruff check` reports 0 problems
- [ ] With `DA_LLM_PROVIDER=fake`, the smoke check prints all 4 items in section 2.8
- [ ] With `claude` and no API key: a clear "ANTHROPIC_API_KEY is missing" message, no crash
- [ ] With `onprem`: a clear "not configured yet" message, no crash
- [ ] With an invalid value such as `qwen2`: a clear message listing the allowed values
- [ ] There is a test proving audit events cannot be edited or deleted
- [ ] `.env` is ignored by Git, and `.env.example` has placeholders only
- [ ] The independent reviewer reports 0 Must fix findings
- [ ] Claude adds a short plain-language "How Phase 0 works" section to the README

## 6. Open questions (do not block Phase 0)
- Q1. How does CodeVision call Qwen and Llama today? (photo, fills the `onprem` provider later)
- Q2. Which database does CodeVision use? (photo of `db_functions`, home uses SQLite until then)
- Q3. Exact library versions in `requirements.txt` at work (photo)
- Q4. Does CodeVision already have a shared logger we should use instead of `da_logging.py`?
