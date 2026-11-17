# Phase 11 fix 2: Capability catalog by meaning, AI program tagging, SonarQube refresh

Version 1.0 APPROVED, 16 Nov 2026 (23:20 SGT). Gian, after his visual review of fix 1: "Go ahead with
your recommendations. I don't want anything stopping tonight, so please do your best while being
careful. I am giving you full authority." Every D-x below is option 1 (the recommended one).

Branch `phase-11-fix-2`, cut from the newest `phase-11-fix-1` (fix 1 is not merged yet: it waits for
Gian's sign-off, #83). PR into `auto/phases-7-10`; it is merged only after PR #77, and only by the
chief after Gian approves. **Do not change `phase-11-fix-1`.** Build it the normal way: plan, plan
review, small steps with tests, code review (max 3 rounds), pytest, ruff, smoke check, screenshots.

## 0. Why this fix exists (Gian, 16 Nov 23:14)

1. **Capability catalog.** "If I search for MARKDOWN, it'll list down all modules that can create
   markdowns." Today the search only matches text in names and paths, and a program belongs to a
   capability only when an Admin-typed path pattern matches it. On 25 Oct we agreed **"AI proposes,
   Admin approves"** for the program-to-capability mapping; fix 1 built plain code only (its spec
   forbade new AI calls). Gian also wants to **scan all of today's CodeVision programs** once and park
   each in a capability.
