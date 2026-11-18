# Plan: Phase 11 fix 3, Admin polish, one index job, real work embedder

Spec: `specs/phase-11-fix-3.md` v1.2 (approved). Branch `phase-11-fix-3` (already merged with the
newest `auto/phases-7-10`). PR into `auto/phases-7-10`, never merged by me. Issue 89.

## Rules for every step
- Tests with each step, `pytest`, `ruff check .`, commit, push to `phase-11-fix-3`. Max 3 steps per run.
- Made-up names only; no real AI or network in tests. Fix 1 and fix 2 tests keep passing; a test
  that must change is listed under its step with why.
- Layouts in `layouts/`, logic in `agents/`, styles in `styles/`; new files start with `da_`.
  No new library, no new database table (status and runs are JSON files next to the index).

## Facts found while reading
- G2 cause confirmed in `agents/da_code_index.py`: `WorkEmbedder` does `from agents.a_vector import ...`
  inside the DA's own process, where `agents` and `configs` are the DA's packages. Fix: a helper process
  run with CodeVision's Python and working folder (D-A). The helper uses only the standard library plus
  what `a_vector` imports, and imports nothing from the DA.
- `da_build_code_index.build_index` embeds every piece in one pass and `_save` writes `.faiss` + `.json`
  together. Delta needs a per-piece file hash and `reconstruct_n` for reuse.
- `da_admin_rebuild.py` has the lock (`da_code_index.lock`, `da_tagger.lock`), `start_rebuild`, and a
  thread. The index job extends this (status file, steps, stop); the tagger job
  (`da_admin_tagger_job.py`) is called as step 2 of the same job.
- `Settings` (`configs/da_config.py`) already has fix 2 fields; two new ones are added there.
- Step 11 of the job (tagging) must not touch B1's rule: index saved first, tag failure keeps it.

## Review fixes (plan review round 1)
- **Helper search path (Must 1):** the helper starts as `python -I da_embed_worker.py <src>`: `-I`
  keeps the script's own folder (the DA's `src`) off the search path; the helper then puts
  `DA_CODEVISION_SRC` first on `sys.path` itself. AH-3 test: same-named modules in both trees, the
  CodeVision one must win.
- **One lock (Must 2):** one lock file for the whole job (index + tagging). Stale = the status file has
  had no progress for 30 min (not a fixed 2 h); `SERVER_STARTED` no longer deletes a live job's lock.
  Tests: a 3 h job stays locked; a later-started process is still refused. The old tagger lock name goes.
- **Approved/rejected kept (Must 3):** `run_tagging` keeps state and capability when a file changed and
  only refreshes summary and hash. Test in step 4.
- **Settings, not os.environ (Should):** `Settings` values are passed into `WorkEmbedder`,
  `source_folder` and the scheduler; `provider` becomes required; test: Nightly under `onprem` picks the
  work embedder.
- **Stop (Should):** a small stop file next to the status file, checked between pieces and between
  modules. Stop during tagging keeps the new index and drops only the new tags (all or nothing for tags).
- **Tagger cap (Should):** `tagger_max_modules` does not apply inside the index job (Full re-tags every
  module), the cap stays on nothing else; noted in step 4 with a test.
- **Delta from old index (Should):** an old index without `file_hash` or `embedder` forces Full. Tested.
- **Check command (Should):** `da_check_embedder` has a test; helper stderr is never logged or shown.
- **Tab names:** the real `ADMIN_TABS` names in `layouts/da_admin_common.py` (incl. Project charter),
  not "Rulebook". `section()` and `window()` there are replaced or extended by the new card.
- **Proof lines:** step 7 `tests/test_da_admin_repo_layout.py`; step 8 split into 8a, 8b (several tabs
  each) with changed fix 1 and fix 2 layout tests listed in each commit; step 9
  `tests/test_da_admin_catalog_search.py` (header link to Repository and index); step 10
  `tests/test_da_admin_ui_standards_fix3.py`. Step 7 also shows the red error box with its fix hint.
- **Step 11:** extend `tests/test_da_admin_screens_browser.py` (its `catalog-names` and `catalog-meaning`
  shots change); demo files `docs/admin-reference/admin-demo-2026-11-14.html` and
  `admin-concept-2026-10-25.html`.
- **Work seed:** the made-up scope is already in the work DB, so AH-11's refusal is the protection;
  new seeds leave the scope empty.

