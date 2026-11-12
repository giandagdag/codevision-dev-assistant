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
| Check the AI can be reached (ping) | `.venv\Scripts\python src\da_llm_ping.py` |
| Run the pretend work AI (for `onprem` at home) | `.venv\Scripts\python src\web\da_fake_onprem_server.py` |

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
   - `onprem`: CodeVision's Qwen and Llama through the standard chat-completions format
     (since Phase 2C, see below).

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
  - more AI questions than the limit on one request (rulebook policy `max_material_decisions`,
    starter 5, allowed 1 to 10) means "get help from a senior". The request then
    waits with no input allowed: the senior escalation inbox comes in Phase 8.
- **Decisions and assumptions.** Something unclear that changes what gets built is always
  asked: the choices stay and the text box opens ("Other, type here", up to 300 characters),
  always including "I need help deciding". A small unclear point is resolved and shown as an assumption with its basis.
- **The confirmation gate**: all 4 questions answered; the main fields filled; at least 2 flow
  steps, 1 success and 1 failure acceptance criterion; no open items and no waiting decision. If it fails,
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
| `web/da_home_web_server.py` | **Home only.** A stand-in CodeVision shell (header, a left menu with only Developer Assistant, `dcc.Location`). Never copied to work |

How a click flows: you press **Send**. `handle_action` calls `create_understand_request` (first
message) or `submit_answer`. If the engine refuses, its plain message appears under the chat and
nothing is written. If it works, the page is drawn again from the database. While the interpreter
thinks, Send shows a spinner and the text box cannot be used twice.

- **Addresses.** `?new=1` is the blank workspace, `?request=CVDA-2026-0001` opens that request,
  nothing opens Home. Reload any of them and you get the same screen.
- **Four composer modes.** Text box; busy (spinner while the interpreter works); locked choices
  (text box off, buttons only, "I need help deciding" always last); done (confirmed; Discover
  then starts by itself). A new request first shows the **4-box form** (see "Phase 6 fixes"). When a senior is needed the box is
  also locked and says why.
- **Enter sends, Shift+Enter makes a new line.** A small browser script (a Dash clientside
  callback in the callbacks file) presses the Send button when you press plain Enter, so Enter
  takes exactly the same path as clicking Send and gets the same checks and messages. It does
  nothing while the box is locked, while a reply is running, or with Shift, Ctrl, Alt or Meta held.
  Enter on an empty box shows the normal "Please type a message first." message.
- **Summary panel.** Six tabs with tabler icons; only Summary works, the rest are greyed out. Fills after every answer; fields changed by the last answer are
  highlighted; empty fields say "Waiting for your answer"; assumptions show their basis.
- **Text is always plain text.** A message such as `<b>hi</b>` is shown as typed, never as HTML.
- **Times** are shown in Singapore time. The server listens on 127.0.0.1 only.
- **Icons** are drawn by `dash-iconify`, which downloads them from the internet when the page
  loads. With no internet the screen still works; the small icons are just missing.

Tests do not open a browser. They build the components and call the callback functions
directly, using the fake provider and a temporary database.

## How Phase 2C works

