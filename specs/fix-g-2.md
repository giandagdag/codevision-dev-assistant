# Fix G2: two parked items (P38 console error, P39 map labels) and the idle state

Version 1.0 APPROVED, 20 Nov 2026 (13:25 SGT). Written in the project chat. Gian, 20 Nov 13:17:
"Yes go ahead. Go for option 2 now." All choices below are decided; none is open.

Branch `phase-g-fix-2`, cut from `auto/phases-7-10` after PR #106. Plan `specs/fix-g-2-plan.md` with a
`## Steps` list, plan review, small steps with tests, commit subjects "G2 step N", code review (max 3
rounds), full pytest, ruff and smoke check on the final commit, PR into `auto/phases-7-10`; the chief
merges it when CI is green. No new library.

**How to open the PR:** write the body to `logs/pr-body-g2.md`, then one plain line:
`gh pr create --base auto/phases-7-10 --head phase-g-fix-2 --title "Fix G2: P38, P39 and the idle state" --body-file logs/pr-body-g2.md`

## Already on this branch (written in the project chat, ops is a guard folder)

**Idle state (#107 was a false alarm).** `Next: idle: <why>` now means "queue empty on purpose":
`chief_tick.has_work` treats it as no work, `stall.reason` raises no alarm (unpushed commits still
do), the board shows "⚪ IDLE: queue empty, waiting for your next job", and `chief.md` tells the
chief to use it when the queue is empty. Evidence: tests/ops 657 passed (4 new), ruff clean. **The
builder does not change these files**; it only keeps them when merging the newest base.

## What the builder builds

| # | Item | Today | Build |
|---|---|---|---|
| P38 | Console error "nonexistent object in a State ... `da-ws-ctx`" | The Phase 5/6 workspace callbacks read `WS_CTX_ID` (`layouts/da_workspace_panel.py`) on pages that do not have that store (the capability map page, probably the Admin page) | Find the cause first (name the callbacks). Then the smallest safe fix: the store is present on every page the shell draws, or the callbacks only fire where it exists. Remove the exception the G1 browser test added for this message, so any console error fails the test again. Check the Admin and Developer Assistant pages in the same test |
| P39 | Map labels overlap | Long module labels collide when bubbles sit close (G1 screenshots) | In `layouts/da_capability_map_view.py` only (the Plotly swap rule stays): show the short module name (file name without folders and `.py`) as the label, the full path on hover/click; labels wrap at a fixed width; a layout setting that spaces nodes by label size. Retake the two G1 screenshots and add a third with 40 modules in one capability |

## Acceptance criteria

| ID | Given / When / Then |
|---|---|
| G2-1 | Given the map, Admin and Developer Assistant pages in the browser test, when opened, then the console has no errors, and the test has no exception for `da-ws-ctx` |
| G2-2 | Given a workspace request page, when used as before, then the workspace callbacks behave exactly as today (existing workspace tests pass unchanged) |
| G2-3 | Given a module `src/agents/da_example_long_name.py`, when drawn, then its label is `da_example_long_name` and the full path shows on click |
| G2-4 | Given 40 modules in one capability (fake data), when the capability view is drawn, then the screenshot `map-dense.png` is saved and the layout setting for label spacing is set (component tree test) |
| G2-5 | Given the final commit, when the gate runs, then the PR shows the real full pytest count, ruff clean and smoke passed |

## Out of scope

- Anything from Gian's work test (not done yet). A Plotly map.
