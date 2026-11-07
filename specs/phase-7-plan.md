# Phase 7 plan: Independent Tester (Layer C, report, labels)

Spec: `specs/phase-7-independent-tester.md` v1.0 (approved). Branch `auto/phase-7`.
Pattern: copy Phase 6. Plain code in one pure file, AI call in one small file, one new storage file,
the loop and the flow get small additions. Every step has tests and its own commit.

## Design in plain words

- **Layer C lives inside the existing background build loop.** After a round passes Layers A and B,
  the loop calls `_layer_c(round)`. New running step `b_tester_review` joins `RUNNING_STEPS`, so
  Stop build, the stale check, the progress polling and the restart recovery all work unchanged
  (T3, T4). A `b_interrupted` during review keeps status TESTER_REVIEW; Try again goes to
  `b_running` and the loop sees "round passed, no saved review" and repeats only the review.
- **One write transaction per review** (T2): read with no lock, plain checks, AI call outside any
  transaction, then ONE `_turn()` that saves the review, findings, state, audit and chat lines, and
  either moves on to the next round or finishes the build (same transaction, so there is no gap).
- **A Must fix round**: the round record already exists (A and B passed) and is append-only, so the
  next round's "files to fix" and "report for the Generator" are rebuilt from the saved review's
  kept Must fix findings (plain code). Should fix and FYI never reach the Generator.
- **Budget**: `len(rounds) >= build_max_rounds` with a Must fix open ends NOT_PASSING (code still
  written, D-H). Check 1 failing (no test for a criterion) ends NOT_PASSING at once, no extra round.
- **Labels are live.** The build run row is closed (immutable), so the label shown is computed from
  the last review plus the developer's accept/reopen actions (`compute_label`). The run row gets
  the label at the moment the build closes. `label_changed` is audited when an accept/reopen
  changes the computed label.
- **Fake script (home).** The Phase 6 fake build already fails 3 tests in round 1, so Layer C first
  runs in round 2. The scripted review answers by the `Round: N` line in its prompt: round 2 gives
  1 Must fix on `excel_processor.py`; round 3 gives 1 Should fix and 1 FYI with good evidence plus
  1 finding with a quote that is not in the file (dropped). So the default home build is 3 rounds
  (round 1 tests fail, round 2 Tester Must fix, round 3 passes and ends yellow). This differs from
  the spec text in section 13 ("round 1 passes A and B"), because rewriting the Phase 6 fake script
  would break about 30 Phase 6 tests. Test-only switches: `review_unusable`, `review_must_fix_always`,
  `review_empty`, plus the existing `no_answer` and `too_big`.
- **ALLOWED_MOVES** adds the 7 spec moves and `TESTER_REVIEW` to `STATUSES`. I remove
  `BUILDING -> READY_FOR_REVIEW` (never used again: every pass goes through TESTER_REVIEW; a saved
  request cannot be mid-move across a restart because recovery sets `b_interrupted` and Try again
  goes through TESTER_REVIEW). `test_da_status_moves` (the hand-written spec table) is updated.
- **Review row is saved only when the review closes** (`done` or `unable`). An interrupted review
  writes only an audit event and the `b_interrupted` step (nothing to save; Try again repeats it).
  The spec lists `interrupted` as a result value; the column accepts it but nothing writes it.
- **Run the Tester review again** (Unable to assess only) is a synchronous flow action, same
  machinery: moves READY_FOR_REVIEW -> TESTER_REVIEW -> (READY_FOR_REVIEW | NOT_PASSING) in one
  transaction (both moves audited), no round used. A Must fix found by a re-run ends NOT_PASSING
  (the build is closed; fixing it is Phase 8).
- **Dispute / Accept / Reopen**: new flow functions using the existing `_turn` (revision check,
  one transaction). Dispute reuses the escalation path with open item `Disputed Must fix: F-n`.
- **W6**: a test proves the Phase 6 tests-writing prompt holds no code; W6 stays open for Phase 8.

## Steps (each ends with pytest, ruff, commit)

1. **Models and policy.** `pydantic_classes/da_tester_models.py` (reply, finding, check result,
   review, action, view rows). `Policy` gets `tester_max_prompt_chars` 60000, `tester_max_attempts`
   2, `tester_quote_window` 2 (+ seed JSON). Status TESTER_REVIEW + moves. Labels constants
   (`LABEL_READY`, `LABEL_WITH_WARNINGS`...), remove `LAYER_C_WARNING`. Tests 7-32, status table.
