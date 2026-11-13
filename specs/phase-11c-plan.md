# Phase 11c plan: Admin console, third part (Overview, health numbers, Repository and index)

Spec: `specs/phase-11-admin-console.md` (D-A to D-M chosen by chief, option 1 each). Branch
`auto/phase-11c`, made from `origin/auto/phases-7-10` (11a and 11b are merged, PR 66 and 68). Scope is
the D-A "11c" slice: **tab 1 Overview (rulebook areas, Needs attention, health numbers with the time
window), tab 3 Repository and index, smoke additions, README, `docs/admin-work-test.md`**. Tabs 2, 4 to 8
are done and are changed only where the shared screen helper needs it.

Pattern as in 11a and 11b: plain code first (testable without Dash), then the screen. Each step ends
with `pytest`, `ruff check .`, a commit and a push to `auto/phase-11c`. At most 3 steps per run, then
`chief_tick.py next "builder continue Phase 11c from step K"`. Code review only after the last step
(max 3 rounds). A stop rule firing goes to `ops/state/worker_note.md`. Ponytail trial: builder tokens per
step are noted in the worker note.

## Design in plain words

- **Read only, plain code, no AI (11-45).** The Overview and the metrics only read. SQL for the health
  numbers goes in `db_table_functions/db_tbl_da_metrics.py` (new, SELECT only, tables from the earlier
  phases); `agents/da_admin_metrics.py` turns the rows into numbers and the "No data yet" states.
  `agents/da_admin_overview.py` (new) holds area status and Needs attention. No SQL against
  `da_rulebook_versions` anywhere in these files (it uses `get_active_version`, `list_versions`).
- **"No data yet" is a state, not 0 (spec 12).** Each number is a small dataclass with `value`
  (None when no rows) and `text`; the screen shows `text`. A rate over zero rows is None. Handoffs is
  always "No data yet (comes with Phase 10)".
- **Time window.** `Window = "30d" | "all"`. Last 30 days means the row's own time (`created_at`,
  `started_at`/`ended_at`, `confirmed_at`, `timestamp`) is at or after `now - 30 days`. Step 1 reads
  how the earlier phases write these timestamps (ISO text) and compares them as text against a cutoff in
  the same format; a test with rows 29 and 31 days old proves the edge (11-43). `now` is a parameter, so
  tests need no clock.
- **Definitions fixed in step 1 (the spec fixes the meaning, the plan fixes the values).** Confirmed
  from the code just read:
  - *Closed build* = `da_build_runs.ended_at IS NOT NULL` and `kind` of the run is `build` or `rebuild`
    (a "Check my edits" run has no Generator, so it has no first-round pass; it is left out). Runs that
    were stopped, escalated or interrupted are closed builds too and count (they did not pass).
    The window uses `ended_at`. Reading noted for the chief; one test pins both parts.
  - *First-round pass* = the closed build's `da_build_rounds` row with `round = 1` passes exactly the
    loop's own test: `LayerAResult.ok and layer_b is not None and LayerBResult.ok` (`da_build_loop.py`
    ~807; `LayerBResult.ok` also needs at least one test). Decoded in Python with the existing models,
    not SQL string matching. A closed build with no round 1 row, or a round 1 with zero tests, counts as
    not passed.
  - *Average fix rounds* = mean of `max(rounds_used - 1, 0)` over the same closed builds.
  - *Requests* by kind: kind is `EnhanceState.kind` inside the `da_enhance_state.state` JSON
    (`enhance` or `fix`), as the spec says; no Enhance row means `new`. Test with an Enhance state and
    no confirmed record.
  - *Revisions per request* = mean of (highest record `version` - 1) over requests with a record.
  - *Files edited by developers* = distinct (request, path) in `da_workspace_files` with `kind =
    'scanned'`; share = requests with at least one over all requests in the window.
  - *Get help* = distinct requests with a `da_audit_events` row that is either `status_changed` with
    `details` JSON `to = 'ESCALATION_REQUIRED'`, or an `escalated` / `discovery_escalated` event
    (Enhance's Get help in `da_enhance_help.py` writes only `escalated`; it is not changed here, and
    the missing status row is mentioned in the PR notes). Step 1 confirms the exact event names by
    grep. A test drives the real Enhance `request_help` path with the fake provider, plus one from
    Approach.
  - *Tester findings by type* = `da_tester_findings` with `kept = 1`, grouped by `check_number` (names
    from `CHECK_NAMES`) and by `severity`; *Unable to assess* = `da_tester_reviews.result = 'unable'`.
  - *Rules cited* = the same `kept = 1` count as the Cited column, top 5. `count_kept_cites` in
    `db_tbl_da_tester.py` gets one optional `since` argument (default None = all time, behaviour
    unchanged); no second copy of the SQL.
  - Cutoff text comes from the project's own `to_db_time` so it matches the stored format. One time
    column per number: `ended_at` (builds), `created_at` (requests, findings, workspace rows),
    `confirmed_at` (record versions), `timestamp` (audit).
