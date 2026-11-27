# Fix G9 plan: the requirement is the referee, and it must follow the rulebook

Spec: `specs/fix-g-9.md` v1.0. Branch `phase-g-fix-9` (cut from `origin/auto/phases-7-10` after G8).
Commit subjects "G9 step N". Built in small runs of at most 3 steps; each step has tests, a commit
and a push. Part order as the spec says: Part 1, 2, 3, 4, then 5. Edge rules of the spec apply to
every step: no new library or table (exceptions and rule-check results live in the request record
JSON and the audit), AI reply text is never shown or logged outside `logs/da_rejected_replies.log`,
labels and hints come from constants (AF-2 label scan), fake AI only. Old records still read: every
new field has a default.

## Review fixes (round 1)
- Step 8 timing is unclear in the spec (the planner runs at Approach, after Understand is confirmed):
  see "Open question for Gian" under Step 8. Steps 1 to 7 do not depend on it.
- Steps 15 and 16 now have tests. Step 1 turns the G5 gate's zone finding into `ZONE:name`
  conflicts. Step 3 says what each target replaces and has the Try again action. Step 4 names the
  routing and trigger rules. Steps 9 and 10 say safety-net tests are never touched. Step 10 adds a
  round flag. Step 17 uses `tests/da_browser.py` browser tests. Fake script entries are listed per
  step. `library_name` is reused in Step 1.

## Step 0: CLAUDE.md "Current phase" says Fix G9 in build (spec, plan, branch), G8 merged (PR #117).
Keep it under 6,000 bytes (a test checks it).

## Part 1. The requirement follows the rulebook (Understand gate)

### Step 1: plain-code conflicts and the keep-only-real filter (U3, U4, G9-4, G9-5)
- New `src/agents/da_rule_conflicts.py`: `RuleConflict` (criterion, rule, why, fix; max 200 each)
  and `plain_conflicts(record, rulebook)`: a criterion/summary text that names a blocked import
  (`policy.build_blocked_imports`) or a library off `policy.approved_libraries`; an out-of-scope
  item matched ignoring case and word order. Destructive/flag zones stay with the G5 safety gate
  (unchanged, so not repeated here).
- `keep_real_conflicts(conflicts, record, rulebook)`: keeps a conflict only when the cited rule
  exists (rule ID, `CHARTER:out_of_scope:n`, `LIB:name`, `ZONE:name`) and the criterion is
  `SUMMARY`, an existing `AC-n` or `DD-n`. Others dropped; logger gets count and kind only.
- A destructive or flag zone without its required parts: the G5 gate (`da_safety_gate`,
  `da_destructive.pending_for`) stays unchanged; its finding is shown as a `ZONE:name` conflict.
- Reuse `library_name` (already used by `da_approach_checks`) for library matching.
- Tests: G9-4 (blocked import gives a conflict with no AI call), G9-5 (unknown rule dropped,
  unknown criterion dropped, real kept), word-order and case match.

### Step 2: the rule check AI call (U1, U2)
- New prompt `src/data/da_rule_check_prompt.md` and `da_rule_check_agent.py`: builds the whole
  rulebook block (constraints, architecture principles, judgement rules ID/title/why, approved
  libraries, blocked imports, flag-for-review zone names; never seniors' names; long lists cut with
  a "(+N more)" count note like the tagger), reads the reply with the G5 forgiving reader
  (`da_reply_reader`), rejected replies go only to `da_rejected_reply_log`.
- Role `interpreter`; fake script entry in `da_understand_fake_script.json` step `rule_check`
  (empty conflicts by default; a test script returns the AC-2 / CV-PY-001 conflict).
- `da_understand_prompt.md` gets the same rulebook block (U1) via `build_prompt`.
- Failure (call or reader) returns a "could not run" result, never an empty pass.
- Tests: prompt holds each list and no senior name; cut note; reader forgiving; failure result.

### Step 3: conflicts block Confirm; the two buttons (U5, G9-1, G9-2)
- `UnderstandSession` gets `rule_conflicts: list[RuleConflict]` and `rule_check_state`
  (`"not_run" | "ok" | "failed"`, default `"not_run"`).
- When the record is complete (in `_run_gate`, once per Understand round, AI call outside the
  write lock, same pattern as `_assume`), run plain + AI checks, keep real conflicts, save them.
