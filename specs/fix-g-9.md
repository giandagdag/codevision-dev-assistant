# Fix G9: the requirement is the referee, and the requirement must follow the rulebook

Version 1.0 APPROVED, 26 Nov 2026 21:15 SGT. Gian, 21:08: "Ok go. See the findings, go ahead and fix."
Written in the project chat from `claude/work-test-2026-11-26-findings.md` (W26-1 to W26-8) and
Gian's direction (20:53, 21:08):
- An agreed build must not wander from the agreed requirement, and the developer must not be asked to
  pick "fix the code or fix the test". The requirement decides, the app applies it.
- **The requirement itself must follow the rulebook.** A request that breaks a rule must not pass
  Understand.
Every choice below is decided; no D-x is open.

Branch `phase-g-fix-9`, cut from the newest `origin/auto/phases-7-10` **after Fix G8 is merged**.
Queue order: **G7, then G8, then G9.** Builder: commit this spec as `specs/fix-g-9.md` as the first
commit on the branch. Normal build: plan `specs/fix-g-9-plan.md` with a `## Steps` list, plan review,
small steps with tests, code review (max 3 rounds), full pytest, ruff, smoke check, screenshots.
Commit subjects "G9 step N". PR into `auto/phases-7-10` with `--body-file`; the chief merges.
Build order inside G9: Part 1, Part 2, Part 3, Part 4, then Part 5.

## 0. What Gian saw (26 Nov)

| Request | What happened |
|---|---|
| CVDA-2026-0006 uppercase CLI, build 2 | Layer B 3 of 4 in all 3 rounds, round cap hit twice, escalated to the senior. Failing frozen test T-4 (AC-2) "Given no arguments, expect error message and non-zero exit" expected the literal text `'Error message'`; the code printed `'NO INPUT PROVIDED'`, which is what AC-2 asks for empty input. "Change what it does" rewrote the request and the same kind of test came back |
| CVDA-2026-0009 password check | F-1 Must fix (CV-PY-001) whose own message says the error text "complies with the rule". F-2 and F-3 Must fix (Check 4, DD-1): the code raises `ValueError` or returns None, while the criteria require returning 'VALID PASSWORD' / 'INVALID PASSWORD' |
| Both | Also: the requirement "print NO INPUT PROVIDED" sits next to rule CV-PY-001 (error messages are plain sentences). Understand never compared the two, so the conflict surfaced only at build time |

## 1. Causes (read 26 Nov at `origin/auto/phases-7-10` da159ef)

| # | Cause |
|---|---|
| C1 | `src/data/da_understand_prompt.md` gives Understand only the charter's purpose, in scope, out of scope and glossary. It never sees constraints, architecture principles, judgement rules (CV-PY-xxx), approved or blocked libraries, or flag-for-review zones. `da_understand_checks.refresh_scope_conflicts` only matches out-of-scope items word for word |
| C2 | `src/data/da_build_tests_prompt.md`: the test writer gets the record and the accepted case list. A case written in loose words ("expect error message") is turned into a literal. No plain-code check compares a frozen test's expected values with the criteria before freezing |
| C3 | The test planner may add cases the criteria do not cover (no arguments) |
| C4 | Repair rounds keep changing the code against a frozen test that the code cannot satisfy; nothing asks whether the test itself is backed by the requirement |
| C5 | The Builder follows the common Python habit (raise on bad input) and the coding rules over a criterion that asks for a returned value. The required results are not given to it as a hard list, and nothing checks them before the Tester runs |
| C6 | `da_tester_review.check_evidence` checks that the quoted line exists and the cite is allowed, not that the finding describes a problem. A finding that says the code complies is kept as Must fix |

## Part 1. The requirement must follow the rulebook (Understand gate)

