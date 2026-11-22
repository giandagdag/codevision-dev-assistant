# Fix G5 plan: work test 21 Nov (spec `specs/fix-g-5.md`)

Branch `phase-g-fix-5` from `origin/auto/phases-7-10`; PR into it (`--body-file`). Commit subjects
"G5 step N". No new library, no new table. `ops/work_queue.json` is not touched. Part 1 first
(Critical), then 2 to 6. Each part ends with green tests. At most 3 steps per run.

## Cause / code facts (read 21 Nov)
- Statuses live in `pydantic_classes/da_models.py` (`STATUSES`, `ALLOWED_MOVES`, `check_status_move`).
  ESCALATION_REQUIRED already returns to the stored previous status; STOPPED copies that idea.
- Understand turns run in `agents/da_understand_flow.py` (`open_new_request`, `submit_form`,
  `_turn`, `_apply_result`, `_ask_decision`). The new check runs before the first interpreter call
  of a new request, so no criteria exist when it stops.
- Zones are path based (`da_approach_checks.py` ~l.293 to 333, from `policy.flag_review_zones`).
  "Destructive data change" is not about paths, so the zone is added to the plan's zone list when the
  request record carries the destructive flag (new optional field with a default), and the zone
  entry is added to both seeds so the senior is a required reviewer.
- There is no Admin Inbox: `da_inbox_page.py` is the senior Inbox (one open escalation per request).
  **Decision:** the "Request stopped by the safety check" item is a new line in Admin Overview
  "Needs attention" (`da_admin_overview.py`), behind `is_admin`; it opens a panel with the request
  text, reason, **Release** (note required) and **Keep stopped**. No escalation row, status stays
  STOPPED. Audit uses `add_admin_event` and the request audit.
- Hook: `submit_form`, before `_interpret`, outside the write transaction (the AI call must not
  hold the lock), using the opening statement plus answers; tested for the new-request and Enhance forms.
- Release stores a "released" mark in the stop event details; the gate skips a released request.
  Test: Release, submit again, request continues.
- Destructive open decisions are never assumed: add them to `NEVER_ASSUME_WORDS`
  (`da_understand_checks.py`); test that "Proceed with these assumptions" leaves them to a senior.
- Zone: seed entries in `da_rulebook_seed.json` and `da_rulebook_seed_work.json` carry a placeholder
  pattern (`path_patterns` needs one); a constant fallback zone covers pinned rulebooks without it.
- `da_reply_reader.py` reuses `strip_think_block` and the fence pattern from `da_understand_agent.py`.
- STOPPED is added to the status groups in `da_developer_assistant_page_callbacks.py` and
  `da_inbox_page_callbacks.py`.

## Design (reuse what exists)
- `agents/da_safety_gate.py`: word lists as constants, `scan(text) -> GateScan(kind, words)`.
  `kind` is none / destructive / intent / both. Pure functions, no AI.
- `agents/da_reply_reader.py` (part 2 R1, but written in step 2 because P2 needs it): `read_json_object(text)`
  returns the first balanced `{...}` dict or None, ignoring fences and `<think>` blocks.
- AI check `check_request(settings, text, answers) -> SafetyVerdict(verdict, reason, ai_failed)`
  using the "Understand" role client and `data/da_safety_prompt.md`. The decision function
  `decide(scan, verdict) -> "stop" | "needs_p5" | "go"` is plain code (P3 table, own tests).
- STOPPED: new status, `ALLOWED_MOVES`: every Understand status to STOPPED; STOPPED to the stored
  previous status only through Admin Release (same guard as escalation return). Stored previous
  status goes in the stop event's details (no new column).
- Stop screen: read-only, only Home. Chat line, Inbox title and audit words are constants.
- P5: new optional record fields `destructive` (bool) and the four required items are checked by one
  plain function over the record; each missing item becomes an open decision (like B2 S7 security).

## Decisions
- Part 6 L4 uses the impeccable skill only when it is installed; if not, say so in the PR body.
- Part 3 N6: the lead (B1 F10 lead 1 or 2) is found by reproducing in Playwright first; the plan
  note is updated with the answer before the fix.
- Work notes go to `docs/build-work-test.md` and `docs/discover-work-test.md` (spec section 9).

## Later-part rules (from plan review)
- Each later step names its test file in its commit; steps 7, 8, 11, 12, 13 are built as sub-steps
  (a, b, ...) at about one concern each: 7a run rows, 7b Try the tagger, 7c re-check + env docs + start
  log + work notes in `docs/`; 8a watcher and version store, 8b progress bar, 8c disabled buttons;
  11a save/edit/withdraw dispute (new optional fields with defaults on the finding record), 11b send one
  escalation, 11c senior answers per finding and the label worked out again; 12a PDF writer, 12b layout,
  12c download, removal of `da_test_report_page.py` route and HTML download, handoff summary names the
  PDF (test); 13a catalog look, 13b Playwright measures and screenshots.
- N6: step 9a is reproduce in Playwright, write the lead into this plan, commit. If it cannot be
  reproduced, park it and tell Gian, never guess. Close P24 when fixed.
- N5: find the cause first and name it in the commit; test that no `open_tab` output fires on first load.

## Steps
0. **Current phase** in `CLAUDE.md` set to Fix G5 (keep under 6,000 bytes).
1. **P1, P4 status part** (G5-1 base): `da_safety_gate.py` plus STOPPED in the status list and moves,
   with tests (`test_da_safety_gate.py`, `test_da_models.py`).
2. **R1, P2, P3** (G5-2, G5-4): `da_reply_reader.py`, `da_safety_prompt.md`, `check_request`, `decide`,
   with fake-provider replies and a failing-call case.