- `confirmation_gate_problems` lists every open conflict ("AC-2 conflicts with rule CV-PY-001 (title):
  why. Suggested wording: fix.") and "The rule check could not run: Try again" on failure.
- Buttons per conflict: **Use the suggested wording** (target `AC-n`: the criterion's `then`
  becomes the wording; `SUMMARY`: the expected behaviour; `DD-n`: that decision's choice; then the
  check runs again) and **Change it myself** (opens the field). A **Try again** action reruns a
  failed check. Constants in one place for the AF-2 scan.
- Fake script: `rule_check` step returns the AC-2 / CV-PY-001 conflict, then none after the wording
  is used.
- Tests: G9-1, G9-2; failure keeps Confirm blocked until Try again succeeds.

### Step 4: Ask for an exception (U6, G9-3 first half)
- Third button **Ask for an exception**: reason required (10+ chars); one Inbox item to the
  capability's senior (Phase 10 routing, `da_escalation_flow`), request waits at Understand.
- Routing: the capability's senior when the record has one; otherwise the Unassigned queue (same
  as other escalations). New trigger `rule_exception`: when an older rulebook has no switch for it,
  it counts as ON (never silently off). A second exception while one is open is added to the same
  open item. Inbox gets Approve and Reject actions for this kind (named constants).
- Approve records `RX-n: <rule> allowed for <criterion>, approved by <senior>, <reason>` in the
  record (new `exceptions` list, default empty), audit `rule_exception`; Reject returns it as an
  open conflict.
- Tests: send, approve, reject, short reason refused, audit row.

### Step 5: exceptions flow down (U7, G9-3 second half)
- Approach, Build and Tester prompts list the `RX-n` lines. Tester finding on an excepted rule for
  that criterion becomes FYI "Allowed by RX-n" in plain code, next to `required_by`.
- Tests: finding on CV-PY-001 for AC-2 turns into FYI; other criterion stays Must fix.

### Step 6: change requests and old requests (U8, U9, G9-6)
- "Change what it does" (v2+) runs the same check before the new version is confirmed.
- A request already past Understand is not checked; the Summary tab shows "Rule check: not run
  (older request)".
- Tests: G9-6, old record shows the line.

## Part 2. Tests come only from the requirement

### Step 7: test writer sees the criteria word for word (T1)
- `da_build_tests_prompt.md` and its builder: each case shows its criterion (ID, given, when, then,
  exact values) plus DD-n and RX-n; add the "copy exactly, never invent message text" rule.
- Tests: prompt contains the criterion text and the rule.

### Step 8: no invented cases (T2, G9-9)
- Planner reply gets `criterion` and `covered_by` per case; plain check on the criterion ID; an
  uncovered case is not planned and becomes an open requirement question at Understand (before
  confirm) or "Not covered by the requirement: <case>" (FYI) on the Tests tab (after confirm).
- **Open question for Gian (not built until answered):** the planner runs at Approach, after
  Understand is confirmed, so "an open question at Understand before confirm" cannot happen today.
  Options: (a) a coverage check during Understand (needs a second AI call, the spec allows one per
  round); (b) the question appears on the Summary tab after confirm (as T3 does); (c) reopen
  Understand. Fake script entry: planner reply with `covered_by`.
- Tests: G9-9 once decided; after confirm shows the FYI line.

### Step 9: expectation check before freezing (T3, G9-7, G9-8)
- New `da_test_expectations.py` (plain code): collect expected string literals (3rd argument of
  `evidence(...)`, expected side of `assertEqual`/`assertIn`) and check each appears, case and
  space blind, in a criterion, decision, exception or the contract.
- Failing test goes back to the writer once with the plain reason; still failing: case dropped,
  "Not covered: the test could not be written from the requirement" (FYI) and the T2 question on
  the Summary tab. The build never starts with a test failing T3.
- Applies only to the requirement test file, never to Phase 9 safety-net tests (test: untouched).
- Fake script: a writer reply with 'Error message', then the same again.
- Tests: G9-7, G9-8.

### Step 10: referee on a repeated failure (T4, T5, G9-10, G9-11)
- In `da_build_loop`: same frozen test failing in two rounds with the same actual value runs T3
  again with the current record. Not backed: one rewrite by the test writer (audit
  `test_rewritten_by_referee` with old and new expected values), Layer B runs again, round not
  counted. Backed: repair note names criterion and exact expected value. No question to the
  developer.
- A saved round gets `referee_only: bool = False`; `_rounds_used` skips it (old records read).
  Same safety-net exclusion as step 9. Fake script: a rewrite reply.
