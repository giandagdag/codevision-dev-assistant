# Phase 11 fix 1: Admin console redesign (match the agreed design)

Version 1.1 APPROVED, 15 Nov 2026 (11:41 SGT). Gian: "Yes go ahead. Do your recommendations. Ensure that it
doesn't mess up with our Phase 10 progress." All D-x below are option 1 (the recommended one).

Branch `phase-11-fix-1` (from `auto/phases-7-10`). PR into `auto/phases-7-10`; the chief merges it.
Build it the normal way: plan, plan review, build in small steps with tests, code review (max 3
rounds), pytest, ruff, smoke check.

**When (Gian, 15 Nov, D-D option 1): after Phase 10.** Checked 15 Nov 11:50: Phase 10 and fix batch
B1 are both merged into `auto/phases-7-10` (B1 = PR #75, `b05914a`), no PR is open, so this fix may
start next. **Do not touch `auto/phase-10` or `auto/phase-b1-fixes`.** This branch holds only this
spec and `docs/admin-reference/`; no code, no CLAUDE.md change. First build step: merge the newest
`auto/phases-7-10` into `phase-11-fix-1`. The builder then sets CLAUDE.md "Current phase" as usual.

**Reuse B1, do not rebuild it.** B1 built the real CodeVision index (`agents/da_code_index.py`,
`src/da_build_code_index.py`, `build_index()`, `--fake` for home) and parked **P23, an Admin
"Rebuild index" button**. Section 7 is P23 plus the screen around it. B1's rules stay: saved
together or not at all, the 10% failure rule, `da_` files never indexed, text never logged.

## 0. Why this fix exists

Gian: "It seems to me I'm navigating through Excel tables." The built console is correct underneath
(versions, Save with a note, Restore, access switch, metrics), but it does not look or work like the
design agreed on 25 Oct and 14 Nov. Root causes, found in `specs/phase-11-admin-console.md`:

1. **No picture.** Line 13: "Visual reference: none in the repo." The 25 Oct demo had real names, so
   it stayed out, and the builder worked from a text summary only.
2. **Cut as later.** Bitbucket connection and indexing (section 15), colours and fonts (section 19),
   golden examples "stored only" (section 7).
3. **Raw names.** Repository and index shows `.env` names (`DA_SEARCH_TOP_K` and so on).

This fix closes all three. The two demos are now in the repo with made-up names (section 2).

## 1. Decisions

| # | Question | Decision |
|---|---|---|
| D-A | Which design is the base? | **DECIDED 1: merge.** The 14 Nov demo decides the **content and rules** (Build and test, 5 triggers, decision limit 8, Unassigned queue, health numbers). The 25 Oct concept decides the **look and the panels** (Bitbucket connection, index health, rule cards, golden examples, colour swatches, diff side panel). Where they disagree, the table in section 3 decides |
| D-B | Does Discover use the capability catalog? | **DECIDED 1: yes, it narrows the search** (section 6) |
| D-C | Bitbucket and indexing at home | **DECIDED 1: working, on B1's index.** Repo, branch and folder fields; Re-index really runs B1's `build_index()` (fake embedder at home, CodeVision's at work); index health and refresh history shown (section 7) |
| D-D | When | **DECIDED 1: after Phase 10 merges** |
| D-E | Golden examples into the Generator prompt? | **DECIDED 1: yes,** the one example matching the planned file's program type, cut to the first 80 lines. 2: stored only (today). Option 1 makes the agreed "Qwen imitates the golden example" true; the risk is prompt size (Q7, the context limit, is still open at work) |
| D-F | Decision limit for existing databases | **DECIDED 1:** the seed default becomes 8; an existing database is not changed, and Gian sets 8 in the console with a note (this also tests Edit and Save). 2: a one-time script writes a new version with 8 |

## 2. The visual reference (binding)

Copy these two files into `docs/admin-reference/` in the same commit as this spec. Real names, file
names and brand words are already replaced with made-up ones. They are not copied to work.

- `docs/admin-reference/admin-concept-2026-10-25.html` (the look)
- `docs/admin-reference/admin-demo-2026-11-14.html` (the content)

Open them in Chrome or Edge, and use Left and Right to move between tabs. **The builder must match the
layout, cards, colours, icons and spacing of the screen named in section 3, tab by tab.** "Match" means
the same panels in the same places with the same kinds of controls. It does not mean pixel-perfect,
and the made-up numbers do not have to match. Use Dash Mantine Components and DashIconify (already
installed). No new library. Emoji used as icons in the demos may stay as emoji.

Colours: take the demo palette (`--navy #1E2B45`, `--blue #1F6FE0`, `--green #157F3B`, `--amber
#9A5B00`, `--red #B42318`, `--violet #5B4BC4` and their light versions) into one constants block in
`src/styles/` (a new `da_admin_styles.py`). No colour code anywhere else.

## 3. Tab by tab

Every tab keeps today's working behaviour: read view, an **Edit** button, edit mode with a floating
bar ("Editing <tab>. Nothing changes for developers until you save." with Cancel and **Save as new
version**), Save asks for a change note, and a stale save names the newer version.

| Tab | Take from | What it must show |
|---|---|---|
| **Header (all tabs)** | 25 Oct | A version pill on the right: green dot, "Active rulebook vN", "Published <date>, <who>", button **View history** |
| **Overview** | 25 Oct layout, 14 Nov numbers | Left (2/3): **Rulebook** panel, one clickable row per area (icon tile, name, 2 to 3 fact chips, a status pill such as "✅ Up to date" or "⚠️ 2 to review", "Updated <date>"). Right (1/3): **Needs attention** rows, each with a Review or Open button that jumps to the right tab (and filter), then **Health numbers** as tiles with the Last 30 days and All time switch. Phase 10's Handoffs and Escalations numbers stay |
| **Project charter** | 25 Oct | Purpose box; Scope as two boxes side by side (✅ In scope, 🔴 Out of scope); Architecture principles and Constraints side by side; Glossary table. The charter size meter in the header (green under 80%, amber 80 to 100%, red over 100%) |
| **Repository and index** | 25 Oct | Section 7 |
| **Capability catalog** | 25 Oct look, 14 Nov queue | Search box ("Search capability, module, senior or backup") and a **Missing backup** filter chip. Table: Capability, **Modules** (chips, one per module path; a module in more than one capability shows "×2"), Senior and Backup (initials circle and name; "⚠️ Missing" pill), in edit mode a person picker. Right panel: **Unassigned queue** as cards: "`path` → suggested capability", why (section 6.3), buttons Approve, Assign to (picker), New capability, Reject |
| **UI standards** | 25 Oct | Left: **Brand constants** table: swatch (a real colour square; a striped square when the value is "Pending brand guide"), name, value, source (Bank brand guide or Core team). Rows for colours, `FONT_FAMILY` (an "Aa" tile drawn in that font), `FONT_BOLD`, `SPACING` (4, 8, 16, 24), and **`TABLE_PAGE_SIZE`** (20). Right: **UI conventions** as rule rows (`CV-UI-001`, text, severity pill) |
| **Coding standards** | 25 Oct | Section 5 |
| **Build and test** | 14 Nov content, 25 Oct look | Cards: **Limits** (max fix rounds 3, allowed 1 to 5, as a − 3 + stepper; test time limit; max files per request; **decision limit 8**, allowed 1 to 15), **Model per role**, **Escalation triggers** (5 switches plus "Lock the developer's chat", from Phase 10), **Flag-for-review zones** as zone cards (name pill, description, examples), **Protected files** as chips, **Tests** (the four fixed facts as a ✅ list, read only). A Severity table "Can hand off?" (Must fix: No; Should fix: Yes, listed in the PR summary; FYI: Yes) |
| **Version history** | 25 Oct | Left: a vertical **timeline** (green filled dot = active, newest first), each card: vN, tags Active or "Restored from vM", the change note, date and who. Right: a **side panel** for the selected version: "What changed in vN" as a coloured diff (green + lines, red − lines, blue area headings, plain words, never raw field names), **Requests pinned** as chips, and **Restore vN** (a confirm box: "vN+1 becomes active for new requests. Requests in progress keep their version. vActive stays in history.") |

## 4. Plain labels, never raw names

One label table (`LABELS` in `agents/da_admin_forms.py` or a new `da_admin_labels.py`) turns every
field name into plain words, used by forms, the diff and the Overview. Examples:

| Raw | Shown |
|---|---|
| `DA_SEARCH_PROVIDER` | Code search source |
| `DA_SEARCH_TOP_K` | Search results per query |
| `DA_DISCOVERY_MAX_ROUNDS` | Discover rounds per request |
| `DA_MAIN_SOURCE` | Where the current code comes from |
| `DA_SANDBOX_SOURCE_DIR` | Sandbox copy of CodeVision |
| `build_max_rounds` | Max fix rounds |
| `max_material_decisions` | Decision limit |

Rule: a test fails if any drawn Admin screen contains `DA_` or a field name with an underscore
outside a code chip (file paths and rule IDs in chips are fine).

## 5. Coding standards

1. **Judgement rules list** (left, 2/3): one row per rule: ID, text, tags, and "fires in N%" (share of
   Tester reviews in the last 30 days with at least one finding citing that rule ID; over 50% shows
   amber "⚠️"). The header shows "7 of 10".
2. **Rule card** (right, 1/3), for the selected row: severity pill, ID, title, then **Why**, **Tags**,
   **Checked by** (Independent Tester), **Source** (Written by Admin, or the seed), **Fires in**, then
   **✅ Good** and **❌ Bad** code snippets in green and red boxes. The data is already on `Rule`
   (`why`, `good_example`, `bad_example`).
3. **Golden examples** panel: one row per program type, **Screen**, **Batch or ingestion**,
   **Utility** (the agreed three), with an icon, the module path chip and a Change button (in edit
   mode, pick a module from the index). Add `program_type` to `GoldenExample` if it is missing (the
   default for old versions: the first tag, or "Utility"). Rule shown: "Each golden example must pass
   all judgement rules." It goes into the Generator prompt (D-E, section 9).
4. **Approved libraries** as chips; blocked imports as red chips.
5. **Automatic checks (SonarQube)** list with "Governed in SonarQube" pill, and the **severity map**
   table (SonarQube level → CodeVision severity pill; editable). The sample list stays marked
   "Sample list".

## 6. Capability catalog feeds Discover (D-B)

1. **Modules per capability.** A capability's modules are the indexed files (B1's piece list; at
   home with no built index, the files under the folder scope) matching its `path_patterns`. The table shows them as chips (max 6, then "+N more"). In edit mode, Add module
   picks a path from the index and adds it as an exact pattern.
2. **Discover narrows the search.** When Discover builds its searches, plain code first finds the
   capabilities that match the request (capability name, description or its modules named in the
   understood request; no AI). Each search runs twice: first filtered to that capability's modules,
   then over the whole index. Results from the matching capability are listed first, with a label
   "In capability: <name>". If no capability matches, the search is as today. The Discovery tab says
   which capability was used.
3. **Unassigned suggestions** (plain code, no AI): a new module's suggested capability is the one
   whose patterns or modules it imports from most (from the index), else none. The card says why
   ("Imports 3 modules from Limits" or "No matching capability found").
4. **Escalation routing is unchanged.**

## 7. Repository and index (D-C, on B1's real index, closes P23)

Layout as the 25 Oct concept: header pill "Index is fresh, built <time ago>" (amber when older than
a day or missing: "The CodeVision index needs building"), buttons **Rebuild index** and **Edit**.

Left column:
- **Connection**: Bitbucket repository, Branch indexed (`main`, locked 🔒), Folder scope. New
  rulebook fields: `index_repo` (shown only, the server reads a folder, not Bitbucket),
  `index_branch` (always `main`), `index_folder_scope`. `index_folder_scope` set = the source folder
  for the build; empty = B1's `DA_CODE_INDEX_SOURCE` or its default (today's behaviour). At home the
  seed sets it to the made-up CodeVision folder `src/data/da_fake_codevision`.
