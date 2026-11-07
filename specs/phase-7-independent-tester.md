# Phase 7: Independent Tester (Layer C, report, labels)

Status: APPROVED v1.0 (7 Nov 2026). Written by the spec writer, the decision rule
(`specs/phase-a-automation.md` section 6) applied by the chief, then Gian approved all of D-A to D-J
as chosen (7 Nov). The two work facts (section 16) stay open as issues #20 (Q9) and #21 (Q7).
Depends on: Phase 6 (Layers A and B, the build state, the Tests tab), merged into `main`.
Next: Phase 8, Refine (3 lanes, edit protection).
Source of truth: `specs/redesign-2026-10-31.md` sections 5.4, 5.5 and 6. Facts:
`specs/phase-7-facts.md`. Status names come from the redesign status table (section 3).
Visual reference: `docs/CodeVision_Developer_Assistant_Demo.html`. Read only the Tests tab and the
Layer C box of `tabBuild`. Ignore the Refine and Handoff parts (Phases 8 and 10).
Build: worker team, branch `auto/phase-7`, merged into `auto/phases-7-10` by the chief.

## In plain words

After Phase 6 the app writes the code, runs the frozen tests, and labels a passing build "Ready with
warnings" because the third check, the independent Tester's review, does not exist yet. Phase 7
builds that third check, **Layer C**:

1. It runs only after Layers A and B pass in a round.
2. **Four checks are plain Python** (no AI): every criterion has a test, every criterion's tests
   pass, the files match the file plan, and which flag-for-review zones were touched.
3. **Three checks are one AI call** to the Tester: were the approach decisions followed, was
   anything extra built, are the rulebook's judgement rules kept.
4. Every AI finding must point at a file, a line, and a criterion or rule. **Plain code throws away
   any finding that has no real evidence.**
5. A **Must fix** goes back to the Generator and uses a round of the same shared budget of 3.
   A **Should fix** goes to the developer: he accepts it with a reason (fixing it is Phase 8).
   An **FYI** is just shown.
6. Then the label: **Ready for your review** (green), **Ready with warnings** (yellow), **Not
   passing** (red) or **Unable to assess**. Never "Approved". The Phase 6 fixed warning "The
   independent Tester review (Layer C) is not built yet." is removed.
7. The report lives on the **Tests tab** only. Nothing about it goes into the code files or the
   developer's folder.

AS400 comparisons:
- Layers A and B are the compile and the unit test run. Layer C is the **peer code review before
  promotion to the QA library**: a second programmer reads the source member against the change
  request and the shop standards. He did not write it and was not in the design meeting chat.
- "Every finding cites file and line" is the reviewer's rule "write the member name and the
  sequence number on the review sheet, or the comment does not count".
- Must fix is a **hold on the promotion**; Should fix is a review comment the programmer may answer
  in writing; FYI is a margin note.
- The label is the promotion form's status box. It never says "Approved": only the human signs.

## Words used in this spec

| Word | Meaning |
|---|---|
| Layer C | The Independent Tester review: 4 plain-code checks and 3 AI checks, after Layers A and B pass |
| Review | One run of Layer C for one round of one build. A build may have several (one per round that reaches Layer C) |
| Finding | One problem the review found: severity, check number, file, line, quoted text, what it cites, one plain sentence |
| Evidence | The file, line, quoted text and cited criterion or rule of a finding. Plain code checks it (section 6) |
| Must fix | A finding that blocks a green or yellow label. Goes to the Generator, uses a round. Cannot be accepted away; the only way past is Dispute |
| Should fix | A finding the developer must answer: fix (Phase 8) or accept with a reason. Open Should fix makes the label yellow |
| FYI | A note. Never changes the label |
| Dispute | The developer says a Must fix is wrong. Goes to a senior (escalation) |
| Unable to assess | The Tester's reply could not be used, twice in a row, for one review |
| Line-numbered code | The code text sent to the Tester with its line number in front of every line, so it can cite lines |

## 1. Decisions already made (do not reopen)

