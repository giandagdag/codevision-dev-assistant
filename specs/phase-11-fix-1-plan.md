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

## Plan review round 2: approved (0 Must fix), two Should fix taken in
- Step 1 changed tests also: the policy-equality line (~510) in the old-version default test is
  adjusted (keep the `== 5` check); the refused-values test (~521) becomes `[0, 16, -1]`. Run the
  Understand tests right after step 1.
- Step 16: the shared embedder helper is used **only by the Admin rebuild**. B1's `main()` and `--fake`
  stay exactly as they are.
- Step 4 mapping: a batch file = text has `__main__`, or a top-level `def run...` (name starts with
  `run`, so `run_batch` counts).

## Risks
- Big UI file (`da_admin_page.py`, 1251 lines): split per tab into new `da_admin_*_tab.py` layouts as
  each tab is redone, rather than growing it.
- Golden example size in the Generator prompt (Q7, context limit, open at work).
- Window width: reviewed at 1366 by 768 only.

## Addendum: section 14, layout rework L1 to L8 (16 Nov 2026)
Layout only: ids, callbacks, data and old behaviour stay. Old tests keep passing; a test that must
change is named under its step. No new library, no AI call. Colours only from `da_admin_styles.py`.
A step's PNG is checked against the matching tab of both demos in `docs/admin-reference/`.

**Split rule.** New `layouts/da_admin_common.py` holds what every tab shares: `section`, `goto_id`,
`GOTO_TYPE`, `version_pill`, `two_columns(left, right)` (CSS grid 2fr 1fr, inline style) and `chip`.
`da_admin_page.py` re-imports them under the old names, so old tests and callbacks still find them.
Each redone tab moves into its own `da_admin_<tab>_tab.py` (imports common, never `da_admin_page`, so
no circular import); `da_admin_page.py` calls it and re-exports the old names.

Steps (numbering continues after 18):
19. **L1 + L2.** `version_pill` replaces `version_line` on all 8 tabs, Version history included (its
    view gets the version): green dot, "Active rulebook vN", "Published <date>, <who>", **View history**
    button (same `goto` id, callback unchanged). A stale-save form says "Started from vN" instead of
    Active. Overview moves to `da_admin_overview_tab.py`: grid with the Rulebook panel (rows stay
    clickable) left 2/3; Needs attention then Health tiles stacked right 1/3. Tests: pill text and
    button on all 8 tabs; Overview child order; old overview tests unchanged (the old "Showing vN" text
    asserts, if any, are listed when changed).
20. **L3 + L4.** Coding standards to `da_admin_coding_tab.py`: left 2/3 rule list, right 1/3 rule card
    of the selected row; golden examples as cards with a working **Change** button (module picker from
    the index, P29); approved libraries as chips, blocked imports as red chips. UI standards (existing
    `da_admin_ui_standards.py`): brand constants left, UI conventions right. Tests: column order, chips,
    Change button per card.
21. **L5 + L6.** Repository and index to `da_admin_repo_tab.py`: left/right columns as spec section 7;
    index health as tiles, allowed folders and markers as chips in the read view (edit view keeps its
    tables). Capability catalog to `da_admin_catalog_tab.py`: table left, Unassigned queue as cards on
    the right with **New capability** and **Reject** (P28). Tests: column order, chips, cards, buttons.
22. **L7 + L8.** Version history to `da_admin_history_tab.py`: left vertical timeline (green filled dot =
    active, newest first, Active / "Restored from vM" tags), right side panel "What changed in vN" with
    coloured plain-word diff, Requests pinned chips and **Restore vN** with the section 3 confirm text;
    the From/To number boxes leave the view. Build and test: compare with the demo, move any panel not
    in place into `da_admin_build_tab.py`. Tests: timeline order and tags, side panel parts, Restore
    confirm. Any old compare test that used the number boxes is changed and listed.
23. **Proof.** Screenshot seed gets 2 versions (v1 seed, v2 with a change note); re-run the script for
    16 PNGs at 1366 by 768. Full pytest, ruff, smoke check. Code review: each PNG next to both demo
    tabs (max 3 rounds). Update the PR body (remove P31 from Known gaps, list changes), open the
    `gian-later` issue "Phase 11 fix 1: screenshots ready for your sign-off", stop. Never merge PR #77.

