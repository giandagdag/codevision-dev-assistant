# Phase A: Automation foundation (spec)

Version 1.0 APPROVED, 6 Nov 2026. Gian chose option 1 for D-A to D-F (section 5).
Goal: from Phase 7 onwards, a team of agents (chief of staff, spec writer, builder, reviewers) runs each phase end to end, merges into an integration branch, and only stops for Gian when a rule says so. Gian tests at the end and merges into `main` himself.

---

## 1. Decisions already made (Gian, 6 Nov)

| # | Decision |
|---|---|
| 1 | Agents merge into an **integration branch** (`auto/phases-7-10`), never into `main`. Gian tests the integration branch and merges it into `main` himself |
| 2 | **Usage stop lines:** agents stop at **80% of the weekly limit** or **85% of the 5-hour limit** |
| 3 | Stay on **Pro** for now |
| 4 | Phase 6 is built and tested the normal way; Gian merges it into `main`. **Automation starts at Phase 7** |
| 5 | The chief **never assumes**. Section 6 says exactly when it may decide and when it must stop |

---

## 2. Step 0 result (6 Nov): cloud sessions cannot see the usage %

- Test: in a claude.ai cloud session, `claude -p "/usage"` returned only this session's cost (0 tokens), not the plan's 5-hour or weekly %.
- The cloud container has no plan login of its own (the host manages it), so a script there cannot ask for the % either.
- The live % reaches the **status line** only in an interactive Claude Code session on a machine logged in to the plan.
- Caveat: tested in a chat cloud session, not inside a scheduled routine. Re-check once during the pilot (A-P2). Expect the same answer.
- **Consequence:** a hard 80/85 stop needs the home laptop (D-A).

---

## 3. What we build (5 pieces)

AS400 comparison: a job scheduler that checks a data area before every step, runs the step, and writes a job log.

| # | Piece | What it is |
|---|---|---|
| A1 | **Usage guard** | `ops/usage_guard.py`: reads the plan %, writes `ops/state/usage.json`, answers GO or STOP. A hook in every worker re-checks before each tool call and makes the worker save and stop when over the line. **Fails closed:** if the % cannot be read, it is STOP |
| A2 | **Quiet runner** (our own small RTK) | `ops/quiet.py pytest|ruff|git ...`: prints a short summary plus failures only; the full output goes to `logs/quiet/<time>.log`. Python, so it works on Windows and in the cloud with nothing to install |
| A3 | **Lean context pack** | `STATUS.md` (max 60 lines) is the chief's whole memory. The handoff note is archived and points to it. CLAUDE.md gets a size budget. Workers start with no connectors and no extra plugins |
| A4 | **Chief rulebook + team** | `.claude/agents/chief.md`, the decision rule (section 6), the phase pipeline (section 7), how questions reach Gian |
| A5 | **Token ledger** | `logs/usage-ledger.csv`: one line per worker run (phase, stage, % before and after, tokens). Tells us what actually saves tokens |

Build order: A3, A1, A2, A4, A5, then the pilot (section 9).

---

## 4. Team and models

| Role | Model | Does |
|---|---|---|
| Chief of staff | Sonnet | Reads STATUS.md, picks the next step, starts one worker, records the result, opens questions for Gian. Never writes product code |
| Spec writer | **Opus** | Writes the phase spec with ranked D-x options (same shape as Phases 5 and 6) |
| Builder | Sonnet | Plan, then build, on branch `auto/phase-N` |
| Plan reviewer, code reviewer | Sonnet | Same caps as today (1 plan fix round, 3 code review rounds) |
| Status digest | Haiku | Short summaries for STATUS.md and the ledger |

---

## 5. Choices (D-x). DECIDED: option 1 for all (Gian, 6 Nov)

### D-A Where the team runs: CHOSEN option 1
1. **Home laptop.** The usage guard works for real (section 2). Laptop must stay on and awake while the team works.
2. Cloud team plus a small "usage beacon" on the laptop that publishes the % to the repo every 15 min. More moving parts, and the laptop must still be on.
3. Cloud only, no real %: a fixed number of runs per day, and Gian watches Settings, Usage himself. No hard stop.

### D-B How the chief starts workers: CHOSEN option 1
1. **Each worker is its own headless Claude Code process (`claude -p`).** It starts fresh, can use its own reviewer subagents, and returns one short result, so the chief's context stays tiny.
2. Workers are the chief's own subagents. The chief's context grows with every step, and subagents cannot start further subagents (the same problem as the old "builder as subagent" gotcha).

### D-C How the chief wakes up: CHOSEN option 1
1. **Windows Task Scheduler runs `ops/chief_tick.py` every 30 min.** It is plain Python, so it costs **zero tokens** when there is nothing to do or the guard says STOP. It only starts Claude when there is work and budget.
2. A Claude Desktop scheduled task. Every wake-up starts Claude and spends tokens, even when idle.
3. `/loop` in an open session. Meant for an afternoon, not for days.

### D-D Where the guard reads the %: CHOSEN option 1
1. **Ask the same usage endpoint Claude Code itself uses, with the laptop's login, fail closed.** Not an official public API, so it can change; if it breaks, everything stops safely and the chief reports "guard blind". Verify on the laptop in A-P1.
2. The status-line numbers saved to a file. Official, but only fresh while an interactive session is open; headless workers never refresh it.
3. Count tokens locally (ccusage) against a budget we calibrate ourselves. A cross-check only, because Pro's limits are not published as numbers.

### D-E How the quiet runner is used: CHOSEN option 1
1. **A hook rewrites `pytest`, `ruff` and `git status/diff/log` to go through `ops/quiet.py` automatically, plus a CLAUDE.md rule.** Same idea as RTK, without installing RTK.
2. A CLAUDE.md rule only. Agents sometimes forget.

