# Fix G5: work test 21 Nov (safety gate, tagger reliability, refresh and progress, build loop, PDF report, catalog look)

Version 1.0 APPROVED, 21 Nov 2026 18:12 SGT. Gian: "Yes go ahead... Lets start the spec so we can
proceed with the build." Written in the project chat from `claude/work-test-2026-11-21-findings.md`
(W21-1 to W21-23). Every choice below is decided (recommended option); no D-x is open. The catalog
features W21-18, W21-20 and W21-23 are a separate spec, **Fix G6** (`specs/fix-g-6.md`), built
after this one.

Branch `phase-g-fix-5`, cut from the newest `origin/auto/phases-7-10` (G4 is merged there, 759153c).
PR into `auto/phases-7-10`; the chief merges it. Build it the normal way: plan `specs/fix-g-5-plan.md`
(a `## Steps` list), plan review, small steps with tests, code review (max 3 rounds), full pytest,
ruff, smoke check, screenshots. Commit subjects "G5 step N". Builder: this spec was put in the
laptop folder untracked as `specs/fix-g-5.md`; commit it as the first commit on the branch. PR body with `--body-file`. Push with an explicit
`git push -u origin phase-g-fix-5`. Leave `ops/work_queue.json` alone (guard file).

**Order is fixed: part 1 first (Critical), then 2, 3, 4, 5, 6.** If the 5-hour window runs out, each
part is a safe stopping point (tests green at the end of every part).

## 0. Code facts (read 21 Nov at 759153c)

| Area | Where |
|---|---|
| Understand | `agents/da_understand_flow.py`, `da_understand_agent.py`, `da_understand_checks.py`, prompt `data/da_understand_prompt.md` |
| Tester review | `agents/da_tester_review.py`, `da_tester_review_agent.py`, prompt `data/da_tester_review_prompt.md`; dispute `da_tester_flow.py::dispute_finding`, trigger `da_escalation_triggers.py::dispute` |
| Build loop | `agents/da_build_loop.py` |
| Test report | `agents/da_test_report.py`, `da_test_report_view.py`, page `layouts/da_test_report_page.py` (`/dev-assistant/report/`), link in `layouts/da_build_panel.py` line ~433 |
| Tagger | `agents/da_admin_tagger.py` (`parse_reply`, `_checked_new`, `run_tagging`, `MAX_SKIPPED_SHARE = 0.10`), job step `da_admin_tagger_job.py`, rebuild `da_admin_rebuild.py::_tag_step` |
| Re-check | `agents/da_admin_recheck.py` (message "Open this tab again when it is done.") |
| Run rows | `agents/da_admin_index.py::record_run` (stores `message`), `layouts/da_admin_index_panels.py::recent_refreshes`, `run_line`, `run_detail` (never show `message`) |
| Job status | `agents/da_admin_job.py` (`begin`, `progress`, `fail`, `progress_line`) |
| Admin tabs | `layouts/da_admin_page.py` (starts on `TAB_OVERVIEW`), `callbacks/screen_callbacks/da_admin_page_callbacks.py::open_tab` |
| Catalog editor | `layouts/da_admin_catalog_tab.py`, `da_admin_catalog_panels.py` (placeholder `src/agents/*limits*`, line 58) |

## Part 1. Safety gate in Understand (W21-8, Critical)

