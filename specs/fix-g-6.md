# Fix G6: catalog from code links, a module in more than one capability, a readable capability map

Version 1.0 APPROVED, 21 Nov 2026 18:12 SGT. Gian: "Yes go ahead... Lets start the spec so we can
proceed with the build." Written in the project chat from `claude/work-test-2026-11-21-findings.md`
(W21-18, W21-20, W21-23). Every choice below is decided (recommended option); no D-x is open.

Branch `phase-g-fix-6`, cut from the newest `origin/auto/phases-7-10` **after Fix G5 is merged** (it
uses G5's forgiving reader, job watcher and progress bar). PR into `auto/phases-7-10`; the chief
merges it. Normal build: plan `specs/fix-g-6-plan.md`, plan review, small steps with tests, code
review (max 3 rounds), full pytest, ruff, smoke check, screenshots. Commit subjects "G6 step N".
Builder: this spec was put in the laptop folder untracked as `specs/fix-g-6.md`; commit it as the first commit on the branch.

## 0. What Gian found (21 Nov)

- With an empty catalog the AI suggested only 2 new capabilities, one program each, one of them wrong
  ("Payment Configuration"; CodeVision has no payments). 32 programs: "No capability fits".
- He wants one module in two capabilities (for example markdown creation and ingestion).
- The capability map (13 bubbles) is unreadable: every link drawn, Unassigned the biggest bubble,
  shared helpers (Config, Classes, Database, Tools) pull every line through the middle, labels on top
  of bubbles, one colour, "EmbeddingandVector" lost its spaces.

## 1. Code facts (read 21 Nov at 759153c)

- Tagger: one program per AI call (`da_admin_tagger.py`); prompt `data/da_tagger_prompt.md`.
- Code links graph: `da_code_impact_graph.py` (`with_catalog_tags`), saved with the index.
- Clusters: `da_code_clusters.py`, label propagation, 20 rounds, fixed order; suggestions only when at
  least 3 linked modules are already tagged (`MIN_TAGGED = 3`), so nothing on an empty catalog.
- Ownership: `da_admin_meaning.py::capability_of` = first match wins; `da_admin_modules.py::
  modules_by_capability` = all matches ("×2" in the table).
- Map: `layouts/da_capability_map_view.py` (`cose`, every edge, `text-overflow-wrap: anywhere`),
  callbacks `da_capability_map_callbacks.py` (tap moves into a capability).

## Part 1. Suggest a catalog (W21-18)

| # | Piece |
|---|---|
| S1 | **Groups from code links, no AI.** New function in `da_code_clusters.py`: `groups(graph, store)`: label propagation on the module link graph with **no** `MIN_TAGGED` rule, then: groups of 1 join the group they link to most (if any), groups over 25 programs are split once by top folder. Each group keeps its programs, its top folders and its link count inside vs outside |
| S2 | **The AI names each group.** One call per group (role "Tagger" model), input: up to 40 programs' paths and saved one-line AI summaries (never code). Reply JSON: `name` (2 to 40 characters, business words), `description` (max 120), `not_in_group` (paths that do not fit), `confidence`. Read with G5's forgiving reader, one retry |
| S3 | **Merge step.** One more call gets all group names and descriptions and returns merges ("A and B are the same area: name C"). Target **5 to 12** capabilities; above 12 the smallest are merged into their most-linked neighbour by plain code. Names equal (ignoring case, spaces, plural "s") to an existing capability become a normal proposal for it |
| S4 | **Button and timing.** Capability catalog, Capabilities view: **Suggest capabilities from the code** (shown when the catalog has fewer than 5 capabilities or more than 30% of programs are unassigned). Also offered once after a Full rebuild with an empty catalog. Runs as a job (same lock, G5 progress bar, steps "Grouping programs", "Naming groups", "Merging") |
| S5 | **Cards.** Each suggestion is a G4 S4 card: "Suggested from code links: <name>", description, program chips (each with Remove from this suggestion), "N programs, M links inside", confidence. **Create and assign** (edit name and description, pick seniors, saves one rulebook version with exact-path patterns), **Reject**. Never created by itself. After any Create, the queue offers the existing **Re-check the No capability fits programs** |
| S6 | **Tagger prompt for an empty list:** when no capabilities exist: "No capabilities exist yet. Suggest a new one for this program; use a short business area name." |
| S7 | Fake data at home: 12 made-up programs in 3 linked groups (plus 1 loner) give 3 suggestion cards, the loner joins its most-linked group |

## Part 2. A module in more than one capability (W21-20)

| # | Piece |
|---|---|
| M1 | **Main and also.** A module's **main** capability stays first match wins (catalog order): it owns the named senior, escalations and Discover's narrowing. Every other capability whose patterns match is an **also in** capability. New helper `capabilities_of(path, capabilities) -> (main, also: list[str])` in `da_admin_meaning.py`; `capability_of` stays and returns `main` |
| M2 | **Shown everywhere:** module chips in the catalog show "Also in: Ingestion"; the meaning search and Discover's "In capability" label list main first, then "also"; the map draws also-in as a dashed link (part 3); the Unassigned count never counts a module that has a main |
| M3 | **Browse modules choices:** a module already in another capability shows two buttons, **Move here** (today: moves the exact pattern) and **Also add here** (adds an exact pattern here, keeps the other) |
| M4 | **Tagger:** the reply may add `also` (one more exact capability name). It becomes a separate card "Also add <path> to <name>?" with Add and Reject. Approve all high-confidence never adds also-in |
| M5 | Escalation, flag zones and required reviewers use the main capability only. Every change is one rulebook version with a plain note |

## Part 3. A readable capability map (W21-23)

| # | Piece |
|---|---|
| C1 | **Unassigned hidden by default:** switch "Show unassigned programs" (off). The count shows in the map header: "34 programs unassigned" with a link to the Review queue |
| C2 | **Strong links only:** slider "Show links with at least N calls" (1 to 20, default 3) and a switch "Top 3 links per capability" (on). Weaker links appear only around a focused capability |
| C3 | **Shared foundations:** new capability field `kind`: Business (default) or **Shared foundation** (edit in the catalog; one rulebook version). Shared foundations are drawn as a row of small chips along the bottom ("Config, used by 9 capabilities"); their links are hidden unless one is clicked. Old versions read as Business |
| C4 | **Click to focus:** clicking a bubble keeps it and its direct neighbours, fades the rest (`.faded`), shows arrows only on its links, and opens a side panel: links in and out (capability, number of calls, top 5 calling programs). Double click or **Open** moves into the capability (today's tap behaviour). Click on empty space clears the focus |
| C5 | **Drawing:** one colour per capability from the palette in `styles/` (stable by name), labels **below** the bubble on a white label background, wrap at spaces only (no `anywhere`; fixes "EmbeddingandVector"), font 12 px, edge width 1 to 6 px (log of calls), layout `concentric` with the most-linked capability in the middle (same picture every time), bubble size by program count capped at 3 times the smallest |
| C6 | **Links table:** a third view next to Map: rows "A calls B: N calls (M programs)", sortable, filter by capability, also-in links marked "also" |
| C7 | **Proof:** Playwright on the map at 1366 and 1920 px with the 13-capability fake catalog: no label overlaps a bubble or another label (bounding boxes from cytoscape), with defaults at most 3 links per capability are drawn, Unassigned is not drawn |

## 2. Edge rules

- No new library (dash-cytoscape is already in). No new database table; new rulebook fields
  (`kind`) with defaults; old versions still read.
- AI never creates or changes a capability by itself. Every Admin change is one rulebook version.
- Prompts get paths and one-line summaries only, never code text, for S2 and S3.
- Never log a prompt, a reply or code. Fake AI at home only. Never touch `main`.
- Words for labels and buttons come from constants.

## 3. Acceptance criteria (Given / When / Then)

| ID | Given / When / Then |
|---|---|
| G6-1 | Given an empty catalog and the 13-program fake graph (3 groups and a loner), when Suggest capabilities runs, then 3 suggestion cards show, the loner is in its most-linked group, and nothing is created |
| G6-2 | Given two groups the fake AI names "Markdown export" and "Markdown Exports", then the merge step gives one card |
| G6-3 | Given 15 groups, then at most 12 cards show; the smallest were merged into their most-linked neighbour |
| G6-4 | Given Create and assign on a card with 1 of 5 programs removed, then one version holds the capability with 4 exact patterns and the note names the suggestion; the removed program stays unassigned |
| G6-5 | Given the job running, then the G5 progress bar shows the 3 step names, other job buttons are disabled, and the cards appear without a reload |
| G6-6 | Given `agent_flows/flw_md_to_fs.py` matched by Markdown (first) and Ingestion, then its main is Markdown, also-in is Ingestion, the chip shows "Also in: Ingestion", and an escalation for it goes to the Markdown senior only |
| G6-7 | Given Browse modules on Ingestion with that module ticked, when Also add here is pressed, then one version adds the exact pattern to Ingestion and keeps Markdown's |
| G6-8 | Given a fake tag reply with `also`, then a separate "Also add ... to ...?" card shows; Approve all high-confidence does not add it |
| G6-9 | Given the map with defaults, then Unassigned is hidden, each capability shows at most 3 links, links under 3 calls are hidden, and Shared foundation capabilities are chips along the bottom |
| G6-10 | Given a click on a bubble, then only it and its neighbours are bright, arrows show on its links only, and the side panel lists its links with call counts and top programs |
| G6-11 | Given a capability named "Embedding and Vector", then its label wraps at the space, never inside a word |
| G6-12 | Given the map drawn twice from the same data, then the bubble positions are the same |
| G6-13 | Given the Links table, then each row shows from, to, calls and programs, sorts by calls, and filters by capability |
| G6-14 | Given the map at 1366 and 1920 px, then no label overlaps a bubble or another label (Playwright measure) |
| G6-15 | AF-2 label scan passes on every new part |

## 4. Work notes

1. After G6: Capability catalog, **Suggest capabilities from the code**; review the cards; Create the
   good ones; Re-check the rest.
2. Mark Config, Classes and Database as **Shared foundation**; open the map with defaults.

## 5. Out of scope

- COBOL, RPG and CL relationships. Running graphify itself (the DA borrows its method: link groups
  first, AI names them).
