# Fix D1: plan

Spec: `specs/fix-d1-test-report.md` v1.0 (all D-x = option 1). Branch `phase-d1-test-report`.
No new library. Frozen tests are never rewritten. Values come from `results.json` only.

Found by reading the code (17 Nov): `TestOutcome` has no evidence (`da_build_models.py`); the runner
(`da_sandbox_runner.py`) writes name/result/message/tail only; `find_test_file_problems`
(`da_build_checks.py`) is used only by `write_tests`; `build_loop.py::_Run` runs Layer B and the
Tester review.

## Steps

0. Update "Current phase" in CLAUDE.md to Fix D1 (stays under 6,000 bytes).
1. **E1 + E3 (D1-1, D1-3, D1-15)** `agents/da_evidence_helper.py` (stdlib only): `evidence(test,
   label, given, expected, actual)` stores `repr()` cut at 500 (`cut` flag), match =
   `bool(expected == actual)` on the real objects (False if the compare raises). Keeps lines in a
   module list. SPEC DEVIATION (flagged for Gian): the spec says secrets use "the same patterns the
   index builder skips", but those are file-path patterns (`looks_secret`) and cannot judge a
   value. The helper copies the value patterns `_SECRET_PATTERNS` of `da_understand_checks.py` (it
   must stay stdlib only and stand alone) and a test fails if the two lists ever differ. Sandbox
   `_build_folder` copies the helper as `da_evidence.py` into the top folder (on the import path);
   tests import `from da_evidence import evidence`. The runner never hard-imports it: it reads
   `sys.modules.get("da_evidence")`, so old frozen tests record no lines. The runner clears the
   lines in `startTest` (not only in `_record`, which returns early for a second sub-test) and
   `_record` adds them to the row. Models: `EvidenceLine`, `TestOutcome.evidence` (default empty,
   so old saved rows load). Proof: helper unit tests; a real sandbox run gives `(2, 3)`, `5`, `5`,
   match true; 2,000 chars -> 500 and cut; `password=...` -> `[hidden]`; an old result without
   `evidence` loads; a failing sub-test followed by a second test does not leak lines.
2. **E2 (D1-2, D1-13)** `da_build_tests_prompt.md` tells the AI to import and call `evidence(...)`
   for every check; `find_test_file_problems` gets the AST rule "Test T-n records no evidence" (each
   `test_` method calls `evidence(`); `da_evidence` is an allowed import. The fake AI test files
   must pass the new rule: `_scripted_tests` in `da_build_agent.py` (`_VALIDATE_CHECK`,
   `_HIDDEN_CHECK`, `_EMPTY_CHECK`, including the `assertRaises` check, which records the raised
   error name) and `criterion_test_parts` in `da_enhance_build_script.py` are changed to call
   `evidence`. Existing fixtures `GOOD_TESTS` (`test_da_build_checks.py`) and the check at
   `test_da_build_agent.py` line ~129 are updated. Frozen tests already saved are not touched.
   Pure helper `evidence_note(outcome, test_text)`: "Evidence not recorded (test written before
   17 Nov)" only when the frozen test file has no `evidence(` call at all; otherwise plain
   "Evidence not recorded". Proof: Layer A test (T-2 without a call gives the exact retry note);
   the allowed import; both note texts; the full existing Build new and Enhance demo tests still
   pass.
3. **3a - E4 + E13 first half (D1-5 partly)** `agents/da_code_tests.py`: `CODE_TEST_LIMIT = 15`,
   prompt `data/da_build_code_tests_prompt.md`, `write_code_tests` (role "Tester"; reads contract,
   code, criteria), Layer A rules for code tests (`C-n` method names, a `Targets:` docstring line,
   at most 15, the evidence rule, same import and risky-call rules). Fake AI reply for the
   code-test prompt, built from the contract in the prompt so it works for Build new and Enhance
   (a passing set; a set with a failing test that is a code bug; a set with a wrong test). Proof:
   unit tests of the checks (good and bad files); the fake reply passes its own checks for a Build
   new and an Enhance contract.
3b. (next run) **E4 loop wiring + storage (D1-4, D1-5)**: `build_loop` calls `write_code_tests`
   only when `LayerBResult.ok`, runs the sandbox once more with its own 60 s, saves the code-test
   outcomes in a new `RoundRecord.code_tests` field (empty default, so old rows load) plus the
   dropped list. Proof: requirement tests fail -> no code-test call; demo -> C-1..C-n run.
3c. (next run) **E5 + E6 (D1-6, D1-7)**: new Tester call `judge_code_tests` (fake reply too) says
   code bug / wrong test + one line per failing C-test. A code bug is recorded as a Tester Must
   fix so the existing round-failure path is reused and the test is kept; a wrong test goes to
   `RoundRecord.dropped_code_tests` with its reason and `compute_label` (`da_tester_review`) caps
   the label at Ready with warnings. Proof: D1-6 and D1-7 in demo mode; a Refine rebuild writes a
   new set (E6).
4. **E7 (D1-8)** table `da_test_reports` (append-only; request ID, build number, round, JSON body,
   created at), db functions, audit event `test_report_saved`, saved when a round that reached
   Layer B ends. Proof: one row, one audit event, earlier rows unchanged.
5. **E8** `agents/da_test_report.py`: builds the report body from saved results (header with
   fingerprints, models, SGT time, Python version; summary per layer; sections 1 to 3; Tester's 7
   checks and findings; asterisk legend). Proof: tests with made-up results, section 3 only for
   Enhance (D1-14), a build with no evidence shows "Evidence not recorded".
6. **E9 (D1-9, D1-10, D1-11)** Dash page `/dev-assistant/report/<request_id>/<build_no>`, read
   only, no server path, Print button plus print styles, Download button
   (`CVDA-<id>-build-<n>-test-report.html`, self-contained). Proof: component-tree tests; the
   downloaded text has the same content; no path on the page; print styles hide chrome.
7. **E10 (D1-12)** Tests tab: summary line, "Open report" link, two groups, Evidence column
   (expandable), "No report for this build (built before 17 Nov)" for old builds.
8. **E11 + E12 (D1-16, D1-17)** handoff PR summary gets the summary lines and the file name;
   `TEST_FACTS` gets "Every build saves a test report: input, expected, actual, pass or fail".
9. Close: full pytest, ruff, smoke check, code review (max 3 rounds), push, PR into
   `auto/phases-7-10` (do not merge; CI is red from GitHub billing).

Run limit: 3 plan steps per run. This run builds steps 1, 2 and 3a (step 0 is not a build step);
the next run continues from step 3b.

## Checks
- `pytest`, `ruff check .`, `src/da_smoke_check.py`.
- Visual print check (D1-11) is Gian's; the test covers the print styles on the component tree.