- Tests: G9-10, G9-11, cap not hit by a referee round.

## Part 3. The Builder follows the required results

### Step 11: required results list and Builder prompt rules (B1, B2, B4)
- `da_required_results.py`: from the criteria, plain code builds exact `given -> output` pairs
  (function call with literal arguments, or CLI entry with literal arguments, exit code).
- Builder prompt shows them with the "beat coding habits and every rule except RX-n" sentence and
  the "return, never raise" rule.
- Tests: pair extraction from sample criteria; prompt holds them.

### Step 12: required results check before the Tester (B3, G9-12)
- After Layer A, run each directly runnable pair once in the sandbox; a mismatch goes back as a
  repair note (criterion ID, expected, actual) and the Tester is not called that round.
- Tests: G9-12 with fake code that raises ValueError.

## Part 4. Findings must name a real problem

### Step 13: compliance check and Tester prompt (F1, F2, G9-13)
- `da_tester_review`: a finding saying complies/meets/follows/satisfies/in line with, without
  "but", "however" or "does not", is dropped as "Not a problem: the finding says the code complies".
  Prompt sentence added.
- Tests: both G9-13 examples.

### Step 14: readable cites (F3, G9-14)
- Hover and keyboard focus tooltip for `DD-n`, `RU-n`, `RX-n`, rule IDs; Check column shows the
  check's name ("Check 4 · Matches the agreement").
- Tests: tooltip text builder; layout test for focusable cite and the Check column label.

## Part 5. Screen fixes

### Step 15: hints and chip (S1, S3, G9-19, G9-20)
- Hint lines under Re-scan and Check my folder from constants; Missing backup chip to the right end
  of the catalog toolbar, label "Show: Missing backup".
- Tests: layout test for the hint constants; browser test at 1366 and 1920 px (extend
  `tests/test_da_admin_catalog_look_browser.py`).

### Step 16: See the findings and tab keeping (S2, S4, G9-15, G9-16)
- "See the findings" button with a clientside scroll-into-view; a redraw caused by a tab button
  keeps that tab open, only a step change chooses a tab.
- Tests: browser test pressing the button three times; callback test that a Dispute keeps the
  Tests tab.

### Step 17: address and menu changes (S5, S6, G9-17, G9-18)
- "Opening..." only when the Developer Assistant page is showing (pathname check); request page
  always redraws after a menu change; Admin tab clicks write the address without a page rebuild;
  Developer Assistant callbacks ignore address changes while another page shows.
- Playwright checks as in the spec, using `tests/da_browser.py` (extend
  `test_da_admin_tab_address_browser.py` and `test_da_home_again_browser.py`); callback tests are
  an extra, not a replacement.

### Step 18: AF-2 label scan and docs (G9-21)
- Label scan on every new screen part; short docs note; PR body file listing workarounds that end.

PARKED step 17 (part W26-8, G9-18 no page reload): the address is written by a callback and Dash
reloads the page. Tried `refresh="callback-nav"` and `history.pushState` (with and without a popstate
event): both leave Home on "Opening..." after Admin, Home, Start (G9-17). Cause not found; reverted.

Then full pytest, ruff, smoke check, code review (max 3 rounds), PR into `auto/phases-7-10` with
`--body-file`.

Step 8 question: ANSWERED, option (a), built as F1 below.

## Finish steps (spec `specs/fix-g-9-finish.md`, Gian chose option a)
Commit subjects "G9 finish step N" (N = the F number). Runs of at most 3 steps. **Run order: F2 first
(the spec says the review is the first step), then F1, F3, F4 to F9.** Every step has tests.

- **F2** Code review round 1 of the new cycle on PR #118 as it stands. Must fix items are fixed
  before F1 starts. Result written under "Finish review" below.
