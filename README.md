# CodeVision Developer Assistant

A new capability inside CodeVision that helps developers understand a change, reuse existing code,
get starter code, and get early review feedback. This folder is a clean-room build, copied into
CodeVision later. All examples are made up.

## Getting started (Windows PowerShell)

```
py -V:3.14 -m venv .venv                          # must be 3.14, not the PC default
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env                            # then edit .env; it never goes into Git
```

| What | Command |
|---|---|
| Run the tests | `.venv\Scripts\python -m pytest` |
| Check code style | `.venv\Scripts\python -m ruff check .` |
| Run the smoke check | `.venv\Scripts\python src\da_smoke_check.py` |

## How Phase 0 works

Phase 0 is the engine room. There are no screens and no real AI features yet. It has five parts,
each in its own file under `src/`, following CodeVision's folder layout:

1. **Settings** (`configs/da_config.py`). Reads `.env` once at startup, like a control card for
   the whole run. A wrong provider name stops the program straight away with a message listing the
   allowed values. The API key is never printed or logged.

2. **AI provider switch** (`agents/da_llm_client.py`). The rest of the app asks for
   `get_llm_client("generator")` or `get_llm_client("reviewer")` and calls `complete(prompt)`.
   It never knows which AI is behind it. `DA_LLM_PROVIDER` chooses:
   - `fake`: a fixed, predictable reply, no network. All tests use this.
   - `claude`: calls Claude. Needs `ANTHROPIC_API_KEY` and the model name for the role
     (`DA_CLAUDE_GENERATOR_MODEL` or `DA_CLAUDE_REVIEWER_MODEL`). If any is missing, you get a
     plain message naming it.
   - `onprem`: placeholder until we connect CodeVision's Qwen and Llama.

3. **Data shapes** (`pydantic_classes/da_models.py`). A *Request* (one developer change) and an
   *AuditEvent* (one thing that happened to it). Pydantic checks every field, like a record layout
   with validation built in.

4. **Storage** (`db_table_functions/`). SQLite at home. All database access lives in this folder,
   so moving to CodeVision's database only touches these files.
   - Request IDs look like `CVDA-2026-0001`: a running number per year, never reused.
     All stored times are UTC, but **the year in the ID follows Singapore time (UTC+8)**, so a
     request made at 01:00 on 1 January in Singapore is a new-year request.
   - The audit trail is **append-only**, like a write-once journal. There are no edit or delete
     functions, and the database itself refuses any UPDATE or DELETE on the audit table.
     Events list in time order, then in the order they were added, so two events with the same
     timestamp never swap.

5. **Logging** (`da_logging.py`). `get_logger(name)` gives every file the same log line format.

The **smoke check** (`da_smoke_check.py`) uses all five together and prints: the active provider,
a new request ID, its two audit events, and one AI reply. It writes to the database in `DA_DB_PATH`.
Log lines (with times) and the numbered results go to separate output streams, so in a console
the log lines may appear first.

## Notes for the move to CodeVision

- **The audit-table triggers are SQLite-only.** The append-only guarantee comes from two SQLite
  triggers in `db_tbl_da_audit.py`. CodeVision's database will need an equivalent, for example
  its own triggers or table permissions that allow INSERT and SELECT only. Until then the audit
  trail is only protected by our code.
- Library versions in `requirements.txt` are home versions; match them to CodeVision's (spec Q3).
- `da_logging.py` may be replaced by CodeVision's shared logger if one exists (spec Q4).