| # | Decision | Source |
|---|---|---|
| 1 | Layer C runs only after Layers A and B pass | Redesign 5.5 |
| 2 | Checks 1, 2, 3 and 7 are plain code; checks 4, 5 and 6 are AI | Redesign 5.5 (C1) |
| 3 | The Tester sees record, approach, test plan, code and test results. **Never the Generator's chat** | Redesign 5.5, facts |
| 4 | Every finding cites file and line plus a criterion or rule; the app rejects findings without evidence | Redesign 5.5 |
| 5 | Labels: Ready for your review, Ready with warnings, Not passing, Unable to assess. Never "Approved" | Redesign 5.5 (C3), Phase 6 section 8 |
| 6 | One shared budget of 3 rounds covers test failures **and** Tester Must fix | Redesign 5.4 (B3, C2) |
| 7 | Must fix cannot be accepted away; Should fix: "Fix it" or "Accept, with reason" (audited, shown at handoff) | Redesign 5.5 |
| 8 | The report lives in the app only (Tests tab), never in the workspace | Redesign 5.5 (C4), Q11 |
| 9 | Tests run only in the server sandbox; test files never go to the folder or Bitbucket | Q11 (3 Nov) |
| 10 | The Tester's model is a setting (`DA_CLAUDE_TESTER_MODEL`, `DA_ONPREM_TESTER_MODEL`; empty = the generator's model). Never hard-coded | Phase 4, facts Q9 |
| 11 | Developer-facing instructions use Command Prompt only (PowerShell and DevTools are blocked at work) | Facts |
| 12 | Phase 7 removes the Phase 6 fixed warning about Layer C | Facts, Phase 6 D-F |

## 2. The flow

Phase 6 steps stay. Phase 7 adds one step and changes where `b_done` is reached.

| Step | Where | The developer sees | Then |
|---|---|---|---|
| `b_running` | Layers A and B of a round | as Phase 6 | Pass: `b_tester_review`. Fail: Phase 6 rules |
| `b_tester_review` (new) | status TESTER_REVIEW | Build tab progress line "Layer C: the independent Tester is reviewing the code." Chat: "Tests pass. The independent Tester is now reviewing the code." Button **Stop build** | Plain checks, then the AI call (section 4) |
| `b_round_failed` | Layer C found a Must fix, budget left | Red banner: "Round 1: the Tester found 1 Must fix. Fixing only `<file>`." | Next round starts by itself (section 7) |
| `b_interrupted` | the Tester AI did not answer, or the input is too big (section 4) | Phase 6 message, adjusted: "The Tester review paused: the AI did not answer." Buttons **Try again**, **Stop build**, **Get help** | Try again resumes at Layer C. No round used |
| `b_done` | Layer C finished, or the budget is used up | Result banner with the Phase 7 label (section 8) | The Phase 6 write (unchanged) |

Rules:
- T1: Layer C runs at most once per round, and only when Layers A and B passed in that round.
- T2: Every Layer C action follows the Phase 6 pattern (B3): read with no lock, do the AI call
  outside any transaction, then ONE write transaction saves review, findings, state, audit events
  and chat lines. The build revision is used for the stale check.
- T3: **Stop build** during `b_tester_review` works as Phase 6 B5: no label, nothing written,
  back to READY_TO_BUILD.
- T4: A server restart during `b_tester_review` sets `b_interrupted` (Phase 6 section 10);
  Try again repeats the whole review of that round (the plain checks are cheap, the AI call is
  repeated). No round used.
- T5: The write still happens only at `b_done` (D-H), through the Phase 5 write job, code files only.

## 3. Statuses

TESTER_REVIEW is now used (it was unused in Phase 6, D-L). TESTING stays unused. New moves (add to
`ALLOWED_MOVES`, every move audited as today):

- BUILDING to TESTER_REVIEW (Layers A and B passed)
- TESTER_REVIEW to BUILDING (Must fix found, budget left)
- TESTER_REVIEW to READY_FOR_REVIEW (green, yellow, or Unable to assess, D-D)
- TESTER_REVIEW to NOT_PASSING (Must fix found, budget used up; or check 1 failed, section 5)
- TESTER_REVIEW to READY_TO_BUILD (Stop build)
- TESTER_REVIEW to ESCALATION_REQUIRED (Get help from `b_interrupted`)
- READY_FOR_REVIEW to TESTER_REVIEW (**Run the Tester review again**, only when the label is Unable
  to assess, D-D)
- READY_FOR_REVIEW and NOT_PASSING to ESCALATION_REQUIRED already exist (Phase 6); reused by Dispute
  (D-F)

The Phase 6 move BUILDING to READY_FOR_REVIEW is no longer used (every pass goes through
TESTER_REVIEW). Keep it in `ALLOWED_MOVES` only if removing it breaks a saved request; the plan
decides and says why.

## 4. What the Tester gets, and what it never gets

