# Fix D1: two test layers and a test report (proof of testing)

Version 1.0 APPROVED, 17 Nov 2026 (20:40 SGT). Written in the project chat from director item D1 in
`claude/findings-2026-11-14-decisions.md` (agreed 14 Nov). Gian, 17 Nov 20:18: "Yes go ahead",
D1 first (the rest of batch B2 is its own spec), no coverage measuring for now. Gian, 17 Nov 20:26:
full authority for the recommendations: **every D-x in section 5 is option 1.**

Branch `phase-d1-test-report` (spec commit on it, cut from `auto/phases-7-10`). Start right after fix
batch C is merged: merge the newest `auto/phases-7-10` in first. PR into `auto/phases-7-10`; the chief
merges it. Build it the normal way: plan `specs/fix-d1-test-report-plan.md` (a `## Steps` list),
plan review, small steps with tests, code review (max 3 rounds), full pytest, ruff, smoke check.
Commit subjects say "D1 step N" so the board can count. Laptop team, no spec-writer run.

## 0. Why

The director wants proof of testing he can open and read: for every test, what went in, what was
expected, what actually came out, and pass or fail. And he wants the code tested two ways:
**against the requirement** (does it do what was agreed) and **against the code** (do its branches
and edge cases behave).

Checked in the code on 17 Nov (`auto/phases-7-10`, commit of 17 Nov 09:05):

| Today | Gap |
|---|---|
| Requirement tests are written from the criteria before the code, frozen, run in the sandbox (`agents/da_build_agent.py::write_tests`, `agents/da_sandbox_runner.py`) | Fine. Keep |
| The runner records only name, result, message, traceback tail (`TestOutcome`) | No input, expected or actual value is ever recorded. A passing test leaves no evidence |
| No code tests exist anywhere | The second layer is missing |
| The Tests tab shows one result word per test (`TestRow`) | No report, no "Open report" |
| The Admin "Build and test" tab (`layouts/da_admin_build_tab.py`, `TEST_FACTS`) already says "Code tests after the build, for branches and edge cases" | **Says something that is not true today.** Fixed by this spec (it becomes true) |

## 1. Words used here

- **Requirement test (T-n):** written from the acceptance criteria before any code, frozen. Tests the
  code **against the requirement**. Exists today.
- **Code test (C-n):** written after the code passed its requirement tests, by an AI that reads the
  code. Tests the code **against itself**: every `if`/`else` branch, empty and boundary values, wrong
  types, error paths. New.
- **Safety-net test (S-n):** Phase 9 (Enhance) tests that guard what must not change. Exists today;
  it goes into the report too.
- **Evidence line:** one recorded check inside a test: label, input, expected, actual, match yes/no.
- **Test report:** the saved proof for one build: header, summary, every test with its evidence, the
  Tester's verdict.

AS400 comparison: today the job log says "step ended normally". After D1 each step also prints its
input record, the expected value and the value it actually produced, and the whole log is kept as a
spool file anyone can open later.

## 2. What we build

