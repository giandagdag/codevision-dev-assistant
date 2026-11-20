# Fix G1: Upgrade G follow-ups (tests on the final code, small fixes, map screenshot)

Version 1.0 APPROVED, 20 Nov 2026 (08:15 SGT). Written in the project chat from the builder's own
"skipped and risks" list in the Upgrade G worker note (PR #105, merged 20 Nov 07:51). Gian, 20 Nov
08:09: "Yes go start with 1." All choices below are decided; none is open.

Branch `phase-g-fix-1`, cut from `auto/phases-7-10` after PR #105. Plan `specs/fix-g-1-plan.md` with
a `## Steps` list, plan review, small steps with tests, commit subjects "G1 step N", code review
(max 3 rounds), **full pytest, ruff and smoke check on the final commit** (paste the counts), PR into
`auto/phases-7-10`; the chief merges it when CI is green. No new library.

**How to open the PR:** write the body to `logs/pr-body-g1.md`, then one plain line:
`gh pr create --base auto/phases-7-10 --head phase-g-fix-1 --title "Fix G1: Upgrade G follow-ups" --body-file logs/pr-body-g1.md`

## What we build

| # | Item | Today (PR #105) | Build |
|---|---|---|---|
| F1 | Proof on the final code | Full pytest ran on 9a4f884, before the review fixes; smoke check too | Run full pytest, ruff and the smoke check on this branch's final commit and paste the real counts in the PR |
| F2 | "Used by" wording | `used_by_block` in `web/da_web_components.py` always says "modules" | "Used by 1 module", "Used by N modules"; with 0, "Not used by other modules" and no list |
| F3 | Map filter at every level | The capability filter only fades bubbles at level 1 (`da_capability_map.py`, `highlight`) | Inside a capability or module view, nodes that belong to the chosen capability stay solid and the rest fade; clearing the filter restores all. Data side only (`da_capability_map.py`), so the Plotly swap rule (G4b) still holds |
| F4 | Confirm boxes name what they restore | "Use build" and "Restore" tag-version confirms do not say which one | "Use build 5 (20 Nov 03:10 SGT, Delta, 1,234 pieces)?" and "Restore tag version 7 (20 Nov 02:40 SGT, Approve all by <user>)?" from the manifest and the version list |
| F5 | One number per build | A failed `save_build` (`agents/da_index_builds.py`) could let two builds share a number | The next number is the highest existing manifest number + 1, read while the rebuild lock is held. `save_build` never overwrites a folder that already has a manifest: it takes the next free number and the run line says so |
| F6 | Links cards after a tag run | A tag run on its own can overwrite a "Suggested from code links" card until the next rebuild | After a tag run, re-run the cluster suggestion step (plain code, no AI, reads the saved graph) so links cards come back. Rejected cards stay rejected (G-7 rule) |
| F7 | Map seen in a real browser | Never opened in a browser | Extend the AF-20 browser test (`tests/test_da_admin_screens_browser.py`, same skip rule when the browser is missing): open the map page with the fake data at 1366 by 768, take `logs/admin-screens/map-level1.png` and `map-capability.png` (after one capability click), and assert the graph rendered (canvas present, node count above 0) with no browser console errors |
| F8 | Work wiring note | The map page is wired only in the home shell | A short section in `docs/build-work-test.md`: the exact lines from the home shell that CodeVision's own page setup must add (`map_shell()`, the map callbacks, the route), plus "run `pip install -r requirements.txt` after downloading, because dash-cytoscape is new" |

## Acceptance criteria

| ID | Given / When / Then |
|---|---|
| G1-1 | Given the final commit, when the gate runs, then the PR shows the real full pytest count, ruff clean and smoke passed |
| G1-2 | Given 1, 3 and 0 users, when `used_by_block` draws, then it reads "Used by 1 module", "Used by 3 modules", "Not used by other modules" |
| G1-3 | Given the filter set to Limits inside a capability view, when the data is built, then non-Limits nodes have `faded` true and Limits nodes false; cleared, none are faded |
| G1-4 | Given build 5 with a manifest, when "Use build 5" is pressed, then the confirm text names its time, mode and piece count |
| G1-5 | Given tag version 7, when Restore is pressed, then the confirm names its time and note |
| G1-6 | Given folder 6 already holds a manifest (a failed earlier save), when the next build saves, then it becomes build 7, folder 6 is untouched and the run line says so |
| G1-7 | Given a links card and a tag run that rewrites the tag file, when the tag run ends, then the links card is back; a rejected one is not |
| G1-8 | Given the browser is installed, when the AF-20 test runs, then both map PNGs exist, the graph rendered and there are no console errors |
| G1-9 | Given `docs/build-work-test.md`, then it has the map wiring section and the pip install line |

## Out of scope

- A Plotly version of the map (only if the cytoscape trial fails at work).
- Wiring the map into CodeVision itself (done at work from F8's note).
- Anything Gian finds in today's work test: that becomes the next batch.
