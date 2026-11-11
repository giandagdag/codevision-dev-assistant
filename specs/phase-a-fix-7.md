# Phase A fix 7: standing orders (the team answers the usual blockers itself)

Version 0.9 DRAFT, 11 Nov 2026 (SGT). Waiting for Gian to choose D-A to D-E (section 5).
Written in the project chat after #51. Gian: "Can't we automate this? I usually follow through your
instructions for such blockers." He chose standing orders now, a cloud troubleshooter maybe later.
Branch `phase-a-fix-7` (from `auto/phases-7-10`). PR into `auto/phases-7-10`; **Gian merges it**
(it changes the team's machinery). Build it the normal way: plan, plan review, build, code review,
pytest, ruff, smoke check. Build in a **cloud** session. **Do not touch `phase-8-fix-1`.**

## 1. Why (what Gian answered so far)

| # | Blocker | Gian's answer | Pattern | Team stopped for |
|---|---|---|---|---|
| #31 | Builder stopped for size: continue or split into 8b? | Continue, same spec | Keep the approved spec | ~2 h |
| #33 | Refine buttons drawn but not wired: wire now or defer? | Wire all now, fix the Should fix items too | Finish the approved scope | hours |
| #36 | PR conflict with `auto/phases-7-10` | Merged and fixed by hand | Git housekeeping | ~3 h |
| #40 | How is Admin told about a new Unassigned file? | Option a: in-app queue only, for now | Smallest in-app option | hours |
| #48 | Builder cannot switch branch | Merged `auto/phases-7-10` in (PR #49) | Git housekeeping | ~2 h |
| #51 | B6 cause not found after 2 tries | Cause found in the cloud; meanwhile the other 7 steps sat idle | Park one step, keep going | ~2 h so far |

**Common thread:** 6 of 7 answers follow a rule Gian would give every time. Only work facts, things
that cannot be undone, and real product choices need him. AS400 comparison: a reply list
(WRKRPYLE) with standing answers for known messages, so the job does not sit in MSGW for them.

## 2. What we build

| # | Piece | What it does |
|---|---|---|
| S1 | **Standing orders table** in `.claude/agents/chief.md` (the decision rule table gets the rows below) and the builder's part in `.claude/agents/builder.md` | The rules in section 3. Each use is written as one Log line `SO-n: <what was done>` and, in the PR body, a "Standing orders used" list |
| S2 | **Non-blocking label `gian-later`** | A question Gian should see, but the team does not wait for. `ops/chief_tick.py` `LABELS` gets it (the issue command accepts it). The board shows `📌 For you later: N` as a line under the top line, never `WAITING FOR YOU`. Only `needs-gian` stays blocking |
| S3 | **Gian can still overrule** | `ops/answers.py`: Gian's comments on open `gian-later` issues are read the same way as on `needs-gian` (fix 4 G2), so a reply wakes the chief. The chief acts on it and closes the issue |
| S4 | **Parked steps** (builder) | When SO-2 fires, the builder writes `PARKED step K: <reason, what was tried>` in the plan file, commits, and continues with the next step. `chief_tick.py next` text names the parked step |
| S5 | **Docs** | `docs/automation.md`: the standing orders, the two labels, how to overrule |

## 3. The standing orders

| # | Situation | The team does | Instead of |
|---|---|---|---|
| SO-1 | Branch behind `auto/phases-7-10`, cannot switch, or a PR conflict | Builder merges `auto/phases-7-10` into its branch. Conflicts in `docs/`, `specs/`, `tests/`, `ops/` text or plan files: resolve, keeping both sides. Conflicts in `src/` logic: resolve only when one side is clearly a superset, then run the full tests. Still unclear: `needs-gian` | `needs-gian` (#36, #48) |
| SO-2 | One step stuck: cause not found, or a test still failing after 2 fix attempts | Park that step (S4), open `gian-later` with what was tried, **continue the other steps**. Before code review: a parked step whose bug is **Critical or High** in the spec makes the builder stop and ask (`needs-gian`); Medium or lower goes into the PR as a known gap | Stopping the whole phase (#51) |
| SO-3 | Phase too big for one run, or "continue or split?" | Continue on the same branch with the approved spec | `needs-gian` (#31) |
| SO-4 | Finish the approved scope now, or defer part of it | Finish it now, including the code review's Should fix items | `needs-gian` (#33) |
| SO-5 | A product choice the spec does not cover, where one option stays inside the app and needs no work fact, no new library and no message outside the app | Take that option, write "Chosen by chief, SO-5" in the spec, open `gian-later` so Gian can overrule | `needs-gian` (#40) |
| SO-6 | Work facts, bank policy, on-prem models, `.env`, `main`, deleting, anything that cannot be undone, a spec with no recommendation | **Unchanged: stop and ask** with `needs-gian` | n/a |

When unsure which row applies, SO-6 wins: ask.

## 4. Edge rules

- Standing orders never touch `main`, never force-push, never delete branches or files (safety hook unchanged).
- A parked step is never silently dropped: it stays in the plan, in a `gian-later` issue, and in the PR body.
- At most 2 parked steps per phase. A third: stop and ask (`needs-gian`).
- `gian-later` issues never make the tick return `waiting` and never count for the stall alarm.
- No change to the guard, usage stop lines, or who merges what.

## 5. Choices (D-x). Recommended: option 1 for all

### D-A Where the standing orders live
1. **Rows in the existing decision table in `chief.md`, plus 3 lines in `builder.md`.** One place, read every run anyway.
2. A separate `docs/standing-orders.md` both agents read. Cleaner, but one more file read per run (tokens).

### D-B How "flag me, keep going" works
1. **New label `gian-later`** (S2, S3). The board stays honest: WAITING FOR YOU only when the team really waits.
2. Reuse `needs-gian` with a `Next:` line that does not wait. Simpler, but the board shows WAITING FOR YOU while the team works.

### D-C A parked Critical or High step at code review
1. **Stop and ask before code review.** The PR never merges with a parked serious bug without Gian.
2. Go on to review and PR, keep the issue open. Faster, but a known serious bug could reach `auto/phases-7-10`.

### D-D Product choices the spec does not cover (SO-5)
1. **The chief takes the in-app, no-work-fact option and records it, overrulable.** (#40 pattern.)
2. Always ask (today).

### D-E When fix 7 goes live
1. **Build now in the cloud; Gian merges it in the same window as fix 6** (after the `phase-8-fix-1` PR
   merges, before Phase 10, during the fix 6 switch-over). One switch-over, one sitting.
2. Merge it now into `auto/phases-7-10`; it reaches the laptop only when the team next switches branch.

## 6. Acceptance criteria (Given / When / Then)

- AS-1 Given `chief.md`, then the decision table has rows SO-1 to SO-6 with the wording of section 3,
  and "When unsure, SO-6" (test reads the file).
- AS-2 Given `builder.md`, then it has the SO-1, SO-2 (park and continue, at most 2) and SO-4 lines.
- AS-3 Given `chief_tick.py issue --label gian-later --title t --body b`, then the issue is opened with
  that label (fake gh records it); an unknown label is still refused.
- AS-4 Given only a `gian-later` issue open and `Next: wait for Gian`, when the tick runs, then it does
  **not** return `waiting`.
- AS-5 Given one open `gian-later` issue, then the board shows `📌 For you later: 1` and its top line
  is not `WAITING FOR YOU`.
- AS-6 Given a new owner comment on an open `gian-later` issue, when the tick runs, then the chief is
  woken with that answer (same prompt as fix 4 G2).
- AS-7 Given `Next: none`, no `needs-gian` issue and one `gian-later` issue, then the stall alarm still
  fires (a `gian-later` issue does not mean "waiting on purpose").
- AS-8 Given the ops test suite, then the real `STATUS.md`, ledger and `logs/workers/` are unchanged.

## 7. Out of scope

- A cloud troubleshooter that investigates blockers by itself (Gian: maybe later).
- Anything in `src/` (the product).
- Changing SO-6 cases, the guard, stop lines, or merge rights.

## 8. Open items

- O1: the chief's judgment of "Critical or High" relies on the spec's severity column. Specs without
  one: treat the step as High (ask).
- O2: if Gian finds the team takes a standing order he would not, he comments on the `gian-later`
  issue and the row is changed in a later fix.
