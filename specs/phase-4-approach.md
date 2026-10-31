# Phase 4: Approach

Status: APPROVED v1.0 (31 Oct 2026). Decisions D-A, D-C, D-D, D-E chosen by Gian (section 14).
Defaults D-B, D-F, D-G (section 15) were set by Claude and not objected to.
Depends on: Phase 2D (criteria with AC IDs, the "choices plus Other, type here" control, the
asterisk for negative scenarios) and Phase 3 (a confirmed Discover round). **Both must be merged
into `main` first.**
Next: Phase 5, Workspace (`specs/redesign-2026-10-31.md` section 5.6)
Source of truth for the design: `specs/redesign-2026-10-31.md` section 5.3.
Visual reference: `docs/CodeVision_Developer_Assistant_Demo.html`. Read only the chat script entries
`/*21*/` to `/*28*/` (in the `MAIN` list) and the function `tabApproach` (it draws the Approach tab).
Build: fresh Claude Code session, Sonnet, branch `phase-4`.

## In plain words

After Discover the app knows WHAT the developer wants (the record) and WHAT already exists (the
Discover findings). Approach answers HOW it will be built, and HOW it will be tested, before a single
line of code is written. The developer agrees to both in plain language. Only then does the request
become READY_TO_BUILD.

Two AI roles do separate jobs, in separate calls:
1. The **Generator** proposes the plan: which files to create or change, what to reuse from Discover,
   which design choices need the developer, which libraries it will use.
2. The **Tester** writes the test plan from the acceptance criteria. It never sees the file plan or
   any code. Its test plan is what the code will later be judged by, so it must not be shaped by the
   code.

The app checks the plan with plain code (folders, names, protected files, libraries, limits). The AI
suggests, the app decides, the developer approves. Same rule as Understand and Discover.

AS400 comparison: this is the program change form signed off before anyone touches the source: the
list of objects to create or change, which existing objects are reused, and the test script written
by QA, not by the programmer. Protected files are objects in a production library that your profile
may not change (like `*PUBLIC *EXCLUDE`). Flag-for-review zones are changes that need a second
person's sign-off (dual control).

## Words used in this spec

| Word | Meaning |
|---|---|
| Approach | The plan: file plan, reuse decisions, design choices, libraries. It has its own version number (v1, v2...), separate from the request record's version |
| File plan | The list of code files to create or change, each with a reason |
| Reuse decision | For each existing piece Discover found: reuse it, extend it, or ignore it, with a reason |
| Design choice | A real either-or question the developer must answer, shown as buttons (and a typed answer) |
| Test plan | Plain-language test cases, one or more per acceptance criterion, written by the Tester |
| Gate | The 4 checks that must all be true before READY_TO_BUILD |
| Protected file | A file the AI may never write, for example `.env`. If the change needs one, the plan says so as a step for a person |
| Flag-for-review zone | An area (for example Login) where touching a file makes a named senior a required reviewer at the pull request. It never blocks |
| Pattern | A file path with `*` standing for any text, for example `*login*`. It is matched against the whole lower-case path with `/` slashes (standard library `fnmatch`) |

## 1. The flow (one step at a time)

Same screen as Understand and Discover: chat on the left, tabs on the right.

| Step | Where | The developer sees | Then |
|---|---|---|---|
| start | after Discover confirms | Button **Proceed to Approach** (replaces the disabled "coming in Phase 4" button) | Generator is called once. Status becomes APPROACH_PROPOSED |
| `choices` | only if the plan has design choices | One question at a time: its option buttons, **I need help deciding**, and the text box ("Other, type here", up to 300 characters) | After the last answer, ONE more Generator call settles the plan (new version, no open choices) |
| `review` | plan has no open choices | Buttons **Accept approach**, **Change something**, **Get help** | Accept leads to `tests_pending`. Change opens the text box |
| `change` | after Change something | Text box (up to 1,000 characters) | Generator call, new approach version. Maximum 3 changes per request (rule G9); after that only Accept or Get help |
| `limit_reason` | Accept pressed with more code files than the limit (D-C) | Buttons **Change something**, **Get help**, and the text box: what is typed is the reason (10 to 300 characters) | Reason saved, approach accepted |
| `tests_pending` | approach accepted | Chat says the Tester is writing the test plan. If the Tester call failed: button **Write the test plan** | Test plan appears, step `tests` |
| `tests` | test plan written | Buttons **Accept test plan**, **Add a test case**, **Change the approach**, **Get help** | Accept runs the gate (section 6) |
| `case_text` | after Add a test case | Text box (up to 500 characters) | Tester call turns it into one case, step `case_check` |
| `case_check` | a draft case is shown | Buttons **Keep this case**, **Discard it** | Back to `tests` |
| done | all 4 gate checks true | Status READY_TO_BUILD. Disabled button **Choose workspace folder (coming in Phase 5)** | End of Phase 4 |