**Sent (one AI call per review, D-B):**
- the charter slice and the rulebook's active `judgement` rules (ID and text),
- the confirmed request record (the version the approach was built on), with the criterion IDs,
- the accepted approach: file plan (path, `create` or `modify`, purpose), reuse decisions, design
  decisions (question and the developer's choice), libraries,
- the accepted test plan (case ID, criterion ID, given, expect, "Yours" tag),
- this round's Layer B results per test (test name, case ID, criterion ID, pass or fail),
- this round's code, **line-numbered**, one block per planned code file. For a `modify` file, the
  current version only (not a diff).

**Never sent:** the Generator's chat or prompts, the developer chat, earlier rounds' failure
reports, earlier reviews' findings (each review is fresh, D-I), the frozen test file text (checks 1
and 2 are plain code), files outside the plan, anything from `.env`.

**Size guard (Q7 is a work fact, section 16):** plain code measures the prompt before the call.
- Over `tester_max_prompt_chars`, or an HTTP 400 reply ("too much context" at work): the review is
  **split into one call per planned code file** (D-C). Each call gets everything above, but only
  that one file's code. Findings from all calls are merged.
- If one file's call is still too big, or returns HTTP 400: `b_interrupted` with "This change is
  too big for the Tester to review in one go." and Get help. No round used.
- The split is recorded on the review (`calls` count), so the work test can see how often it
  happens.

**Reply (JSON, `TesterReviewReply`):** a list of findings, each with `check` (4, 5 or 6),
`severity` (`must_fix`, `should_fix`, `fyi`), `file`, `line`, `quote` (the exact code text it
means, one line, up to 200 characters), `cites` (section 6), `message` (one plain sentence, up to
300 characters). An empty list is a valid reply ("no findings").

**Unusable reply:** not valid JSON, or not the schema, or a severity or check outside the lists.
One more call with the problems listed (`tester_max_attempts`, 2). Still unusable: label **Unable to
assess** (D-D). Findings that fail the evidence rule do **not** make a reply unusable; they are
dropped one by one (section 6).

## 5. The seven checks

| # | Check | How | Result if it fails |
|---|---|---|---|
| 1 | Every criterion has a test | Plain code: every criterion ID in the record has at least one method in the frozen test file whose name carries that ID (Phase 6 naming rule) | **Must fix**, marked "Not fixable by the Generator" (it may not touch tests). No round is used: the build ends NOT_PASSING with "Criterion AC-3 has no test. Change the approach or get help." |
| 2 | Every criterion's tests pass | Plain code: this round's Layer B results, grouped by criterion ID | Must fix. Only a guard: Layer C runs after Layer B passed, so a failure here means the saved results do not match; the plan logs it as an app error |
| 3 | Files match the file plan | Plain code: the build's code files equal the planned code files, no missing, no extra. A `modify` file whose text is identical to its starting text | Missing or extra file: **Must fix**. Unchanged `modify` file: **Should fix** ("The plan said to change `<path>`, but it was not changed.") |
| 4 | Approach decisions followed | AI | Findings as the AI gives them (D-J) |
| 5 | Nothing extra built (scope creep) | AI | Findings as the AI gives them (D-J) |
| 6 | Judgement rules from the rulebook | AI | Findings as the AI gives them (D-J) |
| 7 | Flag-for-review zones touched | Plain code: the Phase 4 zone matcher on the planned paths (same as Phase 6 `zones_touched`) | Not a finding. Each zone touched is a **zone warning** line: "Touches the Login zone: the named senior will be a required reviewer." Makes the label yellow. Never blocks |

Plain-code findings (checks 1 to 3) carry evidence made by plain code (file and line 1, or the
criterion ID), so they always pass the evidence rule.

The Tests tab shows all 7 checks as rows: Passed, Failed (with the finding count), Warning (check 7),
or Not run (for example checks 4 to 6 when the label is Unable to assess).

## 6. Findings and the evidence rule (D-E)

The app numbers findings F-1, F-2... per review. Plain code checks every AI finding; a finding that
fails any line below is **dropped**, saved as `rejected` with the reason, audited, and counted.

| Rule | Check |
|---|---|
| E1 File | `file` is one of this round's planned code files |
| E2 Line | `line` is between 1 and the file's line count |
| E3 Quote | `quote`, with spaces trimmed, appears in that file within `tester_quote_window` lines (2) of `line`. If found on a nearby line, the line is corrected to that line |
| E4 Cites | `cites` is allowed for the check (table below) and exists |
| E5 Text | `message` is not empty and is at most 300 characters |

