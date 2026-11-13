# Phase 11b plan: Admin console, second part

Spec: `specs/phase-11-admin-console.md` (D-A to D-M chosen by chief, option 1 each). Branch
`auto/phase-11b`, made from `auto/phases-7-10` after PR 66 (11a) merged. Scope is the D-A "11b" slice:
**Capability catalog with the Unassigned queue (tab 4), UI standards (tab 5), Coding standards (tab 6)**
and the model changes they need (`backup_senior`, `sonar_severity_map`, `GoldenExample`, new checks).
11c (Overview, metrics, Repository and index, work-test doc, full smoke) is NOT built here. Tabs 1 and 3
keep their "Comes in 11c" line.

Pattern as in 11a: pure rules in plain files first (testable without Dash), then the screen. Each step
ends with `pytest`, `ruff check .`, a commit and a push to `auto/phase-11b`. At most 3 steps per run, then
`chief_tick.py next "builder continue Phase 11b from step K"`. Code review only after the last step
(max 3 rounds). A stop rule firing goes to `ops/state/worker_note.md`.

## Design in plain words

- **Same store, same pattern.** Every save goes through `save_from_form` (11a) and the Phase 1
  functions. New tabs add a `rulebook_from_form` branch per tab. No SQL against the rulebook table (11-45).
  The only reads added are over `da_tester_findings` (Cited column) and `da_unassigned_files` (through
  the Phase 9 functions).
- **Model changes (spec 6, 7, 13), all with defaults so older versions still load:**
  `Capability.backup_senior: str = ""`; `Policy.sonar_severity_map: dict[str, Severity]` (defaults
  BLOCKER must_fix, CRITICAL must_fix, MAJOR should_fix, MINOR fyi, INFO fyi); new `GoldenExample`
  (`title`, `tags`, `code`, `why`) and `Rulebook.golden_examples: list[GoldenExample] = []`.
  `find_rulebook_problems` gains: capability names unique (case-insensitive), every capability pattern
  non-empty, sonar map has exactly the five keys (names the missing or extra key). Golden examples need
  a non-empty title and code (model-level).
- **Approved vs blocked overlap (11-14), review Must fix 1.** `requests` is today in BOTH default lists
  and in the seed (Approach accepts it, Build blocks it: "blocked wins"). A check inside
  `find_rulebook_problems` would lock every save on every tab (and the seed). So: (a) the overlap check
  is `library_overlap_problems(policy)` in `da_admin_forms.py`, run only on the **Coding standards** save
  (compared by `library_name`, which lower-cases and turns `-` into `_`), names the library; (b) step 1
  removes `requests` from `DEFAULT_APPROVED_LIBRARIES` and from the seed's approved list, which equals
  what Build already enforces, so only Approach stops listing it as approved. Noted for the chief as a
  reading; an existing database whose active version has the overlap keeps working on all other tabs and
  the first Coding save shows the name to fix. Step 1 runs the whole suite at once to catch Phase 4 to 9
  tests that expect `requests` approved.
- **Warnings (not refusals), from `save_from_form`:** a capability pattern that cannot match any allowed
  folder. Rule: a pattern starting with `*` or `?` may match any root and never warns; otherwise its
  fixed start (text before the first `*`/`?`/`[`) must start with an allowed folder, or be a prefix of
  one. Tested: the seed gives no warning, `docs/x.py` does. Same helper style as the 11a protected-file
  warning.
- **Seed** gets the new fields at their defaults, one made-up golden example, and made-up backup
  seniors on the seed capabilities (except none is hidden: the 11-28 test builds its own catalog).
  `src/data/da_sonar_checks_sample.json`: made-up key, name, SonarQube severity, read only.
- **Add row for rules (spec 7, 11-12/11-13).** The screen's Add row on a rule table calls
  `next_rule_id(db_path, kind)` at once (judgement for Coding, ui_convention for UI), so the number is
  used up even if Cancel follows; the form says so in one hint line. At 10 judgement rules Add row shows
  the cap message and adds nothing (11-13); the counter reads "7 of 10".
