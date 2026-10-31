# Phase 2D: Understand updates

Status: APPROVED v1.0 (31 Oct 2026). Decisions D-A to D-D chosen by Gian (section 9).
Depends on: Phase 2A, 2B, 2C, P13, P19 (all on `main`). **Phase 3 must be merged into `main`
first** (both phases change the screen and its callbacks; building 2D on top avoids a messy merge).
Next: Phase 4, Approach (`specs/redesign-2026-10-31.md` section 5.3)
Build: fresh Claude Code session, Sonnet, branch `phase-2d` from `main`.

## In plain words

The work test on 30 Oct and the director review showed five small things to fix in Understand
before Approach can be built on top of it:

1. **Testable acceptance criteria.** Approach (Phase 4) asks the Tester to write one or more test
   cases per criterion, and Build tags every test with a criterion ID (AC-1, AC-2...). So the
   record needs criteria written as **Given / When / Then**, not loose "success scenarios".
2. **W3:** decision questions only allow the buttons. Add an "Other, type here" answer.
3. **W4:** the "get help from a senior" message shows twice. Our bug.
4. **W5:** the Summary panel fills everything at the first message. The demo fills it step by step.
5. **P13 Should fix:** today the reply cleaner removes `<think>` text anywhere. Parse the reply as
   it is first; clean it only if that fails.

AS400 comparison: the record is like a DDS file the later programs read. Phase 4 needs a new
field (the criteria), so we change the file layout now, before more programs depend on it.
W3 to W5 are screen fixes, like adjusting a 5250 display file without touching the business logic.

## 1. Testable acceptance criteria (D-A, D-B)

### 1.1 What a criterion is

| Part | Meaning | Example |
|---|---|---|
| ID | `AC-1`, `AC-2`... given by the app, never by the AI | AC-4 |
| Kind | `success` or `failure` | failure |
| Given | The starting situation | an empty workbook |
| When | The action | it is uploaded |
| Then | Something a person or a test can **see** | it is rejected with the standard empty-file error |

Shown as one line: **AC-4** Given an empty workbook, when it is uploaded, then it is rejected
with the standard empty-file error.

### 1.2 Record change (D-A, recommended: replace)
- New record field `acceptance_criteria`: a list of criteria, up to 12 (`LIST_LENGTH_LIMIT`).
  Each part (given, when, then) is 1 to 300 characters (`LIST_ITEM_LIMIT`).
- **Remove** `success_scenarios` and `failure_scenarios` everywhere: record model, field lists,
  labels, prompt, checks, screen, fake script, tests. The criteria replace them (the demo's
  Summary tab has "Acceptance criteria" where "Important scenarios" used to be).
- `kind` keeps the old meaning, so nothing is lost.

### 1.3 The interpreter reply
- New optional top-level key `acceptance_criteria` next to `updates`, `ambiguities` and `hint`:
  a list of `{"kind": ..., "given": ..., "when": ..., "then": ...}`. **No IDs from the AI.**
  - Key left out (or `null`): criteria unchanged.
  - A list: the full new list. It replaces the old one, the same rule as list fields today.
- IDs (D-B, recommended: renumber): while the request is a draft, the app numbers the list
  `AC-1` to `AC-n` in the order the AI gave. Once record v1 is confirmed, the IDs are frozen.
  Stable IDs across versions (v2 says "AC-8 added") arrive with revision mode in Phase 8.

### 1.4 Checks on the reply (plain code, failures go back to the AI as the retry note)
- Kind is `success` or `failure`; each part 1 to 300 characters; at most 12 criteria.
- **Then must be observable.** Refused when, after lower-casing and removing punctuation, the
  then part has fewer than 3 words or is one of: `it works`, `works`, `works correctly`,
  `it works correctly`, `works as expected`, `as expected`, `success`, `it succeeds`, `no error`,
  `ok`. Retry note: "AC-n: the 'then' part must say something a person or a test can see, for
  example a message, a saved value, or a rejected file."
- No two criteria with the same given, when and then (ignoring case and spaces).
- The existing code check and invented-name check also cover all three parts of every criterion.

### 1.5 Confirmation gate
Replace the two scenario lines with:
- "At least 1 success criterion is needed."
- "At least 1 failure criterion is needed."
Everything else in the gate stays.

### 1.6 Prompt (`src/data/da_understand_prompt.md`)
Add a short section, in the same style as today:
- Every success or failure case the developer names becomes a criterion.
- Given = the starting situation, When = the action, Then = what a person or a test can see.
- A decision that changes behaviour becomes a criterion or changes one.
- Never write IDs; the app numbers the criteria.
- Fill any field from any message (the screen decides what to show, see section 4).