- **Refresh**: three option tiles, On every merge to main, Nightly, Manual (`index_refresh_mode`).
  Only Manual runs in this fix; the other two are saved and shown with "Not connected yet" (a new
  parked item: run the build on merge or nightly).
- **Exclusions** table: Pattern, Reason, Type (Config, Build, Scratch) (`index_exclusions`). They
  are skipped **in addition to** B1's own skips (`da_` files, `__pycache__`, secret-looking paths),
  which show as fixed rows with a 🔒 and "Always skipped".
- **Allowed folders**, **Workspace markers**, new file name pattern, workspace max file size: chips
  and fields (today's four `Policy` fields, unchanged).
- **Server settings** (read only, collapsed by default), plain labels from section 4, including
  B1's `DA_CODE_INDEX_DIR` and `DA_CODE_INDEX_MAX_DISTANCE`.

Right column:
- **Index health** tiles, read from B1's piece list (`da_code_index.json`): built at, modules
  indexed (distinct paths), pieces (functions and classes), source folder. "Not built yet" when the
  files are missing.
- **Recent refreshes** list (last 10): who or what started it, when, ✅ Done with the count, or
  "⚠️ N pieces skipped" (click: path and symbol, never the text), or "❌ Not saved: over 10% failed,
  the old index stays". Stored in a small `da_code_index_runs.json` next to the index (Git ignores
  the folder already).