| # | Piece |
|---|---|
| U1 | **Understand sees the whole rulebook.** The prompt adds: constraints, architecture principles, judgement rules (ID, title, why), approved libraries, blocked imports, flag-for-review zones (all from the active rulebook version, never seniors' names). Long lists are cut with a count note, like the tagger |
| U2 | **Rule check before Confirm.** When the record is complete (before the confirmation gate), one AI call ("rule check", role `interpreter`, fake script at home) reads the summary, every criterion and every decision against the rules and replies JSON: `{"conflicts": [{"criterion": "AC-2 or SUMMARY or DD-n", "rule": "<rule ID or CHARTER:out_of_scope:n or LIB:name or ZONE:name>", "why": "<max 200>", "fix": "<suggested wording, max 200>"}]}`. Read with G5's forgiving reader |
| U3 | **Plain-code checks too (no AI):** a criterion or summary that names a blocked import or a library not on the approved list; an out-of-scope item matched ignoring case and word order (not only exact); a destructive or flag zone without its required parts (G5 safety gate unchanged). These are conflicts with the same shape |
| U4 | **Plain code keeps only real conflicts:** the cited rule must exist in the active rulebook and the criterion ID must exist. Others are dropped (logged as count and kind, never the AI text) |
| U5 | **Conflicts block Confirm.** `confirmation_gate_problems` lists every open conflict. Chat: "AC-2 conflicts with rule CV-PY-001 (Error messages are plain sentences): <why>. Suggested wording: <fix>." Buttons per conflict: **Use the suggested wording** (the criterion is updated, the check runs again) and **Change it myself** (opens the field). The request cannot be confirmed while one is open |
| U6 | **Exceptions are the senior's, never silent.** A third button **Ask for an exception** sends one Inbox item to the capability's senior (Phase 10 routing) with the conflict and the developer's reason (required, 10+ characters). Approve records an exception `RX-n: <rule> allowed for <criterion>, approved by <senior>, <reason>` on the record (audited `rule_exception`). Reject returns it as an open conflict. The request waits at Understand meanwhile |
| U7 | **Exceptions flow down.** Approach, Build and Tester prompts list the `RX-n` lines. A Tester finding on an excepted rule for that criterion becomes FYI "Allowed by RX-n" (plain code, like `required_by`) |
| U8 | **Same gate on every change.** Requirement changes ("Change what it does", v2 and later) run the same rule check before the new version is confirmed |
| U9 | **Old requests:** a request already past Understand is not re-checked; the Summary tab shows "Rule check: not run (older request)" |

## Part 2. Tests come only from the requirement

| # | Piece |
|---|---|
| T1 | **The test writer sees the criteria word for word** (ID, given, when, then, exact values) next to each case, plus the decisions (DD-n) and exceptions (RX-n). Prompt rule: "Copy expected text and values from the criterion exactly. Never invent message text. If the criterion does not give an exact value, test only what it gives (for example the exit code, or that the output is not empty)" |
| T2 | **No invented cases.** Each planned case must name the criterion it tests, and its given part must be inside that criterion (plain check on the case's criterion ID; AI check of "inside" is part of the planner reply as `covered_by`). A case the criteria do not cover is not planned. If the planner thinks such a case matters, it becomes an **open requirement question at Understand** (for example "What should happen with no arguments?"), asked before the request is confirmed. For a request already confirmed, it is listed on the Tests tab as "Not covered by the requirement: <case>" (FYI, no test, no failure) |
| T3 | **Expectation check before freezing (plain code).** Every string literal used as an expected value in the test file (the third argument of `evidence(...)`, `assertEqual` and `assertIn` expected sides) must appear, ignoring case and surrounding spaces, in a criterion, a decision, an exception or the contract. A test that fails this is sent back to the test writer once with the plain reason ("T-4 expects 'Error message', which no criterion says"). Still failing: that case is dropped from the frozen set and shown as "Not covered: the test could not be written from the requirement" (FYI) and the developer gets the requirement question from T2 on the Summary tab. **The build never starts with a test that fails T3** |
| T4 | **Referee when the same test fails twice.** If the same frozen test fails in two rounds with the same actual value, the next round does not change code blindly. Plain code runs T3 on that test again with the current record. Not backed by the requirement: the test is rewritten once by the test writer (a logged exception to the frozen rule, audit `test_rewritten_by_referee` with old and new expected values), and Layer B runs again. Backed: the repair note to the Builder names the criterion and the exact expected value. **The developer is never asked "fix the code or fix the test"** |
| T5 | The round budget does not count a round spent only on a referee rewrite |

## Part 3. The Builder follows the required results

| # | Piece |
|---|---|
| B1 | **Required results list.** From the criteria, plain code builds a list of exact input to output pairs where the criterion gives them (for example `given 'hello world' -> output 'HELLO WORLD'`, `given '' -> output 'NO INPUT PROVIDED', exit code non-zero`, `check('abc') -> returns 'INVALID PASSWORD'`). The Builder prompt shows them under "These results are required. They beat coding habits and every rule except an exception RX-n" |
| B2 | Builder prompt rule: "When a criterion says the function returns a value, return it. Never raise instead. Raise only where a criterion or decision says an error is raised" |
| B3 | **Required results check before the Tester (plain code, in the sandbox):** after Layer A, each pair from B1 that can be run directly (a function call with literal arguments, or the CLI entry with literal arguments) is run once; a mismatch goes straight back to the Builder as a repair note with the criterion ID, expected and actual, and the Tester is not called for that round |
| B4 | Coding rules that seem to conflict with a criterion no longer pull the Builder away: the conflict was settled at Understand (Part 1) or excepted (U6) |

## Part 4. Findings must name a real problem

| # | Piece |
|---|---|
| F1 | **Compliance check (plain code):** a finding whose message says the code complies, meets, follows, satisfies or is in line with the rule, without a "but", "however" or "does not", is dropped with the reason "Not a problem: the finding says the code complies" (kept in the dropped list, as other dropped findings) |
| F2 | Tester prompt: "A finding names what is wrong and what to change. If the code follows the rule, write no finding" |
| F3 | **Readable cites (W26-4):** every cite shows its meaning on hover and keyboard focus: `DD-n` → "Design decision n: <question> → <answer>", `RU-n` → the reuse decision, `RX-n` → the exception, a rule ID → its title. The Check column shows the check's name ("Check 4 · Matches the agreement") |

## Part 5. Screen fixes

| # | Piece |
|---|---|
| S1 (W26-2) | Hint lines from constants: under **Re-scan**: "Reads your own edits so the Tester checks them." Under **Check my folder**: "Last step: confirms your folder still matches the tested version." |
| S2 (W26-3) | **See the findings** becomes a button that scrolls to the findings table every time it is pressed (clientside scroll into view), not a `#` link |
| S3 (W26-5) | Capability catalog: the **Missing backup** filter chip moves to the right end of the toolbar, labelled "Show: Missing backup", away from the search box |
| S4 (W26-6) | A redraw caused by a button on a tab (Accept, Dispute, Withdraw, Send disputes, Edit, Fix it) keeps that tab open. Only a step change chooses a new tab |
| S5 (W26-7) | "Opening..." only when the Developer Assistant page is the one showing (pathname check in the clientside callback). After any menu change, the request page always redraws. Playwright: Admin → Coding standards → Developer Assistant → Start a change request shows the Understand page, never "Opening..." after 5 s. Also Inbox → Home, Admin → Home, Home → request → Admin → back |
| S6 (W26-8) | Admin tab and view clicks update the address for F5 and links without a full Admin page redraw (write the address with no page rebuild; the Admin page callback rebuilds only on a pathname change or first load). Developer Assistant callbacks ignore address changes while another page is showing. Playwright: clicking each Admin tab never shows the Developer Assistant page, and F5 still keeps the tab |

## 2. Edge rules

- No new library, no new table (exceptions and rule-check results go in the request record JSON and the audit). Old records still read.
- Never show or log the AI's reply text outside `logs/da_rejected_replies.log`.
- The rule check (U2) is one AI call per Understand round at most; a call failure shows "The rule check could not run: Try again" and Confirm stays blocked (never skipped silently).
- The frozen-test rule stays, with one logged exception: T4's referee rewrite.
- Labels, chat lines and hints from constants; AF-2 label scan passes.
- Fake AI at home only; fake scripts cover every acceptance case. Never touch `main`.

## 3. Acceptance criteria (Given / When / Then)

| ID | Given / When / Then |
|---|---|
| G9-1 | Given a rule CV-PY-001 and a criterion "print NO INPUT PROVIDED on empty input" that the fake rule check flags, when the developer presses Confirm, then Confirm is refused, the chat names AC-2, CV-PY-001, why and the suggested wording |
| G9-2 | Given G9-1, when Use the suggested wording is pressed, then the criterion changes, the check runs again, and with no conflicts Confirm works |
| G9-3 | Given G9-1, when Ask for an exception is sent and the senior approves, then the record holds RX-1, the audit has `rule_exception`, Confirm works, and a later Tester finding on CV-PY-001 for AC-2 shows as FYI "Allowed by RX-1" |
| G9-4 | Given a criterion that names a blocked import, then a conflict appears without any AI call |
| G9-5 | Given the fake rule check cites a rule ID that does not exist, then that conflict is dropped |
| G9-6 | Given "Change what it does" on a confirmed request with a new conflicting criterion, then v2 cannot be confirmed until it is settled |
| G9-7 | Given a test whose evidence expects 'Error message' and no criterion says it, when tests are written, then the writer is asked again once; still wrong, the case is dropped as "Not covered" and the build starts without it |
| G9-8 | Given a test expecting 'NO INPUT PROVIDED' that AC-2 says, then T3 passes it |
| G9-9 | Given a planned case "no arguments" that no criterion covers, then it is not planned, and an open requirement question asks what should happen with no arguments |
| G9-10 | Given the same frozen test failing twice with the same actual value and not backed by the requirement, then the referee rewrites it once, audits `test_rewritten_by_referee`, and the round is not counted |
| G9-11 | Given the same test failing twice and backed by AC-1, then the repair note names AC-1 and the exact expected value, and nobody is asked to choose |
| G9-12 | Given a criterion "check('abc') returns 'INVALID PASSWORD'" and fake code that raises ValueError, then the required results check catches it before the Tester, with the criterion, expected and actual in the repair note |
| G9-13 | Given a finding "The error message is a plain sentence ... which complies with the rule", then it is dropped as not a problem; "complies with the rule, but the message names no fix" is kept |
| G9-14 | Given a finding citing DD-1, when hovered or focused, then the tooltip shows the decision's question and answer, and the Check column says "Matches the agreement" |
| G9-15 | Given the Tests tab, when See the findings is pressed three times with scrolling in between, then the findings table is in view each time |
| G9-16 | Given a Dispute on the Tests tab, then after the redraw the Tests tab is still open |
| G9-17 | Given Admin → Coding standards → Developer Assistant → Start a change request (Playwright), then the Understand page shows and no "Opening..." remains after 5 s |
| G9-18 | Given each Admin tab click (Playwright), then the Developer Assistant page never shows, and F5 keeps the tab |
| G9-19 | Given the catalog toolbar at 1366 and 1920 px, then the Missing backup chip is at the right end, not next to the search box |
| G9-20 | Given Re-scan and Check my folder, then each shows its hint line |
| G9-21 | AF-2 label scan passes on every new screen part |

## 4. Workarounds until G9 is merged

- W26-1: for a test like T-4, the senior's escalation answer is the way out today. New requests: word
  every failure case with its exact text and cover "no arguments" in the criterion yourself.
- W26-6: click the Tests tab again after a Dispute. W26-7: F5. W26-8: wait for the tab to settle.

## 5. Out of scope

- Re-checking requests already past Understand (U9).
- A bake-off of models for the Tester (open work fact Q9).
- Changing the number of repair rounds.