- **Area status and Needs attention (spec 4, 5).** One function builds the list of attention items, each
  with an area, a level (`info` or `red`) and a text; area status is derived from it (green none, amber
  info, red red). Items: charter size amber (info) / red; judgement rules at 9 or 10 of 10 (info line),
  over 10 red; open Unassigned rows (info, with the count and the tab name); an open row older than
  `admin_unassigned_stale_days` (red on the catalog area); capability with no backup senior (info,
  uses `capabilities_without_backup`); trigger off (info, Build and test); empty model per role (info,
  Build and test, "uses the server default"); retired field still carried (uses the existing
  `RETIRED_POLICY_FIELDS`; points at Build and test; empty for a fresh seed, proven by a test).
  Empty list: "Nothing needs attention."
- **Last changed per area (spec 4, 10).** Taken from the `TimelineRow.areas` rows `build_timeline`
  already returns (newest first): the first row naming an area is its last change. No second diff loop.
  Version 1 touches nothing.
- **Missing tables on a fresh install.** The metrics call the existing `ensure_*_tables` functions first
  (the way `queue_rows` does), so an Admin who opens `/admin` before any build gets "No data yet", not a
  crash. Test on a database holding only the rulebook tables.
- **New SQL file is covered by the safety tests.** The existing 11-44 test parses only the callbacks file
  and the 11-45 glob (`_admin_files()`) searches `layouts`, `callbacks`, `agents` for `da_admin*.py`. Step
  1 extends 11-45 ("no `da_rulebook_versions`", "no AI") to `db_table_functions/db_tbl_da_metrics.py`,
  and step 4 extends 11-44 (no import of the developer callbacks) to every console module, the new
  `da_admin_metrics.py` and `da_admin_overview.py` included.
- **Repository and index (spec 11, D-D).** Read-only block "Server settings": `DA_SEARCH_PROVIDER`,
  `DA_SEARCH_TOP_K`, `DA_DISCOVERY_MAX_ROUNDS`, `DA_MAIN_SOURCE`, `DA_SANDBOX_SOURCE_DIR` shown as
  "set / not set" for the folder (never a path or key), plain values for the others. Editable block:
  `allowed_folders`, `new_file_name_pattern`, `workspace_markers`, `workspace_max_file_kb`.
  `rulebook_from_form` gets a `repo` branch (same shape as the Build branch: copy the policy, apply form
  values, `Policy.model_validate`, so the model's own refusal of a non-compiling pattern shows). Lists use
  `_clean_list`. The `repo` tab joins `EDITABLE_TABS`, `TABLES` and the shared Edit/Save/Cancel pattern.
  `_warnings` in `save_from_form` already runs on every save, so the protected-folder warning shows on
  the Repository save too.
- **Overview screen.** Read only. Three blocks: Rulebook areas table (area, one-line summary, status
  badge, last changed), Needs attention list, Health numbers with a `dmc.SegmentedControl` "Last 30 days /
  All time" (default All time, so a new install shows data; the chooser re-draws only the health block).
  A link-like button per attention line opens the tab (sets the tabs value). The health block is a small
  callback with its own output (`adm-health`) so a window change does not touch the rest.
  Tabs list: the "Comes in 11c" text is gone for tabs 1 and 3 (`ADMIN_TABS` third column stays as a
  record of the phase that built each tab).
- **Opening the Overview is cheap.** The Overview is drawn with the page; it recomputes when the Overview
  tab is opened (as the Version history tab does), so a save on another tab shows at once.
- **Not touched:** developer page, LLM client, WF-1 to WF-8, any AI call, any new library, the Phase 1
  store functions (only called). No new table. Phase 10 data is shown as "No data yet (comes with Phase
  10)".