- **F1** Gap check in the same rule check call. Reuse `keep_real_conflicts` style and
  `confirmation_gate_problems`; no new module except a small gap model.
  - Reply gains `uncovered` (max 5; case 120, question 200, suggested_criterion 250 chars), read with
    the forgiving reader; fake script entry `rule_check` returns it in tests.
  - `keep_real_gaps`: drop a gap (ignoring case and word order; G9-9d also tests reordered, capitalised
    words) whose words are already in a criterion's given part, a decision, the
    out-of-scope list (charter and record, "Not needed" lines included); drops logged as a count only.
  - Gate lines "Gap: case. question"; buttons Add this criterion (next AC-n, check runs again),
    Change it myself, Not needed (reason 10+ chars, line "Not needed: case: reason", audit
    `gap_not_needed`). F1d: same gate on a v2 or later requirement. F1f: failure message
    "The rule and gap check could not run: Try again", Confirm stays blocked. Old records without
    `uncovered` read as no gaps. F1e: Approach planner case with no covering criterion is not planned
    and shows "Not covered by the requirement: <case>" on the Tests tab (FYI); old requests past
    Understand are not re-checked.
  - Tests G9-9, 9b, 9c, 9d, 9e, plus: v2 gap blocks, failure message blocks, old record loads.
- **F3** Command-line required results run in the sandbox after Layer A, as a child process of the
  entry script (60 s limit, same Job Object and clean environment as the test runner), stdout with
  trailing spaces and line ends stripped, "non-zero" = any non-zero. Mismatch goes back to the
  Builder as a repair note, Tester not called. Remove G9-a from parked-items. Test G9-12b.
- **F4** Admin tab click: clientside `replaceState`, tab kept in a `dcc.Store`, `?tab=` read on load
  and F5, "Opening..." guard keys on pathname only. Tests (Playwright): Admin, each tab, Home, Start a
  change request shows Understand within 5 s; Admin, tab, F5 keeps the tab. After 2 failed tries keep
  the current code and park as Low with the order and tries; on success remove G9-b from parked-items.
  DONE (try 1: replaceState + store; try 2: the stuck "Opening..." came from the Address-to-Tabs
  callback, removed). G9-b removed from parked-items.
- **F5** v2 refine lane shows conflicts and gaps with the same five buttons. Test: G9-6 with each
  button pressed.
  DONE (new `da_refine_rules.py`; items saved on the Refine state; keys `rc:use|change|ask|add|no:N`
  and `rc:again`; approve writes RX-n into the proposed record).
- **F6** A G5 zone finding also shows as conflict `ZONE:<name>`; G5 safety gate unchanged. Test: the
  conflict appears with buttons, and the existing G5 gate tests still pass.
  DONE (`_zone_conflicts` in `da_rule_conflicts.py`: one `ZONE:Destructive data change` conflict per
  missing item when the record is destructive; G5 gate files untouched).
- **F7** First find the cause (`_rounds_used` already skips `referee_only` rows, so look for the
  counter that is still wrong). Test: round counter unchanged after a referee-only round.
- **F8** Browser tests from the `tests/test_da_poll_browser.py` set-up: G9-15, G9-16, Inbox Approve and
  Reject (G9-3), the F1 buttons. Round-2 FYI fixes: the missing space after `=` (found at
  `COULD_NOT_RUN =` in da_rule_check_agent.py), and the stale check result.
- **F9** Full pytest in groups on one commit (each group named with its count in the PR body, every
  group passes on that same commit, a cut-off run counts as no result), ruff, smoke check. Code review
  rounds 2 and 3 if needed (cap 3, then stop and report). PR #118 body: replace "Known gaps" by what
  F1 to F8 closed and what is still parked. The chief merges PR #118, closes #119 and marks Fix G9
  done in `ops/work_queue.json`.

### Finish review
**Round 1 (27 Nov 2026): 3 Must fix, 5 Should fix/FYI.** Ran: 98 G9 tests, 126 nearby, ruff, smoke: pass.
- Must 1 `da_rule_conflicts.py:23-24`: "import daily rates" / "loan package" flagged as libraries. Fix: only
  code-like names (backticks, dotted, "the X library"); drop "package" and verb "import".
- Must 2 `da_rule_conflicts.py:150`: any AI `LIB:name` kept, rule text not cut (crash in ExceptionAsk,
  AI text in audit). Fix: keep LIB only when the library is refused by the rulebook; drop long rules.
- Must 3 `da_test_expectations.py:52` `_is_message`: one-word expected strings skip T3. Fix: check single
  words too (backed by the requirement text or contract names).
- Should: skip second AI rule check at Proceed when the fingerprint is current; `rule_exception` label in
  `da_admin_metrics.TRIGGER_WORDS`; Approve/Reject closes a row that holds other reasons.
- FYI: plain conflicts lost when the AI call fails; `allowed_by` substring; `says_complies` "no/not";
  `evidence(expected=)` keyword; missing space after `=` in da_handoff_screen:22, da_rule_check_agent:32,
  da_understand_flow:185 (F8).

