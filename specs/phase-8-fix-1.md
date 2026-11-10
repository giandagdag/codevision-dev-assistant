# Phase 8 fix 1: what Gian found testing Refine at home

Version 1.0 APPROVED, 10 Nov 2026 (22:36 SGT). Gian: "go ahead and proceed with your recommendations".
Written in the project chat from Gian's home test of CVDA-2026-0002 and CVDA-2026-0006 (demo mode).
All D-x below are option 1 (the recommended one), except D-E: option 2.

Branch `phase-8-fix-1` (spec commit fbe4ab6, from `auto/phases-7-10`). PR into `auto/phases-7-10`;
the chief merges it. Build it the normal way: plan, plan review, build in small steps with tests, code
review (max 3 rounds), pytest, ruff, smoke check.

**When (Gian, 10 Nov 22:47, D-E option 2): queued AFTER Phase 9.** Do not pause or touch Phase 9.
When the Phase 9 PR is merged into `auto/phases-7-10`, the chief launches the builder on this fix
(laptop team, as normal). First step of the build: merge `auto/phases-7-10` into `phase-8-fix-1`, so
the fix is built on top of Phase 9. Then Phase 10.

Keep changes surgical: Phase 9 has changed the same screen and Refine files. Check each fix still
applies to the Phase 9 version of the file (for example Phase 9 Refine steps and enhance requests).

## 1. The bugs

| # | Severity | What Gian saw | Root cause (checked in code) |
|---|---|---|---|
| B6 | Critical | Check my edits "does nothing": the Build tab stays at "Layer B: running 9 tests" and all three boxes say Waiting | **Not a stuck run.** The check run finished at 22:11:01 (same second it started). The server log shows **no browser request at all** from 22:11:01 until Gian's manual refresh at 22:28:20, so the 3-second poll (`da-build-poll`, `poll_build`) never fired after the redraw that started the run. Exact cause not found yet (see section 3) |
| B1 | High | Added test T-10, it fails today, but the Tests tab still ends at T-9 | As spec D-N: nothing is appended before his click, so a pending test lives only in the chat. Correct storage, missing display |
| B4 | High | Requirement change: chat says "AC-8 is added" but AC-8 is nowhere on screen until Confirm v2; tab stays where it was | Phase 8 spec section 5 step 4 says the Summary tab shows the diff at the checkpoint. `version_history_blocks` only reads **saved** versions, so a draft v2 shows nothing. The chat line names the ID but not its text |
| B5 | High | After Confirm v2, Discover only offers "Findings look right" | Spec D-D chose one click. Also, after Confirm v2 the status leaves REVISION_IN_PROGRESS, so Get help is gone too: no way out if the findings are wrong |
| B3 | Medium | Restore an earlier version: red "There is no earlier version to restore yet." | `open_restore` leaves out the last tested set. With only Build 1, the list is empty, but the button still shows. And when he has untested edits, going back to the last tested set ("undo my edits") is a real need that is blocked |
| B8 | Medium | A check run says BUILDING, "Building. This takes a few minutes", "Round 1 of 3", "Cancel build", "Rounds used: 0 of 3", "Build 2 (check)" | Spec section 3 step 1 reuses BUILDING and the build words. Nothing is built: it is a test run |
| B2 | Medium | Tests tab needs scrolling right; finding IDs show "F-" with the number on the next line | Tester findings table (`_findings_table`) has 7 columns; the "Where" cell is monospace paths with no break points; the ID column is so narrow it breaks after the hyphen |
| B7 | Low | Button order: Re-scan, Get help, Check my edits, Restore | Get help sits between his two editing tools |
| B9 | Low | "Checking your 2 edited file(s)" when only 1 file was edited | `_check_round` counts every planned file, not the changed ones |

## 2. What we build

