# Phase 5: Workspace, build plan

Spec: `specs/phase-5-workspace.md` (the only spec read; it points at the demo's `/*28*/`, `chip` and
`WS_FILES`, which I read when I reach the screen step). Branch: `phase-5`.
Pattern copied from Approach: read with no lock, let the browser do its file work, ONE write
transaction, own revision. No AI calls in this phase.

## How the browser and the server talk (the one new idea)

The Python server cannot touch the laptop. Only JavaScript in the page can. The chain, each hop a
Dash callback:

1. **Click** (a browser-run button) goes straight to a clientside callback. The picker only opens
   right after a click, so there is no server round trip before it. It picks (or re-allows) the
   folder and collects the facts of spec section 4. Result goes into store `da-ws-facts`.
2. **Server callback "judge"** reads the facts, runs the pure check rules, and replies with either
   "blocked" (ONE write: `ws_blocked`, audit, chat) or a **write job** (no write yet) in store `da-ws-job`.
3. **Clientside callback "write"** runs the job (edit guard, write, read back, fingerprint). Result goes into store `da-ws-report`.
4. **Server callback "save"** does the ONE write transaction: state, `baseline`/`written` rows,
   audit events, chat lines. Then the page refreshes.

Re-scan is the same, minus the write hop. The server never stores the job: the "save" hop rebuilds
the job from its own saved plan and accepts only paths that are in it (W3). The workspace revision
is carried in the stores and checked at hops 2 and 4 (W2, `STALE_MESSAGE`).

AS400 picture: the browser is the job on the workstation that can read the library; the server is
the program that holds the change form, decides what may be changed, and keeps the journal.

## Decisions I made where the spec is silent (none change a Done-when row)

| # | Choice | Why |
|---|---|---|
| P1 | `ws_picking` and `ws_checking` are shown only in the browser (spinner and chat line from the busy state). Only `start` (no row), `ws_blocked`, `ws_ready`, `ws_fallback` and `escalated` are saved | W2 says ONE write after the browser's file work. Saving a transient step first would be a second write. 5-21 needs only a chat line, which is a small write that does not bump the revision |
| P2 | **Gian decided (2 Nov): Python Playwright, pinned `playwright==1.63.0` in `requirements-home.txt`.** Browser tests are pytest tests that are SKIPPED (not failed) when Playwright or its browser is missing, so the laptop run stays green. No `playwright install` is ever run; the cloud browser already at `/opt/pw-browsers` is used |
| P3 | The JavaScript is one file `src/web/da_workspace.js`. A Python helper reads it at start-up and prefixes each clientside callback with it, defining `window.daWorkspace` once. Nothing goes into CodeVision's `assets` folder | Spec section 9 asks the plan to state the choice |
| P4 | Browser-run buttons have ids `{"type": "da-ws-btn", "index": key}` and are handled by clientside callbacks. Server-only buttons (**Change the approach**, **Get help**) reuse the existing `da-choice` pattern, routed by a `workspace` key in the page state | Keeps Phase 4's stale-window rule (button position checked against the saved view) |
| P5 | ZIP is built in the browser with a tiny "stored" (no compression) writer and CRC32, about 40 lines. Upload uses an `<input webkitdirectory>` that JS creates on click | No library; Dash's `html.Input` does not pass `webkitdirectory` |
| P6 | **Change the approach** (W5) writes in one transaction: status to APPROACH_PROPOSED, Approach state `done` to `change` with `change_from_tests=False` (so it counts, G9), workspace state back to `start` (folder name kept), audit `approach_reopened`. At 3 changes the button is not offered and a note says so | Spec W5 says the counter applies; G9 caps it at 3. After the approach changes, the old baseline no longer matches the file plan, so the check runs again |
| P7 | B7 (tests folder in use) compares the files found with the names of `written` rows for this request. Files this request wrote are fine, so a second check after Change the approach does not block itself | Otherwise W5 then re-check would always hit B7 |
| P8 | **Get help** at `ws_blocked` (W6): **Gian approved (2 Nov).** The workspace step STAYS `ws_blocked` (not lost). The Approach state also gets step `escalated`, and the open item reads exactly `Escalated in Workspace: ws_blocked`. Tests check both |
| P9 | The smoke check and the flow tests use a pure-Python `FakeBrowserFolder` (in `src/web/da_fake_browser_folder.py`) that answers the same facts and write-job contract as the JavaScript, over a dict or a temp folder | Spec section 11 "fake browser bridge". Lives in `src/` because the smoke check does |
| P10 | N2 (D-E option 1): gate check 2 also needs the confirmed round's `record_version` equal to the request's current record version. `compute_gate` gets one new argument, filled from `da_discovery_results` | The column exists; this adds its use |
| P11 | New file lines: `\n`. Changed existing file: its own style, detected from the last seen text (stored per file row as `line_ending`) | D-G |
| P13 | **Fingerprints are always recomputed in Python** from the text the browser sends (baseline, written, scanned). If the browser's own hash differs, the result is refused as "the browser and the server disagree" and nothing is saved. Test in step 8 | W3: the server never trusts the browser |
| P14 | Two-storage saves (`change_approach`, `request_help`) use the flow's single connection and one `begin_write`: the workspace storage functions and the Approach storage functions both take the caller's connection (existing pattern), so one commit covers status, both states, audit and chat. Test in step 8: a failure midway (forced error after the first insert) leaves nothing saved | W2 |
| P15 | D-B warning: each request saves the folder NAME at link time. A different name at a later check adds a chat line "This request was linked to <old>. You picked <new>." and the check continues (a warning, not a blocker, as D-B says). Start step shows **Use <name>** and **Choose another folder** when the browser remembers a folder | Spec 14 D-B, section 1 start row |
| P16 | Skipped browser tests show a plain skip reason ("Playwright or its browser not found: browser rows 5-15, 5-16, 5-23, 5-24, 5-27 NOT proven"). Step 17 pastes the cloud run where they pass | Evidence before done |
| P12 | `workspace_max_file_kb` is checked in the browser (it skips reading) and again on the server against the text length | W3: the server never trusts the browser |