## Steps
0. **CLAUDE.md "Current phase"** names fix 3, this plan, branch `phase-11-fix-3` (stay under 6,000 bytes).
1. **Work embedder in a helper process (G2; AH-3, AH-4, AH-4b).** Settings `DA_CODEVISION_SRC`,
   `DA_CODEVISION_PYTHON`; `.env.example` lines with made-up paths. `src/da_embed_worker.py` (stdlib only,
   JSON lines: reads `{"text":...}` writes `{"vector":[...]}` or `{"error":"plain words"}`, never prints
   text). `WorkEmbedder` starts it with an argument list (spaces in paths OK), cwd = source folder, one
   helper for the whole build, `close()`, one restart on death, second death raises a plain error.
   `src/da_check_embedder.py`. Proof: `tests/test_da_embed_worker.py` with a temp fake CodeVision
   (`agents/a_vector.py`, `configs/llm_config.py`, `tools/`) using the DA's package names: AH-3 (fakes
   imported, many texts, one helper), AH-4 (empty or wrong setting, missing module, no text or key in
   messages), AH-4b (helper killed once = restarted; twice = error). Changed tests: any asserting
   `WORK_ONLY_MESSAGE` from `WorkEmbedder` (listed in the commit).
2. **Delta rebuild in `build_index` (D-B; AH-5, AH-6).** Each piece stores `file_hash`. New
   `mode="full"|"delta"`; Delta loads the old index, re-embeds pieces from new or changed files only,
   reuses vectors with `reconstruct_n`, drops deleted files, then writes both files again. Full forced
   when vector size or embedder changed (record `embedder` name). A `progress(done, total)` callback.
   Proof: `tests/test_da_delta_rebuild.py` with a counting fake embedder over 3 temp files: only the
   changed file's pieces embedded, vector N matches piece N, search equals a Full rebuild, deleted file
   gone from both files, forced Full.
3. **Index job: status file, steps, Stop, work safety (D-G; AH-7, AH-11).** `da_admin_job.py` (or
   extend `da_admin_rebuild.py`): status JSON (`da_index_job.json`: step, done, total, percent, started,
   by, time left after 20 items, last error), Stop flag checked between pieces (old index stays),
   `start_rebuild(mode=...)`. With `onprem`, a scope inside `da_fake_codevision` is refused with the
   spec line; empty scope means `DA_CODEVISION_SRC`; work seed leaves scope empty. Recent refreshes rows
   gain Full/Delta, Manual/Nightly, pieces re-read, programs tagged, duration. Proof:
   `tests/test_da_admin_job.py`. Changed tests: `test_da_admin_rebuild*.py` for the new mode arg.
4. **Tagging inside the job (D-C; AH-8, AH-9).** Step 2 of the job calls the tagger after the index is
   saved: Full tags all, Delta only new or changed modules; over-10% failure keeps the index and the run
   row says tagging was not saved. Remove "Scan all programs" and "Tag new or changed" buttons and
   callbacks. Changed tests: tagger job and scan callback tests (listed in the commit).
5. **Refresh modes and Nightly (D-D; AH-10, AH-17).** Policy refresh mode field (Manual/Nightly, time,
   default 02:00 SGT), equal-width tiles, "On every merge" disabled with the WF-12 reason. Scheduler thread
   at server start, Delta job with the same lock file (second process loses). Proof: tests with a
   fake clock and two lock takers.
6. **Shared card, page titles, grid (G1, G6, G11; AH-1, AH-2).** `layouts/da_admin_card.py`,
   `da_admin_page_title`, styles only in `styles/da_admin_styles.py` (V1 to V8). Test walks all 8 tabs and
   fails if a top-level child is not a card (title excepted).
7. **Repository and index tab layout (G3, G5; AH-7 UI).** Main column cards (Connection, Refresh,
   Exclusions, Allowed folders, Server settings collapsed), side column Index job card (health pill,
   Delta and Full with confirm and estimate, progress bar, Stop, polling 5 s, red error box, equal health
   tiles, Recent refreshes last 10).
8. **Other tabs into cards.** Overview, Capability catalog, UI standards, Rulebook, Build, Coding,
   History moved onto the shared card, rows with dividers, empty states (V5, V7).
9. **Catalog: one search box (D-E; AH-12, AH-13).** Enter-only combined search, matches labelled
   "Matches what the code does"; header "Programs last tagged..."; find and fix why AI proposals do not
   show in the Unassigned queue and Overview (G7).
10. **UI standards (D-F; AH-14 to AH-16).** Brand constants edit mode (new version), conventions rows
    drawn and count matches (G10), Generator prompt for Screen files gets both lists once.
11. **Finish (AH-18).** Screenshot script for 8 tabs at 1366 by 768, full pytest, ruff, smoke check, code
    review (max 3 rounds), PR into `auto/phases-7-10`, not merged.

## Out of scope
Recolouring the running app, Bitbucket webhook (WF-12), WF-9 timing numbers, any new library.
