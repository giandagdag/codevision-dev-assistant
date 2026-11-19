# Upgrade G plan: index relationships, capability map, versioning (#101)

Spec: `specs/index-catalog-versioning.md` v1.0 (approved 19 Nov, no open D-x). Branch
`phase-g-index-graph`. PR into `auto/phases-7-10` with `--body-file logs/pr-body-g.md`; never main.
Commit subjects say "G step N". At most 3 steps per run; each step: tests, commit, push. Tests use
fakes and `tmp_path` only (no real AI, no internet), made-up modules only. Only new library:
`dash-cytoscape==1.0.2` (step 9). CLAUDE.md "Current phase" gets one line in step 1 (file stays under
6,000 bytes). Pytest in small groups per step, full run once at the end.

AS400 picture: step 1 is DSPPGMREF for every Python module (who calls whom); steps 2 and 3 are save
files of each index build with compare and restore; step 6 does the same for the tag file.

Facts read in the code (20 Nov): `da_build_code_index.build_index` splits with `split_folder`
(skips `.venv`, `__pycache__`, `looks_secret`, `da_` paths and Admin exclusions) and saves with
`_save` (`.new` files then `os.replace`); `da_admin_rebuild._run` calls it, then `_tag_step`, then
`record_run` (last 10 in `da_code_index_runs.json`); `da_admin_job.progress` feeds the job panel;
`da_admin_tag_store` owns `da_module_tags.json`.

## Steps (build order)

1. **G1a/b Relationship layer (pure module).**
   - New `agents/da_code_graph.py`, standard library only: `build_graph(source, files, old=None)`
     reads the same file list the index keeps (caller passes the kept paths), parses with `ast`,
     records `imports`, `calls`, `uses class` edges only when provable (same-module name, `from x
     import y`, `alias.name`); unresolved calls counted per module. `save_graph`/`load_graph` for
     `da_code_graph.json` (per file: hash, edges, unresolved). Delta: files with an unchanged hash
     keep their saved entry; deleted files drop. A file that fails to parse is listed in `skipped`
     with its reason.
   - CLAUDE.md "Current phase": REPLACE the Fix NP text with one Upgrade G line (stays under 6,000
     bytes). Reuse `da_impact.module_name` for path to dotted name and the index's own file hashes.
   - Tests `tests/test_da_code_graph.py`: G-1, G-2, G-3, G-4 (re-read count), G-5, G-25 (fixed
     generated data, 5,000 nodes / 17,000 edges, load under 2 s).
