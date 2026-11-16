# Plan: Phase 11 fix 2, Capability catalog by meaning, AI tagging, SonarQube refresh

Spec: `specs/phase-11-fix-2.md` v1.0 (approved). Branch `phase-11-fix-2`, cut from `phase-11-fix-1`
(do not change that branch). PR into `auto/phases-7-10`, not merged by me.

## Rules for every step
- Tests with each step, `pytest`, `ruff check .`, commit, push to `phase-11-fix-2`. Max 3 steps per run.
- Made-up names only. No real network or AI in tests (fake client, fake session).
- Fix 1 tests keep passing; a test that must change is listed under its step with why.
- Layouts in `layouts/`, logic in `agents/`; new files start with `da_`. No new library.

## Facts found while reading (they shape the plan)
- Spec 3.5 says "a fourth row". Today Model per role has **two** rows (Generator, Tester) and `Role`
  has three values. So Program tagger becomes the **third row**. Not a blocker, same intent.
- `FakeEmbedder` is a hash: it knows nothing about meaning. The home meaning search goes through the
  fake **search index** (`FakeSearchIndex`, word stems plus synonym groups, mode "meaning"), which
  reads `da_fake_index` JSON pieces. AG-1 therefore uses that file plus the tagger-summary match of
  spec section 2 (the allowed fallback). The two new made-up modules get snippets and a summary
  with "write" and "markdown" words; no function name holds "markdown".
- `da_admin_rebuild.py` already has lock file, `running_since`, background thread. The tagger job
  reuses that pattern with its own lock name and a **shared "one job at a time" check** (AG-8): scan
  refused while a rebuild runs and the other way round.

## Review fixes (plan review round 1)
- **Step 0**: CLAUDE.md "Current phase" now names fix 2, this plan and branch `phase-11-fix-2`
  (stay under 6,000 bytes).
- **10% rule vs the bad reply (spec clash, resolved):** the shipped `da_tagger_fake_script.json` has
  one reply per module including one `none`, and **no bad reply**, so the home scan saves. The bad
  reply (AG-5) lives only in tests: they build 20 scripted replies in a temp folder (1 bad = skipped,
  3 bad = "Not saved"). AG-4 "every module gets a summary" means every module with a valid reply.
- **AG-1:** the fake search also scores words from the path. The two new modules' snippets and tags
  use "creates", "markdown", "file"; the test also asserts `docs_folder_to_md.py` ranks by its
  snippet words (its name has no "markdown"). New pieces are appended at the end of the fake index
  file; any Discover test that counts or ranks hits and changes is listed in step 2's commit.
- **AG-2:** the "no index" line shows for `IndexFormatError`, `IndexNotBuiltError`, a missing faiss
  import and `no_index_at_work`; new constant with the spec wording, `INDEX_NEEDS_BUILDING_MESSAGE`
  stays for Discover.
- **Tagger client:** a `ScriptedTaggerClient` (same pattern as `ScriptedTesterClient`) reads the
  script; module list from the piece list, file text from `source_folder(policy)`.
- **Approve all:** `_add_pattern` takes a list of (path, capability) pairs and saves once; the
  single card calls it with one pair. AI cards have their own resolve in the JSON store; Approve is
  hidden on "No capability fits" cards.
- **One job at a time:** one shared message "One job at a time: wait for the other one to finish."
  `start_rebuild` also checks the scan lock; changed rebuild tests are listed in step 4.
- **Tag new or changed** shows when index `built_at` is newer than the last tag run.
- **Sonar:** snapshot read and pill switch go in `da_admin_sonar.py`; `da_sonar_client.py` holds only
  the network calls. Server settings rows get plain labels; the token shows "set" / "not set".
- **Proof lines:** step 4 `tests/test_da_admin_tagger_job.py` (lock, refusal, progress, model used);
  step 5 `tests/test_da_admin_tag_cards.py` (cards, approve, approve all, hidden Approve); step 6
  callback and layout tests in `tests/test_da_admin_catalog_meaning.py` (modes, results, AG-3 same
  results as before); step 7 `tests/test_da_sonar_client.py` plus panel tests.
- **Changed tests expected (step 1):** `test_da_model_per_role.py`, `test_da_admin_forms.py`,
  `test_da_admin_overview.py` (third model line), `test_da_llm_client.py` if it counts roles.

## Steps
0. **CLAUDE.md "Current phase"** (see above).
1. **Settings, role, model row (AG-14 part).** `Role`/`ROLES` gain `tagger` (Claude: generator's model
   when empty; on-prem: admin model else server default). `Policy.tagger_model: str = ""` (old
   versions load), `_MODEL_FIELDS`, build-tab third row "Program tagger", labels table, Overview "For
   your information" line. Settings: `tagger_max_modules` (`DA_TAGGER_MAX_MODULES`, 500) and the four
   Sonar fields (empty by default; token never in repr). Proof: tests for `get_llm_client("tagger")`,
   form save, labels scan, config defaults. Changed tests: those asserting `ROLES` or the fields
   tuple, if any.
2. **Search by meaning, plain function (AG-1, AG-2, AG-3 base).** `agents/da_admin_meaning.py`:
   `ModuleHit`, `modules_by_meaning` (search_safely, group by path, best score, 15 max, 3 symbols,
   capability from patterns else "Unassigned", summary from tag file, summary-word match with
   `_query_words`/`_meaning_id`). No-index line. Two new made-up modules under
   `src/data/da_fake_codevision/src/agents/` and pieces in the fake index file. Proof: AG-1 (both in
   top 3, FakeLLMClient never called), AG-2.
3. **Tagger core (AG-4, AG-5, AG-9, AG-10 logic).** `data/da_tagger_prompt.md`,
   `data/da_tagger_fake_script.json`, `agents/da_admin_tagger.py`: build prompt (200 line cut,
   capability names and descriptions only, skip `da_`, `looks_secret`, excluded), validate reply,
   store `da_module_tags.json` (all or nothing, over 10% skipped = "Not saved", run log of 10), hash
   check for "new or changed". Proof: tests for each AG.
4. **Job and buttons (AG-8).** Lock file, background thread, progress "120 of 340", shared one-job
   check with Rebuild; `DA_TAGGER_MAX_MODULES` cap message; callbacks and header buttons with confirm.
5. **Queue cards and approvals (AG-6, AG-7).** "From the AI scan" cards, Approve / Assign to / Reject,
   Approve all high-confidence (one version, one note), tooltips with summary, Overview "N AI proposals
   to review".
6. **Catalog search modes UI (AG-1..3 UI).** SegmentedControl, results list, click filters table
   (`da_admin_catalog_meaning.py`).
7. **SonarQube (AG-11..13).** `agents/da_sonar_client.py` (GET only, two calls, paging to 20, token as
   user name, plain errors, no token in logs), snapshot next to the index, panel pill and button.
8. **Finish (AG-15, AG-16).** AF-2 label scan over new parts, screenshot script additions, full
   pytest, ruff, smoke check, code review (max 3 rounds), PR into `auto/phases-7-10`.

## Out of scope
Overview layout, AI drafting judgement rules, reading Bitbucket, any AI writing a rulebook version.
