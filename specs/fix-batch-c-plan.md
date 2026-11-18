# Fix batch C: plan

Spec: `specs/fix-batch-c.md` v1.0. Branch `phase-c-fixes`. No product screen change, no new library.

Cause of P27 (found by reading `src/agents/da_sandbox.py`): on Windows the sandbox ends a run with
`taskkill /T /PID <runner>`. `/T` walks the tree from the parent. When the runner has already
exited (the normal end), the child is an orphan and `/T` cannot find it. A Job Object does not need
the parent: closing the job kills every process in it.

## Steps

0. Update "Current phase" in CLAUDE.md to Fix batch C (stays under 6,000 bytes).
1. **C1** (also removes the sandbox skip marker) `da_sandbox.py`: Windows branch only. `_Job` (ctypes, standard library): create a job,
   set `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, assign the runner after `Popen`. `_end_process_tree`
   closes the job on Windows (taskkill stays as the fallback if the job could not be made).
   The job is closed in the `finally` of `_run` (every path). Linux paths untouched. Linux proof:
   the CI job on the PR is green. SO-2 fallback: if still failing after 2 attempts, skip that one
   test on Windows only, reason "the sandbox runs on the Linux OCP server only (decided 3 Nov)",
   and say so in the PR; step 6 then records the skip reason instead of "closed". Proof: the sandbox child test passes on Windows; a small test that the
   job helper is only used when `os.name == "nt"`.
2. **C2 + C3** remove the skip marker of the sandbox child test (with C1) and of 8.42
   (`test_da_refine_e2e.py`); 8.42 waits for the "Picked:" line before clicking Apply. Proof: 8.42
   passes 5 times alone.
3. **C4** remove the 9.50 skip marker (`test_da_enhance_e2e.py`); the setup puts
   `ExpiryReport.build_line` in scope. Test only. Proof: 9.50 alone and in the full run, smoke check.
4. **C5** `ops/status_board.py`: `merged_record_path()` (`ops/state/merged_phases.json`, follows
   `DA_STATE_DIR`), `read_merged()`, `add_merged(phase)`, `seed_merged()` (writes
   `7, 8, 9, 10, 11a, 11b, 11c` only when the file is missing). `phase_facts`: merged when the branch
   check says so **or** the record lists it. `ops/chief_tick.py`: `tick` calls `seed_merged()` at
   start; `merge_pr` reads `headRefName` and, for `auto/phase-<name>`, calls `add_merged` after the
   merge. Proof (new ops tests): branch missing + record lists 7 -> board 100% (all merged); a merge
   through the helper adds its phase; a missing record is seeded; a fix branch merge adds nothing.
   The record stores text; `phase_facts` compares `str(phase)` (tests: 7 and "11a"). A phase is
   added only when its name is in `status_board.PHASES` (test with head `auto/phase-11-fix-1`);
   a PR info without `headRefName` adds nothing.
5. **C6** close #56, #57, #80, #81 with the fixing commits; relabel #74 `needs-work-test`.
6. **C7** `specs/parked-items.md`: P27 row says what was done.

7. Close: push, open the PR into `auto/phases-7-10`; the chief merges when checks are green and
   opens the `gian-later` issue "Fix batch C merged: ready for main" with the evidence.

Run limit: 3 plan steps per run; the rest continues in the next run.
Then: full pytest, ruff, smoke check, code review (max 3 rounds).

## Checks
- `.venv\Scripts\python -m pytest`, `ruff check .`, `src\da_smoke_check.py`.