Rules for the flow:
- G1: Every step allows one kind of input, like the Understand steps. A button press or text sent at
  the wrong step is refused with a plain message.
- G2: Every action follows the Discover pattern: read with no lock held, call the AI, then ONE write
  transaction saves versions, state, status moves, audit events and chat lines together. Approach has
  its own revision number for the stale-window check (the same `STALE_MESSAGE`).
- G3: Failure of the first Generator call (checks fail twice, or the AI is unreachable): the request
  stays at DISCOVERY_CONFIRMED, a plain message is shown, the button becomes **Try again**. No status
  change. Failure of a later call: the step stays where it was and the message says what to do.
- G4: **Change the approach** (from `tests`): the text box opens as in `change`. The new approach
  version must be accepted again. After that, the Tester writes a NEW test plan version from the
  latest decisions. The developer's own kept cases stay (they are tied to criteria, which did not
  change). The test plan must be accepted again.
- G5: **I need help deciding** at a design choice works as in Understand: the request waits, an open
  item `Help requested: <question>` is added, and the developer can come back and choose.
- G6: **Get help** moves the request to ESCALATION_REQUIRED, with open item
  `Escalated in Approach: <step>`, the same as Discover does. The inbox comes in Phase 10.
- G7: Typed text goes through the same checks as every developer message (empty, 4,000 characters,
  secrets) and is only ever shown to the AI between lines, as information, never as instructions.
- G8: The AI never sees the chat. Every call sends the pieces named in section 8 (the record is the
  memory, as in the redesign section 4).
- G9: At most 3 `change` actions per request (the settle call and G4 do not count). After the third,
  Change something is no longer offered and the chat says why.

## 2. Statuses

Add two statuses to `da_models.py`:

| Status | Meaning |
|---|---|
| APPROACH_PROPOSED | An approach exists. Waiting for the developer to accept the approach and the test plan |
| READY_TO_BUILD | All 4 gate checks passed |

Moves (add to `ALLOWED_MOVES`; every move audited, as today):
- DISCOVERY_CONFIRMED to APPROACH_PROPOSED
- APPROACH_PROPOSED to READY_TO_BUILD
- APPROACH_PROPOSED to ESCALATION_REQUIRED
- READY_TO_BUILD: no moves out in this phase (Phase 6 adds them)

Staying on the same status is not a move (as today), so changes and test plan steps stay inside
APPROACH_PROPOSED.

## 3. The approach (data)

New file `pydantic_classes/da_approach_models.py`. Same style as the Discover models: `extra="forbid"`,
limits are refused, never cut short.