2. **Storage.** `db_table_functions/db_tbl_da_tester.py`: 3 tables (append-only triggers), insert and
   read functions, count of Unable to assess. `ensure_build_tables` also creates them. Tests.
3. **Plain checks and evidence rule.** `agents/da_tester_review.py`: checks 1, 2, 3, 7; numbering
   DD-n / RU-n; line-numbered code; E1 to E5; label rules; fix lines for the Generator; prompt
   builder with the size guard split. Tests 7-3 to 7-9, 7-4 to 7-7, 7-24 prompt side, label table.
4. **The AI call.** `agents/da_tester_review_agent.py` + `data/da_tester_review_prompt.md` +
   scripted reply (fake and pretend server). Attempts, unusable twice, HTTP 400 split then pause,
   no answer. Tests 7-10, 7-24, 7-25, 7-26 (agent side), 7-29, 7-30.
5. **The loop.** `da_build_loop.py`: `_layer_c`, `_rounds` change, Must fix next round, finish
   with the Phase 7 label, remove the Phase 6 warning, `b_tester_review` in `RUNNING_STEPS`,
   restart recovery. `result_for` takes the label. Update the Phase 6 tests that named the old
   warning or the 2-round fake build. Tests 7-1, 7-2, 7-11, 7-13 to 7-16, 7-23, 7-26 to 7-28, 7-31, 7-33.
6. **Developer actions.** `agents/da_tester_flow.py`: accept (10 to 300 chars), reopen, dispute,
   run again, tester view for the screen. Tests 7-12, 7-17 to 7-21, 7-31.
7. **Screen.** `layouts/da_tester_panel.py` (Tests tab report, findings, actions), Build tab Layer C
   box and progress, banner, buttons, `BuildView.tester`, callbacks for the finding buttons,
   status colour. Tests 7-20, 7-22, 7-23 screen side.
8. **Smoke check, README, docs.** `da_smoke_check.py` full path through TESTER_REVIEW;
   `docs/tester-work-test.md` (Command Prompt only); README; CLAUDE.md untouched except as needed.
   Playwright test 7-35 is written but skipped when no browser (cloud only).
9. **Full run and code review** (max 3 rounds).

## Plan review result (plan-reviewer, 7 Nov 2026): 0 Must fix, 4 Should fix, all taken
- Re-run: read with no lock, AI call OUTSIDE any transaction, then one `_turn()` with both moves; a test proves the AI call is not inside the write (step 6).
- Re-run finding a Must fix ends NOT_PASSING: this is a guess, flagged as an OPEN QUESTION for Gian (alternative: use a round if budget is left).
- Test 7-34 (W6: Phase 6 tests-writing prompt holds no code) is in step 4.
- Step 5 is split into 5a (enter Layer C and finish), 5b (Must fix next round and the cap), 5c (Stop, restart recovery, old Phase 6 test updates). Step 7 is split into 7a (Tests tab: 7 check rows with "Not run", earlier reviews collapsed, Show dropped toggle) and 7b (Build tab: Layer C box, findings by severity, model name, "Reviewed file by file (N calls)", elapsed time).
- `docs/tester-work-test.md` matches the real flow: round 1 tests fail, round 2 Tester Must fix, round 3 yellow. README says `interrupted` is never written in Phase 7.

## Out of scope (as the spec)
Fix it (Phase 8), inbox/overrule/auto-escalation (Phase 10), admin screens (Phase 11), choosing
the Tester model (Q9) and the real size limit (Q7).

## Risks
- Loop restructure touches Phase 6 tests (listed in step 5).
- The default home build now takes 3 rounds (see fake script note above).
- Re-run is synchronous inside a page callback (a real AI may take 10 to 20 s; the busy mode covers it).
- `.pyc`/Windows: none.

## Gian's decisions on the plan (7 Nov 2026, project chat)
Accepted all 4 choices the builder flagged: (1) the home build takes 3 rounds, round 2 has the
Tester's Must fix; (2) `BUILDING -> READY_FOR_REVIEW` is removed, every pass goes through
`TESTER_REVIEW`; (3) a review row is saved only when the review closes, an interrupted review writes
an audit event only; (4) "Run the Tester review again" runs inside the page callback (note the 10 to
20 s wait for the work test). The `plan-reviewer` still reviews the whole plan before the build.
