# Fix G7 plan: Approach tells the truth, forgives long text, knows the standard library

Spec: `specs/fix-g-7.md` (approved). Branch `phase-g-fix-7` from `origin/auto/phases-7-10` (G6 merged;
the spec file is already on that base, identical, so no separate spec commit was needed).
Commit subjects "G7 step N". Runs of at most 3 steps; push after each step.

## Steps (each with tests; "check" = how to prove it)

0. **Housekeeping.** "Current phase" in CLAUDE.md names Fix G7 (file stays under 6,000 bytes; the
   size test checks it). Commit this plan.
1. **Standard library with dots (S1, S2, S3) + shared problem kinds (R5).**
   - `da_approach_checks._library_problems`: compare the part of `library_name(name)` before the
     first dot.
   - S2: `da_build_checks.py` (~310, ~493) and `da_safety_net_checks.py` (~128) already use the
     top-level part (`top`); add a test that `xml.etree.ElementTree` passes the approved-list check.
   - New `agents/da_problem_kinds.py::problem_kinds(problems) -> str` ("1 problem (library)"), kinds
     json/shape/too_long/library/folder/protected/file_name/reuse/design/other, used in the 5 "not
     usable" log lines (Approach, Tester, Build, Discover, Understand).
   - S3 sentence in `data/da_approach_prompt.md`.
   - Check: G7-6, G7-7, G7-11 (log text holds kinds, never reply text).
2. **Say the real reason (R1 to R4) + problems on the Approach tab.**
   - `ApproachResult.kind` (`ok`/`unreachable`/`rejected`). `generate_approach` sets it. A rejected
     result gets `message` from `rejected_message(problems)`: header, up to 3 problems, "...and N
     more (see the Approach tab)", library hint (R4), "Press Try again, or change the request."
     Shape errors mapped to plain words (R3), no raw field paths.
   - To make "(see the Approach tab)" true: the failed-call audit event keeps all the problems (the
     check sentences, never reply text; capped at 12 sentences of 300 characters) instead of
     `[:5]`, and the failure note on the Approach tab lists them from the saved audit, not the log
     file.
   - `da_approach_flow.py`: `NOT_REACHABLE` only for `unreachable` (`_failure_text_plain`, line
     ~829, line ~735 wording " Nothing was saved. Please try again." checked so it does not repeat
     "Try again"). The Refine lanes reuse `_failure_text`; one test covers them.
   - Check sentences that quote the AI's own question text (da_approach_checks ~240) are shortened
     to a number ("design question 2") so no AI text is echoed.
   - Check: G7-1, G7-2, AF-2 label scan.
3a. **Forgive long text: models and cut (L1, L2, L6, L7).**
   - `DesignChoice.options` become `ApproachOption {label<=60, detail<=300}`; a before-validator
     reads a plain string (label made from it, L2) so old saved rows and replies still read (L7).
     `full_text: dict[str, str]` (default empty, uncut text up to 1,000) is declared on
     `ApproachReply` (summary, purpose by file index, reason) and on `DesignChoice` (question,
     impact, option details), because `_Shape` forbids extra fields and `ApproachState.pending_choices`
     saves `DesignChoice`.
   - New `agents/da_approach_cut.py::cut_reply(data)` runs before `model_validate` in `parse_reply`:
     cuts summary, purpose, reason, question, impact, label, detail at a word boundary to its limit
     with "…", fills `full_text`, keeps labels unique inside one question (a clash gets " (2)").
     Length is never a rejection reason; count limits and library names over 50 stay checks (G7-8).
   - `_reply_texts` (`da_approach_checks.py:274`) scans label, detail and the full text for code.
   - Check: G7-3 (model part), G7-5, G7-8, G7-13, old-row test, code-in-option test.
3b. **Decisions keep the full detail (L4).**
   - `da_approach_flow.py`: `_screen_for` keeps `(key, label)` and the detail is looked up from
     the pending choice; `choose_option` matches by label, then by detail; the saved
     `ApproachDecision.choice`, the chat line and the audit hold the detail. Understand is not
     touched.
   - Check: G7-4.
4. **Hover and prompt (L3, L5).**
   - The Approach layout (`da_approach_panel.py`) wraps option buttons in `dmc.Tooltip` (detail),
     opens also on keyboard focus; cut lines (summary, purpose, question, impact) get a tooltip
     with the full text from `full_text`.
   - Prompt lists the limits and its JSON example and `da_approach_fake_script.json` use
     `{"label","detail"}`; one extra plain-string fake reply for L1/L7. The retry note adds "Keep
     option labels under 60 characters" when a cut happened (L5).
   - Check: layout tests, prompt test, G7-12 Playwright (skipped with no browser) and screenshots.
5. **Search again and index lines (D1, D2, D3).** **Gated, see the open question below.**
   - D3 (Admin Index health amber line when search provider is not `codevision`): built, G7-10.
   - D2/D1 reuse `no_index_at_work`, `IndexNotBuiltError` and `SEARCH_AGAIN_OPTION`. The offer
     shows only when the last result's limitations hold the "No CodeVision index is connected" /
     "needs building" text AND the index is available now (provider `codevision` and
     `current_build()` set). The Approach failure message shows it on the same condition.
6. **Finish:** docs (`docs/build-work-test.md` work notes), full pytest, ruff, smoke check,
   screenshots, code review (max 3 rounds), PR into `auto/phases-7-10`.

## Open question for Gian (step 5, D1 only; steps 0 to 4 do not depend on it)

Gian's case is a request in DISCOVERY_CONFIRMED whose Approach failed. A new Discover round from
there hits three locks in the code: (a) the status table has no DISCOVERY_CONFIRMED to SEARCHING
move; (b) `da_discovery_results` has primary key (request_id, round), so a second "round 1" cannot
be stored; (c) the cap `discovery_max_rounds` counts rounds. The plan's proposal, unless Gian says
otherwise: allow DISCOVERY_CONFIRMED to SEARCHING only while no approach version exists; the new
round gets the next number (old rounds stay, so "stay in the audit" holds); a Search-again round
started this way does not count against the cap; Approach state is cleared with the usual restart.
Until answered, step 5 builds D3 only and D1/D2 are written down but not built.

## Edge rules kept
No new library, table or setting. AI reply text never shown or logged outside
`logs/da_rejected_replies.log`. Labels and hints are constants. Fake AI only.
