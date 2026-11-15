# Plan: Phase 11 fix 1, Admin console redesign

Spec: `specs/phase-11-fix-1.md` v1.1 (approved). Branch `phase-11-fix-1`. PR into `auto/phases-7-10`.

## Step 0 (done by Gian, nothing to build)
Gian checked that `phase-11-fix-1` at `7ade2d2` already contains `origin/auto/phases-7-10` at
`b05914a` (B1, PR #75). **So the spec's "first build step: merge" is not done: there is nothing to
merge.** Re-checked in this run: `git merge-base --is-ancestor origin/auto/phases-7-10 HEAD` is true.
If `auto/phases-7-10` moves later, stop and report (no merge, no allow-list change).
Reference demos are already in `docs/admin-reference/`.

## Rules for every step
- Each step: tests first or with it, `pytest`, `ruff check .`, commit, push to `phase-11-fix-1`.
- No new library, no AI call, no new table. Made-up names only. Colours only from `da_admin_styles.py`.
- Old Phase 11 / 10 tests keep passing. A test that must change is listed under its step, with why.
- Layouts in `layouts/`, logic in `agents/`, styles in `styles/`; new files start with `da_`.
- At most 3 steps per run; then `chief_tick.py next`.

## Steps
1. **Foundations.** Set CLAUDE.md "Current phase". Add `styles/da_admin_styles.py` (palette constants).
   Add `agents/da_admin_labels.py` (`LABELS`, section 4) plus a helper test that scans drawn text for
   `DA_` / underscore field names outside code chips (used by AF-2 in later steps). Raise
   `max_material_decisions` to 1..15, seed default 8 (D-F; existing DBs untouched).
   Changed test: the one asserting the 1..10 bound (now 1..15). Proof: AF-17 decision limit part.
2. **Shell fix (AF-1).** `_menu()` in `da_home_web_server.py` marks the active entry from the URL
   (needs the pathname, so the menu is drawn by a small callback or from the page layout; home shell only).
   Proof: test for `/`, `/admin`, inbox path.
3. **New data fields (AF-19).** In `da_rulebook_models.py`, all with defaults: `index_repo`,
   `index_branch` (`main`), `index_folder_scope`, `index_refresh_mode`, `index_exclusions`, brand
   constants list, `program_type` on `GoldenExample` (old default: first tag else "Utility"), severity on
   UI conventions. Seed: three made-up golden examples that pass every judgement rule, brand rows,
   folder scope `src/data/da_fake_codevision`. Proof: an old stored version loads; seed passes
   `find_rulebook_problems`.
4. **Golden example in Generator prompt (AF-21).** Plain-code mapping (layouts/ and callbacks/ = Screen;
   agents/ with a run entry = Batch or ingestion; else Utility); first 80 lines; heading "Follow this
   example's style"; not sent to Tester or Understand. Proof: prompt test.
5. **Header version pill + View history (AF-3)** on all tabs.
6. **Overview (AF-4, AF-5).** Rulebook rows (icon, chips, status pill, updated), Needs attention with
   jump buttons (Assign opens catalog filtered to Missing backup), Health tiles with 30 days / All
   time. Phase 10 Handoffs and Escalations numbers stay.
7. **Project charter tab.** Purpose, scope boxes, principles/constraints, glossary, size meter.
8. **Capability modules (AF-9).** Plain function: modules per capability from the index piece list (or
   files under folder scope at home), "×2" for shared, max 6 then "+N more"; catalog table, search,
   Missing backup chip, Add module picker in edit mode.
9. **Discover narrowing (AF-10, AF-11, AF-12b).** Plain-code capability match; each search twice
   (capability modules first, then whole index); filter after vector search, empty falls back to whole
   index; "In capability: <name>" label; Discovery tab names it. No match = unchanged.
10. **Unassigned queue (AF-12).** Suggestion from imports (index), reason text, Approve / Assign to /
    New capability / Reject cards.
11. **UI standards tab (AF-13).** Brand constants with swatches (striped when pending), FONT rows,
    SPACING, TABLE_PAGE_SIZE; conventions with severity pills.
12. **Coding standards (AF-14, 15, 16).** Rule list with "fires in N%" (Tester findings citing the rule,
    30 days, over 50% amber), rule card, golden examples panel (Change in edit mode), libraries chips,
    SonarQube list and severity map.
13. **Build and test tab (AF-17).** Cards: limits (steppers), model per role, escalation triggers,
    zones, protected files, tests, severity table.
14. **Version history (AF-18).** Timeline, side panel with coloured plain-word diff, pinned requests,
    Restore with confirm.
15. **Repository and index screen (AF-6).** Run store `da_code_index_runs.json` (last 10), index health
    tiles from `da_code_index.json`, Connection, Refresh tiles (only Manual runs), Exclusions with B1's
    fixed 🔒 rows, allowed folders etc., read-only server settings (plain labels).
16. **Rebuild index (AF-7, AF-8; closes P23).** `build_index()` gets an optional `extra_exclusions`
    argument (default none, so B1 tests unchanged). Background thread, lock file, one at a time, fake
    embedder at home, never at work; confirm box; poll; "Rebuild the index now?" after saving scope or
    exclusions. Park a new item in `specs/parked-items.md`: build on merge / nightly.
17. **Screenshots (AF-20).** Playwright script, skipped with no browser, 16 PNGs to `logs/admin-screens/`.
18. **Close-out.** Full pytest, ruff, smoke check; AF-2 label scan across all tabs; code review (max 3
    rounds, panels compared to the reference demos); PR body.

## Plan review round 1: fixes (these override the steps above where they differ)
- **Step 0:** the merge is "not needed: already contained".
- **Step 5 also builds the shared floating edit bar** (all tabs): "Editing <tab>. Nothing changes for
  developers until you save." with Cancel and **Save as new version**; Save still asks for a note, stale
  save still names the newer version. Proof: bar text and button label in edit view of each tab.
- **Step 1 decision limit:** only `src/data/da_rulebook_seed.json` becomes 8. The Python default
  `DEFAULT_MAX_MATERIAL_DECISIONS` stays 5, so old versions without the field keep 5 (D-F: existing
  databases unchanged). Changed tests in `tests/test_da_rulebook_models.py`: the 1..10 bound (~line 524,
  now 1..15) and the seed-value assert (~line 500, now 8). The old-version default test (~line 509)
  stays as is. Step 1 `da_admin_styles.py` imports `NAVY` and `BLUE` from `da_styles.py`; the "no colour
  code elsewhere" rule covers Admin screens only.
- **Step 3 golden module path:** add `module_path` (default empty) to `GoldenExample`. Change in edit
  mode picks a module from the index, sets `module_path`, and copies its first lines into `code`.
  Seed examples set both. Resolve `src/data/da_fake_codevision` from the project root, not the cwd.
- **Step 4 mapping:** "agents/ file with a run entry" = the file text contains `__main__` or a top-level
  `def run`.
- **Step 8 also tests AF-5** (Missing backup chip is built here); step 6 only tests that the Assign
  button carries the target tab and filter.
- **Reuse, named:** step 6 extends `da_admin_overview.py` (`attention_items`, `area_status`,
  `server_settings_view`); steps 8 and 10 extend `da_admin_catalog.py` (`queue_rows`, `resolve_row`,
  `would_match`); step 12 uses `da_admin_cited.py` `cited_counts` for "fires in N%"; step 14 extends
  `da_admin_diff.py` (`area_of_path`, `build_timeline`); step 6 health tiles use `da_admin_metrics.py`.
- **Proof lines:** 5 pill shows version, date, who, View history link; 6 six area rows each link to
  their tab, tiles switch 30 days / all time; 7 meter colour at 79%, 80%, 100%, 101% (green, amber,
  amber, red); 8 chips max 6 then "+N more", "×2"; 9 AF-10/11/12b; 10 AF-12; 11 AF-13; 12 AF-14/15/16;
  13 AF-17 (rounds 1..5); 14 AF-18; 15 AF-6 (no files = "needs building"); 16 AF-7/8; 17 AF-20.
- **Step 16:** embedder rule = reuse B1's: `DA_LLM_PROVIDER == onprem` gets `WorkEmbedder`, anything
  else `FakeEmbedder`, via one small shared helper that `main()` also uses. Empty `index_folder_scope`
  falls back to `DA_CODE_INDEX_SOURCE`, then B1's default (both tested). The lock file holds its start
  time; a lock older than 2 hours, or left from before server start-up, is cleared (one test). The run
  file stores only "path symbol" strings (`BuildSummary.skipped`), never code text.
- **Step 18:** the AF-2 scan also draws all 8 tabs from an old stored version (AF-19).

## Risks
- Big UI file (`da_admin_page.py`, 1251 lines): split per tab into new `da_admin_*_tab.py` layouts as
  each tab is redone, rather than growing it.
- Golden example size in the Generator prompt (Q7, context limit, open at work).
- Window width: reviewed at 1366 by 768 only.
