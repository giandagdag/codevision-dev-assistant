# CodeVision Developer Assistant

A new capability inside CodeVision that helps developers understand a change, reuse existing code,
get starter code, and get early review feedback. This folder is a clean-room build, copied into
CodeVision later. All examples are made up.

## Getting started (Windows PowerShell)

```
py -V:3.14 -m venv .venv                          # must be 3.14, not the PC default
.venv\Scripts\python -m pip install -r requirements-home.txt
copy .env.example .env                            # then edit .env; it never goes into Git
```

| What | Command |
|---|---|
| Run the tests | `.venv\Scripts\python -m pytest` |
| Check code style | `.venv\Scripts\python -m ruff check .` |
| Run the smoke check | `.venv\Scripts\python src\da_smoke_check.py` |
| Publish the starter rulebook (once) | `.venv\Scripts\python src\da_load_starter_rulebook.py` |
| Run the screen (then open http://127.0.0.1:8050) | `.venv\Scripts\python src\web\da_home_web_server.py` |

## How Phase 0 works

Phase 0 is the engine room. There are no screens and no real AI features yet. It has five parts,
each in its own file under `src/`, following CodeVision's folder layout:

1. **Settings** (`configs/da_config.py`). Reads `.env` once at startup, like a data area the
   program reads when it starts. A wrong provider name stops the program straight away with a message listing the
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
   *AuditEvent* (one thing that happened to it). Pydantic checks every field, like DDS field keywords
   (VALUES, RANGE, CHECK) built into a file description.

4. **Storage** (`db_table_functions/`). SQLite at home. All database access lives in this folder,
   so moving to CodeVision's database only touches these files.
   - Request IDs look like `CVDA-2026-0001`: a running number per year, never reused.
     All stored times are UTC, but **the year in the ID follows Singapore time (UTC+8)**, so a
     request made at 01:00 on 1 January in Singapore is a new-year request.
   - The audit trail is **append-only**, like a journal: entries are added, never changed. There are no edit or delete
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
- **Versions work like journal receivers** (`db_table_functions/db_tbl_da_rulebook.py`). Every
  save is a new version (v1, v2, v3...). Old versions are never overwritten or deleted: the
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
  end, even when newer versions are saved, like a job that keeps the library list it started
  with, whatever changes in the system afterwards. `get_rulebook_for_request(request_id)` returns that version. Creating a
  request before any rulebook is published is refused with a plain message.

The smoke check now **works in a throwaway database** that is deleted at the end of each run,
because rulebook versions can never be deleted and we don't want test versions in the real
database. It never touches `DA_DB_PATH`, so you can run it as often as you like. Items 5 to 8:
v1 published from the seed; the request pinned to v1; v2 saved with one changed rule while the
request stays on v1; v1 restored as v3, with all three versions listed newest first.

## How Phase 2A works

Phase 2A is the engine for **Understand**, the developer's step 1: the developer describes a
change, answers 4 fixed questions, settles any decisions, and confirms a request record. There
is no screen yet (that is 2B), and no code is ever written or shown.

Think of it as a 5250 interactive program. The web calls the program fresh on every Enter, so
the conversation is kept in a work file between screens. A page reload loses nothing.

- **Statuses** (`pydantic_classes/da_models.py`): DRAFT, CLARIFICATION_IN_PROGRESS,
  DECISION_REQUIRED, READY_FOR_CONFIRMATION, CONFIRMED_FOR_DISCOVERY. Only the moves in the
  spec 3.1 table are allowed, like a screen where only some function keys work. Any other move
  is refused with a plain message. Every move writes a `status_changed` audit event.
- **The program** (`agents/da_understand_flow.py`) decides everything: which question comes
  next, when a decision must be asked, and whether the record may be confirmed. The screen
  (2B) will only call these functions: `create_understand_request`, `submit_answer`,
  `choose_option`, `skip_optional`, `confirm_request`, `get_understand_view`,
  `list_my_requests`.
- **The interpreter** (`agents/da_understand_agent.py`) is like a called subprogram whose
  output is validated before use. The AI only *suggests* field values and points out what is
  unclear. Its prompt is `src/data/da_understand_prompt.md`, and it only sees the charter of the
  rulebook the request is pinned to. A bad reply is retried once with a note; a second bad reply
  gives "I couldn't process that answer..." and the record does not change.
- **The app checks** (`agents/da_understand_checks.py`), plain Python, like DDS field keywords
  plus a validity-check program:
  - no code in a reply;
  - no file or function names (like `excel_reader.py`, `check_type()` or `upload.check_type`)
    in the flow or expected behaviour, unless the developer typed them;
  - field lengths (title 80, text 1,000, lists 12 items of 300);
  - an item both in scope and out of scope becomes an open item;
  - more than 5 decisions on one request means "get help from a senior". The request then
    waits with no input allowed: the senior escalation inbox comes in Phase 8.
- **Decisions and assumptions.** Something unclear that changes what gets built is always
  asked: the text input is locked and only the choices work, always including "I need help
  deciding". A small unclear point is resolved and shown as an assumption with its basis.
- **The confirmation gate**: all 4 questions answered; the main fields filled; at least 2 flow
  steps, 1 success and 1 failure scenario; no open items and no waiting decision. If it fails,
  every missing item is listed.
- **Storage** (`db_table_functions/db_tbl_da_understand.py`):
  - `da_understand_sessions` is the work file. Each save carries a revision number: a save
    from an old window is refused ("updated in another window"), so two windows can't
    overwrite each other.
  - `da_chat_messages` and `da_request_records` are journaled files: the database refuses any
    UPDATE or DELETE, even from a raw SQL tool.
  - Each action is saved in one transaction (chat, session, status, audit events), or not at
    all. The AI call happens before the lock is taken, because it can take seconds.
- **Safety.** A message that looks like a password or key is refused before it is saved or
  sent, and the message says why. Messages are limited to 4,000 characters.
- **Demo mode.** With `DA_LLM_PROVIDER=fake`, replies come from
  `src/data/da_understand_fake_script.json`: a made-up Excel upload example from the demo. It
  ignores what you type.
- **Starter rulebook loader** (`da_load_starter_rulebook.py`): run once to publish the seed
  as v1 in your real database (`saved_by` is `setup-script`). Running it again changes nothing.

The smoke check adds items 9 to 12 in its throwaway database: the loader publishes v1 and then
changes nothing; a request answers questions 1 to 4; a decision is asked and recorded; and the
request is confirmed as record v1, after which a raw SQL edit of v1 is refused. Items 9 to 12
always use the fake script, whatever provider is set.

## How Phase 2B works

Phase 2B puts a screen on the 2A engine. It adds **no rules of its own**: every check (secret
words, length, stale window, which input is allowed) still lives in the 2A code. The screen only
shows what the engine says and passes on the clicks.

AS400 comparison: the layout file is the display file (DDS), the callbacks are the small part of
an RPG program that reads the function key and calls the right subroutine, and the Understand
engine is the program that does the real work. The conversation is kept in a work file (the
database) between screens, so a page reload or a lunch break loses nothing.

**Run it** (first time, publish the starter rulebook once; see the table at the top):
`.venv\Scripts\python src\web\da_home_web_server.py`, then open http://127.0.0.1:8050.
With the default `DA_LLM_PROVIDER=fake`, replies are scripted and a banner says so.

| File | What it does |
|---|---|
| `layouts/da_developer_assistant_page.py` | What is on the screen: Home, the blank workspace, a request's workspace (stepper, chat, composer, Summary panel) |
| `callbacks/screen_callbacks/da_developer_assistant_page_callbacks.py` | `show_page` draws the right page from the URL; `handle_action` handles Send, a choice button or Skip and calls one 2A function |
| `web/da_web_components.py` | Our own building blocks: status pill, stepper, chat bubble, panel section, progress bar |
| `styles/da_styles.py` | The colours and sizes, in one place |
| `web/da_home_web_server.py` | **Home only.** A stand-in CodeVision shell (header, left menu, `dcc.Location`). Never copied to work |

How a click flows: you press **Send**. `handle_action` calls `create_understand_request` (first
message) or `submit_answer`. If the engine refuses, its plain message appears under the chat and
nothing is written. If it works, the page is drawn again from the database. While the interpreter
thinks, Send shows a spinner and the text box cannot be used twice.

- **Addresses.** `?new=1` is the blank workspace, `?request=CVDA-2026-0001` opens that request,
  nothing opens Home. Reload any of them and you get the same screen.
- **Four composer modes.** Text box; busy (spinner while the interpreter works); locked choices
  (text box off, buttons only, "I need help deciding" always last); done (confirmed, with the
  disabled "Proceed to Discovery (coming in Phase 3)" button). When a senior is needed the box is
  also locked and says why.
- **Summary panel.** Fills after every answer; fields changed by the last answer are
  highlighted; empty fields say "Waiting for your answer"; assumptions show their basis.
- **Text is always plain text.** A message such as `<b>hi</b>` is shown as typed, never as HTML.
- **Times** are shown in Singapore time. The server listens on 127.0.0.1 only.
- **Icons** are drawn by `dash-iconify`, which downloads them from the internet when the page
  loads. With no internet the screen still works; the small icons are just missing.

Tests do not open a browser. They build the components and call the callback functions
directly, using the fake provider and a temporary database.

## Notes for the move to CodeVision

- **The audit-table triggers are SQLite-only.** The append-only guarantee comes from two SQLite
  triggers in `db_tbl_da_audit.py`. CodeVision's database will need an equivalent, for example
  its own triggers or table permissions that allow INSERT and SELECT only. Until then the audit
  trail is only protected by our code. **The same applies to the rulebook-version table**
  (`db_tbl_da_rulebook.py`), **the chat messages and the confirmed request records**
  (`db_tbl_da_understand.py`).
- **Write locks** use SQLite's `BEGIN IMMEDIATE` (`begin_write` in `da_db.py`), so two saves
  cannot both pass the stale-save check. CodeVision's database needs its own equivalent, for
  example `SELECT ... FOR UPDATE` on the newest version.
- **No database link from requests to rulebook versions.** The pinned version number is set in
  code, in the same transaction as the request. CodeVision's database could add a foreign key.
- `requirements.txt` holds only what goes to work, at CodeVision's versions (spec Q3).
  `requirements-home.txt` adds `anthropic`, `pytest` and `ruff` and is never copied to work.
  The Claude provider is home only; the app starts at work without `anthropic`.
- `da_logging.py` may be replaced by CodeVision's shared logger if one exists (spec Q4).
- **Phase 2B files to copy:** `layouts/`, `callbacks/`, `styles/` and `web/da_web_components.py`.
  Do **not** copy `web/da_home_web_server.py` (it stands in for CodeVision's own header, menu and
  routing). At work, check two things (spec Q6): the id of CodeVision's `dcc.Location` (the page
  uses `url`, see `LOCATION_ID`), and where the side-menu entries are listed.
- `dash`, `dash-mantine-components` and `dash-iconify` are in `requirements.txt` at the work
  versions. Dash pulls in Flask; home gets 3.1.3, work has 3.1.2.