- **Rule table shape.** A rule has long fields (why, good and bad example), so the edit form is one row
  of cells per rule using the 11a `list_table` helper: columns `rule_id`, `title`, `tags`, `severity`
  (dropdown), `why`, `good_example`, `bad_example`, `source`, and on the Coding tab a read-only `Cited`
  column (read and edit view). **How the ID travels (review Must fix 2):** the 11a callbacks read back
  only `adm-cell` values, so `rule_id` is a **disabled input that keeps the `adm-cell` id** (its value
  is read like any cell); the severity Select also carries the `adm-cell` id itself, not a wrapper.
  Test: a drawn edit form read back through `form_from_cells` keeps every rule ID, also after Add row
  and Remove. `kind` is fixed by the tab. `rulebook_from_form` refuses a row without an ID. A new row
  with only its ID and nothing typed is dropped (like the glossary) and its ID stays used up. Rules of
  the other kind are kept untouched. **Tags:** a one-per-line text area (the 11a way); the DMC tags
  input is a later polish. The seed tags are listed in a hint line under the table. Deviation from
  spec 7 "chips", stated here, no new library.
- **Cited column (read only).** SQL goes in `db_tbl_da_tester.py` as `count_kept_cites(db_path)` (SQL
  lives in `db_table_functions`, review Should fix); `agents/da_admin_cited.py` is a thin wrapper that
  returns `{rule_id: count}`. The step confirms the exact column names and what "kept" means from
  `db_tbl_da_tester.py` before writing it, and notes it. 11c reuses it for "Rules cited".
- **Where "Move to" is stored (spec 19, review Should fix).** A Move resolves the row `changed` and the
  chosen capability is stored in a **new nullable column `resolved_capability`** on `da_unassigned_files`
  (spec 19 rule: add a nullable column; `ensure` adds it with `ALTER TABLE ... ADD COLUMN` if missing,
  and `resolve_unassigned` gets an optional `resolved_capability=""` argument; the "resolved rows
  cannot be edited" trigger only guards UPDATE of resolved rows, so the column is set in the same
  UPDATE that resolves). Show resolved displays it. Confirm leaves it empty (the pick stands).
- **Catalog order in the diff (review Should fix).** `flatten_rulebook` gets one extra entry
  `policy.capabilities.order` (the names joined in order) so a catalog reorder shows in the diff and
  under Capability catalog. Rule reorders still give an empty diff (11-35). `GoldenExample` is keyed by
  `title` (add `title` to `_ITEM_KEYS`).
- **Catalog and queue logic (`agents/da_admin_catalog.py`, plain code).**
  `would_match(path, capabilities)` reuses `lookup_capability` from `da_enhance_checks.py` (first match
  wins, same function the developer flow uses, so Admin sees exactly what a request would get).
  `queue_rows(settings)` joins `list_unassigned` with `would_match` against the **active** catalog.
  `resolve_row(settings, unassigned_id, state, capability, admin_id, add_pattern: bool, note)`:
  state `confirmed` or `changed` calls `resolve_unassigned`; the optional pattern offer (D-E) is a normal
  `save_from_form` on the catalog tab that appends the path as a pattern to the chosen capability, with
  the required change note. Order: the pattern save first, then the resolve, so a refused save leaves the
  row open and nothing half done. The request's record is never touched (11-31). Show resolved lists
  the last 50 resolved rows with who and when.
- **Catalog edit.** Rows: name, description, named senior, backup senior, path patterns (one per line);
  Move up and Move down buttons per row (first match wins). Implemented as two small callbacks that
  swap rows in the draft form, same mechanism as Add row and Remove.
- **Screen.** Tabs 4, 5, 6 join `EDITABLE_TABS`; `TABLES` in the callbacks file gains their tables.
  The new tabs reuse the 11a ids. New ids: the queue buttons (`adm-q` type). The queue lives under the
  catalog table and is shown only in read view: while the catalog is in Edit mode its buttons are
  disabled (one change at a time), and a click on a stale view hits the stale path below.
