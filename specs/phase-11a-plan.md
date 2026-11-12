# Phase 11a plan: Admin console, first part

Spec: `specs/phase-11-admin-console.md` (D-A to D-M chosen by chief, option 1 each). Branch
`auto/phase-11a`. Scope is the D-A "11a" slice only: page shell and access switch, Version history,
Project charter, Build and test (with zones and protected files), retiring the old fields and the five
triggers. 11b (Coding standards, UI standards, Capability catalog, `backup_senior`, `sonar_severity_map`,
`GoldenExample`) and 11c (Overview, metrics, Repository and index, smoke additions, work-test doc) are
NOT built here. Tabs 1, 3, 4, 5, 6 show a plain "Comes in 11b/11c" line so the console has its 8 tabs.

Pattern: pure rules in plain files (testable without Dash), one thin storage change, then the screen.
Each step ends with `pytest`, `ruff check .`, a commit and a push to `auto/phase-11a`. At most 3 steps
per run, then `chief_tick.py next "builder continue Phase 11a from step K"`. Code review only after the
last step (max 3 rounds). A stop rule firing goes to `ops/state/worker_note.md`.

## Design in plain words

- **One store.** Everything goes through the Phase 1 functions (`save_new_version`, `restore_version`,
  `list_versions`, `get_version`, `next_rule_id`). The console never writes SQL against the rulebook table
  (11-45). The only new SQL is a read-only count of pinned requests, in `db_tbl_da_requests.py`.
- **Retiring (spec 9, D-J, D-K).** `default_level`, `max_level`, `max_review_rounds` become `None` by
  default, `never_generate_zones` an empty list. A `model_serializer` on `Policy` leaves them out of the
  saved JSON when empty, so every new version is clean; old rows still load. `LEVELS`, `LOCKED_LEVEL`,
  `MIN/MAX_REVIEW_ROUNDS`, `_level_problems`, `_review_round_problems` go. `NeverGenerateZone` stays as
  the type of the old list (old versions hold it). Triggers: five names; a `Policy` validator maps the
  old names on load and adds missing ones as on. Restore strips the retired fields from the copy, so a
  restored old version holds the new shape (11-25). Retire check: `Grep` shows nothing in `src/` outside
  the model, seed and tests reads these fields (confirmed in planning).
- **New 11a Policy fields:** `generator_model`, `tester_model` (str, default ""),
  `admin_unassigned_stale_days` (int 1 to 365, default 14; stored now, used by 11c).
- **Access (WF-2 as a switch).** `DA_ADMIN_SOURCE` = `env` (default) or `codevision` placeholder that
  returns False and logs; `DA_ADMIN_IDS` comma list, default empty = nobody. `is_admin(settings, user_id)`.
