# Phase 11: Admin console and health metrics

Status: DRAFT v0.1 (12 Nov 2026). Written by the spec writer. Not yet approved by Gian. The chief applies
the decision rule (`specs/phase-a-automation.md` section 6) to D-A to D-M (section 17). The work facts
(section 18) need Gian and get no recommendation.
Depends on: Phase 9 (catalog, Unassigned queue), merged into `auto/phases-7-10`. **Phase 10 is on hold
(Gian, 12 Nov 2026); Phase 11 is built first** and must not depend on Phase 10 code.
Next: Phase 10, Review my code, Handoff, Escalations inbox.
Source of truth: `specs/redesign-2026-10-31.md` section 7 (AD1, the Admin console changes), section 6
(model per role is an Admin setting), section 5.11 (the five escalation triggers), section 8 (phase
list), and `specs/phase-11-facts.md` (Gian, 12 Nov 2026).
Facts: `specs/phase-11-facts.md`. Nothing about work is assumed beyond it.
Visual reference: none in the repo. Gian's Admin concept demo (25 Oct) is **not** in the repo (real
names); the facts file's "Screen reference" section replaces it. The developer demo
(`docs/CodeVision_Developer_Assistant_Demo.html`) is not used by this phase.
Build: worker team, branches `auto/phase-11a`, `auto/phase-11b`, `auto/phase-11c` (D-A), merged into
`auto/phases-7-10` by the chief.

## In plain words

Every phase since Phase 1 **reads** the rulebook: the charter, the coding rules, the flag-for-review
zones, the protected files, the approved libraries, the build limits, the catalog. Until now the only
way to change it is to edit `src/data/da_rulebook_seed.json` and reload. Phase 11 builds the
**maintenance screens** so the CodeVision core team ("Admin") changes the rules without touching JSON,
with every save kept as a new version, and an **Overview** with health numbers that say how the
assistant is doing.