Phase 2C fills in the `onprem` provider, so on the work laptop the Understand conversation can
run against CodeVision's Qwen or Llama. We cannot reach them from home, so the connector is built
to the standard "chat completions" format (the same format CodeVision's `API_CALL` uses) and is
tested at home against a pretend server that answers in that format.

AS400 comparison: the screen and the logic already existed. This phase writes the program that
CALLs the remote system through its published parameter list, plus a dummy remote program on the
test LPAR that answers the same way, plus a PING to prove the line works first.

| Piece | File | What it does |
|---|---|---|
| The client | `agents/da_llm_client.py` (`OnPremLLMClient`) | One HTTP POST per question. Body: model, messages, `temperature` 0.2, `top_p` 0.2, `max_tokens` 2048, `stream` false. Reply text is read from `choices[0].message.content`. |
| Settings | `configs/da_config.py`, `.env.example` | `DA_ONPREM_URL`, `_MODEL`, `_API_KEY`, `_AUTH_HEADER`, `_AUTH_PREFIX`, `_VERIFY`, `_TIMEOUT_SECONDS` |
| Rejected-reply log | `agents/da_rejected_reply_log.py` | Every reply the engine rejects is appended to `logs/da_rejected_replies.log` (Singapore time, request ID, attempt, provider, model, problems, raw text cut at 20,000 characters). Stays on the laptop. A log that cannot be written never stops the conversation. |
| Ping | `da_llm_ping.py` | Sends "ping", prints provider, model, host name only, seconds and the first 200 characters of the reply. Exit code 0 or 1. Works with `fake` too. |
| Pretend server | `web/da_fake_onprem_server.py` | Standard library only, 127.0.0.1 only, port 8070. Answers from the same scripted entries as the fake provider. |

**Try it at home** (two terminals):

1. Terminal 1: `.venv\Scripts\python src\web\da_fake_onprem_server.py`
   (options: `--mode normal`, `--mode bad-json`, `--mode error`, `--port 8070`)
2. In `.env`: `DA_LLM_PROVIDER=onprem`, `DA_ONPREM_URL=http://127.0.0.1:8070/v1/chat/completions`,
   `DA_ONPREM_MODEL=fake-qwen`
3. Terminal 2: `.venv\Scripts\python src\da_llm_ping.py`, then start the screen as usual.

The modes: `bad-json` makes the first reply of each turn not JSON, to prove the engine's retry and
fill the rejected-reply log. `error` answers HTTP 500, to prove the network retries and the plain
message. Set `DA_FAKE_ONPREM_KEY` (in `.env` or the environment) to make the server answer 401
unless the client sends `Authorization: Bearer <that key>`.

**Retries.** Connection errors, timeouts, HTTP 429 and HTTP 5xx are tried 3 times in total,
waiting 2 then 4 seconds. Other answers (401, 403, 404, other 4xx) and certificate problems are
not retried. Every failure gives a plain message saying what to check. The key never appears in a
message or log line. This is separate from the engine's own "bad JSON, try once more" retry.

**Certificates.** The check is on by default. `DA_ONPREM_VERIFY` can be a path to the bank's
certificate file, or `false` for the prototype only (a WARNING is logged every time).

**If Friday's photos show a difference** (auth header, body field names, where the reply text
sits, `httpx` instead of `requests`): the format lives in three small functions in
`da_llm_client.py` (`_build_body`, `_build_headers`, `_read_reply`) plus the constants at the top
of the file. Auth header name and prefix are settings. Change one place and update its test.

The smoke check adds items 13 (the ping against the pretend server) and 14 (a full conversation
with `onprem` against it, reaching CONFIRMED_FOR_DISCOVERY). They always use the pretend server,
whatever provider is set. The Monday plan is `docs/monday-work-test.md`.

## How Phase 3 works

Phase 3 is **Discover**: after a request is confirmed, the app searches approved code for
something that already does the job, so the developer reuses it instead of writing a copy.

AS400 comparison: like running a where-used query (DSPPGMREF) before writing a new program. The
app runs the queries (CL), the AI writes one short report, and the result goes into its own
journaled file keyed to the request. Request record v1 is never touched.

**The flow in 5 lines**

1. Discovery starts by itself when you press **Proceed with this understanding**. The app builds up to 6 searches from the
   record (exact: title and references; meaning: objective and expected behaviour).
2. The searches run on the index, our own safety filter drops anything deprecated, restricted or
   secret-looking, and the best 12 hits are numbered.
3. The AI is asked once to sort the hits into findings (it may only cite hit numbers it was
   given). A bad reply is retried once. After two bad replies the app shows plain search results
   instead, with a banner.
4. The app picks the outcome (**Similar implementation found** or **No reliable match**), and
   saves the round, the status moves, the audit events and the chat lines in ONE transaction.
