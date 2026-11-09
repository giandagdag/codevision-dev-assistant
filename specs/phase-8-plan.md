# Phase 8 plan: Refine (3 lanes, revision mode, edit protection)

Spec: `specs/phase-8-refine.md` v1.0 (approved). Branch `auto/phase-8`.
Pattern: copy Phases 6 and 7. Plain-code rules in two pure files, one storage file, flows are thin
(read with no lock, slow work outside, ONE write transaction). Every step has tests and its own commit.
The spec has 42 "done when" lines and about 7,000 lines of existing code to join, so the steps are
ordered **pure rules first, then storage, then flows, then screen**. If a stop rule fires, the
finished steps are pushed and the rest is named in `ops/state/worker_note.md`.

## Design in plain words

- **Statuses.** `REVISION_IN_PROGRESS` does not exist in `da_models.py` yet; I add it (D-A option 1:
  from the lane click until the lane hands over). New moves exactly as spec section 10. Rebuilds
  and check runs use the normal BUILDING / TESTER_REVIEW / READY_FOR_REVIEW / NOT_PASSING path.
- **Refine state** has its own row and own revision (`da_refine_state`, F1), so the stale check
  works like the build's. Refine count is counted at the lane click.
- **Check run** = a build row of kind `check` run by the same `_Run` loop with a flag: no contract or
  test writing, no Generator, one pass of Layers A, B, C on the scanned texts as the "code". No budget.
  It reuses `_layer_c` and `_save_review`. Result closes the run (`check` kind column is added by
  `ALTER TABLE ... ADD COLUMN` guarded, because `CREATE TABLE IF NOT EXISTS` will not add it).
- **Rebuild** = a normal build whose start texts are his scanned texts (already true in Phase 6) and
  where every file is `modify` (R5.2). Fix rounds for the bug lane: round 1 sends only the traced
  files (`choose_files_to_fix` on the repro failure) plus the report.
- **Test set versions** (`da_test_sets`): append-only; the frozen test file of a build is the latest
  set. Appending a repro/Yours method never touches earlier methods (fingerprint of each method's
  source is checked in a test).
- **Conflicts** are pure functions over `difflib`: his lines = diff(last written, scanned);
  Generator edit blocks are applied to his text; a block is a conflict if its line span (in his
  text) overlaps his lines or comes within `distance` lines of them. Spec section 12 gives ONE
  field, `refine_conflict_context_lines` (3), for both the display context and this distance, so
  the plan follows it literally: the function takes `distance` as a named parameter and the flow
  passes the policy field. Gian may later want a separate smaller adjacency value (open question Q-a).
- **No new library.** `difflib` is standard library. "Current phase" in `CLAUDE.md` is already updated.
- **Lane suggestion** uses the **Tester role client** (WF-3 a/b/c is a work fact; the role is a
  one-line setting `LANE_ROLE = "tester"` in one place, nothing else hard-coded).
- **Restore** goes through the existing `prepare_write` / `save_write` shape with mode `restore`
  (adds `restore` to `WorkspaceMode`). The browser JS is unchanged except that it accepts the mode.
- **Not touched:** WF-1 to WF-5. They stay `needs-work-test` (WF-4 `needs-gian`). Existing guards
  (`build_max_prompt_chars`, `tester_max_prompt_chars`) are reused; no clean-up of versions.

## Steps (each ends with pytest, ruff, commit)

1. **Plan + models + policy + statuses.** `REVISION_IN_PROGRESS` and its moves in `da_models.py`
   (update `test_da_status_moves`). `pydantic_classes/da_refine_models.py`: `LaneSuggestion`,
   `CriteriaOps`, `RecordDiff`, `Conflict`, `ConflictPick`, `RefineState`, `RefineRow`, `TestSet`.
   Four `Policy` fields + seed JSON (old versions load). Tests 8-39 and the status table.
2. **Plain rules A (`agents/da_refine_checks.py`): record.** Apply criterion operations (never reuse
   an ID across any version; removed IDs kept as "removed"; unchanged byte for byte), apply field
   updates, record diff, lane-reply checks (bug without criterion becomes requirement), Refine cap.
   Tests 8-10, 8-13, 8-14, 8-12 (rule side).
3. **Plain rules B (same file): code.** His-lines (`difflib`), conflict detection (overlap, adjacent,
   far), merge of picks, prompt marker text, restore set building, every-file-is-modify, test-set
   append keeping earlier method fingerprints, Layer A refusal of `tests/` paths (check exists; add
   test 8-35). Tests 8-26 (pure part), 8-27 (pure part), 8-28, 8-35, 8-22 (fingerprints).
