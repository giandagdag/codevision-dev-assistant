# Fix G3 plan: tests run with CodeVision's Python (spec `specs/fix-g-3.md`)

Branch `phase-g-fix-3`, PR into `auto/phases-7-10` (body from `logs/pr-body-g3.md`, `--body-file`).
Commit subjects "G3 step N". No new library. The ops idle files are not touched.

## Cause (read in the code)
`agents/da_sandbox.py::_run` starts the tests with `sys.executable` (the Developer Assistant's own
Python). `DA_CODEVISION_PYTHON` (`settings.codevision_python`) is only read by the work embedder.
Layer A (`da_build_checks._code_import_problems`) never asks whether an approved library is
installed where the tests run.

## Design (small, reuse what exists)
- New `agents/da_sandbox_python.py` (standard library plus `Settings` type only):
  - `TestPython` dataclass: `path`, `source` ("codevision" or "own"), `version` (tuple), `error`
    ("" when usable), with `label` ("CodeVision's Python 3.14.2" / "Developer Assistant's Python
    3.14.2", never a path) and `where` ("CodeVision .venv" / "Developer Assistant .venv").
  - `test_python(settings)`: `codevision_python` set and file exists -> use it; set but missing ->
    `error` "DA_CODEVISION_PYTHON points to a file that does not exist"; not set -> `sys.executable`
    (version read in-process, no call). Version for a set path: one `python -I -c` call, cached by
    (path, file mtime). Below 3.14 -> `error` naming the version.
  - `missing_libraries(python, names)`: ONE `python -I -c` call (importlib.util.find_spec on every
    name, 10 s limit, minimal environment) returning the names not found. NOT cached across builds
    (installing a library does not change python.exe's file time, so a cache would keep saying
    "missing" until a restart); one call per build / per Approach prompt. Decided by this plan: a
    call that fails or times out returns "none missing" (the real run then gives the Fix NP words).
    `sys.executable` skips the call and asks `find_spec` in-process.
  - A version call that crashes, times out or prints no version: `error` "could not read the
    version of the test Python" (no path), refused like a too-old version. Not cached.
- `run_tests(..., settings=None)`: asks `test_python(settings)`; an `error` returns the existing
  `LayerBResult(ran=False, error=...)` via `_could_not_start`, so no round is used (the callers
  already raise `_Paused` on `not ran`). `_run` takes the path. All callers pass `settings=...`:
  `da_build_loop` has FOUR calls (`_code_tests` ~687, `_trace_bug` ~718, `_layer_b` ~918,
  `_run_expected_tests` ~1370; all `self.settings`), plus `da_refine_bug._run_proof` and
  `da_safety_net_flow.sandbox_runner` (six in all). `settings=None` keeps `sys.executable` so old
  tests stay unchanged; to stop a silent fallback a guard test reads `src/` and asserts every
  `run_tests(` call passes `settings=`. A test per call site (build loop incl. expected-to-change,
  bug repro, safety net) proves the set path is the one started.
- Layer A stays plain code: `LayerAContext` gets `not_installed: frozenset[str] = frozenset()` and
  `python_where: str = ""`. `_layer_a` in the build loop fills them from `missing_libraries` over the
  approved list (one call per build, cached). `_code_import_problems`: an import that is approved
  and whose `library_name` is in `not_installed` gives the G3 sentence (with line number).
- T4: `format_policy(policy)` in `da_approach_agent.py` gets an optional `not_installed` set; the
  library line lists installed ones; a second line "Approved, not installed: do not use: ...".
  The caller computes it from `missing_libraries` with `settings`.
- T5: `MISSING_LIBRARY_TEXT` takes `{who}`; `pause_text(result, who=...)`; both prefixes are kept in
  `_SYSTEM_PREFIXES` ("CodeVision's Python is missing ", "The Developer Assistant's Python is
  missing ", AND the old "The server's Python is missing " kept: paused builds saved before G3
  hold it, e.g. CVDA-2026-0002; a test proves the old words still count as a system pause). `BuildView.tests_run_with` (new string field) is set in `get_build_view`; `build_tab`
  shows "Tests run with: <label>" as a small dimmed line.
- T6: `server_settings_view` gets one more row "Tests run with" (label, or the refusal text).
- T7: `docs/build-work-test.md` paragraph.
- Runner and evidence helper are not changed (already standard library only); a test asserts their
  imports stay stdlib (edge rule).
- Tests never start a real CodeVision Python: a fake interpreter is a small `.cmd`/shell script in
  `tmp_path` or `sys.executable` passed explicitly; `subprocess` is monkeypatched where a version
  or find_spec answer is needed.

## Steps
1. T1 + T2: `da_sandbox_python.py` (path choice, missing-file refusal, version check, cache),
   `run_tests(settings=)`, all six calls (four in the build loop, refine bug, safety net). Tests G3-1 (all four run kinds use the path),
   G3-2, G3-3 (refused, no round used), G3-4.
2. T3 + T4: `missing_libraries`, Layer A "approved but not installed" sentence, Approach prompt
   lines. Tests G3-5, G3-6, G3-7 (and that the AI gets the message in the next round's report).
3. T5 + T6 + T7: words with "who", Build tab line, Admin Overview row, work notes (incl. the old
   words on `docs/build-work-test.md` line ~103); update every existing test that names "The
   server's Python is missing" (search first; `test_da_load_errors*.py`). Tests G3-8, G3-9 (no path
   on screen). Existing Approach prompt tests may need `missing_libraries` faked (step 2).
Final gate: full pytest, ruff, smoke on the final commit; code review (max 3 rounds); PR.

## Out of scope
Installing libraries; changing the approved list; running tests on the OCP server.
