# Phase 6: Build + test loop, build plan

Spec: `specs/phase-6-build-test-loop.md` v1.1 (the only spec read; it points at the demo's
`tabBuild`, states `running`, `r1`, `written`, which I read at the screen step). Branch: `phase-6`,
made from `origin/main` after PR #16 (Phase 5) was merged. Baseline before any change: 1210 tests
pass, ruff clean, smoke check passes (21 items).
Pattern copied from Approach and Workspace: read with no lock, do the slow work (AI, sandbox,
browser) outside any transaction, then ONE write transaction with the build's own revision.

## The shape of the build (the one new idea)

Two things run in two places, joined only through the database:

- **The server thread** (background, D-D) runs the loop: contract, tests, then rounds of
  *generate, Layer A, Layer B*. It never touches the laptop. At the end it saves the result and
  moves the status. Like a `SBMJOB` batch job writing to its job log.
- **The browser** (Phase 5 pattern) does the two things only a laptop can: the pre-build re-scan
  at the start, and the write job at the end. The page sees `b_done` / not written and runs the
  Phase 5 write job by itself (D-E).

The page polls every 3 s (`dcc.Interval`) while the step is `b_running` or `b_round_failed`.
The database is the truth, not the thread (a restart marks it `b_interrupted`).

## Decisions I made where the spec is silent or conflicts (none change a Done-when row)

| # | Choice | Why |
|---|---|---|
| P1 | **Gian decided (3 Nov): Build reuses the Phase 4 fields `protected_files` and `approved_libraries`.** Only 6 new policy fields are added: `build_max_rounds`, `build_test_timeout_seconds`, `build_max_prompt_chars`, `build_max_parallel`, `build_blocked_imports`, `build_sandbox_exclude`. Spec section 11 gets a note (decision D-M) in the docs step | Spec section 11 listed `build_protected_files` and `build_approved_libraries` as new, but Phase 4 already has two such lists with different values. Two lists could disagree (Approach allows a library, Build blocks it). **Consequences, all tested:** (a) **a blocked import always beats an approved library**: the Phase 4 seed approves `requests` and `flask`, and `requests` is in `build_blocked_imports`, so Layer A A4 refuses `requests` (test with `requests` as the case; spec A4 "never a blocked module"); (b) Layer A A3 and A4 **reuse the Approach matchers** (`_matches_any` for protected globs such as `*/.env*`, `_library_name` for libraries), moved to a small shared function in `da_approach_checks.py` or imported from it, never a second matcher; (c) the starter values for these two lists are now the Phase 4 seed values (6-31 checks the 6 new fields only); (d) spec sections 5, 11, 21 and 6-31 wording get the D-M note in step 16 |
| P2 | **Layer A check A7 has no rule to run today.** The seed has 5 `judgement` and 2 `ui_convention` rules and no plain-code kind. A7 is built as an empty hook that runs plain-code rules of the rulebook when one exists, and the Layer A result says "0 rulebook checks apply". Nothing invented (spec A7) | Spec says "none are invented here" |
| P3 | **Sandbox layout (Q15 default, the spec asks it to follow Q15 which is still open):** temp folder holds `src/` (copy + planned files) and `tests/` at the top. The runner puts `<tmp>/src` on `sys.path` itself (needed because `-I` drops the working folder), working folder is `<tmp>`, discovery runs on `tests/<id>/` with top level `<tmp>`. So a test says `from agents.upload_validator import validate`, the same way CodeVision modules import each other when started from `src`. When Q15 is answered, only `da_sandbox.py` changes | Matches the Q15 example in the spec (`from web.web_components import ...` run from `src`) |
| P4 | D-B check: the Phase 4 file plan (`PlannedFile`) has path, action, purpose, reuses and **no function names**, so the contract call is needed (D-B option 3 does not apply). Checked in the code, not assumed | Spec D-B says the builder checks this first |
| P5 | The fake provider answers build prompts with a **scripted client** like `ScriptedApproachClient` (JSON files in `src/data/`, selected by a marker line in each prompt). Test-only switches are arguments of the script loader that tests pass in; the app has no switch. Scripted replies follow the existing fake plan: create `src/agents/excel_processor.py`, modify `src/agents/upload_validator.py` | Same pattern as Phases 3 to 5 |
| P6 | **Refined in step 7:** replies are plain code, not JSON. A new file and the test file come back as the whole Python text (a code fence is allowed). An existing file comes back as visible edit blocks (`<<<<<<< FIND` / `=======` / `>>>>>>> REPLACE`). Only the contract is JSON. Parsed into `CodeReply` (`text` or `edits`) by plain code | Spec D-C says "the reply is the whole file text" for new files. Models often break multi-line code inside JSON strings (quotes, newlines), which would waste rounds on format errors |
| P6b | A new `ContextTooLargeError` (a kind of `LLMClientError`) is raised for HTTP 400, so the Build does not match on message text. Existing tests that expect `LLMClientError` still pass | Spec section 4: HTTP 400 is "too big", not the code's fault |
| P7 | The runner (`da_sandbox_runner.py`) writes `results.json` with per test: name, result, message, last 20 traceback lines; plus the name of the test that was running when killed (a small `startTest` hook writes `running.txt` before each test). The kill is `Popen(start_new_session=True)` then `os.killpg` on timeout (Linux, the OCP server, Q14a). On Windows the home laptop uses `taskkill /T`; the test of the time limit runs in the cloud (Linux) and on the laptop | Spec: "whole process tree is ended" and "names the test that was running" |
| P8 | Slots (`build_max_parallel`): counted from `da_build_runs` rows with no end time, inside the one write transaction that starts a build. A third build gets step `b_running` with progress line "Waiting for a free slot (N ahead of you)" and a thread that polls the count every second | Database is the truth, works after a restart. Per copy of CodeVision only; Q14(e) note below |
| P9 | **Q14(e) stop point:** if Gian reports (before step 9) that OCP runs several copies of CodeVision, I stop and ask before building step 9, as spec section 17 says. Q14(e) is unanswered today, so I build step 9 for one copy and say so | Spec section 17 note |
| P10 | Labels are plain strings stored on `da_build_runs.label` (`Ready with warnings`, `Not passing`) and the chat-only `Unable to assess`. The fixed warning text is a constant tested by exact match | D-F |
| P11 | The write at `b_done` reuses `build_write_job` from `da_workspace_checks.py` with `creatable_folders=[]` after C2. The job holds code files only, in file-plan order; the builder refuses any path starting `tests/` (6-37) | Spec section 9 |
| P12 | `tests/da_workspace_play.py` and `da_approach_play.py` get a `ready_to_build_with_workspace_id` helper (request at `ws_ready` in a fake browser folder), so build tests start from a real saved state. No existing helper is changed | Surgical |
| P13 | Flag-for-review zones (spec section 5, last paragraph): zones exist in the rulebook, so step 8 records which planned files fall in a zone, using the same matcher Approach uses (`zones_touched` on the approach version is already saved by Phase 4). Phase 6 only copies it into the `build_passed` / `build_not_passing` audit details as `zones_touched`; it never blocks. Test in step 8 | Spec says record, Phase 10 uses it |
| P14 | The CLAUDE.md stop rules (test fails after 2 fixes, spec unclear, review caps, photos) apply to every step, not only steps 6 and 9 | Reviewer finding |