- **Offer when an earlier capability already matches.** Lookup is first match wins. If an earlier
  capability already matches the path, adding the pattern to the chosen one changes nothing, so the
  dialog does not offer it and says which capability matches first (tested).
- **Sonar map UI.** Five dropdowns (right-hand side only), then the sample list read only, each row
  showing the mapped severity, with the banner "Sample list. The real list comes from SonarQube when
  access is decided (WF-4)."
- **Golden examples:** a table (title, tags, code, why). Stored only; a test proves no prompt builder
  reads `golden_examples` (scan of the prompt-building files in `src/agents`, leaving out
  `da_admin*.py`, same style as the 11a no-AI test).
- **Seed catalog:** gets made-up backup seniors on its capabilities. 11-28 uses its own test catalog.
- **11-44 / 11-45:** the 11a tests scan `da_admin*.py` files by glob, so the new files are covered
  automatically; step 6 names this and confirms it.
- **Not touched:** WF-1 to WF-8 stay open. No new library. No AI call. Developer page untouched.
  11a screens are changed only where the shared helper needs a new column type.

## Steps

1. **Models, seed, checks.** Update CLAUDE.md "Current phase" (11b). `da_rulebook_models.py`:
   `backup_senior`, `sonar_severity_map`, `GoldenExample`, `golden_examples`, the three new checks;
   `requests` out of the default approved list. Seed JSON gets the new fields (and loses `requests`
   from approved); `src/data/da_sonar_checks_sample.json` (new); `resolved_capability` column and
   `resolve_unassigned` argument; diff `order` entry and `title` key. Test an 11a-shape version
   (current seed before this step, copied to `tests/data/da_rulebook_seed_11a.json`) still loads with
   defaults, and restoring it writes the new fields. Run the **whole** suite now. Tests: 11-16, 11-17
   (model half), duplicate capability name, empty pattern, old version loads, seed loads and publishes
   and has no approved/blocked overlap, resolved column added to an existing database, catalog reorder
   shows in the diff.
2. **Forms: UI standards, Coding standards.** `rulebook_from_form` branches for tabs `ui` and `coding`:
   rules (by kind), approved libraries, blocked imports, sonar map, golden examples. `agents/
   da_admin_cited.py` for the Cited counts. An `add_rule_row(db_path, kind)` helper that calls
   `next_rule_id` and applies the 10-rule cap message. Tests: 11-12 (ID from `next_rule_id`, next Add row
   gets the following number after Cancel), 11-13, 11-14 (Coding save refused naming the library, also
   with `-` vs `_` spelling; a Build tab save on an overlapping version still works), 11-15 (MAJOR
   to fyi saved), 11-17 (golden example in the new version, and no prompt contains it), Cited counts on
   a made-up database, the other kind's rules are kept untouched, a form row without an ID is refused,
   an untouched new row is dropped, whole problem list returned. The shared pattern (11-5 to 11-10:
   empty note, saved line, problems list, stale names the newer version, no changes, Cancel) is run
   as **one parametrised test over the tabs `ui`, `coding`, `capability`** once step 3 exists.
3. **Forms: Capability catalog and the queue logic.** `rulebook_from_form` branch for tab `capability`
   (with move up and down helper on the draft), the no-folder-match warning, `agents/
   da_admin_catalog.py` (`would_match`, `queue_rows`, `resolve_row`, `resolved_rows`). Tests: 11-28
   (backup senior missing is detectable by a plain function `capabilities_without_backup`, used by 11c),
   11-29 (row shows path, pick, request, waiting since, would match), 11-30 (confirm, pattern offer
   accepted gives a new version with a note, row `confirmed` by the Admin ID), confirm without the offer,
   a refused pattern save leaves the row open, no offer when an earlier capability matches, 11-31
   (move: row `changed`, `resolved_capability` stored, request record untouched), the no-folder-match
   warning rule,
   catalog order matters (swap changes `would_match`), show-resolved limit 50.
