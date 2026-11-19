# Fix NP plan: a test file that cannot load must say why

Spec: `specs/fix-not-proven-spec.md` v1.0 (approved 19 Nov, no open D-x). Branch `fix-not-proven`
(cut from newest `origin/auto/phases-7-10`). PR into `auto/phases-7-10`; the chief merges. Never
main. Commit subjects say "NP step N". At most 3 steps per run; each step: tests, commit, push to
`fix-not-proven`. Tests use fakes and `tmp_path` only (no real AI, no internet). No new library, no
new status. The frozen tests are never changed. CLAUDE.md "Current phase" gets one line in step 1
(file stays under 6,000 bytes). Pytest in small groups per step, full run once at the end.

Plain-words picture (AS400): today the batch job log shows "7 messages, 0 good" when the program
object could not even be loaded (like a CALL that fails on a missing library in the library list).
After NP the log says "library X not found" once, names whose fault it is, and does not count the
tests that never started.

Facts read in the code (19 Nov): `da_sandbox_runner._name()` stores a stand-in's own name;
`da_sandbox._read_results` turns every expected method with no outcome into `not_proven` only when at
least one outcome exists; `da_build_loop._record_round` pauses with `NOT_PROVEN_TEXT` when
`layer_b.not_proven` is non-empty, `_rounds_used` skips such rows, `_retry_unproven` adds a new round
row (new Layer A and B progress lines) on Resume; `da_check_words` holds the F3 words.

## Steps (build order)

1. **N1 load failures are named (model + runner + sandbox).**
   - `da_build_models.py`: add result kind `not_run` to `TestResultKind`; new `LoadError` model
     (`kind` one of `import`, `set_up`, `other`; `error_type`, `message`, `traceback_tail`);
     `LayerBResult.load_error: LoadError | None = None` (old saved rows still load). `ok` stays
     false when `load_error` is set; `passed`/`failed` unchanged; new property `ran_count` (frozen
     tests that reported pass, fail or error only).
   - `da_sandbox_runner.py` (standard library only): when `test` is a `_FailedTest`, `_ErrorHolder`
     or its name starts with `setUpClass`/`setUpModule`/`tearDownClass`/`tearDownModule`, record
     the row with extra keys `"standin": "import"` or `"set_up"` and `"error_type"`. Type is
     checked first, name prefix second.
   - `TestOutcome` has `extra="forbid"` and `_read_outcomes` swallows `ValueError`, so a new key
     would hide every row. Fix: `_read_outcomes` pops `standin` and `error_type` from each raw row
     before `model_validate` and returns them beside the outcome. A test proves the rows still load.
   - `da_sandbox._read_results`: stand-in rows leave `tests` and the first one becomes `load_error`
     (more than one is allowed; later ones are ignored). ONLY expected frozen methods with no real
     outcome become `TestOutcome(result="not_run", message="Did not run: the test file could not
     load")`; real rows (for example tests that passed before a failing `tearDownClass`) are kept.
     Without any stand-in row, today's `not_proven` path stays (NP-6).
   - Tests (`tests/test_da_sandbox_load_error.py`, real subprocess on `tmp_path`): NP-1 sandbox part
     (missing import), setUpClass raise, `tearDownClass` fails after passes (real rows kept),
     real Not proven unchanged (NP-6).