3. **P4 flow** (G5-1, G5-2): hook in `submit_form` before `_interpret`; stop line, STOPPED status,
   `safety_stop` audit event; read-only screen (session step and input mode `stopped`).
   BUILT. The Admin Overview line moved to step 4 so step 3 stays one concern.
4. **P4 Admin side** (G5-1 Inbox part, G5-5): Overview "Needs attention" line (the "Admin Inbox
   item"; Gian to confirm in the PR), stopped-request panel, Release (note required, writes
   `safety_released`, moves back to the stored status and step), Keep stopped; all audited.
   BUILT (step 4): `da_safety_release.py`, line and panel in Admin Overview, tests in
   `test_da_safety_release.py`.
5. **P5, P6** (G5-3): destructive flag, four-item check as open decisions, zone in both seeds, senior
   required reviewer, fake scripts for the three cases.
   BUILT. The zone is in `da_rulebook_seed.json` and in `_default_zones` (the work seed has no
   policy block, so it takes the defaults). Gaps go to a senior as open items (`da_destructive.py`).
6. **Part 2 R2 to R5, R10** (G5-6 to G5-8): tagger accepts and cleans, reasons, one retry, no
   `MAX_SKIPPED_SHARE`, `unreadable` entries and cards.
   BUILT. Left for step 7: the card buttons "Try again" and the amber run-row colour (the text
   "Tags: N of M tagged, K could not be read" is already in the run row message). A new capability
   name that looks like a path (`/`, `\`, `.`, `:`) is still refused (`bad_new_name`).
7. **R6 to R9** (G5-9, G5-10): run rows, Try the tagger, re-check, env docs and start log.
   BUILT (7a, 7b, 7c). `.env.example` was not edited (the safety hook blocks that file name); the
   `DA_CODE_INDEX_DIR` and `DA_DB_PATH` setup is in `docs/discover-work-test.md` instead.
8. **Part 3 N1 to N4** (G5-11, G5-12): job watcher, version store, progress bar, disabled buttons.
   BUILT (8a, 8b, 8c). `da_admin_watch.py` (store `admin-data-version` = {n, running}; n goes up when
   a job ends), `da_admin_job_bar.py` (one bar, Stop, `locked()` wrapper with tooltip), N4 end line in
   the job status file. The Review queue "Try the tagger" panel is now a closed `Details` block: it
   pushed the G4 browser test (8 cards at 1920 x 1080) to 7 cards. Not done: the full `pytest` run did
   not finish in the time limit (it ran over 45 min); targeted runs (admin, g4, g5, index: 626 passed
   plus browser tests) pass.
9. **N5, N6** (G5-13, G5-14): tab address, request page header per entry path.
   9a N6 DONE. Reproduced in Playwright (slow server): it is neither F10 lead 1 nor 2. The old page
   (Home, with its subtitle) stays on screen until the slow `show_page` answers. The four entry paths
   (direct, Home list, Home then reopen, F5) pass on a fast server. Fix: a clientside callback puts
   "Opening..." into the page at once when the address changes. Tests: `test_da_request_header_browser.py`.
   The Inbox link is a plain address, so it is the "direct address" path. P24 can close.
   9b N5 DONE (`da_admin_address.py`; tests `test_da_admin_address.py`, `test_da_admin_tab_address_browser.py`).
   Plain `/admin` loaded in Playwright stayed on Overview after 4 s, so the "Project charter after
   load" shift did not reproduce at home; the `open_tab` guard (no click, no change) is kept and no
   callback changes the tab on load. Needs a work check. Page opens the tab from the address; two
   browser callbacks keep address and tabs in step. The Map view has its own page, so it has no `view` key.
10. **Part 4 B1 to B4** (G5-15 to G5-18).
    BUILT. B1 prompt + guard (`required_by`, FYI "Required by AC-n" in the saved review). B2
    `repeated_must_fix` + `stop_text`; the build ends Not passing with the B2 line and audit event
    `tester_repeat_stop`; the Dispute, Change and Get help buttons are the ones the Tests tab and
    Refine already have. B3 `reason_line` + link `#da-tester-findings`. B4 `model_label()` in
    `da_model_label.py`: Tests tab, report page and the audit event. Admin shows model names only
    as editable config fields, so they are left as typed. The fake provider's repeat Must fix
    appears in round 3 (not 2), so the loop test checks the stop, not an earlier round.
11. **B5** (G5-19): dispute in two steps.
    BUILT (11a, 11b, 11c). No new fields: the finding actions table is append-only, so Edit = a new
    `disputed` action, Withdraw = `withdrawn`, Send = `dispute_sent` per finding plus one escalation
    `Disputed Must fix: F-1, F-2`, senior Keep = `dispute_kept` (state `kept`). Accept dispute is the
    old overrule (button renamed). Save/withdraw audit as `dispute_saved`/`dispute_withdrawn`;
    `finding_disputed` is written only at Send so the health numbers stay right. Not done: a
    Playwright check of the buttons; the full `pytest` run (targeted runs pass).
12. **Part 5 F1 to F4** (G5-20 to G5-22): PDF writer, layout, download.
13a. BUILT (L1, L2, L3; tests in `test_da_admin_catalog_panels.py`). "Browse modules..." button and pop-up
    title, "+ Add capability", arrow icon buttons with tooltips (ends disabled), Remove red, one nowrap
    group; pattern box placeholder from the index, help line, hint with first 5 paths, zero match
    refused until "Save anyway". 13b (L4 Playwright measures, screenshots, G5-25 label scan) is next.
13. **Part 6 L1 to L4** (G5-23, G5-24): catalog look, Playwright measures, screenshots, G5-25 label scan.