4. **Storage.** `db_table_functions/db_tbl_da_refine.py`: 4 tables (state, refines, test sets,
   conflicts), insert/read, guarded `kind` column on build runs, `restore` file mode, `b_conflicts`
   step, `check` build kind, in-a-row NOT_PASSING count. `ensure_build_tables` creates them. Tests.
5. **Prompts and AI calls.** `data/da_lane_prompt.md`, `da_revision_prompt.md`, `da_repro_prompt.md`;
   `agents/da_refine_agent.py` (lane call, revision call, repro/Add-a-test-case Tester call) with
   attempts and unusable handling; fake script and pretend-server answers in `da_llm_client.py` /
   `da_fake_onprem_server.py`; test-only switches. Tests 8-9, 8-11, 8-15 (no chat, no code in
   prompts), 8-21 (switch).
6. **Re-scan and Check my edits.** Flow `refine_rescan` (saves `scanned` rows, side-by-side data),
   `start_check`, check run in the loop, the R3 buttons (Fix my edit, My edit is right, I'll fix it
   myself). Tests 8-3, 8-4, 8-5, 8-6, 8-7, 8-8, 8-38.
7. **Lane start and requirement lane.** `agents/da_refine_flow.py`: Refine click, lane buttons,
   cancel, revision mode in `da_understand_flow.py`, Confirm v2 / Cancel revision, record v2 save
   (`da_request_records` already keyed by version), auto Discover, approach source `revision`,
   test plan update with New tags, gate and workspace check, files-no-longer-planned chat line.
   Tests 8-13 (flow), 8-16, 8-17, 8-18, 8-19.
Done-when per step: steps 1 to 3 = new test files `test_da_refine_models.py`, `test_da_refine_checks.py`
and the changed status/rulebook tests pass; 4 = `test_da_refine_storage.py` (incl. 8-38 count, old
database gets the `kind` column and old rows read as `build`); 5 = `test_da_refine_agent.py`;
6 to 12 = one `test_da_refine_*.py` per step with the listed 8-x tests; 13 = screen tests; 14 = smoke
check passes. Refine row also stores `repro_passed_today` (WF-2 count). Step 13 is split in
screen steps 13a (composer, 8-1, 8-2, 8-12 cap message and Re-scan/Check still enabled), 13b
(Summary and Approach tabs), 13c (Tests tab), 13d (Build tab: side by side, conflicts, Versions,
protection card). Step 9 is split in 9a (bug lane, repro proof) and 9b (Fix it, Add a test case).
Step 10 is split in 10a (b_conflicts in the loop, nothing written) and 10b (picks, merge, check
run, edit guard). Spec section 13 assumed a build `kind` column; it does not exist, so step 4 adds it
(Q-c).

8. **Approach lane.** Phase 4 `change` call with source `refine`, G9 untouched, criterion-change
   refusal and Switch to requirement. Tests 8-20, 8-21.
9. **Bug lane, Fix it, Add a test case.** Repro call, sandbox proof (must fail), two tries,
   confirm appends a test set version, fix-round rebuild with fresh budget and traced files only,
   Should-fix "Fix it", Tests-tab Add a test case. Tests 8-22, 8-23, 8-24, 8-25, 8-33, 8-34.
10. **Rebuild as patch, conflicts, write guard.** `b_conflicts` step in the loop, picks, Apply my
    choices, check run on merged files, audit per pick, edit guard test. Tests 8-26, 8-27, 8-28,
    8-29, 8-30, 8-41.
11. **Restore and download mode.** Versions list, Restore flow, warning, mode `restore`, download
    mode wording. Tests 8-31, 8-32, 8-40.
12. **Escalation, stale, status.** Get help in every lane step, stale refusal on every action,
    restart recovery of a lane step. Tests 8-36, 8-37.
13. **Screen.** Composer at `b_written` (Refine box, Re-scan, Check my edits, Restore, Get help),
    Summary version history and diff, Approach version list, Tests tab tags, Build tab side-by-side,
    conflicts, Versions, "Refine 2: bug" tag, protection card, header pill, callbacks. Tests 8-1, 8-2.
14. **Smoke check, docs, Playwright.** `da_smoke_check.py` path (bug lane, then requirement lane),
    `docs/refine-work-test.md` (Command Prompt only), README, CLAUDE.md "Current phase". Playwright
    8-42 is written but skipped when no browser (cloud only).