| # | Piece |
|---|---|
| P1 | **Plain-code check first** (`agents/da_safety_gate.py`, new): word lists in one constants place for (a) broad destruction: drop, truncate or delete combined with all, every, entire, whole, schema, database; wipe; disable logging, audit or controls; and (b) harmful intent: hate, revenge, get back at, punish, sabotage, angry at, my boss/manager/colleague with a negative word. Returns `none`, `destructive`, `intent` or `both`, with the matched words |
| P2 | **One AI check** (role "Understand" model): the request text and answers, reply JSON `{"verdict": "ok" or "stop" or "review", "reason": "<one line>"}`, read with the forgiving reader from part 2. Runs on **every** new request before any criteria are written. Prompt in `data/da_safety_prompt.md` |
| P3 | **Decision:** stop when the AI says `stop`, or when plain code finds `intent` (whatever the AI says). `destructive` without intent and AI `ok` or `review` goes to P5. AI call failure: plain code decides alone; `destructive` then goes to P5, never silently on |
| P4 | **Stop:** chat line (constant): "I can't help build this. <what> is destructive and cannot be undone, and the reason given is not a business need. This request has been sent to Admin." New status **STOPPED** (read only, no buttons except Home). Admin Inbox item "Request stopped by the safety check" with the request text and reason. Audit event `safety_stop` (who, when, matched words, AI reason). Admin can **Release** (with a required note, audited) or **Keep stopped** |
| P5 | **Allowed destructive work:** the request continues only with all four in the requirement: a business reason, a named list of tables or objects (never "all"), a backup or rollback step as an acceptance criterion, and the work marked as the flag-for-review zone **"Destructive data change"** (new zone in both seeds; the senior becomes a required PR reviewer). The AI asks for any missing one as an open decision (never assumed, like security in B2 S7) |
| P6 | Fake scripts at home: the director's case, a grudge reason on a harmless request, a planned clean-up of 2 named tables with a reason |

## Part 2. Tagger reliability (W21-12, W21-15, and re-check)

| # | Piece |
|---|---|
| R1 | **Forgiving reader** `agents/da_reply_reader.py` (new, shared): take the first balanced `{...}` JSON object in the text (ignore words, code fences and a `<think>...</think>` block around it). Used by the tagger and the safety check (P2) |
| R2 | **Tagger accepts and cleans:** summary over 120, reason over 160, description over 120 are **cut** (at a word, with "...") not rejected; capability matched to the list ignoring case and spaces; confidence lower-cased; `new_name` cleaned (`&` to "and", other symbols dropped, spaces squeezed) then checked for 2 to 40 characters |
| R3 | **Why, per program:** each rejection gets one reason word (`no_json`, `bad_capability`, `bad_confidence`, `bad_new_name`, `empty_summary`, `call_failed`). The run log line counts them: "Tagger run: 101 programs, 95 tagged, 6 could not be read (no_json 4, call_failed 2)". Never the reply text |
| R4 | **One retry** per program that fails to read, with the line "Reply with the JSON object only." added to the prompt |
| R5 | **Never drop the whole run.** `MAX_SKIPPED_SHARE` is removed. Good tags are always saved. Failed programs are saved as entries with state `unreadable` and their reason, shown in the Review queue as cards "AI could not read this program" (reason, **Try again**, **Assign to**). Over 30% unreadable: the run still saves, and the job line warns in amber "Many programs could not be read: check the AI model" |
| R6 | **Honest run row (W21-15):** each row shows two results: "Index: Done, 463 pieces (Build 3)" and "Tags: 95 of 101 tagged, 6 could not be read" (green when all, amber otherwise, red when the tag step crashed, with the message). The job card's last line does the same. `record_run` keeps `tagged`, `unreadable` and the per-reason counts |
| R7 | **Try the tagger on one program:** button on the Review queue view, path picker from the index, runs one tag call (same lock), shows the raw reply (first 2,000 characters, in a code box), the reader's result and the reason. Saves nothing |
| R8 | **Re-check uses the same rules** (it calls `run_tagging`), and also re-tries `unreadable` programs |
| R9 | **Data outside the code folder (W21-12 g):** `.env.example` and `docs/` work setup: set `DA_CODE_INDEX_DIR` to a folder outside the code folder (for example `C:\Users\<you>\CodeVisionDA\data\da_code_index`) so a new ZIP keeps the index, the tags and the run history. Check the database path setting the same way and document it. At start, the app logs which index folder and database it uses (path only) |
| R10 | Fake script cases: reply wrapped in words, a `<think>` block before the JSON, a 150-character summary, `"High"`, `new_name` "Upload & Ingestion", one reply with no JSON at all (becomes `unreadable` after one retry) |

## Part 3. Refresh, progress and navigation (W21-16, W21-17, W21-22, W21-7)