- **Model per role (D-G).** `get_llm_client(role, settings, model="")`: a non-empty `model` (from the
  request's pinned version) wins over the `.env` model; empty keeps today's behaviour; the fake provider
  ignores it. The client helpers `get_build_client` and `get_tester_client` get an optional `model`;
  the build loop (holds the pinned rulebook) and the Enhance flow (`pinned`) pass it. Other callers
  (Approach, Refine lanes, safety net) stay on `.env` unless step 2 finds the pinned rulebook already in
  reach there; the step note lists which. Tests use `DA_LLM_PROVIDER=onprem` with a made-up URL and
  assert `client.model` (the constructor makes no network call); `complete` is never called.
- **Diff (D-L).** `agents/da_admin_diff.py`: flatten a `Rulebook` to `path -> value`, lists keyed by
  rule ID, zone/capability/glossary term name, or the item text for plain string lists (so a reorder is
  not a change; an edited string-list line shows as one removed plus one added, and the 11-34 test is
  written to match); returns added, removed, changed; `difflib` line diff for text over 200 characters.
- **Edit pattern (D-C).** `agents/da_admin_forms.py`: per tab a `rulebook_from_form(base_rulebook, form)`
  function and one shared `save_from_form(settings, tab, form, base_version, user_id, note)` that returns
  a result with kind `saved`, `problems`, `stale`, `unchanged` or `refused_note`, mapped from the Phase 1
  exceptions. **Lists are editable tables with Add row and Remove (spec section 2)**: one shared helper
  in `layouts/da_admin_page.py` draws a table from column names, used for zones (name, description,
  examples, path patterns), protected files, glossary (term, meaning) and the charter string lists; 11b
  reuses it. Cells are read back by pattern-matching ids. Bounds come from the model and are shown as a
  hint next to each number field; form values are validated by building the `Policy`, and any
  `ValidationError` becomes a plain "field: message" line (11-19). Retired fields never appear in any
  form (11-26).
- **Save always drops retired fields.** One helper `without_retired_fields(rulebook)` (in the models
  file) is used by BOTH `restore_version` and `save_from_form`, so a save from an old-shape active
  version (Gian's home v1) also writes a clean row. Tested from the old-shape seed.
- **Rules that must also guard restore live in `find_rulebook_problems`** (models file, step 1): two
  zones with the same name are refused there. The warning for a protected-file pattern that is also a
  whole folder in `allowed_folders` is a warning line returned by `save_from_form` (not a refusal).
- **11-7 reading:** with triggers always mapped to five on load, the second problem of 11-7 is built as
  a duplicate or unknown trigger name in a test-built rulebook, which `_trigger_problems` refuses; the
  form itself offers five on/off switches only. Noted for the chief; no spec change.
- **11-44 reading:** "nothing outside the LLM client changed" is read as "the LLM client plus the client
  helpers that pass the pinned name". Step 2 lists the exact files in its note; callers with no pinned
  rulebook in reach stay on `.env`.
- **Screen.** `layouts/da_admin_page.py` (layout function and the 8 tabs), callbacks in
  `callbacks/screen_callbacks/da_admin_page_callbacks.py` (own file, imports nothing from the developer
  page callbacks, 11-44). Home shell: second menu entry **Admin** and the path `/admin` on the existing
  `dcc.Location`, via a small route function so the developer layout is not touched.
- **Not touched:** WF-1 to WF-8 stay open. No new library. No AI call anywhere in the console.

## Plan review notes (approved, 0 Must fix)

- **No changes (R5) from an old-shape base:** `_refuse_if_unchanged` compares against
  `without_retired_fields(active.rulebook)` too, so an unchanged form from Gian's old home v1 gets the
  plain "No changes" line, not a clean-up version. Test in step 1.
- **Exact files for model per role:** `da_llm_client.py`, `da_build_agent.py` (`get_build_client`),
  `da_tester_agent.py` (`get_tester_client`), `da_build_loop.py`, `da_enhance_flow.py`. Other callers
  (Approach, Refine lanes, safety net, Understand, Discover) stay on `.env`. The factory is called with
  `model=` only when non-empty, so existing fake factories keep working.
- **Questions for the chief (readings, not blockers):** the 11-44 reading above, and the 11-7 reading.
- **Diff from an old-shape version** lists the four retired paths as removed; expected, shown once.

## Steps

1. **Models, seed, retiring.** Update CLAUDE.md "Current phase". `da_rulebook_models.py`: retired
   fields optional, serializer, five triggers with load mapping, `_trigger_problems` for five, remove
   level/review-round checks and constants, add the 3 new fields, duplicate zone name check,
   `without_retired_fields`. Seed JSON: retired fields dropped, five
   triggers, new fields. `tests/data/da_rulebook_seed_phase1.json`: copy of the old seed. `restore_version`
   strips retired fields. Rewrite the Phase 1 tests that proved levels and review rounds in
   `test_da_rulebook_models.py`, `test_db_tbl_da_rulebook.py` and `test_da_refine_merge.py` (they now
   prove "old version loads and shows nothing"). Tests 11-19, 11-20 (save half), 11-23, 11-24, 11-25,
   11-27, the trigger mapping, a save from the old-shape active version writes no retired key.
2. **Access switch, model per role.** `DA_ADMIN_SOURCE`, `DA_ADMIN_IDS` in `da_config.py` and
   `.env.example`; `agents/da_admin_access.py`; `get_llm_client(..., model=)` and the build/tester agents
   passing the pinned names. Tests 11-2 (function part), 11-21, 11-22, `is_admin` env list and
   placeholder log.
3. **Diff, pinned counts, timeline data.** `agents/da_admin_diff.py`, `count_pinned_by_version` and
   `list_pinned_request_ids` in `db_tbl_da_requests.py`, timeline builder (version rows with areas
   touched and pinned counts). Tests 11-33, 11-34, 11-35, 11-36 and the area mapping (charter, rules,
   policy build and test).
4. **Forms and save pattern.** `agents/da_admin_forms.py` for Charter and Build and test (limits,
   models, five triggers, zones, protected files, advanced limits). Tests 11-5 to 11-10 (function part),
   11-11, 11-19, 11-20, 11-23, stale save names the newer version, whole problem list returned, cancel
   leaves the active version untouched (nothing written until Save).
5. **Screen A: shell and read views.** `da_admin_page.py` layout with the table helper, 8 tabs,
   placeholders for 11b/11c tabs, read views for Charter and Build and test with the version header line
   and bound hints, the refusal page, callbacks file (access only), home server route and menu. Tests:
   11-1, 11-2, 11-3, 11-18 (fields present, Advanced limits collapsed), 11-26, every layout builds from
   the seed, 11-44 (no import from the developer callbacks), 11-45 (no `da_rulebook_versions` SQL
   outside the storage file).
6. **Screen B: Edit, Save, Cancel.** Form mode, other tabs disabled, note dialog, problems list, stale
   message with Reload, "No changes", green "Saved as v<n>" line, Cancel. Tests 11-4, 11-6 (screen line).
7. **Screen C: Version history.** Timeline with pinned counts, diff picker, Restore dialog with the
   pre-filled note, Phase 1 refusals shown. Tests 11-33, 11-37 (v4 "Restored from v1"; restoring the
   active version refused).
8. **Docs and checks.** Minimal 11a part only: a short README section and the existing smoke check run
   plus a small 11a addition (v2 from the Build and test form function, v3 restored from v1, diff v1 to
   v2 lists one changed path). D-A puts the full smoke and the work-test doc in 11c. CLAUDE.md phase
   line, full `pytest`, `ruff check .`, smoke check. Then code review (max 3 rounds).

## Done when (11a share of spec section 16)

11-1 to 11-11, 11-18, 11-19, 11-20 (save half only; the Needs attention line is Overview, 11c), 11-21 to
11-27, 11-33 to 11-37, 11-44, 11-45. Not in 11a: 11-12 to 11-17, 11-28 to 11-32, 11-38 to 11-43
(11b/11c). 11-46 (Playwright) is cloud-only and not run here.

## Risks

- Dropping empty retired keys on save changes the stored JSON shape; the equality check
  (`_refuse_if_unchanged`) compares models, not text, so it is unaffected.
- Callers of `get_llm_client` with no pinned rulebook in reach keep `.env` models until a later fix.
- Dash callback ids for a form with many fields: kept as pattern-matching ids in one dict per tab.
