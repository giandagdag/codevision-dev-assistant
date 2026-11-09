# Phase A fix 4 plan: the chief never sits still by mistake

Spec: `specs/phase-a-fix-4.md` v1.0 (approved, D-A to D-D = option 1). Branch `phase-a-fix-4`
(from `auto/phases-7-10`, which has fix 3). PR into `auto/phases-7-10`; Gian merges.
Nothing in `src/` changes. `auto/phase-8` is not touched. Tests use fakes only (no real `gh`,
`git` or `claude`). Zero tokens unless the chief is really woken.

## Design in plain words (AS400: the scheduler owns the "job active" flag, reads the reply queue, and raises an alarm for a job that runs but never moves)

- **`ops/status.py`**: `set_running(path, agent, started)` and `clear_running(path)` find the line with
  `lstrip("- ").startswith("Running:")` (the live file has `- Running: ...`), replace or delete it, and
  never grow the file past 60 lines. A new line goes right after `Stopped:`.
- **New `ops/answers.py`** (small, imports no tick code, like `stall.py`):
  - `owner(gh)`: `gh repo view --json owner`, parsed in Python.
  - `open_questions(gh)`: open `needs-gian` issues `[(number, title)]`, stall issues left out.
  - `newest_owner_comment(gh, n, owner)`: parses `gh issue view N --json comments`; only comments whose
    `author.login` equals the owner (case-insensitive); returns `(comment_id, text)` of the newest, or None.
  - `ops/state/answers.json` = `{ "<issue>": "<comment id>:<sha1 of text>" }`. A comment is new when its
    key differs from the stored one, so an edited comment (same id, new text) counts once.
  - `find_new_answer(gh)` returns `(number, text, key)` for the first issue with a new owner comment, else None.
    `remember(number, key)` is called only after the chief was really launched, so a refused launch
    (hooks broken) does not swallow the answer.
  - `idle_runs.json` helpers: `count`, `add`, `reset`.
- **`ops/chief_tick.py`**
  - **G1** `start_background` writes the line after the pid is known, from `note["started"]`
    (`Running: chief since 10:21 SGT`). `check_queue` (finished, vanished, over time) and `stop_worker`
    delete it. `_tick` self-heals after `check_queue`: no `running.json` and a `Running:` line means
    delete it plus one Log line `Running line removed: no worker`.
  - **G2/G3** in `_tick`, after the guard says GO (so STOP wakes nothing) and only when `git` is given
    (the same on/off switch as fix 3, so every old test keeps its exact `gh` calls):
    1. new owner answer found: with a launcher, run the chief with the prompt
       `Gian answered #N: "<full text>". Act on it, then close #N with a short comment.`; when it ran, write
       Log `ANSWER #N (HH:MM SGT): <first 300 chars>` and `remember`. Without `--launch`: a Log line, `would-start`.
    2. else if `Next:` contains `waiting for gian` (the phrase the board already uses) and an open non-stall
       `needs-gian` issue exists: return `waiting`, launcher not called.
    3. else the old path.
  - A `gh` failure while reading comments: one line via `status_board.log_failure`, treated as "no new answer".
  - **G4** command `answer N`: prints the newest owner comment, or `no answer yet`.
  - **G5** around the foreground chief run in `_tick`: snapshot before (Next lines, ids of all open issues);
    after the run: progress = `running.json`/`worker_done.json` exists, or Next lines changed, or the issue
    set changed (or the issue list could not be read: unknown counts as progress, no false alarm).
    Progress resets `idle_runs.json` to 0, otherwise add 1. At 2 or more, call `open_gian_issue`
    `🔴 Team stalled: chief made no progress twice` (it already refuses a duplicate), Log line only when
    newly opened, `stall.save_stall`. `waiting` and `idle` ticks never touch the count.
- **`ops/status_board.py`** (G8): `highest_step_label` reads `step 13d` and `step 9b-3`; `PhaseFacts.step_label`;
  stage text `Build, step 13d of 15` when the label's number equals the counted step. The bar still counts whole steps.
  `top_line` already shows WAITING FOR YOU for the `waiting` result (an open non-stall issue exists).
- **`ops/safety_hook.py`** (G6): `split_segments(command)` replaces `SEGMENT_SPLIT`. It walks the command
  with bash's own quote rules (single quotes: nothing is special; double quotes: backslash escapes the next
  char; outside quotes: a backslash makes the next char plain). It splits on `&&`, `||`, `;`, `|`, `&`,
  newline **outside quotes only**. Unclosed quote returns None, refused as "could not be read safely".
  The splitter follows bash, not the later `\` to `/` rewrite, so `echo \"; rm x; echo \"` cannot hide
  an `rm` (the `\"` is plain text in bash, so the `;` splits). The existing per-segment checks do not change.
- **Agent files and docs** (G7, G9): `builder.md`, `chief.md`, `code-reviewer.md` get the refusal rule;
  `chief.md` also: never write, edit or trust `Running:`, and use `chief_tick.py answer N`.
  `docs/automation.md` explains the tick-owned line, how answers arrive, the alarm, and `answer`.

## Interpretations I made (the plan-reviewer should check these)

1. The spec says `launch_worker` writes the line, but `launch_worker` is the in-tick foreground run and
   writes no `running.json`. The code that writes `running.json` (what `chief_tick.py launch` calls) is
   `start_background`, so the line is written there. This is the only reading where "the line comes from
   the real start time in running.json" works.
2. "Next: says the team waits for Gian" is tested as the text `waiting for gian` (case-insensitive), the
   same phrase the board's WAITING rule uses, **and** an open non-stall `needs-gian` issue. A Next line
   with real work and an unrelated parked issue still wakes the chief.
3. One answer per tick: if two issues have new answers, the second is handled on the next tick.
4. An answer is "seen" only once the chief was launched for it. A refused launch retries on the next tick.
5. G5 counts only the foreground chief run made by `tick`. A chief run that finds `running.json` after it
   (it launched a worker) is progress.
6. Once the no-progress alarm has fired, the count stays at 2 or more until progress; the duplicate check
   in `open_gian_issue` stops a second issue, and the Log line is written only the first time.
7. The `ANSWER` comment author test uses `gh repo view --json owner` (`owner.login`). For a repo owned by an
   organisation that would be the org name, so no person's comment would count; this repo is a personal one.
   If the repo ever moves to an organisation, the check fails safe (nothing is acted on).

## Steps

1. Spec status helpers: `set_running`, `clear_running` in `ops/status.py`, with tests (live `- Running:` shape, 60-line cap).
2. `ops/answers.py` (owner, comments, answers.json, idle_runs.json) with tests (AS-4, edit counts once, gh failure).
3. G1 in `chief_tick.py`: write on start, clear on record and stop, self-heal; tests AS-1, AS-2.
4. G2, G3: answers and `waiting` in `_tick`; tests AS-3, AS-4, AS-5, AS-10; board shows WAITING FOR YOU.
5. G4 `answer` command; test AS-6.
6. G5 no-progress alarm; test AS-7.
7. G6 quote-aware splitter in `safety_hook.py`; tests AS-8 (allowed, still refused, unclosed quote, escaped-quote bypass).
8. G8 board sub-steps; test AS-9.
9. G7 agent files, G9 docs, agent-file tests; full pytest, ruff, smoke check; code review.

## How Gian can check it

`python -m pytest tests/ops` (all green), `ruff check .`, smoke check, and `git diff --stat` shows only
`ops/`, `tests/ops/`, `docs/automation.md`, `.claude/agents/`, `specs/`, `CLAUDE.md`.