## Steps (each ends with its tests, ruff clean)

0. **Done:** branch `phase-5`, `CLAUDE.md` "Current phase" says Phase 5, this plan.
1. **Prove the picker stand-in works in the cloud browser** (spec 11, stop rule). Throwaway Node
   script in the scratchpad, not committed: `add_init_script` replaces `showDirectoryPicker` with
   `navigator.storage.getDirectory()`; then create folder, write, read back, `crypto.subtle` SHA-256,
   `queryPermission`, store the handle in IndexedDB and read it back, all from a page on
   `http://127.0.0.1`. **If it fails: stop and report.** Done when: script prints all OK.
   **Result (1 Nov, cloud):** secure context, stand-in picker, create folder, write, read back, `queryPermission` (granted) and SHA-256 (equals Python's) all work in Chromium. Storing an OPFS handle in IndexedDB **crashes** the cloud browser, so the browser tests patch `IDBObjectStore.put/get` in the test's init script to keep handles in memory (test side only, no switch in the app). The real remembered-handle path is covered by the work test (Q8) and Gian's home check.
2. **P25** `.gitignore` gets `.vscode/`. Test 5-29.
3. **Statuses and moves** (`da_models.py`): READY_TO_BUILD to APPROACH_PROPOSED and to ESCALATION_REQUIRED. Update tests that asserted "READY_TO_BUILD has no moves out". Done when: moves table test and `test_da_status_moves.py` pass.
4. **Policy fields** (`da_rulebook_models.py`, `da_rulebook_seed.json`): `workspace_markers` (`src/web`, `src/callbacks`), `workspace_max_file_kb` 512, with defaults. Test 5-26 (old JSON loads with defaults), seed has them.
5. **Models** (`pydantic_classes/da_workspace_models.py`): `WorkspaceState`, facts (`FolderFacts`, `FileFact`), `CheckOutcome`, `WriteJob`/`JobFile`, `WriteReport`, `ScanResult`, `WorkspaceView`. Tests: extra fields refused, limits.
6. **Pure rules** (`agents/da_workspace_checks.py`): normalise and fingerprint (5-14), keep line endings (5-16 Python half), path safety (`..`, `.`, empty parts, not in job: 5-11 server half), blockers B1 to B7 and the Git information line (5-2 to 5-9), write-job builder, edit-guard decision (5-12, 5-13), re-scan comparison (5-17, 5-18). Table-driven tests, one per row.
7. **Storage** (`db_tbl_da_workspace.py`): 3 tables, append-only triggers on files and scans, revision check on state (base 0 inserts), same style as `db_tbl_da_approach.py`. Tests: round trip, append-only, stale save refused.
8. **Fake browser folder first** (`web/da_fake_browser_folder.py`, P9), then the **Flow** (`agents/da_workspace_flow.py`): `get_workspace_view`, `judge_facts` (blocked or job), `save_write_report`, `rescan`, `picker_cancelled`, `use_fallback`, `record_download`, `check_uploaded`, `change_approach`, `request_help` (P14, P15). One test file per group: check and blocked, ready (5-10), write and stop (5-11 to 5-13), re-scan (5-17, 5-18), exits (5-19 to 5-21), fallback (5-22 to 5-24), stale (5-25). Audit events as the spec lists. Tests also cover P13, P14, P15.
9. **Carried fixes in Approach** (`da_approach_flow.py`, `da_approach_checks.py`): P24 (Get help at `tests_pending`, added to `request_help` steps and `_screen_for`), N2 (P10). Tests 5-28, 5-30.
10. **Browser script** (`web/da_workspace.js`, `web/da_workspace_bridge.py`): picker, remembered handle, `queryPermission` only on load (W4), facts, write with edit guard, re-scan reads, fallback (ZIP, upload). Playwright tests: 5-15 (same code as Python), 5-16 (CRLF kept on disk), 5-11 browser half (`..` and path not in job refused), 5-18 browser half (nothing outside plan and tests folder opened), **5-12 and 5-13 browser half** (change a file in the stand-in folder, run a job: it stops at that file, earlier files stay written, nothing after is written; and a new file expected "absent" that now exists is refused), **5-23** (Download ZIP in the browser; the test saves the download and opens it with Python `zipfile`: entries are exactly `tests/<id>/__init__.py` and `READ_ME_FIRST.txt`, text matches the job), **5-24** (a picked folder holds planned files, tests-folder files and an unrelated `secret.txt`; the test counts reads in the JS and asserts the unrelated file's content was never read, and the posted payload lists only planned and tests-folder paths).
12. **Screen** (`da_web_components.py`, `da_developer_assistant_page.py`, `da_approach_panel.py`): header chip (5 states), composer buttons per workspace step, Build tab (file table, scan result, disabled Build button), Approach tab warning text. Chat shows P15 (Use <name> / Choose another folder, different-folder warning). Build tab says "Workspace: codevision. Checked 1 Nov, 15:40." in Singapore time; Approach tab warning reads "Checked: found in your workspace" or the B3 text. Tests 5-1, 5-22 screen half, button sets per step, these three texts.
13. **Callbacks**: the four hops above plus the routing of server-only buttons; stale checks (5-25 at the screen level).
14. **End-to-end in a real browser** (test 5-27): Dash app on `127.0.0.1` against a temp database with the `fake` provider, seeded to READY_TO_BUILD with the Phase 4 test helper, picker stand-in, click through to `ws_ready`, check the file exists in that folder. Also fallback: picker removed, Download ZIP and Upload folder.
15. **Smoke check** (`da_smoke_check.py`, items 22 and 23): READY_TO_BUILD to `ws_ready` with the fake browser folder, then a re-scan that finds one changed file.
16. **Docs:** README section; `docs/workspace-work-test.md` (Q8 live test steps, plus Q11 and Q12 questions); `CLAUDE.md` table unchanged.
17. **Finish:** full `pytest`, `ruff`, smoke check, browser check, `code-reviewer` (max 3 rounds), commit, push `phase-5`. Gian does the home check on `127.0.0.1:8050` with a COPY of the repo and merges himself.

## Files touched

New: `da_workspace_models.py`, `da_workspace_checks.py`, `da_workspace_flow.py`, `db_tbl_da_workspace.py`, `da_workspace.js`, `da_workspace_bridge.py`, `da_fake_browser_folder.py`, `docs/workspace-work-test.md`, matching tests.
Edited: the files in the steps above and the existing tests that assert the old disabled "Choose workspace folder (coming in Phase 5)" button text.

## Out of scope (spec section 13), not touched

Any code file write (only `tests/<id>/__init__.py`), side-by-side view, sending edits through test layers, Bitbucket freshness, Review my code, final fingerprint check, any Git command, Admin screens.

## Risks

- `da_developer_assistant_page.py` is 905 lines and `da_approach_flow.py` is 1,098: workspace code goes into new files and small additions, not rewrites.
- Chrome may drop click permission if a server hop comes before the picker; hop 1 is clientside for that reason.
- Smoke item numbers (22, 23) are confirmed against the file at step 15.
- Dash dynamic buttons only exist after a redraw; clientside callbacks use pattern-matching ids.
- Cloud headless Chromium may behave differently from Gian's Chrome; step 1 and the work test (Q8) cover the gap.