15. **Full run, code review (max 3 rounds), push to `auto/phase-8`, stop.**

## Plan review 2 (0 Must fix) and what I take from it
- "Last tested" is a `last_tested_build` number plus its kind on `da_refine_state` (step 4), set by
  a finished check run, rebuild or restore; a test shows it changes in each case.
- Step 6 builds only the banner, "I'll fix it myself" (8-6, 8-7). "My edit is right" (8-8) is built
  in step 7, "Fix my edit" in step 9a with its own test.
- Step 7 is split: 7a (lane click, Refine row, cancel, revision mode, Confirm v2, record v2: 8-13
  flow, 8-18) and 7b (Discover, approach `revision`, test plan New tags, gate, workspace check,
  dropped-files line: 8-16, 8-17, 8-19).
- Gian's home check on `127.0.0.1:8050` with a COPY of the repo is his job after the build; it is
  named in the final report.

## Open questions (decided in the plan, Gian can change)
- Q-a: one policy field (3) is both display context and adjacency distance, as spec section 12 says.
- Q-b: lane call uses the Tester role client (WF-3 is a work fact).
- Q-c: a "check" build stores its kind in a new guarded column, not a new table.

## Step 16: wire the Refine callbacks (added 9 Nov, Gian answered issue #33 with option 1)
Why: steps 13a to 13d only drew the Refine parts; no click did anything. Rule R12 holds: callbacks
stay thin, every check stays in the engine functions already built (steps 5 to 12).
- 16a. `agents/da_refine_actions.py` (no Dash). (1) `get_refine_bar(settings, request_id)`: for the
  open lane step (`RefineState.step`) returns the note line, the buttons as (key, label) and whether
  the text box is open. (2) `perform_refine(settings, key, request_id, refine_revision, text, arg)`:
  one dict key to engine call, returns a `Job` name (`"build"` when the caller must start the build
  runner, else `""`). Tests: a table of every step to its buttons; each key calls the right engine
  function; a stale refine revision is refused; Send at `b_written` calls `suggest`; the build job is
  returned for check, Fix it, bug fix, Apply (Keep mine) and Add-test-confirm.
- 16a table (the single list; one test asserts every key here is handled by `perform_refine`, and
  that every engine function named exists). Key, label, engine call, job:
  | Step (where) | Buttons (key) | Engine call | Job |
  |---|---|---|---|
  | `b_written`, Refine box | Send | `lanes.suggest` | |
  | `b_written` | Check my edits `check` | `flow.start_check` | build |
  | `b_written` | Restore `restore` | `flow.restore_preview` (shows warning, Restore build N / Cancel) | |
  | restore preview | Restore build N `restore_go`, Cancel `restore_cancel` | browser hop 1 `prepare_restore`, hop 2 `save_restore` (16c); Cancel clears the preview | |
  | `b_written`, download mode | Upload folder to re-scan; restore ZIP | `rescan`; `prepare_restore_download` (16c) | |
  | NOT_PASSING after check | Fix my edit `fix_edit`, My edit is right `edit_right`, I'll fix it myself `fix_myself` | NEW small engine fns in 16a: `fix_edit` = suggest(source `failed_check`) then bug lane at the rebuild step with the failing tests as repro; `edit_right` = suggest(source `failed_check`, pre-filled text) then requirement lane; `flow.fix_myself` | fix_edit: build |
  | `lane_choice` | Requirement change / Approach change / Bug `lane_*`, Cancel `cancel` | `lanes.choose_lane`, `lanes.cancel` | |
  | `req_revise` | (runs by itself on entry) Try again `revise` | `lanes.revise` | |
  | `req_checkpoint` | Confirm v2 `confirm_v2`, Cancel revision `cancel`, Send = Correct something | `lanes.confirm_revision`, `lanes.cancel`, `lanes.revise(correction)` | |
  | `req_discover` | Try again `discover` | `revision.run_discover` | |
  | `req_findings` | Findings look right `findings_ok` | `revision.confirm_findings` | |
  | `req_approach` | Try again `rev_approach` | `revision.start_revision_approach` | |
  | `req_plan`, `approach_plan` | Phase 4 buttons (Accept approach, Change something, Accept test plan, Get help) | existing `_approach_action` path, reused | |
  | `approach_start` | Send of the feedback is already saved; Try again `approach_change` | `approach.start_approach_change` | |
  | `approach_refused` | Switch to requirement change `switch`, Cancel | `approach.switch_to_requirement`, `lanes.cancel` | |
  | `bug_start` | Send (description) | `bug.start_repro` | |
  | `bug_confirm` | Yes, this is the bug `repro_yes`, No, describe again `repro_no`, Cancel | `bug.confirm_repro`, `bug.reject_repro`, `lanes.cancel` | |
  | `bug_help` | Get help, No, describe again, Cancel | `help.request_help`, `bug.reject_repro`, `lanes.cancel` | |
  | `bug_rebuild` | Start the fix | `bug.start_bug_fix` | build |
  | `own_confirm` | Add this test `own_add`, Drop this test `own_drop` | `owntest.confirm_own_test` then `flow.start_check(after_new_test)`; `owntest.drop_own_test` | build |
  | `own_fails` | Yes, fix it `own_bug`, Drop this test | `owntest.treat_as_bug` then `bug.start_bug_fix`; `owntest.drop_own_test` | build |
  | Tests tab | Add a test case (criterion + text) | `owntest.add_test_case` | |
  | Tests tab | Fix it on a Should fix | `fixit.fix_it` | build |
  | `b_conflicts` | Keep mine / Take the AI's (per conflict), Apply my choices | `picks.pick`, `picks.apply_choices` | build if any Keep mine |
  | any open lane step | Get help | `help.request_help` | |
  The two NEW functions `fix_edit` and `edit_right` are NOT yet in the engine (only the source
  value `failed_check` exists); each gets its own tests (8-8, 8-6 area) before wiring.
