# Phase 10: Handoff and Escalations inbox

Status: DRAFT v0.1 (14 Nov 2026). Written by the spec writer from `specs/phase-10-facts.md` (Gian,
13 Nov 2026). Not yet approved by Gian. The chief applies the decision rule
(`specs/phase-a-automation.md` section 6) to D-A to D-L (section 18). The work facts (section 19)
need Gian and get no recommendation.
Scope: **Handoff + Escalations inbox only.** "Review my code" (redesign 5.9) is parked as
**Phase 10b** and is not in this spec (facts, Gian 13 Nov 23:26).
Depends on: Phases 7 to 9 and 11 (11a, 11b merged; **11c must be merged into `auto/phases-7-10`
before this build starts**, because section 13 changes the Overview metrics 11c wrote).
Next: Gian's own findings list (its own thread), then Phase 10b.
Source of truth: `specs/redesign-2026-10-31.md` sections 5.10 (Handoff), 5.11 (Escalation), 3 (status
table), 7 (Admin row for triggers and zones); `specs/phase-10-facts.md`; Phase 5 Q10 (commit or upload
from the workspace); Phase 7 D-F (Dispute); Phase 8 "Last tested" and F4; Phase 9 "Stored for Phase
10"; Phase 11 sections 6, 8, 9, 12 and open item "Trigger names and Phase 10".
Visual reference: `docs/CodeVision_Developer_Assistant_Demo.html`. Read only the chat entries `/*46*/`
to `/*48*/` (the `MAIN` list), the function `tabAudit` (the PR summary box and the Copy summary
button) and the last `ws(...)` call (`ch:"6 Handoff"`). Note two things the demo gets wrong: it lists
a `tests/...` file in the PR summary (tests never go to the workspace since Phase 6 Q11) and it shows a
full folder path (only the folder name is known, Phase 5). There is no demo screen for the inbox.
Build: worker team, ONE branch `auto/phase-10` (facts). If the build is large, the plan orders the
steps so **Handoff comes first** and each run can stop cleanly. Do not split branches.

## In plain words

After Phase 9 a request can be built, reviewed by the Tester, refined, and the code sits in the
developer's folder with a label. Two things are still missing:

1. **Handoff.** The developer says "I'm done". The app checks that he really is: 0 Must fix, every
   Should fix fixed or accepted with a reason, and his folder holds exactly the files that were last
   tested (a final fingerprint check). Then it writes a **PR summary** he copies into Bitbucket, and
   locks the request. The app never commits, pushes, approves or opens the PR. He does that himself,
   from his clone or from his ZIP copy (Phase 5 Q10).
2. **Escalation.** Today "Get help" and "Dispute" move a request to ESCALATION_REQUIRED and it stays
   there: nothing can move it out (`ALLOWED_MOVES[ESCALATION_REQUIRED]` is empty). Phase 10 adds the
   other three triggers (plain code, each behind its Admin on/off switch), a **senior inbox** inside
   the Developer Assistant where the capability's named senior (or the backup) sees the request and
   acts: overrule a finding, send guidance, take over, or close, and the moves that bring the request
   back to the developer.

Flag-for-review zones are **not** an escalation. They only make the named senior a required PR
reviewer, which the PR summary says in words.

AS400 comparisons:
- Handoff is the **promotion request**: the programmer does not move the object to production
  himself; he fills in the change form (the PR summary), and the form says exactly which members, which
  tests, and who must sign. The final fingerprint check is `CMPPFM` between what was tested and what is
  in his library: any difference and the form is refused.
- HANDED_OFF is the member being **checked in and locked**: `CHGPFM` is refused; a later change is a
  new change request that points back to this one.