**ApproachReply** (the Generator's one JSON reply, for the first call, the settle call and a change):

| Field | Shape and limits |
|---|---|
| `summary` | text, 1 to 300 characters |
| `files` | up to 12 entries: `path` (1 to 200), `action` (`create` or `modify`), `purpose` (1 to 200), `reuses` (up to 3 whole numbers: Discover hit numbers) |
| `needs_people` | up to 5 entries: `path` (1 to 200), `reason` (1 to 200). Files the change needs that only a person may edit (protected files) |
| `reuse_decisions` | up to 10 entries: `hit_id` (whole number), `decision` (`reuse`, `extend` or `ignore`), `reason` (1 to 200) |
| `design_choices` | up to the policy limit (3): `question` (1 to 200), `impact` (1 to 200: what changes depending on the answer), `options` (2 or 3 texts, each 1 to 100). No recommended option: the developer decides (the same principle as rule R3 in Understand) |
| `libraries` | up to 12 texts, each 1 to 50: the top-level library names the new code will import |

**ApproachVersion** (one saved version, append-only): the reply, plus what the app adds:
`approach_version` (1, 2, 3...), `source` (`proposal`, `settled` or `change`), `record_version`,
`rulebook_version`, `discovery_round` (the round number it was built from), `decisions` (the
developer's answers so far: question, choice, custom or not, decided_at), `warnings` (computed by the
app, see section 4), `zones_touched` (computed by the app), `model`, `created_at`.

The AI never fills `zones_touched` or `warnings`. The app computes them.

Test file row: the app adds one fixed line to the file plan on screen: `tests/<request id in lower
case with _>/` ("written by the Tester, frozen, in Phase 6"). It is not in `files` and does not count
toward the file limit.

## 4. App checks on the Generator's reply (plain code)

Every check returns plain sentences. All problems go back to the Generator as the retry note (once,
`MAX_ATTEMPTS` 2, as in Understand). Still failing: the call fails (G3).

Checks that REFUSE the reply:
1. **Paths:** relative, no `..`, no drive letter, no leading `/`. Backslashes are turned into `/`.
2. **Allowed folders:** a path must start with one of the policy's `allowed_folders`.
3. **No tests in the plan:** a path starting with `tests/` is refused ("Tests are written by the
   Tester, not planned here").
4. **Protected files:** a path in `files` that matches a `protected_files` pattern is refused with
   "<path> is protected. List it under needs_people with the reason instead."
5. **Naming:** for `create`, the file name must match the policy's `new_file_name_pattern`.
6. **Duplicates:** the same path twice is refused.
7. **Reuse numbers:** every `reuses` and `hit_id` must be a hit of the confirmed Discover round.
8. **Reuse coverage:** every hit cited by a finding of kind `existing_capability` or
   `similar_implementation` in that round needs exactly one reuse decision.
9. **Libraries:** each name must be in the Python standard library (`sys.stdlib_module_names`) or in
   the policy's `approved_libraries`. Names are compared lower case, with `-` and `_` treated alike.
10. **Design choices:** no more than the policy limit; no two with the same question; none that was
    already answered. On the settle call the reply must have **no** design choices.
11. **Text:** the existing code check (no code fences or code lines) on every text field.

Checks that WARN (saved in `warnings`, shown in the Approach tab, never refuse):
- **Not seen in Discover:** a `modify` path that is not the source path of any hit in the confirmed
  round: "Not found in Discover. It will be checked against your workspace in Phase 5."
- **Too many files:** more `files` than the policy's `max_files` (D-C): "N code files; the limit is M.
  Splitting the request is safer."
- **Needs a person:** each `needs_people` entry: "A person must change <path>: <reason>."
- **Flag-for-review zones:** each zone whose `path_patterns` match any path in `files` is put in
  `zones_touched`, with the warning "Touches <zone>. A named senior becomes a required reviewer at
  the pull request." This is computed by the app (D-E).

`needs_people` entries are carried to Handoff (Phase 10) as "steps for you after the build". They do
not block the gate.

## 5. The test plan (Tester)

**TestPlanReply** (the Tester's JSON for the first plan and for a new plan after G4):
`cases`: 1 to 30 entries, each `criterion_id` (like `AC-4`), `given` (1 to 300), `expect` (1 to 300).
No IDs from the AI: the app numbers the cases T-1, T-2... in the order given, and keeps a case's
number for the rest of the request.

**TestCase** (saved): `test_id`, `criterion_id`, `given`, `expect`, `source` (`tester` or `developer`).

Checks (refuse and retry, once):
1. Every `criterion_id` is a criterion of the confirmed record.
2. **Every criterion has at least one case** ("AC-4 has no test case").
3. No more than 3 Tester cases per criterion.
4. `expect` must say something a person or a test can see: the same rule as the "then" part of a
   criterion in 2D (fewer than 3 words, or `it works` and the like, is refused).
5. No code (existing code check). No file, function or dotted names the developer never typed (the
   existing invented-name check, using everything the developer has typed on this request).

**Add a test case** (A2): the developer types a case in plain words. A Tester call returns ONE draft
case `{"case": {criterion_id, given, expect}}`, or `{"case": null, "note": "<why>"}` when it fits no
criterion. The same checks apply. A draft is shown in chat and in the tab, highlighted, and is saved
only when the developer presses **Keep this case** (then `source` is `developer`, shown as "Yours").
**Discard it** saves nothing.
- A case that fits no criterion is refused with: "This does not match any acceptance criterion. If it
  is a new requirement, the requirement has to change first (a later phase)."
- At most 5 developer cases per request.

Test plan versions are append-only (`plan_version` 1, 2...). Every kept case, and every new Tester
plan after G4, makes a new plan version. A plan version records the `approach_version` it was written
for.

## 6. The gate (4 checks, recomputed from saved data every time)

| # | Check | True when |
|---|---|---|
| 1 | Request confirmed | the latest approach was built from the latest confirmed record version |
| 2 | Discover done | the latest approach was built from the latest saved Discover round, and that round was confirmed |
| 3 | Approach confirmed | the accepted approach version is the latest approach version |
| 4 | Test plan accepted | the accepted test plan version is the latest one, it was written for the accepted approach version, and every criterion has a case |

All four true: status READY_TO_BUILD and audit event `gate_passed`. If any is false when the
developer presses **Accept test plan**, the chat lists every false check in plain words and the
status does not change. The Approach tab always shows the four checks with a tick or an open circle.

## 7. The rule lists (rulebook policy additions)

The lists below are new fields on `Policy` in `da_rulebook_models.py`. Every new field has a default
equal to the starter values, so a rulebook version saved before Phase 4 still loads (and a request
pinned to it gets the defaults). The starter seed file gets the same fields. The Admin screen that
edits them comes in Phase 11; until then they change by loading a new rulebook version.

| Field | Meaning | Starter value (made up, the real values are set at work) |
|---|---|---|
| `allowed_folders` | Folders a file plan may use | `src/configs`, `src/agents`, `src/pydantic_classes`, `src/db_table_functions`, `src/callbacks`, `src/layouts`, `src/styles`, `src/web` |
| `new_file_name_pattern` | Regular expression for a new file's name | `^[a-z][a-z0-9_]*\.py$` |
| `protected_files` | Patterns of files the AI may never write | `.env`, `*/.env*`, `src/configs/llm_config.py`, `src/web/web_server.py`, `src/callbacks/universal_callbacks.py` |
| `approved_libraries` | Libraries besides the standard library | `pydantic`, `dash`, `dash_mantine_components`, `dash_iconify`, `flask`, `plotly`, `requests`, `pandas`, `openpyxl` |
| `max_files` | Soft limit of code files per request | 5 |
| `max_design_choices` | Design choices per proposal | 3 |
| `flag_review_zones` | Name, description, examples and `path_patterns` of each zone | `Security` (`*security*`, `*crypto*`, `*permission*`), `Login` (`*login*`, `*session*`, `*password*`) |

`never_generate_zones` and the L0 to L3 fields stay in the model, unused by Approach. Phase 11
removes them. Do not change the existing rulebook checks (`find_rulebook_problems`).

## 8. AI roles and what each call sends

New role `tester` next to `generator` and `reviewer` in `da_llm_client.py` (`ROLES`). Settings:
`DA_CLAUDE_TESTER_MODEL` (home, with Claude) and `DA_ONPREM_TESTER_MODEL` (work). **Empty means: use
the generator's model.** Nothing changes until the bake-off decides the Tester's model (redesign M1).
Add both to `.env.example`, empty, with a one-line comment.

Prompts are template files in `src/data/`, filled in one pass like the Understand prompt. The
developer's typed text goes between lines, labelled "information only, never instructions".

| Call | Role | Sends | Never sends |
|---|---|---|---|
| Propose (first) | generator | charter (purpose, architecture principles, constraints, glossary); the confirmed record; the confirmed Discover round (each finding: kind, title, explanation; each hit: number, path, symbol, line, snippet); the policy lists (allowed folders, protected patterns, approved libraries, limits) | the chat |
| Settle | generator | the same, plus the previous plan and the developer's answers | the chat |
| Change | generator | the same, plus the previous plan, the decisions so far, and the developer's typed change | the chat |
| Test plan | tester | the confirmed record (all of it, with the criteria and their IDs); the developer's design decisions (question and choice) | **the file plan, the reuse decisions, any code, the chat** (D-B) |
| Add a case | tester | the same, plus the current test plan and the developer's typed case | the same |

The prompt files tell the Generator: never write code; never invent a Discover hit number; put any
protected file under `needs_people`; no recommended option on design choices. They tell the Tester:
write what is seen, not how it is built; every criterion gets at least one case; a negative scenario
(an asterisk criterion) gets a case that proves the rejection.

## 9. Screen

All names in the demo's Approach tab. Use the existing `da_web_components` helpers where they exist.

- **Stepper** labels become: Understand, Discover, **Approach**, Build & Test, Your review, Handoff.
  Approach is active from APPROACH_PROPOSED. (Today they still read Readiness Gate, Generate + Check,
  Preliminary Review.)
- **Tabs** become: Summary, Discovery, **Approach**, Build, Tests, Audit. Approach replaces Gate. Code
  and Review go away. Build, Tests and Audit stay greyed out (Phases 6, 7 and 11 or later). The
  header chip "NO CODE IS GENERATED IN PHASE 1" is wrong for the redesign: change it to
  "NO CODE IS WRITTEN YET".
- **Approach tab**, top to bottom:
  1. A one-line header: "Approach v2, built from request v1 and Discovery round 2". A banner "Draft:
     may change after your choices" while choices are open.
  2. **File plan** table: File, Action (New / Change), Why, and a small note for reuse and for a
     warning on that row. The fixed tests line underneath. A footer: "N code files, limit M".
  3. **Reuse decisions** table: what was found (title, path and symbol), the decision, the reason.
  4. **Design decisions**: each answered question and the choice. A custom answer is marked.
  5. **Libraries and zones**: libraries as chips, then the warnings (zones touched, needs a person,
     not found in Discover, too many files) as a short list.
  6. **Test plan** table (after it exists): Test, Criterion (the AC badge, with the asterisk of 2D for a
     negative scenario), Given, Expect, a "Yours" tag on developer cases. A line: "9 cases cover 7 of
     7 criteria". A draft case is highlighted until kept or discarded.
  7. The **4 gate checks**, ticked or open. When READY_TO_BUILD, a green line "READY TO BUILD".
- The Discovery tab's disabled "Proceed to Readiness Gate" button becomes the active **Proceed to
  Approach**. Before Discover is confirmed it stays hidden or disabled as today.
- The composer follows the 2D control: text only, buttons only, or buttons plus text, depending on
  the step in section 1.
- "My recent requests" reopens a request at the same step (state is saved every turn).

## 10. Storage

New file `db_table_functions/db_tbl_da_approach.py`, same style as `db_tbl_da_discovery.py`. Three new
tables, created with `CREATE TABLE IF NOT EXISTS`. Nothing in the existing tables changes.

| Table | Holds | Rule |
|---|---|---|
| `da_approach_versions` | one row per approach version: request ID, approach version, source, record version, rulebook version, discovery round, plan JSON, decisions JSON, warnings JSON, zones JSON, model, created time | append-only, key (request ID, approach version) |
| `da_test_plans` | one row per plan version: request ID, plan version, approach version, cases JSON, source of change, model, created time | append-only, key (request ID, plan version) |
| `da_approach_state` | the working state: step, own revision, pending design choices, decisions, accepted approach version, accepted plan version, change count, help flag, file limit reason, a draft case | one row per request, revision goes up by 1 with every save |

Audit events (actor in brackets): `approach_proposed` (llm), `approach_failed` (system),
`design_choice_recorded` (developer, with `custom` true or false), `approach_settled` (llm),
`approach_change_requested` (developer), `approach_changed` (llm), `file_limit_overridden`
(developer, with the reason), `approach_accepted` (developer), `test_plan_written` (llm),
`test_case_drafted` (llm), `test_case_kept` and `test_case_discarded` (developer),
`test_plan_accepted` (developer), `gate_passed` (system), `help_requested` (developer), `escalated`
(developer). Every status move is audited, as today.

## 11. Fake script, pretend server, smoke check

- New scripted replies for `DA_LLM_PROVIDER=fake`, on the Excel example from the demo: `propose` (the
  2-file plan, 2 reuse decisions, the design choice "Where does Excel upload live?" with 2 options),
  `settle`, `change`, `test_plan` (9 cases over 7 criteria, T-6 added by the developer in the demo),
  `test_case`. They follow the same rules as `da_understand_fake_script.json`: ignore what was typed,
  reuse an entry when a step repeats.
- **The pretend work server (`da_fake_onprem_server.py`) must answer all the new prompts too.** In 2D
  the builder had to add this by itself, so it is in this spec on purpose. A full run with
  `DA_LLM_PROVIDER=onprem` against the pretend server must reach READY_TO_BUILD.
- Smoke check: add items that run a full fake request from DISCOVERY_CONFIRMED to READY_TO_BUILD, and
  prove the Tester's prompt contains the criteria and not the file plan.

## 12. Out of scope

- Choosing the workspace folder, writing or reading any file (Phase 5).
- Writing code or the `unittest` code of the tests, the layers, the sandbox, the rounds (Phase 6).
- The Tester's review of the finished code and the report (Phase 7).
- Requirement revision, new record versions, edit protection (Phase 8). In Phase 4 a change to the
  requirement itself means starting over from Understand.
- Enhancement mode, freshness check against `main`, safety-net tests (Phase 9).
- Admin screens for the rule lists, removing the L0 to L3 and never-generate fields (Phase 11).
- The escalation inbox (Phase 10). The Tester bake-off, and W1 and W2 (Llama behaviour).

## 13. Done when (every line becomes a test, Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| 4-1 | a request at DISCOVERY_CONFIRMED with record v1 and a confirmed round | Proceed to Approach is pressed | approach v1 is saved with the record version and round number; status is APPROACH_PROPOSED; audit has `approach_proposed` |
| 4-2 | the first Generator call fails twice | the action ends | status stays DISCOVERY_CONFIRMED, a plain message shows, the button reads Try again |
| 4-3 | a reply with a path `../x.py`, or an absolute path, or `src/other/x.py` | it is checked | each is refused with its own note and the reply is retried once |
| 4-4 | a reply with a path under `tests/`, and one with `src/web/web_server.py` | it is checked | both are refused (4-4a: tests are the Tester's; 4-4b: protected) |
| 4-5 | a new file named `Upload Excel.py` | it is checked | refused by the naming rule; `excel_processor.py` passes |
| 4-6 | a reply citing Discover hit 9 that does not exist | it is checked | refused |
| 4-7 | a round whose findings cite hits 1 and 2 as existing capabilities, and a reply that decides only hit 1 | it is checked | refused: hit 2 needs a decision |
| 4-8 | libraries `openpyxl`, `json`, `evilkit` | they are checked | `openpyxl` and `json` pass, `evilkit` is refused |
| 4-9 | a plan that modifies a path no Discover hit has | it is saved | a "Not found in Discover" warning is stored; the plan is accepted by the checks |
| 4-10 | a plan with a file under `src/layouts/login_page.py` | it is saved | zone Login is in `zones_touched` and the warning shows; status is unchanged |
| 4-11 | a reply that lists `src/web/web_server.py` under `needs_people` | it is saved | the warning "A person must change..." is stored and the gate is not blocked |
| 4-12 | a proposal with 2 design choices | the developer answers the first by button and the second by typing 150 characters | one question is asked at a time; after the second answer ONE settle call is made; version 2 has no choices and version 1 is still stored |
| 4-13 | a typed design answer of 301 characters | it is sent | refused with the 300-character message, nothing saved |
| 4-14 | a settle reply that contains a design choice | it is checked | refused |
| 4-15 | a design choice | I need help deciding is pressed | the request waits with the open item; choosing later clears it |
| 4-16 | a plan at `review` | Change something and a typed change are sent | a new version is saved; the old one is kept; after 3 changes the button is gone and the chat says why |
| 4-17 | a plan with 6 code files and `max_files` 5 | Accept approach is pressed | step `limit_reason`; a 5-character reason is refused; a 12-character reason accepts and audit has `file_limit_overridden` |
| 4-18 | an accepted approach | the Tester is called | its prompt holds the record, the criteria with IDs and the design decisions, and holds no file plan, no reuse decisions and no chat |
| 4-19 | a Tester reply with no case for AC-4 | it is checked | refused: "AC-4 has no test case"; retried once |
| 4-20 | a Tester case whose expect is "it works" | it is checked | refused |
| 4-21 | a valid Tester reply of 9 cases | it is saved | cases are numbered T-1 to T-9 by the app; plan version 1 records the approach version |
| 4-22 | the developer types a case that fits AC-3 | the draft is shown and Keep this case is pressed | the case is saved as the next T-number with source `developer` and shows "Yours"; Discard it saves nothing |
| 4-23 | a typed case that fits no criterion, and a sixth developer case | each is sent | each is refused with its own message |
| 4-24 | a test plan exists | Change the approach is used and the new approach is accepted | a new Tester plan is written, the developer's cases are kept, and the plan must be accepted again |
| 4-25 | all four checks are true | Accept test plan is pressed | status READY_TO_BUILD; audit has `gate_passed`; the Build button is disabled with the Phase 5 text |
| 4-26 | the accepted test plan belongs to an older approach version | Accept test plan is pressed | the false check is named in plain words and the status does not change |
| 4-27 | a rulebook version saved before Phase 4 | it is loaded | it loads, and the new fields hold the starter values |
| 4-28 | any Approach action | it is sent with an old revision | refused with the stale message |
| 4-29 | `DA_LLM_PROVIDER=fake`, and again `onprem` against the pretend server | a full request runs from DISCOVERY_CONFIRMED | it reaches READY_TO_BUILD both times; the smoke check passes |
| 4-30 | a request in any Approach step | the screen is drawn | the stepper and tabs use the new names, Approach is active, Build, Tests and Audit are greyed, the chip says "NO CODE IS WRITTEN YET" |
| 4-31 | a test plan with a negative-scenario criterion | the tab is drawn | the criterion shows its AC badge with the asterisk of 2D |

Plus: `pytest` 0 failures, `ruff check` 0 problems, smoke check passes, code reviewer 0 Must fix, and a
browser check at home that a full request reaches READY_TO_BUILD with the fake provider.

## 14. Decisions (chosen by Gian, 31 Oct 2026: option 1 for all four)

| # | Question | Options | Chosen |
|---|---|---|---|
| D-A | Where the new rule lists live (allowed folders, protected files, approved libraries, limits, zones) | 1. Rulebook policy (versioned, pinned per request, audited). 2. A separate settings file | **1**: the Admin console of Phase 11 already edits the rulebook, and a request keeps the rules it started with |
| D-C | More code files than the limit of 5 | 1. Soft: a warning, and Accept anyway with a typed reason that is audited and shown at handoff. 2. Hard: Accept is not possible | **1**: Phase 4 has no "split the request" feature, so a hard block would leave the developer stuck. The reason trail does the job |
| D-D | When the Tester writes the test plan | 1. After the developer accepts the approach. 2. Automatically as soon as the design choices are answered (as the demo shows) | **1**: fewer wasted Tester calls if the plan changes, and one click is clearer |
| D-E | How a flag-for-review zone is detected | 1. Path patterns per zone, matched by plain code. 2. The AI judges | **1**: predictable, testable, and never changes between runs |

## 15. Defaults I chose (tell me if you disagree)

| # | Choice | Why |
|---|---|---|
| D-B | The Tester sees the record and the design decisions, but not the file plan | The test plan is judged against the code later. If the Tester saw the plan, it could write tests that fit the plan instead of the requirement |
| D-F | The file limit counts code files only, not the test file | The Generator writes one file per AI call in Phase 6, and the tests are written by the Tester. The demo's "3 files" line becomes "2 code files plus 1 test file" |
| D-G | A change to the requirement during Approach means starting over from Understand | Revision mode (record v2, same CVDA number) is Phase 8 |

## 16. Files the builder will touch (for planning, not a limit)

`pydantic_classes/da_models.py` (statuses and moves), `da_approach_models.py` (new),
`da_rulebook_models.py` and `data/da_rulebook_seed.json` (policy fields), `da_llm_client.py` and
`configs/da_config.py` (tester role and settings), `agents/da_approach_agent.py`,
`da_tester_agent.py`, `da_approach_checks.py`, `da_approach_flow.py` (all new),
`db_table_functions/db_tbl_da_approach.py` (new), prompts `data/da_approach_prompt.md`,
`da_test_plan_prompt.md`, `da_test_case_prompt.md` (new), fake scripts for approach and Tester (new),
`web/da_fake_onprem_server.py`, `layouts/da_developer_assistant_page.py`, the page callbacks,
`web/da_web_components.py` (stepper), `da_smoke_check.py`, `.env.example`, `README.md`, `CLAUDE.md`
("Current phase"), and the matching tests.