4. **Screen: UI standards and Coding standards.** Layout functions for both tabs (read view with header
   line, rule table, counter, hints), edit mode with Add row calling the ID helper, the severity dropdown
   cell, libraries and blocked lists, sonar map with sample list and banner, golden examples table,
   callbacks `TABLES` extended. Tests: both tabs build from the seed, header line (11-3), counter text,
   Cited column with a made-up count, banner text, sample list shows `fyi` for the `MAJOR` checks after
   the map is changed (11-15), no retired field (11-26), 11-4 for these tabs (other tabs disabled),
   rule IDs survive `form_from_cells` after Add row and Remove, the Add row at 10 shows the cap message.
5. **Screen: Capability catalog and Unassigned queue.** Catalog table with backup senior, Move up and
   Move down, the queue block below it (path, pick, request, waiting since, would match, Confirm and
   Move to...), the pattern-offer dialog with the required note, Show resolved. Callbacks for the queue
   in the same file. Tests: layout builds from the seed with and without queue rows, the queue actions
   through `run_queue_action` (plain function, as `run_action` in 11a) for 11-29 to 11-31, the stale
   case when the catalog changed between draw and click, queue buttons disabled in Edit mode, header
   line and other-tabs-disabled (11-3, 11-4) on the catalog tab, no retired field (11-26).
6. **Docs and checks.** README: short 11b section. Smoke check addition: a rule added through the forms
   function, Cited count runs on the smoke database, one queue row confirmed. CLAUDE.md phase line. Full
   `pytest`, `ruff check .`, smoke check. Then code review (max 3 rounds).

## Done when (11b share of spec section 16)

11-12 to 11-17, 11-29 to 11-31, plus the 11b halves of 11-3, 11-4, 11-5 to 11-10 (the shared pattern
works on the three new tabs), 11-26 (no retired field on the new tabs), 11-44, 11-45. 11-28 and 11-32
need the Overview (11c); 11b ships the plain functions they will use (`capabilities_without_backup`,
the queue rows with their age). 11-46 (Playwright) is cloud-only and not run here.

## Plan review notes (approved on the second review, 0 Must fix)

- `resolve_row` takes `base_version` (the version the screen was drawn from) and passes it to
  `save_from_form`, so the pattern save detects a stale view.
- Step 1 also adds `resolved_capability` to the `UnassignedFile` model and `_to_unassigned`; a test reads
  it back. A small read function `list_resolved(conn, limit=50)` in `db_tbl_da_enhance.py` merges both
  resolved states, newest first; tested at the limit of 50.
- Step 4: `run_action` sends `adm-add` on the two rule tables to `add_rule_row(db_path, kind)`; the cap
  message appears as a notice and no row is added.
- Duplicate golden example titles are refused on the Coding save. The queue is drawn in read view with
  its buttons disabled while the catalog is in Edit mode (one wording).

## Questions for the chief (readings, not blockers)

- `requests` removed from the default approved libraries (it was in both lists; Build already blocks it).
- Tags as one-per-line text, not chips (no new library).
- Overlap check runs on the Coding save, not in `find_rulebook_problems`, so it cannot lock other tabs.

## Risks

- The rule table is wide (8 columns); it may look cramped. It works, and a nicer layout is a later fix.
- Add row spends a rule ID even when Cancel follows. By design (Phase 1 R7), stated on the form.
- Pattern save then resolve are two writes, not one transaction (two different stores). If the resolve
  fails after the save, the catalog has the new pattern and the row stays open; Confirm can be pressed
  again and sees "a pattern already matches". Accepted, and tested.
- The Cited SQL depends on `da_tester_findings` columns; step 2 confirms them before writing it.
- Wide edits across `da_admin_page.py` (shared helper) could regress 11a screens; the 11a tests stay in
  the suite and must still pass at every step.