| # | Piece |
|---|---|
| N1 | **One job watcher** on the Admin page: a `dcc.Interval` (2 s while a job runs, 15 s when idle) reads the job status. When a job changes to done or failed, one store `admin-data-version` is bumped; the catalog tab, the Review queue, the "Review queue (N)" count, the Capabilities list and the Overview Needs attention listen to it and redraw. Search text, filters, sort and scroll position are kept |
| N2 | **Progress everywhere:** the same progress bar component (percent, "x of y programs", time left, Stop) shows on the Index job card, the Capability catalog header and the Review queue view, for index, tagging and re-check jobs (step names: "Reading code", "Linking code", "Tagging programs", "Re-checking programs") |
| N3 | **Buttons while a job runs:** Full rebuild, Delta rebuild, Re-check, Try the tagger and Use build are **disabled** (greyed, not hidden) with the job's short status as the tooltip. The server lock stays as the second guard |
| N4 | **End line:** when a re-check ends: "Re-check done: 18 programs placed, 23 still with no fit, 0 could not be read." The text "Open this tab again when it is done." is removed |
| N5 | **Tab in the address (W21-17):** `/admin?tab=<key>&view=<key>` (keys: overview, charter, repository, catalog, ui, coding, build, history; view: capabilities, queue, map). Changing tab or view updates the address (no reload). F5, Back and a shared link open the same place. Plain `/admin` opens **Overview**. Find and fix what opens Project charter after load today (likely `open_tab` fired by a pattern-matching button drawn with a click count): no callback may change the tab on page load |
| N6 | **Request page from the Home list (W21-7):** find which lead it is (B1 F10 leads 1 and 2; say which in the plan). Rule: from the Home list, the Inbox link, a direct `?request=` address, Home then reopen, and F5, the request page always shows Home, the title, the request ID and the step bar, never the Home subtitle. Playwright test per entry path, including a request waiting on a decision (choice buttons) |

## Part 4. Build loop and Tester (W21-1, W21-2, W21-3, W21-4, W21-6)

| # | Piece |
|---|---|
| B1 | **A requirement beats a judgement rule (W21-1).** (a) The Tester prompt gets the acceptance criteria (Given, Expect) and the line: "Never flag output text that a criterion requires word for word. CV-PY-001 applies only to error paths: raise, except, logged errors." (b) Plain-code guard after the Tester: a finding whose `Where` line holds a string literal that appears in any criterion's expected text becomes **FYI** with the note "Required by AC-n" (never Must fix). Audit shows the change |
| B2 | **Stop burning rounds (W21-2).** When the same Must fix (same rule ID and same file and line, or same quoted text) comes back in the next round, the loop stops before using another round and shows: "The Tester's finding F-1 conflicts with what was built for AC-1, or cannot be fixed without breaking a test. Your call:" with **Dispute F-1**, **Change what it does** (requirement lane), **Get help**. Rounds used so far stay counted |
| B3 | **Say why it is not passing (W21-3).** The red label banner gets one reason line built from the result: tests ("2 of 19 tests fail"), Tester ("all 19 tests passed, but 2 Must fix findings are still open: Tester check 6, Judgement rules kept"), or not proven. A link "See the findings" opens the Tests tab at the findings |
| B4 | **Model short name (W21-4).** Everywhere a model is shown (Tests tab "Reviewed by", report, Audit, Admin), show the last part of the path only (`Qwen3.6-35B-A3B`). One helper `model_label()` |
| B5 | **Dispute in two steps (W21-6).** (a) **Dispute** on a finding only saves the reason ("Disputed, not sent yet", **Edit**, **Withdraw**); no escalation, no lock. (b) Under the findings: **Send N disputes to my senior** (shown when N ≥ 1) with the note "M Must fix not disputed". Sending makes **one** escalation (trigger `dispute`, all disputed findings and reasons), then the lock rule applies as today. (c) The senior answers per finding in the Inbox: **Accept dispute** or **Keep finding** (reason required). Accepted findings become FYI "Dispute accepted by <senior>", audited. When no Must fix is left open, the label is worked out again (it can become Ready for your review or Ready with warnings without a rebuild) |

## Part 5. Test report as a PDF download (W21-5, decided 21 Nov 13:36: option 1, standard library)