Run size: this run builds 19, 20, 21; the next run 22 and 23.
Risk: CSS grid is inline-style only (no stylesheet); checked in the PNGs.

### Addendum, plan review round 1: fixes (override the steps above where they differ)
- **Header line:** "existing callbacks stay". New callbacks are named under their step (M1).
- **Common file (M3).** `da_admin_common.py` holds: the `TAB_*` constants, `ADMIN_TABS`, `body_id`,
  `act_id`, `goto_id`, `GOTO_TYPE`, `section`, `chips` (the existing `_chips`, reused as the chip helper),
  `two_columns`, `version_pill` (with its own id counter, history target `TAB_HISTORY`), and the shared
  list table (`list_table`, `_table_row`, `_cell_text`, `_text_rows`, `_draft`). Each tab file takes its
  own private helpers and constants with it. `da_admin_page.py` re-exports with an `__all__` list (ruff
  F401 clean). One test imports every `da_admin_*_tab.py` and `da_admin_common.py` alone in a fresh
  interpreter (no ImportError). `version_line` stays as an alias of `version_pill`.
- **Version for History (S2).** `history_content` (callbacks file, line ~510) passes the active version
  to `history_view` as a new argument; this one line is changed and named.
- **Steps renumbered (S4), small and one per concern:**
  19 L1 common file and pill on all 8 tabs. 20 L2 Overview grid. 21 L3a Coding standards two-column
  layout and rule-card selection (new callback `adm-rule-pick` on a rule row click fills the card;
  card text comes from the existing `rule_cards`). **Next run:** 22 L3b golden Change button (new
  callback: in edit mode, picks a module from `module_paths`, sets `module_path` and copies the first
  lines into `code` in the draft) and libraries/blocked chips. 23 L4 UI standards. 24 L5 Repository and
  index. **Run after:** 25 L6a catalog table plus queue cards. 26 L6b Reject and New capability.
  27 L7 History. 28 L8 Build and test. **Last:** 29 Proof (as step 23 above).
- **Reject (M2), smallest meaning.** Reject adds a fourth resolved state `rejected` to
  `UnassignedState` and to the guard in `resolve_unassigned` (`db_tbl_da_enhance.py` line ~395); the
  state column is plain text, so no table change. A rejected file leaves the open queue, shows in the
  Resolved list as "Rejected", and a later change to the same file opens a new row (as for confirmed
  rows). Files touched: `da_enhance_models.py`, `db_tbl_da_enhance.py`, `da_admin_catalog.py`,
  `da_admin_page_callbacks.py` and the queue card. **New capability** opens the Capability catalog in
  edit mode with one new row: name from the suggestion (or empty), path pattern = the file's folder
  pattern; saving follows the normal Save with a note. Tests: reject moves the row to Resolved; a
  later change reopens it; New capability pre-fills one row. This is my reading of P28; Gian can
  change it at sign-off.
- **Changed tests (S1), named now.** Step 19: the "Showing v1 (active)" asserts in
  `test_da_admin_catalog_screen.py:70`, `test_da_admin_overview_screen.py:31`,
  `test_da_admin_repo_screen.py:52`, `test_da_admin_rule_screen.py:74`, `test_da_admin_edit.py:121,125`
  (now "Active rulebook v1" / "Started from v1"); `test_da_admin_header.py` keeps `version_line`
  through the alias, with its asserts updated to the pill text. Step 20: `test_da_admin_overview_screen.py:83`
  ("Rulebook areas" becomes "Rulebook"). Step 27: `test_da_admin_history.py:75-82` and
  `test_da_admin_label_scan.py:88-91` (compare by clicking a timeline row).
- **L8 (S3).** Step 28 is decided after I read the Build and test tab of the demos at step 28; the plan
  names the panels and one test for card order then.
- **Close-out (FYI).** Mark P28, P29, P31 DONE in `specs/parked-items.md`.
