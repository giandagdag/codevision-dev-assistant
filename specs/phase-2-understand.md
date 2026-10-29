# Phase 2: Understand

Status: APPROVED v1.0 (25 Oct 2026). Decisions D-A to D-H all approved as recommended.
Depends on: Phase 0, Phase 1
Next phase: Phase 3, Discover

## In plain words

The developer describes a change in plain words. The assistant asks 4 short questions, fills a
live summary panel as they answer, stops to ask whenever something important is unclear, and ends
with a confirmed, versioned request record. That record, not the raw chat, drives every later phase.
No code is written or shown in this phase. This is also the first phase with a screen.

AS400 comparison: a 5250 interactive program with a display file. The screen asks, the program
checks the fields and shows a message when something is wrong, and when a decision is needed only
the valid function keys work (like a screen where only F3 and F12 are allowed). One difference:
the web calls our program fresh on every Enter, so the conversation is saved in a work file between
screens, and a page reload or a lunch break loses nothing. Confirming writes the final record once
to a journaled file that can never be changed.

Naming note: on screen, Understand is step 1 of the developer's 6 steps (as in the demo).
In this build plan it is Phase 2. The screen always uses the developer's numbering.

## 1. Goal

- A developer can start a change request, answer 4 mandatory questions and 1 optional area,
  and see the summary panel fill in after every answer.
- Material ambiguity is always asked, never assumed. Minor ambiguity is resolved and labelled.
- The developer confirms the summary. It is saved as record v1 with status CONFIRMED_FOR_DISCOVERY.
- The developer can leave and resume any unfinished request.

## 2. Two parts, built and committed separately (see decision D-A)

| Part | What | Has a screen? | Needs Q6 photos? |
|---|---|---|---|
| 2A Engine | Statuses, conversation flow, interpreter, checks, storage, loader, smoke check | No | No |
| 2B Screen | Home page, chat, summary panel, home web server | Yes | Only the menu photo, before moving to work |

Each part goes through its own Plan, Build, Review and Sign-off. 2B starts only after 2A is committed.

## 3. In scope

### 3.1 Statuses and moves (2A)
Statuses are stored as upper-case codes; the screen shows them with spaces (as in the demo pills).

| Status | Meaning | Can move to |
|---|---|---|
| DRAFT | Request created, no answer yet | CLARIFICATION_IN_PROGRESS |
| CLARIFICATION_IN_PROGRESS | Questions being answered | DECISION_REQUIRED, READY_FOR_CONFIRMATION |
| DECISION_REQUIRED | A material decision is waiting, or the developer asked for help | CLARIFICATION_IN_PROGRESS |
| READY_FOR_CONFIRMATION | All checks pass, waiting for the developer | CONFIRMED_FOR_DISCOVERY, CLARIFICATION_IN_PROGRESS (Correct something), DECISION_REQUIRED (Need help) |
| CONFIRMED_FOR_DISCOVERY | Record v1 saved. Final for Phase 2 | (Phase 3 adds moves) |

- Any move not in this table is refused with a plain message.
- `NEW` from Phase 0 is replaced by `DRAFT` (decision D-B). Phase 0 tests are updated to match.

### 3.2 The conversation (2A)
1. The developer's first message creates the request (title "New change request", pinned to the
   active rulebook as in Phase 1). Status DRAFT, then CLARIFICATION_IN_PROGRESS.
