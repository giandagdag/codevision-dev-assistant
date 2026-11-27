# Fix G9 finish: Step 8 as option (a), and every open G9 gap closed before merge

Version 1.0 APPROVED, 27 Nov 2026 16:30 SGT. Gian, 16:19: "I would prefer option A. It emphasizes
potential gaps on the understanding. Go ahead and proceed. I give you full authority." He also
asked that every outstanding fix is included. This answers issue #119 and the Step 8 open question
in `specs/fix-g-9-plan.md`.

Same branch `phase-g-fix-9`, same PR #118. Builder: commit this spec as `specs/fix-g-9-finish.md`
as the first commit of this stage. Add a `## Finish steps` list (F1 to F9) to `specs/fix-g-9-plan.md`.
Commit subjects "G9 finish step N". Runs of at most 3 steps, tests with each step.
**Gian's approval for #119: a new review cycle for this finish, up to 3 code review rounds**
(the 3 earlier rounds are spent). Then the chief merges PR #118 into `auto/phases-7-10`.

## Where G9 stands (27 Nov 13:51)

- Steps 0 to 7 and 9 to 18 are built. Step 8 was skipped (open question).
- Review round 2: 7 Must fix items, all fixed (dbb8ec5, 6251275).
- Review round 3: 3 Must fix items. **The list was lost**: the builder wrote it to
  `ops/state/worker_note.md`, which no longer exists, and only a cut-off log line is left.
- Last full pytest: passed at 11:36 (4,512 tests, 53 min). The 13:23 run hit the background time
  limit and gave no result.
- Known gaps from the PR body and `specs/parked-items.md` (G9-a, G9-b): every one is in scope below.

## F1. Step 8 as option (a): Understand finds the gaps before Confirm (T2, G9-9)

| # | Piece |
|---|---|
| F1a | **The gap check goes in the same rule check call (U2), no second AI call.** The reply gains `"uncovered": [{"case": "<input or situation, max 120>", "question": "<what should happen?, max 200>", "suggested_criterion": "<Given/When/Then, max 250>"}]`. The prompt asks for inputs and situations that a developer of this change should decide and that no criterion covers: no input or no arguments, empty values, wrong type, too long, missing file, the error path of each step. Max 5, most important first. Read with G5's forgiving reader |
| F1b | **Plain code keeps only real gaps:** drop an item whose case is already named, ignoring case and word order, in a criterion's given part, a decision (DD-n), the out-of-scope list or an earlier "Not needed" answer. Drops are logged as a count, never the AI text |
| F1c | **Open gaps block Confirm**, listed by `confirmation_gate_problems` next to rule conflicts. Chat: "Gap: <case>. <question>" with buttons: **Add this criterion** (adds the suggested criterion as the next AC-n, then the check runs again), **Change it myself** (opens the criteria field), **Not needed** (developer gives a reason, 10+ characters; recorded as an out-of-scope line "Not needed: <case>: <reason>", audited `gap_not_needed`) |
| F1d | **Same gate on every change** (U8): a v2 or later requirement runs the gap check too |
| F1e | **Approach backstop stays:** the planner still returns `criterion` and `covered_by` per case. A planned case with no covering criterion is not planned and shows on the Tests tab as "Not covered by the requirement: <case>" (FYI). Old requests past Understand are not re-checked (U9) |
| F1f | The rule check failure message (edge rule) covers both: "The rule and gap check could not run: Try again". Confirm stays blocked |

Acceptance: **G9-9** (rewritten): given the CVDA-0006 uppercase CLI record with AC-1 and AC-2 only and
a fake rule check that returns the gap "no arguments", when the developer presses Confirm, then
Confirm is refused and the chat shows the gap and its question. **G9-9b**: Add this criterion adds
AC-3, the check runs again, and with no gaps Confirm works. **G9-9c**: Not needed with a reason
records the out-of-scope line and the audit, and Confirm works. **G9-9d**: a fake gap that a
criterion already covers is dropped by plain code. **G9-9e**: a planner case with no covering
criterion shows the FYI line and no test.

## F2. Find the 3 round-3 Must fix items again

