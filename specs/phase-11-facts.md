# Phase 11 facts (from Gian, project chat, 12 Nov 2026)

Facts for the Phase 11 spec writer. Phase 11 = Admin console and health metrics.
Source of truth for scope: `specs/redesign-2026-10-31.md` section 7 (AD1) and the Admin rows in
section 8. Format to copy: `specs/phase-9-enhance.md`. Facts marked **work fact** are Gian's to
decide: give options, no recommendation, and the chief opens a `needs-work-test` issue.

## Order change (Gian, 12 Nov)
- **Phase 10 is ON HOLD. Phase 11 is built first.** Phase 10 (Review my code, Handoff,
  Escalations inbox) comes after Phase 11 merges.
- So Admin must not depend on Phase 10 code. Rule: **Admin saves the settings; Phase 10 will read
  them later.** Example: the 5 escalation triggers and flag-for-review zones are edited and saved in
  Admin now; Phase 10 acts on them. Metrics that need Phase 10 data (escalations, handoffs) show a
  plain "No data yet (comes with Phase 10)" state, never a fake number.
- Why Admin matters (Gian): it is how code generation is governed. AS400 comparison: Phase 1 built
  the data areas and files (the rulebook); every phase since reads them. Phase 11 builds the
  maintenance screens (like a WRK/CHG menu) so the core team changes the rules without editing JSON.

## What is already built (on `auto/phases-7-10`)
- Phase 1 rulebook core: versioned storage, every save = new version, pinning of requests to a
  version, restore copies an old version into a new one (`db_table_functions/db_tbl_da_rulebook.py`,
  `pydantic_classes/da_rulebook_models.py`). Reuse it. Do not build a second store.
- `Policy` already holds most Admin settings: review rounds, escalation triggers (3 old names),
  flag-review zones, protected files, approved libraries, allowed folders, max files, build rounds,
  test time limit, Tester limits, Refine and Enhance limits, and the capability catalog (Phase 9).
- Old fields still in `Policy` from before the redesign: `default_level`, `max_level`,
  `never_generate_zones`. The redesign removed L0 to L3 and never-generate zones. The spec decides
  how to retire them without breaking older saved versions (they must still load).
- Phase 9 left `list_unassigned()` (read-only) for the Admin Unassigned queue (Phase 9 spec, WF-4).
- Model per role (Generator, Tester) exists as settings since Phase 4/7. Redesign 6: the model
  per role is an Admin setting.
- `cv_styles.py` is CodeVision's styles module. The Developer Assistant screens use `src/styles`.

## Screen reference
Gian's Admin concept demo (25 Oct, before the redesign) has 8 tabs: Overview, Project charter,
Repository and index, Capability catalog, UI standards, Coding standards, Generation and review,
Version history. Each tab: read view, an Edit button, one save = one new version with a required
change note, Cancel discards. Overview: rulebook areas with status, a "Needs attention" list, and
health numbers. Version history: timeline, what changed (diff), requests pinned to a version,
Restore. The demo file is NOT in the repo because it has real names; this section replaces it.

Apply redesign section 7 to that concept:
| Concept tab | Change |
|---|---|
| Generation and review | Becomes **Build and test**: max fix rounds (3), test time limit (60 s), max files per request (5), auto-escalation (cap hit twice in a row), model per role. No L0 to L3, no "AI code kept %" |
| Never-generate zones | Become **Flag-for-review zones**: description and examples per zone; effect = senior is a required PR reviewer (the PR part is Phase 10) |
| (new) | **Protected files**: files the AI may never write; needing one is flagged in Approach |
| Coding standards | Add **Approved libraries** (Layer A checks imports against it). Judgement rules, SonarQube severity map, golden examples stay |
| Capability catalog | Add the **Unassigned queue** (confirm the developer's pick, or move it) |
| Escalation triggers | Fixed list of **5**, on/off only: cap hit twice in a row, out of scope, dispute, Tester unable twice, Get help |
| Overview metrics | Remove "AI code kept %". Add first-round pass rate, average fix rounds, requirement revisions per request, files edited by developers, escalations, Tester findings by type |
| Charter, UI standards, version history | Unchanged |

## Decisions Gian already made (Admin concept, Oct 2026)
- Admin role = the CodeVision core team. UOB brand team owns official styles; Admin mirrors them.
- No maker-checker and no pre-publish testing for now. Saves apply to NEW requests only; requests
  in progress keep their pinned version.
- Rules live in the database with version history and one-click restore. Rules are tagged by Admin
  and shown to developers.
- Judgement rules capped at 10 for the pilot. Rule IDs are generated and never reused.
- SonarQube checks are governed in SonarQube; Admin only maps severities (read-only list).
- Escalations go to a named senior per capability, with a backup. The inbox is Phase 10.
- Developer-facing wording: "negative scenario" (asterisk and legend), never "failure".

## Open items (work facts and unknowns)
- **Q2, work fact:** one shared database on the OCP server for all developers. Admin edits must
  reach every developer's requests. Build against the existing rulebook store; say what changes
  when Q2 is answered.
- **Q5, work fact:** user IDs. Who counts as Admin (how the screen knows the core team). Give
  options (e.g. a list in `.env` or config) without a recommendation.
- **#39 (Phase 9 WF-2), work fact:** real capability list and named seniors. Use made-up examples.
- **Work fact:** can the server read SonarQube (API, export file, or nothing)? Until known, the
  severity map is editable and the check list is a made-up sample.
- Notification channel for escalations (email or Teams) is pending bank approval: out of scope.

## Size
8 screens is large. The spec should split the build into ordered parts the builder can finish
and push one at a time (for example 11a: version history, charter, Build and test, zones,
protected files, approved libraries; 11b: catalog with Unassigned queue, coding and UI standards;
11c: Overview and metrics). The spec writer decides the split and ranks it as a D-x.

## Rules that still apply
- Clean room: no real UOB names, people, programs or addresses. Made-up names only.
- Dash Mantine Components, the folder layout in CLAUDE.md, new files start with `da_`.
- Tests never call a real AI. Work laptop: Chrome and Edge only, PowerShell and DevTools blocked.
- Leftovers, not Phase 11 scope: P26, P27, P28, P31, #56, #57.

## House style for the spec
Plain language, AS400 comparisons (never mainframe), short sections, ranked D-x options with one
recommendation each, Given/When/Then criteria, no em dashes.