2. The 4 mandatory questions, always in this order (decision D-G). The question wording is fixed
   app text; the interpreter may add one short hint (up to 200 characters).

   | # | Question | Fills |
   |---|---|---|
   | 1 | What needs to change, and why? | title, objective, reason |
   | 2 | What happens today? (you don't need to know the source files) | current behaviour |
   | 3 | What should happen after the change? | expected behaviour, functional flow, in scope |
   | 4 | What are the inputs, outputs, and important success or failure cases? | inputs, outputs, success and failure scenarios, out of scope |

3. After each answer: the interpreter proposes updates, the app checks them (3.5), then saves.
4. Material ambiguity: the app asks the decisions one at a time. Text input is locked; only the
   choices are shown (2 or 3 options from the interpreter, plus "I need help deciding", always
   added by the app). The choice is saved as a decision.
5. "I need help deciding": status DECISION_REQUIRED, an open item "Help requested: ..." is added,
   and the request waits. The developer can come back later and choose. (The real senior
   escalation inbox is Phase 8.)
6. Optional area, after question 4 and all decisions: constraints, exclusions, references.
   The developer can type them or press Skip.
7. Checkpoint: if the confirmation gate passes (3.5), status READY_FOR_CONFIRMATION and 3 choices:
   - Proceed with this understanding: saves record v1, status CONFIRMED_FOR_DISCOVERY
   - Correct something: text input opens ("What should change?"), the interpreter updates the
     record, checks run again, back to the checkpoint
   - I need help deciding: as in step 5
8. After confirmation: the chat shows the saved record summary and a disabled
   "Proceed to Discovery (coming in Phase 3)" button.

### 3.3 The request record (2A)
`pydantic_classes/da_request_record_models.py`

| Field | Type | Filled by |
|---|---|---|
| request_id, version, rulebook_version | text, number, number | app |
| title | text, up to 80 characters | Q1 |
| objective, reason | text | Q1 |
| current_behaviour | text | Q2 |
| expected_behaviour | text | Q3 |
| functional_flow | list of plain-language steps | Q3, refined by Q4 |
| in_scope, out_of_scope | lists | Q3, Q4, decisions |
| inputs, outputs | text | Q4 |
| success_scenarios, failure_scenarios | lists | Q4 |
| constraints, references | lists | optional area |
| decisions | list of question, choice, decided at | material decisions |
| assumptions | list of text and basis (for example "Rulebook v1 glossary") | minor ambiguity |
| open_items | list | app |
| answered_questions | numbers 1 to 4 | app |

Limits: each text field up to 1,000 characters; each list up to 12 items of up to 300 characters.

### 3.4 The interpreter (2A)
`agents/da_understand_agent.py`. Uses `get_llm_client("generator")` (Qwen at work, decision D-D).

- Input (prompt): the current question, the developer's answer, the current record, and from the
  request's **pinned** rulebook only the charter purpose, scope lists and glossary.
  The prompt text lives in `src/data/da_understand_prompt.md`.
- Output: JSON only, checked by a Pydantic model:
  - `updates`: field name and new value, allowed fields only (3.3, excluding app-filled fields)
  - `ambiguities`: list of text, material (true or false), options (2 or 3, material only),
    assumption (minor only)
  - `hint`: optional, up to 200 characters
- Bad reply (not JSON, wrong shape, or fails a check in 3.5): retry once with a short note on what
  was wrong. If it fails again: a plain message ("I couldn't process that answer. Please try again
  or rephrase it."). Nothing in the record changes.
- `fake` provider: replies come from a made-up script, `src/data/da_understand_fake_script.json`,
  that walks the Excel example from the demo (decision D-C). It ignores what is typed, so the
  screen shows a banner "Demo mode: replies are scripted". Tests use their own stub replies.
- `onprem` provider: the plain "not configured yet" message from Phase 0, shown in the chat.
- `CLAUDE_MAX_TOKENS` goes from 1024 to 2048, so a full record reply is not cut off.

### 3.5 App checks (2A): the app decides, the interpreter only suggests
`agents/da_understand_checks.py`. Plain Python, no AI.

Checks on every interpreter reply:
- Only allowed fields, within the limits in 3.3
- No code anywhere: refuse code blocks and lines starting with `def`, `class`, `import`, `from ... import`
- No invented names in `functional_flow` and `expected_behaviour`: a file name (`*.py`), a
  function call (`name()`), or a dotted name is refused unless the developer typed it
- An item in both in scope and out of scope becomes an open item, not a silent fix
- More than 5 material decisions on one request: the rest become open items and the request goes
  to DECISION_REQUIRED ("This change has many open decisions. Please get help from a senior.")

Confirmation gate (all must pass to reach READY_FOR_CONFIRMATION):
- Questions 1 to 4 answered
- title, objective, reason, current behaviour, expected behaviour, inputs, outputs not empty
- At least 2 flow steps, 1 success scenario, 1 failure scenario
- No open items and no decision waiting
- The message lists every failed item in plain words

### 3.6 Storage (2A)
SQLite at home, all in `db_table_functions/`, same patterns as Phase 0 and 1.

| Table | What | Editable? |
|---|---|---|
| `da_understand_sessions` | The working state of each unfinished conversation (step, record so far, waiting decision), with a revision number | Yes, with stale-save protection |
| `da_chat_messages` | Every message: request, time, speaker (developer, assistant, system), text | No, append-only (triggers) |
| `da_request_records` | Confirmed record versions: request, version, record, confirmed by, confirmed at | No, append-only (triggers) |

Functions (names can change in planning):
- `create_understand_request(developer_id, first_message)`
- `submit_answer(request_id, text, base_revision)`
- `choose_option(request_id, option, base_revision)`
- `skip_optional(request_id, base_revision)`
- `confirm_request(request_id, base_revision)`: in one transaction saves record v1, sets the
  request's status and version, records the audit event, closes the session
- `get_understand_view(request_id)`: everything the screen needs (messages, record, status,
  progress text, which input mode, which fields just changed)
- `list_my_requests(developer_id)`: newest first, with title and status
- `update_request(...)`: new in `db_tbl_da_requests.py` for title, status, version and updated time

Audit events (actor in brackets): request_created (developer), question_answered (developer),
interpreter_reply (llm, with provider and model), interpreter_failed (system),
decision_asked (system), decision_recorded (developer), help_requested (developer),
assumption_added (system), correction_requested (developer), ready_for_confirmation (system),
confirmed (developer, with version).

### 3.7 One-time starter rulebook loader (2A)
`src/da_load_starter_rulebook.py`, run once: `.venv\Scripts\python src\da_load_starter_rulebook.py`
- No version in `DA_DB_PATH`: publishes the seed file as v1 and prints "Rulebook v1 published."
- A version already exists: prints "Rulebook already published (active vN). Nothing changed."
- `saved_by` is `setup-script`.

### 3.8 Setup changes (2A, do these first)
- Update "Current phase" in CLAUDE.md. In the same edit, change "Comparisons to COBOL or mainframe
  ideas are welcome" to "Comparisons to AS400 (IBM i) ideas such as RPG, CL, DDS, data areas,
  journals and 5250 screens are welcome. Do not use mainframe comparisons."
- Rewrite the README comparisons in AS400 terms (for example: settings read once at startup like a
  data area; Pydantic checks like DDS field keywords; rulebook versions like journal receivers that
  are never overwritten).
- Match the work library versions (Q3): `pydantic==2.12.5` (home has 2.14.1) and
  `python-dotenv==1.2.1` (home has 1.2.4). Re-run all tests after the change.
- `anthropic` is not installed at work. `da_llm_client.py` imports it at the top of the file, so
  at work the whole app would fail to start, even with `fake`. Move the import inside the Claude
  part so only `DA_LLM_PROVIDER=claude` needs it. Add a test that the module loads without it.
- Split `requirements.txt` into two files: `requirements.txt` (what goes to work, versions from Q3)
  and `requirements-home.txt` (adds `anthropic`, `pytest`, `ruff`).
- New `DA_DEVELOPER_ID` (default `dev-home-01`): stands in for the logged-in developer until
  CodeVision's login is connected (Q5). Added to `.env.example`.

### 3.9 Smoke check (2A, extend `da_smoke_check.py`)
After items 1 to 8, using the temporary database and the fake script:
9. The loader publishes v1, and a second run says "Nothing changed"
10. A request is created and questions 1 to 4 are answered, printing each status
11. A material decision is asked (DECISION_REQUIRED) and recorded (back to CLARIFICATION_IN_PROGRESS)
12. The request is confirmed as record v1 (CONFIRMED_FOR_DISCOVERY), and an edit to v1 is refused

### 3.10 The screen (2B)
**Visual reference:** the Understand screens of `docs/CodeVision_Developer_Assistant_Demo.html` (open it in a browser). CodeVision has no Chat page to copy, so the demo is the look to follow.
Not built from the demo: the presenter bar (Back, Next, page counter, "What this shows"),
"Envisioned" badges, and the content of the other tabs.

**CodeVision's page pattern (from the Q6 photos), which our files follow:**
- A page is `layouts/<name>_page.py` with a `layout()` function that builds and returns a list of
  components (see `upload_page.py`, `onboard_application_page.py`)
- Clicks are handled in `callbacks/screen_callbacks/<name>_page_callbacks.py` through a
  `register_<name>_page_callbacks(app)` function. Each callback is attached with
  `app.callback(Output(...), Input(...), State(...), prevent_initial_call=True)(function)`, and
  `raise PreventUpdate` is used when there is nothing to do (see `upload_page_callbacks.py`)
- One difference in ours: CodeVision defines the callback functions inside the register function.
  We define them at the top level of the file and only attach them inside it, so tests can call
  them directly. The register function looks the same from outside.
- Shared building blocks live in `web/web_components.py`. AI replies are shown as plain text in a
  bordered card (`dmc.Paper` with `dmc.Text`, see `loaders.py`)
- IDs can be dictionaries, for example `{'type': 'app-onboarding-input', 'field': 'app_code'}`

New files:
```
src/layouts/da_developer_assistant_page.py                         what is on the screen
src/callbacks/screen_callbacks/da_developer_assistant_page_callbacks.py   clicks (thin)
src/web/da_web_components.py      our own building blocks: chat bubble, stepper, panel section, pill
src/styles/da_styles.py           style dicts, cv_styles.py pattern
src/web/da_home_web_server.py     home only: a stand-in CodeVision shell
```
We build our own building blocks (decision D-H) instead of calling `web_components.py`, because
it is not available at home and has no chat parts. They use the same look (bordered cards,
medium radius and padding).

**Home page**
- Card "Start a change request" (active)
- Card "Review my code" (disabled, "Coming in a later phase")
- "My recent requests" table: request ID, title, status pill. Clicking a row resumes it.

**Request workspace** (as the demo)
- Top: the 6-step stepper (Understand highlighted), title, request ID, status pill
- Left: chat. Banner "No code is generated in Phase 1" (as in the demo). Composer in one of 4 modes:
  text, busy (waiting for the interpreter), locked choices, done
- Right: side panel, Summary tab only. Other tabs shown greyed out.
  Sections: progress bar (4 segments plus text), requirement summary, scope, inputs and outputs,
  important scenarios, functional flow, assumptions, open items, references.
  Fields changed by the last answer are highlighted. Empty fields say "Waiting for your answer".
- Progress text: "N of 4 mandatory questions answered", "Clarification required: N open items",
  "Ready for confirmation", "Confirmed and saved as version 1"
- Times shown in Singapore time

**Home web server** (`web/da_home_web_server.py`, home only, never copied to work)
- A minimal AppShell like the demo: header, a left menu (Home, Chat, Create Docs, Developer
  Assistant; only Developer Assistant works) and `dcc.Location`, so the page plugs in the same way
  it will at work. At work, CodeVision's own header and menu are used instead.
- Run: `.venv\Scripts\python src\web\da_home_web_server.py`, open http://127.0.0.1:8050

**New libraries, pinned to the work versions (Q3, checked to install on Windows with Python 3.14):**

| Library | Version | Why |
|---|---|---|
| `dash` | 3.4.0 | The web framework CodeVision uses (brings Flask 3.1.2) |
| `dash-mantine-components` | 2.5.1 | CodeVision's screen components (AppShell, cards, buttons) |
| `dash-iconify` | 0.1.2 | Icons, as CodeVision uses them |

Dash Mantine Components changes a lot between major versions, so all examples and code must be
written for version 2.5.1 specifically. `dash-bootstrap-components` (2.0.4 at work) is only added
if the Q6 photos show the page layout needs it.

## 4. Out of scope (do NOT build in Phase 2)
- Discover, Readiness Gate, generation, review, handoff (Phases 3 to 7)
- Changing a record after it is confirmed (v2 and later, Phase 3 onward)
- Review my code path and the escalation inbox (Phase 8)
- Guided templates and any Admin screen (Phase 9)
- File attachments in the chat
- Discarding a draft (decision D-E, parked as P6)
- Skipping ahead when one answer covers several questions (decision D-G, parked as P7)
- Real login and real developer IDs (Q5), real UOB fonts and colours (applied at work)
- Streaming replies word by word
- Browser-driven screen tests

## 5. Rules
- R1. No code in this phase: never generated, never shown (checks in 3.5).
- R2. The app decides, the interpreter suggests. Statuses, questions, gates and checks are app
  code. The interpreter can only propose field updates and ambiguities.
- R3. Material ambiguity is always asked, never assumed. The choices always include "I need help deciding".
- R4. Every minor assumption is shown in the panel with its basis. No silent assumptions.
- R5. Confirmed records and chat messages are append-only. The database refuses edits and deletes
  (same triggers as the audit trail).
- R6. Every status change writes an audit event in the same transaction.
- R7. Stale-save protection on sessions: a save from an old revision is refused ("This request was
  updated in another window. Reload to continue."). Nothing is written.
- R8. Secret check: a message that looks like a password, key or private key (a short fixed list of
  patterns) is refused before it is saved or sent to the interpreter. The message says why.
- R9. Developer messages up to 4,000 characters.
- R10. The interpreter only sees the charter of the request's pinned rulebook version.
- R11. Developer and interpreter text is always shown as plain text, never as HTML.
- R12. Thin callbacks: no business logic in layouts or callbacks. All logic lives in 2A code with tests.
- R13. The home web server listens on 127.0.0.1 only.
- R14. Made-up content only. All Phase 0 and Phase 1 rules still apply.

## 6. Done when

**2A Engine**
- [ ] `pytest` passes with 0 failures (Phase 0 and 1 tests included), `ruff check` reports 0 problems
- [ ] The smoke check prints items 1 to 12
- [ ] Tests prove: the full fake-script conversation reaches CONFIRMED_FOR_DISCOVERY with record v1
- [ ] Tests prove: every move not in the 3.1 table is refused
- [ ] Tests prove: a text answer is refused while a decision is waiting
- [ ] Tests prove: "I need help deciding" gives DECISION_REQUIRED, and choosing later resumes the flow
- [ ] Tests prove: a minor ambiguity becomes a labelled assumption
- [ ] Tests prove: a bad interpreter reply is retried once, then gives a plain message with the record unchanged
- [ ] Tests prove: code and invented names are refused (3.5)
- [ ] Tests prove: the confirmation gate lists every missing item
- [ ] Tests prove: record v1 and chat messages cannot be edited or deleted, even with raw SQL
- [ ] Tests prove: a stale revision is refused and nothing is written
- [ ] Tests prove: a message with a fake key is refused and not saved
- [ ] Tests prove: the prompt uses the pinned rulebook's charter after a newer version is saved
- [ ] Tests prove: the loader publishes once and then changes nothing
- [ ] All tests pass on the work versions of `pydantic` and `python-dotenv`
- [ ] Tests prove: `da_llm_client.py` loads without `anthropic` installed (fake and onprem still work)
- [ ] CLAUDE.md and README use AS400 comparisons only
- [ ] Reviewer: 0 Must fix. README gets "How Phase 2A works". Parked items updated.

**2B Screen**
- [ ] `pytest` and `ruff` still clean; layout and callback functions have basic tests
- [ ] Gian's hands-on check with the fake script: start a request, see the panel fill after each
      answer, see the chat lock on the decision, confirm, see the green pill on the home page
- [ ] Reload the page mid-conversation: everything is still there
- [ ] With `onprem`: a plain message in the chat, no crash
- [ ] Reviewer: 0 Must fix. README gets "How Phase 2B works" with the run command.

## 7. Open questions
- Q3. ANSWERED 25 Oct 2026 from the photo of the work `requirements.txt`. Versions in 3.8 and 3.10.
- Q6. ANSWERED for building 2B (folder tree, `universal_callbacks.py`, `upload_page.py`,
  `onboard_application_page.py`, `loaders.py`, `upload_page_callbacks.py`). Still needed, but
  only before the 2B screen is moved to work: the code that picks a page from the URL (search
  `pathname`) and where the side menu items are listed.
- Q1. MOSTLY ANSWERED 25 Oct 2026. CodeVision calls the models over HTTP through
  `tools/spirare.py` (`API_CALL`), with the header and body built by `tools/payload_generation.py`,
  settings in `configs/llm_config.py`, and up to 3 retries. Not needed for Phase 2. Filling the
  `onprem` provider needs photos of `API_CALL` and the chat part of `payload_generation.py`
  (proposed as a small separate step, P8).
- Q2 hint from the photo: `SQLAlchemy` and a `sqlite_sample.py` file are present. Not confirmed yet.
- Q4 hint: the code seen uses `print()`, so there may be no shared logger. Keep `da_logging.py`.
- Q5. Real developer IDs from CodeVision's login. Until then, `DA_DEVELOPER_ID`.
- Q1. On-prem Qwen. Phase 2 works with fake and claude only.

## 8. Decisions (all approved by Gian, 25 Oct 2026)

| # | Decision | Approved |
|---|---|---|
| D-A | Split into 2A Engine and 2B Screen | Yes |
| D-B | Replace `NEW` with `DRAFT` | Yes |
| D-C | Fake provider plays a scripted Excel demo | Yes |
| D-D | Interpreter uses the existing `generator` role (Qwen), no new role | Yes |
| D-E | Discard draft | Park as P6 |
| D-F | Store the chat transcript, append-only, with the secret check (R8) | Yes |
| D-G | Questions always asked in order, no skip-ahead | Yes, park skip-ahead as P7 |
| D-H | Our own building blocks in `web/da_web_components.py`, not CodeVision's `web_components.py` | Yes |

## 9. Decisions made during planning
- 25 Oct 2026: `anthropic` is never installed at work (confirmed by Gian). The Claude provider is home only.
- 25 Oct 2026: The demo's Understand screens are the visual reference (no Chat page exists to copy).
- 25 Oct 2026 (2A plan): The developer's first message is read by the interpreter (it can fill fields and gives the hint for question 1). Question 1 is then asked and only counts once the developer answers it, as in the demo.
- 25 Oct 2026 (2A plan): When the interpreter fails on an answer, the developer's message and the plain reply both stay in the chat. The record does not change.
- 25 Oct 2026 (2A plan review): Staying on the same status is not a move. A help item is cleared when the developer later chooses. "Proceed" from DECISION_REQUIRED confirms in one action, with every move audited. Request creation is two saves; if the interpreter fails, question 1 is asked without a hint.
- 26 Oct 2026 (2A build): Every status move also writes a `status_changed` audit event (from, to), so rule R6 holds for moves that have no event of their own in 3.6. Skipping the optional area writes `optional_skipped`.
