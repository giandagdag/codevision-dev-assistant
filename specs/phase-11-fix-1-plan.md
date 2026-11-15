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

## Risks
- Big UI file (`da_admin_page.py`, 1251 lines): split per tab into new `da_admin_*_tab.py` layouts as
  each tab is redone, rather than growing it.
- Golden example size in the Generator prompt (Q7, context limit, open at work).
- Window width: reviewed at 1366 by 768 only.