- 16a end-to-end test (answers plan review Must fix 2): through the callback functions, a
  requirement lane (Send, lane pick, Confirm v2, Findings look right, Accept approach, Accept test
  plan, workspace check, Build, READY_FOR_REVIEW) and a bug lane, with the fake provider. The
  existing Phase 4/5/6 buttons are reused unchanged while status is REVISION_IN_PROGRESS; `refine_revision`
  is read fresh from `lanes.get_refine_revision` on every draw and sent in the page state.
- Who starts the runner: the Refine callback calls `build_runner.submit_build` when `perform_refine`
  returns job `build` (the same call `_build_action` makes). A test sends two clicks in a row: the
  second is refused as stale (F2).
- 16b. Layout and callbacks. Page state gets `refine_revision` and `refine: True`. A new button
  pattern id `REFINE_TYPE` draws the lane bar in the composer while status is REVISION. Callbacks in
  `callbacks/screen_callbacks/da_refine_callbacks.py`, registered from the page register function:
  Send at `b_written` (Refine), lane/step buttons, conflict picks (existing `CONFLICT_PICK_TYPE`),
  Fix it (Tests tab), Add a test case, Get help. Poll keeps running while a build job runs.
  Tests call the functions directly, as the Phase 7 callback tests do. One more test lists the
  registered callback inputs and checks every Refine button id the layout draws is among them.
- 16c. Browser buttons Re-scan and Restore (hop 1 / hop 2) use the same bridge pattern as the
  Phase 5/6 write buttons, including download mode (8-40). Checked by tests on the script text and
  the bridge routes; the real clicks are checked by 8-42 (16d). The final report says whether 8-42
  ran or was skipped; a skip means the buttons are NOT verified, and Gian's home check on
  127.0.0.1:8050 is the proof.
- 16d. Enable 8-42 (Playwright, skipped only if no browser is installed). Fix the 2 round-1 Should
  fix items: smoke items 27 and 28 must end READY_FOR_REVIEW (item 28 does the rebuild), and the
  "Known gap" note leaves `docs/refine-work-test.md` (a test checks it is gone; the smoke check
  asserts and prints the final status of items 27 and 28). Step 15 is superseded by 16e.
- 16e. Full run, code review rounds 2 and 3, PR into `auto/phases-7-10`.
Stop rule: if 16c cannot be done without a library or a decision, stop and write it to the worker note.

## Out of scope
As spec section 15. Admin screens, Handoff, Enhance, deleting files, Git, tests in the workspace.
WF-1 to WF-5: no work, parked as `needs-work-test` / `needs-gian`.

## Risks
- The size of the phase: I may stop after step 9 or 10 and report the rest.
- The loop is shared with Phases 6 and 7; each step re-runs the full suite to catch breakage.
- Windows-only sandbox test failure P31 is known and accepted.
- Real-work behaviour (model quality for lane/repro prompts) is untestable at home.
