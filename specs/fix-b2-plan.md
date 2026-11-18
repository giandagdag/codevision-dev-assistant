# Fix batch B2 plan: screens and flow

Spec: `specs/fix-batch-b2.md` v1.0 (approved, all D-x option 1). Branch `phase-b2-screens` (cut from
`auto/phases-7-10`, merged 18 Nov: already up to date). PR into `auto/phases-7-10`; the chief
merges. Never main. Commit subjects say "B2 step N". Runs of at most 3 steps; each step: tests,
commit, push to `phase-b2-screens`. Tests use fakes and `tmp_path` only. No new library, no new
status. CLAUDE.md "Current phase" gets one line in step 1 (file stays under 6,000 bytes).
Pytest is run in small groups (one test file or two per call), full run once at the end.

Order note (review M1): the spec wants D1 and Phase 11 fix 3 merged first; neither is on
`auto/phases-7-10` yet. Gian's run instruction (18 Nov) was to merge `auto/phases-7-10` and build
now, and not to touch PR 98 or `phase-11-fix-3`. So we build now. Overlap risk: D1 and step 7
(B2-14) both touch Handoff; a later merge may need a small conflict fix. Reported to Gian.

Plain-words picture (AS400): the lane and cancel words are the command-key legend at the bottom of
a 5250 screen. Today the legend text is typed in many places; B2 keeps it in one table. The AI
calls (Explain, Help me decide, Let the AI describe it, assumptions) are extra function keys that
only fill a field or print a message line; the user still presses Enter.

## Steps (build order)

1. **S1 lane words + S2 Cancel look.** `agents/da_refine_lanes.py` `LANE_LABELS` become "Change what
   it does", "Change how it's built", "It's not working as agreed" (keys unchanged). Find every
   place that prints the old words (Audit, Handoff, chat, panels, tests) with Grep and make them
   read `LANE_LABELS`. Cancel keys (`cancel`, `restore_cancel`, `cancel_revision`, Cancel build and
   Cancel test excluded because they are Stop buttons) get a `variant`/class "plain grey outline"
   in the refine bar drawing, in its own row apart from the lane row. Tests: B2-1, B2-2 (component
   tree check).
2. **S6 announce the automatic check.** In the Add-this-test path (`da_refine_owntest.py`) add two
   constants and two chat lines: before ("Checking your new test against the current code...")
   and after (result). Behaviour unchanged. Test: B2-7.
3. **S7a default 8 + S7b batches of 3.** `DEFAULT_MAX_MATERIAL_DECISIONS = 8` (M2: the work seed file holds only
   charter `purpose` and `in_scope`, merged by `_with_work_purpose`; a policy key there would land in
   the charter, so it is NOT edited. The practice seed already has 8. The work run gets 8 from the
   model default because the work seed has no policy key). Fix the "default 5" docstrings and tests
   that assume 5. A work database that already stored a limit keeps it; Admin changes it (told to
   Gian). `_ask_decision` asks up to 3 pending decisions per message (numbered, answered one by
   one with the existing answer path). A new batch message goes out only when the previous batch
   is fully answered (not after every answer). Tests: B2-8 (load with `at_work=True`, policy
   limit 8), B2-9 (5 decisions: batch of 3, then 2).
4. **S7c/e limit buttons + never-assume list.** At the limit (`needs_senior` today) the screen offers
   "Proceed with these assumptions" and "Send to my senior". `Send to my senior` uses the existing
   escalation (senior inbox). Own key and constant for Proceed (the checkpoint already has a
   "Proceed"). A decision is never assumed if a broad keyword list matches (security, password,
   money, amount, payment, balance, account number, customer, personal data) OR the AI marked it
   sensitive: fails safe. After a Proceed that leaves a sensitive decision, the gate still blocks
   and the only way on is Send to my senior. Test: B2-11 (made-up customer-data decision).
5. **S7d Assumptions section.** The record already has an `assumptions` list (used in
   `_apply_result`); step 5 reads how it is shown and reuses it, no new field unless that fails. Proceed makes one AI call (fake script in demo) that
   writes one assumption per open non-sensitive decision; they are saved in the record's
   Assumptions with a fixed `basis` constant that marks them as Proceed assumptions, shown and
   editable at the checkpoint (existing edit path). The open decisions they replace (the
   `SENIOR_PREFIX` open items) are removed from `open_items`, so the gate stops blocking on them.
   The AI call returns Given, When, Then for each assumption; on Confirm only the marked ones
   become acceptance criteria (kind success, next free ID) with tests through the normal build.
   Role: the Interpreter role from Admin; the fake script gets one new entry in the Understand fake
   script. Tests: B2-10, and a failed call leaves record and status unchanged.