## Steps (each ends with its tests, ruff clean; commit per step, push `phase-6` after each group)

0. **Done:** branch `phase-6` from `origin/main`, `CLAUDE.md` "Current phase" says Phase 6, this plan.
1. **Policy fields** (`da_rulebook_models.py`, `da_rulebook_seed.json`): the 6 fields of P1 with defaults. Tests 6-31 (old JSON loads with the starter values; seed has them), bounds (rounds 1..5, timeout 1..600, and so on).
2. **Statuses and moves** (`da_models.py`): `BUILDING`, `READY_FOR_REVIEW`, `NOT_PASSING` and the moves of spec section 2. Update the tests that said "READY_TO_BUILD has only 2 moves" (`test_da_status_moves.py`, `test_da_models.py`). Done when: moves table test lists every spec move and refuses the others. First `grep` for every place that lists all statuses (status chip colours, "My recent requests" labels, `STATUSES` users, tests that count them) and update each; the list of places is pasted in the step's report.
3. **Models** (`pydantic_classes/da_build_models.py`): `BuildState` (step, build number, revision, write state), `Contract`, `FileEdit` / `EditReply`, `LayerAResult`, `TestResult` / `LayerBResult`, `RoundRecord`, `FailureReport`, `BuildView`. Extra fields refused. Steps `b_prescan`, `b_running`, `b_round_failed`, `b_interrupted`, `b_done`, `b_written`, `b_write_stopped`, `b_unable`.
4. **Storage** (`db_tbl_da_build.py`): 5 tables of spec section 13, append-only triggers on files, rounds and progress, revision check on state (same style as `db_tbl_da_workspace.py`). Tests: round trip, append-only, stale save refused, `da_build_runs` updated only to close.
5. **Pure rules** (`agents/da_build_checks.py`): contract checks, test-file checks (one method per case, naming, imports, no outside file or network use), Layer A A1 to A7, edit-block apply (once, zero, twice, keeps `\r\n`), `tests/` path refusal, file-to-fix choice (D-J), failure report in both forms, label rules, prompt-size guard. Table-driven tests, good and bad made-up code per check. Covers 6-5 (half), 6-7, 6-9, 6-10, 6-11, 6-12 (size half). Also: `requests` refused although approved (P1a); check the claim that the seed has no plain-code rule (P2) in the code, not from memory.
6. **Sandbox, the real one** (`agents/da_sandbox.py`, `agents/da_sandbox_runner.py`, fixture `tests/fixtures/da_reference_codevision/` shaped like the fake plan, plus a `.env` and `.db` inside it that must never be copied): real subprocesses, no AI, no internet. Tests 6-13 (passing, folder deleted), 6-14 (sleeps past a 2 s limit, process tree gone, test named), 6-15 (no key in the environment), 6-16 (no `.env` or `.db` copied), 6-17 (1 MB output cut at 200 KB), 6-41 (own `tests/` folder in the temp folder only), a sandbox that cannot start (missing reference folder). **Stop rule:** if the time-limit kill leaves a live process after 2 fix attempts, stop and report.
7. **Prompts and AI calls** (`agents/da_build_agent.py`, `src/data/da_build_contract_prompt.md`, `da_build_tests_prompt.md`, `da_build_code_prompt.md`, `da_build_fake_script.json`): contract call, test-writing call (the Tester never gets code text; tested by checking the prompt), one code call per file (create: whole text; modify: edit blocks), the fix call (failing file only). Reuses `get_tester_client` style and `get_llm_client`. Step 7 tests only the agent output and the rules: contract reply valid and limited to planned files (6-4 first half), 6-5, Tester bad twice returns "unable" (6-6 first half), 6-8, an HTTP 400 reply raises the "too big" error (6-12 first half), and the "other files only as contract lines" prompt content. The saved-and-frozen, `b_unable`, `b_interrupted` and "no round used" halves are tested in step 8.
8. **Build flow** (`agents/da_build_flow.py`): `start_build` (B1 gate: READY_TO_BUILD, `ws_ready`, permission; saves pre-build scan as `scanned`), `run_build` (the loop: contract, tests, freeze, rounds, results, the one-transaction saves, audit events of spec section 13), `stop_build`, `try_again` (resume, no round used), `request_help`, `change_approach` (reuses the Phase 4 counter), `rescan_and_build_again`, `get_build_view`. Stale checks on the build revision (6-29). In step 8 the loop runs **synchronously** in tests (no thread, no slots); step 9 adds the thread and the slots. Also here: B2 (wrong input at each step gets a plain message), B8 (the chat line "Please don't edit the planned files until I finish." is sent exactly once per build), P13 zones in the audit details, and the second halves of 6-4 (contract saved and frozen), 6-6 (`b_unable`, nothing written, no round) and 6-12 (`b_interrupted`, no round). Tests: 6-2, 6-3, 6-18, 6-19, 6-20, 6-21 (always-failing switch, cap, files still written), 6-25, 6-26, 6-30, B2/B4/B5. One test file per group (start, rounds, interrupt, stop and help).
9. **Background runner** (`agents/da_build_runner.py`): thread start, slots (P8), start-up recovery of builds still marked running (6-27: Try again does not regenerate finished files), 3 s progress lines. Tests 6-27, 6-28. Q14(e) stop point (P9).
10. **Phase 5 removals** (C1 to C6, section 15.1) and **P26** in `da_workspace_flow.py`, `da_workspace_checks.py`, `da_workspace.js`, `da_workspace_panel.py`: no write at the workspace check, writer creates no folders, no B7, re-scan reads planned files only, ZIP and upload code files only, `isSameEntry` wording. Existing Phase 5 tests that expect `tests/<id>/__init__.py` are changed to expect the new behaviour. Tests 6-32, 6-35 to 6-40 (browser halves are Playwright, SKIPPED with a plain reason if Playwright is missing; run in the cloud).
11. **The write at `b_done`** (in `da_build_flow.py` + `da_workspace_flow.py`): job from the saved code files, `expected` per spec section 9, the browser writes, the server verifies and saves `written` rows, step `b_written` or `b_write_stopped`. Download mode (spec section 9): the build's ZIP holds the code files only, with the "upload your folder before every new download" line, and a re-scan by upload feeds B9. Tests 6-22, 6-23, 6-24, the page-closed case, and the download-mode build (ZIP entries are exactly the code files plus `READ_ME_FIRST.txt`).
12. **Screen** (`da_web_components.py`, new `layouts/da_build_panel.py`, `da_developer_assistant_page.py`, `da_approach_panel.py`): Build tab (demo `running`, `r1`, `written`, `not_written`), layer boxes, Tests tab (frozen list, per-round results, View test code toggle, "not copied to your folder" line), chip, composer buttons per build step, "My recent requests" reopens at the same step. Tests 6-1, 6-42, button sets per step, and exact-text tests for "Time limit 60 seconds per run", "Coming in Phase 7" (Layer C slot) and "These tests run on the CodeVision server. They are not copied to your folder."
13. **Callbacks** (`callbacks/screen_callbacks/da_build_callbacks.py`): Build click (browser re-scan, then server start), Interval poll that turns itself off, server buttons (Stop, Try again, Get help, Change the approach), auto-write hop on open.
14. **Pretend work server** (`web/da_fake_onprem_server.py`): answers the three build prompts with the same fixed script. Test 6-33 through the real onprem connector.
15. **End to end and smoke:** Playwright test 6-34 (cloud only: full request from READY_TO_BUILD to `b_written`, fingerprints match, no `tests/` folder in the folder), smoke items 24 and up (full build with fake provider, real sandbox, fake browser bridge, to READY_FOR_REVIEW then `b_written`). Numbers confirmed against the file.
16. **Docs:** `README.md` section, new `docs/build-work-test.md` (Q14 and Q15 steps, Command Prompt only), `docs/workspace-work-test.md` (DevTools steps dropped, Q8 marked done), `.env.example` (`DA_SANDBOX_SOURCE_DIR`, plus its loading in `da_config.py` and a test), spec note D-M for P1 in sections 5 (A3, A4), 11, 21 and the 6-31 wording (field names and starter values), and a missing `DA_SANDBOX_SOURCE_DIR` leads to `b_interrupted`, never a crash (test).
17. **Finish:** full `pytest`, `ruff`, smoke check, `code-reviewer` (max 3 rounds), commit, push `phase-6`. Gian does the home check on `127.0.0.1:8050` (`DA_LLM_PROVIDER=fake`, a COPY of the repo as workspace, leave the page and come back, no `tests/` folder written) and merges himself.