## Steps

1. **Health numbers (plain code).** `db_tbl_da_metrics.py` (SELECT only) and `agents/da_admin_metrics.py`:
   requests by kind, first-round pass rate, average fix rounds, revisions per request, files edited,
   Get help count with the "Get help only" label, Handoffs fixed text, findings by check and severity,
   Unable to assess count, rules cited (top 5), the window cutoff. First read how timestamps are stored
   and write the window comparison against that format. Tests (made-up database, known rows): 11-39
   (4 closed builds, 2 passing round 1 gives 50%, average fix rounds, revisions, files edited as
   computed), 11-40 (empty database: every number "No data yet", Handoffs with the Phase 10 text),
   11-41 (one Get help request gives 1 with the label; a status move to another state does not count),
   11-42 (findings on checks 1, 4, 6 grouped by name and severity; the rule cited most is first; rejected
   findings not counted), 11-43 (rows older than 30 days not counted in the 30 day window, counted in All
   time, with the 29/31 day edge), open builds (no `ended_at`) not counted, a "check" run not counted, a
   stopped run counted as not passed, a build with no round 1 row counts as not passed, a round 1 with a
   timed-out `layer_b` or with zero tests counts as not passed, an Enhance state with no record counts as
   its kind, Get help from the real Enhance path and from Approach both counted once per request, a
   database holding only the rulebook tables gives "No data yet" on every number, and the 11-45 scan
   (no `da_rulebook_versions`, no AI) now includes `db_tbl_da_metrics.py`.