AS400 comparison: Phase 1 built the data areas and the files (the rulebook). Phase 11 is the
`WRK*`/`CHG*` menu over them: a display file per area, `F6` to edit, a required change note on save
(like a journal entry's reason code), and `DSPJRN` plus a one-click "copy the old member back" for
history. Nothing is ever overwritten; the newest version is the active one, and a job that already
started keeps the version it opened with.

What Phase 11 does **not** do: it does not make Phase 10 happen early. The five escalation triggers and
the flag-for-review zones are **edited and saved here**; Phase 10 acts on them later. Any number that
needs Phase 10 data shows "No data yet (comes with Phase 10)", never a made-up number.

## Words used in this spec

| Word | Meaning |
|---|---|
| Admin | A member of the CodeVision core team allowed to open the console. Who that is at work is WF-2 |
| Console | The Admin page: 8 tabs (section 3), reached at `/admin` at home (D-B) |
| Tab | One of the 8 screens. Each has a read view and an Edit button |
| Edit mode | The tab's fields become a form. Save asks for a change note; Cancel discards everything |
| Version | One row of `da_rulebook_versions` (Phase 1). Every save is a new one; the newest is active |
| Pinned | A request keeps the version that was active when it was created (Phase 1, 2.4). Never changes |
| Retired field | A `Policy` field the redesign removed (`default_level`, `max_level`, `never_generate_zones`, and `max_review_rounds`, section 9) |
| Trigger | One of the five fixed escalation triggers (redesign 5.11), on or off |
| Unassigned row | A file a developer put in a capability that Admin has not confirmed yet (Phase 9, section 11) |
| Health number | A plain-code count or rate over the existing tables (section 12). Never from an AI |
| Needs attention | A plain-code list on the Overview of things an Admin should look at (section 4) |
| Sample check list | A made-up list of SonarQube-style checks shown read-only until WF-4 is answered |

## 1. Decisions already made (do not reopen)

| # | Decision | Source |
|---|---|---|
| 1 | The rulebook store is the Phase 1 one: versioned, append-only, every save is a new version with a required change note, restore copies an old version into a new one, requests are pinned. **No second store** | Phase 1, facts "What is already built" |
| 2 | Saves apply to **new** requests only; a request in progress keeps its pinned version | Facts, Phase 1 2.4 |
| 3 | No maker-checker and no pre-publish testing for now | Facts (Admin concept, Oct 2026) |
| 4 | Admin = the CodeVision core team. The UOB brand team owns official styles; Admin mirrors them | Facts |
| 5 | Judgement rules capped at 10 for the pilot. Rule IDs are generated and never reused | Facts, Phase 1 R7 |
| 6 | SonarQube checks are governed in SonarQube; Admin only maps severities. The check list is read-only | Facts |
| 7 | Escalation triggers: a fixed list of **5**, on/off only: cap hit twice in a row, out of scope, dispute, Tester unable twice, Get help | Redesign 5.11, 7 |
| 8 | Flag-for-review zones replace never-generate zones: description and examples per zone; effect = the named senior is a required PR reviewer (the PR part is Phase 10). They never block | Redesign 7, Phase 4 D-E |
| 9 | Protected files: files the AI may never write; needing one is flagged in Approach (built, Phase 4) | Redesign 7 |
| 10 | Approved libraries: Layer A checks imports against the list (built, Phase 6) | Redesign 7 |
| 11 | Build and test settings: max fix rounds (3), test time limit (60 s), max files per request (5), auto-escalation (cap hit twice in a row), model per role. **No L0 to L3, no "AI code kept %"** | Redesign 6, 7 |
| 12 | Overview metrics: first-round pass rate, average fix rounds, requirement revisions per request, files edited by developers, escalations, Tester findings by type. "AI code kept %" is removed | Redesign 7 |
| 13 | Capability catalog gets the Unassigned queue: confirm the developer's pick, or move the file | Redesign 7, Phase 9 WF-4 |
| 14 | Escalations go to a named senior per capability, with a backup. The inbox itself is Phase 10 | Facts |
| 15 | Rules are tagged by Admin and shown to developers (built: `tags` on every rule) | Facts |
| 16 | Developer-facing wording: "negative scenario", never "failure" | Facts, Phase 6 fixes |
| 17 | Phase 10 is on hold. Admin saves the settings; Phase 10 reads them later. Metrics needing Phase 10 data show a plain "No data yet" state | Facts (Gian, 12 Nov) |
| 18 | Charter, UI standards and Version history tabs are unchanged from the concept | Facts |
| 19 | The notification channel for escalations (email or Teams) is pending bank approval: out of scope | Facts |
| 20 | Dash Mantine Components, the CodeVision folder layout, new files start with `da_`, Developer Assistant screens use `src/styles` (not `cv_styles.py`) | CLAUDE.md, facts |

## 2. The shape of every tab

Each tab works the same way, so the builder writes the pattern once (D-C):

1. **Read view.** The active version's content for that area, plain and labelled. The header line says
   "Active version v<n>, saved by <id> on <date>: <change note>".
2. **Edit** turns the fields into a form. While in edit mode the other tabs are disabled (one change at
   a time, one note per save).
3. **Save** opens a small dialog: a required **change note** (empty is refused, Phase 1 R2). Plain code
   builds the new `Rulebook` from the form, runs `find_rulebook_problems`, and calls
   `save_new_version(base_version=<the version the Edit started from>)`. Problems: the whole list is
   shown above the form (Phase 1 R3), nothing is saved. Stale (Phase 1 R4, someone saved first): the
   message names the newer version and offers **Reload v<n>**, which discards the form.
   "No changes to save" (R5) is shown as a plain line, not an error.
4. **Cancel** discards the form and returns to the read view.
5. After a save the read view shows the new version and a green line "Saved as v<n>. New requests use it
   from now; requests in progress keep their version."

Every number field has the bound the `Policy` model already gives it (for example `build_max_rounds`
1 to 5), shown as a hint next to the field. Lists (zones, files, libraries) are editable tables with
**Add row** and **Remove**. A removed rule is gone from the new version but its ID is never reused
(Phase 1 R7); the read view of an old version still shows it.

**Editing is the only writer.** The console calls the Phase 1 functions and the Phase 9 Unassigned
functions. It never runs SQL of its own against the rulebook table.

## 3. The 8 tabs

| # | Tab | What it shows and edits | Part |
|---|---|---|---|
| 1 | Overview | Rulebook areas with status, Needs attention, health numbers (sections 4, 12). Read only | 11c |
| 2 | Project charter | The 5 charter sections (purpose, in scope, out of scope, principles, constraints) and the glossary; the size check (green, amber, red). Edit | 11a |
| 3 | Repository and index | Read-only server settings (search provider, top-k, discovery rounds, main source, sandbox source folder, from `.env`) and the editable `Policy` fields `allowed_folders`, `new_file_name_pattern`, `workspace_markers`, `workspace_max_file_kb` (D-D) | 11c |
| 4 | Capability catalog | The capabilities (name, description, named senior, **backup senior**, path patterns) and the **Unassigned queue** (section 6). Edit | 11b |
| 5 | UI standards | The `ui_convention` rules (`CV-UI-*`): title, tags, severity, why, good and bad example, source. Edit | 11b |
| 6 | Coding standards | The `judgement` rules (`CV-PY-*`, cap 10, counter shown "7 of 10"), **Approved libraries**, blocked imports, the **SonarQube severity map** with the sample check list, **golden examples** (section 7). Edit | 11b |
| 7 | Build and test | Limits (section 8), model per role, the 5 triggers, flag-for-review zones, protected files. Edit | 11a |
| 8 | Version history | Timeline, what changed, requests pinned, Restore (section 10) | 11a |

Where the console hangs: at home, a second menu entry **Admin** in `da_home_web_server.py` and the path
`/admin` on the existing `dcc.Location` (D-B). At work, CodeVision's own menu (WF-6). The console is one
layout function `layouts/da_admin_page.py` with its own callbacks file, so the developer page is not
touched.

**Access check (WF-2, built as a switch):** `agents/da_admin_access.py`, `is_admin(settings, user_id)`.
Setting `DA_ADMIN_SOURCE`: `env` (home: the comma-separated list `DA_ADMIN_IDS` in `.env`, default
empty = nobody) or `codevision` (a placeholder that returns False and logs "Admin access is not
configured yet", the same pattern as `DA_SEARCH_PROVIDER=codevision`). Not an Admin: `/admin` shows
"This page is for the CodeVision core team." and nothing else. The real source at work is WF-2.

## 4. Overview

Read only. Three blocks:

1. **Rulebook areas.** One row per tab 2 to 7: area, a one-line summary ("5 judgement rules, 2 UI
   conventions", "3 capabilities, 2 Unassigned"), status (green, amber, red; section 5), last changed
   (the newest version whose diff touched that area, section 10).
2. **Needs attention.** Plain code, from the active version and the tables:
   - charter amber or red (size check),
   - judgement rules at the cap (10 of 10),
   - one or more open Unassigned rows ("2 files wait for a capability", a link to tab 4),
   - a capability with no backup senior,
   - a trigger that is off (information: "Out of scope trigger is off"),
   - a model per role left empty ("Tester model: uses the server default", D-G),
   - a retired field still carried (never shown after 11a; a test proves the list is empty for a
     fresh seed).
   Empty list: "Nothing needs attention."
3. **Health numbers** (section 12), with the time window chooser **Last 30 days / All time**.

## 5. Area status (plain code)

| Status | Rule |
|---|---|
| green | no Needs attention line points at this area |
| amber | an information line points at it (charter amber, rules at 9 of 10, a trigger off, an empty model) |
| red | charter red, rules over the cap (an old version restored under a tighter cap), an open Unassigned row older than `admin_unassigned_stale_days` (section 8) |

## 6. Capability catalog and the Unassigned queue

**Catalog edit:** the Phase 9 `Capability` part plus one new optional field `backup_senior: str = ""`
(decision 14; empty keeps older versions loading). Rules on save (added to `find_rulebook_problems`):
names unique (case-insensitive), every pattern non-empty, a pattern that matches no allowed folder root
is a warning line (not a refusal). Catalog order matters (Phase 9: first match wins), so rows can be
moved up and down.

**Unassigned queue (below the catalog, read from `list_unassigned()`):** path, the capability the
developer picked, request ID, waiting since, and, from plain code, which capability the **active**
catalog would give the path today ("Would match: Reports" or "No match"). Two actions per row,
both calling the Phase 9 `resolve_unassigned`:

- **Confirm** (state `confirmed`, resolved by the Admin ID): the pick stands. If no active capability
  pattern matches the path, the dialog offers to **add the path as a pattern** to the picked capability
  (this is a rulebook save: change note required, new version). D-E.
- **Move to…** (state `changed`): a dropdown of the catalog; the same optional pattern offer for the
  chosen capability.

A resolved row leaves the open list; **Show resolved** lists the last 50 with who and when. The request
that queued the file is **not** changed (its record keeps the developer's pick and the
"capability not yet confirmed by Admin" mark; Phase 10's PR summary reads the queue state). How Admin is
told about a new row is Phase 9 WF-4 (carried, WF-7 here): in-app only.

## 7. Coding standards

- **Judgement rules:** the table; Add row takes the next ID from `next_rule_id("judgement")` the
  moment the row is added (the number is used up even if Cancel follows, by design, Phase 1 R7, and
  the form says so). Tags are free text chips; the seed's tags (`general`, `data`, `logging`, `ui`) are
  offered first. Severity `must_fix`, `should_fix`, `fyi`. **Cited** column: how many kept Tester
  findings cite this rule ID (`da_tester_findings.cites`, all time), plain code, read only.
- **Approved libraries** (`approved_libraries`) and **Blocked imports** (`build_blocked_imports`):
  editable lists. A name in both lists is refused on save with the name.
- **SonarQube severity map (D-F):** new `Policy` field `sonar_severity_map: dict[str, Severity]`
  with the five fixed keys `BLOCKER`, `CRITICAL`, `MAJOR`, `MINOR`, `INFO` (defaults: must_fix,
  must_fix, should_fix, fyi, fyi; made up). Only the right-hand side is editable; a missing or extra
  key is refused on save. Below it the **sample check list**: read only, from
  `src/data/da_sonar_checks_sample.json` (made up: key, name, SonarQube severity), each shown with the
  mapped severity. A banner says "Sample list. The real list comes from SonarQube when access is
  decided (WF-4)."
- **Golden examples (D-H):** new rulebook part `GoldenExample` (`title`, `tags`, `code`, `why`), a
  list `golden_examples` on `Rulebook` (default empty). Stored only; not sent to any AI call in this
  phase.

## 8. Build and test

| Field | Shown as | Today |
|---|---|---|
| `build_max_rounds` | Max fix rounds | 3 |
| `build_test_timeout_seconds` | Test time limit (seconds) | 60 |
| `max_files` | Max files per request | 5 |
| trigger `cap_hit_twice` | Auto-escalation: round cap hit twice in a row (on/off) | on |
| `generator_model`, `tester_model` (new, D-G) | Model per role | empty = `.env` |
| `escalation_triggers` | The 5 triggers, on/off (section 9) | all on |
| `flag_review_zones` | Name, description, examples, path patterns | Security, Login |
| `protected_files` | Patterns | 5 |
| **Advanced limits** (collapsed) | every other numeric `Policy` field: `build_max_prompt_chars`, `build_max_parallel`, `tester_*`, `refine_*`, `enhance_*`, `safety_net_*`, `impact_max_callers`, `max_design_choices`, `max_material_decisions`, and the new `admin_unassigned_stale_days` (default 14) | as the seed |

Zones and protected files live on this tab as sections (D-I). A zone with no pattern is refused (the
model already says so); two zones with the same name are refused on save. A protected-file pattern that
also appears in `allowed_folders` as a whole folder is a warning line.

**Model per role (D-G):** two text fields, "model name as CodeVision knows it". Empty = the `.env`
value (`DA_ONPREM_MODEL` / `DA_ONPREM_TESTER_MODEL`, or the Claude ones at home). The LLM client reads
the names from the **request's pinned version**, so a request keeps its models like it keeps its rules.
With the `fake` provider the names are ignored. Which names exist at work (`default`, `reasoning-vlm`,
redesign 6) and which to pick per role is WF-5.

## 9. Retiring the old fields and the three old triggers (D-J, D-K)

Nothing in `src/` reads `default_level`, `max_level`, `never_generate_zones` or `max_review_rounds`
(only the model, the seed and Phase 1 tests). Older saved versions still hold them and **must still
load** (Phase 1 R1: they are never rewritten).

1. The four fields become optional on `Policy` (`Level | None = None`, `list = []`,
   `int | None = None`). `_level_problems` and `_review_round_problems` are removed from
   `find_rulebook_problems`; `LEVELS`, `LOCKED_LEVEL` and friends go with them (the Phase 1 tests that
   proved them are rewritten to prove "an old version with these fields loads and shows nothing").
2. The console never shows them. A save from the console writes a rulebook **without** them (they are
   dropped from the dump when `None` or empty). The seed file drops them too.
3. **Triggers:** `ESCALATION_TRIGGER_NAMES` becomes the five of decision 7: `cap_hit_twice`,
   `out_of_scope`, `dispute`, `tester_unable_twice`, `get_help`. A `Policy` validator maps the three
   old names on load (`max_rounds_with_must_fix_open` to `cap_hit_twice`,
   `developer_disputes_finding` to `dispute`, `out_of_scope` unchanged) and adds any missing trigger
   as **on**. `_trigger_problems` demands exactly the five. So an old version loads with five triggers,
   and **restoring** it saves the mapped shape (restore re-checks problems, Phase 1).
4. A test loads a version saved with the Phase 1 shape (the old seed, kept under `tests/data/`) and
   proves: it loads, the four fields are `None` or empty, five triggers, the Phase 4 to 9 defaults.

Phase 10 reads the five names; until then no code acts on them except "Get help", which already exists
and is unchanged.

## 10. Version history

- **Timeline:** every version, newest first: number, when, who, change note, "Restored from v<n>" when
  set, the areas touched, and **requests pinned** (count of `da_requests.rulebook_version = n`, with
  the IDs on expand). The active one is marked.
- **What changed (D-L):** pick a version, see its diff against the one before (or any two). Plain code:
  both rulebooks are flattened to `path -> value` (`policy.build_max_rounds`, `rules[CV-PY-003].why`,
  keyed by ID or name, never by list position, so a reorder of rules does not look like a rewrite).
  Three lists: added, removed, changed (old and new). A changed text over 200 characters shows a
  `difflib` line diff. No AI.
- **Restore:** a button on every non-active version; a dialog with the change note pre-filled
  "Restored from v<n>" (editable); calls `restore_version`. Refusals from Phase 1 (already active,
  unchanged, problems under today's rules) are shown as they come.
- Each area tab's "last changed" (section 4) comes from this diff: the newest version whose diff has a
  path under that area.

## 11. Repository and index (D-D)

Read-only block "Server settings (from `.env`, changed by the CodeVision team)": `DA_SEARCH_PROVIDER`,
`DA_SEARCH_TOP_K`, `DA_DISCOVERY_MAX_ROUNDS`, `DA_MAIN_SOURCE`, `DA_SANDBOX_SOURCE_DIR` (shown as set or
not set, never the key values). Editable block: `allowed_folders`, `new_file_name_pattern` (the model
already refuses a pattern that does not compile), `workspace_markers`, `workspace_max_file_kb`. No
index is rebuilt from here (P15 is a work item).

## 12. Health numbers (plain code, `agents/da_admin_metrics.py`)

Every number is a query over tables that exist today. Window = **Last 30 days** (by the row's own
time) or **All time**. A number with no rows shows "No data yet", never 0 dressed as a result.

| Number | Definition | Tables |
|---|---|---|
| Requests | count, split by kind: new, enhance, fix (Phase 9 D-M) | `da_requests`, `da_enhance_state.kind` |
| First-round pass rate | closed builds whose round 1 passed Layers A and B, over all closed builds | `da_build_runs` (`ended_at` set), `da_build_rounds` round 1 |
| Average fix rounds | mean of `rounds_used - 1` over closed builds | `da_build_runs` |
| Requirement revisions per request | mean of (highest record version - 1) over requests with a record | `da_request_records` |
| Files edited by developers | distinct (request, path) with a `scanned` row; and the share of requests with at least one | `da_workspace_files` |
| Escalations (D-M) | **Get help** count (requests that entered `ESCALATION_REQUIRED`, from the audit status moves), labelled "Get help only; the other four triggers come with Phase 10" | `da_audit_events` |
| Handoffs | "No data yet (comes with Phase 10)" | none |
| Tester findings by type | kept findings grouped by check (1 to 7, the Phase 7 check names) and by severity; "Unable to assess" reviews counted separately | `da_tester_findings`, `da_tester_reviews` |
| Rules cited | top 5 rule IDs by kept findings citing them (the same count as section 7) | `da_tester_findings.cites` |

The builder confirms each column's exact values in the plan (for example which `result_status` means a
pass); the spec fixes the meaning, not the SQL. All counts are per server (one shared database, WF-1).

## 13. Storage

No new table for the rulebook. Changed:

| What | Change |
|---|---|
| `Policy` | optional retired fields (section 9); `escalation_triggers` five names with the load mapping; new `generator_model`, `tester_model` (str, default ""), `sonar_severity_map` (dict, defaults), `admin_unassigned_stale_days` (int, default 14, 1 to 365) |
| `Capability` | `backup_senior: str = ""` |
| `Rulebook` | `golden_examples: list[GoldenExample] = []` |
| `data/da_rulebook_seed.json` | retired fields dropped; five triggers; the new fields with their defaults; one made-up golden example |
| `data/da_sonar_checks_sample.json` | new, made up, read only |
| `tests/data/da_rulebook_seed_phase1.json` | the old-shape seed, for the load test |

Admin actions are recorded where they already are: a save or restore is a version row (who, when,
note, restored from); a queue action is the row's `resolved_by` and `resolved_at`. No new audit table
(the audit trail is per request, and these actions belong to no request). D-C.

Settings (`configs/da_config.py`, `.env.example`): `DA_ADMIN_SOURCE` (`env` default, or `codevision`
placeholder), `DA_ADMIN_IDS` (home only). No new library.

## 14. Testing without work

- **pytest, plain rules:** an old-shape version loads (section 9, step 4); the trigger mapping; saves
  from each tab build the right `Rulebook` (a form-to-rulebook function per tab, tested without Dash);
  every refusal is shown as the whole list; stale save shows the newer version; Cancel leaves the
  active version untouched; `next_rule_id` is used on Add row and never reused after Cancel; the diff
  keys by ID (a reorder of rules gives an empty diff); restore of an old-shape version saves five
  triggers; pinned counts; area status and Needs attention on a made-up database; every health number
  on a made-up database with known rows, and "No data yet" on an empty one; the Unassigned Confirm and
  Move paths and the pattern offer; `is_admin` with the `env` list and the placeholder; models per role
  read from the pinned version with the `.env` fallback; `sonar_severity_map` refuses a missing key;
  a name in both approved and blocked lists is refused.
- **Dash:** the layout of each tab builds from the seed without error (as the Phase 5 to 9 panel
  tests); the console never imports from the developer page's callbacks.
- **Smoke check:** after the Phase 1 items: v2 saved from the Build and test form (one limit changed),
  v3 restored from v1 through the console's function, the diff v1 to v2 lists one changed path, the
  health numbers block runs on the smoke database.
- **Playwright (cloud session only):** open `/admin` as an Admin, edit the charter, save with a note,
  see v<n+1> in Version history; open `/admin` as a non-Admin, see the refusal line.
- **Home check by Gian:** `DA_ADMIN_IDS=dev-home-01` in `.env`, open `http://127.0.0.1:8050/admin`,
  change the max fix rounds, save, restore, then start a new request and see it pinned to the new
  version while an older request keeps its own.
- **Work test** (`docs/admin-work-test.md`, new, Command Prompt only): the steps for section 18.

## 15. Out of scope

- The Escalations inbox, auto-escalation, Handoff, the PR summary, senior actions (Phase 10). Phase 11
  saves what they will read.
- Maker-checker, approval flows, pre-publish testing of a rulebook (decision 3).
- Sending golden examples or the SonarQube map to any AI call, and reading SonarQube itself (WF-4).
- Rebuilding or configuring the code index (P15), any Bitbucket adapter (Phase 9 WF-1).
- Any change to the developer page, except that the LLM client reads the model per role from the
  pinned version (section 8).
- Brand constants or a styles editor: the brand team owns styles (decision 4); UI standards are the
  `ui_convention` rules only.
- A login screen or user directory. Who is Admin is WF-2; the switch is built, the source is not.
- Email or Teams notifications (decision 19).
- Leftovers P26, P27, P28, P31, #56, #57 (facts).
- Metrics beyond section 12 (no charts over time, no per-developer tables: a per-developer table could
  read like staff appraisal, which was never asked for).

## 16. Done when (every line becomes a test, Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| 11-1 | `DA_ADMIN_SOURCE=env`, `DA_ADMIN_IDS` holds the user | `/admin` is opened | the console with 8 tabs shows, Overview first |
| 11-2 | the user is not in the list, or `DA_ADMIN_SOURCE=codevision` | `/admin` is opened | "This page is for the CodeVision core team." and nothing else; a log line for the placeholder |
| 11-3 | any tab in read view | drawn | the header names the active version, who, when and the change note |
| 11-4 | Edit on a tab | pressed | the fields are a form; the other tabs are disabled |
| 11-5 | a form with a change | Save with an empty note | refused with the Phase 1 R2 message; nothing saved |
| 11-6 | a form with a change | Save with a note | a new version exists with that note and the Admin ID; the read view shows it and the "new requests use it" line |
| 11-7 | a form with two problems (11 judgement rules, a trigger missing) | Save | both problems listed above the form; nothing saved |
| 11-8 | an Edit started from v3 and someone saved v4 | Save | refused naming v4, with Reload v4; the form is kept until Reload |
| 11-9 | a form with no change | Save | the plain "No changes to save" line, no version |
| 11-10 | a form with a change | Cancel | the active version is unchanged; read view |
| 11-11 | the charter at 81% of the limit | Charter tab | the amber status and the percent |
| 11-12 | Coding standards, Add row | pressed then Cancel | the row's ID came from `next_rule_id`; the next Add row gets the following number |
| 11-13 | 10 judgement rules | Add row | refused on the screen with the cap message; the counter shows 10 of 10 |
| 11-14 | a library in Approved libraries and in Blocked imports | Save | refused naming it |
| 11-15 | the SonarQube map with `MAJOR` set to `fyi` | Save | saved; the sample list shows the sample `MAJOR` checks as `fyi`; the banner names WF-4 |
| 11-16 | a map missing `INFO` (test-built rulebook) | validated | refused naming the key |
| 11-17 | a golden example added | Save | it is in the new version; no AI prompt built in the tests contains it |
| 11-18 | Build and test | drawn | max fix rounds, test time limit, max files, the cap-twice trigger, model per role, five triggers, zones, protected files, Advanced limits collapsed |
| 11-19 | `build_max_rounds` typed as 9 | Save | refused with the 1 to 5 bound |
| 11-20 | a trigger set off | Save | the new version holds it off; Needs attention shows the information line |
| 11-21 | `tester_model` set to `made-up-model` and a new request | the Tester client is built | it uses `made-up-model`; an older request pinned before the save still uses the `.env` value |
| 11-22 | `generator_model` empty | the Generator client is built | the `.env` model is used |
| 11-23 | two zones with the same name | Save | refused naming it |
| 11-24 | a version saved with the Phase 1 shape (old seed) | loaded | it loads; the four retired fields are `None` or empty; five triggers, the two old names mapped, the three new ones on |
| 11-25 | 11-24 | restored | the new version holds five triggers and no retired field |
| 11-26 | the console | any tab | no retired field is shown or in any form |
| 11-27 | the seed file | loaded and published | no retired field; five triggers; the new fields hold their defaults |
| 11-28 | the catalog with a capability lacking a backup senior | Overview | Needs attention names it; the area is amber |
| 11-29 | an open Unassigned row | Capability catalog | the row shows path, pick, request, waiting since, and "Would match" from the active catalog |
| 11-30 | 11-29, no pattern matches | Confirm | the row is `confirmed` by the Admin ID; the dialog offered to add the path as a pattern; accepting it saves a new version with a note |
| 11-31 | 11-29 | Move to another capability | the row is `changed`; the request's record is untouched |
| 11-32 | an open row older than `admin_unassigned_stale_days` | Overview | the catalog area is red |
| 11-33 | versions v1 to v3 and two requests pinned to v1 | Version history | newest first; v1 shows "2 requests pinned" with their IDs on expand; the active one is marked |
| 11-34 | v2 differs from v1 in one limit and one rule's `why` | What changed v1 to v2 | exactly those two paths, with old and new values |
| 11-35 | v2 equals v1 with the rules reordered (test-built) | What changed | an empty diff |
| 11-36 | a changed text over 200 characters | What changed | a line diff |
| 11-37 | Restore on v1 | confirmed | v4 with "Restored from v1"; Restore on the active version is refused with the Phase 1 message |
| 11-38 | Repository and index | drawn | the `.env` settings read only (no key values), the four `Policy` fields editable |
| 11-39 | a made-up database with 4 closed builds, 2 passing in round 1 | Overview, All time | first-round pass rate 50%, average fix rounds as computed, revisions per request as computed, files edited by developers as computed |
| 11-40 | an empty database | Overview | every health number says "No data yet"; Handoffs says "No data yet (comes with Phase 10)" |
| 11-41 | one request that pressed Get help | Overview | Escalations 1, with the "Get help only" label |
| 11-42 | kept findings on checks 1, 4 and 6 with mixed severities | Overview | findings by type grouped by check name and by severity; the rule cited most is first in Rules cited |
| 11-43 | the Last 30 days window and rows older than 30 days | Overview | they are not counted; All time counts them |
| 11-44 | the console's modules | imported | nothing from `callbacks/screen_callbacks/da_developer_assistant_page_callbacks` is imported; nothing in `src/` outside the LLM client changed for the developer page |
| 11-45 | the whole console | any action | no SQL against `da_rulebook_versions` outside `db_tbl_da_rulebook.py`; no AI call |
| 11-46 | Playwright | charter edited and saved as an Admin; `/admin` as a non-Admin | the new version is in the timeline; the refusal line |

Plus: `pytest` 0 failures, `ruff check` 0 problems, smoke check passes, code reviewer 0 Must fix, and a
home check by Gian on `127.0.0.1:8050/admin`.

## 17. Decisions (D-x), for the chief's decision rule

None of D-A to D-M decides a work fact, and each can be undone later. Where a choice depends on a work
fact, the column says so; the work fact itself is in section 18 with no recommendation.

| # | Question | Options (ranked) | Recommendation | Rule |
|---|---|---|---|---|
| D-A | How is the build split? | 1. **11a:** page shell and access switch, Version history, Charter, Build and test (with zones and protected files), retiring the old fields and the five triggers. **11b:** Coding standards (rules, libraries, Sonar map, golden examples), UI standards, Capability catalog with the Unassigned queue. **11c:** Overview with metrics, Repository and index, smoke, docs. 2. Three parts in concept tab order (Overview first). 3. One branch | **1**: the facts suggest it; Version history first means every later tab's save can be seen and restored from day one; the model changes (retired fields, triggers) land before any tab that edits them. Option 2 builds metrics before there is anything to govern | To chief |
| D-B | Where does the console hang at home? | 1. `/admin` on the existing `dcc.Location`, a second menu entry in the home shell, its own layout and callbacks files. 2. A ninth tab on the developer page. 3. A separate Dash app on another port | **1**: CodeVision routes pages by path (Phase 2 Q6); the developer page stays untouched. Option 2 shows Admin controls to developers. Depends on WF-6 for the work menu | To chief |
| D-C | One edit pattern, and where Admin actions are recorded | 1. One Edit/Save/Cancel pattern for every tab, a form-to-rulebook function per tab; actions recorded only as version rows and queue rows. 2. Inline editing per field with autosave. 3. A new `da_admin_audit` table | **1**: one save = one version with one note (the concept), testable without Dash. Option 2 makes many versions with empty notes. Option 3 duplicates what the version row already holds | To chief |
| D-D | What is on Repository and index? | 1. The server's search and source settings read only, plus the four `Policy` folder and file fields editable. 2. Read only entirely. 3. Make the `.env` search settings rulebook fields | **1**: the folder fields are rules (what the AI may touch), the search provider is a server fact. Option 3 moves secrets-adjacent settings into a versioned table | To chief |
| D-E | Confirming an Unassigned file whose path matches no pattern | 1. Confirm closes the row and **offers** to add the path as a pattern (a normal save with a note). 2. Confirm silently adds the pattern. 3. Confirm never touches the catalog | **1**: without the pattern the next request on the same path queues again; the offer keeps the catalog change explicit and noted. Option 2 saves a version with no note (breaks R2) | To chief |
| D-F | Shape of the SonarQube severity map | 1. Five fixed keys (SonarQube severities) to our three severities; the check list read only and sample. 2. A map per check key. 3. Nothing until WF-4 | **1**: it is what "Admin only maps severities" says and it works whatever WF-4 answers. Option 2 needs the real check list first | To chief |
| D-G | Model per role: where it lives and which version is read | 1. Two `Policy` text fields, empty = `.env`; the client reads the request's **pinned** version. 2. The **active** version always. 3. Keep `.env` only, shown read only | **1**: redesign 6 says Admin setting; pinned keeps "one request, one version" (decision 2). Option 2 can switch a request's model mid-build. Option 3 ignores redesign 6. The names to set are WF-5 | To chief |
| D-H | Golden examples | 1. A new rulebook part, stored and editable, sent to no AI call yet. 2. Also added to the Generator prompt. 3. Dropped | **1**: the concept keeps them; sending them changes Phase 6 prompts and needs a work test (prompt size, WF-5 of Phase 9). Option 2 is one later fix | To chief |
| D-I | Where zones and protected files live | 1. Sections on Build and test (8 tabs stay). 2. A ninth tab. 3. On Coding standards | **1**: they are policy, as in Phase 1's policy area, and the facts keep 8 tabs | To chief |
| D-J | How the retired fields go | 1. Optional with `None`/empty defaults, checks removed, never shown, dropped on the next save; old versions load. 2. Keep and show read only as "retired". 3. Rewrite old versions | **1**: honest and R1-safe. Option 3 breaks append-only | To chief |
| D-K | Three old triggers to five new | 1. Map on load, add missing as on, demand five on save. 2. Accept either list. 3. Refuse old versions | **1**: one shape everywhere after load; restore works. Option 2 leaves Phase 10 reading two shapes | To chief |
| D-L | What changed (diff) | 1. Plain-code flattened paths keyed by ID or name, plus `difflib` for long text. 2. Raw JSON text diff. 3. An AI summary | **1**: a reorder is not a change; testable. Option 3 is an AI call for nothing | To chief |
| D-M | Escalations number before Phase 10 | 1. Count Get help now (real data), labelled "Get help only; the other four come with Phase 10"; Handoffs "No data yet". 2. "No data yet" for both. 3. Count status moves of every kind | **1**: Get help is real and already stored; the label keeps it honest (decision 17 forbids fake numbers, not real ones). Option 2 hides data Gian can already use | To chief |

**Chosen by chief, 6.1 (12 Nov 2026):** D-A, D-B, D-C, D-D, D-E, D-F, D-G, D-H, D-I, D-J, D-K, D-L and
D-M all take option 1 (the recommendation). Each can be undone later and none decides a work fact. D-B
and D-G only fix the home behaviour; their work-side halves are WF-6 and WF-5 (issues opened).

"To chief": the chief writes "Chosen by chief, 6.1" (recommended option) or opens an issue, per
section 6 of the automation spec. D-B and D-G depend on work facts; if the chief reads that as touching
a work fact, he opens the issue instead.

## 18. Work facts (no recommendation, Gian decides)

The chief opens one issue per row with the label shown and builds everything around it.

| # | Question | Options (not ranked) | What Phase 11 builds meanwhile | Label |
|---|---|---|---|---|
| WF-1 (Q2, carried) | One shared database on the OCP server for all developers, so an Admin save reaches every developer's new request (CodeVision internals) | a. One SQLite file on the server. b. CodeVision's own database with the same tables. c. Other | Against the existing store. What changes when answered: the SQLite-only append-only triggers need their equivalent; R4 stale-save already handles two Admins saving at once; nothing in the console changes | `needs-gian` |
| WF-2 (Q5, carried) | Who counts as Admin and how the screen knows the core team (bank policy, CodeVision login) | a. A list of user IDs in `.env` or a config file. b. A CodeVision role or group from its login. c. A table in the database. d. No check: the bank's entitlement on the URL | `is_admin()` with `DA_ADMIN_SOURCE=env` (home list) and a `codevision` placeholder that refuses | `needs-gian` |
| WF-3 (#39, Phase 9 WF-2, carried) | The real capability list, named seniors and backups (bank org data) | Unknown. Not guessed here | The made-up seed catalog with made-up backup labels; the edit screen | `needs-gian` |
| WF-4 | Can the server read SonarQube: API, an export file, or nothing (CodeVision internals, bank policy) | a. SonarQube web API with a token. b. An exported file loaded by Admin. c. Nothing: the map stays a note for reviewers | The five-key map, editable; the sample check list, read only, with a banner | `needs-gian` |
| WF-5 (Q9, carried) | Which model name per role at work (`default`, `reasoning-vlm`, or empty), decided by the bake-off | a. Generator `reasoning-vlm`, Tester `default`. b. Both `reasoning-vlm`. c. Other | Two text fields, empty = `.env`; nothing hard-coded | `needs-work-test` |
| WF-6 (Q6, carried) | How the console is reached inside CodeVision at work: menu entry, path, who adds it (CodeVision internals) | a. A new side-menu entry under the Developer Assistant. b. A separate Admin menu. c. Other | The `/admin` path and the home shell's menu entry | `needs-gian` |
| WF-7 (Phase 9 WF-4, carried) | How Admin is told about a new Unassigned file (email, Teams, in-app only) | a. In-app queue only. b. Also a message. c. Other | The queue on the catalog tab and the Needs attention line. No message is sent (decision 19) | `needs-gian` |
| WF-8 | Does the work laptop's browser (Chrome or Edge, DevTools blocked) show Dash Mantine tables, modals and tabs as at home? | Unknown until the work test | Nothing special: the same components the developer page already uses at work | `needs-work-test` |

## 19. Open items

- **`max_review_rounds` is retired with the levels** (section 9): nothing reads it after the redesign
  (the Build limit is `build_max_rounds`, the Refine cap is `refine_max_per_request`). If Gian wants a
  "review rounds" limit for Phase 10's "Review my code", Phase 10 adds its own named field.
- **Brand constants and UI standards:** the concept's UI standards tab is "unchanged", but the rulebook
  holds only `ui_convention` rules; no brand constants were ever built (Phase 1 out of scope). If the
  concept tab showed colours or fonts, that is a later phase; Phase 11 shows the rules.
- **Trigger names and Phase 10:** Phase 10 reads `Policy.escalation_triggers` by the five names in
  section 9. The Phase 10 spec must use the same names.
- **Admin ID in `saved_by`:** at home the Admin ID is `DA_DEVELOPER_ID` (one person is both). At work
  it is CodeVision's logged-in user (WF-2).
- **Health number definitions** (section 12) are a first cut; the builder confirms the column values in
  the plan. Any number whose definition turns out wrong at the work test is a one-line SQL fix.
- **Phase 9 `list_unassigned` and `resolve_unassigned`** are reused as they are. If the plan finds the
  resolve function needs a "moved to" capability stored, add a nullable column (Phase 9 section 14 rule).
- No photos needed for this spec. WF-1, WF-4 and WF-6 are questions for the CodeVision team, not photos.

## 20. Files the builder will touch (for planning, not a limit)

`pydantic_classes/da_rulebook_models.py` (retired fields, five triggers with the load mapping,
`backup_senior`, `generator_model`, `tester_model`, `sonar_severity_map`, `admin_unassigned_stale_days`,
`GoldenExample`, new problem checks), `data/da_rulebook_seed.json`, `data/da_sonar_checks_sample.json`
(new), `tests/data/da_rulebook_seed_phase1.json` (new), `agents/da_admin_access.py` (new),
`agents/da_admin_forms.py` (new: form to rulebook per tab, the refusal lists), `agents/da_admin_diff.py`
(new: what changed), `agents/da_admin_metrics.py` (new: health numbers, area status, Needs attention),
`agents/da_llm_client.py` (model per role from the pinned version), `db_table_functions/db_tbl_da_requests.py`
(pinned counts per version), `layouts/da_admin_page.py` (new), `callbacks/screen_callbacks/da_admin_page_callbacks.py`
(new), `web/da_web_components.py` (shared pieces only if needed), `web/da_home_web_server.py` (menu entry
and `/admin`), `configs/da_config.py`, `.env.example`, `da_smoke_check.py`, `README.md`, `CLAUDE.md`
("Current phase"), `docs/admin-work-test.md` (new, Command Prompt only), and the matching tests.
