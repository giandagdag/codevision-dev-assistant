# Fix batch B1 plan: trust fixes + real CodeVision index

Spec: `specs/fix-b1-trust.md` v1.0 (approved by Gian 14 Nov). Branch `phase-b1-fixes` (from
`auto/phases-7-10`). PR into `auto/phases-7-10`; the chief merges. Never main. Runs of 3 steps; each
step: tests, commit, push. Tests use fakes and `tmp_path` only. No new database tables (F2 reads the
expected test names from the frozen test text, spec section 4). New libraries only in step 14
(`faiss-cpu==1.12.0`, `numpy==2.4.1`, approved). CLAUDE.md "Current phase" gets one line in step 1.

Plain-words picture (AS400): the test runner is a job log. Today it logs only some message types, so a
test that sent an unlisted message left no line, and the job still ended "normal". F1/F2 make the
log complete and make "normal end" mean "every expected line is there".

## Steps (build order of spec section 6)

1. **F1 runner records every outcome.** `agents/da_sandbox_runner.py`: add `addExpectedFailure`
   (`expected_failure`), `addUnexpectedSuccess` (`unexpected_success`), `addSubTest` (a failing
   sub-test: parent `fail` with the sub-test message, once; all sub-tests pass: `pass` once, no
   duplicate with `addSuccess`). `TestResultKind` gains the three new kinds (+ `not_proven`, step 2).
   Test: run the real runner on a made-up test file with each outcome (B1-1, B1-2).
2. **F2 pass means proven.** `LayerBResult` gets `expected: list[str]`; property `not_proven` (expected
   names with no result); `ok` needs ran, no timeout, expected all reported and every result `pass`
   (an empty `expected` keeps today's rule for old records and the safety-net caller). `run_tests`
   fills `expected` from the frozen test text (`find_test_methods`). `failed` counts only fail/error,
   as today; the panel count line says "N of M passed". Test: 8 expected, 5 results (B1-3 model
   part), all pass (B1-4).
3. **F3 Not proven is the system's problem.** `agents/da_build_loop.py`: when a round's Layer B has
   `not_proven`, record the round (rows show), then end like an interrupted run: step
   `b_interrupted`, no repair round used, chat text from a constants place. `layouts/da_build_panel.py`
   draws the "Not proven: no result recorded" row in orange. Check callers of `_record_round` so the
   loop stops (also in the Check-my-edits path). Test: fake sandbox returning 5 of 8 (B1-3).
4. **F4 contract reads fields.** `_class_args` in `agents/da_build_checks.py`: `__init__` args when
   present, else annotated class-level fields of a class that is a Pydantic model or dataclass (base
   `BaseModel`, or a `@dataclass` decorator), without `ClassVar` and `_` names. Test: B1-5.
5. **F5 Get help says whose fault.** A `system` flag on the failure (F3 and checks flagged
   `system=True`); Get help text starts with the constant line and offers Send to my senior. Test: B1-6.
6. **F6 never rewrite his test silently.** Tester answers `CONFLICT AC-n: why`; plain code shows the
   chat text and two buttons; nothing stored until he picks; fake Tester `conflict` switch. Test: B1-7.
7. **F8 log empty replies.** `_read_reply` in `agents/da_llm_client.py` reads `finish_reason`; empty
   content logs model, reason, token counts, first 2,000 characters; error names the reason. Test: B1-9.
8. **F7 no silent practice index at work + demo banner.** Onprem + search `fake`: Discovery says "No
   CodeVision index is connected yet..." and carries on; `fake` LLM provider: banner on every page.
   Test: B1-8.
9. **F9 work rulebook.** `data/da_rulebook_seed_work.json`, loader choice by `DA_LLM_PROVIDER`,
   `--refresh-purpose`. Tests on a copy only. Test: B1-10.
10. **F11 update what the DA wrote.** B4 in `agents/da_workspace_checks.py` allows `create` on an
    existing file whose text matches the last `WrittenFile` fingerprint (action becomes `modify`);
    edited since: Keep mine / Take the AI's. Test: B1-12, B1-13, B1-14.
11. **F12 busy text per action.** One constant table; each waiting button has its own line. B1-15.
12. **F10 Home always works.** Find the cause first (spec section 3, say which lead it was), Playwright
    test (skipped with no browser), then fix. SO-2 applies: park after 2 failed attempts, `gian-later`.
13. **I1 embedder interface** `agents/da_code_index.py` (`FakeEmbedder`, `WorkEmbedder`).
14. **I2 + I3 build command** `src/da_build_code_index.py`, saved together or not at all, 10% rule.
    Needs `faiss-cpu`, `numpy` in `requirements.txt`. B1-16, B1-17.
15. **I4 + I5 `CodeVisionSearchIndex`** replaces the placeholder: exact (shared word matching),
    meaning (`index.search` ourselves, distance limit, filters after), honest when missing, embedding
    failure falls back to exact. B1-18 to B1-21.
16. **I6 smoke check item + I7 docs** (`docs/discover-work-test.md`; new parked item "Admin Rebuild
    index button" in `specs/parked-items.md`).

(Steps 13 to 15 are three plan steps; step 16 is small. Each run builds at most 3.)

## Plan review round 1: changes taken in (Must fix 1, Should fix 6)

- Step 1 also edits CLAUDE.md "Current phase" (one line, size test kept green).
- Step 5: only F3 sets `system` for now; no other existing check is flagged.
- Step 6: **Change what it does** opens the requirement lane with his test text as start;
  **Change my test** keeps the AI's rewrite path; no case ID used until he picks; words in one
  constants place; test that the first button pre-fills the text.
- Step 7 also names the `reasoning_content`-only reply in log and error (test).
- Step 8: banner rule is the spec's literal "fake provider" = `DA_LLM_PROVIDER=fake`. A `claude`
  provider with search `fake` shows no banner (home-only Claude use is Gian's call; noted as a risk).
- Step 10: build uses edit blocks, never deletes a file, no archive copies.
- Step 13 tests: same text same vector; `WorkEmbedder` at home gives "This only works inside CodeVision
  at work."; the embedded text is never logged (stub module).
- Step 14 adds: `src/data/da_code_index/` in `.gitignore` (MUST, test with `git check-ignore`);
  vector size from the first vector, a later different size stops the build (test); setting
  `DA_CODE_INDEX_SOURCE` (default the running `src`), 2,000-character cut, progress every 50 pieces.
- Step 15 lists: `top_k x 4`, `DA_CODE_INDEX_MAX_DISTANCE` default 0.90, score `1 - distance/2` cut to
  0..1, `drop_unsafe_hits` as today.
- Final report mentions CodeVision's `a_vector.py` retry/print behaviour (not changed).
- The "N of M passed" line (step 2) already exists in the panel; no wording change.

## Risks

- Step 3 touches the build loop's round handling: the exact stop point is read in the code first.
- F10 may not reproduce at home (SO-2).
- Section 9 `WorkEmbedder` can only be tested at work; at home it is tested with a stub module.
- Out of scope per spec section 8: B2, Review my code, Audit timeline, Rebuild index button, P16, P18.

## Done checks per step

`pytest`, `ruff check .`, smoke check; real results pasted in the worker note. Code review after step 16.