- The escalation inbox is a **message queue** (`DSPMSG` on the senior's `MSGQ`): the system puts a
  message there when a fixed condition is met; the senior replies (send guidance is a reply message
  that the program reads on its next step), takes the job, or ends it.

**AI calls in this phase: none of our own.** Handoff and the inbox are plain code. "Send guidance"
only adds text to the **next** AI call that an existing flow makes (section 9).

## Words used in this spec

| Word | Meaning |
|---|---|
| Handoff | The last step: checks pass, the PR summary is written, status HANDED_OFF, request locked |
| Final fingerprint check | The browser re-reads every planned file; each fingerprint must equal the "last tested" one (Phase 8). Any difference blocks Handoff |
| Last tested | The set of planned-file fingerprints the last finished build or check run tested (Phase 8 `da_refine_tested`: `last_tested_build`, `last_tested_kind`) |
| PR summary | A plain-text block (section 5) with a copy button. The developer pastes it into the Bitbucket pull request. Never a Git action |
| Hand-edited file | A planned file whose last tested text came from the developer, not the Generator: it has a `scanned` row (Phase 5/8) whose fingerprint equals the last tested one, or the last tested run was a Phase 8 check run on his edits |
| Accepted risk | A Should fix accepted with a reason (Phase 7 `finding_accepted`), a freshness override (Phase 9), or a "not covered by the safety net" item (Phase 9). All shown at Handoff |
| Trigger | One of the five fixed escalation conditions (redesign 5.11), each with an Admin on/off switch in the rulebook (`Policy.escalation_triggers`, Phase 11 section 9 names) |
| Escalation | One row in `da_escalations` (section 15): why, when, which senior, and what happened. A request has at most one **open** escalation |
| Senior | The capability's `named_senior` from the catalog, or its `backup_senior` (Phase 11). Who a logged-in user is, is WF-1 |
| Inbox | The senior's page inside the Developer Assistant (`/inbox` at home, D-G): open escalations addressed to him, with the four actions |
| Guidance | Text a senior sends. It appears in the developer's chat and is added, once, to the next AI call of the flow the request was in |
| Overrule | A senior marks a Must fix (or Should fix) as not applying, with a reason. Audited. The finding's state becomes `overruled` |
| Take over | A senior marks himself as working on the request. The developer is told; the senior keeps the inbox row until he closes it |
| Close | The senior ends the escalation with a note and sends the request back to where it was (section 10), or abandons it (D-D) |
| Chat lock | (D-A) While an escalation is open, the developer's composer is disabled until the senior closes or sends guidance |

## 1. Decisions already made (do not reopen)

| # | Decision | Source |
|---|---|---|
| 1 | Handoff is allowed only at green or yellow: 0 Must fix open, each Should fix fixed or accepted with a reason, **and** the final fingerprint check shows the workspace equals what was last tested | Redesign 5.10, facts |
| 2 | The assistant never commits, pushes, approves or opens a PR. The developer commits **or uploads** from his workspace (clone or ZIP copy) and opens the PR in Bitbucket himself | Redesign 5.10, Phase 5 Q10 |
| 3 | PR summary with a copy button, holding: request ID, record version, one-line summary; criteria -> tests -> results; files changed and which were hand-edited; reuse and approach decisions; accepted risks with reasons; flag-for-review zones (named senior is a required reviewer); safety-net gaps; a capability still waiting in the Unassigned queue is marked | Redesign 5.10, facts |
| 4 | Status HANDED_OFF, request locked | Redesign 5.10, 3 |
| 5 | Five fixed triggers, plain code, each obeys its Admin on/off switch: (1) round cap hit twice in a row on the same request, (2) request or approach out of scope, (3) developer disputes a Must fix, (4) Tester "Unable to assess" twice, (5) Get help | Redesign 5.11, facts |
| 6 | Trigger names are the Phase 11 ones: `cap_hit_twice`, `out_of_scope`, `dispute`, `tester_unable_twice`, `get_help` | Phase 11 section 9, open item |
| 7 | An escalation goes to the capability's named senior, or the backup senior | Facts, Phase 11 decision 14 |
| 8 | Senior inbox, inside the Developer Assistant: overrule a finding (audited), send guidance (goes into the chat and the next AI call), take over, close | Redesign 5.11, facts |
| 9 | Flag-for-review zones are **not** an escalation; they only make the senior a required PR reviewer | Redesign 5.11 (X3), facts |
| 10 | Tests never go to the workspace or Bitbucket; the PR summary names tests and results but lists no test file | Phase 6 Q11 |
| 11 | "Get help" already moves a request to ESCALATION_REQUIRED with open item `Escalated in <stage>: <step>`; Dispute does the same with `Disputed Must fix: F-<n>` | Phases 4 to 9, Phase 7 D-F |
| 12 | Phase 8 stores "last tested" (`da_refine_tested`) and the count of rebuilds that ended NOT_PASSING in a row (`not_passing_in_a_row`, F4); Phase 7 stores the Unable to assess count (`count_unable_reviews`); Phase 9 stores the PR-summary facts (targets, capability, named senior, capability-not-confirmed flag, freshness result and override, impact, safety-net results, not-covered list) | Phase 7, 8, 9 specs |
| 13 | Admin Overview shows "No data yet (comes with Phase 10)" for Handoffs and labels Escalations "Get help only". Phase 10 makes both real by reading the existing metrics code (`agents/da_admin_metrics.py`, `db_table_functions/db_tbl_da_metrics.py`) | Facts, Phase 11 section 12 |
| 14 | Notification to the senior (email or Teams) is pending bank approval. **Inbox only** | Facts, Phase 11 decision 19 |
| 15 | "Review my code" is Phase 10b. The Home card stays as it is today | Facts |
| 16 | Developer-facing wording: "negative scenario", never "failure"; Command Prompt only in developer instructions; made-up names only | CLAUDE.md, facts |
| 17 | Every action follows the Phase 6 B3 pattern: read with no lock, slow work (the browser's file read) outside any transaction, ONE write transaction for state, rows, audit and chat; a revision number for the stale check (`STALE_MESSAGE`) | Phases 4 to 9 |

## 2. Handoff: the flow (one step at a time)

Same screen: chat on the left, tabs on the right. Handoff has its own small state (section 15) with
its own revision number.

| Step | Where | The developer sees | Then |
|---|---|---|---|
| start | READY_FOR_REVIEW with label green or yellow | Chat button **Ready for handoff** (demo `/*46*/`), next to the Phase 8 Refine box | H1 to H3 |
| `h_blocked_findings` | a Must fix is open, a Should fix is neither fixed nor accepted, or the label is Not passing or Unable to assess | Chat lists what blocks, in plain words, each naming the finding ID: "F-3 (Should fix) is still open: Fix it or Accept, with reason." Buttons **Open the Tests tab**, **Get help** | He fixes or accepts on the Tests tab (Phase 7 and 8), then presses Ready for handoff again |
| `h_checking` | checks of H2 pass | Chat: "Final check: reading your folder." Busy state | The browser reads every planned file and returns fingerprints (Phase 5 re-scan, planned files only) |
| `h_blocked_folder` | at least one planned file differs from last tested, or is missing, or permission is gone | Chat names each file and why: "Changed since the last test", "Missing". Buttons **Re-scan and check my edits** (Phase 8 Check my edits path), **Restore the tested version** (Phase 8 restore, D-B), **Get help** | H4 |
| `h_done` | the final check passed | Chat `/*48*/` wording (adjusted: "Commit or upload from your folder and open the PR in Bitbucket yourself. I never commit, push or approve."). Audit tab shows the **PR summary** box with **Copy summary** (section 5). Status pill HANDED OFF | End of Phase 10 for this request. Section 4: locked |

Rules:
- H1: **Ready for handoff** is shown only at READY_FOR_REVIEW. It is never shown at NOT_PASSING,
  REVISION_IN_PROGRESS, BUILDING, TESTER_REVIEW or ESCALATION_REQUIRED. At NOT_PASSING the chat says
  once "Handoff needs a passing build. Refine, or Get help."
- H2: **Findings check** (plain code, no browser): the label of the last review is green or yellow;
  no kept Must fix whose latest action is not `overruled` (section 9); every kept Should fix has a
  latest action `accepted` or `overruled`, or was fixed (a later review no longer lists it); the
  last tested run is a finished build or check run, not stopped or interrupted. All conditions are
  listed when one fails; the chat shows the whole list.
- H3: **Workspace check**: the request has a workspace at `ws_ready` with permission (Phase 5 W4;
  **Reconnect** first if not). In download mode (Phase 5 fallback) the final check runs on an
  **Upload folder to check** (D-C).
- H4: **Final fingerprint check**: for every planned file of the accepted approach version, the
  browser's fingerprint must equal the last tested fingerprint (the `da_build_files` code row of the
  last tested build, or the `scanned` row a check run tested). Equal for all: `h_done`. Otherwise
  `h_blocked_folder`. The check reads **planned files only** (Phase 5 R1), writes nothing, and never
  changes a file. Nothing is auto-fixed: Handoff after "Changed since the last test" needs a Check
  my edits run (then the edit is the new last tested) or a Restore.
- H5: `h_done` happens in ONE write transaction: status READY_FOR_REVIEW to HANDED_OFF, the PR
  summary text saved (section 5), the handoff row (section 15), audit `handoff_checked` and
  `handed_off`, chat lines. The browser's read happens before the transaction.
- H6: An open escalation on the request blocks Handoff: "A senior is looking at this request." The
  request is at ESCALATION_REQUIRED then anyway (H1), so this is a plain-code guard in the handoff
  function, tested directly.
- H7: **Get help** from `h_blocked_findings` or `h_blocked_folder` is trigger 5 (section 7) with open
  item `Escalated in Handoff: <step>`.

## 3. Statuses

New status **HANDED_OFF** (from the redesign table; the only new status in this phase). New moves
(add to `ALLOWED_MOVES`, every move audited as today):

- READY_FOR_REVIEW to HANDED_OFF (H5)
- ESCALATION_REQUIRED to each status it can have come from (section 10 "return": the status stored
  in the escalation row's `from_status`); the plain-code check allows only the stored one
- ESCALATION_REQUIRED to HANDED_OFF: **never** (a senior cannot hand off for the developer)

`HANDED_OFF` has no moves out: `ALLOWED_MOVES[HANDED_OFF] = ()`. The redesign names the escalated
status `ESCALATED`; the built name is `ESCALATION_REQUIRED` and stays (D-K).

## 4. HANDED_OFF: locked

- Every developer action on the request is refused with one message: "This request is handed off
  and locked. Start a new request for further changes; it will be linked to this one." No Refine, no
  Re-scan write, no Build, no Dispute, no Accept, no workspace Change. Reading is fine: every tab,
  the chat history, the PR summary and Copy summary.
- The composer shows a read-only line, not a text box (the demo's "Ask a follow-up question" box is
  not built: it would need an AI call and a memory design Phase 10 does not have; D-E).
- **Follow-up request** (redesign 5.1 "New CVDA instead of a new version"): the chat at `h_done`
  offers **Start a follow-up request**. It opens Home card 1 or 2 (the same kind as this request) with
  one new field on the request: `follows_request_id` (nullable, section 15). The Summary tab of the new
  request shows "Follows CVDA-2026-0001". Nothing is copied from the old request (D-F).
- "My recent requests" lists handed-off requests with the HANDED OFF pill; opening one shows the
  Audit tab first.
- Admin's rulebook saves never touch a handed-off request (pinned, Phase 1).

## 5. The PR summary (plain code, no AI)

Built once at `h_done` and saved as text (`da_handoffs.summary_text`). Shown in a monospace box on
the Audit tab with **Copy summary** (a Dash clientside callback using `navigator.clipboard.writeText`;
if the browser refuses, the box is selectable text and the chat says "Select the text and copy it").
Lines, in this order, each from a named source (the builder confirms columns in the plan):

| # | Line | Source |
|---|---|---|
| 1 | `CVDA-2026-0001 v2: <one-line summary>` (record version = highest confirmed `da_request_records.version`; summary = the record's title or first purpose line) | `da_requests`, `da_request_records` |
| 2 | `Kind: new | enhancement | fix` and, for an enhancement, the targets and capability: `Capability: Limits (senior: Limits capability lead)`; if the Unassigned row for a target is still `open`: `Capability: Limits (picked by developer, not yet confirmed by Admin)` | `da_enhance_state`, `da_unassigned_files`, catalog of the pinned rulebook |
| 3 | `Follows: CVDA-...` only when `follows_request_id` is set | `da_requests` |
| 4 | `Criteria: 8 · Tests: 10 of 10 passed (1 written by the developer, 2 safety-net)` then one line per criterion: `AC-1: 2 tests, passed` (results from the last tested run's Layer B; "Yours" and safety-net counts from the frozen test set) | `da_request_records`, `da_build_files` (tests), `da_build_rounds` |
| 5 | `Tester: Ready for your review` or `Ready with warnings`, with counts: `<n> Must fix fixed, <n> Should fix fixed, <n> accepted, <n> FYI, <n> overruled by <senior id>` | `da_tester_reviews`, `da_tester_findings`, `da_tester_finding_actions` |
| 6 | `Files:` one line per planned file: path, `(new)` or `(changed)`, and `edited by developer` where the file is hand-edited (Words table) | approach file plan, `da_workspace_files`, `da_refine_tested` |
| 7 | `Reuses:` the accepted reuse decisions (`RU-<n>` texts); `Decisions:` the design decisions (`DD-<n>` texts), one line each | accepted approach version |
| 8 | `Accepted risks:` one line per accepted Should fix: `F-3: <reason> (accepted by <developer id>, <date>)`; freshness override: `Local changes confirmed as intentional` or `Freshness not checked: Bitbucket main unreachable`; or `none` | `da_tester_finding_actions`, `da_freshness_checks` |
| 9 | `Flag-for-review zones: Login (required reviewer: <named senior>)` one per zone touched, from the last review's `zone_warnings`; or `none`. When the capability's named senior is set, that senior is named; otherwise the zone line says `required reviewer: see the capability catalog` | `da_tester_reviews.zone_warnings`, catalog |
| 10 | `Safety-net gaps:` the Phase 9 not-covered list, one per item, each with `Check manually`; `not applicable (new code)` for card 1 requests; impact `Impact could not be checked` if stored | Phase 9 stored facts |
| 11 | `Senior involvement:` one line per closed escalation on this request: trigger, senior, outcome, date; or `none` | `da_escalations` |
| 12 | `Final check: workspace = last tested (build <n>, <date>)` | `da_handoffs` |
| 13 | `Generated by the CodeVision Developer Assistant. It did not commit, push, approve or open this PR.` | fixed |

Rules: plain text, no Markdown tables (Bitbucket's PR box keeps it readable either way); under 4,000
characters for a 5-file request with the seed (a test checks the fake request); made-up IDs only; no
folder path, only the folder name if named at all; no test file path (decision 10). Every line that
names a senior uses the catalog label as stored (at home a made-up label such as "Limits capability
lead"). Which requests got the summary and when is the "Handoffs" number (section 13).

## 6. Handoff: what the developer does next (words on screen)

Chat at `h_done`, two variants from the Phase 5 check result (Q10, "no `.git` folder" information):

- **Git clone:** "Commit the changed files from your folder and open the pull request in Bitbucket.
  Paste the summary from the Audit tab into the PR description. Add <named senior> as a reviewer if
  the summary names a flag-for-review zone."
- **ZIP copy:** "Upload the files listed under Files in the summary to the Bitbucket branch and open
  the pull request. Paste the summary into the PR description." (same senior line)

No Git command is shown or run. If a work-test note wants exact Command Prompt lines for `git add`
and `git commit`, that is a one-line doc change (`docs/handoff-work-test.md`, Command Prompt only).

## 7. Escalation triggers (plain code)

One module, `agents/da_escalation_triggers.py`, one function per trigger returning "fire with this
reason" or "do not fire". Each reads the **request's pinned rulebook** (`Policy.escalation_triggers`
by the Phase 11 names) and does nothing when its switch is off. Where each is checked:

| # | Name | Fires when | Checked where | Open item text |
|---|---|---|---|---|
| 1 | `cap_hit_twice` | `da_refine_tested.not_passing_in_a_row` reaches 2 (two builds in a row on the same request ended NOT_PASSING; Phase 8 F4 keeps the count, a pass or check run resets it) | at the end of the build loop, in the same transaction that writes `build_not_passing` | `Round cap hit twice: builds <n-1> and <n>` |
| 2 | `out_of_scope` | (a) Understand: the confirmed record has a `Scope conflict:` open item (`da_understand_checks.SCOPE_CONFLICT_PREFIX`) at Confirm; (b) Approach: the Generator's file plan needs a protected file or a path outside `allowed_folders` after the Phase 4 change cap (G9) is used up. **The AI never decides scope**; only these plain-code facts do (D-H) | (a) at record confirm, (b) at the approach refusal | `Out of scope: <the conflict or path>` |
| 3 | `dispute` | the developer disputes a Must fix (Phase 7 `dispute_finding`) | already escalates; Phase 10 only adds the escalation row and the senior (section 8). **Switch off:** Dispute still refuses to accept the Must fix away, but goes nowhere: the chat says "Disputes are not routed to a senior at the moment. Get help instead." (D-I) | `Disputed Must fix: F-<n>` (unchanged) |
| 4 | `tester_unable_twice` | `count_unable_reviews(request)` reaches 2 (two reviews of this request ended Unable to assess) | at the end of a Tester review, in the transaction that writes `tester_unable_to_assess` | `Tester unable to assess twice: reviews <a> and <b>` |
| 5 | `get_help` | every existing Get help button (Understand checkpoint, Discover, Approach, Workspace, Build, Refine, Enhance, Handoff) | the existing `request_help` functions, through one shared `escalate(...)` helper (section 8). **Switch off:** the buttons stay (a developer must never be stuck) but the request does not move; the chat says "Get help is not routed to a senior at the moment. Ask your senior directly." (D-I) | unchanged `Escalated in <stage>: <step>` |

Rules:
- X1: A trigger that fires while an escalation is already **open** on the request does not open a
  second one; it adds a line to the open row's `reasons` list and audits `escalation_reason_added`.
- X2: A trigger fires at most **once per cause**: trigger 1 fires at count 2, not again at 3 unless
  the count was reset in between; trigger 4 likewise. The count that fired is stored on the row.
- X3: Triggers 1, 2 and 4 are **automatic**: the status moves to ESCALATION_REQUIRED in the same
  transaction, the chat tells the developer in plain words why ("Two builds in a row did not pass.
  Your capability's senior, <label>, has been asked to look at this request."), and the Build tab or
  Tests tab keeps showing the last result.
- X4: Triggers never fire at HANDED_OFF (nothing runs there) and never fire for a request already
  at ESCALATION_REQUIRED (X1 covers the row).

## 8. Who gets it: the senior

Plain code, `agents/da_escalation_routing.py`:
1. The request's capability: for an enhancement, the confirmed target's capability (Phase 9
   `da_enhance_state`); for a new request, the **catalog lookup on the planned files** of the accepted
   approach (first match wins, Phase 9 rule). Several capabilities: the first planned file's one;
   the others are listed on the row.
2. `named_senior` of that capability in the **active** rulebook version (not the pinned one: a
   senior who left should not keep getting mail, D-J). Empty: `backup_senior`. Both empty, or no
   capability at all (no approach yet, no catalog match): the row is addressed to **"Unassigned"**
   and appears in every senior's inbox under a heading "Nobody is named for this capability", plus a
   Needs attention line on the Admin Overview ("1 escalation has no named senior").
3. The row stores both labels (`senior_label`, `backup_label`) at the time of escalation. The inbox
   shows a row to a user whose ID matches either (how a user ID matches a catalog label is WF-1; at
   home the label is the ID, D-G).

Escalations open today with no senior (requests escalated before this phase) are routed at the
first inbox load with the same function and audited `escalation_routed`.

## 9. The senior inbox

Where it hangs: `/inbox` at home, a third menu entry **Inbox** in `da_home_web_server.py`, next to
Admin (D-G). Access check `agents/da_senior_access.py`, `is_senior(settings, user_id)`: `DA_SENIOR_SOURCE`
`env` (home: `DA_SENIOR_IDS`, comma-separated; **and** any ID that appears as a `named_senior` or
`backup_senior` in the active catalog) or `codevision` (placeholder that returns False and logs
"Senior access is not configured yet"), mirroring Phase 11's `is_admin`. Not a senior: "This page is
for capability seniors." At work the real source is WF-1.

**The list.** One table, newest first, open rows only by default (**Show closed** adds the last 50):
request ID and title, developer ID, capability, trigger(s) in words, when, status before, the open
item text, who has taken it over. A filter **Mine / All**: Mine = rows whose senior or backup label
matches me; All = every open row (any senior may act on any row, so a sick senior is no dead end,
D-L). "Unassigned" rows appear in both.

**The detail.** Clicking a row opens, read-only, the developer's view of that request: the chat, the
Summary, Approach, Build, Tests and Audit tabs (the same layout functions, with the composer replaced
by the senior's action bar). The senior can read the record, the findings with evidence, the last
build's result and the audit trail. He cannot press any developer button.

**The four actions** (each ONE write transaction with the escalation row's own revision for the
stale check; each audited with actor `senior` and the senior's ID; each adds a chat line in the
developer's chat, marked as from the senior):

| Action | What it does | Allowed when |
|---|---|---|
| **Overrule a finding** | Pick one kept finding of the last review (Must fix or Should fix), type a reason (20 characters minimum, as Accept). A `da_tester_finding_actions` row `overruled` with actor `senior:<id>`. Plain code re-labels: if no Must fix is left open, the label moves from Not passing to Ready with warnings (audit `label_changed`, from, to); a yellow label with every Should fix answered and no zone becomes green (Phase 7 rule). The status does **not** change here; Close does that. The Tests tab shows "Overruled by <id>: <reason>" and the PR summary line 5 counts it | an open row with at least one open finding |
| **Send guidance** | Text (1 to 2,000 characters). Saved on the row (`guidance` list), shown in the developer's chat as a senior bubble, and added **once** to the **next** AI call of the flow the request returns to: the prompt builders of Approach, Build (Generator fix round), Refine lane suggestion and the Tester review get an optional `senior_guidance` block ("Guidance from your senior: ..."), consumed and marked `used_in` on the row when sent. Plain code, no AI call of its own. If chat lock (D-A) is on, guidance **unlocks** the chat without closing the row | an open row |
| **Take over** | Sets `taken_over_by` to the senior. Chat: "<id> has taken over this request." The row shows it in the list. Nothing else changes: the developer's buttons stay disabled (ESCALATION_REQUIRED). The senior may then **Return to developer** (same as Close with outcome `returned`) when done | an open row not already taken over by someone else (a second senior sees "Taken over by <id>") |
| **Close** | A note (required) and an outcome: **Return to developer** (status moves back to `from_status`, section 10) or **Abandon request** (D-D: status stays ESCALATION_REQUIRED, row closed with outcome `abandoned`, the request is shown as "Closed by senior" in My recent requests, locked like HANDED_OFF). Chat line with the note | an open row |

**No AI call in the inbox.** The senior sees the findings' evidence (file, line, quote) as the
developer does; nothing is summarised for him.

## 10. Returning to the developer

- `from_status` is read at escalation time from the request's status in the same transaction (the
  status move writes `from` and `to`; the row keeps `from`). Return moves ESCALATION_REQUIRED to
  exactly that status; `check_status_move` allows only the stored one (section 3).
- The flow state the request was in (Approach step, Build step, Refine step, Enhance step) is left
  untouched during the escalation, so the screen redraws at the same step. The open item on the
  approach state (`open_item`) is cleared on Return, as the Phase 4 to 9 code already does when
  leaving the escalated step.
- **Dispute return:** if the senior overruled the disputed Must fix, Return lands at READY_FOR_REVIEW
  (or NOT_PASSING if other Must fix remain) with the new label; if he did not overrule it, the Must
  fix stays open and the developer's only ways are Refine (fix it) or another Dispute, which is X1
  (a new row, since the old one is closed; the chat says the senior upheld it).
- **Cap-twice return:** `not_passing_in_a_row` is reset to 0 on Return (the senior has looked), so
  trigger 1 does not fire again on the very next NOT_PASSING; it needs two more in a row.
- **Unable-twice return:** the Unable count is **not** reset (it is a Tester history), but trigger 4
  fires again only at count 4 (X2 stores the count that fired).
- A request whose `from_status` is one that no longer exists or that cannot be reached (none today;
  a guard for later phases) is returned to READY_FOR_REVIEW if it has a finished build, else to
  APPROACH_PROPOSED if it has an approach, else to the Understand checkpoint
  READY_FOR_CONFIRMATION, with an audit note. A test covers the guard with a made-up status.

## 11. Chat lock (D-A, default on)

While an escalation is open on a request: the developer's composer shows "Waiting for your senior.
Your chat is locked until <label> replies." and no button. Every Get help button is hidden (there is
nothing more to ask). **Reading** is free: tabs, chat history, Re-scan (a read, Phase 5 W8). The
lock lifts when the senior sends guidance or closes the row. With D-A option 2 (no lock) the
developer keeps Re-scan and the read-only screen, exactly as ESCALATION_REQUIRED behaves today; the
difference is only the wording.

## 12. Rulebook and settings

No new `Policy` fields for the triggers (they exist since Phase 11, section 9). New:

| Where | Field | Meaning | Starter value |
|---|---|---|---|
| `Policy` | `escalation_lock_chat` | D-A: lock the developer's chat while an escalation is open | `true` |
| `Policy` | `handoff_summary_max_chars` | Guard for the PR summary length (over it: the lines are kept, the criteria list is shortened to counts, and a note says so) | 6000 |
| `.env` | `DA_SENIOR_SOURCE` (`env` default, `codevision` placeholder), `DA_SENIOR_IDS` (home only) | Section 9 | empty |

Defaults equal the starter values so older rulebook versions still load (Phase 4 section 7 pattern).
Admin screen for the two new fields: the Phase 11 Build and test tab's **Advanced limits** gets
`handoff_summary_max_chars`; `escalation_lock_chat` sits next to the five triggers as a sixth
switch labelled "Lock the developer's chat during an escalation". A one-row change to the Phase 11
form function, with a test.

## 13. Making the Admin numbers real (Phase 11 section 12)

In `agents/da_admin_metrics.py` and `db_tbl_da_metrics.py`, within the chosen window:

| Number | Was | Now |
|---|---|---|
| Handoffs | `NO_DATA_PHASE_10` | count of `da_handoffs` rows; note "<n> of <requests> requests (<share>%)"; "No data yet" when the table is empty |
| Escalations | Get help count with `GET_HELP_LABEL` | count of `da_escalations` rows, grouped by trigger name in words (`items`: "Get help 3, Dispute 1, Cap hit twice 0 ..."), plus open vs closed and the average hours open for closed rows. The old Get help counting from audit events stays only for requests escalated **before** this phase (no row): they are counted as Get help or Dispute from the open item, as today. The `GET_HELP_LABEL` note is removed; a test proves it no longer appears |
| Needs attention | - | "1 escalation has no named senior" (section 8 step 2), "3 escalations open longer than `admin_unassigned_stale_days`" (reuses the Phase 11 field) |

A `Metric` with no rows still says "No data yet", never 0 dressed as a result.

## 14. Screen

Use the existing `da_web_components` helpers.

- **Developer page:**
  - Chat button **Ready for handoff** at READY_FOR_REVIEW (H1), in the same row as the Phase 8 lane
    box.
  - Stepper: the sixth step **Handoff** lights at HANDED_OFF (the stepper already has six names,
    redesign 3).
  - Status pill: HANDED OFF; ESCALATION REQUIRED gets the senior's label under it ("With: Limits
    capability lead").
  - **Audit tab** at HANDED_OFF: the demo's `tabAudit` layout: the lock banner, the PR summary box
    with Copy summary, the audit timeline the tab already has. The PR summary box is also shown on
    the Build tab's "This build" card as a link "Open the PR summary" (one place to copy from).
  - Senior guidance bubbles in the chat: a distinct style (left side, labelled "Senior: <id>").
  - Composer at ESCALATION_REQUIRED: section 11. At HANDED_OFF: section 4.
- **Inbox page** (`layouts/da_inbox_page.py`, callbacks in
  `callbacks/screen_callbacks/da_inbox_page_callbacks.py`): the list with Mine/All and Show closed,
  the detail with the request's tabs read-only, the action bar (four buttons, each opening a small
  dialog with its text box), a green line after each action ("Guidance sent to CVDA-2026-0001").
- **Admin Overview:** the two numbers and Needs attention lines of section 13; the Build and test tab
  change of section 12.
- "My recent requests": HANDED OFF and "Closed by senior" pills; a handed-off request opens on the
  Audit tab.

## 15. Storage

New file `db_table_functions/db_tbl_da_handoff.py` and `db_tbl_da_escalation.py`, same style as
`db_tbl_da_refine.py`. `CREATE TABLE IF NOT EXISTS`. One existing table changes (`da_requests`, a
nullable column, Phase 9 section 14 rule).

| Table | Holds | Rule |
|---|---|---|
| `da_handoff_state` | request ID, step, own revision, last check result JSON (per path: fingerprint seen, fingerprint expected, result), updated time | one row per request |
| `da_handoffs` | request ID, record version, approach version, last tested build and kind, summary text, handed off by (developer ID), created time | one row per request, append-only (a request is handed off once) |
| `da_escalations` | escalation ID, request ID, trigger name(s) JSON, reasons JSON, open item text, `from_status`, capability, `senior_label`, `backup_label`, `taken_over_by`, guidance JSON (text, sent at, used_in), outcome (`open`, `returned`, `abandoned`), close note, closed by, opened at, closed at, own revision, the count that fired (triggers 1 and 4) | one open row per request (unique index on `request_id WHERE outcome = 'open'`); updated only to add reasons or guidance, take over, or close |
| `da_tester_finding_actions` | new action value `overruled`, actor `senior:<id>` | existing append-only table, no schema change |
| `da_requests` | new nullable column `follows_request_id` | section 4 |

Audit events (actor in brackets): `handoff_blocked` (system, which check, the list), `handoff_checked`
(system, per-path results), `handed_off` (developer), `follow_up_started` (developer, the old ID, on
the new request), `escalation_opened` (system, trigger, senior label, from_status), `escalation_reason_added`
(system), `escalation_routed` (system), `escalation_taken_over` (senior), `guidance_sent` (senior),
`guidance_used` (system, which prompt), `finding_overruled` (senior, finding, reason), `label_changed`
(reused), `escalation_closed` (senior, outcome, note), `escalated` (reused by Get help and Dispute).
Every status move is audited, as today. `Actor` gains the value `senior` (today: developer, system,
llm).

## 16. Testing without work

- **pytest, plain rules:** H2 findings check for every blocking case and the passing case; H4 compare
  with equal, changed, missing and extra-file facts (made-up fingerprints); the PR summary builder on
  a made-up request of each kind (new, enhancement with an open Unassigned row, enhancement with a
  freshness override and two not-covered items, a request with an overruled finding and a closed
  escalation), each line asserted, no test file path, no full folder path, length guard; each
  trigger with its switch on and off, the fire-once rule (X2), the add-to-open-row rule (X1); routing
  (named senior, backup, Unassigned, several capabilities); `is_senior` with the `env` list, the
  catalog labels and the placeholder; each senior action on a made-up database (overrule re-labels,
  guidance is added to exactly one next prompt and marked used, take over by a second senior refused,
  close returns to the stored status and only that status, abandon locks); the return rules of
  section 10 including the cap reset and the made-up-status guard; lock on and off; the metrics on a
  made-up database and on an empty one; HANDED_OFF refuses every developer action; the follow-up
  request carries `follows_request_id`.
- **Fake provider (home):** the Phase 6 to 9 fixed scripts, unchanged. Test-only switches force: a
  build that ends NOT_PASSING twice (trigger 1), a Tester unusable twice in two reviews (trigger 4), a
  scope conflict at confirm (trigger 2a), a file plan needing a protected file after the G9 cap
  (trigger 2b). The "next AI call" test asserts the fake client received the guidance block.
- **Pretend work server** (127.0.0.1:8070): one Generator fix round after guidance, proving the
  block travels through the onprem connector.
- **Playwright (cloud session only):** the private test folder stands in for the picker. A full
  request reaches READY_FOR_REVIEW (green), Ready for handoff passes the final check, the PR summary
  box exists and Copy summary puts the text on the clipboard (Playwright grants clipboard permission);
  then a second request: edit a planned file after the build, Ready for handoff is blocked naming the
  file. Inbox: open `/inbox` as a senior, send guidance, Return to developer, see the chat bubble on
  the developer page.
- **Smoke check:** after the Phase 9 items: Dispute a Must fix (fake switch) -> an escalation row
  addressed to the made-up senior -> overrule with a reason -> Return -> label Ready with warnings ->
  Ready for handoff -> final check passes -> HANDED_OFF with a summary under the length guard; and
  the Admin health report shows Handoffs 1 and Escalations 1 (Dispute).
- **Home check by Gian:** on `http://127.0.0.1:8050` with `DA_LLM_PROVIDER=fake`,
  `DA_SENIOR_IDS=senior-home-01` and `DA_DEVELOPER_ID=dev-home-01`: build a request, press Get help,
  open `/inbox` in a second tab (the home shell has no login: the builder adds a `?as=` query switch
  **in the home shell only**, never in `src/` code that goes to work, D-G), send guidance, Return, see
  the bubble, Ready for handoff, copy the summary into Notepad.
- **Work test** (`docs/handoff-work-test.md`, new, Command Prompt only): the steps for WF-1 to WF-3
  and the clipboard check in Chrome at work.

## 17. Out of scope

- **Review my code** (redesign 5.9): the third Home card's flow, its short Understand, "pick files",
  "Let AI fix". Parked as **Phase 10b**. The Home card stays as it is today.
- Gian's findings and enhancements list (own thread after this phase). Not guessed here.
- Any Git or Bitbucket action: commit, push, branch, PR creation, reviewer assignment, merge. The
  PR summary is text the developer pastes.
- Email or Teams notification to the senior (WF-2). Inbox only.
- A login screen or user directory (WF-1). The access switch is built; the source is not.
- A follow-up chat at HANDED_OFF ("Ask a follow-up question", demo). D-E.
- Copying anything from a handed-off request into its follow-up request (D-F).
- Senior editing of code, running builds, or refining on the developer's behalf. "Take over" is a
  marker and a conversation, not a second developer seat.
- An AI summary for the senior, or any new AI prompt. Guidance is appended to existing prompts only.
- Charts or per-developer tables on the Overview (Phase 11 out of scope stands).
- Changing the five trigger definitions or adding a sixth (redesign: fixed list).
- Reopening a HANDED_OFF request.

## 18. Decisions (D-x), for the chief's decision rule

None of D-A to D-L decides a work fact and each can be undone later. Where a choice depends on a work
fact, the column says so; the work fact itself is in section 19 with no recommendation.

| # | Question | Options (ranked) | Recommendation | Rule |
|---|---|---|---|---|
| D-A | Lock the developer's chat while an escalation is open? (idea parked 6 Nov, F1) | 1. **Lock**, as a rulebook switch `escalation_lock_chat` default on: composer disabled with "Waiting for your senior", reading and Re-scan still allowed; guidance or Close unlocks. 2. **No lock**: ESCALATION_REQUIRED behaves as today (read-only screen, Get help hidden), only the wording changes | **1**: a developer who keeps typing into a request a senior is reading creates two conversations; the lock makes "with the senior" mean one thing, and the switch lets Admin turn it off in a day if seniors are slow. Option 2 is safer only if seniors take days to answer, which the work test will show | To chief |
| D-B | What may the developer do when the final check finds a changed file? | 1. **Check my edits** (Phase 8: Layers A, B, C on his text, which then becomes last tested) or **Restore the tested version** (Phase 8 restore), then press Ready for handoff again. 2. Hand off anyway with a "differs from tested" warning in the PR summary. 3. Auto-run Check my edits inside Handoff | **1**: redesign 5.10 says the folder must **equal** what was tested; option 2 breaks that rule. Option 3 hides a minutes-long Layer C run behind a button called Handoff and may still fail | To chief |
| D-C | Final check in download mode (Phase 5 fallback)? | 1. **Upload folder to check** runs the same compare on the uploaded planned files. 2. Handoff refused in download mode. 3. Trust the last download | **1**: the fallback already exists for re-scan and the compare is the same function. Option 3 cannot see the laptop and would pass a folder the developer edited | To chief |
| D-D | What does a senior's Close offer? | 1. **Return to developer** (back to the stored `from_status`) or **Abandon request** (closed and locked, "Closed by senior"). 2. Return only. 3. Return, Abandon, or Hand off for the developer | **1**: some escalations end with "this request should not be built" (out of scope); without Abandon the request sits at ESCALATION_REQUIRED forever. Option 3 breaks "only the developer hands off" (decision 2 spirit: the PR is his) | To chief |
| D-E | Chat after HANDED_OFF? | 1. **Read-only line**, no text box; a follow-up request button. 2. The demo's "Ask a follow-up question" box answered by an AI call over the record and summary. 3. A text box that only appends notes to the chat (no AI) | **1**: option 2 is a new prompt with a new memory question (what does it read?) and Phase 10 has no AI work otherwise; option 3 writes to a locked request. A later phase can add 2 with a spec of its own | To chief |
| D-F | What does a follow-up request carry over? | 1. **Only the link** `follows_request_id` (shown on the Summary tab and in the PR summary). 2. Copy the record as draft v1 of the new request. 3. Reuse the same CVDA with a new record version | **1**: redesign 5.1 says a new CVDA linked to the old; copying a record invites stale criteria; option 3 undoes the lock. The link is enough for Discover to show "see CVDA-... first" later | To chief |
| D-G | Where does the inbox hang at home, and who counts as a senior? | 1. **`/inbox`** on the existing `dcc.Location` with a menu entry, like `/admin`; `is_senior()` with `DA_SENIOR_SOURCE=env` (`DA_SENIOR_IDS` plus the active catalog's senior labels, which at home are IDs) and a `codevision` placeholder; the home shell gets a `?as=<id>` switch for Gian's two-tab test. 2. A tab on the developer page shown only to seniors. 3. A separate Dash app | **1**: mirrors Phase 11's proven pattern (D-B, WF-2); seniors are also developers, so a separate path keeps the developer page untouched. The `?as=` switch lives in the home shell only (never copied to work). The work half is WF-1 | To chief |
| D-H | How is "out of scope" (trigger 2) detected without the AI deciding it? | 1. **Two plain-code facts only:** a `Scope conflict:` open item at record confirm, and a file plan needing a protected file or a path outside `allowed_folders` once the Phase 4 change cap is used up. 2. Ask the Generator "is this in scope?" in Approach. 3. Only the Understand scope conflict | **1**: redesign 5.11 says triggers are "checked by plain code"; the example "asked to write login code" is a protected file or zone path, which plain code sees in the file plan. Option 2 lets the model escalate. Option 3 misses the Approach case | To chief |
| D-I | What happens to Dispute and Get help when their switch is **off**? | 1. **The buttons stay**, nothing moves; the chat tells the developer to ask his senior directly; audited `escalation_switched_off`. 2. Hide the buttons. 3. Ignore the switch for these two (always route) | **1**: Admin owns the five switches (decision 7), but a developer must never be stuck without a message. Option 2 leaves a Must fix with no visible way out. Option 3 makes two of the five switches fake | To chief |
| D-J | Which rulebook version names the senior: the request's pinned one or the active one? | 1. **Active** version for routing and the inbox match; the label is stored on the row at that moment. 2. The pinned version | **1**: a senior change in the catalog (someone leaves) must take effect on open requests at once; everything else about the request stays pinned. Option 2 routes to a person who may be gone. Depends on WF-3 for the real labels | To chief |
| D-K | Status name for "with the senior" | 1. **Keep `ESCALATION_REQUIRED`** (built since Phase 3); the pill reads "ESCALATION REQUIRED, with <label>". 2. Rename to `ESCALATED` as in the redesign table | **1**: a rename touches every phase's moves, tests and audit history for a word. The redesign's intent (the request is with the senior) is met by the pill text | To chief |
| D-L | May a senior act on a row not addressed to him? | 1. **Yes** (filter Mine/All; every action records who did it). 2. Only the named or backup senior; Admin can re-route. 3. Only the named senior | **1**: a sick senior with no backup would block a developer; the audit trail names the actor anyway. Option 2 needs an Admin re-route screen (more build) and still blocks when Admin is away | To chief |

**D-A to D-L: Chosen by chief, 6.1 (option 1 each, 14 Nov 2026).** None is a work fact; D-G and D-J
are home-side only, the work half stays in WF-1 (#59), WF-3 (#58). Issues: WF-1 #59, WF-3 #58, WF-4 #60
(carried, needs-gian), WF-2 #70 (needs-gian, not a blocker), WF-5 #71, WF-6 #72 (needs-work-test).

"To chief": the chief writes "Chosen by chief, 6.1" (recommended option) or opens an issue, per
section 6 of the automation spec. D-G and D-J touch the home side of work facts WF-1 and WF-3; if the
chief reads that as deciding a work fact, he opens the issue instead.

## 19. Work facts (no recommendation, Gian decides)

The chief opens one issue per row with the label shown and builds everything around it.

| # | Question | Options (not ranked) | What Phase 10 builds meanwhile | Label |
|---|---|---|---|---|
| WF-1 (Phase 11 WF-2, issue #59, carried) | How the work login names a user, so the inbox knows who is a senior and matches him to a catalog label (bank policy, CodeVision login) | a. A list of user IDs in `.env` or a config file. b. A CodeVision role or group from its login. c. A table mapping login ID to catalog label. d. The bank's entitlement on the URL | `is_senior()` with `DA_SENIOR_SOURCE=env` (made-up IDs, `DA_SENIOR_IDS`) and a `codevision` placeholder that refuses; the catalog labels are made up and equal the IDs at home | `needs-gian` |
| WF-2 (Phase 11 decision 19, carried) | Notification to the senior: email, Teams, or nothing until bank approval (bank policy) | a. Inbox only. b. Email. c. Teams. d. Other | Inbox only. The row and audit event exist, so a sender is one function later | `needs-gian` |
| WF-3 (Q2, issue #58, carried) | One shared database for developers and seniors (CodeVision internals). The inbox only works across laptops if both use the same server database | a. One SQLite file on the OCP server. b. CodeVision's own database with the same tables. c. Other | Against the existing store; all rows keyed by request ID; nothing assumes two databases | `needs-gian` |
| WF-4 (Phase 9 WF-2, Phase 11 WF-3, carried) | The real capability list, named seniors and backups (bank org data) | Unknown. Not guessed here | The made-up seed catalog | `needs-gian` |
| WF-5 | Does the bank's Bitbucket PR description accept a plain-text block of this size, and does the work Chrome allow `navigator.clipboard.writeText` on `https` CodeVision (CodeVision internals, bank policy) | Unknown until the work test | Copy summary with a "select and copy" fallback line; `handoff_summary_max_chars` guard | `needs-work-test` |
| WF-6 | Does the work laptop's Chrome keep folder permission long enough for the final check after a Refine session, or does Reconnect appear every time (work laptop) | Unknown until the work test | Reconnect before the check (Phase 5 W4) | `needs-work-test` |

## 20. Done when (every line becomes a test, Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| 10-1 | READY_FOR_REVIEW, label green | the screen is drawn | **Ready for handoff** is shown; at NOT_PASSING, REVISION_IN_PROGRESS, BUILDING, TESTER_REVIEW and ESCALATION_REQUIRED it is not |
| 10-2 | a kept Must fix open | Ready for handoff | step `h_blocked_findings`; the chat names F-<n> and the whole list; nothing read from the folder; audit `handoff_blocked` |
| 10-3 | a Should fix neither accepted nor fixed | Ready for handoff | blocked naming it with "Fix it or Accept, with reason" |
| 10-4 | label Unable to assess | Ready for handoff | blocked with "Run the Tester review again" named |
| 10-5 | findings pass, workspace needs permission | Ready for handoff | Reconnect is offered first; after it the check runs |
| 10-6 | every planned file equals last tested | the final check runs | `h_done`; status HANDED_OFF; `da_handoffs` row; audit `handoff_checked`, `handed_off`; one transaction |
| 10-7 | one planned file edited after the last test | the final check runs | `h_blocked_folder` naming it "Changed since the last test"; buttons Re-scan and check my edits, Restore the tested version, Get help; nothing written |
| 10-8 | 10-7 then Check my edits passes | Ready for handoff | the check passes (his text is now last tested) |
| 10-9 | a planned file missing | the final check runs | blocked naming it "Missing" |
| 10-10 | download mode (D-C) | Ready for handoff | Upload folder to check runs the compare on the uploaded planned files only |
| 10-11 | HANDED_OFF | any developer action (Refine, Build, Dispute, Accept, Change folder, a chat message) | refused with the locked message; every tab still readable; `ALLOWED_MOVES[HANDED_OFF]` is empty |
| 10-12 | HANDED_OFF | Start a follow-up request | a new request with `follows_request_id` set; its Summary tab shows "Follows CVDA-..."; nothing copied; audit `follow_up_started` |
| 10-13 | a fake card-1 request handed off | the PR summary is built | lines 1, 4 to 9, 12, 13 as section 5; line 10 "not applicable (new code)"; no `tests/` path; no folder path; under `handoff_summary_max_chars` |
| 10-14 | a fake enhancement with an open Unassigned row, a freshness override and two not-covered items | the PR summary is built | line 2 says "picked by developer, not yet confirmed by Admin"; line 8 has the override; line 10 lists both with "Check manually" |
| 10-15 | one planned file hand-edited (scanned text equals last tested) | the PR summary is built | that file's line has "edited by developer"; the others do not |
| 10-16 | a zone warning Login and a catalog senior | the PR summary is built | line 9 names the zone and the senior as required reviewer |
| 10-17 | a summary over the guard (test-built) | built | criteria shortened to counts, a note says so, every other line kept |
| 10-18 | `h_done` | Copy summary is pressed (Playwright) | the clipboard holds the summary text; without clipboard permission the "select and copy" line shows |
| 10-19 | `h_done` on a workspace with no `.git` (Phase 5 information) | the chat is drawn | the ZIP-copy wording; with `.git` the clone wording; no Git command anywhere |
| 10-20 | two builds in a row ending NOT_PASSING, `cap_hit_twice` on | the second build ends | ESCALATION_REQUIRED in the same transaction; a `da_escalations` row with trigger `cap_hit_twice`, `from_status` NOT_PASSING, the count 2; chat names the senior label; audit `escalation_opened` |
| 10-21 | 10-20 with the switch off | the second build ends | status NOT_PASSING; no row; audit `escalation_switched_off` |
| 10-22 | a third NOT_PASSING after 10-20's row was returned (count reset) | the build ends | no new row (count is 1) |
| 10-23 | a scope conflict open item at Confirm, `out_of_scope` on | the record is confirmed | a row with trigger `out_of_scope` naming the conflict |
| 10-24 | a file plan needing a protected file with the G9 cap used up | the approach is refused | a row with trigger `out_of_scope` naming the path; with the cap not used up, no row |
| 10-25 | a Must fix | Dispute with a reason, `dispute` on | the existing move plus a row with trigger `dispute`, open item `Disputed Must fix: F-<n>` |
| 10-26 | 10-25 with `dispute` off | Dispute | no move, no row, the Must fix stays open, the chat says disputes are not routed and offers Get help |
| 10-27 | two reviews of one request ended Unable to assess, `tester_unable_twice` on | the second ends | a row with trigger `tester_unable_twice` and the review numbers; a third Unable does not open another (fires again at 4) |
| 10-28 | any Get help button (Understand checkpoint, Discover, Approach, Workspace, Build, Refine, Enhance, Handoff) | pressed with `get_help` on | the existing open item plus a row with trigger `get_help`; with it off, no move, the "ask your senior directly" line |
| 10-29 | an open row | a second trigger fires on the same request | no second row; the reason is added; audit `escalation_reason_added` |
| 10-30 | an enhancement in capability Limits (named senior set) | a row opens | `senior_label` is the Limits senior and `backup_label` the backup, read from the **active** version |
| 10-31 | a new request whose first planned file matches no capability, or a capability with no senior and no backup | a row opens | addressed to "Unassigned"; it appears in every senior's inbox under the heading; Overview Needs attention says "1 escalation has no named senior" |
| 10-32 | a request escalated before this phase (no row) | the inbox loads | a row is created and routed; audit `escalation_routed` |
| 10-33 | `DA_SENIOR_SOURCE=env`, the user in `DA_SENIOR_IDS` or equal to an active catalog label | `/inbox` is opened | the list shows; a user in neither sees "This page is for capability seniors."; `codevision` logs the placeholder line |
| 10-34 | rows for two seniors | Mine / All | Mine shows only rows whose senior or backup label is me (plus Unassigned); All shows every open row; Show closed adds closed ones |
| 10-35 | a row | opened | the request's chat and tabs are shown read-only; no developer button works from the inbox |
| 10-36 | a row with an open Must fix making the label Not passing | Overrule with a 20-character reason | an `overruled` action with actor `senior:<id>`; label Ready with warnings; audit `finding_overruled`, `label_changed`; status unchanged; the Tests tab shows "Overruled by" |
| 10-37 | a row | Send guidance | the text is on the row and in the developer's chat as a senior bubble; the next AI call of the flow (fake client) contains the guidance block once; the call after it does not; `used_in` set; audit `guidance_sent`, `guidance_used` |
| 10-38 | a row | Take over by A, then Take over by B | A is recorded; B is refused with "Taken over by A"; the developer's chat names A |
| 10-39 | a row from NOT_PASSING | Close, Return to developer | status NOT_PASSING; the open item cleared; `not_passing_in_a_row` is 0; the Refine box works again; audit `escalation_closed` with the note |
| 10-40 | a row from APPROACH_PROPOSED | Close, Return | status APPROACH_PROPOSED and the Approach step is the one it was at |
| 10-41 | a row | Close, Abandon | status stays ESCALATION_REQUIRED, outcome `abandoned`, the request is locked like HANDED_OFF, "Closed by senior" in My recent requests |
| 10-42 | a row with a made-up `from_status` (test-built) | Return | the section 10 guard picks READY_FOR_REVIEW, APPROACH_PROPOSED or READY_FOR_CONFIRMATION and audits the note |
| 10-43 | an open row, `escalation_lock_chat` on | the developer page is drawn | the composer shows the waiting line, no button; Re-scan still reads; after Send guidance or Close the composer is back |
| 10-44 | `escalation_lock_chat` off | the developer page is drawn | the page behaves as ESCALATION_REQUIRED did before this phase (read-only screen, Get help hidden) |
| 10-45 | an open escalation | Ready for handoff (test-built, direct call) | refused with "A senior is looking at this request." |
| 10-46 | any handoff or inbox action | sent with an old revision | refused with the stale message |
| 10-47 | a rulebook version saved before Phase 10 | loaded | `escalation_lock_chat` true, `handoff_summary_max_chars` 6000; the Admin Build and test tab shows the new switch and the Advanced limit |
| 10-48 | a database with 2 handoffs, 3 escalations (one open 3 days, two closed) | the Overview health report | Handoffs 2 with the share; Escalations 3 grouped by trigger, open 1, closed 2, the average hours; `GET_HELP_LABEL` appears nowhere; an empty database says "No data yet" for both |
| 10-49 | a request escalated before this phase with a Get help open item and no row | the health report | counted as Get help from the audit, as today |
| 10-50 | the inbox modules | imported | nothing imports from `callbacks/screen_callbacks/da_developer_assistant_page_callbacks`; the developer page layout functions are reused read-only |
| 10-51 | the whole phase | any action | no new AI prompt file; the only prompt change is the optional guidance block in the four existing builders |
| 10-52 | the smoke check | run | Dispute -> row -> overrule -> Return -> Ready for handoff -> HANDED_OFF with a summary; Handoffs 1, Escalations 1 |
| 10-53 | Playwright with the private test folder | a green request, Ready for handoff, Copy summary; a second request edited after the build, Ready for handoff | HANDED_OFF with the clipboard text; blocked naming the file |
| 10-54 | Playwright as a senior | `/inbox`, Send guidance, Return | the developer page shows the bubble and the composer |

Plus: `pytest` 0 failures, `ruff check` 0 problems, smoke check passes, code reviewer 0 Must fix, and a
home check by Gian on `127.0.0.1:8050` (two tabs: developer and `/inbox`).

## 21. Open items

- **11c must be merged first** (section 13 edits `da_admin_metrics.py`). If 11c is still open when
  this build starts, the plan puts section 13 last and the chief rebases.
- **Phase 8 `last_tested_kind`:** the builder confirms which kinds (`build`, `check`, `restore`)
  exist and that each leaves per-path fingerprints the final check can read (section 2 H4). If a
  `restore` kind stores none, the check reads the restored build's code rows.
- **Hand-edited detection** (Words table) is a definition, not SQL; the builder confirms it against
  `da_workspace_files` and `da_refine_tested` in the plan. If a simpler marker already exists in the
  Phase 8 code (for example `his lines` per file), use it.
- **"Out of scope" (b):** the Phase 4 refusal path for a protected file after the G9 cap must exist
  as one function the trigger can hook; if Phase 4 only shows a message, the plan adds the hook and a
  test, nothing more.
- **Guidance into prompts:** the four builders (Approach, Generator fix round, Refine lane, Tester
  review) each need one optional field. The "no code in the Tester prompt" and "no chat in the lane
  prompt" tests of Phases 6 to 8 must still pass: guidance is senior text, not chat and not code,
  and the tests say so explicitly.
- **Senior actor in the audit:** `Actor` becomes `developer | system | llm | senior`. Phase 0 tests
  that enumerate actors are updated, not loosened.
- **Redesign status name** `ESCALATED` vs built `ESCALATION_REQUIRED`: D-K. If Gian wants the rename,
  it is its own small fix after this phase.
- **Demo out of date** for Handoff (tests path, full folder path, follow-up chat box). The demo is
  not changed by this phase.
- **Phase 10b (Review my code)** will need: a short Understand, "pick workspace and files", a Handoff
  that works with no approach version (the file plan is his picked files). Section 5 line 7 and
  section 8 step 1 should then accept "no approach"; a note in the plan, no code now.
- No photos needed for this spec. WF-1, WF-3 and WF-5 are questions for the CodeVision team or the
  work test, not photos.

## 22. Files the builder will touch (for planning, not a limit)

`pydantic_classes/da_models.py` (HANDED_OFF, moves out of ESCALATION_REQUIRED, `follows_request_id`,
`senior` actor), `da_handoff_models.py` and `da_escalation_models.py` (new), `da_rulebook_models.py`
and `data/da_rulebook_seed.json` (two fields), `agents/da_handoff_flow.py` (new: H1 to H7, the final
check), `da_handoff_summary.py` (new: section 5), `da_escalation_triggers.py`, `da_escalation_routing.py`,
`da_escalation_flow.py` (new: the shared `escalate` helper, the four senior actions, return rules),
`da_senior_access.py` (new), the existing `request_help` functions (Approach, Workspace, Build, Refine,
Enhance, Understand, Discover) and `da_tester_flow.dispute_finding` (through the shared helper),
`da_build_loop.py` (trigger 1 hook), `da_tester_flow.py` (trigger 4 hook, overrule re-label),
`da_understand_flow.py` and `da_approach_flow.py` (trigger 2 hooks), the four prompt builders
(guidance block), `da_admin_metrics.py` and `db_tbl_da_metrics.py` (section 13), `da_admin_forms.py`
(section 12), `db_table_functions/db_tbl_da_handoff.py` and `db_tbl_da_escalation.py` (new),
`db_tbl_da_requests.py` (the column), `layouts/da_developer_assistant_page.py` and the page callbacks
(Ready for handoff, lock, HANDED_OFF, Audit tab box, senior bubbles), `layouts/da_inbox_page.py` and
`callbacks/screen_callbacks/da_inbox_page_callbacks.py` (new), `web/da_web_components.py` (summary box,
Copy summary clientside), `web/da_home_web_server.py` (menu entry, `/inbox`, the `?as=` switch),
`configs/da_config.py`, `.env.example`, `da_smoke_check.py`, `README.md`, `CLAUDE.md` ("Current
phase"), `docs/handoff-work-test.md` (new, Command Prompt only), and the matching tests.
