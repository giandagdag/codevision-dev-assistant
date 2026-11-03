# Phase 5: Workspace

Status: APPROVED v1.0 (1 Nov 2026). Decisions D-A to D-E chosen by Gian: option 1 for all five
(section 14). Defaults D-F to D-I (section 15) were set by Claude and not objected to. Q10 answered
(section 16).
**v1.1 (3 Nov 2026), after Gian's work test:** P29 (practice folder instead of "a copy of the repo",
Command Prompt steps, no DevTools part) and P30 (Re-scan, Change and Reconnect only as chat buttons;
the header chip shows status only; no Re-scan in the Build tab). Edited: sections 1, 3, 6, 9, 11,
16, 17, 18. Rows 5-1 to 5-30 are unchanged; 5-31 and 5-32 are new.
Depends on: Phase 4 (READY_TO_BUILD, the accepted file plan). **Merged into `main` at a5f1368.**
Next: Phase 6, Build + test loop (`specs/redesign-2026-10-31.md` section 5.4).
Source of truth for the design: `specs/redesign-2026-10-31.md` sections 5.6, 5.7 (re-scan and rule R5.1
only) and 5.10 (the final fingerprint check, later).
Visual reference: `docs/CodeVision_Developer_Assistant_Demo.html`. Read only the chat script entry
`/*28*/` (in the `MAIN` list), the function `chip` (the header chip) and the constant `WS_FILES` (the
file status table). Note: the demo shows a full path `C:\Dev\codevision`. The browser only ever tells
the page the folder's NAME (`codevision`), never the full path. Show the name only. Also note: the
demo's chip carries a Re-scan button; in the build the chip is status only (P30) and Re-scan sits
under the chat.
Build: fresh Claude Code session, Sonnet, branch `phase-5`.

## In plain words

After Approach the app knows exactly which files it will write. Phase 5 connects the app to the
developer's own copy of CodeVision on his laptop (the workspace), checks that the file plan fits that
folder, takes a fingerprint of every planned file, and proves that writing and reading back works.
Phase 6 then writes the real code through this same door.

The key fact: **the Python server cannot touch the laptop.** Only the browser can, and only after the
developer picks the folder in the browser's own folder picker and clicks Allow. So all file work in
this phase is done by JavaScript in the page. Python decides WHAT may be written and keeps the record;
the browser does the reading and writing.

AS400 comparison: the workspace is like a developer's own source library. The app is allowed to
`ADDPFM` and `CHGPFM` only the members on the approved change form (the file plan), nothing else in
the library. A fingerprint is like the member's last-changed timestamp, but exact: if even one
character changes, the fingerprint changes. "Re-scan" is like running `DSPFD` over those members to
see which ones somebody touched since we last wrote them.

**No AI calls in this phase.** Nothing for the fake script or the pretend work server.

## Words used in this spec

| Word | Meaning |
|---|---|
| Workspace | The developer's local CodeVision folder (his clone). Chosen with the browser's folder picker |
| Folder picker | The browser's own "choose a folder" window (File System Access API, `showDirectoryPicker`). Chrome and Edge only, https or `127.0.0.1` only |
| Handle | What the browser gives the page after the folder is picked: a key to that one folder. It can be remembered in the browser's own storage (IndexedDB), never on the server |
| Fingerprint | A SHA-256 hash of a file's text: a 64-character code that changes if any character changes |
| Baseline | The fingerprint and text of each planned `modify` file, taken at the workspace check, before anything is written |
| Write job | The list the server hands the browser: path, text, and the fingerprint the file must still have before it is overwritten |
| Re-scan | The browser reads the planned files and this request's tests folder again and compares fingerprints |
| Fallback | For when the picker is missing or refused: download a ZIP, and upload the folder to re-scan |
| Tests folder | `tests/<request id in lower case with _>/`, for example `tests/cvda_2026_0001/`. The only folder the app may create |

## 1. The flow (one step at a time)

Same screen: chat on the left, tabs on the right. The workspace has its own small state (section 10)
with its own revision number, like Approach.

