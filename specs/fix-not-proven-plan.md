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
     the row with extra key `"standin": "import"` or `"set_up"` and the exception type name.
   - `da_sandbox._read_results`: split the outcomes into real rows and the one stand-in row. The
     stand-in row becomes `load_error` (not a `tests` row) and every expected frozen method becomes
     `TestOutcome(result="not_run", message="Did not run: the test file could not load")`. Without
     a stand-in row, today's `not_proven` path stays (NP-6). `_read_outcomes` ignores the extra key
     safely (model allows it through a runner-only field list).
   - Tests (`tests/test_da_sandbox_load_error.py`, real subprocess on `tmp_path`): NP-1 sandbox part
     (missing import), setUpClass raise, real Not proven unchanged (NP-6).
2. **N2 whose fault, decided from the error.**
   - New `agents/da_load_errors.py`: `classify_load_error(load_error, reference_src, planned_paths)`
     returns `missing_library`, `planned_code` or `frozen_test`. `ModuleNotFoundError` naming a top
     module that is not a folder or file under the reference `src/` and not a planned file →
     `missing_library`. Import error naming a planned module, or `cannot import name` from one →
     `planned_code`. `set_up` kind or an error in the test file itself → `frozen_test`.
     Words (constants in `da_check_words.py`): "The server's Python is missing `<module>`. This
     needs the CodeVision team, not a code change."; "A frozen test cannot run: <message>".
   - `da_build_loop._record_round`: `missing_library` and `frozen_test` pause like F3 (no round used,
     AI not told, `_rounds_used` skips them, the pause text is the new sentence, kind marked as the
     Developer Assistant's own so Get help offers Send to my senior). `planned_code` is a normal
     failure: failure report carries the import error text, one round used, next prompt holds it.
     `SYSTEM_FAILURE_MESSAGES` check becomes a prefix/classify check so the new texts count.
   - Tests: NP-1 loop part (no round used, chat sentence), NP-2, NP-3 with a fake client and fake
     sandbox result.
3. **N3 always show the reason (with `<sandbox>`).**
   - New `hide_sandbox(text, root_hint)` in `da_load_errors.py`: replaces the temporary folder name
     (`da_sandbox_*`), the reference dir, and any absolute path with `<sandbox>`; secrets become
     `[hidden]` using the same patterns D1 uses (reuse the D1 helper found by Grep, no new copy).
     Applied when the result is saved (message and last 20 traceback lines) so nothing unsafe is
     stored or shown.
   - `layouts/da_build_panel.py` (Build tab) and the Tests tab: under the Layer B row, show the
     load error or each Not proven row's message and traceback tail. Get help / Send to my senior
     text (find with Grep `SEND_TO_SENIOR_LABEL`) starts with the missing-module sentence and
     includes the tail.
   - Tests: NP-4 (component text has `<sandbox>`, no `da_sandbox_` or drive path), NP-6 reason
     shown, NP-8 help text.
4. **N4 counts + N5 Resume without duplicate rows.**
   - Layer B row text (`_record_round` note, `_layer_b_state`, round summaries): with a load error,
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
