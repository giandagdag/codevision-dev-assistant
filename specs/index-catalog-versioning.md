# Upgrade G: index relationships, capability map and versioning (#101)

Version 1.0 APPROVED, 19 Nov 2026 (23:45 SGT). Written in the project chat from project doc
`claude/queued-index-catalog-versioning.md` (queued 19 Nov 21:13, tracking issue #101). Design talk
answers from Gian, 19 Nov 23:30: versioning covers **rules, index and catalog**; map drawn with
**dash-cytoscape as a trial** (if it does not work at work, Gian asks for Plotly); map for **Admin and
developers**; cluster suggestions **always wait for Admin**. Gian gave full approval for everything
else (19 Nov 23:22): every other choice below is decided, no D-x is open.

Branch `phase-g-index-graph`, cut from `auto/phases-7-10` after Fix NP (PR #104) was merged. Plan
`specs/index-catalog-versioning-plan.md` with a `## Steps` list, plan review, small steps with tests,
code review (max 3 rounds), full pytest, ruff, smoke check. Commit subjects say "G step N" so the board
counts. PR into `auto/phases-7-10`; the chief merges it when CI is green, then opens a `gian-later`
issue for Gian's look check of the map page at work.

**How to open the PR (19 Nov lesson, #103):** a multi-line `gh pr create --body "..."` is refused in
dont-ask mode. Write the body to `logs/pr-body-g.md` first, then run one plain line:
`gh pr create --base auto/phases-7-10 --head phase-g-index-graph --title "Upgrade G: index relationships, capability map, versioning" --body-file logs/pr-body-g.md`

## 0. Why

The code index (B1, Phase 11 fix 3) stores **pieces** (functions and classes) so Discover can search
by meaning. It does not know **who uses whom**. Gian's 16 Nov ask: scan all of CodeVision, know what
each module does, park programs under capabilities. His director's item D4 (parked 12 to 14 Nov):
versions and rollback. This upgrade adds both.

AS400 comparison: today we have member descriptions. This adds DSPPGMREF for every program (the
cross-reference), groups programs that work together, draws the picture, and keeps saved copies of
each build like a save file you can restore from.

Checked in the code on 19 Nov (`auto/phases-7-10` after PR #104):

| Today | Gap |
|---|---|
| `agents/da_admin_rebuild.py` runs Full and Delta index builds as one job; runs listed in `da_code_index_runs.json` (last 10) | No relationships; no build number; no saved copies, so no compare and no rollback |
| Rulebook versions and Restore exist (`db_tbl_da_rulebook.py`, History tab) | Restore does not say which open requests are on which version |
| Discovery and Approach rows store `rulebook_version` | No record of which index build a request searched |
| Program tags in `da_module_tags.json` (fix 11-2) | No history: an Approve all cannot be undone |
| Phase 9 Enhance has a light structural search (P16) | No real "who uses this" |

## 1. Words used here

- **Edge:** one proven link between two pieces of code: `imports`, `calls`, `uses class`
  (inherits or creates). Only links read from the code; never guessed.
- **Graph:** all edges, saved in `da_code_graph.json` next to the index.
- **Cluster:** a group of modules that mostly link to each other.
- **Index build K:** one saved Full or Delta run, numbered 1, 2, 3...
- **Tag version T:** one saved state of `da_module_tags.json`.

## 2. What we build

### G1 Relationship layer (no AI, no new library)

| # | Piece |
|---|---|
| G1a | New `agents/da_code_graph.py`. Reads the same files the index reads (same `source_folder`, same skip rules, `looks_secret` files skipped) with the standard `ast` module. Records `imports` (module to module), `calls` (function to function, only when the target can be proven: a name defined in the same module, a name brought in by `from x import y`, or `alias.name` where `alias` is an imported module), `uses class` (base classes and `ClassName(...)` calls resolved the same way). Calls it cannot resolve are **counted per module, never drawn** |
| G1b | Saved as `da_code_graph.json`: per file its hash, its edges and its unresolved count. Delta builds re-read only files whose hash changed and drop edges of deleted files |
| G1c | Runs inside the existing rebuild job after the pieces step (Full and Delta). The job panel shows "Reading code links: n of m files". A file that fails to parse is listed under skipped with its reason, the build goes on |

### G2 Clusters suggest capabilities (Admin always confirms)

| # | Piece |
|---|---|
| G2a | `agents/da_code_clusters.py`: module-level weights (imports + calls between two modules), clustered with plain label propagation, deterministic (sorted order, fixed 20 rounds). Standard library only |
| G2b | For an **untagged** module whose cluster has at least 3 tagged modules and one capability holds more than half of them: a suggestion "Suggested from code links: N of M linked modules are <capability>". Shown as a card in the existing Capability catalog proposals, with the same Approve / Assign to / Reject buttons. Never saved by itself. Rejected suggestions are not shown again until the cluster changes |

### G3 Impact answers

| # | Piece |
|---|---|
| G3a | `who_uses(module_or_symbol)`: direct users; `impact_of(module)`: direct users plus their users (2 levels), each with the capability tag |
| G3b | Discover: each hit shows "Used by N modules" with the list on expand |
| G3c | Enhance (Phase 9): the impact section lists the 2-level users from the graph when a graph exists; otherwise today's light search, unchanged |

### G4 Capability map page (dash-cytoscape trial)

| # | Piece |
|---|---|
| G4a | New library `dash-cytoscape==1.0.2` in `requirements.txt` and `requirements-home.txt` (approved by Gian 19 Nov as a trial; checked: installs with Dash 3.4.0 on Python 3.14, its script is served by our own app, no internet) |
| G4b | **All cytoscape code in one file**, `layouts/da_capability_map_view.py`. The data comes from `agents/da_capability_map.py` as plain nodes and edges (no cytoscape types), so a switch to Plotly later changes one layout file and its tests |
| G4c | Page `/dev-assistant/capability-map`, read only, opens in a new tab. Links: **"Open capability map"** on the Admin Capability catalog, and on the Discover tab for developers |
| G4d | Level 1: capabilities as bubbles (size = module count), lines = links between them (thickness = weight), plus one "Unassigned" bubble. Click a capability: its modules and their links (other capabilities shown as faded bubbles). Click a module: its functions, who calls it, who it calls, its capability, its unresolved-call count. Back button and breadcrumb. Search box (module or function name) and capability filter |
| G4e | At most 300 nodes per view; above that it shows the top 300 by links and a note "Showing 300 of N, narrow with search". No absolute or server path anywhere: module paths only from `src/` down, as the catalog shows them |
| G4f | Colors and fonts from `cv_styles` / Admin brand constants, never the library's defaults |
| G4g | Old data: no graph yet shows "Run a Full rebuild to draw the map" |

### G5 Versioning (rules, index, catalog)

| # | Piece |
|---|---|
| G5a | **Index build number.** Every saved Full or Delta run gets build number K (run list and job panel show "Build K"). Manifest `da_code_index_builds/K/manifest.json`: time, mode, started by, file hashes, piece, edge and module counts |
| G5b | **Saved copies.** The last 5 builds keep a full copy of their index files (FAISS, pieces, graph); older builds keep the manifest only. Fixed in code (`KEPT_INDEX_COPIES = 5`), not an Admin setting |
| G5c | **Compare builds.** Repository and index tab: pick two builds, see modules added, removed, changed, and piece and edge count changes |
| G5d | **Roll back the index.** "Use build K" (only builds with a saved copy) restores its files, refused while a rebuild or tag job runs, asks to confirm, audited (`index_rolled_back`), adds a run line "Rolled back to build K". Never deletes the newer copies |
| G5e | **Requests record the build.** Discovery and Approach rows get `index_build` (new column, default empty; old rows read as "not recorded"). Summary and the Handoff PR summary show "Rules vN · Index build K" |
| G5f | **Tag versions.** Every tag change event (approve, reject, assign, Approve all, restore) saves tag version T with a one-line note, who and when (`da_module_tags_versions/T.json` + list file). Capability catalog gets "Tag history": list, view what changed (modules added, moved, removed), **Restore T** (confirm, audited `tags_restored`, saved as a new version "Restored from T") |
| G5g | **Rules impact on restore.** The History tab's Restore confirm shows how many open requests (not handed off) use each older rulebook version and says they keep their version; new work uses the restored one. Same note on Save |

## 3. Edge rules

- New library: only `dash-cytoscape==1.0.2`. Everything else is the standard library and what is installed.
- No AI in G1 to G3 and G5. Nothing runs by itself: graph, clusters and copies happen inside the Admin rebuild job.
- Suggestions never tag silently (G2b). Rollback and restore never delete history.
- Python source only (CodeVision is Python). COBOL, RPG and CL links are out of scope.
- Clean room: tests and home data use made-up modules only. No real UOB names.
- Size: the graph file for about 4,700 pieces must load in under 2 seconds on the laptop (test with a generated graph of 5,000 nodes and 17,000 edges).

## 4. Acceptance criteria (Given / When / Then)

| ID | Given / When / Then |
|---|---|
| G-1 | Given `a.py` with `from b import f` and a call `f()`, when the graph is built, then edges a→b (imports) and a.caller→b.f (calls) exist |
| G-2 | Given a call to a name that cannot be resolved, when built, then no edge exists and the module's unresolved count is 1 |
| G-3 | Given class `C(B)` and `B()` in another module, when built, then two `uses class` edges exist |
| G-4 | Given a Delta build after one file changed, when it runs, then only that file is re-read and the other files' edges are unchanged |
| G-5 | Given a file with a syntax error, when the build runs, then it is listed as skipped with its reason and the build is saved |
| G-6 | Given a cluster of 5 linked modules, 4 tagged Limits and 1 untagged, when suggestions run, then one card says "Suggested from code links: 4 of 4 linked modules are Limits" and nothing is tagged until Admin approves |
| G-7 | Given a rejected suggestion, when the next build leaves the cluster unchanged, then the card does not come back |
| G-8 | Given the graph, when `impact_of("m")` runs, then it returns direct users and their users with capability tags |
| G-9 | Given a Discover hit, when drawn, then it shows "Used by N modules" |
| G-10 | Given an Enhance request and a graph, when the impact section is drawn, then it lists the 2-level users; with no graph, today's result is unchanged |
| G-11 | Given the catalog, when "Open capability map" is clicked, then `/dev-assistant/capability-map` opens in a new tab at capability level, read only |
| G-12 | Given a developer (not Admin), when the Discover tab is drawn, then the map link is there and the page opens; no Admin buttons appear on it |
| G-13 | Given a capability click (fake data), when the view redraws, then its modules and links show; a module click shows its functions, callers and callees |
| G-14 | Given 1,000 modules, when level 1 or a capability view would show more than 300 nodes, then 300 show with "Showing 300 of N" |
| G-15 | Given the page, when rendered, then no absolute or server path and no external script URL appear, and colors come from the brand constants |
| G-16 | Given `da_capability_map.py`, when imported, then it does not import `dash_cytoscape` (swap rule G4b) |
| G-17 | Given two saved builds, when compared, then added, removed and changed modules and the count changes are listed |
| G-18 | Given 7 builds, when the 7th saves, then builds 3 to 7 have copies and 1 and 2 keep only manifests |
| G-19 | Given build 5 with a copy, when Admin confirms "Use build 5", then the index files match build 5, an `index_rolled_back` audit event exists, and the run list says "Rolled back to build 5" |
| G-20 | Given a rebuild running, when "Use build K" is pressed, then it is refused with the reason |
| G-21 | Given a new Discovery and Approach, when saved, then they store the index build; old rows show "not recorded" |
| G-22 | Given a handoff, when the PR summary is made, then it says "Rules vN · Index build K" |
| G-23 | Given an Approve all of 12 tags, when saved, then tag version T+1 exists; Restore T brings the old tags back as version T+2 "Restored from T", audited |
| G-24 | Given 2 open requests on rulebook v6 and active v8, when Admin opens Restore v7, then the confirm says "2 open requests use v6 and keep it" |
| G-25 | Given a generated graph of 5,000 nodes and 17,000 edges, when loaded, then it takes under 2 seconds |

## 5. Decided

All by Gian on 19 Nov (four answers in chat at 23:30, full approval for the rest at 23:22): versioning
scope rules + index + catalog; dash-cytoscape trial with the one-file swap rule; map for Admin and
developers; suggestions always confirmed by Admin; 300-node cap; 5 kept index copies; G3 limited to
2 levels.

## 6. Out of scope

- COBOL, RPG and CL relationships. Running graphify itself. Coverage measuring.
- "Review my code" (on hold). Changing how the AI tagger itself works.
- A Plotly version of the map (only if the cytoscape trial fails at work: then a small follow-up).
