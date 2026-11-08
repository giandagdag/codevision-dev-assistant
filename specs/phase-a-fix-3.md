# Phase A fix 3: no more silent stalls

Version 1.0 APPROVED, 8 Nov 2026 (17:31 SGT). Gian chose option 1 for D-A to D-D (section 5).
Written in the project chat after the 8 Nov stall.
Branch `phase-a-fix-3` (from `auto/phases-7-10`). PR into `auto/phases-7-10`; **Gian merges it**
(it changes the team's machinery). Build it the normal way: plan, plan review, build, code review,
pytest, ruff, smoke check. Build in a **cloud** session, never on the laptop while a team worker runs.

## 1. Why (what went wrong on 7 and 8 Nov)

| # | Blocker | Root cause | Lost |
|---|---|---|---|
| 1 | Merge denied 3x overnight | Permissions did not match the task | ~5 h |
| 2 | Builder stopped after step 6 of 15 "for size" | Phase too big for one run; the stop was a surprise, so it became a `needs-gian` question | ~2 h |
| 3 | Code reviewer killed | Builder (headless `claude -p`) started it in the background and ended its turn, which ends the process | review 0 of 3 |
| 4 | Chief idle 16:23 to 17:26 | Chief wrote `Running: ... Next tick: ...` instead of a `Next:` line, so `has_work()` said no work | ~1 h |
| 5 | 8 denied tool calls in 3 runs | Compound commands (`;`, pipes) and read-only tools (`grep`, `tail`, `git show`, the smoke check) are not in the allowlist | small, adds up |
| 6 | Fake "15 Jan 16:00" rows in the real ledger, `20270115-*-chief.json` in `logs/workers/` | An ops test writes to real paths | messy data |

**Common thread:** every failure was silent. "Stuck" looks the same as "nothing to do".
AS400 comparison: the job scheduler has no MSGW alert. A job waits and nobody hears it until someone
runs WRKACTJOB.

Already done by hand on 8 Nov (not part of this build, just keep it): line in `.claude/agents/builder.md`
"Headless rule: never start a subagent in the background".

## 2. What we build

| # | Piece | What it does |
|---|---|---|
| F1 | **Stall alarm** in `ops/chief_tick.py` | Plain Python, **zero tokens**. When a tick ends `idle`, check section 3. If stalled: one `needs-gian` issue titled `🔴 Team stalled: <reason>` (never a second one while one is open with the same title), one Log line, and the status board top line `🔴 STALLED: <reason>` (outranks IDLE and READY, below WAITING FOR YOU) |
| F2 | **`Next:` helper** | New command `chief_tick.py next "<text>"`: replaces the single `- Next:` line in STATUS.md (adds it under "## Where we are" if missing). Refuses empty text. `chief.md` and `builder.md`: always set the next step with this command, never by hand-editing |
| F3 | **Unpushed-commit check** | When `check_queue` records a finished, vanished or over-time worker, compare local `auto/phase-N` with `origin/auto/phase-N` (`git rev-list --count origin/X..X`, no fetch needed beyond what exists). Ahead > 0: Log line `UNPUSHED: <n> commits on <branch>` and board warning. If the branch is also not being worked on (no running worker, F1 conditions), the stall reason is "unpushed commits" |
| F4 | **Planned small builder runs** | `builder.md`: build at most **3 plan steps per run** (D-B). After each step: tests for that step, commit, **push at once**. At the end of the run: `chief_tick.py next "builder continue Phase N from step K"` and stop. `chief.md`: a `Next: builder continue ...` line means relaunch the builder, never a `needs-gian` question. Code review starts only after the last step |
| F5 | **Fewer denials** | (a) Add to `ops/worker_settings.json` allow: `Bash(grep:*)`, `Bash(head:*)`, `Bash(tail:*)`, `Bash(wc:*)`, `Bash(git show:*)`, `Bash(git rev-parse:*)`, `Bash(git rev-list:*)`, `Bash(git branch:*)`, `Bash(git ls-remote:*)`, `Bash(python src/da_smoke_check.py:*)`, `Bash(.venv/Scripts/python src/da_smoke_check.py:*)`, `Bash("$DA_PYTHON" src/da_smoke_check.py:*)`. Nothing that writes, deletes or merges. (b) `builder.md`, `chief.md`, `code-reviewer.md`, `plan-reviewer.md`: one command per Bash call, no `;`, `&&` or pipes; prefer the Read and Grep tools. The deny list does not change. The safety hook that stops workers editing `ops/` stays as it is (that 8 Nov denial was correct) |
| F6 | **Test isolation** | `tests/ops/conftest.py`: one autouse fixture that points every ops path at `tmp_path` (`DA_LEDGER_FILE`, `DA_WORKER_LOG_DIR`, the usage state folder, `logs/quiet`, `logs/status_board.log`, STATUS.md). Find and fix the test that wrote "15 Jan 16:00" rows. Add a guard test: a session-scoped check that the real `logs/usage-ledger.csv` and `logs/workers/` are unchanged after the ops tests |
| F7 | **Docs** | `docs/automation.md`: the stall alarm, the `next` command, chunked builder runs, "one command per Bash call". STATUS.md format rule: exactly one `- Next:` line |

## 3. When is the team stalled? (F1, first match wins)

The tick returned `idle` (no running worker, usage under the stop lines), and:

1. STATUS.md has **no** `- Next:` line, or more than one. Reason: "no valid Next line".
2. `Next: none` (or no work), there is **no** open `needs-gian` issue, and the final
   `auto/phases-7-10` into `main` PR is **not** open. Reason: "nothing to do, but the job is not finished".
3. F3 found unpushed commits. Reason: "unpushed commits on <branch>".

Not a stall: `Next: none` while a `needs-gian` issue is open (the team is waiting for Gian on purpose),
or the final PR is open (finished). Paused by the guard is `stopped`, not a stall.

When the cause is gone (a valid Next line returns, commits are pushed), the tick does **not** close the
issue; Gian closes it. The board stops showing STALLED as soon as section 3 no longer matches.

## 4. Edge rules

- F1 and F3 use the same `gh` and `git` wrappers as today (fakes in tests, no real calls).
- A failing `gh` or `git` call in F1 or F3 is logged once and never stops the tick (same as the board).
- F2 keeps STATUS.md within 60 lines (it replaces a line, never appends).
- The stall alarm costs zero tokens: it never starts Claude.

## 5. Choices (D-x). DECIDED: option 1 for all (Gian, 8 Nov 17:31)

### D-A How a stall reaches Gian: CHOSEN option 1
1. **A `needs-gian` issue plus the board top line.** Phone notification, same channel as questions.
2. Board top line only. Quieter, but Gian must look.

### D-B Size of one builder run: CHOSEN option 1
1. **At most 3 plan steps per run**, push after each step. Predictable, and Phase 8's 15 steps become 5 runs.
2. Time based: stop after 60 minutes of work. Harder to test, steps can be cut in half.
3. Keep as is (builder decides). This is what caused the 8 Nov surprise stop.

### D-C Fewer denials: CHOSEN option 1
1. **Read-only commands added to the allowlist, plus the one-command-per-call rule.**
2. The rule only. Agents forget rules; each slip costs a denied call.

### D-D When fix 3 takes effect: CHOSEN option 1
1. **Build now in the cloud, Gian merges into `auto/phases-7-10`. It is live on the laptop from Phase 9**
   (Phase 9 starts from `auto/phases-7-10`). Phase 8 finishes on the current machinery; Gian glances at
   STATUS.md once a day meanwhile.
2. Also merge `auto/phases-7-10` into `auto/phase-8` after fix 3 merges, so it is live during Phase 8.
   Faster, but it changes the machinery under a running build and may conflict.

## 6. Acceptance criteria (Given / When / Then)

- AS-1 Given STATUS.md has no `- Next:` line and no worker runs, when the tick wakes, then one issue
  `🔴 Team stalled: no valid Next line` exists with label `needs-gian`, and a Log line says so.
- AS-2 Given that issue is already open, when the next tick finds the same stall, then no second issue is opened.
- AS-3 Given `Next: none` and an open `needs-gian` issue, when the tick wakes, then no stall issue is opened.
- AS-4 Given a finished builder left 2 commits on `auto/phase-8` that `origin` lacks, when the tick
  records it, then the Log has `UNPUSHED: 2 commits on auto/phase-8` and the board shows a warning.
- AS-5 Given `chief_tick.py next "builder continue Phase 8 from step 10"`, then STATUS.md has exactly
  one `- Next:` line with that text, and STATUS.md is still 60 lines or fewer.
- AS-6 Given `chief_tick.py next ""`, then it refuses and STATUS.md is unchanged.
- AS-7 Given `Next: builder continue Phase 8 from step 10`, when the chief wakes, then it launches the
  builder and opens no issue (checked by a chief.md wording test or a scripted reply test, builder's choice).
- AS-8 Given the ops test suite runs, then the real `logs/usage-ledger.csv` and `logs/workers/` are unchanged.
- AS-9 Given the allowlist, then a worker command `grep -n x file` is allowed and `git push --force` is still denied
  (test reads `ops/worker_settings.json`).
- AS-10 Given a `gh` failure during the stall check, when the tick runs, then it still returns `idle`
  and logs one line.

## 7. Out of scope

- Changing the guard, the usage stop lines, or who merges what.
- Letting workers edit `ops/` (the safety hook stays).
- Cleaning the 5 junk rows already in the laptop's ledger: Gian or the project chat does that by hand.
- Anything in `src/` (the product).

## 8. Open items

- O1: the first stall-alarm issue will likely fire on day one if some STATUS.md is still hand-made.
  That is the alarm working; the fix is a valid `Next:` line.