### D-F How questions reach Gian: CHOSEN option 1
1. **One GitHub issue per question, labelled `needs-gian`.** Gian gets a phone notification and answers in a comment; the chief reads it on its next wake-up. Status questions: Gian asks in the project chat, which reads `STATUS.md`.
2. A `QUESTIONS.md` file Gian edits. Not phone-friendly.

---

## 6. Chief decision rule ("never assume")

| Situation | Chief does |
|---|---|
| A spec D-x choice with a recommendation, the choice can be undone later, and it touches no work fact | Picks the recommended option, writes "Chosen by chief, 6.1" next to it in the spec, continues |
| Anything about **work facts**: bank policy, CodeVision internals, on-prem models, work laptop limits | **Stops that stage, opens a `needs-gian` issue**, moves to other work if any |
| Cannot be undone, touches `.env`, secrets, `main`, branch protection or deleting anything | **Stops, opens an issue** |
| The spec has no recommendation, or two options look equally good | **Stops, opens an issue** |
| A test still failing after 2 fix attempts, a review cap reached, the spec unclear | Stops that phase, reports (today's stop rules) |
| Guard says STOP, or the guard is blind | Saves state in STATUS.md, stops everything, writes the reason and the reset time |
| Something needs Gian at work (bake-off Q9, context limit Q7, start command Q15) | Builds everything around it, parks that piece with label `needs-work-test` |

Never: merge into `main`, force-push, rebase shared branches, edit `.env`, or install a plugin.

---

## 7. Phase pipeline (per phase, from Phase 7)

1. **Spec** (Opus worker) from the handoff facts plus the redesign sections for that phase. Chief applies section 6 to every D-x.
2. **Plan** (builder) then **plan review** (auto-approve on 0 Must fix, max 1 fix round).
3. **Build** on `auto/phase-N`, then **code review** (max 3 rounds).
4. **Tests:** pytest, ruff, smoke check through the quiet runner. All green, or stop.
5. **PR** from `auto/phase-N` into `auto/phases-7-10`; the chief merges it when checks are green.
6. **STATUS.md and ledger** updated. Next phase.

When Phases 7 to 10 are done (or stopped), the chief opens one PR from `auto/phases-7-10` into `main` with a summary: what was built, every decision the chief took, open `needs-gian` and `needs-work-test` items. Gian tests and merges.

**Protection (Gian sets once in GitHub):** branch protection on `main` (PR plus Gian's approval required). The agents' GitHub token is a fine-grained token for this one repo only. So "never merge to main" is enforced by GitHub, not just by a rule.

---

## 8. Tools and plugins for the team

| Item | Verdict for the automated team |
|---|---|
| **Ponytail** | **Off for workers.** Its rule "a vague request gets the smallest version" clashes with our stop rule, which matters most when nobody watches. Its one good part (end every reply with "what I skipped, and risks") goes into CLAUDE.md as one line |
| **Karpathy skill** | **Off for workers too.** Same ground as our CLAUDE.md habits; two rulebooks cost tokens on every message. Keep both for your own manual chats if you like |
| **Playwright (Python, pinned)** | Keep, as now. Browser tests skip where it is missing |
| **Playwright MCP / mods** | Skip. Our usage guard is our own small mod |
| **RTK** | Not installed; A2 gives the same benefit for our commands |
| **Serena** | Later, only if the ledger shows file reading is the big cost |
| Connectors (Higgsfield, IBKR, Supabase, Drive, etc.) | **Off for workers** (empty MCP config). Each connected server adds its tool list to every request |

---

## 9. Pilot

- **A-P1 (laptop, Gian present):** guard reads the %, ledger writes a line, quiet runner on the full test suite, a fake STOP (set the line to 1%) makes a worker save and stop.
- **A-P2:** re-check Step 0 inside one cloud routine (5 min).
- **A-P3:** chief runs **Phase 7 spec stage only**, then stops. Gian reviews what the chief decided and what it asked.
- **A-P4:** full Phase 7 (without the bake-off). Then 8 to 10.

---

## 10. Acceptance criteria (Given / When / Then)

- AC-1 Given weekly usage is 80% or more, when the chief wakes, then no worker starts and STATUS.md shows "Stopped: weekly 8x%, resets <time SGT>".
- AC-2 Given a worker is running and the 5-hour usage passes 85%, when it next calls a tool, then the hook blocks it, the worker saves its state and stops.
- AC-3 Given the guard cannot read the %, when the chief wakes, then nothing starts and an issue "guard blind" exists.
- AC-4 Given a D-x touches a work fact, when the chief reaches it, then a `needs-gian` issue exists and that stage is paused.
- AC-5 Given all checks are green on `auto/phase-N`, when the chief merges, then it merges only into `auto/phases-7-10`; a merge into `main` is refused by GitHub.
- AC-6 Given `pytest` runs through the quiet runner with 1 failure, then the agent sees the summary plus that one failure, and the full log exists in `logs/quiet/`.
- AC-7 Every worker run adds one ledger line.

---

## 11. Out of scope

- Changes to the Developer Assistant product itself.
- Anything at work. Work tests stay manual.
- Upgrading the plan.

## 12. Open items

- O1: confirm the usage endpoint works with Gian's laptop login (A-P1).
- O2: Gian creates the fine-grained GitHub token and branch protection (step-by-step instructions to come with the build).
- O3: laptop power settings: no sleep while plugged in, during the team's hours.
- O4: the Phase A build must also update CLAUDE.md: today's safety rule allows pushing only to `phase-N` and setup branches. Add `auto/phase-N` and `auto/phases-7-10`, and say that only the chief may merge, and only into `auto/phases-7-10`.
- O5: build Phase A only after Phase 6 is merged into `main`, so the team starts from a known-good base.
