# Fix NP: a test file that cannot load must say why (never "0 of 7, Not proven")

Version 1.0 APPROVED, 19 Nov 2026 08:05 SGT. Gian: "start it. i give you full approval on what needs
to be done." Written in the project chat (project doc `claude/parked-bug-not-proven-0-of-7.md`) from
Gian's work test of 18 Nov. All choices below are decided; no D-x is open.

Branch `fix-not-proven`, cut from the newest `origin/auto/phases-7-10` (B1, Phase 11 fix 1 to 3,
batch C, D1 and B2 are all merged there). PR into `auto/phases-7-10`; the chief merges it. Build it
the normal way: plan `specs/fix-not-proven-plan.md` (a `## Steps` list), plan review, small steps with
tests, code review (max 3 rounds), full pytest, ruff, smoke check. Commit subjects say "NP step N".
Builder: commit this spec file as the first commit on the branch (it was written to disk untracked).

## 0. What happened at work (18 Nov, CVDA-2026-0002, Excel to Markdown Conversion Module)

- Tester wrote **6** frozen tests. AI wrote `excel_to_markdown_agent.py`. Layer A passed.
- Layer B: **"0 of 7 tests passed"**, and the build paused with the F3 text ("This is a problem in the
  Developer Assistant, not in your code"). Resume build: same result at once. After Resume the
  Layer A and Layer B rows are shown **twice** in the Build checklist.
- Gian cannot see server logs or the sandbox folder at work, so he could not find the reason.

## 1. Cause (read in the code on 19 Nov, `auto/phases-7-10`)

- `agents/da_sandbox_runner.py` `main()` uses `unittest.TestLoader().discover(...)`. When the test
  module **cannot be imported**, unittest adds one stand-in `_FailedTest` whose `_testMethodName` is
  the **module name**. A failing `setUpClass` / `setUpModule` gives an `_ErrorHolder` with a name like
  `setUpClass (tests...)`. `_name()` records those names as they are.
- `agents/da_sandbox.py` (result builder after the run): when `results.json` has at least one outcome,
  every expected method with no outcome becomes `not_proven`. So 1 stand-in error row + 6 Not proven =
  **7 rows, 0 passed**.
- `agents/da_build_loop.py` then treats any `not_proven` as the app's own problem (F3): no round used,
  AI not told, the real error text (already in the stand-in row) hidden behind the F3 message.

Likely real reasons for an Excel feature: the sandbox Python lacks a library the tests or code import
(`openpyxl`, `pandas`), or the tests import the written module by a path that does not match where it
was placed under `src/`. The D1 evidence helper is copied, so it is not the cause.

## 2. What we build

| # | Piece |
|---|---|
| N1 | **Load failures are named.** In `da_sandbox.py`, a recorded outcome whose name is not one of the expected method names and that comes from unittest's stand-ins (`_FailedTest`, `_ErrorHolder`, `setUpClass`, `setUpModule`, `tearDownClass`, `tearDownModule`) becomes one `LayerBResult` field `load_error` (kind, message, traceback tail). The frozen tests then get a new result `not_run` with message "Did not run: the test file could not load" (not `not_proven`). `ok` stays false. The runner itself may also record the stand-in's kind explicitly, standard library only |
| N2 | **Whose fault, decided from the error.** `ModuleNotFoundError`/`ImportError` naming a module that is **not** in the reference `src/` tree and not a planned file: "The server's Python is missing `<module>`. This needs the CodeVision team, not a code change." Ends like F3 (no round used) and Get help offers Send to my senior. Import error naming a **planned file** or a name inside it (wrong function or class name, wrong path): a normal failure; the AI gets the message in the next round; one round used. Error inside the frozen test's own code (not an import of the planned code): "A frozen test cannot run: <message>" + Send to my senior; frozen tests are never rewritten silently |
| N3 | **Always show the reason.** Every load error and every Not proven row shows the message and the traceback tail (last 20 lines, server paths and the temporary folder replaced by `<sandbox>`, secrets `[hidden]` with the same patterns D1 uses) under the Layer B row of the Build tab and in the Tests tab, and it goes into the Get help and Send to my senior text. No server path ever shown |
| N4 | **Counts.** The Layer B row counts frozen tests only: "0 of 6 ran: the test file could not load" instead of "0 of 7 passed". A stand-in row never adds to the count |
| N5 | **Resume does not duplicate rows.** After Resume build, the checklist shows each round's Layer A and Layer B once; a re-run of the same round replaces its rows (or is labelled "Round 1, try 2"). Nothing in the audit trail is deleted |
| N6 | **Test report (D1).** A load error appears in the report summary and as its own line in section 1, not as Not proven |
| N7 | **Work test notes.** One short section in `docs/build-work-test.md`: resume `CVDA-2026-0002` at work after the merge and expect the real reason (or real results) |

## 3. Edge rules

- No new library. Tests still run only in the server sandbox, never in the developer's folder.
- Real Not proven (a method ran nowhere and no stand-in explains it) keeps today's F3 behaviour, now
  with the reason shown (N3).
- Frozen tests are never changed by this fix.
- Never touch `main`.

## 4. Acceptance criteria (Given / When / Then)

| ID | Given / When / Then |
|---|---|
| NP-1 | Given a frozen file that imports a module the sandbox does not have, when Layer B runs, then `load_error` names the module, the 6 frozen tests are `not_run`, the row says "0 of 6 ran: the test file could not load", the chat says the server's Python is missing it, and no round is used |
| NP-2 | Given a frozen file that imports a function the written code does not define, when Layer B runs, then it is a normal failure, one round is used, and the next build prompt holds the import error |
| NP-3 | Given a frozen file whose `setUpClass` raises, when Layer B runs, then the reason is "A frozen test cannot run: <message>" and Get help offers Send to my senior |
| NP-4 | Given any load error or Not proven row, when the Build and Tests tabs are drawn, then the message and traceback tail show with `<sandbox>` instead of any server path |
| NP-5 | Given a paused build, when Resume build re-runs the same round, then the checklist shows that round's Layer A and Layer B once (or labelled try 2), never two identical rows |
| NP-6 | Given a test method that truly reports nothing and no stand-in row, when Layer B ends, then today's Not proven and F3 behaviour stays, with the reason text shown |
| NP-7 | Given a load error, when the D1 test report is saved, then the report shows it as a load error, not as Not proven |
| NP-8 | Given the Get help text after NP-1, then it starts with the missing-module sentence and offers Send to my senior |

## 5. Out of scope

- Installing libraries on the work server (a CodeVision team task once NP-1 names the module).
- `phase-board-queue-2` leftover commit (board step counting).