2. **N2 whose fault, decided from the error.**
   - New `agents/da_load_errors.py`: `classify_load_error(load_error, reference_src, planned_paths)`
     returns `missing_library`, `planned_code` or `frozen_test`. `ModuleNotFoundError` is
     `planned_code` when the missing name's last dotted part equals the name of any planned file
     (wrong path, e.g. `excel_x` instead of `agents.excel_x`), or its top module exists in the
     reference `src/` (e.g. `agents.nothing`), or on `cannot import name` from a planned module.
     Otherwise (top module not in `src/`, not a planned file) → `missing_library`. `set_up` kind or an error in the test file itself → `frozen_test`.
     Words (constants in `da_check_words.py`): "The server's Python is missing `<module>`. This
     needs the CodeVision team, not a code change."; "A frozen test cannot run: <message>".
   - The class is worked out once and saved: `LoadError.fault` (`missing_library`, `planned_code`,
     `frozen_test`), set by `_layer_b` in `da_build_loop.py` (which knows reference src and planned
     paths) right after the sandbox returns. Later code only reads the field, so `_rounds_used`
     needs no extra arguments and old rows without it read as `planned_code`.
   - `da_build_flow.py` line 288 (`state.message in SYSTEM_FAILURE_MESSAGES`, exact match) switches
     to `is_system_failure(message)`, with a test (NP-8: Get help offers Send to my senior).
   - N5 choice (decided): the Resume re-run of the same round REPLACES its rows (same Layer A and
     Layer B line numbers, newest row wins); nothing is deleted from the audit trail.
   - One shared check `is_system_pause(layer_b)` (true for Not proven rows, or a load error
     classed `missing_library` or `frozen_test`), used in all four places: `_record_round` (the
     `unproven` flag), `_rounds` and `_check_run` (the Run-again-on-Resume branch, so a second
     Resume never calls the AI and uses no round), and `_rounds_used`. Pause text is the new
     sentence; `_pause` (line 350) and `SYSTEM_FAILURE_MESSAGES` use a prefix check (one helper
     `is_system_failure(message)` in `da_check_words.py`) so the new texts are not wrapped in "The
     build paused:" and Get help offers Send to my senior. `planned_code` is a normal failure,
     one round used.
   - `da_build_checks.py` (`build_failure_report`, `choose_files_to_fix`, `_files_from_tracebacks`):
     with a `planned_code` load error, add one failure item built from `load_error` and read its
     traceback tail for the file to fix, so the next prompt holds the import error (NP-2).
   - Tests: NP-1 loop part (no round used, chat sentence, then Resume twice: fake AI never called,
     no round used), NP-2 (wrong function name, and wrong path in both directions), NP-3, all with
     a fake client and fake sandbox result.
3. **N3 always show the reason (with `<sandbox>`).**
   - New `hide_sandbox(text, root_hint)` in `da_load_errors.py`: replaces only the folder at the start
     of a path (the temporary folder `da_sandbox_*`, the reference dir) with `<sandbox>` and keeps
     the part after it (`<sandbox>/src/agents/x.py`), so `_files_from_tracebacks` still finds the
     file; any other absolute path becomes `<sandbox>/<file name>`. Secrets become `[hidden]` by
     calling `hide_secret` from `da_evidence_helper.py` (D1) one line at a time (it blanks the
     whole text it is given); no new copy of the patterns.
     Applied when the result is saved (message and last 20 traceback lines) so nothing unsafe is
     stored or shown.
   - `layouts/da_build_panel.py`: add `not_run` to `RESULT_TEXT` ("Did not run") and
     `RESULT_COLOUR`. Build tab and the Tests tab: under the Layer B row, show the
     load error or each Not proven row's message and traceback tail. Get help / Send to my senior
     text (find with Grep `SEND_TO_SENIOR_LABEL`) starts with the missing-module sentence and
     includes the tail.
   - Tests: NP-4 (component text has `<sandbox>`, no `da_sandbox_` or drive path), NP-6 reason
     shown, NP-8 help text.
4. **N4 counts + N5 Resume without duplicate rows.**
   - Layer B row text (`_record_round` note in `da_build_loop.py`, `_layer_b_state` in
     `layouts/da_build_panel.py`, round summaries): with a load error,
     "0 of 6 ran: the test file could not load"; otherwise count frozen tests only. Stand-in rows
     never counted (`ran_count`).
   - `_retry_unproven` and the Resume path: the re-run of the same round reuses that round's Layer A
     line (no second "Layer A" note) and replaces its Layer B line (same line number, newest row
     wins, as `_note` already allows) or is labelled "Round N, try 2". Cause is confirmed with a
     failing test first. Nothing is deleted from the audit trail or `rounds` table.
   - Tests: NP-5 (resume twice, checklist has one Layer A and one Layer B per round), NP-4 counts.
5. **N6 test report + N7 work notes.**
   - `da_test_report.py` / `da_test_report_view.py`: summary line "Load error" and its own line in
     section 1 (message + tail, redacted), never counted as Not proven. Old saved reports still
     render.
   - `docs/build-work-test.md`: one short section: after the merge resume `CVDA-2026-0002` at work,
     expect the real reason (likely missing `openpyxl`/`pandas`, told to the CodeVision team) or
     real results.
   - Tests: NP-7; a test that the doc section exists is not needed.

## Test map

| Criterion | Step |
|---|---|
| NP-1 | 1, 2 |
| NP-2, NP-3 | 2 |
| NP-4, NP-8 | 3 |
| NP-5 | 4 |
| NP-6 | 1, 3 |
| NP-7 | 5 |

## After the last step

Full pytest, `ruff check .`, smoke check, then `code-reviewer` (max 3 rounds), then PR into
`auto/phases-7-10`. Known risk: a stand-in row name differs by Python version; the runner decides
from the object type first and the name prefix second, and step 1 tests run on the real 3.14.
