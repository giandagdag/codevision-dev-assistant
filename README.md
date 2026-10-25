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
a new request ID, its two audit events, and one AI reply. Since Phase 1 it also checks the
rulebook (items 5 to 8, below). Log lines (with times) and the numbered results go to separate
output streams, so in a console the log lines may appear first.

## How Phase 1 works

Phase 1 adds the **rulebook**: the one set of house rules that code generation and the
Independent Reviewer will read in later phases. There are still no screens; the Admin console
comes in Phase 9.

- **What is in it** (`pydantic_classes/da_rulebook_models.py`): a *charter* (purpose, scope,
  architecture principles, constraints, glossary), *rules* (`judgement` rules with IDs like
  `CV-PY-001`, and `ui_convention` rules with IDs like `CV-UI-001`), and a *policy* (default and
  max level, never-generate zones, max review rounds, 3 escalation triggers).
  The starter rulebook is the made-up `src/data/da_rulebook_seed.json`.
- **Versions work like a GDG with no limit** (`db_table_functions/db_tbl_da_rulebook.py`). Every
  save is a new version (v1, v2, v3...). Old versions are never changed or rolled off: the
  database itself refuses any UPDATE or DELETE, as with the audit trail. The newest version is
  the active one. *Restore* copies an old version into a new one, so nothing is lost.
- **A save is refused, with nothing written**, if: the change note is empty; someone else saved
  first (you are told which version is newer); nothing changed; or the rulebook breaks a house
  rule (L3 used, default above max, more than 10 judgement rules, review rounds outside 1 to 5,
  wrong escalation triggers, a repeated rule ID). All problems are listed in one message.
- **Rule IDs come from a counter**, like request numbers. `next_rule_id(kind)` hands out the next
  number and uses it up. Deleting CV-PY-006 never lets 006 come back: the next one is CV-PY-007.
  After v1, a save may only use IDs already handed out.
- **Charter size check**: the charter's text against a 6,000-character limit (about 2 pages).
  Green under 80%, amber 80% to 100%, red over 100%. A red charter can still be saved.
- **Pinning**: when a request is created, it is locked to the active version and keeps it to the
  end, even when newer versions are saved, like a running job that keeps reading the generation
  it started with. `get_rulebook_for_request(request_id)` returns that version. Creating a
  request before any rulebook is published is refused with a plain message.

The smoke check now **works in a throwaway database** that is deleted at the end of each run,
because rulebook versions can never be deleted and we don't want test versions in the real
database. It never touches `DA_DB_PATH`, so you can run it as often as you like. Items 5 to 8:
v1 published from the seed; the request pinned to v1; v2 saved with one changed rule while the
request stays on v1; v1 restored as v3, with all three versions listed newest first.

## Notes for the move to CodeVision

- **The audit-table triggers are SQLite-only.** The append-only guarantee comes from two SQLite
  triggers in `db_tbl_da_audit.py`. CodeVision's database will need an equivalent, for example
  its own triggers or table permissions that allow INSERT and SELECT only. Until then the audit
  trail is only protected by our code. **The same applies to the rulebook-version table**
  (`db_tbl_da_rulebook.py`).
- **Write locks** use SQLite's `BEGIN IMMEDIATE` (`begin_write` in `da_db.py`), so two saves
  cannot both pass the stale-save check. CodeVision's database needs its own equivalent, for
  example `SELECT ... FOR UPDATE` on the newest version.
- **No database link from requests to rulebook versions.** The pinned version number is set in
  code, in the same transaction as the request. CodeVision's database could add a foreign key.
- Library versions in `requirements.txt` are home versions; match them to CodeVision's (spec Q3).
- `da_logging.py` may be replaced by CodeVision's shared logger if one exists (spec Q4).