## Honest limits (stated, not hidden)

The sandbox is a separate process with a time limit, an empty environment and Layer A import and
call rules. It does **not** block the network at operating-system level and does **not** cap memory
(Q14 d). A test file can still do harm that Layer A cannot see (for example heavy computation up to
the 60 s limit). Windows home laptops end the tree with `taskkill`; the OCP server is Linux.

## Files touched

New: `da_build_models.py`, `db_tbl_da_build.py`, `da_build_checks.py`, `da_build_agent.py`,
`da_build_flow.py`, `da_build_runner.py`, `da_sandbox.py`, `da_sandbox_runner.py`,
`da_build_panel.py`, `da_build_callbacks.py`, three build prompts, `da_build_fake_script.json`,
`tests/fixtures/da_reference_codevision/`, `docs/build-work-test.md`, matching tests.
Edited: the files in the steps above, plus existing tests that assert the Phase 5 tests-folder
behaviour or "READY_TO_BUILD has only 2 moves" or the old "Build (coming in Phase 6)" button.

## Out of scope (spec section 16), not touched

Layer C, Refine and developer-edit patching, Enhance, auto-escalation and Handoff, Admin screens,
any Git command, writing tests to the workspace (never, Q11).

## Risks

- `da_developer_assistant_page.py` (1,004 lines) and `da_approach_flow.py` (1,102) are big: build
  code goes into new files and small additions, not rewrites.
- A background thread plus Dash plus SQLite: every thread opens its own connection (the existing
  `_write` pattern), never shares one.
- Step 10 changes Phase 5 behaviour and its tests; done as its own step with the old tests changed
  in the same commit so the suite is never knowingly red.
- Playwright-only rows are SKIPPED with a plain reason on a laptop without it; step 15 pastes the
  cloud run where they pass.
- Step 6 and step 9 are the two places a stop rule is most likely (process kill, restart recovery).