| Check | Allowed `cites` |
|---|---|
| 4 Approach decisions | a design decision of the accepted approach, as `DD-<n>` (its order in the approach), or a reuse decision as `RU-<n>` |
| 5 Scope creep | a planned file as `PLAN:<path>` (the file's planned purpose) or a criterion `AC-<n>` it goes beyond |
| 6 Judgement rules | an active judgement rule ID, for example `CV-PY-003` |

The `DD-<n>` and `RU-<n>` numbers are made by plain code when the prompt is built and listed in the
prompt, so the Tester cites what it was shown.

Under the findings table the Tests tab shows: "2 Tester findings were dropped because their
evidence did not check out." The dropped ones are visible behind a **Show dropped** toggle
(read-only). This is useful for the bake-off (Q9).

## 7. Rounds and Must fix (D-A)

- One shared budget of `build_max_rounds` (3) per build, as Phase 6. A Layer C Must fix (checks 2 to
  6) uses a round, exactly like a failing test.
- **Which files are fixed:** the files named by the Must fix findings. Never the tests.
- **What the Generator gets** for the fix: the Phase 6 failure report for the Generator, built by
  plain code, now with one line per Must fix: finding ID, file, line, quote, cite, message. Should
  fix and FYI findings are **not** sent to the Generator.
- After the fix, Layers A and B run again, then Layer C runs again as a **fresh, full review** (D-I).
- Budget used up with a Must fix still open: status NOT_PASSING, label Not passing, the code is
  still written (Phase 6 redesign B4), the open Must fix stays on the Tests tab.
- Budget used up with tests still failing: as Phase 6. Layer C did not run in that round; the Tests
  tab shows "Layer C did not run: the tests did not pass."
- Not the code's fault (Tester AI not answering after the existing retries, input too big): pause
  at `b_interrupted`, no round (Phase 6 D-H).

## 8. Labels

Plain code sets the label from the last review. The AI never sets it.

| Situation | Status | Label | Colour |
|---|---|---|---|
| 0 Must fix, 0 open Should fix, no zone touched | READY_FOR_REVIEW | **Ready for your review** | green |
| 0 Must fix, and at least one open Should fix or one zone touched | READY_FOR_REVIEW | **Ready with warnings** | yellow |
| Budget used with tests failing or a Must fix open, or check 1 failed | NOT_PASSING | **Not passing** | red |
| Tester reply unusable twice in one review | READY_FOR_REVIEW | **Unable to assess** | grey (D-D) |
| Tests could not be written (Phase 6 `b_unable`) | READY_TO_BUILD | Unable to assess (chat only) | unchanged from Phase 6 |

- The Phase 6 fixed warning "The independent Tester review (Layer C) is not built yet." is removed
  everywhere (label, Build tab, chat, smoke check). A test proves it no longer appears.
- When the developer accepts the last open Should fix and no zone is touched, the label moves from
  yellow to green, audited (`label_changed`). FYI never changes the label.
- Handoff (Phase 10) will allow only green and yellow. Phase 7 only stores the label.
- The label lives in the app, never in the code files.

## 9. The Tests tab (the report)

Above the Phase 6 content (frozen test list, results per round, View test code):

1. **Result banner** with the label and one line, for example "Tester review of round 2: 0 Must fix,
   1 Should fix, 1 FYI. Touches the Login zone."
2. **The 7 checks** (section 5), one row each.
3. **Findings table**: ID, severity, check, `file:line`, cited criterion or rule, message, quoted
   line (monospace). Sorted Must fix, Should fix, FYI.
4. **Actions per finding:**
   - Should fix: **Accept, with reason** opens a text box (10 to 300 characters) and **Save**. Saved,
     audited (`finding_accepted`), shown as "Accepted: <reason>". It can be undone with **Reopen**
     (audited) until handoff. **Fix it** is shown greyed with "Coming in Phase 8" (D-G).
   - Must fix: **Dispute** (D-F). No accept button.
   - FYI: no action.
5. Zone warnings, the dropped-findings line (section 6), and the model name the review used (for
   the bake-off).
6. One line under the report: "This report stays in the app. Nothing from it is written to your
   folder."

Earlier reviews of the same build are listed under **Earlier reviews** (collapsed), read-only.

Buttons on the composer at a finished build (2D control, buttons only): as Phase 6, plus **Run the
Tester review again** when the label is Unable to assess.

## 10. The Build tab

- The Layer C box "Matches the agreement?" shows Passed, Must fix found, Warnings, or Unable to
  assess, with a link "See the Tester report" that opens the Tests tab. "Coming in Phase 7" is gone.
- The progress list gets a Layer C line per round, with elapsed time and, when split, "Reviewed
  file by file (3 calls)".
- The `r1` banner covers Layer C Must fix too (section 2).
- "This build" adds: Tester findings by severity, and the model name the Tester used.

## 11. Rulebook policy additions

Same pattern as Phases 4 to 6: new `Policy` fields with defaults equal to the starter values, so older
rulebook versions still load. Admin screens are Phase 11.

| Field | Meaning | Starter value (made up, real values set at work) |
|---|---|---|
| `tester_max_prompt_chars` | Largest Tester prompt in one call before the per-file split (D-C) | 60000 |
| `tester_max_attempts` | Tester calls per review when the reply is unusable | 2 |
| `tester_quote_window` | How many lines away from `line` the quote may be found (E3) | 2 |

`tester_max_prompt_chars` is separate from `build_max_prompt_chars` because the Tester may run on a
different model with a different server limit (Q7, Q9).

## 12. Storage

New file `db_table_functions/db_tbl_da_tester.py`, same style as `db_tbl_da_build.py`. New tables,
`CREATE TABLE IF NOT EXISTS`. Nothing in existing tables changes; the Phase 6 build state gets the
new step value only.

| Table | Holds | Rule |
|---|---|---|
| `da_tester_reviews` | request ID, build number, round, review number, model name, calls, prompt chars, attempts, result (`done`, `unable`, `interrupted`), check results JSON (7 rows), zone warnings, label, created time | one row per review; updated only to close it |
| `da_tester_findings` | request ID, build number, review number, finding ID, check, severity, file, line, quote, cites, message, made by (`plain`, `tester`), kept or rejected, reject reason, created time | append-only |
| `da_tester_finding_actions` | request ID, finding ID, action (`accepted`, `reopened`, `disputed`), reason, actor, created time | append-only; the latest action is the finding's state |

Audit events (actor in brackets): `tester_review_started` (system), `tester_review_split` (system,
calls), `tester_reply_unusable` (system, attempt), `tester_finding_rejected` (system, reason),
`tester_review_done` (system, counts per severity, zones), `tester_unable_to_assess` (system),
`tester_review_rerun` (developer), `finding_accepted` and `finding_reopened` (developer, reason),
`finding_disputed` (developer), `label_changed` (system or developer, from, to). Every status move
is audited, as today. The count of Unable to assess per request is kept for Phase 10 (escalation
trigger 4).

## 13. Testing without work

- **pytest, plain rules:** checks 1, 2, 3 and 7 with good and bad made-up builds; the evidence
  rule E1 to E5 one by one (wrong file, line 0, line past the end, quote two lines away is corrected,
  quote five lines away is dropped, wrong cite kind, unknown rule ID); label rules for every row of
  section 8; yellow to green after the last accept; Must fix uses a round, Should fix never does;
  the Generator's fix input holds Must fix only; the Tester prompt holds no chat, no earlier
  findings and no test file text; the size guard splits, then pauses.
- **Fake provider (home):** a fixed script. Round 1 passes Layers A and B, Layer C returns 1 Must
  fix on one file; round 2 passes A and B, Layer C returns 1 Should fix and 1 FYI with good
  evidence plus 1 finding with a quote that is not in the file (dropped). Test-only switches force:
  an unusable reply twice (Unable to assess), a Must fix every review (cap, Not passing), no
  answer, an HTTP 400, an empty review (green).
- **Pretend work server** (127.0.0.1:8070): answers the Tester review prompt with the same script,
  so the onprem connector path is tested end to end with `DA_ONPREM_TESTER_MODEL` set and empty.
- **Playwright (cloud session only):** a full request reaches `b_written` with label Ready with
  warnings; on the Tests tab the Should fix is accepted with a reason and the label turns green.
- **Smoke check:** a full request from `ws_ready` through BUILDING and TESTER_REVIEW to
  READY_FOR_REVIEW with the scripted findings, then `b_written`. It no longer looks for the Phase 6
  Layer C warning.
- **Home check by Gian:** on `http://127.0.0.1:8050` with `DA_LLM_PROVIDER=fake` and a COPY of the
  repo as the workspace: watch round 1 fail on the Tester's Must fix, round 2 pass, then accept the
  Should fix on the Tests tab and see the label turn green.
- **Work test** (`docs/tester-work-test.md`, new, Command Prompt only): the Q9 bake-off steps and
  the Q7 check (section 16). No PowerShell, no DevTools.

## 14. Out of scope

- "Fix it" for a Should fix, the bug lane, the requirement and approach lanes, edit protection,
  restore (Phase 8).
- Safety-net tests for existing programs (Phase 9).
- Escalations inbox, senior overrule of a finding, auto-escalation on "Unable to assess twice" and
  "cap twice in a row", Handoff, PR summary (Phase 10). Phase 7 only stores what they need.
- Admin screens for the new policy fields and the "Tester findings by type" metric (Phase 11).
- Choosing the Tester's model (Q9, a work fact) and setting the real size limit (Q7, a work fact).
- Any change to how the Tester writes the test plan (Phase 4) or the tests (Phase 6), including W6
  (section 17).
- Leftovers P26, P27, P28.
- Any Git command. Writing the report or tests to the workspace or Bitbucket.

## 15. Decisions (D-x), decision rule applied

Each row: ranked options, one recommendation, and what the decision rule says. None of D-A to D-J
touches a work fact, all can be undone later (a code or policy change), and each has one clear
recommendation, so the chief picks the recommendation (rule row 1). Gian may still overrule any of
them before the build.

| # | Question | Options (ranked) | Recommendation | Decision rule |
|---|---|---|---|---|
| D-A | Does a Layer C Must fix use a round? | 1. Yes: the Generator fixes the cited files, then A, B and C run again, same shared budget. 2. No: Must fix goes straight to the developer. 3. A separate Layer C budget | **1**: the redesign says one shared budget covers test failures and Tester Must fix (B3, C2). Option 2 shows the developer code the app already knows is wrong. Option 3 can double the AI calls | Chosen by chief, 6.1. Approved by Gian, 7 Nov |
| D-B | How many AI calls per review? | 1. One call for checks 4, 5 and 6 together. 2. One call per check. 3. One call per file always | **1**: fewest slow calls, and the three checks need the same input. The per-file split exists only for the size guard (D-C). Option 2 triples the calls and the input | Chosen by chief, 6.1. Approved by Gian, 7 Nov |
| D-C | What happens when the Tester's input is too big (Q7 guard, HTTP 400)? | 1. Split into one call per file; if one file is still too big, pause at `b_interrupted` with Get help. 2. Pause at once with Get help. 3. Give the label Unable to assess | **1**: most reviews still finish, and it does not depend on the unknown limit (only its value does, section 16). Risk: a per-file call sees less of the whole, so check 5 may miss scope creep spread over files. Option 2 blocks every big change until Q7 is answered. Option 3 hides an app limit behind a model label | Chosen by chief, 6.1. Approved by Gian, 7 Nov |
| D-D | What does "Unable to assess" do? | 1. The code is written (A and B passed), status READY_FOR_REVIEW, grey label, buttons **Run the Tester review again** (no round used) and **Get help**. 2. Nothing written, pause at `b_interrupted`. 3. Treat it as yellow | **1**: the tests passed, so the developer can start his manual test, and the label stops a handoff (Phase 10 allows only green and yellow). Option 2 holds back tested code because of the Tester's reply. Option 3 claims a review that never happened | Chosen by chief, 6.1. Approved by Gian, 7 Nov |
| D-E | How strict is the evidence rule? | 1. File, line in range, the quote found within 2 lines, and a cite of the allowed kind that exists (section 6). 2. File and line only. 3. Trust the AI | **1**: a made-up finding almost never quotes real code on the right line; this is the main guard against a weak Tester model. Risk: a good finding with a slightly wrong quote is dropped; the dropped list shows it and the bake-off measures it | Chosen by chief, 6.1. Approved by Gian, 7 Nov |
| D-F | What does Dispute do in Phase 7, before the inbox exists? | 1. Moves the request to ESCALATION_REQUIRED with open item `Disputed Must fix: F-<n>` and the reason, like Get help. 2. Show "Coming in Phase 10". 3. Let the developer close the Must fix himself | **1**: reuses the existing escalation path and keeps "Must fix cannot be accepted away". Option 2 leaves him stuck on a wrong finding. Option 3 breaks the redesign rule | Chosen by chief, 6.1. Approved by Gian, 7 Nov |
| D-G | "Fix it" on a Should fix in Phase 7? | 1. Not built: greyed with "Coming in Phase 8"; only Accept with reason works. 2. A small fix that uses a round of the finished build. 3. Hide the button | **1**: "Fix it" is the bug lane, which is Phase 8, and the developer can still edit the file by hand. Option 2 builds half a Refine lane. Option 3 hides the plan from him | Chosen by chief, 6.1. Approved by Gian, 7 Nov |
| D-H | When is the code written? | 1. At `b_done`, after Layer C (or at the cap). 2. After Layers A and B, label updated after Layer C | **1**: the redesign order is pass, Tester review, write (5.4 step 6), and it avoids writing code that a Must fix round then rewrites. Option 2 gets code to him sooner but writes twice in most builds | Chosen by chief, 6.1. Approved by Gian, 7 Nov |
| D-I | After a Must fix round, how does Layer C review again? | 1. A fresh full review of the new round, with no earlier findings sent. 2. Re-check only the earlier findings. 3. Review only the fixed files | **1**: simple, catches problems the fix created, and keeps the Tester independent of its own earlier opinion. Options 2 and 3 miss new problems. Risk: a finding can come back worded differently; the report lists earlier reviews so the developer can compare | Chosen by chief, 6.1. Approved by Gian, 7 Nov |
| D-J | Who sets the severity of an AI finding? | 1. The AI proposes Must fix, Should fix or FYI; plain code keeps it if the evidence checks out; plain checks have fixed severities (section 5). 2. Every AI finding is capped at Should fix (the AI can never block). 3. Severity from a fixed table per check | **1**: matches the redesign (the Tester's Must fix shares the budget) and Dispute is the way out of a wrong one. Risk: a weak Tester model may over-use Must fix and burn rounds; the bake-off (Q9) shows this, and switching to option 2 later is a small change | Chosen by chief, 6.1. Approved by Gian, 7 Nov |

## 16. Work facts (no recommendation, Gian decides)

The chief opens one issue per row with the label shown and builds everything around it.

| # | Question | Options (not ranked) | What Phase 7 builds meanwhile | Issue |
|---|---|---|---|---|
| WF-1 (Q9) | Which model is the Tester at work? The bake-off (same 3 sample requests, Llama vs Qwen, separate call) has not been run | a. `default` (Llama-4-Maverick): 2 to 5 s, but repetitive and stopped at the 5-decision limit in Understand (W1, W2). b. `reasoning-vlm` (Qwen3.6): 10 to 20 s, did well in Understand, but the same model as the Generator. c. Leave `DA_ONPREM_TESTER_MODEL` empty (= the generator's model) | The model stays a setting; nothing is hard-coded. Each review saves the model name, kept and dropped findings, attempts and time, so the bake-off can compare. `docs/tester-work-test.md` lists the bake-off steps in Command Prompt, with 3 made-up sample requests | `needs-work-test`, #20 |
| WF-2 (Q7) | The server's context limit per model name | Unknown. Not guessed here | The size guard (section 4) and HTTP 400 handling stop cleanly whatever the limit. `tester_max_prompt_chars` starts at a made-up 60000; when the limit is known it is set from it (roughly 3 characters per token, minus room for the reply), per model | `needs-work-test` |

## 17. Open items

- **W6 (watch):** in Phase 4 and Phase 6 the Tester writes tests "without seeing code", but the
  design question text it sees could name a file. Layer C sees the code anyway, so W6 does not
  affect Phase 7. Phase 7 does not change the test-writing prompts. The plan checks that the Phase 6
  test-writing prompt still holds no code text (one test) and records W6 as still open for the
  Phase 8 spec.
- **Unable to assess twice** is escalation trigger 4 (redesign 5.11). Phase 7 stores the count;
  Phase 10 acts on it.
- **Dropped findings rate:** if the bake-off shows many good findings dropped by E3, raise
  `tester_quote_window` (a policy value, no code change).
- **D-C risk:** per-file calls can miss scope creep that spreads over files. Revisit when Q7 is
  known.
- Leftovers P26, P27, P28 stay in `specs/parked-items.md` (not Phase 7).

Photos: none needed for this spec.

## 18. Done when (every line becomes a test, Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| 7-1 | a round where Layers A and B pass | the round ends | status TESTER_REVIEW, step `b_tester_review`, audit `tester_review_started` |
| 7-2 | a round where Layer B fails | the round ends | Layer C does not run; Phase 6 behaviour is unchanged |
| 7-3 | a review | the Tester prompt is built | it holds the record, approach, test plan, test results and line-numbered code; it holds no Generator chat, no developer chat, no earlier findings and no test file text |
| 7-4 | a record with a criterion that has no test method | check 1 runs | a Must fix "not fixable by the Generator", no round used, status NOT_PASSING with the "Change the approach or get help" line |
| 7-5 | a build missing a planned file, or with an extra file | check 3 runs | a Must fix naming the file |
| 7-6 | a `modify` file whose text is unchanged | check 3 runs | a Should fix "The plan said to change `<path>`" |
| 7-7 | a planned path in the Login zone | check 7 runs | a zone warning, no finding, label at best yellow |
| 7-8 | AI findings with: a file not in the build; line 0; a line past the end; a quote not near the line; a cite of the wrong kind; an unknown rule ID | the evidence rule runs | each is dropped with its reason, saved as rejected, audited, and counted on the Tests tab |
| 7-9 | an AI finding whose quote is 2 lines from the stated line | the evidence rule runs | it is kept and its line is corrected |
| 7-10 | an unusable Tester reply, then a valid one | the review runs | 2 attempts, the valid reply is used |
| 7-11 | an unusable Tester reply twice | the review runs | label Unable to assess, status READY_FOR_REVIEW, code written, checks 4 to 6 "Not run", buttons Run the Tester review again and Get help |
| 7-12 | label Unable to assess | Run the Tester review again | a new review of the same round, no round used, status TESTER_REVIEW then the new label |
| 7-13 | a Layer C Must fix and budget left | the review ends | step `b_round_failed`, status BUILDING, only the cited file is regenerated, the Generator input holds the Must fix lines and no Should fix or FYI |
| 7-14 | a Must fix in every review (fake switch) | 3 rounds end | status NOT_PASSING, label Not passing, code still written, the open Must fix shown on the Tests tab |
| 7-15 | a review with 0 findings and no zone | it ends | label Ready for your review (green), status READY_FOR_REVIEW, then the Phase 6 write |
| 7-16 | a review with 1 Should fix | it ends | label Ready with warnings (yellow) |
| 7-17 | a yellow label from 1 Should fix and no zone | the developer accepts it with a 20-character reason | the label turns green, audits `finding_accepted` and `label_changed` |
| 7-18 | an accept reason of 5 characters | Save is pressed | refused with a plain message |
| 7-19 | an accepted Should fix | Reopen | it is open again and the label is yellow again, audited |
| 7-20 | a Must fix | the Tests tab is drawn | there is no accept button; Dispute is there |
| 7-21 | a Must fix | Dispute with a reason | ESCALATION_REQUIRED with open item `Disputed Must fix: F-<n>`, audit `finding_disputed` |
| 7-22 | a Should fix | the Tests tab is drawn | Fix it is greyed with "Coming in Phase 8" |
| 7-23 | any finished build | the label, Build tab, chat and smoke check are read | the text "The independent Tester review (Layer C) is not built yet." appears nowhere |
| 7-24 | a Tester prompt over `tester_max_prompt_chars` | the review runs | one call per planned code file, findings merged, `calls` saved, audit `tester_review_split` |
| 7-25 | a per-file call still too big, or an HTTP 400 on it | the review runs | `b_interrupted` with the "too big for the Tester" message, no round used |
| 7-26 | the Tester AI does not answer after retries | in Layer C | `b_interrupted`, round count unchanged, Try again repeats the review |
| 7-27 | a build in `b_tester_review` | Stop build | status READY_TO_BUILD, nothing written, audit `build_stopped` |
| 7-28 | a build marked in `b_tester_review` at server start-up | the server starts | `b_interrupted` with the restart message; Try again repeats only that review |
| 7-29 | `DA_ONPREM_TESTER_MODEL` set, and empty | a review runs against the pretend work server | the set model, or the generator's model, is called; the model name is saved on the review |
| 7-30 | the code | searched | no Tester model name is hard-coded outside the settings and tests |
| 7-31 | any Layer C action | sent with an old build revision | refused with the stale message |
| 7-32 | a rulebook version saved before Phase 7 | it is loaded | the three new fields hold the starter values |
| 7-33 | a finished review | the workspace write job is built | it holds code files only; no report, no test file |
| 7-34 | the Phase 6 test-writing step (W6) | its prompt is built | it holds no code text |
| 7-35 | Playwright with the private test folder | a full request runs | label yellow at `b_written`; after accepting the Should fix it is green |

Plus: `pytest` 0 failures, `ruff check` 0 problems, smoke check passes, code reviewer 0 Must fix, and a
home check by Gian on `127.0.0.1:8050` with a COPY of the repo as the workspace.

## 19. Files the builder will touch (for planning, not a limit)

`pydantic_classes/da_models.py` (moves), `da_tester_models.py` (new: `TesterReviewReply`,
`Finding`), `da_rulebook_models.py` and `data/da_rulebook_seed.json` (policy fields),
`agents/da_build_flow.py` (Layer C step, rounds, labels), `agents/da_tester_review.py` (new: plain
checks, evidence rule, prompt building, size guard), the Tester review prompt under `data/`,
`agents/da_llm_client.py` (fake script and pretend-server answers for the review prompt),
`db_table_functions/db_tbl_da_tester.py` (new), `layouts/da_developer_assistant_page.py`, the page
callbacks, `web/da_web_components.py` (Tests tab report, Build tab Layer C box), `da_smoke_check.py`,
`README.md`, `CLAUDE.md` ("Current phase"), `docs/tester-work-test.md` (new: Q9 bake-off and Q7
steps, Command Prompt only), and the matching tests.