5. The developer confirms, types a hint (**Something's missing**, up to 3 rounds in total), or
   escalates to a senior developer.

| Piece | File | What it does |
|---|---|---|
| Search interface and safety filter | `agents/da_search_index.py` | `SearchIndex` with one `search` method, the pretend index, `get_search_index`, and `drop_unsafe_hits` (our own filter, run after any index) |
| Pretend index | `data/da_fake_index.json` | About 26 made-up pieces in the shape the real index will have. The position in the list IS the piece number, and the loader refuses gaps or wrong order |
| Python splitter | `agents/da_code_splitter.py` | One piece per function, class and method (standard `ast`). Used in tests now, by the work adapter later (P15) |
| Searches and merge | `agents/da_discover_queries.py` | Builds the queries; merges hits by (path, symbol), so two functions in one file stay two hits |
| The AI call | `agents/da_discover_agent.py`, `data/da_discover_prompt.md` | One call, retry once, plain-results fallback |
| Checks | `agents/da_discover_checks.py` | Cited hits must be hits we sent; no code in any text; hint checks |
| Flow | `agents/da_discover_flow.py` | `start_discovery`, `add_hint_and_search`, `confirm_discovery`, `escalate_discovery`, `get_discovery_view` |
| Storage | `db_table_functions/db_tbl_da_discovery.py` | `da_discovery_results` (one row per round, append-only) and `da_discovery_state` (the discovery revision) |
| Screen | `layouts/`, `callbacks/`, `web/da_web_components.py` | Discover workspace, Discovery tab, finding cards |

**How the pretend index works.** `DA_SEARCH_PROVIDER=fake` (the default) reads
`data/da_fake_index.json`. Exact search matches whole words (case does not matter) in the path,
tags and snippet. Meaning search matches after a small synonym list (for example extract, parse,
read are one group). It proves the pipeline; it is not real semantic search. `codevision` is a
placeholder that says "CodeVision search is not configured yet" until the work adapter (P15).

**Try it at home.** Run the screen as usual with `DA_LLM_PROVIDER=fake`. Get a request to
CONFIRMED FOR DISCOVERY (the scripted Excel example; Discovery starts by itself), then try
**Something's missing** with a hint such as `batching helper`, then **Findings look right**.
To see the fallback banner, start the pretend server with `--mode bad-json`, set
`DA_LLM_PROVIDER=onprem` as in Phase 2C, and press Proceed with this understanding: both AI tries are bad,
so plain results show. (Unlike Understand, bad-json is bad on every Discover try.)

**Stale windows.** Discover keeps its own revision number (`da_discovery_state`), so the Understand
session and record v1 are never written by Discover. A second window acting on an old view is
refused with the usual "updated in another window" message.

The smoke check adds items 15 (the pretend index, searches and the safety filter), 16 (a full
Discover run to DISCOVERY_CONFIRMED with record v1 unchanged) and 17 (bad-json fallback).

## How Phase 4 works

Phase 4 is **Approach**: after Discover is confirmed, the app plans HOW the change will be built
and HOW it will be tested, before any code is written. Only then does the request become
**READY TO BUILD**. (AS400 comparison: the program change form signed off before anyone touches the
source. It lists the objects to create or change, which existing objects are reused, and a test
script written by QA, not by the programmer.)

Two AI roles do separate jobs in separate calls. The **Generator** proposes the plan (files to
create or change, what to reuse from Discover, design choices, libraries). The **Tester** writes
the test plan from the acceptance criteria and never sees the file plan or any code. The app checks
every reply with plain code; the AI suggests, the app decides, the developer approves.

1. **Findings look right** starts the approach by itself (one Generator call). The Approach tab shows the file plan, reuse
   decisions, libraries and warnings. If the plan has design choices, they are asked one at a time
   (buttons, **I need help deciding**, or type your own answer, 300 characters). After the last one,
   ONE more call settles the plan as a new version; the old version is kept.
2. **Accept approach** or **Get help**; to change the plan, type what should change and press
   **Change something** (up to 3 per request). More code files
   than the limit (5 in the starter rulebook) asks for a typed reason, which is audited.
3. The Tester writes the **test plan**. Type a case and press **Add a test case** (up to 5); you
   see a draft and press **Keep this case** or **Discard it**. **Go back and change the approach** from here
   makes a new approach and a new Tester plan; your own cases are kept.
4. **Accept test plan** runs the **gate**: request confirmed, Discover done, approach confirmed,
   test plan accepted. All four true gives READY TO BUILD. The Build button stays disabled until
   Phase 5.

**The rule lists** (allowed folders, new file name pattern, protected files, approved libraries,
the file limit, the design-choice limit and the flag-for-review zones) are new fields on the
rulebook `policy`. A rulebook version saved before Phase 4 loads with the starter values. The
Admin screen that edits them comes in Phase 11. A file in a flag-for-review zone (for example a
login page) never blocks: it adds a warning and the zone name, and a named senior becomes a
required reviewer at the pull request.

**Tester model.** `DA_CLAUDE_TESTER_MODEL` (home) and `DA_ONPREM_TESTER_MODEL` (work) choose the
Tester's model. Empty means the generator's model, until the bake-off decides.

**Try it at home.** Run the screen with `DA_LLM_PROVIDER=fake`, take the scripted Excel example to
DISCOVERY CONFIRMED (the approach starts by itself after **Findings look right**). The fake plan always shows one warning, "Not
found in Discover", on purpose: it modifies a path that no Discover hit has. To see the failure
paths, start the pretend server with `--mode bad-json` and set `DA_LLM_PROVIDER=onprem`: the
first call fails twice and the button reads **Try again**. (Like Discover, bad-json is bad on every
try for these prompts.)

**Stale windows.** Approach keeps its own revision number (`da_approach_state`). A second window
acting on an old view is refused with the usual "updated in another window" message.

The smoke check adds items 19 (fake provider to READY TO BUILD), 20 (the same against the pretend
server) and 21 (the Tester's prompt holds the criteria and not the file plan).

## How Phase 5 works

Phase 5 is the **Workspace**: after READY TO BUILD, the app connects to your own copy of CodeVision
on your laptop, checks that the file plan fits that folder, takes a fingerprint of every planned
file, and proves that writing and reading back works. Phase 6 then writes the real code through
the same door. (AS400 comparison: the workspace is your own source library. The app may `ADDPFM`
and `CHGPFM` only the members on the approved change form, nothing else in the library. A
fingerprint is the member's last-changed stamp, but exact. A re-scan is `DSPFD` over those
members to see which ones somebody touched; **Build** does it by itself, and a Re-scan button
after a build comes back in Phase 8.)

**The key fact: the Python server cannot touch your laptop.** Only the browser can, and only after
you pick the folder in the browser's own window and click Allow. So JavaScript in the page
(`src/web/da_workspace.js`) reads and writes files. Python decides what may be written and keeps
the record. They talk in four hops, each a Dash callback:

1. **Click** (browser): you press **Choose workspace folder**; the page collects *facts* about the
   folder (does `src/web` exist, does each planned file exist, what does it say).
2. **Judge** (server): plain Python turns the facts into blockers B1 to B7 or into a *write job*.
3. **Write** (browser): the page runs the job. Before overwriting a file it checks the file still
   has the fingerprint the server expects (the **edit guard**: your edits are never overwritten).
4. **Save** (server): ONE database save holds the state, the file rows, the audit events and the
   chat lines together.

(Phase 5 first wrote `tests/<request id>/__init__.py` to prove the write door works. **Phase 6
removed that:** the check now writes nothing, and tests never go to your folder. See "How Phase 6
works".) If the folder has a problem you get **Choose another folder**, **Change the approach**
(only when the problem is a planned file, B3 to B6; back to APPROACH PROPOSED, counts as one of
the 3 changes) or **Get help** (the workspace step
stays `ws_blocked`; the open item reads `Escalated in Workspace: ws_blocked`).

**Fallback.** If the browser has no folder picker, or you refuse it, **Download ZIP** gives you the
files with a `READ_ME_FIRST.txt`, and **Upload folder to check** lets the app check your folder
(only the planned files are read; the rest is never opened).

**Fingerprints** ignore the line-ending style and a leading byte-order mark (Windows editors flip
those). The app keeps a file's own line-ending style when it changes it. The server recomputes
every fingerprint itself and never trusts the browser's.

**Two new rulebook policy fields:** `workspace_markers` (folders that must exist, starter
`src/web`, `src/callbacks`) and `workspace_max_file_kb` (512). Older rulebook versions load with
these values.

**Carried fixes.** **Get help** now also shows at the "Write the test plan" step (P24), `.vscode/` is
ignored by Git (P25), and gate check 2 now also needs the confirmed Discover round to be built
from the latest request version (N2).

**Check it at home.**
- Tests: `.venv\Scripts\python -m pytest`. The real-browser tests need Playwright 1.63.0 and its
  browser (cloud session only); on your laptop they are **skipped**, and the skip text says which
  rows were not proven. Do not run `playwright install`.
- Smoke check items 22 and 23 run READY TO BUILD to `ws_ready` with a pretend folder and then find
  one changed file.
- By hand: run the screen on `http://127.0.0.1:8050` (it counts as a secure page) with
  `DA_LLM_PROVIDER=fake`, take a request to READY TO BUILD and press **Choose workspace folder**.
  Pick the small **practice folder**, not your working folder and not a copy of the repo. The
  fake plan changes `src\agents\upload_validator.py`, which the repo does not have, so a repo
  copy always stops at blocker B3. The Command Prompt steps that build the practice folder (it
  needs `src\web`, `src\callbacks` and a one-line `src\agents\upload_validator.py`) are in
  `docs/workspace-work-test.md`; they work at home too.

**Stale windows.** The workspace keeps its own revision number (`da_workspace_state`). A second
window acting on an old view is refused with the usual "updated in another window" message.

## How Phase 6 works

Phase 6 is the **Build + test loop**: this is where code is finally written. (AS400 comparison: the
whole build is a batch job you submit with `SBMJOB` and check later with `WRKSBMJOB`. The tests are
a signed-off UAT script that the programmer may not edit. Layer A is the compile listing. Layer B
is a job in its own subsystem with its own `QTEMP` and a maximum run time.)

What happens when you press **Build** (after your workspace is ready):

1. **Pre-build re-scan.** The page reads your planned files once more. If you changed one, your
   text is the starting text (nothing is lost).
2. **Contract.** The Generator (Qwen at work) writes only the public names and arguments of each
   planned file. The Tester sees this, never any code.
3. **Tests, then frozen.** The Tester turns the accepted test plan into `unittest` code, one test
   per case, named like `test_t6_ac4_empty_sheets_rejected`. They are saved and never edited.
4. **Code, one file per AI call.** A new file is written whole. An existing file gets edit blocks
   (`<<<<<<< FIND` ... `=======` ... `>>>>>>> REPLACE`) that must each match exactly once.
5. **Layer A** (plain Python, no AI): syntax, planned files only, protected files, allowed imports
   (a blocked module always beats an approved library), risky calls, the agreed names.
6. **Layer B** (the sandbox): the frozen tests run on the **server**, in a separate Python process,
   in a temporary folder, with an empty environment (no keys) and a time limit (60 s, then the
   whole process tree is ended). The folder is deleted afterwards.
7. **Rounds.** One shared budget of 3. A failed round sends a plain failure report back and only
   the failing files are fixed. The AI not answering, a prompt that is too big, or a restart
   **never** uses a round: the build pauses and **Resume build** resumes it.
8. **Result.** After Layers A and B pass, the independent Tester reviews the code (Layer C, Phase 7,
   see "How Phase 7 works"). The budget used up is **Not passing** (red). Never "Approved".
9. **Write.** The page writes the code files by itself when the build is done and your folder is
   allowed (otherwise press **Reconnect**). It is the Phase 5 write job: it creates **no** folders
   and never overwrites a file you changed (the edit guard). **The tests are never written to your
   folder.** CodeVision has no automated tests today, so you test the change by hand on your
   laptop, as before; the tests and their results stay on the **Tests** tab.

The build runs on a background thread in the server. The page asks for progress every 3 seconds;
you can leave and come back (**My recent requests**). If the server restarts mid-build, the build
is paused with "The server restarted during your build." and **Resume build** carries on without
rewriting finished files. At most 2 builds run at once on one server; the others wait their turn.

**Honest limits.** The sandbox is a separate process with a time limit and no secrets. It does
**not** block the network at operating-system level and does **not** cap memory. Layer A's import
and call rules are the guard. Question Q14 (d) asks the CodeVision team about more.

**Six new rulebook policy fields** (older versions load with these starter values):
`build_max_rounds` 3, `build_test_timeout_seconds` 60, `build_max_prompt_chars` 60000,
`build_max_parallel` 2, `build_blocked_imports`, `build_sandbox_exclude`. The protected-file and
approved-library lists are the **Phase 4 ones** (one list each, so Approach and Build agree).

## How Phase 7 works

Phase 7 is the **Independent Tester** (Layer C). AS400 picture: the peer code review before the
promotion to the QA library. A second programmer reads the source against the change request and
the shop standards; he was not in the design meeting and never saw the Generator's chat.

- **When.** Only after Layers A and B pass in a round. Status `TESTER_REVIEW`, step
  `b_tester_review`. **Cancel build**, the stale check, restart recovery all work as before.
- **Seven checks.** 1, 2, 3 and 7 are plain Python (a test for every criterion, those tests pass,
  files match the file plan, flag-for-review zones). 4, 5 and 6 are one AI call (approach decisions
  followed, nothing extra built, judgement rules kept).
- **Evidence rule.** Every AI finding must name a planned file, a real line, a quote found within
  2 lines, and an allowed cite (`DD-n`, `RU-n`, `PLAN:path`, `AC-n` or a rule ID). Plain code drops
  any finding that fails; dropped ones are saved with the reason (**Show dropped** on the Tests tab).
- **Severity.** **Must fix** goes back to the Generator and uses a round of the same shared budget
  of 3 (only the cited files; Should fix and FYI never reach the Generator). **Should fix**: accept
  with a reason (10 to 300 characters) or leave open. **FYI**: shown only. **Fix it** is greyed
  ("Coming in Phase 8").
- **Labels** (worked out by plain code, never by the AI): **Ready for your review** (green),
  **Ready with warnings** (yellow: an open Should fix or a zone touched), **Not passing** (red),
  **Unable to assess** (grey: the reply was unusable twice; **Run the Tester review again** makes a
  new review and uses no round). Never "Approved". The label is recalculated from the newest review
  plus your accept and reopen actions; the closed run row is not edited.
- **A Must fix found by a re-run** ends the build as **Not passing** (Gian's decision, 7 Nov).
- **Dispute** a Must fix: the request goes to a senior (`Disputed Must fix: F-n`); the inbox comes
  in Phase 10.
- **Too big.** If the prompt is over `tester_max_prompt_chars` (60000), or the server answers HTTP
  400, the review is split into one call per file. If one file is still too big, the build pauses
  and **Resume build** repeats the review. No round is used.
- **The report stays in the app** (Tests tab). Nothing from it goes to your folder.
- **The Tester model** is a setting (`DA_CLAUDE_TESTER_MODEL`, `DA_ONPREM_TESTER_MODEL`); empty
  means the Generator's model. Which model at work is open question Q9; see `docs/tester-work-test.md`.
- **At home** the fake Tester follows a script, so a default build takes 3 rounds: round 1 the tests
  fail, round 2 the Tester's Must fix, round 3 passes yellow. `interrupted` is a possible review
  result in the table, but Phase 7 never writes it (an interrupted review only writes an audit event).
- **Three new rulebook policy fields:** `tester_max_prompt_chars` 60000, `tester_max_attempts` 2,
  `tester_quote_window` 2 (older versions load with these starter values).

**Phase 6 fixes batch (work test, 6 Nov 2026).** Built on the same branch before the merge.
Spec `specs/phase-6-fixes-2026-11-06.md`, plan `specs/phase-6-fixes-plan.md`.
- **Understand asks the 4 questions as one form** (4 labelled boxes plus an optional 5th, one
  **Submit**). One AI call reads the opening statement and all answers together; only then are
  the AI's clarifying questions asked, one at a time. A box that fails shows its message under it
  and keeps its text. The AI is told which decisions are made or queued, so it returns only new
  questions. The limit of AI questions is `max_material_decisions` in the rulebook policy.
  Requests saved in the middle of the old one-at-a-time questions finish the old way.
- **Typing is the correct / change / add path.** At the Understand checkpoint (**Correct
  something**), the Approach review (**Change something**) and the test plan (**Add a test
  case**) the text box is open and the Send button carries the action's name.
- **The next step starts by itself:** Discover after **Proceed with this understanding**,
  Approach after **Findings look right**. **Try again** shows only if the started step fails.
  **Build** is still pressed by the developer.
- Design-choice buttons look equal; the Discovery tab says when the index is the made-up
  practice index; the folder button is **Change folder**; there is no manual **Re-scan** before
  Build; the final build line says when the tests never ran; the Tests tab says why no test has a
  result; the chat badge follows the real write state; **Resume build** and **Cancel build**.

**Setting.** `DA_SANDBOX_SOURCE_DIR` in `.env`: the CodeVision folder (the one holding `src`) the
sandbox copies from. At home with `DA_LLM_PROVIDER=fake` leave it empty: the made-up folder under
`tests/fixtures/da_reference_codevision/` is used.

**Check it at home.**
- Tests: `.venv\Scripts\python -m pytest`. The sandbox tests start real Python processes (no AI,
  no internet). The real-browser tests are skipped on your laptop if Playwright is missing.
- Smoke check items 24 and 25 run a whole build (fake provider, real sandbox, pretend folder).
- By hand: run the screen on `http://127.0.0.1:8050` with `DA_LLM_PROVIDER=fake`, take a request
  to **READY TO BUILD**, pick the practice folder from `docs/workspace-work-test.md`, press
  **Build**, leave the page and come back, then look at the **Build** and **Tests** tabs. Check
  that your folder got the code files and **no** `tests` folder.
- At work: `docs/build-work-test.md` (questions Q14 and Q15, Command Prompt only).

**Phase 5 changes made here (section 15.1 of the spec).** The workspace check no longer writes
anything. The writer creates no folders. There is no tests-folder blocker (B7) and no "New in tests
folder" re-scan result. The ZIP and the upload hold and send code files only. A different folder
with the **same name** as the linked one is no longer silently accepted: pick it with **Change**
to link it on purpose (P26).

## How Phase 8 works

Phase 8 is **Refine**. AS400 picture: changing a program after its first compile, where your own
local fixes must survive. It starts at `b_written` (READY_FOR_REVIEW or NOT_PASSING). Spec
`specs/phase-8-refine.md`, plan `specs/phase-8-plan.md`.

- **Three lanes.** You type feedback; one AI call suggests a lane; you always pick.
  **Bug**: the Tester writes one test that must fail on today's code, you confirm it, it is appended
  as a new test set version (earlier tests untouched), and a fresh fix build writes only the traced
  file. **Requirement**: the record gets v2 (same CVDA number), Discover and Approach run again,
  only new and changed criteria get new test cases. **Approach**: a changed design, record untouched.
- **Edit protection.** **Re-scan** finds files you changed (side by side). **Check my edits** runs
  the frozen tests on your version. A rebuild is a patch: where the AI and you changed the same
  method you pick **Keep mine** or **Take the AI's**. Nothing of yours is overwritten without a pick.
  **Restore** brings back an older build (it warns about edits it would replace).
- **Versions.** Summary shows record versions with diffs, Approach lists its versions with their
  source, Tests marks cases New, Bug or Yours, Build lists builds ("Refine 2: bug").
- **Get help** is offered in every lane step. A stale window is refused on every action.
- **Findings after a revision (fix 1, F4).** When Discover has run again on the new record version
  you get the same three buttons as Phase 3: **Findings look right**, **Something's missing**
  (type a hint, same 3-round limit counted over the whole request) and **Escalate to a senior
  developer** (ESCALATION_REQUIRED, open item `Escalated in Refine: Discover`).
- **Smoke check.** Items 27 (bug lane to a fix build) and 28 (requirement lane to a revision
  approach) run with the fake provider. With the scripted fake code the fix build ends
  **Not passing** (10 of 11 tests): the script does not really fix the bug. That is expected.
- **Known gap.** The Refine box is drawn, but its click callbacks are not wired yet, so the browser
  test 8-42 (`tests/test_da_refine_e2e.py`) is written and skipped. Work test: `docs/refine-work-test.md`.

## How Phase 9 works

Phase 9 is **Enhance**: change a program that already exists (home card 2, "Change an existing
program"). AS400 picture: changing a live RPG program. First you find the member, check your copy
is the one in the production library, record what it does today, then change only the procedures
you named. Spec `specs/phase-9-enhance.md`, plan `specs/phase-9-plan.md`. No new status: the header
pill shows the step (`e_find` to `s_accepted`).

- **Find.** Name the program or describe it. A name search and a meaning search run on the Phase 3
  index (same safety filter), merged, with a **Best match** mark. Each program shows its capability
  (the rulebook's catalog); one not in it gets a pick and goes to the **Unassigned** queue.
  **This is a fix** pre-fills "Make it work as intended". Card 1 offers a switch to Enhance once
  when a program is a Best match.
- **Freshness.** The browser sends the program as it is in your folder; the server compares it with
  main (`DA_MAIN_SOURCE`: `fake` reads `DA_FAKE_MAIN_DIR`, `bitbucket` says "not configured" until
  WF-1). Equal: the text becomes the baseline. Anything else stops at `e_stale`, never a silent pass.
- **Understand** gets a today-draft (one AI call), boxes for what changes and what must NOT change
  (`NC-1`, `NC-2`...), and a functions-in-scope checkpoint.
- **Impact** is plain code (`ast`): who calls the functions in scope, in the server's reference copy.
- **Safety net.** The Tester writes tests of today's behaviour, they are proven on today's code,
  failing ones are fixed or dropped and listed as not covered. You accept the net before Approach.
- **Build** shows the Generator only the functions in scope. Two new Layer A checks: **A8** (an edit
  outside the scope) and **A9** (a locked signature changed while a caller is outside the plan).
  Tests you marked "expected to change" run once for information; a still-old result is an FYI.
- **Smoke check** items 29 (card 2 to READY_FOR_REVIEW) and 30 (the card 1 switch offer).
  The real-browser test 9-50 (`tests/test_da_enhance_e2e.py`) is skipped when no browser is found.
  Work test: `docs/enhance-work-test.md`.
- **Fixed on the way:** a Layer C check-1 FYI (an NC item "not covered") used to end the build as
  Not passing. Only a Must fix of check 1 does now.
- **Screen, as wired.** Impact card (Discovery tab), **Safety net** tab (with "After the change"
  dropdowns while you review), the read-only net in the Approach tab, the header pill, the
  functions-in-scope tick list at the checkpoint and the safety net writing in the background
  (the page redraws every 3 seconds) are all connected to their callbacks.
- **Known gaps.** There is no separate "Show other matches" button: when Find returns more than one
  program, a tick list is shown at once with the Best match ticked (same result, one click less).
  The real-browser test 9-50 is written and skipped until a browser is available.

## How Phase 11a works

Phase 11a is the first part of the **Admin console** (the `/admin` page, menu entry **Admin**).
AS400 picture: a maintenance screen for the system's control data, with a journal of every change.
Spec `specs/phase-11-admin-console.md`, plan `specs/phase-11a-plan.md`.

- **Who may open it.** `DA_ADMIN_IDS` is a comma list of user IDs (empty = nobody).
  `DA_ADMIN_SOURCE` is `env` (the default) or `codevision` (a placeholder that says no until wired).
  Anyone else sees one plain refusal line and no rulebook data.
- **Tabs.** Eight tabs. Built here: **Project charter**, **Build and test**, **Version history**.
  The others say "Comes in 11b" or "Comes in 11c".
- **Edit, Save, Cancel.** Edit turns the tab into a form (lists are tables with Add row and Remove).
  Save needs a change note and writes a new rulebook version; Cancel writes nothing. A stale save
  names the newer version; every problem is listed at once; an unchanged form says "No changes".
- **Version history.** Newest first, with the areas each version touched, the requests pinned to
  it, **What changed** between two versions (plain code, no AI) and **Restore** (a new version,
  note pre-filled "Restored from v<n>").
- **Retired fields.** `default_level`, `max_level`, `max_review_rounds` and the never-generate
  zones are gone from screens and new versions; old versions still load. Triggers are now five.
- **Model per role.** `generator_model` and `tester_model` in Build and test win over `.env` for
  requests pinned to that version (empty = use `.env`).
- **Smoke check** items 31 to 33 (form save, restore, one changed path). Not yet: Overview,
  metrics, work-test doc (11c) and the other tabs (11b).

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
- **Phase 2C files:** `agents/da_llm_client.py`, `agents/da_rejected_reply_log.py`, the settings in
  `configs/da_config.py`, `da_llm_ping.py`. `requests` 2.32.5 is the one library added to
  `requirements.txt`. For the Monday test only (decision D-E), `web/da_fake_onprem_server.py` is
  not needed at work, but `da_home_web_server.py` is copied to run the screen on the work laptop.
  Smoke check items 13 and 14 import the pretend server, so copy it too if you run the smoke check.
- **Phase 3 files:** `agents/da_discover_*.py`, `agents/da_search_index.py`,
  `agents/da_code_splitter.py`, `db_table_functions/db_tbl_da_discovery.py`,
  `pydantic_classes/da_discovery_models.py`, `data/da_discover_prompt.md`, the three Discover
  settings, and the screen edits. `data/da_fake_index.json` and `data/da_discover_fake_script.json`
  are for home. The two Discover tables use SQLite triggers (append-only), like the others.
- **Phase 4 files:** `agents/da_approach_*.py`, `agents/da_tester_agent.py`,
  `db_table_functions/db_tbl_da_approach.py`, `pydantic_classes/da_approach_models.py`,
  `layouts/da_approach_panel.py`, the three prompt files, the new policy fields in
  `da_rulebook_models.py` and the seed, the Tester settings, and the screen edits.
  `data/da_approach_fake_script.json` and `data/da_tester_fake_script.json` are for home. The
  `da_approach_versions` and `da_test_plans` tables use SQLite triggers (append-only). Phase 4
  also made `is_vague_then` in `da_understand_checks.py` public (it was private).
- **Phase 5 files:** `agents/da_workspace_flow.py`, `agents/da_workspace_checks.py`,
  `db_table_functions/db_tbl_da_workspace.py`, `pydantic_classes/da_workspace_models.py`,
  `layouts/da_workspace_panel.py`, `callbacks/screen_callbacks/da_workspace_callbacks.py`,
  `web/da_workspace.js` and `web/da_workspace_bridge.py`, the two new policy fields, and the screen
  edits. The JavaScript is read from its file at start-up and put inside the Dash callbacks, so
  CodeVision's own `assets` folder needs no change. `web/da_fake_browser_folder.py` is for home
  (tests and smoke check). The three workspace tables use SQLite triggers (append-only), like the
  others. **Check at work (Q8):** the browser's folder picker may be switched off by IT policy
  (`edge://policy`, look for "FileSystem"); the ZIP and upload fallback is the safety net.
- `dash`, `dash-mantine-components` and `dash-iconify` are in `requirements.txt` at the work
  versions. Dash pulls in Flask; home gets 3.1.3, work has 3.1.2.
- **Check at work that Dash clientside callbacks (inline JavaScript) are allowed.** Enter-to-send
  uses one; if CodeVision blocks inline scripts, Send still works by click.