| # | Piece |
|---|---|
| F1 | **PDF writer** `agents/da_pdf_writer.py` (new): standard library only. PDF 1.4 text objects, built-in fonts Helvetica and Helvetica-Bold (WinAnsi), the Helvetica character widths as a table in the module (so text wrapping is exact), A4 landscape, margins 15 mm, body 9 pt, headings 12 pt. Tables with fixed column widths, cell text wrapping at word boundaries (long words broken), row height from the tallest cell, header row repeated after a page break, a row never split across pages unless taller than a page, footer "CVDA-<id> build <n> test report · Page n of m". Characters outside WinAnsi become `?` (noted in the code) |
| F2 | **Report layout** (from the saved `da_test_reports` row, as D1): header block (request ID and title, build and round, date and time SGT, models by short name, label with the B3 reason line), summary counts per layer, then **one table per section** (1. Against the requirement, 2. Against the code, 3. Safety net, Enhance only) with the same columns every time: `Test 8% · Criterion or target 22% · Input 17% · Expected 17% · Actual 17% · Match 7% · Result 12%`. One row per evidence line; a test with several checks spans several rows with the Test cell shown once. Failure message as a full-width row under the test. "Evidence not recorded" rows kept. Then the Tester's 7 checks and the findings table (ID, severity, where, message, rule). Negative scenarios keep the asterisk and legend |
| F3 | **One click:** the Tests tab's **Open report** becomes the button **Download report (PDF)**, `dcc.Download`, file `CVDA-<id>-build-<n>-test-report.pdf`. No new tab. The report page route and the HTML download are removed; the handoff PR summary names the PDF file |
| F4 | Values are cut at 500 characters and secrets shown as `[hidden]` (D1 rules) |

## Part 6. Catalog editor look and visual checks (W21-9, W21-10, W21-21, W21-11)