| Step | Where | The developer sees | Then |
|---|---|---|---|
| start | request is READY_TO_BUILD | Button **Choose workspace folder** (replaces the disabled Phase 4 button). If the browser remembers a folder (D-B), the chat names it and offers **Use codevision** and **Choose another folder** | The picker opens (or the remembered folder is re-allowed) |
| `ws_picking` | picker open | The browser's own window. Cancel returns to start with "No folder chosen" | Folder picked and allowed: step `ws_checking` |
| `ws_checking` | folder allowed | Chat: "Checking your folder". Busy state | The browser runs the workspace check (section 4) and returns the results in one go |
| `ws_blocked` | the check found a blocker | The list of blockers in plain words. Buttons **Choose another folder**, **Change the approach**, **Get help** | See W5 and W6 |
| `ws_ready` | the check passed | Chat: the folder name, the warnings if any, "Tests folder created". Build tab shows the file table. Disabled button **Build (coming in Phase 6)**. Header chip shows the folder name and a tick (status only). Chat buttons: **Re-scan** and **Change** (and **Reconnect**, only when the browser needs your OK again, W4) | End of Phase 5 |
| `ws_fallback` | picker not available, or refused | Buttons **Download ZIP**, **Upload folder to check**, **Try the folder picker again** | Section 7 |

Rules for the flow:
- W1: Every step allows one kind of input, as in Understand and Approach. Wrong input is refused with
  a plain message.
- W2: Every action follows the Approach pattern: read with no lock, let the browser do its file work,
  then ONE write transaction saves state, file rows, audit events and chat lines together. The
  workspace revision is used for the stale-window check (the same `STALE_MESSAGE`).
- W3: The server never trusts a path from the browser. It only accepts results for paths it put in
  the job. The browser never writes a path that is not in the job (R1 checked on both sides).
- W4: The browser asks for permission only after a click (browsers require this). On page load it may
  only CHECK whether permission is still there; if not, the chip says "Needs your OK" and a
  **Reconnect** button appears under the chat (it is drawn hidden and the browser shows it, again on
  every redraw and on "My recent requests" reopen; it exists at `ws_ready` only).
- W5: **Change the approach** from `ws_blocked` moves the request back to APPROACH_PROPOSED and opens
  the Approach change box (Phase 4 rule G4 applies from there: re-accept, new Tester plan, re-accept).
  This uses the Phase 4 change counter (G9).
- W6: **Get help** moves the request to ESCALATION_REQUIRED with open item
  `Escalated in Workspace: <step>`, as Approach does.
- W7: **Change** (a button under the chat, at `ws_ready`) re-opens the picker. A different folder runs the full
  check again and takes a new baseline. Nothing is deleted from the old folder.
- W8: Re-scan is allowed at `ws_ready` at any time and never changes the step or the status.

## 2. Statuses

No new statuses (D-I). The workspace is a connection, not a stage of the request. Two new moves
(add to `ALLOWED_MOVES`, every move audited as today):
- READY_TO_BUILD to APPROACH_PROPOSED (W5)
- READY_TO_BUILD to ESCALATION_REQUIRED (W6)

Phase 6 will add "workspace ready" as a condition before BUILDING.

## 3. The workspace state shown to the developer (header chip)

| Chip | When |
|---|---|
| 📁 No workspace chosen | No folder linked to this request |
| 📁 codevision · Needs your OK | Folder remembered, but the browser wants permission again (new visit). The **Reconnect** button is under the chat |
| 📁 codevision · ✅ | Linked and allowed, check passed. **Re-scan** and **Change** are under the chat |
| 📁 codevision · ⚠️ Not a CodeVision folder | Check found the folder is wrong (section 4, B1 or B2) |
| 📁 Download mode | Fallback in use. **Download ZIP** and **Upload folder** are under the chat (at `ws_ready` in download mode: **Download ZIP** and **Upload folder to re-scan**) |

The chip never holds a button (P30). Every action is a chat button, once.

## 4. The workspace check (browser reads, server judges)

The browser collects facts; the Python side turns them into blockers and warnings with plain code,
so the rules are testable with pytest without a browser.

