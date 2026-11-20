# Fix G3: tests run with CodeVision's own Python (DA_CODEVISION_PYTHON)

Version 1.0 APPROVED, 20 Nov 2026 (20:10 SGT). Written in the project chat from Gian's work test of
20 Nov (CVDA-2026-0002). Gian gave full approval for fixes (19 Nov 23:22) and reported this one at
19:58. All choices below are decided; none is open.

Branch `phase-g-fix-3`, cut from `auto/phases-7-10` after PR #109. Plan `specs/fix-g-3-plan.md` with a
`## Steps` list, plan review, small steps with tests, commit subjects "G3 step N", code review (max 3
rounds), full pytest, ruff and smoke check on the final commit, PR into `auto/phases-7-10`; the chief
merges it when CI is green, then sets Next to `idle: queue empty after Fix G3`. No new library.

**How to open the PR:** write the body to `logs/pr-body-g3.md`, then one plain line:
`gh pr create --base auto/phases-7-10 --head phase-g-fix-3 --title "Fix G3: tests run with CodeVision's Python" --body-file logs/pr-body-g3.md`

## 0. What happened at work (20 Nov 16:30 and 19:58)

- Resume build on CVDA-2026-0002 (Excel to Markdown). Fix NP worked: the screen said "The server's
  Python is missing `openpyxl`". The AI's file does `from openpyxl import load_workbook`.
- **openpyxl IS installed in CodeVision's `.venv`.** Gian's `.env` has
  `DA_CODEVISION_PYTHON=...\CodeVision_v61\.venv\Scripts\python.exe` and `DA_SANDBOX_SOURCE_DIR`
  set to CodeVision's source. He restarted the app: same result.
- Cause (read in the code): `agents/da_sandbox.py::_run` starts the tests with `sys.executable`, the
  Python running the **Developer Assistant app** (its own `.venv`, no openpyxl). `DA_CODEVISION_PYTHON`
  is only used by the work embedder (`da_admin_rebuild.py`, `da_code_index.py`). The Layer A import
  check (`da_build_checks.py::_code_import_problems`) only compares names with the approved list; it
  never asks whether the library is installed where the tests run.
- **The developer must not install libraries twice.** CodeVision's code must be tested with
  CodeVision's Python and libraries.

AS400 comparison: the right source, but the job was submitted with the wrong library list.

## 1. What we build

| # | Piece |
|---|---|
| T1 | **Test Python.** New `agents/da_sandbox_python.py::test_python(settings) -> TestPython` (path, where it came from: `DA_CODEVISION_PYTHON` or "the Developer Assistant's own Python", and its version). `DA_CODEVISION_PYTHON` set and the file exists: use it. Set but missing: refuse the run with "DA_CODEVISION_PYTHON points to a file that does not exist" (no silent fallback). Not set: `sys.executable`, as today (home and old setups unchanged). Every sandbox run (requirement tests, code tests, bug repro, safety net) uses it; the flags (`-I`, the empty environment) stay |
| T2 | **Version check.** Before the first run, ask the test Python for its version (one quick call, cached per path and file time). Below 3.14: refuse with the version in the message |
| T3 | **Installed check in Layer A.** For each import that passed today's rules and is not the standard library, a CodeVision module or a planned file: ask the test Python whether it can find it (`importlib.util.find_spec`, one call per build for all names, standard library only, 10 s limit). Not found: a Layer A problem "Line N: '`openpyxl`' is approved but not installed in CodeVision's Python (<path shown as `CodeVision .venv`>). Pick an installed library or ask the CodeVision team." That is a normal Layer A failure the AI can fix in the next round |
| T4 | **Approach knows what is installed.** The Approach prompt's library line lists only approved libraries that the test Python has (same check, cached); approved but missing ones are listed separately as "approved, not installed: do not use" |
| T5 | **Clear words.** The Fix NP message (`da_check_words.py`) names which Python: "CodeVision's Python is missing `x`" when `DA_CODEVISION_PYTHON` is used, "The Developer Assistant's Python is missing `x`" otherwise. Build tab shows a small line "Tests run with: CodeVision's Python 3.14.x" (never the full path) |
| T6 | **Admin Overview.** The settings check already lists `DA_CODEVISION_PYTHON`; add "Tests run with" and the version |
| T7 | **Work notes.** `docs/build-work-test.md`: tests use `DA_CODEVISION_PYTHON` when set; no second install in the Developer Assistant's `.venv` |

## 2. Edge rules

- The sandbox runner and the D1 evidence helper must stay standard library only (they now run in
  CodeVision's Python, which has no Developer Assistant libraries).
- No server path in the app: show "CodeVision .venv" or "Developer Assistant .venv".
- Tests never start a real CodeVision Python: use a fake interpreter path made in a temp folder (a
  small script) or `sys.executable` passed explicitly.

## 3. Acceptance criteria

| ID | Given / When / Then |
|---|---|
| G3-1 | Given `DA_CODEVISION_PYTHON` set to an existing Python, when a sandbox run starts, then the command uses that path (all four run kinds) |
| G3-2 | Given it is not set, then `sys.executable` is used, as today |
| G3-3 | Given it points to a missing file, then the run is refused with the plain message and no round is used |
| G3-4 | Given a test Python older than 3.14 (fake), then the run is refused with its version |
| G3-5 | Given code importing an approved library that the test Python cannot find, when Layer A runs, then it fails with "approved but not installed in CodeVision's Python" and the AI gets the message next round |
| G3-6 | Given the same library installed, then Layer A passes it |
| G3-7 | Given the Approach prompt, then it lists installed approved libraries and "approved, not installed: do not use" for the others |
| G3-8 | Given a load error for a missing module with `DA_CODEVISION_PYTHON` set, then the message says "CodeVision's Python is missing" |
| G3-9 | Given the Build tab, then it shows "Tests run with: CodeVision's Python 3.14.x" and no path |
| G3-10 | Given the final commit, then the PR shows the full pytest count, ruff clean and smoke passed |

## 4. Out of scope

- Installing libraries anywhere. Changing the approved list. Running tests on the OCP server.
