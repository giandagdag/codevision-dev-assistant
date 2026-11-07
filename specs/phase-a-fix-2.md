# Phase A fix 2: the "Team status" issue (a dashboard Gian can peek at)

Version 1.1 APPROVED, 7 Nov 2026 (v1.1 adds progress bars, section 3a, Gian 18:17).
Version 1.0 APPROVED, 7 Nov 2026. Gian chose option 1A in the project chat: one pinned GitHub
issue, refreshed by the tick, built after Phase 7 is merged into `auto/phases-7-10`.
Branch `phase-a-fix-2` (from `auto/phases-7-10`). PR into `auto/phases-7-10`; **Gian merges it**
(it changes the team's machinery). Build it the normal way: plan, plan review, build, code review,
pytest, ruff, smoke check. **Do not start the build while a team worker runs on the laptop.**

## 1. Why

Today Gian has to ask in the project chat to learn where the team is. STATUS.md, the running note
and the logs live only on the laptop. He wants one page he can glance at on his phone that answers:
is it working, is it paused, and is it waiting for me?

AS400 comparison: a job that refreshes one message on a shared display every 30 minutes. Anyone
can look; nobody has to run a report.

## 2. What we build

| # | Piece | What it does |
|---|---|---|
| S1 | **`ops/status_board.py`** | Builds the issue text from local files (section 3) and writes it to the issue. Plain Python, **zero tokens** |
| S2 | **Tick calls it at the end of EVERY wake-up** | Whatever the tick returned (`busy`, `stopped`, `idle`, `ran`, `hooks-broken`, `would-start`). Also after `launch` and `stop`. A failure here is logged once in `logs/status_board.log` and never stops the tick |
| S3 | **The issue** | Title `🤖 Team status`, label `team-status`. Found by its number in `ops/state/status_issue.json`; if missing, found by title; if none, created. Pinned once (`gh issue pin`, ignore failure). Never closed by the tick |
| S4 | **Only write when something changed** | Keep a hash of the last body in `ops/state/status_issue.json`. The "Updated" time alone does not count as a change, except once an hour (so a stale time really means the laptop stopped) |
| S5 | **Hidden worker window** (small extra) | The runner starts `claude` with `CREATE_NO_WINDOW` on Windows, so no black window appears and it cannot be closed by mistake. Keep the runner's own flags from fix 1 |
| S6 | **Docs** | `docs/automation.md`: what the issue shows, what each colour means, "a stale Updated time means check the laptop" |

## 3. What the issue shows (top line first, short, phone-friendly)

```
## 🟢 WORKING: builder on Phase 7 (running 1h 12m, since 12:03 SGT)
Updated 13:17 SGT

| Progress | |
|---|---|
| Phases 7 to 10 | `▓▓▓░░░░░░░` 31% (Phase 7 of 10) |
| Phase 7 | `▓▓▓▓▓░░░░░` 52% · Build, step 4 of 9 |
| Usage 5h | `▓▓▓▓▓▓▓▓░░` 71% of the 85% stop line |
| Usage weekly | `▓▓▓░░░░░░░` 29% of the 80% stop line |

### Waiting for you
None.                                   (or a list of open needs-gian issues, with links)

### Needs the work laptop (does not block)
- #20 WF-1 (Q9): which model is the Tester at work
- #21 WF-2 (Q7): server context limit per model

### Next step (from STATUS.md)
Phase 7 build ...

### Latest commits on auto/phase-7
- 13:05 Step 3/9: Layer C plain checks
- ... (5 lines)

### Last log lines (STATUS.md)
- ... (5 lines, each cut at 160 characters)
```

Top-line states, first match wins:

| State | When |
|---|---|
| 🔴 **WAITING FOR YOU** | An open `needs-gian` issue exists, OR the STATUS.md `Next:` line contains "waiting for Gian" |
| ⚫ **GUARD BLIND** | The usage cannot be read (the tick said `stopped` because the guard is blind) |
| 🟡 **PAUSED: usage** | The guard said STOP. Show which line and the reset time in SGT |
| 🟠 **HOOKS BROKEN** | The tick returned `hooks-broken` |
| 🟢 **WORKING** | `running.json` exists and the worker is alive |
| ⚪ **IDLE** | Nothing running and `Next:` is `none` (or no work) |
| 🔵 **READY FOR NEXT STEP** | Nothing running, work exists, the next tick will start it |

Sources (all local, read only): STATUS.md, `ops/state/running.json`, `ops/state/usage.json`,
`git log -5` on the current branch, and `gh issue list` for the two labels. **Never** put into the
issue: `usage_raw.json`, anything from `.env`, worker reply files, or prompt text beyond 200
characters.

## 3a. Progress bars (v1.1, Gian 7 Nov 18:17)

Gian wants build progress and token usage as percentages, at a glance. Bars are 10 characters of
`▓` and `░`, rounded down, with the number next to them. All values come from local files, zero tokens.

**Phase progress** (the current phase N, from 7 to 10). Each stage has a fixed share; a stage
counts as done when its marker is found:

| Stage | Share | Done when (marker) |
|---|---|---|
| Spec | 15% | `specs/phase-N-*.md` (not `-plan`, not `-facts`) exists and says APPROVED |
| Plan | 10% | `specs/phase-N-plan.md` exists and a commit message on `auto/phase-N` says the plan-reviewer approved |
| Build | 55% | split by steps: (highest K in commits "Phase N step K") / (number of `Step` headings in `specs/phase-N-plan.md`). No plan steps found = 0% of this share |
| Code review | 15% | 5% per "code review round" commit, max 15%; full 15% once tests are green and the branch is pushed |
| Merged | 5% | `auto/phase-N` is merged into `auto/phases-7-10` (`git merge-base --is-ancestor`) |

The line shows the current stage name and, during Build, "step K of T".

**Overall progress (Phases 7 to 10):** (merged phases × 100 + current phase %) / 4.

**Usage bars:** each bar is the % read by the guard (`ops/state/usage.json`), with the stop line
written next to it. When the guard is blind, both bars read `blind` instead of a number.

If a marker cannot be read (missing file, odd commit message), that stage counts as not done, and
the line ends with `(estimate)`. The board never fails because of progress.

## 4. Choices (D-x), recommended options already applied

| # | Question | Options (ranked) | Chosen |
|---|---|---|---|
| D-A | Who writes the issue? | 1. The tick (plain Python, every wake-up). 2. The chief (a Claude run). | **1**: zero tokens, and it still updates while the team is paused or the guard is blind |
| D-B | Edit the issue text, or add a comment each time? | 1. Edit the text. 2. New comment per tick. | **1**: one place to look, no notification spam (GitHub does not notify on text edits) |
| D-C | Hidden window (S5) in this fix? | 1. Yes. 2. Later. | **1**: tiny, and it removes the "closed the window by mistake" risk |

Gian may overrule any of them before the build.

## 5. Done when (each row becomes a test; no real `gh` or `claude`, use fakes)

| # | Given | When | Then |
|---|---|---|---|
| AS-1 | A running builder, no open questions | the board is built | the top line is 🟢 WORKING with the agent, phase and running time |
| AS-2 | An open `needs-gian` issue | the board is built | the top line is 🔴 WAITING FOR YOU and the issue is linked under "Waiting for you" |
| AS-3 | `Next:` contains "waiting for Gian" | the board is built | 🔴 WAITING FOR YOU |
| AS-4 | The guard said STOP at 85% | the board is built | 🟡 PAUSED with the line and the reset time in SGT |
| AS-5 | The guard is blind | the board is built | ⚫ GUARD BLIND |
| AS-6 | `needs-work-test` issues are open, nothing else | the board is built | they are listed under "Needs the work laptop" and the top line is not red |
| AS-7 | No `status_issue.json` and no issue with the title | the board is written | one issue is created with the label, its number is saved |
| AS-8 | Same content as last time, less than an hour later | the board is written | no `gh issue edit` call |
| AS-9 | `gh` fails | the tick runs | the tick still returns its normal result; one line in `logs/status_board.log` |
| AS-10 | Any tick result (`busy`, `stopped`, `idle`, `ran`) | the tick ends | the board is refreshed |
| AS-11 | Windows (mocked) | the runner starts `claude` | `CREATE_NO_WINDOW` is passed |
| AS-12 | `usage_raw.json` and `.env` exist | the board is built | the body contains nothing from them |
| AS-13 | Phase 8: spec approved, plan approved, commits up to "Phase 8 step 3", plan has 6 steps | the board is built | Phase 8 reads 52% (15 + 10 + 27.5, rounded down) with "Build, step 3 of 6"; overall reads (100 + 52) / 4 = 38% |
| AS-14 | Usage 5h 34%, weekly 34% | the board is built | the bars show 34% with stop lines 85% and 80% |
| AS-15 | The plan file is missing | the board is built | Build counts 0%, the line ends with "(estimate)", the board is still written |

## 6. Out of scope
- A web page or Claude artifact (Gian chose the issue).
- Notifications beyond what GitHub already sends for `needs-gian` issues.
- Any change to `src/` or to Phase 7.

## 7. Home check (Gian, laptop, about 10 min, team NOT running)
1. Wait until Phase 7 is merged and the team is idle (no `ops\state\running.json`).
2. Switch the laptop to this branch, run `.venv\Scripts\python -m pytest tests\ops -q`: all pass.
3. Run `.venv\Scripts\python ops\chief_tick.py tick` once: the issue "🤖 Team status" appears on
   GitHub, pinned, with the right top line. Open it on your phone.
4. Merge the PR into `auto/phases-7-10`, then bring it into the next phase branch.
