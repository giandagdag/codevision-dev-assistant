# Fix G1 plan (spec `specs/fix-g-1.md`, branch `phase-g-fix-1`)

Commit subjects: "G1 step N". Small runs: 3 steps per run. Code review after the last step.
Plan review round 1 found 2 Must fix; both are answered below (step 0, and the F3 meaning).

## Steps

0. **Current phase** in `CLAUDE.md`: Fix G1 (spec, plan, branch, PR into `auto/phases-7-10`); Upgrade G
   is merged (PR #105). Stay under 6,000 bytes (a test checks it). Check: `pytest tests -k claude`.
1. **F2 + F3** (wording and map filter).
   - `used_by_block` (`web/da_web_components.py`): 1 -> "Used by 1 module", N -> "Used by N modules",
     0 -> "Not used by other modules" with no list.
   - F3 meaning, decided from the spec text ("nodes of the chosen capability stay solid, the rest
     fade; clearing the filter restores all"): "restores" = the level's own look from Upgrade G
     (linked other-capability bubbles at level 2 and callers/callees at level 3 stay faded, as
     today). With the filter set, EVERY node not in the chosen capability is faded, and every node in
     it is solid. G1-3 "none faded" is tested on a fixture whose capability has no outside links.
   - `da_capability_map.py`: `capability_view` and `module_view` take `highlight=""` (data only).
     `pick_view` in the layout file only passes `highlight` on (one line of wiring, no drawing).
   - Tests: G1-2, G1-3. Check: `pytest tests/test_da_capability_map.py tests/test_da_web_components.py`.
2. **F5 + F6** (index numbering, links cards).
   - F5: `next_build_number` already skips manifest folders and `_run` reads it under the lock.
     `save_build` additionally refuses a folder that already has a manifest: it takes
     `next_build_number(out)`, rewrites the `build` value in the saved pieces file (same side-file +
     replace way) before copying, and returns the manifest with the real number. `_save_build_copy`
     uses `manifest["build"]` for `extra["build"]` and adds "Build 6 was already saved, this is
     build 7." The G1-6 test checks manifest, pieces file `build`, `current_build` and run line agree.
   - F6: the only tag run is `_tag_step` in `_run`, and `_cluster_step` runs right after it. First
     write the G1-7 test through `_run`. If it passes, add no second call and say so in the PR; if it
     fails, fix the order in `_run` (one place, no duplicate in `da_admin_tagger_job`). Rejected
     cards stay rejected (existing G-7 rule, asserted in the same test).
   - Check: `pytest tests/test_da_index_builds.py tests/test_da_admin_rebuild.py`.
3. **F4 + F8** (confirm wording, work note).
   - Two small plain functions, tested directly: `build_confirm_text(manifest)` in
     `da_index_builds.py` ("Use build 5 (20 Nov 03:10 SGT, Delta, 1,234 pieces)?") and
     `tag_confirm_text(version)` in `da_tag_versions.py` ("Restore tag version 7 (20 Nov 02:40 SGT,
     Approve all by <user>)?"). Time via `format_singapore_time` (times are saved as local time; fine
     on a Singapore machine, tests use a fixed time). The "open" callbacks of the builds panel and
     tag history panel get one extra output (the modal text) filled from these functions.
   - `docs/build-work-test.md`: map wiring section (home-shell lines `map_shell()`, map callbacks,
     route) and the "run `pip install -r requirements.txt`, dash-cytoscape is new" line.
   - Tests: G1-4, G1-5, G1-9. Check: run those test files; read the doc section.
4. **F7** browser test (G1-8) in `tests/test_da_admin_screens_browser.py`, same skip rule. The test
   first builds and saves a graph from `src/data/da_fake_codevision` (`build_graph`, `save_graph`)
   into the test index folder, so the map has nodes. A console listener is attached before the page
   opens (or the page is reloaded after attaching) so early errors are caught. 1366x768, PNGs
   `map-level1.png` and `map-capability.png`, canvas present, node count above 0, no console errors.
   Check: run the test; open the two PNGs.
5. **F1** gate: full pytest, ruff, smoke on the final commit; code review (max 3 rounds); PR body
   in `logs/pr-body-g1.md` with the real counts; `gh pr create ... --body-file logs/pr-body-g1.md`.
