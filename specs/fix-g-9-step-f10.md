# Fix G9 finish step F10: safe column upgrades, then merge

Version 1.0 APPROVED, 28 Nov 2026 11:05 SGT, under Gian's standing go (27 Nov 16:19 and
28 Nov 01:01: "full authority to do what needs to be done"). Same branch `phase-g-fix-9`, same PR
#118. Builder: commit this file as `specs/fix-g-9-step-f10.md` first. Commit subjects
"G9 finish step F10". Push **only** to `phase-g-fix-9` (never `auto/phase-g-fix-9`).

## What CI showed (28 Nov, commit f242de4)

| Run | Result | Failing test | Cause |
|---|---|---|---|
| 46041190037 (push) | pass | - | - |
| 46041199203 attempt 1 (PR) | 1 failed, 4,548 passed | `test_da_capability_map_browser.py::test_click_on_empty_space_clears_the_focus` (G6) | Browser timing on the CI runner (flaky) |
| 46041199203 attempt 2 (PR) | 1 failed | `test_da_g9_inbox_browser.py::test_g9_3_the_senior_rejects_an_exception_on_the_inbox_scr...` | **Real bug:** `sqlite3.OperationalError: duplicate column name: impact` in `db_tbl_da_discovery._add_impact_column`, reached through `ensure_build_tables` from a Dash callback (HTTP 500) |

**Cause of the real bug.** Every `ensure_*_tables` reads `PRAGMA table_info`, then runs
`ALTER TABLE ... ADD COLUMN` if the column is missing. Dash runs callbacks in parallel threads, each
with its own connection. When two callbacks start on a fresh database, both see the column missing
and both run ALTER: the second one crashes. It has been there since Phase 9. G9's new browser tests
fire callbacks together, so CI now hits it. On the OCP server with several developers it could
crash the first screen actions after an upgrade, so it must be fixed before work use.

## F10a. One safe helper for every column upgrade

- New `add_column_if_missing(conn, table, column, definition)` in `src/db_table_functions/da_db.py`
  (or the existing shared DB module). It runs the ALTER, and treats
  `sqlite3.OperationalError` whose message contains "duplicate column name" as done (another
  connection added it first). Any other error is raised as before. Table and column names come
  only from code constants (never user text); assert they are plain identifiers.
- Replace all 10 hand-written `ALTER TABLE ... ADD COLUMN` sites with the helper:
  `db_tbl_da_approach.py` (index_build), `db_tbl_da_discovery.py` (impact, index_build),
  `db_tbl_da_build.py` (code_tests, dropped_code_tests, referee_only, kind),
  `db_tbl_da_enhance.py` (resolved_capability), `db_tbl_da_requests.py` (follows_request_id),
  `db_tbl_da_refine.py` (the loop over test-set columns). Keep each column's type and default.
- `grep -rn "ADD COLUMN" src` afterwards finds only the helper.

Tests (plain, no browser):
- **F10-1:** an old-shape database without `impact`; two threads, each with its own connection,
  call `ensure_build_tables` at the same moment (a `threading.Barrier`), 20 repeats: no error, the
  column exists once.
- **F10-2:** the helper raises on any other OperationalError (for example a missing table).
- **F10-3:** calling every `ensure_*_tables` twice on the same database is still fine.

## F10b. The G6 map test flake

Do not change the test now. Add it to `specs/parked-items.md` as Low: "G9-c: on the CI runner,
`test_click_on_empty_space_clears_the_focus` failed once on timing (run 46041199203 attempt 1),
passed in the other runs. Fix: wait for the map's tap handler before clicking, when it flakes
again."

## F10c. Finish

1. Run the database tests, the G9 browser test files, and the full suite in groups that fit the
   time limit, on one commit. ruff and smoke check.
2. Push to `phase-g-fix-9`. Both PR #118 checks must be green on the new commit. If one fails on
   a test with no relation to F10 and the other run of the same commit passed, re-run once.
3. The chief merges PR #118 into `auto/phases-7-10`, closes #120 and #121, marks Fix G9 done in
   `ops/work_queue.json`, sets Next to none and goes idle (nothing else is approved yet).
