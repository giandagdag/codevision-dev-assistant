# Phase 10 plan: Handoff and Escalations inbox

Spec: `specs/phase-10-handoff-escalations.md` (D-A to D-L chosen by chief, option 1 each). Branch
`auto/phase-10`, made from the 11c branch (11c is in it, so section 13 can be built in place).
Scope: Handoff + Escalations inbox only. "Review my code" is Phase 10b and is not touched.

Pattern as in Phases 7 to 11: plain code first (testable without Dash), then the screen. Every step ends
with `pytest`, `ruff check .`, a commit and a push to `auto/phase-10`. At most 3 steps per run, then
`chief_tick.py next "builder continue Phase 10 from step K"`. Code review only after the last step
(max 3 rounds). A stop rule firing goes to `ops/state/worker_note.md`. Handoff steps come first (1 to 5)
so a run can stop cleanly after any of them.

## Design in plain words

- **No AI call of our own.** Handoff, triggers, routing and the inbox are plain code. The only prompt
  change is an optional `senior_guidance` block in four existing builders (step 9).
- **Same transaction pattern as Phase 6 B3** (decision 17): read with no lock, the browser's file read
  outside any transaction, ONE write transaction for state, rows, audit and chat; own revision numbers
  for the stale check (`STALE_MESSAGE`). New files start with `da_`.
- **Pure modules first.** `agents/da_handoff_checks.py` (H2 findings check, H4 fingerprint compare) and
  `agents/da_handoff_summary.py` (section 5) take plain data in and give plain data out, so most tests
  need no database.
- **Facts the builder confirms in step 1 by reading code (spec section 21), and writes down at the end
  of this file under "Confirmed facts":** the kinds `last_tested_kind` can hold and which per-path
  fingerprints each leaves (`da_build_files` code rows or `scanned` rows in `da_workspace_files`);
  the hand-edited marker (use an existing one if Phase 8 has it); the one Phase 4 function for the
  protected-file refusal after the G9 cap (trigger 2b hook); the column names for the PR summary lines.
- **Locked means locked.** One function `refuse_if_locked(conn, request_id)` raises the locked message at
  the top of every developer action (Refine, Build, Dispute, Accept, Re-scan write, workspace Change,
  chat). It is called from the same `_write(...)` helper style each flow already uses, found by grep in
  step 4. Reading stays open.
- **Statuses.** HANDED_OFF has no moves out. ESCALATION_REQUIRED gets moves back, but only to the stored
  `from_status` (checked in code, not in the table alone: the table lists the legal set, the escalation
  function checks the stored one).
- **Plain code never decides scope; the AI never routes.**
- **Admin numbers (section 13) are built last** (step 10). 11c is already in the branch, so no rebase.

## Steps

### Step 1: Foundations (first: update CLAUDE.md "Current phase" to Phase 10)
- CLAUDE.md "Current phase": Phase 10, spec, plan `specs/phase-10-plan.md`, branch `auto/phase-10`
  (kept under 6,000 bytes; step 10 only marks it finished).
- Statuses, actor, policy fields, tables, models:
- `da_models.py`: `STATUS_HANDED_OFF`, in `STATUSES`; `ALLOWED_MOVES[READY_FOR_REVIEW]` adds HANDED_OFF;
  `ALLOWED_MOVES[HANDED_OFF] = ()`; ESCALATION_REQUIRED moves out to every status it can come from
  (never HANDED_OFF); `Actor` gains `senior`; `Request.follows_request_id: str | None`.
- `db_tbl_da_requests.py`: nullable column `follows_request_id` added with the PRAGMA-and-ALTER pattern
  used in `_add_net_columns`; read and create paths carry it.
- `da_rulebook_models.py` and `data/da_rulebook_seed.json`: `Policy.escalation_lock_chat = True`,
  `Policy.handoff_summary_max_chars = 6000` (defaults, so older versions load, test 10-47 part 1).
