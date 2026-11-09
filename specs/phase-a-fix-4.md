# Phase A fix 4: the chief never sits still by mistake

Version 1.0 APPROVED, 9 Nov 2026 (10:47 SGT). Gian: "go ahead, write fix 4, and any other fixes you deem
necessary". Recommendations chosen as option 1 for D-A to D-D (section 5), same as fix 3.
Written in the project chat after the 8 and 9 Nov incidents. Builds on fix 3 (merged, PR #32).
Branch `phase-a-fix-4` (from `auto/phases-7-10`). PR into `auto/phases-7-10`; **Gian merges it**
(it changes the team's machinery). Build it the normal way: plan, plan review, build, code review,
pytest, ruff, smoke check. Build in a **cloud** session, never on the laptop while a team worker runs.
**Do not touch `auto/phase-8`**: Gian tests Phase 8 today.

## 1. Why (what fix 3 does not catch)

| # | When | What happened | Root cause | Fix 3 catches it? |
|---|---|---|---|---|
| 1 | 8 Nov 22:51 | Chief saw `Running: builder since 22:30` (a time it made up, later than the real result) and did nothing | Two records of "is a worker running": `ops/state/running.json` (true) and a hand-written `Running:` line (can be wrong) | No: there was a valid `Next:` line, so the tick was not idle |
| 2 | 8 Nov 22:51 onwards | Chief woke every 30 minutes and changed nothing | No alarm for "chief runs, but nothing moves" | No |
| 3 | 9 Nov 10:21 | Chief could not read Gian's answer on #33 | `gh issue view 33 --json ... --jq '{...(.comments\|last\|.body)}'`: the safety hook splits commands on `\|` **even inside quotes**, so a jq filter looks like a pipe, and the command is refused | No |
| 4 | 9 Nov 09:21 to 10:21 | Chief woken 3 times while waiting for Gian, each costs tokens, each says "no comments yet" | The tick cannot see issue comments, so it wakes Claude just to look | No |
| 5 | 9 Nov 03:22 | Builder said "Bash is denied in this session" after ONE refused command (`python -c "print(1)"`) and stopped | It read one refusal as "Bash is off" | No |
| 6 | 8 Nov 19:00 | Board stuck at "step 7 of 15" through 7a and 7b | The progress reader ignores letters after the step number | Cosmetic |

AS400 comparison: the job scheduler now raises MSGW when a job ends without a next job (fix 3). Fix 4 adds:
the scheduler owns the "job active" flag itself, reads the reply queue itself, and raises an alarm when a
job keeps running but never moves.

## 2. What we build

| # | Piece | What it does |
|---|---|---|
| G1 | **The tick owns the `Running:` line** | `launch_worker` writes `Running: <agent> since <HH:MM SGT>` from the real start time in `running.json`, right after the start. `check_queue` deletes it when it records the result (finished, vanished, over time, stopped by hand). Self-heal: at every tick, if `running.json` does not exist and a `Running:` line does, delete the line and add one Log line `Running line removed: no worker`. `chief.md`: **never write, edit or trust a `Running:` line**; only the tick does |
| G2 | **The tick reads Gian's answers** (zero tokens) | For each open `needs-gian` issue that is not a `Team stalled` issue: read its comments with the `gh` wrapper (`gh issue view N --json comments`, parsed in Python). Only comments by the repo owner (`gh repo view --json owner`) count; anything else is ignored (no instructions from strangers). A new owner comment (newer than the last one seen, kept in `ops/state/answers.json`) is written as one Log line `ANSWER #N (HH:MM SGT): <first 300 chars>`, and the chief is woken with the prompt `Gian answered #N: "<full text>". Act on it, then close #N with a short comment.` |
| G3 | **Do not wake the chief to wait** | If `Next:` says the team waits for Gian (an open non-stall `needs-gian` issue exists) and G2 found no new answer: the tick returns `waiting` and does **not** start Claude. Zero tokens while Gian sleeps. The board shows WAITING FOR YOU as today |
| G4 | **`chief_tick.py answer N`** | Prints the newest owner comment on issue N (or `no answer yet`). For the chief and for manual checks, so nobody needs `gh --jq` |
| G5 | **"Chief did nothing" alarm** | After each chief run, the tick compares: did it launch a worker, change the `Next:` line, or open/close an issue? If none of these, add 1 to `ops/state/idle_runs.json`, else reset to 0. At **2 in a row** (D-B): fix 3's stall alarm with reason `chief made no progress twice`. G3 means waiting for Gian never counts |
| G6 | **Safety hook reads quotes properly** | `SEGMENT_SPLIT` must not split inside single or double quotes. Use a small quote-aware splitter (not `shlex` alone: it must still find `;`, `&&`, `\|\|`, `\|`, `&` and newlines outside quotes). **Fail closed**: an unclosed quote is refused as today. Every existing safety-hook test must still pass; add tests for `gh issue view 33 --json comments --jq '.comments\|last\|.body'` (allowed) and `echo 'x' ; git push --force` (still refused) |
| G7 | **One refusal is not "Bash is off"** | `builder.md`, `chief.md`, `code-reviewer.md`: "A refused command refuses only that command. Read the reason, use the allowed form (for Python: `.venv/Scripts/python ...`), and carry on. Bash is off only if three different allowed commands in a row are refused; then say so in the worker note" |
| G8 | **Board shows sub-steps** | The progress reader takes the step label with its letters and parts (`13d`, `9b-3`). The bar still counts whole steps (13d stays in step 13), but the text shows `Build, step 13d of 15` |
| G9 | **Docs** | `docs/automation.md`: the tick owns `Running:`, how answers reach the chief, the no-progress alarm, the `answer` command |

## 3. Edge rules

- G2, G3, G5 are plain Python in the tick: **no tokens** unless the chief is actually woken.
- G2 never acts on a comment by anyone other than the repo owner. A comment that is only an edit of an
  older one (same id, changed text) counts as new once.
- If `gh` fails while reading comments: log once, treat as "no new answer", and the tick still returns
  (same rule as the board and fix 3's AS-10).
- G3 does not hide a stall: a `Team stalled` issue alone is not "waiting for Gian" (fix 3 rule kept).
- G1 keeps STATUS.md within 60 lines (it replaces or deletes one line).
- The usage guard runs first, as today. When it says STOP, nothing in this fix wakes Claude.

## 4. What does NOT change

- Who merges what, the guard, the stop lines, the deny list, workers not editing `ops/`.
- Fix 3's `Next:` rule and stall alarm (G5 reuses it).
- Anything in `src/` (the product). P31 (Windows sandbox test) is a product fix, not part of this.

## 5. Choices (D-x). DECIDED: option 1 for all (Gian, 9 Nov 10:47)

### D-A How Gian's answers reach the chief: CHOSEN option 1
1. **The tick reads owner comments and wakes the chief with the answer (G2), and skips the chief while
   waiting (G3).** Zero tokens while waiting; the answer arrives within one tick.
2. Only the `answer` command (G4); the chief is still woken every 30 minutes to check. Costs tokens all night.

### D-B No-progress threshold: CHOSEN option 1
1. **2 chief runs in a row** with no launch, no `Next:` change and no issue opened or closed. About 1 hour lost at most.
2. 3 in a row. Fewer false alarms, up to 1.5 hours lost.

### D-C Who owns the `Running:` line: CHOSEN option 1
1. **The tick, from `running.json` (G1).** One source of truth.
2. The chief keeps it, plus a self-heal only. The chief can still write a wrong time.

### D-D When fix 4 takes effect: CHOSEN option 1
1. **Build now in the cloud, Gian merges into `auto/phases-7-10`. Live from Phase 9**, together with fix 3.
   Phase 8 is untouched so Gian can test it today.
2. Also merge into `auto/phase-8`. Rejected: Gian is testing Phase 8 today.

## 6. Acceptance criteria (Given / When / Then)

- AS-1 Given the chief is launched at 10:21 SGT, then STATUS.md has `Running: chief since 10:21 SGT`
  written by the tick, and when the tick records the result, the line is gone.
- AS-2 Given no `running.json` and a `Running:` line in STATUS.md, when the tick wakes, then the line is
  deleted and one Log line says so.
- AS-3 Given open issue #33 (`needs-gian`) and a new comment by the repo owner, when the tick wakes, then
  the Log has `ANSWER #33 ...` and the chief is launched with the answer in its prompt.
- AS-4 Given the same issue with a new comment by someone else, then nothing is launched and no ANSWER line is written.
- AS-5 Given an open non-stall `needs-gian` issue and no new owner comment, when the tick wakes, then it
  returns `waiting` and no Claude process starts (fake launcher not called).
- AS-6 Given `chief_tick.py answer 33`, then it prints the newest owner comment, or `no answer yet`.
- AS-7 Given two chief runs in a row that launch nothing, change no `Next:` line and touch no issue,
  then one `Team stalled: chief made no progress twice` issue exists. Given one run that launches, the count resets to 0.
- AS-8 Given `gh issue view 33 --json comments --jq '.comments|last|.body'`, then the safety hook allows it;
  given `echo 'x' ; git push --force`, it is still refused; given an unclosed quote, it is refused.
- AS-9 Given commits `Phase 8 step 13d: ...`, then the board text says `step 13d of 15` and the bar counts step 13.
- AS-10 Given a `gh` failure while reading comments, then the tick logs one line and still returns.

## 7. Out of scope

- P31 (Windows-only sandbox test failure). It must be fixed before the final merge into `main`, as its own small fix.
- Upgrading the plan, changing the guard.
- Cleaning junk ledger rows on the laptop.
