# Fix G2 plan: P38 console error, P39 map labels (spec `specs/fix-g-2.md`)

Branch `phase-g-fix-2`, PR into `auto/phases-7-10`. The ops idle change is already on the branch
and is not touched.

## Cause of P38 (found first)
In `callbacks/screen_callbacks/da_workspace_callbacks.py` three clientside callbacks (auto write,
"Use remembered folder", header chip) have `Input("da-page-content", "children")` and
`State(WS_CTX_ID, "data")`. They run at page load. The `da-ws-ctx` store is drawn inside
`da-page-content` only on a request page, so on the map, Admin and Developer Assistant home pages
the State object does not exist, and Dash logs "nonexistent object in a State".
Dash runs a callback only when all its Inputs exist. So the fix: use the store itself as the Input
(`Input(WS_CTX_ID, "data")`), keep the State. The callbacks then run exactly where the store is
drawn (every workspace page) and nowhere else. The store is redrawn with the page, so they still
run after each redraw. Because a new store counts as a new component, AUTO_WRITE's
`prevent_initial_call=True` would skip it, so it is dropped there (its body already returns when
`ctx` is empty or the revision was already written).

(Plan review round 1 fixes: auto write keeps its `allow_duplicate` Output, so it gets
`prevent_initial_call="initial_duplicate"` instead of none; the JS argument lists become `"ctx"`
with the redundant State dropped; the Enhance panel store is named; path source is stated.)

## Steps
0. Set "Current phase" in CLAUDE.md to Fix G2 (spec, plan, branch, PR target); stay under 6,000
   bytes. Commit subjects are "G2 step N". When merging the newest base, keep the ops idle files.
1. P38: switch the three callbacks to `Input(WS_CTX_ID, "data")` and drop their State (JS args
   `"ctx"`). AUTO_WRITE gets `prevent_initial_call="initial_duplicate"` (it has an
   `allow_duplicate` Output; plain removal would make Dash refuse it). The callbacks then also run
   where `da_enhance_panel.py` draws the store (right: that is a workspace page); the enhance and
   workspace browser tests must pass unchanged. A test registers the callbacks on a Dash app.
   Browser test: one test opens the map, Admin and Developer Assistant pages and asserts zero
   console errors; remove the `da-ws-ctx` exception in `test_da_admin_screens_browser.py` and the
   comment in `test_da_understand_form_browser.py`. Existing workspace tests (incl. browser) must
   pass unchanged (G2-2). Update `specs/parked-items.md` (P38 done).
   Proof: new test, workspace tests, ruff.
2. P39 (only `layouts/da_capability_map_view.py`): node ids are dotted module names, the file
   path is the key of `graph["files"]`. `pick_view` (it has `graph`) sets each module node's label
   to the last dotted part (= file name without `.py`) and puts the path in the module details
   (`details["path"]`), which `details_lines` shows as a "File: <path>" line on a module click.
   Labels wrap at a fixed width (`text-wrap: wrap`, `text-max-width`, `text-overflow-wrap:
   anywhere` since names have no spaces), and the layout gets a label-aware spacing setting
   (`nodeDimensionsIncludeLabels: True`, plus `nodeRepulsion`). Component tree tests for G2-3 and
   G2-4. Plotly swap rule stays: no import outside this file.
3. Pictures and gate: retake `map-level1.png`, `map-capability.png`; add `map-dense.png`: the
   browser test saves a fake graph of 40 made-up modules and tags them into one capability in
   `tmp_path`. Mark P38 and P39 done in `specs/parked-items.md`. Run full pytest, ruff, smoke; code review;
   open the PR with `--body-file logs/pr-body-g2.md`.

## Out of scope
Gian's work test items; a Plotly map.