6. **S7f senior reopen.** New field `extra_decision_rounds: int = 0` on `UnderstandSession` (it is
   saved as JSON in the session row, so the stale check R7 covers it and old rows still read; no
   new SQL column). `_decision_limit` = policy limit + extra rounds. Senior reopen action in the
   inbox: picks 1 to 5 more rounds (D-C; 0 and 6 refused), audited `decision_limit_raised`. It
   reuses the existing `close_escalation(..., "returned")` path (no new outcome or status), clears
   `needs_senior`, and moves the `SENIOR_PREFIX` open items back into the pending decisions up to
   the new limit, so the next decision is really asked. Test: B2-12 (8 + 3 = 11 for that request
   only, and the next decision is asked), plus bounds tests.
7. **S8 No negative scenario applies.** Record gets `no_negative_reason: str = ""` (default, max 200;
   old rows read). Gate rule in `confirmation_gate_problems`: failure kind needed unless a reason
   is set; the interpreter reply's existing `hint` carries the suggestion when there are no inputs
   (no new reply field; `no_negative_reason` stays out of `INTERPRETER_FIELDS`, so only he sets
   it; fake script too); UI
   option with a one-line field. Reason goes to Audit (`no_negative_reason_set`) and the Handoff
   PR summary. Tests: B2-13, B2-14.
8. **S5 lock buttons while waiting.** One helper in the page layout returns `disabled=True` for every
   action button when the request is waiting on the AI, except a constant allow list (Cancel
   build, Cancel test, Home). Server check (M3: there is no saved busy flag today; "busy" is only
   Dash `running=` and `da_busy_text.py`). Decision: a small in-memory lock per request id
   (`agents/da_ai_lock.py`, `try_start(request_id)` / `finish`, with a time limit of 10 minutes so a
   stuck entry clears). In memory is enough for the one-process laptop and the current work
   setup; if CodeVision runs several worker processes later, move it to a table (listed in
   `specs/parked-items.md`). Every AI-calling action takes it first and refuses with a plain
   message when taken: the existing Understand, Approach, Build, Refine actions, plus steps 5, 9,
   10 of this plan (the lock test is extended in those steps). Tests: B2-6 (tree check, a forced
   second call refused, a stuck entry clears after the limit).
9. **S3 Explain simply + Help me decide.** Two buttons at lane choice and in Get help (D-B). Each
   is one AI call (roles from Admin; fake script), audited (`explain_simple`, `lane_decide_help`).
   Explain: max 120 words, in chat, nothing else changes. Decide: sets `suggested_lane`
   and reason; that lane's button gets a "Suggested" tag; no lane starts. Failure says so and
   changes nothing. Role: the existing lane role (`LANE_ROLE`); fake script: new entries in the
   build fake script that `get_build_client` serves. Tests: B2-3, B2-4, a failed call for each
   (nothing changes), buttons added to the step 8 lock test.
10. **S4 Let the AI describe it.** Button above the bug text box. One AI call using the failing tests
    and the last chat lines; the draft goes into the box (returned as the box value, never sent).
    Role: the existing repro role; fake script entry beside it. A failed call says so and
    leaves the box as it was. Tests: B2-5, the failed call, and the lock test (step 8) extended.
11. **S9 full-width layout.** Page container full width on large screens, three Home cards equal
    height, extra width to the right panel, chat line max-width about 80ch. Test on the component
    tree (B2-15); Gian does the visual check at 1366 and 1920 px.
12. **Wrap-up.** Docs line in `docs/`, smoke check item if cheap, full pytest, ruff, smoke check.
    Then code review (max 3 rounds) and the PR.

(12 steps: four runs of 3. After each run set the next step with `ops/chief_tick.py next`.)

## Plan review result (18 Nov)

Round 1: 4 Must fix, all fixed above. Round 2: APPROVED, 0 Must fix. Should fix items taken in:
- Step 4: "sensitive" mark = keyword list only (the AI-mark idea is dropped: `Ambiguity` has no field).
- Step 5 and 6: use `SENIOR_PREFIX` from `agents/da_understand_flow.py` ("Needs a senior decision: "),
  not the one in `da_senior_actions.py`.
- Step 6: when a decision is moved aside, keep its options in a small list on the session; reopen
  restores them and raises `material_decisions_asked` per item. Update the session first, then
  `close_escalation` (so a failure never leaves "returned" but stuck). Tests for both.
- Step 8: the lock is released in a `finally`; test with an AI call that raises.

## Risks

- Step 5 (assumptions to criteria) touches the record and the build; keep it in small commits.
- Step 8 depends on how "waiting" is stored today; read first, then decide, and say so.
- Step 1 may find old lane words in test files; they change with the constants.