### 1.7 Screen and messages
- Summary tab: section "Acceptance criteria (each one gets tested)" in place of "Important
  scenarios", placed under "Requirement summary" as in the demo. Each line as in 1.1, with the ID
  as a small badge and a small "failure" tag on failure criteria. Empty text: "Each success or
  failure case becomes a testable criterion".
- Confirmed message: add the line "Acceptance criteria: N".
- Question 4 hint (app text, not AI): "Each case you name becomes an acceptance criterion, and
  every criterion gets tested."

### 1.8 Requests saved before 2D
Saved records and sessions with the old scenario fields would no longer load. There are no real
users yet, so no conversion:
- Opening such a request shows a plain page: "Request CVDA-... was saved before the Understand
  update (2D) and cannot be opened. Please start a new request." No crash, no stack trace.
- It still appears in "My recent requests".
- Nothing is deleted. The audit trail stays.

## 2. W3: "Other, type here" on decisions (D-C)

- At a decision step the choice buttons stay, **and the text box opens** with the placeholder
  "Other, type here". The checkpoint (Proceed, Correct something, I need help deciding) stays
  buttons only.
- A typed answer goes through the same checks as any message (empty, secrets) and must be at most
  300 characters ("Please keep your own answer under 300 characters, or choose a button.").
- It is saved as the decision's choice, exactly like a button, with audit event
  `decision_recorded` and `"custom": true` in the details.