The browser collects, for the picked folder:
- whether each marker folder in the policy's `workspace_markers` exists (D-F),
- whether the folder looks like `src` itself (it holds the markers one level up, minus `src/`),
- whether a `.git` folder exists (it is not opened),
- for each file in the accepted file plan: does it exist, does its parent folder exist, and for
  existing files the text and fingerprint (size limit `workspace_max_file_kb`, UTF-8 only),
- whether the tests folder exists and which files it holds (names only).

Blockers (the step becomes `ws_blocked`):
- B1 **Not CodeVision:** a marker folder is missing. "This does not look like your CodeVision folder.
  It should contain src/web and src/callbacks."
- B2 **Picked src:** "You picked the src folder. Pick the folder above it." (the picker cannot go up a
  level by itself, so the developer must pick again).
- B3 **Missing file to change:** a `modify` file does not exist. "The plan changes <path>, but your
  folder does not have it. Pull the latest code, choose another folder, or change the approach."
  (This settles Phase 4's "Not found in Discover, checked in Phase 5" warning.)
- B4 **New file already there:** a `create` file already exists. "<path> already exists. Choose
  another folder, or change the approach to modify it instead."
- B5 **Missing folder:** a planned file's parent folder does not exist. The app never creates folders
  in `src/`.
- B6 **Unreadable:** a `modify` file is larger than the limit or is not UTF-8.
- B7 **Tests folder in use:** the tests folder already holds files this request did not write (for
  example from an older attempt). "Move or delete tests/cvda_2026_0001/ first."

Information (shown, never blocks, not a warning):
- **No .git folder:** "This folder is not a Git clone (for example a ZIP from Bitbucket). That is
  fine: at Handoff you upload the changed files to Bitbucket yourself, and the Handoff list tells you
  which ones." Saved in the check result so Phase 10 can word the Handoff steps for this case (Q10).

When there is no blocker, in the same transaction: the baseline of every `modify` file is saved
(D-H), the tests folder is written (D-A), and the step becomes `ws_ready`.

## 5. Writing (the write job)

Phase 5 writes one real file: `tests/<id>/__init__.py` with a one-line comment (D-A). The same code
path writes Phase 6's code later, so it must be complete now.

The server builds a write job: for each file `path`, `text`, `expected` (the fingerprint the file
must have right now: the baseline or the last write; "absent" for a new file).

The browser, for each file in order:
1. Walk the path one folder at a time. Refuse `..`, `.`, empty parts, and any path not in the job.
   Create folders only for the tests folder (`tests/` and `tests/<id>/`).
2. **Edit guard (R5.1, D-C):** read the file now and fingerprint it. If it differs from `expected`
   (or the file exists when "absent" was expected), STOP: write nothing more and report
   "changed since last time, Re-scan first".
3. Write the text, then read it back and fingerprint it. Report the new fingerprint.

The server saves one `written` row per file that succeeded and an audit event per job. A stop or an
error leaves the files already written in place and says exactly which ones were written and which
were not. Nothing is retried automatically.

Line endings (D-G): before hashing, the text is normalised (Windows line endings `\r\n` become `\n`,
and a leading byte-order mark is dropped). When the app changes an existing file it keeps that
file's line-ending style. New files get `\n`.

## 6. Re-scan

Allowed at `ws_ready`, from the **Re-scan** button under the chat (in download mode: **Upload folder
to re-scan**). The browser reads only: every planned file,
and the names and text of files inside this request's tests folder. Nothing else is opened (R1).

Result per file, compared with its last known fingerprint (last write, else baseline):

| Result | Meaning |
|---|---|
| Unchanged | Same fingerprint |
| Changed by you | Different fingerprint. The new text is saved as a `scanned` row |
| Missing | The file is gone |
| New in tests folder | A file in the tests folder the app did not write. Listed, saved as `scanned` |

Phase 5 only detects and lists. Showing the change side by side, and sending the developer's edits
through the test layers, is Phase 8. The chat says: "1 file changed by you. It will be checked when
the build runs (Phase 6 onwards)."

## 7. Fallback (small on purpose)

Offered automatically when `window.showDirectoryPicker` does not exist or the page is not a secure
page, and offered as a button when the developer refuses the picker or permission.

- **Download ZIP:** a ZIP of the current write job (in Phase 5: the tests folder `__init__.py`) laid
  out with full paths, plus a one-page `READ_ME_FIRST.txt` saying which folder to unzip it into.
  The app records the fingerprints as `written` with mode `download`, because it cannot see the
  laptop.
- **Upload folder to check:** an `<input type="file" webkitdirectory>`. The browser lists the whole
  folder, but the page reads and sends ONLY the planned files and the tests folder files. The rest
  is never read. The server runs the same check (section 4) or re-scan (section 6) on what arrives.
- The fallback has no edit guard on download (the app cannot see the folder). The chat says so once:
  "In download mode, upload your folder before every new download so I never overwrite your edits."
- No other fallback features. If the live test at work (Q8) shows the picker works, this stays a
  safety net.

## 8. Rulebook policy additions

Same pattern as Phase 4 section 7: new `Policy` fields with defaults equal to the starter values, so
older rulebook versions still load.

| Field | Meaning | Starter value (made up, real values set at work) |
|---|---|---|
| `workspace_markers` | Folders that must exist in a CodeVision clone | `src/web`, `src/callbacks` |
| `workspace_max_file_kb` | Largest file the browser will read | 512 |

## 9. Screen

Use the existing `da_web_components` helpers where they exist.

- **Header chip** as section 3 (status only, no buttons), on every step from READY_TO_BUILD onwards.
- **Approach tab:** unchanged, except the "Not found in Discover" warning now reads "Checked: found in
  your workspace" or the B3 blocker text, once a check has run.
- **Build tab** becomes available (no longer greyed) from `ws_ready`, with only the workspace panel:
  1. One line: "Workspace: codevision. Checked 1 Nov, 15:40." (Singapore time, stored UTC.)
  2. **File table** like `WS_FILES`: File, Action (New / Change), Status (Not written yet, Written,
     Changed by you, Missing), and the baseline time for `modify` files. The tests folder row shows
     "Created".
  3. The last re-scan result, if any.
  4. Disabled **Build (coming in Phase 6)**. The tab holds no Re-scan button (P30).
- The composer follows the 2D control: buttons only on every workspace step.
- "My recent requests" reopens at the same step. If the browser needs permission again, the chip says
  so and a **Reconnect** button appears under the chat; the developer clicks it (W4).

How the page runs browser code: Dash clientside callbacks (JavaScript that runs in the page). They may
return a promise (Dash 2.4 and later; work has 3.4.0). The JavaScript must ship as part of our own
files so that plugging the page into CodeVision needs no change to CodeVision's own `assets` folder
(the builder picks how, for example reading one `src/web/da_workspace.js` file into the callbacks at
start-up). The plan states the choice.

## 10. Storage

New file `db_table_functions/db_tbl_da_workspace.py`, same style as `db_tbl_da_approach.py`. Three
new tables, `CREATE TABLE IF NOT EXISTS`. Nothing in existing tables changes.

| Table | Holds | Rule |
|---|---|---|
| `da_workspace_state` | step, own revision, folder name, mode (`picker` or `download`), last check result JSON, linked time | one row per request, revision goes up by 1 with every save |
| `da_workspace_files` | request ID, path, file version (1, 2...), kind (`baseline`, `written`, `scanned`), text, fingerprint, line-ending style, mode, approach version, created time | append-only, key (request ID, path, file version) |
| `da_workspace_scans` | request ID, scan number, results JSON (path and result), created time | append-only |

Audit events (actor in brackets): `workspace_chosen` (developer, folder name), `workspace_check_failed`
(system, blockers), `workspace_check_passed` (system, warnings), `workspace_baseline_taken` (system,
paths and fingerprints), `workspace_written` (system, paths and fingerprints), `workspace_write_stopped`
(system, the path and why), `workspace_rescanned` (developer, counts), `workspace_fallback_used`
(developer, which one), `approach_reopened` (developer), `escalated` (developer). Every status move is
audited, as today.

## 11. Testing without a laptop

- **pytest (Python side):** the check rules (section 4) and re-scan rules (section 6) take the
  browser's facts as plain data, so they are tested with made-up facts. The write job builder, the
  edit-guard decision, line-ending normalisation and the fingerprint (Python `hashlib.sha256` must
  give the same code as the browser for the same text) are all plain functions.
- **Playwright (cloud session only):** headless Chrome cannot click a real folder picker. The test
  replaces `window.showDirectoryPicker` before the page loads (`page.add_init_script`) with one that
  returns the browser's private test folder (`navigator.storage.getDirectory()`), which is a real
  folder handle. The plan's first step proves this works in the cloud browser; if it does not, stop
  and report (stop rule). No test switch is added to the app itself.
- **Smoke check:** run a full request from READY_TO_BUILD to `ws_ready` with a fake browser bridge,
  then a re-scan that finds one changed file.
- **Home check by Gian:** on `http://127.0.0.1:8050` (it counts as a secure page). Pick the small
  **practice folder** (P29): `src\web`, `src\callbacks` and a one-line `src\agents\upload_validator.py`.
  Not a copy of the repo: the fake plan modifies that file, which the repo does not have, so a repo
  copy always stops at B3. The Command Prompt steps are in `docs/workspace-work-test.md`.

## 12. Carried forward (small fixes in this phase)

| ID | Fix |
|---|---|
| P24 | Offer **Get help** at Approach step `tests_pending` (next to Write the test plan), so a Tester that stays down is not a dead end. Add `tests_pending` to the steps `request_help` accepts |
| P25 | Add `.vscode/` to `.gitignore` |
| N2 | Already stored: `da_discovery_results` has a `record_version` column, filled by Discover. What is missing is a USE of it. Add to Phase 4 gate check 2: "and that round was built from the latest confirmed record version", with a test. (See D-E if you would rather just close N2.) |

## 13. Out of scope

- Writing any code file (Phase 6). Phase 5 writes only the tests folder `__init__.py`.
- Side-by-side view of changes, sending edits through the layers, conflict picking, restore (Phase 8).
- Freshness check against Bitbucket `main` (Phase 9).
- Picking files for Review my code (Phase 10). The final fingerprint check at Handoff (Phase 10).
- Any Git command. The app never commits, pushes or pulls.
- Admin screens for the new policy fields (Phase 11).

## 14. Decisions (chosen by Gian, 1 Nov 2026: option 1 for all five)

| # | Question | Options (ranked) | Recommendation |
|---|---|---|---|
| D-A | What does Phase 5 really write, when no code exists yet? | 1. Check + baseline + write the tests folder `__init__.py` (a real file that `unittest` needs anyway). 2. Check + baseline only; the writer is built and unit-tested but the first real write happens in Phase 6. 3. A home-only "test write" button | **1**: the whole door (write, read back, fingerprint, re-scan, edit guard) is proven on a real laptop before Phase 6 piles the generator on top. Option 2 hides write bugs until Phase 6 |
| D-B | Where is the chosen folder remembered? | 1. In the browser (IndexedDB), one workspace per browser; each request saves the folder NAME it was linked to and warns if a different one is used. 2. Pick the folder again for every request | **1**: it matches the demo ("chosen once, remembered") and Chrome's "Allow on every visit" option. The browser still asks for permission each new visit unless he picks that option |
| D-C | Build the edit guard (never overwrite an unscanned edit, R5.1) now or in Phase 8? | 1. Now, inside the writer. 2. Phase 8 | **1**: it costs one fingerprint compare per file now. Retrofitting it after Phase 6 writes real code means a window where the app can overwrite his edits |
| D-D | When the check finds a blocker, what are the ways out? | 1. Choose another folder, Change the approach (back to APPROACH_PROPOSED), Get help. 2. Warn and continue anyway | **1**: continuing with a missing `modify` file only moves the failure into Phase 6, where it is more confusing |
| D-E | N2 | 1. Add the record-version condition to gate check 2 now (small, one test). 2. Close N2 as done (the column exists) and leave the check to Phase 8, when record v2 first appears | **1**: it is a few lines and a test, and it stops a stale Discover round slipping through once Phase 8 exists. Option 2 is fine if you want Phase 5 strictly about the workspace |

## 15. Defaults Claude chose (say if you disagree)

| # | Choice | Alternative | Why |
|---|---|---|---|
| D-F | A CodeVision folder is recognised by marker folders in the rulebook policy, plus a "you picked src" check; no `.git` is information only | Accept any folder | Picking the wrong folder is the most likely mistake. A ZIP download from Bitbucket is a normal workspace (Q10) |
| D-G | Fingerprints ignore line-ending style (`\r\n` vs `\n`) and a leading byte-order mark; writes keep a file's existing style | Raw bytes | On Windows, editors and Git flip line endings. With raw bytes every such flip would show as "changed by you" |
| D-H | The server keeps the TEXT of every baseline, write and scan, not just the fingerprint | Fingerprints only | Restore (R5.4) and Phase 6 patching need the text. At work it sits in CodeVision's own database, next to the code it came from |
| D-I | No new status; the workspace has its own state, and Phase 6 checks it before building | A WORKSPACE_READY status | A folder can be changed or lose permission at any time; a status cannot go back and forth like that cleanly |

## 16. Open questions (for the work test, round 2)

- Q8 live test (still to do, 3 Nov change): PowerShell and DevTools are blocked on the work laptop,
  so the picker is tried through the real screen, in Chrome, then Edge, with the practice folder
  (P29). Press **Choose workspace folder**. Note whether the folder window opens (if not, the app
  offers the ZIP fallback), how many prompts appear, and whether "Allow on every visit" is offered.
  Pick the practice folder only.
- Q10 **Answered (Gian, 1 Nov):** Git is allowed on work laptops but not mandatory. Developers get
  CodeVision either with `git clone` or by downloading a ZIP from the Bitbucket repo. Either folder
  is a valid workspace. The generated files stay in that folder; the developer moves them to
  Bitbucket himself (commit and push, or upload). The Developer Assistant never pushes. For Phase 10:
  redesign 5.10 "commits from his clone" becomes "commits or uploads from his workspace".
- Q11 Where do CodeVision's own tests live, and does the top `tests/` folder have an `__init__.py`?
  `python -m unittest` discovery only goes into folders that have one. If `tests/__init__.py` is
  missing, our `tests/<id>/` tests will not be found from the top folder (Phase 6 problem, found now).
- Q12 Where do developers keep the clone? Chrome refuses to share some folders (for example the whole
  user folder or system folders). A folder like `C:\Dev\codevision` is fine.

## 17. Done when (every line becomes a test, Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| 5-1 | a request at READY_TO_BUILD | the screen is drawn | the chip says "No workspace chosen" and Choose workspace folder is active |
| 5-2 | facts from a folder missing `src/callbacks` | the check runs | blocker B1, step `ws_blocked`, nothing written |
| 5-3 | facts from the `src` folder itself | the check runs | blocker B2 with "Pick the folder above it" |
| 5-4 | a plan that modifies a file the folder lacks | the check runs | blocker B3 names the path |
| 5-5 | a plan that creates a file that already exists | the check runs | blocker B4 |
| 5-6 | a plan file whose parent folder is missing | the check runs | blocker B5; no folder is created |
| 5-7 | a `modify` file over the size limit, and one that is not UTF-8 | the check runs | B6 for each |
| 5-8 | a tests folder holding a file this request did not write | the check runs | B7 |
| 5-9 | a good folder with no `.git` | the check runs | it passes; the "not a Git clone" information line shows and is saved in the check result |
| 5-10 | a good folder | the check passes | baselines saved for every `modify` file; `tests/<id>/__init__.py` written and read back; step `ws_ready`; audit has `workspace_check_passed`, `workspace_baseline_taken`, `workspace_written` |
| 5-11 | a write job | a path not in the job, or with `..`, reaches the writer | it is refused on both the browser and server side |
| 5-12 | a file whose current fingerprint differs from `expected` | a write job runs | the job stops at that file, files before it stay written, the message names both lists, audit has `workspace_write_stopped` |
| 5-13 | a new file expected "absent" that now exists | a write job runs | stopped by the edit guard |
| 5-14 | the same text with `\r\n` and with `\n`, and with a leading byte-order mark | fingerprinted in Python | all give the same fingerprint |
| 5-15 | the same text | fingerprinted in Python and in the browser (Playwright) | the codes are equal |
| 5-16 | a file with `\r\n` line endings | the app writes a changed version | the written file keeps `\r\n` |
| 5-17 | `ws_ready` and one planned file edited on disk | Re-scan is pressed | it is listed as Changed by you, a `scanned` row is saved, status and step unchanged |
| 5-18 | `ws_ready` and an extra file in the tests folder | Re-scan is pressed | it is listed as New in tests folder; no file outside the plan and tests folder is read |
| 5-19 | `ws_blocked` | Change the approach is pressed | status APPROACH_PROPOSED, the change box opens, the change counter goes up, audit has `approach_reopened` |
| 5-20 | `ws_blocked` | Get help is pressed | status ESCALATION_REQUIRED with open item `Escalated in Workspace: ws_blocked` |
| 5-21 | the picker is cancelled | the action ends | back at start with "No folder chosen"; nothing saved but the chat line |
| 5-22 | a browser without `showDirectoryPicker` (simulated) | Choose workspace folder is shown | step `ws_fallback` is offered |
| 5-23 | fallback | Download ZIP is pressed | the ZIP holds `tests/<id>/__init__.py` and `READ_ME_FIRST.txt`; `written` rows with mode `download` |
| 5-24 | fallback | a folder is uploaded | only planned and tests folder files are sent; the check runs on them |
| 5-25 | any workspace action | it is sent with an old revision | refused with the stale message |
| 5-26 | a rulebook version saved before Phase 5 | it is loaded | the new fields hold the starter values |
| 5-27 | Playwright with the private test folder standing in for the picker | a full request runs from READY_TO_BUILD | it reaches `ws_ready` and the file exists in that folder |
| 5-28 | Approach step `tests_pending` (P24) | the screen is drawn | Get help is offered and works |
| 5-29 | `.gitignore` (P25) | it is read | it lists `.vscode/` |
| 5-30 | a Discover round built from record v1 while the latest confirmed record is v2 (N2, if D-E is 1) | the gate runs | check 2 is false and named in plain words |
| 5-31 | a request at any workspace step (P30) | the screen is drawn | the header chip has no button; Re-scan, Change, Reconnect (and the fallback buttons) appear once each, under the chat; the Build tab has no Re-scan; Reconnect is hidden until the browser needs your OK, and is shown again after any redraw |
| 5-32 | the practice folder (P29): `src\web`, `src\callbacks` and a one-line `src\agents\upload_validator.py` | the check runs on the fake plan | it passes; and `docs/workspace-work-test.md` builds exactly that folder with Command Prompt lines |

Plus: `pytest` 0 failures, `ruff check` 0 problems, smoke check passes, code reviewer 0 Must fix, and a
home check by Gian on `127.0.0.1:8050` with the practice folder (P29) as the workspace.

## 18. Files the builder will touch (for planning, not a limit)

`pydantic_classes/da_models.py` (two moves), `da_workspace_models.py` (new), `da_rulebook_models.py` and
`data/da_rulebook_seed.json` (two policy fields), `agents/da_workspace_flow.py`, `da_workspace_checks.py`
(new), `db_table_functions/db_tbl_da_workspace.py` (new), the browser script (new, for example
`web/da_workspace.js`), `layouts/da_developer_assistant_page.py`, the page callbacks,
`web/da_web_components.py` (chip, Build tab), `agents/da_approach_flow.py` (P24, N2),
`da_smoke_check.py`, `.gitignore`, `README.md`, `CLAUDE.md` ("Current phase"), a new
`docs/workspace-work-test.md` (the Q8 live test steps from section 16, as Command Prompt steps with the practice folder), and the matching tests.