First step of the stage: run one code review of PR #118 as it stands (it counts as round 1 of the
new cycle) and fix what it marks Must fix. Write the review result into `specs/fix-g-9-plan.md`
under "Finish review", not only into `ops/state/`, so it cannot be lost again.

## F3. Required results for command-line pairs (B3, parked G9-a)

CVDA-2026-0006 is a command-line tool, so this cannot stay parked. In the sandbox, after Layer A,
run each command-line pair from the required results list as a child process of the entry script
with the literal arguments (the 60 s limit, the same Job Object and clean environment as the test
runner). Compare stdout with trailing spaces and line ends stripped, and the exit code ("non-zero"
in a criterion means any non-zero value). A mismatch goes back to the Builder as a repair note with
the criterion ID, expected and actual, and the Tester is not called that round. Remove G9-a from
`specs/parked-items.md`.
Acceptance **G9-12b**: given "given no arguments, output NO INPUT PROVIDED, exit code non-zero"
and fake code that prints "Error" and exits 0, the check catches it before the Tester.

## F4. Admin tab click without a page reload (W26-8, parked G9-b, G9-18)

Decided approach: the tab click writes the address in a **clientside callback with
`window.history.replaceState`**, not through `dcc.Location` (so Dash never sees an address change and
never rebuilds). The open tab is kept in a `dcc.Store`. On first load and on F5 the Admin page reads
`?tab=` from the real address. `replaceState` (not `pushState`) means no new history entry and no
popstate. The "Opening..." guard (S5) must key only on a pathname change.
Test the exact order that broke before: Admin → each tab → Home → Start a change request shows the
Understand page within 5 s; and Admin → tab → F5 keeps the tab.
If this still fails after 2 tries, keep the current code (the tab is already kept, only the flash
is left), record it as Low in `specs/parked-items.md` with the failing order and the tries, and go
on. Do not open a question for it.

## F5. Rule conflicts and gaps in the v2 refine lane (U8)

The v2 and later lane shows conflicts and gaps with the same buttons as Understand (Use the
suggested wording, Change it myself, Ask for an exception, Add this criterion, Not needed), not as
an error only. Acceptance: G9-6 with the buttons pressed.

## F6. Flag-for-review zones as rule conflicts (U3)

A G5 zone finding also shows as a conflict `ZONE:<name>` with the same shape and buttons. The G5
safety gate is unchanged.

## F7. Round budget and the referee (T5)

A round spent only on a referee rewrite must not count (T5). The round-2 FYI says it still counts:
fix it, with a test that the round counter is unchanged after a referee-only round.

## F8. Browser tests for what was checked only by hand

Copy the live-build server set-up from `tests/test_da_poll_browser.py` and add Playwright tests for:
G9-15 (See the findings pressed 3 times with scrolling, table in view each time), G9-16 (Tests tab
still open after a Dispute), Inbox Approve and Reject of an exception (G9-3), and the F1 buttons.
Also fix the small round-2 FYI items (missing space after `=`, the stale check result).

## F9. Finish

1. Full pytest **on one commit, split into groups that each fit the background time limit** (for
   example `tests/ops`, `tests/test_da_[a-l]*`, `tests/test_da_[m-z]*` plus the rest). Every group
   must pass on the same commit; list the groups and counts in the PR body. Never report a pass from
   a cut-off run. `ruff check .` and the smoke check.
2. PR #118 body: replace "Known gaps" with what F1 to F8 closed, and list anything still parked with
   its parked-items number.
3. The chief merges PR #118 into `auto/phases-7-10`, closes #119, and marks Fix G9 done in
   `ops/work_queue.json`.

## Edge rules

All G9 edge rules stay: no new library or table, fake AI at home only, AI text only in
`logs/da_rejected_replies.log`, labels from constants, AF-2 label scan passes, never touch `main`.
Old records still read (no `uncovered` key means no gaps).

## After G9

Nothing else is approved. Gian retests at work (the G9 cases, the CVDA-0006 and CVDA-0009 requests
again), then undoes the work-laptop hand edits (`OPTION_LIMIT = 300`, `_library_problems` split,
`MAX_SKIPPED_SHARE = 1.0`, `SNIPPET_LIMIT = 2000`). Older parked items (P22, P28, P29, P31 layout,
P32, P34, G5-b, G5-c, G6-b) stay parked until Gian picks them.