| # | Fix |
|---|---|
| F1 (B1) | **Pending test row.** While the Refine step is `own_confirm` or `own_fails`, the Tests table shows the pending case as the last row: `T-10 (Yours)`, its criterion, its Expect line, Result in orange: **"Fails today, waiting for your choice"** (`own_fails`) or **"Passes today, waiting for your choice"** (`own_confirm`). Drop this test: the row goes. Add this test or Yes, fix it: the row becomes a normal row. Read from the Refine state; nothing new is stored |
| F1b (B1) | **Too vague is an answer.** The own-test Tester reply may be `VAGUE` plus one question (up to 200 characters). Plain code shows "Describe the case more: <question>", nothing is run or stored, no case ID is used up. The fake script gets a `vague` switch for the test. In demo mode the scripted test stays as today |
| F2 (B4) | **Show the draft before Confirm.** At step `req_checkpoint`: (a) the chat diff lists every added and changed criterion with its full Given, When, Then (changed: old and new; removed: the old text); (b) the Summary tab shows the draft v(N+1) criteria list with tags **"New in vN+1 (not saved yet)"**, **"Changed"** (old text struck through above the new) and **"Removed"** (struck through), the new and changed rows highlighted; (c) the right panel opens on the Summary tab |
| F3 (B4) | **Open the tab the step is about.** One small mapping in the page code: `req_checkpoint` to Summary, `req_findings` to Discovery, the revision approach step to Approach, a running build or check run to Build (as today). Only when the step changes; a tab he picked himself stays until the next step |
| F4 (B5) | **Same three Discover buttons as Phase 3** at `req_findings`: ✅ Findings look right, ✏️ Something's missing, 🙋 Escalate to a senior developer. Reuse the Phase 3 handlers and the round cap (`Round 2 of 3`). Escalate moves the request to ESCALATION_REQUIRED with open item `Escalated in Refine: Discover`, audit as the Phase 3 escalate |
| F5 (B3) | **Restore only when it can work, plus Undo my edits.** (a) When there is no earlier set **and** no untested edits, the button is shown greyed with the line "Nothing to restore yet: there is only one tested version." (b) When a re-scan found untested edits, the last tested set is offered too, as **"Undo my edits (back to build N)"**. It uses the same restore write and warning ("Your current edits in `<path>` will be replaced. They stay saved on the server and can be restored."). The error text stays as a server-side guard |
| F6 (B8) | **A check run reads as testing.** Status stays BUILDING inside the system (no new status, no `ALLOWED_MOVES` change). When the current run has kind `check`, the screen says: pill **TESTING**; chat "Testing your edits. This takes a few minutes. You can leave this page."; banner "One test pass on your files (the AI changes nothing)." instead of "Round 1 of 3"; button **Cancel test**; This build box title **This test run** without the Rounds line; Versions row **"Test run N (your edits)"**. Normal builds and rebuilds unchanged |
| F7 (B2) | **No side scroll on the Tests tab.** Findings table: ID cell `white-space: nowrap`; Where cell wraps anywhere (`overflow-wrap: anywhere`); Check number and Cites move under the message as one small dimmed line, so 5 columns are left. Rule for this tab: no horizontal scrollbar at a 1366 px wide window |
| F8 (B7) | **Button order** at `b_written` and NOT_PASSING: Re-scan, Check my edits, Restore an earlier version (or Undo my edits), Get help last |
| F9 (B9) | **Honest file count:** "Testing <n> planned file(s) (<m> edited by you)". `m` = files whose scanned fingerprint differs from the last written one. After his new test case (`after_new_test`), "Testing <n> planned file(s) with your new test" |
| F10 (B6) | **The page keeps refreshing while a run is going.** Find the cause first (section 3), then fix it so the poll fires for every build kind started from any button |

## 3. B6: find the cause first

Facts: demo mode; Check my edits clicked 22:11:01; server log has two 200 and four 204 responses at
22:11:01, then nothing until the manual reload at 22:28:20; after the reload the page shows the
finished result (Build 2, check, Ready for your review, 9 of 9). So the run, the database and the
redraw are fine; the timer in the browser did not run.

Leads to check, in this order (say which one it was before changing code):
1. The page redraw replaces `dcc.Interval(id="da-build-poll")`. At `b_written` it is drawn with
   `disabled=True`; the next redraw draws it with `disabled=False` under the same id. Check whether
   the browser keeps the old timer stopped (React reuses the component).
2. The Refine bar path (`handle_refine_button` then `run_refine` then `submit_build`) versus the
   Phase 6 Build button path: compare what each returns and redraws.
3. `poll_build` refuses when `n_intervals` is falsy or `state["build"]` is missing.