2. **G1c + G5a/b Wire into the rebuild job; build numbers and saved copies.**
   - New `agents/da_index_builds.py`: `next_build_number` (highest manifest number + 1, so a
     rollback never reuses a number), `save_build(out, mode, started_by, hashes, counts)`, called
     from `da_admin_rebuild._run` only when `summary.saved` (Stop and "Not saved" get no number; the
     command-line `main()` does not number). It writes `da_code_index_builds/K/manifest.json`,
     copies FAISS, pieces and graph files for the newest `KEPT_INDEX_COPIES = 5` builds and deletes
     the copies (never manifests) of older ones.
   - `da_build_code_index.build_index` calls graph build after the pieces step (progress "Reading
     code links: n of m files" via a new optional callback, default none) and saves the graph
     beside the index only on the saved path, in the same `.new` then `os.replace` save as the
     other two files. `_run` works out K with `next_build_number` before the build and passes it to
     `build_index` as a new optional argument; `_save` writes K into the pieces record next to
     `build_id`, so a rollback brings the right K back and step 7 reads it from there (the
     command-line `main()` passes none).
     `da_admin_job.STEP_LABELS`/`TOTAL_STEPS` get a new step "Reading code links" (noun "files"),
     the tagging step moves to 3 (`job.progress(..., step=2)` at lines 44 and 47 of
     `da_admin_tagger_job.py`); test: panel says "Step 3 of 3: tagging programs". `_run` puts "build" in the run row; `run_line` and
     the job panel say "Build K".
   - Tests: panel text "Reading code links: n of m files"; G-18 (7 builds, copies on 3 to 7 only), manifest content, run line shows "Build K",
     Delta build leaves other files' edges unchanged, a build with a bad file is saved.
3. **G5c/d Compare builds and roll back the index.**
   - In `da_index_builds.py`: `compare_builds(out, a, b)` (modules added, removed, changed; piece and
     edge count changes from manifests), `roll_back(out, k, who)` restores the copy files with the
     same `.new` then `os.replace` pattern, refuses while a rebuild or tag job runs (uses
     `running_since`), only when the copy exists, adds run line "Rolled back to build K", writes
     audit `index_rolled_back`, never deletes newer copies. `roll_back` takes the same lock
     (`_take_lock`, `LOCK_NAME`) for the whole restore and frees it at the end.
   - **Audit decision (plan review Must fix 1):** `add_audit_event` needs a request id, and an index
     rollback or tag restore belongs to no request. No admin audit store exists. Decision, flagged
     for Gian in the PR: a small append-only JSON log `da_admin_audit.json` next to the index
     (`agents/da_admin_audit.py`: `add_admin_event(kind, who, text)`, `read_admin_events`), used by
     steps 3 and 6. Moving to a table later changes that one file.
   - Repository and index tab (`da_admin` layout/callback files, found with Grep): two build pickers
     with a Compare result, "Use build K" with a confirm.
   - Tests: G-17, G-19, G-20.
4. **G3 Impact answers.** New `agents/da_code_impact_graph.py`: `who_uses`, `impact_of` (2 levels,
   capability tag from the tag store). Discover hit shows "Used by N modules" with expand list;
   Enhance impact section uses the graph when present, else today's light search unchanged.
   Tests G-8, G-9, G-10.
5. **G2 Clusters and suggestions.** `agents/da_code_clusters.py` (label propagation, sorted, 20
   rounds); suggestion cards in the existing Capability catalog proposals with Approve / Assign to /
   Reject; rejected suggestions stored with the cluster fingerprint in `da_cluster_rejects.json`.
   Clusters are computed inside the rebuild job after the graph step, never when the page is drawn. Tests G-6, G-7.
6. **G5f Tag versions.** `da_module_tags_versions/T.json` plus list file, saved from the Admin
   decision callers of `save_store` (`da_admin_tag_cards.py`: approve, reject, assign, Approve all,
   restore) with who and note passed in; an AI tagger run is NOT a version event (it only proposes;
   noted for Gian). Question for Gian in the PR: Restore T brings back the tag file only; the rulebook
   version saved by Approve (`approve_pairs`) is undone with History Restore. Built to the spec
   words. Tag history list, diff view, Restore T (confirm, audit `tags_restored`, new version
   "Restored from T"). Tests G-23.
7. **G5e Requests record the build.** `index_build` column on Discovery and Approach (default empty;
   added to old databases with the `PRAGMA table_info` then `ALTER TABLE` pattern of
   `db_tbl_da_discovery.py`; old rows "not recorded"), summary and Handoff PR summary "Rules vN ·
   Index build K". Tests G-21, G-22, plus an old-schema database test.
7b. **G5g Rules impact.** History Restore and Save confirm shows open requests (not handed off) per
   older rulebook version, reusing `list_pinned_request_ids`. Test G-24. Own commit "G step 7b".
8. **G4b Capability map data.** `agents/da_capability_map.py`: plain nodes and edges for levels
   (capabilities, one capability, one module), 300-node cap with "Showing 300 of N", module paths
   only, no cytoscape import. Tests G-13 (data part), G-14, G-16, G4g empty-graph text.
   Step 8 also holds plain search (module or function name) and capability filter functions, the
   faded other-capability nodes and the "Unassigned" bubble, each with a test.
9. **G4a/c/f/g Map page** (also the search box, filter, back button, breadcrumb and the new-tab
   link, each with a test). `dash-cytoscape==1.0.2` in `requirements.txt` and `requirements-home.txt`
   (checked it installs; ask Gian only if it does not); `layouts/da_capability_map_view.py` (the only
   cytoscape file; brand constants for colors and fonts), page `/dev-assistant/capability-map`,
   links "Open capability map" on Admin catalog and Discover. Tests G-11, G-12, G-13, G-15.

## Test map

| Criterion | Step |
|---|---|
| G-1 to G-5, G-25 | 1 |
| G-18 | 2 |
| G-17, G-19, G-20 | 3 |
| G-8 to G-10 | 4 |
| G-6, G-7 | 5 |
| G-23 | 6 |
| G-21, G-22 | 7 |
| G-24 | 7b |
| G-14, G-16 | 8 |
| G-11 to G-13, G-15 | 8, 9 |

## After the last step

Full pytest, `ruff check .`, smoke check, then `code-reviewer` (max 3 rounds), then write
`logs/pr-body-g.md` and open the PR. Known risks: Python 3.14 `ast` call resolution is limited to
provable names (by design); cytoscape is a trial and lives in one file.