- New `pydantic_classes/da_handoff_models.py` and `db_table_functions/db_tbl_da_handoff.py`:
  `da_handoff_state` (own revision) and `da_handoffs` (append-only triggers like the tester tables);
  read/save functions with the stale check. Table creation hooked in where `ensure_refine_tables` is.
- Tests: moves table (HANDED_OFF empty, nothing moves to it except from READY_FOR_REVIEW, escalation
  moves out), Phase 0 actor test updated (not loosened), old rulebook loads with defaults, stale
  revision refused, `da_handoffs` second insert for the same request refused, handoffs append-only.
- Prove: `pytest`, `ruff check .`.

### Step 2: Handoff checks (pure plain code): tests 10-2, 10-3, 10-4, 10-7, 10-9, 10-8 (compare part)
- `agents/da_handoff_checks.py`: `findings_check(review, actions, last_tested) -> list[Blocker]`
  (H2: label green or yellow, no open Must fix, each Should fix fixed or accepted/overruled, last
  tested run finished) with every blocker worded as in the spec ("F-3 (Should fix) is still open: Fix it
  or Accept, with reason."; Unable to assess names "Run the Tester review again"). `compare_fingerprints`
  (H4): per planned path `equal | changed | missing`; extra files in the folder are ignored (planned
  files only, R1). Fingerprint function is the existing Phase 5 one.
- `get_last_tested_fingerprints(conn, request_id)` in `db_tbl_da_handoff.py`: reads the last tested
  build's code rows or the `scanned` rows per the confirmed facts.
- Tests with made-up fingerprints: every blocker case, the passing case, equal/changed/missing/extra.

### Step 3: PR summary builder (pure): tests 10-13 to 10-17
- `agents/da_handoff_summary.py`: `build_summary(facts: SummaryFacts, max_chars) -> str`, lines 1 to 13
  of section 5 in order, plain text, no `tests/` path, no folder path. `SummaryFacts` is a plain model
  filled by `gather_summary_facts(conn, request_id)` (the only function that reads tables).
- Over the guard: criteria list cut to counts and a note, every other line kept.
- Hand-edited detection per the confirmed fact (scanned fingerprint equals last tested one,
  OR the last tested run was a `check` run on his edits; test both).
- Tests (also here): made-up request of each kind (new, enhancement with open Unassigned row + freshness override
  + two not-covered, overruled finding + closed escalation (the escalation part uses a plain list until
  step 6)), each line asserted, no `tests/`, length under 4,000 for the 5-file fake.

### Step 4: Handoff flow and lock: tests 10-5, 10-6, 10-11, 10-12, 10-45, 10-46
- `agents/da_handoff_flow.py`: `get_handoff_view`, `ready_for_handoff` (H1 to H3 plain checks, audit
  `handoff_blocked`), `final_check(settings, request_id, base_revision, fingerprints)` (H4/H5: ONE
  transaction: status move, `da_handoffs` row with summary, audit `handoff_checked` and `handed_off`,
  chat lines), `start_follow_up` (new request with `follows_request_id`, audit `follow_up_started`).
  H6 guard: an open escalation refuses (reads `da_escalations` if the table exists, else no-op; the
  table arrives in step 6 and the test for 10-45 is finished there).
- `refuse_if_locked` wired into the developer actions found by grep.
- Handoff `request_help` (open item `Escalated in Handoff: <step>`, H7) is added here as a plain
  function like the others; step 7 moves it onto the shared helper.
- Tests: pass, blocked-findings writes nothing but audit, changed file writes nothing, stale refused,
  every developer action refused at HANDED_OFF, tabs still readable, follow-up request, and 10-8 end to
  end (edit, Check my edits passes, handoff then passes).

### Step 5: Handoff screen, Copy summary, wording, smoke: tests 10-1, 10-18, 10-19
- Layout and callbacks: chat button **Ready for handoff** at READY_FOR_REVIEW only; blocked lists; the
  buttons Open the Tests tab / Re-scan and check my edits / Restore the tested version / Get help
  (existing handlers reused); Upload folder to check in download mode (D-C); Audit tab PR summary box
  with a clientside **Copy summary** and the "select and copy" fallback; "Open the PR summary" link on
  the Build tab; sixth stepper step; HANDED OFF pill; read-only composer line; clone vs ZIP wording
  (no Git command anywhere).
- Also: the once-only NOT_PASSING chat line "Handoff needs a passing build. Refine, or Get help.";
  **Start a follow-up request** button at `h_done` and "Follows CVDA-..." on the new request's Summary
  tab (10-12); a handed-off request opens on the Audit tab and shows the HANDED OFF pill in My recent
  requests (small layout test); tests for Upload folder to check in download mode (10-10) and the Playwright scenario
  10-53 (cloud only).
- `web/da_web_components.py` gets the summary box helper.
- `da_smoke_check.py`: handoff item (build, handoff, summary under the guard). README Handoff section.
- Playwright tests only in a cloud session (marked, skipped at home, as in earlier phases).

### Step 6: Escalation tables, routing, senior access, triggers (pure): tests 10-20 to 10-31 (rules part)
- `pydantic_classes/da_escalation_models.py`, `db_tbl_da_escalation.py` (`da_escalations`, unique index
  one open row per request, own revision).
- `agents/da_escalation_routing.py` (section 8, active rulebook, Unassigned), `da_senior_access.py`
  (`is_senior`, `DA_SENIOR_SOURCE`, `DA_SENIOR_IDS`, placeholder logs the line), `da_escalation_triggers.py`
  (one function per trigger, switch on/off, X1 to X4). `configs/da_config.py` and `.env.example`.
- Finish the H6 guard test (10-45) now the table exists.

### Step 7: Shared `escalate` helper and the five trigger hooks: tests 10-20 to 10-29
- `agents/da_escalation_flow.py`: `escalate(...)` called inside the caller's transaction. Existing
  `request_help` functions (Understand, Discover, Approach, Workspace, Build, Refine, Enhance, Handoff)
  and `dispute_finding` go through it; switch-off behaviour per D-I with audit
  `escalation_switched_off`. Hooks: build loop (trigger 1), Tester review (trigger 4), record confirm
  and approach refusal (trigger 2, the hook added only if Phase 4 has none, with a test).
- Existing tests that expect the old behaviour are updated, not loosened.
- The real Get help functions (confirmed by review): `request_help` in build, workspace, approach,
  refine and enhance flows; Discover escalates inline in `da_discover_flow.py`; **Understand has no
  escalate today**: its Help choice leaves the request at DECISION_REQUIRED with `Help requested:`
  (spec decision 11 is wrong here). Plan assumption, flagged to Gian in the worker note: with
  `get_help` on, Understand Help opens a row and moves to ESCALATION_REQUIRED (`from_status`
  DECISION_REQUIRED, already a legal move) with open item `Escalated in Understand: <step>`. Only
  step 7 is affected; Gian can overrule it without touching steps 1 to 6.
- The Understand change is the last part of this step, in its own commit; today's `Help requested:`
  behaviour stays the path when `get_help` is off.
- Fake-provider test switches for triggers 1, 2a, 2b and 4 are added here (test-only).

### Step 8: Senior actions and return rules: tests 10-32, 10-36 to 10-46
- `da_escalation_flow.py`: `overrule`, `send_guidance`, `take_over`, `close` (return, abandon), the
  section 10 return rules including the cap reset and the made-up-status guard; pre-Phase-10 rows routed
  at first load (10-32); chat lock logic (10-43, 10-44). Overrule re-labels via the Phase 7 label code.
  `overruled` added to `ActionKind`. `refuse_if_locked` is extended to an abandoned escalation
  (10-41), with a test.

### Step 9: Guidance into prompts: test 10-37, 10-51
- Optional `senior_guidance` block in the Approach, Generator fix round, Refine lane and Tester review
  prompt builders; consumed once, `used_in` set, audit `guidance_used`. Tests prove "no code in the Tester
  prompt" and "no chat in the lane prompt" still pass, with the fake client receiving the block once.
  The pretend work server (127.0.0.1:8070) fix-round check goes in `docs/handoff-work-test.md` if it
  cannot run in pytest.

### Step 10a: Admin numbers and form: tests 10-47 (part 2), 10-48, 10-49
- `da_admin_metrics.py`, `db_tbl_da_metrics.py`: Handoffs and Escalations real, Needs attention lines,
  `GET_HELP_LABEL` note removed. `da_admin_forms.py` and `layouts/da_admin_page.py` (trigger rows):
  the sixth switch and the Advanced limit. If 11c was merged differently, the chief rebases first.

### Step 10b: Inbox page: tests 10-33 to 10-35, 10-50, 10-54
- `layouts/da_inbox_page.py`, `callbacks/screen_callbacks/da_inbox_page_callbacks.py` (imports nothing
  from the developer page callbacks), `da_home_web_server.py` menu entry, `/inbox`, `?as=` switch in the
  home shell only. Composer waiting line, senior bubbles, pill "ESCALATION REQUIRED, with <label>",
  pills in My recent requests.
- **Added 14 Nov (Gian): unread badge, no email or Teams.** The Inbox menu entry shows the count of
  open rows for this senior (addressed to him as senior or backup, plus Unassigned rows): `Inbox (2)`,
  plain `Inbox` at 0. Home shows a banner to seniors only: "You have 2 escalations waiting" with a
  link to `/inbox`. Non-seniors see neither. One pure count function, plain code, no AI.
  Tests 10-55 (count: 2 open rows -> `Inbox (2)`, 0 -> `Inbox`, closed rows not counted) and
  10-56 (banner shown to a senior with open rows, hidden for a non-senior and at 0).

### Step 10c: Smoke, docs, finish
- Smoke item (Dispute -> row -> overrule -> Return -> handoff, Handoffs 1, Escalations 1) 10-52, README,
  `docs/handoff-work-test.md` (Command Prompt only), `CLAUDE.md` Current phase marked finished.

SO-3 applies: a step that proves too big continues on the same branch, never split.

## Not built (per spec section 17)
Review my code (10b), any Git or Bitbucket action, email or Teams, login, follow-up chat, copying data
into a follow-up request, senior editing code, any new AI prompt, reopening HANDED_OFF.

## Risks
- Wiring `refuse_if_locked` into every developer action may touch many files (step 4 lists them by grep).
- The `last_tested_kind` / hand-edited facts may differ from the spec; the plan then follows the code and
  notes it here.
- Step 7 changes behaviour of existing Get help paths: old tests need careful updates.

## Confirmed facts
- `LastTestedKind` (`da_refine_models.py`) is `build`, `rebuild`, `check`, `restore`. `rebuild` is a
  build too: H4 reads its code rows like `build`. Step 1 confirms where `check` and `restore` leave their
  per-path fingerprints (`scanned` rows or restored build code rows) and writes it here.
- Confirmed in step 2: `check` and `restore` runs also leave their tested text as `code` rows of the
  last tested build (`da_refine_tested.last_tested_build`; same read as `changed_paths` in
  `da_refine_flow.py`). So `get_last_tested_fingerprints` reads `read_latest_code` of that build, with
  the current build as fallback when no Refine row exists. No `scanned` read is needed for H4.
- A fixed finding is one the newest review no longer lists, so `findings_check` takes the newest
  review's kept rows with their state. `overruled` is a state string only (step 8 adds the action).
- Header note: 11c is in this branch; if it is merged differently the chief rebases before step 10a.