**Rebuild index** asks to confirm ("Re-reads the folder scope and rebuilds the index. Takes a few
minutes. Discovery keeps using the old index until the new one is saved."), then calls B1's
`build_index()` in the background with the folder scope and the extra exclusions. At home it uses
`FakeEmbedder` (B1's `--fake` rule: never at work); at work `WorkEmbedder`. The button is disabled
while a build runs ("Rebuilding… started 14:02"); the page polls for the result. Saving a change to
the folder scope or the exclusions asks "Rebuild the index now?" (Later or Rebuild). One build at a
time on the server (a lock file); a second click says one is already running.

## 8. Shell fix

The side menu highlights the page you are on. Today `da_home_web_server.py` sets `active=True` on
Developer Assistant always. Fix: the active entry follows the URL (`/` Developer Assistant, `/admin`
Admin, the Inbox path Inbox). Check that CodeVision's own menu at work is not affected (home shell
only).

## 9. Seed and data changes

- `max_material_decisions`: allowed range 1 to 15 (today 1 to 10); seed default 8 (D-F).
- New fields with defaults so every old version still loads: `index_repo`, `index_branch`,
  `index_folder_scope`, `index_refresh_mode`, `index_exclusions`, brand constants (a list of name,
  value, source; seeded with the 25 Oct rows, made-up values), `program_type` on golden examples, a
  severity on UI conventions.
- The seed gets three made-up golden examples (one per program type) from the made-up CodeVision
  folder, each passing every judgement rule.
- **Generator prompt (D-E):** when a planned file is built, the golden example of its program type
  (Screen for `layouts/` and `callbacks/`, Batch or ingestion for `agents/` files with a run entry,
  else Utility; the plan may refine this plain-code mapping) is added once, cut to its first 80
  lines, under the heading "Follow this example's style". Not sent to the Tester or Understand.
- No new database table. The refresh history is the small JSON file in section 7.

## 10. Proof that it looks right

1. **Screenshots.** A Playwright script (skipped when no browser, like 7-35) opens each of the 8 tabs
   at 1366 by 768 in read view and in edit view, and saves PNGs to `logs/admin-screens/`. The
   code-reviewer opens each PNG next to the matching reference demo screen and lists every panel that
   is missing or in the wrong place. A missing panel is a Must fix.
2. **Gian signs off visually** at home before the PR is merged (same as other phases).

## 11. Acceptance criteria (Given / When / Then)

| ID | Given / When / Then |
|---|---|
| AF-1 | Given `/admin` is open, when the side menu is drawn, then Admin is highlighted and Developer Assistant is not; on `/`, the reverse |
| AF-2 | Given any Admin tab in read or edit view, when drawn, then no text contains `DA_` and no field name with an underscore shows outside a code chip |
| AF-3 | Given any tab, when drawn, then the header shows the active version pill with View history |
| AF-4 | Given the Overview, when drawn, then each of the 6 areas is a row with icon, fact chips and status pill, and clicking it opens that tab |
| AF-5 | Given a capability without a backup, when its Needs attention Assign is clicked, then the catalog opens filtered to Missing backup |
| AF-6 | Given Repository and index, when drawn, then Connection (repo, branch locked to main, folder scope), Refresh, Exclusions with reason and type (plus B1's fixed skips with 🔒), Index health from the piece list and Recent refreshes all show; with no index files the pill says the index needs building |
| AF-7 | Given an exclusion is added and saved, when Save finishes, then "Rebuild the index now?" is asked; Rebuild runs `build_index()` with the fake embedder, the new piece list has none of the excluded files, and a new Recent refreshes row shows ✅ Done with the count |
| AF-8 | Given the fake embedder fails for 1 of 20 pieces, when rebuilt from Admin, then the row shows "⚠️ 1 piece skipped" naming path and symbol; given 3 of 20 fail, the row shows "❌ Not saved" and the old index is unchanged; given a build is running, a second Rebuild click is refused |
| AF-9 | Given the catalog, when drawn, then each capability lists its module chips from the index; a module in two capabilities shows "×2"; the search filters by module name |
| AF-10 | Given a request about a made-up capability (for example "limits expiry report"), when Discover runs, then the first searches are filtered to the Limits modules, results are labelled "In capability: Limits", and the Discovery tab names the capability |
| AF-11 | Given a request that matches no capability, when Discover runs, then the searches and results are the same as today |
| AF-12b | Given Discover with provider `codevision` and a built index, when a capability matches, then the capability filter is applied after the vector search (B1's rule: filters after the search; an empty filter result falls back to the whole index, never to no results) |
| AF-12 | Given a new module that imports from Limits modules, when it reaches the Unassigned queue, then the card suggests Limits and says why; Approve saves a new version |
| AF-13 | Given UI standards, when drawn, then every brand colour shows a coloured swatch, a pending value shows a striped swatch, and FONT_FAMILY, FONT_BOLD, SPACING and TABLE_PAGE_SIZE rows show |
| AF-14 | Given Coding standards, when a rule row is clicked, then the rule card shows Why, Tags, Checked by, Source, Fires in, and the Good and Bad snippets |
| AF-15 | Given Tester findings citing CV-PY-007 in 6 of 10 reviews in 30 days, when the rule list is drawn, then CV-PY-007 shows "⚠️ fires in 60%" |
| AF-16 | Given Coding standards, when drawn, then Golden examples shows Screen, Batch or ingestion and Utility, each with a module chip |
| AF-17 | Given Build and test, when drawn, then the decision limit shows 8 on a new seed and accepts 1 to 15; max fix rounds shows 3 and accepts 1 to 5 |
| AF-18 | Given Version history, when an older version is selected, then the side panel shows a coloured diff in plain words, its pinned requests and Restore; Restore asks to confirm and creates a new active version |
| AF-19 | Given a rulebook version saved before this fix, when loaded, then every tab draws with the new fields at their defaults |
| AF-20 | Given the screenshot script, when run, then 16 PNGs (8 tabs, read and edit) are saved (skipped with no browser) |
| AF-21 | Given a Generator prompt is built for a planned Screen file, then it holds the Screen golden example, at most 80 lines, and no other golden example |

## 12. Edge rules

- Everything already working stays working: access switch, Save with a note, stale save, Restore,
  pinned versions, metrics, Phase 10's additions. Existing Phase 11 tests keep passing, or the plan
  lists each changed test and why.
- Plain code only for statuses, suggestions and the capability match. No AI call is added. The only
  prompt change is the golden example in the Generator prompt (D-E).
- Made-up names only. The reference demos, seed and tests use the made-up names from section 2.
- Keep functions short; layouts in `layouts/`, logic in `agents/`, styles in `styles/`.

## 13. Out of scope

- Reading Bitbucket itself (the server indexes a folder), automatic rebuild on merge or nightly
  (new parked item), reading SonarQube itself (WF-4), AI rule suggestions from
  PR comments or repeated findings (parked as P-new, "AI suggestions"), email or Teams messages to
  Admin (WF-7).
- The developer pages, except Discover's capability step (section 6.2) and the menu highlight.
- P31 (Windows-only sandbox test). Still open, still must be fixed before `main`.