| # | Piece |
|---|---|
| E1 | **Evidence helper.** A small standard-library module `agents/da_evidence_helper.py`, copied into the sandbox folder next to the tests (like the runner). Tests call `evidence(self, label, given, expected, actual)` before their assert. It stores `repr()` of each value, cut at 500 characters each, and returns nothing. The runner collects the lines per test into `results.json`. Uses no new library |
| E2 | **Requirement tests record evidence.** The tests prompt (`build_tests_prompt`) tells the AI to call `evidence(...)` for every check. `find_test_file_problems` gets one new AST rule: each `test_` method calls `evidence(` at least once, else the retry note "Test T-n records no evidence". Frozen tests written before D1 are **not** rewritten (frozen means frozen): their rows show "Evidence not recorded (test written before 17 Nov)" and their result still counts |
| E3 | **Outcome model.** `TestOutcome` gets `evidence: list[EvidenceLine]` (new small model: `label`, `given`, `expected`, `actual`, `match: bool`, `cut: bool`). A failing assert with no evidence line still shows its message, as today |
| E4 | **Code tests (new step after Layer B).** When the requirement tests pass (`LayerBResult.ok`), one AI call (`write_code_tests`, model role "Tester") reads the contract, the written code and the criteria, and writes up to **15** code tests (`C-1` to `C-15`, fixed number, constant `CODE_TEST_LIMIT`). Each test has a docstring line `Targets: <file>:<function> <branch or edge case in plain words>`. Same Layer A checks as requirement tests plus E2's evidence rule. Run in the same sandbox, same 60 s limit (one more run, not shared with Layer B's time) |
| E5 | **What a failing code test does.** See D-B. Recommended: the Independent Tester (Layer C) judges each failing code test as **code bug** or **wrong test** with one line why. Code bug: it becomes a normal failure, uses one round of the shared budget, and the code test is kept for the next round. Wrong test: dropped, kept in the report under "Dropped code tests" with the reason, never silently removed |
| E6 | **Code tests are per build.** Unlike requirement tests they are not frozen: a new build or a Refine rebuild writes them again, because the code changed. The report keeps each build's set |
| E7 | **Report storage.** New append-only table `da_test_reports` (one row per finished build round that reached Layer B): request ID, build number, round, JSON body, created at. Never updated, never deleted (audit). New audit event `test_report_saved` |
| E8 | **Report contents.** Header: request ID and title, requirement version, approach version, test set version, build number and round, file fingerprints of the tested code, date and time (SGT), AI models used per role, where it ran ("CodeVision server sandbox, Python <version>"), the label (Ready for your review, Ready with warnings, Not passing, Unable to assess). Summary: counts per layer (passed, failed, not proven, dropped). Then three sections in this order: **1. Against the requirement** (T-n), **2. Against the code** (C-n), **3. Safety net** (S-n, Enhance only, else hidden). Each test: ID, criterion (or Targets line), Given, Expect, its evidence lines as a table (Input, Expected, Actual, Match), result, and the failure message when not passing. Last: the Tester's 7 checks and findings. Negative scenarios keep the asterisk and legend |
| E9 | **Open report.** A Dash page `/dev-assistant/report/<request_id>/<build_no>` (no server path shown anywhere). Read only. Two buttons: **Print** (the browser's own print, with print styles so it fits A4 and shows no app chrome; "Save as PDF" in the print box gives a PDF with no new library) and **Download** (one self-contained HTML file named `CVDA-<id>-build-<n>-test-report.html`). Opens in a new tab |
| E10 | **Right panel, Tests tab.** Top: a summary line, for example "Against the requirement: 8 of 8 passed. Against the code: 11 of 12 passed, 1 dropped." plus the **Open report** link. The table gets two groups (Requirement tests, Code tests) and an Evidence column ("3 checks", click to expand). Old builds with no report show "No report for this build (built before 17 Nov)" |
| E11 | **Handoff.** The PR summary gets the report summary lines and the report file name, so the reviewer knows where the proof is |
| E12 | **Admin wording.** `TEST_FACTS` in the Admin Build and test tab gets one more line: "Every build saves a test report: input, expected, actual, pass or fail". The code-tests line stays (now true) |
| E13 | **Demo mode.** The fake AI scripts get a code-tests reply (one passing set, one with a failing test that is a code bug, one with a wrong test) so all of this can be tried at home |

## 3. Edge rules

- **No new library.** Evidence helper, report page, print and download use the standard library, Dash
  and what is installed. Coverage measuring stays out (needs a library: ask first, decided 14 Nov).
- Frozen requirement tests are never changed by D1 (E2).
- A code test can never turn a failing requirement test into a pass, and a code test is never written
  until the requirement tests pass (E4).
- The report shows **what ran**, never what was meant to run: values come from `results.json`, never
  from the AI's own words. A test with no evidence shows "Evidence not recorded", never made-up text.
- Values are cut at 500 characters each; anything that looks like a secret (the same patterns the
  index builder skips) is shown as `[hidden]`.
- Tests still run only in the server sandbox, never in the developer's folder (decided 3 Nov).
- Round budget stays 3 and shared (E5 uses it, it does not add rounds).

## 4. Acceptance criteria (Given / When / Then)

| ID | Given / When / Then |
|---|---|
| D1-1 | Given a test calling `evidence(self, "total", (2, 3), 5, 5)`, when the sandbox runs it, then `results.json` has one evidence line with input `(2, 3)`, expected `5`, actual `5`, match true |
| D1-2 | Given a test file where T-2 never calls `evidence(`, when Layer A checks it, then the retry note says "Test T-2 records no evidence" |
| D1-3 | Given a value of 2,000 characters, when recorded, then 500 are kept and the line is marked cut |
| D1-4 | Given the requirement tests fail, when the round ends, then no code tests are written |
| D1-5 | Given the requirement tests pass in demo mode, when the build goes on, then code tests C-1 to C-n are written (n ≤ 15), each with a Targets line, run in the sandbox, and shown under "Against the code" |
| D1-6 | Given a failing code test the fake Tester calls a code bug, when the round ends, then it counts as a failure, one round is used, and the test is kept for the next round |
| D1-7 | Given a failing code test the fake Tester calls a wrong test, when the round ends, then it is listed under "Dropped code tests" with the reason, no round is used, and the label is at best Ready with warnings |
| D1-8 | Given a finished build, when the report is saved, then `da_test_reports` has one new row, an audit event `test_report_saved` exists, and no earlier row changed |
| D1-9 | Given a saved report, when Open report is clicked, then a new tab shows the header, the summary and sections 1 and 2 with every test's evidence table; no server path appears on the page |
| D1-10 | Given the report page, when Download is pressed, then one HTML file named `CVDA-<id>-build-<n>-test-report.html` downloads and opens offline with the same content |
| D1-11 | Given the report page, when printed, then the app header, buttons and chat are hidden (print styles test on the component tree; visual check by Gian) |
| D1-12 | Given a build made before D1, when the Tests tab is drawn, then it says "No report for this build (built before 17 Nov)" and the old rows still show their results |
| D1-13 | Given a frozen test from before D1, when it runs in a new build, then its row says "Evidence not recorded (test written before 17 Nov)" and its pass still counts |
| D1-14 | Given an Enhance request, when the report is drawn, then section 3 lists the safety-net tests; for a Build new request section 3 is hidden |
| D1-15 | Given a value that looks like a secret, when recorded, then the report shows `[hidden]` |
| D1-16 | Given a handoff, when the PR summary is made, then it has the report summary lines and the report file name |
| D1-17 | Given the Admin Build and test tab, when drawn, then `TEST_FACTS` includes the test report line |

## 5. Choices (D-x). DECIDED: all option 1 (Gian, 17 Nov 20:26)

- **D-A Where evidence comes from:** 1. The `evidence(...)` helper inside each test (exact, works for
  any test). 2. Parse the assert line after the run (no help from the AI, but misses most values).
- **D-B A failing code test:** 1. The Tester judges code bug or wrong test (E5). 2. Every failing code
  test is a warning only (never blocks, label at best Ready with warnings). 3. Every failing code test
  blocks like a requirement test (risk: a wrong AI test blocks good code).
- **D-C Code test limit:** 1. Fixed 15 in code. 2. An Admin setting (adds an Admin field and tests).
- **D-D Report format:** 1. Report page with Print (to PDF via the browser) and Download HTML. 2. Also a
  real PDF file (needs a new library: ask first).
- **D-E When:** 1. Right after fix batch C, before Phase 11 fix 3. 2. After Phase 11 fix 3.

## 6. Out of scope

- Coverage measuring (needs a new library).
- The rest of batch B2 (items 1 + D2, 2, 3, 4, 6, 7, 8, 10, 16): a separate spec.
- "Review my code" (on hold). Director item D4 (rule versioning and rollback).
- Rewriting old frozen tests to add evidence.