| # | Piece |
|---|---|
| L1 | **Browse modules... (W21-9):** the Add modules button becomes **Browse modules...** with a list icon (opens the existing pop-up). Add row becomes a small text button "+ Add capability" under the table |
| L2 | **Row actions (W21-10):** every row's actions in one fixed-width column, one line, never wrap: **↑**, **↓** (icon buttons with tooltips Move up, Move down), then **Remove** in red. First row's ↑ and last row's ↓ shown disabled. Same in the patterns panel and the capability rows |
| L3 | **Pattern box (W21-21):** placeholder built from the index (the first module's folder, for example `agent_flows/*`); help line "Paths start inside the source folder. Use / between folders. * matches anything, including sub-folders. Case does not matter."; the live match count with the first 5 matching paths shows as soon as typing starts; a pattern matching 0 modules shows "Matches nothing yet" and needs **Save anyway** |
| L4 | **Checks that fail the build (W21-11):** Playwright measures (skip when no browser) on the catalog in **edit view**, the patterns panel and the Browse modules pop-up, at 1366, 1536 and 1920 px: in every table, all action buttons of a row share one top position (no wrap, 2 px tolerance) and each action sits at the same left position in every row; inputs in one row have equal height. Screenshots of those states added to the screenshot script. If the impeccable skill is installed for the builder at home, its layout critique runs on those screenshots and its Must fixes are fixed in the same step (required, no longer optional) |

## 7. Edge rules

- No new library (the PDF writer is standard library). No new database table; new fields with
  defaults; old rows still read. STOPPED is a new status: add it to the status list and the allowed
  moves (any Understand status to STOPPED; STOPPED to the previous status only through Admin Release).
- Never log a key, a header, a prompt, code or an AI reply text (counts and reason words only).
- Fake AI at home only; `FakeLLMClient` never at work.
- Every Admin change is a new rulebook version with a plain change note; nothing silent.
- One job at a time (index, tagging, re-check, try-one share the lock).
- Words for every new label, chat line and banner come from constants.
- Never touch `main`.

## 8. Acceptance criteria (Given / When / Then)

| ID | Given / When / Then |
|---|---|
| G5-1 | Given the request "I need a program to delete all database tables" with reason "I hate my boss", when Understand starts, then no criteria are written, the chat shows the stop line, the status is STOPPED, an Admin Inbox item and a `safety_stop` audit event exist |
| G5-2 | Given a harmless request with the reason "to get back at my manager", then it stops (plain code `intent`), even when the fake AI says `ok` |
| G5-3 | Given "Delete the 2 tables TMP_LOAD_A and TMP_LOAD_B after month end, they are no longer used" with a backup step, then it continues, the zone "Destructive data change" is flagged and the senior is a required reviewer; without a backup step the AI asks for one as an open decision |
| G5-4 | Given the safety AI call fails, when plain code finds `destructive`, then the request goes to the P5 checks, never straight on |
| G5-5 | Given Admin presses Release with a note on a stopped request, then it returns to its previous status and the audit has the note |
| G5-6 | Given replies wrapped in words, with a `<think>` block, with a 150-character summary, with `"High"`, with `new_name` "Upload & Ingestion", then all five are tagged (summary cut with "...", name "Upload and Ingestion") |
| G5-7 | Given a reply with no JSON, then one retry is made; when it fails again the program is `unreadable` with reason `no_json` and shows as a card |
| G5-8 | Given 70 of 101 unreadable, then the 31 good tags are saved, the run row says "Tags: 31 of 101 tagged, 70 could not be read" in amber, and the log line counts reasons |
| G5-9 | Given a finished full rebuild, then the run row shows the Index result and the Tags result on separate lines; a crashed tag step shows red with its message |
| G5-10 | Given Try the tagger on one program, then the raw reply (max 2,000 characters), the reader result and reason show, and the tags file is unchanged |
| G5-11 | Given the catalog open while a fake re-check of 5 programs runs, then the progress bar moves on the catalog and the queue, Re-check and both rebuild buttons are disabled, and when it ends the queue and counts change without a reload and the end line shows |
| G5-12 | Given a search text and a filter in the Review queue, when a job ends, then they are kept |
| G5-13 | Given the catalog tab with the queue view open, when F5 is pressed, then the same tab and view open; `/admin` alone opens Overview; Back returns to the previous tab |
| G5-14 | Given each entry path (Home list, Inbox, direct address, Home then reopen, F5) to a request waiting on a decision, then Home, the title, the request ID and the step bar show and the Home subtitle does not |
| G5-15 | Given AC-1 "prints the exact text 'NUMERIC'" and a Tester Must fix on `print("NUMERIC")` citing CV-PY-001, then the finding becomes FYI "Required by AC-1" and the label is not Not passing for that reason |
| G5-16 | Given the same Must fix in two rounds in a row, then the loop stops before the next round and shows the three choices; rounds used are unchanged |
| G5-17 | Given a Not passing build with all tests passed and 2 open Must fix, then the banner says so in one line with the link |
| G5-18 | Given the model `/data/genai/models/Qwen3.6-35B-A3B`, then every screen and the PDF show `Qwen3.6-35B-A3B` |
| G5-19 | Given 2 Must fix, when F-1 is disputed, then nothing is sent and nothing is locked; F-2 can be disputed; Send 2 disputes makes one Inbox item with both; after the senior accepts both, the label is worked out again without a rebuild |
| G5-20 | Given a saved report, when Download report (PDF) is pressed, then one file `CVDA-<id>-build-<n>-test-report.pdf` downloads, starts with `%PDF-`, has a trailer, holds every test ID, and no new tab opens |
| G5-21 | Given a report with 40 tests, then it has more than one page, the column header repeats on each page, every page has "Page n of m", and every table on every page has the same column positions (checked from the drawing commands) |
| G5-22 | Given a 500-character value without spaces, then it wraps inside its cell and does not overflow the column |
| G5-23 | Given the catalog in edit view, the patterns panel and Browse modules at 1366, 1536 and 1920 px, then no row's actions wrap and the action columns line up (Playwright measure) |
| G5-24 | Given the pattern box at work with an index, then the placeholder is a real folder from the index, the help line shows, and typing shows the live count and 5 paths |
| G5-25 | AF-2 label scan still passes on every new screen part (no `DA_`, no raw field names) |

## 9. Work notes (for `docs/build-work-test.md` and `docs/discover-work-test.md`)

1. Before unzipping the new code: set `DA_CODE_INDEX_DIR` (and the database path) in `.env` to a
   folder outside the code folder, and copy the current `src\data\da_code_index\` there once.
2. Undo the 21 Nov test change: `MAX_SKIPPED_SHARE` no longer exists after G5.
3. Retest: the director's delete-all-tables request (must stop), CVDA-2026-0004 (Not passing reason,
   dispute both findings, senior accepts), Full rebuild (run row shows tags), Re-check (progress,
   no F5), F5 on the catalog tab, Download report (PDF).

## 10. Out of scope (Fix G6)

- W21-18 Suggest a catalog from code links, W21-20 a module in more than one capability, W21-23
  capability map clean-up.