2. **Area status, Needs attention, last changed.** `agents/da_admin_overview.py` as designed above.
   Tests: 11-28 (a capability with no backup: attention line names it, catalog amber), 11-32 (an open row
   older than the stale days: catalog red; younger: amber), 11-11 (charter at 81%: amber with the percent
   in the line), 11-20 (a trigger off: the information line, Build and test amber), rules 9 of 10 amber
   and 11 rules red (an in-memory rulebook passed straight to the status function, because
   `restore_version` itself refuses an over-cap rulebook), empty model line, retired fields: empty for a fresh seed
   and non-empty for the Phase 1 shape loaded from `tests/data/da_rulebook_seed_phase1.json` (carried
   fields reported), "Nothing needs attention." for a made-up rulebook with none (a test-built rulebook,
   since the seed's own catalog may carry attention lines, checked in the test), last changed names the
   newest version touching each area and is empty when none did.
3. **Forms: Repository and index.** `rulebook_from_form` branch for tab `repo`
   (`TAB_REPO` in `da_admin_forms.py`), the server-settings read function
   `server_settings_view(settings)` in `agents/da_admin_overview.py` (name and shown value; the folder as
   set / not set; never a path or secret). Tests: 11-38 (settings listed, no key value and no folder path
   in the text, a sandbox folder set shows "set"), a repo save builds the right `Rulebook` (a changed
   `workspace_max_file_kb`), a pattern that does not compile is refused with the model's message, a
   save from the repo tab leaves the other policy fields and the retired-field list untouched, the whole
   problem list is returned (two bad values at once), and the shared Save pattern for `repo`
   (11-5 empty note, 11-6 saved, 11-8 stale, 11-9 no changes, 11-10 Cancel) as repo tests in a new
   `tests/test_da_admin_repo.py`: the 11a/11b pattern tests are per file, so no parametrised test exists
   to extend.
4. **Screen: Overview.** `overview_view(...)` in `layouts/da_admin_page.py` (areas table, Needs
   attention, health block with the window chooser), `admin_content` and the callbacks pass the new data,
   a callback for the window chooser and one that refreshes the Overview when its tab opens, attention
   lines link to their tab. The Overview shows the `version_line` header (11-3). Every new callback
   starts with the `is_admin` guard and raises `PreventUpdate` for a non-Admin, like `refresh_on_open`.
   Tests: layout builds from the seed, the header line is present, a non-Admin gets `PreventUpdate`
   from the window and refresh callbacks, empty database shows "No data yet" on
   every number and the Phase 10 text for Handoffs (11-40 on the screen), areas table has six rows with a
   status badge, window change redraws only the health block (plain function `health_content(settings,
   window)` called without Dash), Overview opens first (11-1), console still never imports the developer
   callbacks (11-44: the existing test parses only the callbacks file, so it is widened to every console
   module, the new ones included), `ADMIN_TABS` no longer says "Comes in" for Overview.
5. **Screen: Repository and index.** Layout (server settings read only, four editable fields as the
   existing text and list helpers), `EDITABLE_TABS` and `TABLES`/`TABLE_COLUMNS` entries, header line
   (11-3), other tabs disabled in Edit (11-4), no retired field (11-26). Tests: layout builds from the
   seed in read and edit view, edit form read back through `form_from_cells` and saved through
   `run_action` makes the new version, tab buttons disabled while editing, "Comes in" text gone for all
   eight tabs (a test over `admin_page`).
6. **Smoke, docs, review.** `da_smoke_check.py`: v2 saved from the Build and test form (one limit
   changed), v3 restored from v1 through the console's function, diff v1 to v2 lists one changed path,
   health numbers block runs on the smoke database (spec 14; each piece is added only if 11a/11b did not
   already add it, checked first). README: short 11c section. `docs/admin-work-test.md` (new, Command
   Prompt only, covers WF-1 to WF-8 as work-test steps; no real names). Full `pytest`, `ruff check .`, smoke check. Then code review (max 3 rounds).

## Done when (11c share of spec section 16)

11-1 (Overview first), 11-11, 11-20 (Overview half), 11-28, 11-32, 11-38, 11-39 to 11-43, plus the 11c
halves of 11-3, 11-4, 11-5 to 11-10 (the shared pattern works on `repo`), 11-26, 11-44, 11-45. 11-46
(Playwright) is cloud-only and not run here. The home check by Gian (`127.0.0.1:8050/admin`) is listed in
the PR body.

## Questions for the chief (readings, not blockers)

- Request kind (new, enhance, fix) is read from `EnhanceState.kind` inside `da_enhance_state.state`
  (no row = new).
- Pass rate and fix rounds count closed `build` and `rebuild` runs (stopped and escalated ones count as
  not passed); "Check my edits" runs are left out.
- Get help also counts the `escalated` event, because Enhance's Get help writes no status row
  (`da_enhance_help.py`, not changed here).
- All time is the default window of the chooser (a fresh install has few rows).
- "Files edited by developers" counts `da_workspace_files` rows with `kind = 'scanned'` (the laptop scan
  of edits), as the spec says.

## Risks

- The first-round pass definition decodes the stored JSON of Layers A and B. If a later phase changes
  those shapes the number changes silently; the test builds rows with the real models, so a model change
  breaks the test first.
- The Overview diffs every version against the one before to find "last changed". Fine for tens of
  versions; slow for thousands. Accepted for the pilot (judgement rules are capped at 10, versions are
  Admin saves).
- Timestamp text comparison assumes one format everywhere; step 1 confirms it before writing the SQL and
  a test pins it.
- Wide edits to `da_admin_page.py` and the callbacks file could regress 11a/11b screens; their tests
  stay in the suite and must pass at every step.