- D-C (recommended: ask the AI right away): after any decision (button or typed, not "I need help
  deciding"), the app calls the interpreter once with the decision question as the question and
  the choice as the answer, so the Summary and criteria update straight away (demo: "Noted as a
  confirmed decision, and added as criterion AC-3").
  - Same pattern as creating a request: save 1 records the decision; the AI is called with no
    database lock; save 2 applies the reply and moves on.
  - If the AI call fails: the decision stays saved. Message: "Your decision is saved. I couldn't
    update the summary from it; it will be picked up with your next answer." Then move on.
  - New material ambiguities from this reply are queued as usual and count toward the limit of 5.
  - Fake script: a new `decision` step entry (see section 6).

## 3. W4: the senior message shows once

Cause found while writing this spec (builder: prove it with a failing test first):
`_apply_result` in `agents/da_understand_flow.py` says `SENIOR_MESSAGE` when `needs_senior`
first turns on, and `_advance` says it again when it enters the `senior` step. With no pending
decisions both happen in the same turn. With pending decisions the first one appears too early.

Fix: say it only in `_advance`, only at the moment the step changes to `senior`. Remove the other.
The waiting text in the disabled text box is not a chat message and stays.

## 4. W5: the Summary fills step by step (D-D)

The record stays the memory: the AI still fills any field from any message, so nothing the
developer says early is lost (each AI call only sees the record, not the chat). **Only the screen
waits** (D-D, recommended: reveal by question).

| Shown after | Fields |
|---|---|
| Question 1 answered | objective, reason |
| Question 2 answered | current behaviour |
| Question 3 answered | expected behaviour, functional flow, in scope |
| Question 4 answered | inputs, outputs, acceptance criteria, out of scope |
| Optional step answered or skipped | constraints, references |
| Always | assumptions, decisions, open items |

- A field not yet shown says "Waiting for your answer" (as in the demo).
- At the correction step, the checkpoint and after confirmation, every field is shown (the gate
  messages name fields, so they must be visible).
- A field that becomes visible in this turn is highlighted like a changed field, even if its
  value was filled earlier.
- The rule is plain code in the flow module: `UnderstandView` gets a new `visible_fields` list,
  so it is testable without Dash. The page only reads it.
- The request title in the header keeps updating as today.

## 5. P13 Should fix: parse as-is first

In `agents/da_understand_agent.py` `parse_reply`:
1. Trim the text, remove a whole-reply ```` ```json ```` fence (as today), parse.
2. Only if that fails: remove a **leading** think block (optional spaces, `<think>`, up to the
   **first** `</think>`), or, with no opening tag, everything up to the **first** `</think>`.
   Then fence and parse again.
3. Never remove think text from inside or after the JSON.
- The rejected-reply log still keeps the full raw reply.
- `strip_think_block` changes to match (non-greedy, first closing tag). Mark the P13 Should fix
  done in the handoff note's open items via Gian.

## 6. Fake script and smoke check
- `src/data/da_understand_fake_script.json`: replace the scenario lists in `question_4` with the
  demo's criteria AC-1, AC-2 and AC-4 to AC-7 (6 criteria, made-up Excel example), and add a
  `decision` entry that adds the hidden-sheet criterion and puts hidden sheets out of scope
  (7 criteria at the checkpoint, matching the demo).
- Smoke check: update the Understand items so a full fake run reaches CONFIRMED_FOR_DISCOVERY
  with 7 criteria. Add an item for W5 (after question 1 only objective and reason are visible).

## 7. Out of scope
- Revision mode, enhancement mode, short mode for Review my code (later phases).
- Stable criterion IDs across versions (Phase 8).
- W1 and W2 (Llama behaviour). Qwen is the Generator; the Tester bake-off decides Llama's role.
- Discover changes (tag results with the record version). Separate, small, after Phase 3 merges.
- Any change to the status list or the database tables (the record is stored as JSON already).

## 8. Done when (each one is a test, Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| 2D-1 | a reply with 3 valid criteria | it is applied | the record has AC-1 to AC-3 in that order |
| 2D-2 | a reply with a criterion whose then part is "it works" | it is checked | it is refused with the AC-n retry note and retried once |
| 2D-3 | a reply without the `acceptance_criteria` key | it is applied | the criteria are unchanged |
| 2D-4 | a record with only success criteria | the gate runs | "At least 1 failure criterion is needed." is listed |
| 2D-5 | a saved session with `success_scenarios` | the request is opened | the plain "saved before 2D" page shows, no error |
| 2D-6 | a decision step | the developer types "Only the first sheet" | it is saved as the choice, audit has `"custom": true`, the AI is called once |
| 2D-7 | a decision step | the developer types 301 characters | it is refused with the 300-character message, nothing saved |
| 2D-8 | a decision was saved and the AI call fails | the turn ends | the decision is kept and the "will be picked up" message shows |
| 2D-9 | a reply that pushes the 6th material ambiguity, nothing pending | the turn ends | the senior message is in the chat exactly once |
| 2D-10 | the same, with 2 decisions still pending | the developer answers both | the senior message appears once, after the last decision |
| 2D-11 | the opening message fills every field | question 1 is asked | `visible_fields` holds only the "always" fields |
| 2D-12 | question 1 answered | the view is built | objective and reason are visible and highlighted, current behaviour is not |
| 2D-13 | a valid JSON reply whose hint contains the text `</think>` | it is parsed | it parses on the first try and the hint keeps the text |
| 2D-14 | a reply wrapped in a think block, and one with only a closing tag | they are parsed | both parse; the log keeps the raw text |
| 2D-15 | `DA_LLM_PROVIDER=fake` | a full run is made | CONFIRMED_FOR_DISCOVERY with 7 criteria; smoke check passes |

Plus: `pytest` 0 failures, `ruff check` 0 problems, smoke check passes, code reviewer 0 Must fix,
and a browser check at home that the Summary fills step by step and "Other, type here" works.

## 9. Decisions (chosen by Gian, 31 Oct 2026: option 1 for all four)

| # | Question | Options | Chosen |
|---|---|---|---|
| D-A | Criteria and the old scenario lists | 1. Criteria replace them. 2. Keep both | **1**: one source of truth; the AI never has to keep two lists in step |
| D-B | Criterion IDs while drafting | 1. Renumber AC-1..n until confirmed. 2. Stable IDs from now, AI must quote them | **1**: simpler and safer with our models; stable IDs come with revision mode |
| D-C | When a decision updates the Summary | 1. AI call right after the decision. 2. Wait for the next answer | **1**: otherwise a decision followed by Skip never reaches the criteria. Costs 10 to 20 s per decision with Qwen |
| D-D | W5 step-by-step Summary | 1. Screen reveals by question, AI still fills everything. 2. AI may only fill the current question's fields. 3. Leave it | **1**: option 2 loses early details, because the record is the only memory |

## 10. Files the builder will touch (for planning, not a limit)
`pydantic_classes/da_request_record_models.py`, `agents/da_understand_checks.py`,
`agents/da_understand_agent.py`, `agents/da_understand_flow.py`,
`data/da_understand_prompt.md`, `data/da_understand_fake_script.json`,
`layouts/da_developer_assistant_page.py`, the page callbacks, `web/da_web_components.py`,
`db_table_functions/db_tbl_da_understand.py` (old-record handling), `da_smoke_check.py`, and the
matching tests.