2. **Coding standards.** "How do we fetch the ruling in SonarQube? Is it possible?" Today the
   SonarQube list is a made-up sample. SonarQube's Web API can list a quality profile's active rules
   (`api/qualityprofiles/search`, then `api/rules/search?activation=true&qprofile=<key>`, paged,
   token login). Whether the OCP server may reach SonarQube is work fact WF-4 (#61).

Out of this fix: the Overview layout (done in fix 1, section 15), AI drafting judgement rules from
PR comments (stays parked), reading Bitbucket.

## 1. Decisions

| # | Question | Decision |
|---|---|---|
| D-A | How does "search by meaning" work? | **1: over the existing code index, no AI writing.** The catalog search box gets a second mode, **What the code does**. It runs the same safe search Discover uses (`search_safely`, B1's index at work, the fake index at home) and groups the hits by module. 2: AI reads every file per search (slow, costly) |
| D-B | Who proposes a capability for a program? | **1: the AI (a new `tagger` role), Admin approves.** The 25 Oct agreement. 2: plain code only (today, weak) |
| D-C | Which model is the tagger? | **1: a new role `tagger` in Model per role, default "uses the server default"**, like the other roles. 2: reuse the `tester` model |
| D-D | Where do summaries and proposals live? | **1: a JSON file next to the index**, `da_module_tags.json` (Git ignores the folder already). No new database table. The request-based Unassigned rows stay in the database as today. 2: a new table |
| D-E | When does tagging run? | **1: Admin clicks "Scan all programs"** (first time, all modules), and after every **Rebuild index** the screen offers **"Tag new or changed programs"** (only modules whose file hash changed). Nothing runs by itself. 2: automatically after every rebuild |
| D-F | How are proposals approved? | **1: per card (Approve, Assign to, Reject as today), plus "Approve all high-confidence"**, which saves **one** new rulebook version with exact-path patterns and a change note listing the count |
| D-G | SonarQube | **1: a read-only "Refresh from SonarQube" button** behind settings that are empty by default. Empty settings: the sample list stays with "Not connected yet (#61)". The severity map stays Admin's (unchanged). 2: wait for #61 |

## 2. Search by meaning (D-A)

- Catalog search box: a `SegmentedControl` **Names and people** (today's search, unchanged) and
  **What the code does** (new). Placeholder for the new mode: "Describe what the code does, for
  example: creates markdown".
- New plain function `modules_by_meaning(query, settings, top_k=30) -> list[ModuleHit]` in
  `agents/da_admin_meaning.py`: calls `search_safely` with the query, groups hits by `path`, keeps the
  best score per module, and returns up to 15 modules, best first. Each `ModuleHit`: path, the matched
  symbols (max 3), the module's capability (from the active catalog patterns, or "Unassigned"), and
  its one-line AI summary when `da_module_tags.json` has one.
- The tagger summaries are searched too: a module whose summary contains the query words (the same
  stemming and synonyms as `da_search_index._query_words`) is added with a "from summary" label.
- The results show as a list under the search box: module chip, capability pill, summary in plain
  words, matched symbols as small code chips. Clicking a module filters the table to its capability.
- No index built: one line, "The code index needs building. Open Repository and index." No error.
- The whole search runs in plain code plus the embedder. **No LLM call.**

## 3. AI program tagging (D-B to D-F)

### 3.1 What the tagger gets and returns

- One call per **module** (distinct `path` in B1's piece list), never per function.
- Prompt file `src/data/da_tagger_prompt.md`: the module path, its first 200 lines (cut, never more;
  a line count note when cut), and the **active capability list** (name and description only, never
  seniors). It asks for JSON only:
  `{"summary": "<one plain line, max 120 characters>", "capability": "<exact name from the list or none>",
  "confidence": "high|medium|low", "reason": "<max 160 characters>"}`.
- Plain code checks the reply: valid JSON, summary 1 to 120 characters, capability exactly one of the
  names or `none`, confidence one of three. Anything else: that module is **skipped** (B1's rule), the
  reply text is never logged or stored.
- Never sent: `da_` files (B1 never indexes them), secret-looking paths (`looks_secret`), excluded
  paths. Never logged: the code, the prompt, the reply.

### 3.2 The store

`da_module_tags.json` next to the index, one entry per module:
`path, file_hash (sha256 of the file text), summary, proposed_capability, confidence, reason,
model, tagged_at, state (proposed | approved | rejected | matched)`.
- `matched`: the module already matches a capability pattern; the summary is kept, no card is shown.
- Saved together or not at all, like B1: over 10% of the modules in one run skipped means "Not saved:
  over 10% failed, the old tags stay".
- A run log in the same file (last 10 runs: who, when, scanned, proposed, skipped).

### 3.3 Runs

- **Scan all programs** (catalog header, Admin, edit mode not needed): confirm box "Asks the AI to
  read every program once and propose a capability. About N programs. Runs in the background; you
  can leave the page." Background job with a lock file, one at a time, the same pattern as Rebuild
  index (`agents/da_admin_rebuild.py`). The page polls; the button shows "Scanning… 120 of 340".
- **Tag new or changed programs**: shown after a Rebuild index finishes (and on the catalog header
  when the index is newer than the last tag run). Only modules with no entry or a changed hash.
- At home: `FakeLLMClient` with a script `src/data/da_tagger_fake_script.json` covering the made-up
  CodeVision folder (one reply per module, including one `none` and one bad reply for the skip test).
- At work: `get_llm_client("tagger", settings, admin_model)`. A program limit per run,
  `DA_TAGGER_MAX_MODULES` (default 500), protects the on-prem model; the rest waits for the next run
  and the screen says so.

### 3.4 Showing and approving

- **Unassigned queue** (right panel): cards come from two sources, labelled **From a request** (today)
  and **From the AI scan** (new). An AI card: `path` → proposed capability (or "No capability fits"),
  confidence pill, the summary, the reason, buttons Approve, Assign to, Reject (New capability as
  today). Approve and Assign to add an **exact-path pattern** and save a new rulebook version with a
  change note "AI scan: <path> to <capability>" (the existing `_add_pattern` path); Reject marks the
  entry `rejected` (no rulebook change).
- **Approve all high-confidence** (queue header, shown when there are any): one confirm box listing
  the count per capability, then **one** new version, note "AI scan: N programs approved
  (high confidence)".
- Capability table: under each module chip, its summary as a tooltip.
- Overview **Needs attention**: "N AI proposals to review" with a Review button to the catalog.

### 3.5 Model per role

Build and test, **Model per role**: a fourth row **Program tagger** (`tagger`), default "uses the
server default". `Role` in `da_llm_client.py` gains `"tagger"`. Every place that lists roles is
checked (labels table, metrics, the Overview "For your information" lines).

## 4. SonarQube refresh (D-G)

- Settings (`.env`, all empty by default, plain labels in Server settings): `DA_SONAR_URL`,
  `DA_SONAR_TOKEN` (never shown, never logged), `DA_SONAR_PROFILE` (the quality profile name; empty
  means the default Python profile), `DA_SONAR_LANGUAGE` (default `py`).
- `agents/da_sonar_client.py`, `requests` only (already pinned), GET only:
  1. `GET {url}/api/qualityprofiles/search?language={language}` → the profile key (by name, else the
     one with `isDefault`).
  2. `GET {url}/api/rules/search?activation=true&qprofile={key}&f=name,severity,actives&ps=500&p={n}`
     until all pages are read (stop at 20 pages).
  Token login as SonarQube expects it (the token as the user name, empty password). 15 s timeout per
  call. Any error: a plain message ("SonarQube did not answer", "The token was refused", "Profile not
  found"), and the old list stays.
- Snapshot `src/data/da_sonar_rules.json` is **not** used for real data; the real snapshot goes next to
  the index folder as `da_sonar_rules.json` (Git ignores it): key, name, severity, fetched_at, profile.
- Coding standards, Automatic checks panel: when a snapshot exists it replaces the sample list, the
  "Sample list" pill becomes "From SonarQube, <date>", and a **Refresh from SonarQube** button shows.
  Empty settings: the sample stays, the button is disabled with "Not connected yet (#61)".
- Tests use a fake session object (no network, ever). One test proves the token never reaches a log.

## 5. Acceptance criteria (Given / When / Then)

| ID | Given / When / Then |
|---|---|
| AG-1 | Given the made-up folder with two new made-up modules, `src/agents/docs_markdown_export.py` (writes a Markdown file; no "markdown" in any function name) and `src/agents/docs_folder_to_md.py`, and the fake index rebuilt, when "What the code does" searches "creates markdown", then both are listed in the top 3 with their capability pill (or Unassigned), and no LLM is called. The fake embedder must make this work by meaning words, not file names: if it cannot, the plan says so and the test uses the summary match from section 2 instead |
| AG-2 | Given no index files, when a meaning search runs, then one plain line says the index needs building and nothing fails |
| AG-3 | Given "Names and people" mode, when searching, then the results are the same as before this fix |
| AG-4 | Given the fake tagger script, when Scan all programs runs, then every module gets a summary; modules already matching a pattern are `matched`; the others become AI cards in the queue |
| AG-5 | Given 1 bad reply in 20 modules, then that module is skipped and named in the run log; given 3 bad of 20, then "Not saved" and the old tags stay |
| AG-6 | Given an AI card, when Approve is clicked, then a new rulebook version holds the exact-path pattern and the module shows under its capability |
| AG-7 | Given 4 high-confidence proposals, when Approve all high-confidence is confirmed, then exactly one new version is saved with all 4 patterns and the count in the note |
| AG-8 | Given a scan is running, when a second scan or a Rebuild index is clicked, then it is refused with "one job at a time" |
| AG-9 | Given a module whose file hash did not change, when Tag new or changed programs runs, then it is not sent to the AI again |
| AG-10 | Given the tagger prompt, then it holds no `da_` file, no secret-looking path, at most 200 code lines, and never a senior's name |
| AG-11 | Given empty SonarQube settings, then the sample list shows with "Not connected yet (#61)" and the refresh button is disabled |
| AG-12 | Given a fake SonarQube with 2 pages of active rules, when Refresh runs, then all rules are saved with their severities and the panel shows "From SonarQube, <date>" |
| AG-13 | Given the fake SonarQube refuses the token, then the message says the token was refused, the old list stays, and the token text is in no log line |
| AG-14 | Given Build and test, then Model per role shows a Program tagger row; saving a model for it is used by the next scan |
| AG-15 | Given any new screen part, then the AF-2 label scan still passes (no `DA_` and no raw field names) |
| AG-16 | Screenshots: the catalog in both search modes, the queue with AI cards, and Coding standards with the SonarQube panel are added to the screenshot script |

## 6. Edge rules

- Fix 1 behaviour stays: every fix 1 test keeps passing, or the plan lists each changed test and why.
- No AI writes a rulebook version: only Admin's click saves one.
- Made-up names and code only at home. `--fake` and `FakeLLMClient` never at work (B1's rule).
- The tagger never runs during a request; it is an Admin job only.
- Keep layouts in `layouts/` (a new `da_admin_catalog_meaning.py` if `da_admin_catalog_tab.py` grows
  past 400 lines), logic in `agents/`.

## 7. Work facts (new, `needs-work-test`, they do not stop the build)

- WF-9: about how many Python programs CodeVision has, and how long one tagger call takes on Qwen.
- WF-10: may the tagger run on the on-prem model at night without hurting daytime users?
- WF-4 (#61) still decides SonarQube: URL reachable from OCP, a read-only token, the profile name.