Proof: a Playwright test (skipped when no browser, like 7-35): demo mode, edit a planned file,
Re-scan, Check my edits, then wait **without reloading** until the page shows "Ready for your
review" (max 15 seconds). Also run it for the first Build, to know if Phase 6 has the same bug.
If the cause cannot be found in 2 attempts, stop and report (CLAUDE.md stop rules).

## 4. Edge rules

- No new library, no new status, no database change (F1 and F2 read existing state).
- F3 never moves him away from a tab during the same step (a redraw by the poll keeps his tab).
- F5 never deletes files and never touches frozen tests or the record version (spec section 9 kept).
- F6 words come from one place (constants), so Phase 9 can reuse them.
- The Refine cap, budgets and audit events are unchanged, except F4's escalate event.

## 5. Choices (D-x). DECIDED: option 1 for all (Gian, 10 Nov 22:36)

- **D-A Pending test display:** 1. Row on the Tests tab (F1). 2. Chat only (today). 3. A separate "Pending" box.
- **D-B Undo my edits:** 1. Offer the last tested set when untested edits exist (F5). 2. Never (today).
- **D-C Discover after a revision:** 1. The three Phase 3 buttons (F4), changes Phase 8 D-D. 2. One click (today).
- **D-D Check run wording:** 1. Screen-only TESTING (F6). 2. A real TESTING status (more moves and tests, same result on screen).
- **D-E When:** CHOSEN option 2 by Gian (10 Nov 22:47): after Phase 9 is merged, before Phase 10. (Option 1 was now, in a cloud session in parallel.)
- **Parked (Phase 9 or later):** a warning when his edit adds behaviour no criterion covers.

## 6. Acceptance criteria (Given / When / Then)

| ID | Given / When / Then |
|---|---|
| FX-1 | Given a check run started from Check my edits in demo mode, when it finishes, then the page shows the result **without a reload** within 6 seconds (Playwright; skipped with no browser) |
| FX-2 | Given the first Build in demo mode, when it finishes, then the page shows the result without a reload (same test, tells us if Phase 6 had B6 too) |
| FX-3 | Given a new test case that fails today, when the Tests tab is drawn, then the last row is the case with "Fails today, waiting for your choice"; after Drop this test the row is gone; after Yes, fix it it is a normal row |
| FX-4 | Given the fake Tester answers VAGUE, when he adds a test case, then the chat asks "Describe the case more: ..." and no case ID is used up |
| FX-5 | Given a requirement change that adds AC-8, when the checkpoint is shown, then the chat shows AC-8's Given, When, Then, the Summary tab shows AC-8 tagged "New in v2 (not saved yet)", and the Summary tab is open |
| FX-6 | Given a change that edits AC-3 and removes AC-5, when the checkpoint is shown, then AC-3 shows old and new text and AC-5 is struck through with "Removed" |
| FX-7 | Given Discover ran on v2, when the findings step is drawn, then the three Phase 3 buttons show; Something's missing runs round N+1 within the cap; Escalate ends in ESCALATION_REQUIRED with an open item |
| FX-8 | Given only one tested version and no untested edits, when the Build tab is drawn, then Restore is greyed with the "Nothing to restore yet" line and no click reaches the server |
| FX-9 | Given one tested version and an untested edit after a re-scan, when he presses Undo my edits (back to build 1), then the warning names the file, and after confirming the folder has build 1's text and his edit is still on the server |
| FX-10 | Given a check run is running, when the page is drawn, then the pill says TESTING, the chat says "Testing your edits...", the button says Cancel test and no "Round 1 of 3" shows; given a normal build, the words are unchanged |
| FX-11 | Given 2 planned files and 1 edited, when a check run starts, then the line reads "Testing 2 planned file(s) (1 edited by you)" |
| FX-12 | Given the Tests tab with findings, when drawn, then IDs are on one line, Where cells may wrap, and the table has 5 columns (layout test on the component tree; visual check by Gian at 1366 px) |
| FX-13 | Given `b_written`, when the Refine bar is drawn, then the order is Re-scan, Check my edits, Restore (or Undo my edits), Get help |

## 7. Out of scope

- P31 (Windows-only sandbox child-process test). Still open, still must be fixed before `main`.
- Any Phase 9 feature or file that exists only on `auto/phase-9`.
- The Audit tab (greyed today as planned).
- The parked "behaviour no criterion covers" warning.
