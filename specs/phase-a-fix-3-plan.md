# Phase A fix 3 plan: no more silent stalls

Spec: `specs/phase-a-fix-3.md` v1.0 (approved, D-A to D-D = option 1). Branch `phase-a-fix-3`
(from `auto/phases-7-10`, which already has fix 2). PR into `auto/phases-7-10`; Gian merges.
Nothing in `src/` changes. Zero tokens: no step starts Claude. Tests use fakes only (no real
`gh`, `git` or `claude`).

## Design in plain words (AS400: a message queue alarm, so a job in MSGW is heard)

- **New file `ops/stall.py`**, small and pure, imported by `chief_tick.py` and `status_board.py`
  (so the board never imports `chief_tick`, as its test requires):
  - `next_lines(text)`: the `- Next:` lines of STATUS.md (same rule as `has_work`).
  - `reason(text, finished, unpushed)`: spec section 3, first match wins. `finished()` is a callable
    (lazy, so `gh` is asked only when needed) that says "a `needs-gian` issue is open, or the final
    PR is open".
  - Two small notes in `ops/state/` (local): `unpushed.json` (`{"branch"}`, F3) and `stall.json`
    (`{"reason"}`, F1), plus `unpushed_count(branch, git)` = `git rev-list --count origin/X..X`.
- **`ops/status.py`**: `set_next(path, text)` (F2). Replaces the first `- Next:` line **and its
  indented continuation lines**, deletes any further `- Next:` lines, adds one under
  `## Where we are` when missing (creates that heading if needed), refuses empty text, collapses
  line breaks. Goes through the existing `_write`, so the 60 line trim still applies.
- **`ops/chief_tick.py`**:
  - New command `next "<text>"` (prints the new line; empty text gives `Refused:`, exit 1).
  - `tick(..., git=None)`: **same pattern as `board=None`**. `None` switches the stall alarm and the
    unpushed check off, so every existing test keeps its exact `gh` calls. `main()` passes the
    real `status_board.run_git`.
  - Idle branch of `_tick` calls `stall_alarm(...)`: compute `reason`; if stalled, save
    `stall.json`, open ONE `needs-gian` issue `🔴 Team stalled: <reason>` through the existing
    `open_gian_issue` (it already refuses a second open issue with the same title), and add ONE
    Log line **only when the issue was newly opened** (no Log spam every 30 minutes). Not stalled:
    delete `stall.json`. Any non-idle tick result also deletes `stall.json`.
  - A `gh` or `git` failure inside this code is caught and written as one line through
    `status_board.log_failure` (the board's log file); the tick still returns `idle` (AS-10). A
    failed call means "unknown", so no issue is opened and `stall.json` is left as it was.
  - F3: `check_queue(..., git=None)`. After it records a finished, vanished or over-time worker, and
    the running note has a numeric `phase`, it counts commits `auto/phase-N` is ahead of
    `origin/auto/phase-N`. More than 0: Log line `UNPUSHED: <n> commits on <branch>` (`commit` when
    n is 1) and `unpushed.json`. 0: delete `unpushed.json`. The idle tick re-counts from
    `unpushed.json` every time, so the warning and the stall go away as soon as the branch is pushed.
- **`ops/status_board.py`**: `Inputs.stall` and `Inputs.warnings`. `gather` reads `stall.json`
  (only when the result is `idle`) and re-counts `unpushed.json` with its own `git`. Top line
  `## 🔴 STALLED: <reason>` goes **right after WAITING FOR YOU, before** GUARD BLIND, PAUSED, HOOKS
  BROKEN, WORKING, IDLE, READY. These other states never happen with an `idle` result, so the order
  only matters against IDLE and READY, as the spec says. Warning line `> ⚠️ UNPUSHED: n commits on
  branch` under the "Updated" line.
- **Agent files and docs**: wording only, each checked by a test that reads the file.

## Interpretations I made (the plan-reviewer should check these)

1. **The stall issue is itself a `needs-gian` issue (D-A option 1).** So after it opens, the same
   tick's board refresh shows WAITING FOR YOU (the spec ranks that above STALLED). STALLED shows
   alone only when the issue could not be opened (for example `gh` is down). This follows the spec
   as written; the issue title carries the reason in the "Waiting for you" list.
2. **Section 3 case 3 (unpushed) is checked even when case 2 is exempt** (a `needs-gian` issue is
   open). Unpushed work is at risk whatever Gian is doing. Exemptions in the spec are written
   under case 2 only.
3. **"Idle" is the tick result `idle`.** That already means no worker, usage under the lines, and
   no work in STATUS.md. Case 3 can therefore only fire with `Next: none` or no `Next:` line,
   because with real work the tick launches the chief instead.
4. **Which branch F3 checks:** `auto/phase-<phase>` from the `phase` in `running.json`. A worker
   launched with no phase (the chief itself) is not checked. If `origin/auto/phase-N` does not exist
   or git fails, the result is "unknown": one board-log line, no Log line, no stall.
5. **`next` takes one text argument**, as in the spec. It does not forbid `;` `&` `|` `>` or quotes
   itself (the chief and builder prompts already say to keep these plain, because the safety hook
   cannot read them); `docs/automation.md` repeats it.
6. **"Headless rule: never start a subagent in the background"** was added by hand on 8 Nov
   (spec section 1) but is **not in `builder.md` on this branch**. I add it in step 7 and test for
   it, so it is kept.
7. **`git branch:*` in the allowlist is safe:** `ops/safety_hook.py:120` already refuses
   `git branch -D/-d/--delete` for workers. The deny list in `worker_settings.json` is not changed.
8. **F4 counting:** "3 plan steps per run" counts build steps only. Writing the plan and the plan
   review happen before step 1 and do not count. If steps remain after the 3rd, the builder sets
   `next "builder continue Phase N from step K"` (K = the next unbuilt step) and stops. When the
   last step is done it goes straight on to the full checks and the code review.
9. **F6 guard test** watches `logs/usage-ledger.csv` (size and time) and `logs/workers/` (names,
   sizes, times) only, as the spec says. The snapshot is taken once per pytest session and compared
   by a test file named `test_ops_zz_real_logs.py` so it runs last among the ops tests.

## Steps (each: tests for that step, ruff, commit, push)

0. **Done:** plan written, CLAUDE.md "Current phase" updated, plan-reviewer asked.
1. **F6 test isolation (first, so later tests never pollute real files).** In
   `tests/ops/conftest.py` add ONE autouse fixture that sets `DA_LEDGER_FILE`, `DA_WORKER_LOG_DIR`,
   `DA_STATE_DIR`, `DA_LOG_DIR` (quiet), `DA_STATUS_BOARD_LOG`, and points `chief_tick.STATUS_FILE`
   at a temp STATUS.md. The existing board fixture keeps only its stubs. Culprit already found:
   `tests/ops/test_ops_status_board.py` (`c.tick` and `c.main` calls, its fixture sets only
   `DA_STATE_DIR`); the central fixture fixes it with no edit to that test. Add the session
   snapshot fixture and `tests/ops/test_ops_zz_real_logs.py` (AS-8), with a test that proves the
   snapshot function notices a changed file in a temp folder.
   *Check:* delete `logs/`, run `pytest tests/ops`, `logs/` is not created; the guard test passes.
2. **F2 `status.set_next` and the `next` command.** Tests: replaces the line and its continuation;
   removes a second `Next:`; adds it under `## Where we are`; creates the heading when missing;
   empty and blank text refused, file unchanged (AS-6); a 60 line STATUS.md stays at 60 or less
   (AS-5); `main(["next", ...])` returns 0 and prints, empty returns 1.
3. **F5a allowlist.** Add the 12 entries to `ops/worker_settings.json` allow (deny untouched). Test
   (AS-9) with a tiny matcher for `Bash(prefix:*)`: `grep -n x file` allowed, `git push --force`
   denied, `git rev-list --count a..b` allowed, `git rm` and `gh pr merge` still denied, and the
   deny list equals the list before this change (copied into the test).
4. **F3 unpushed check.** `ops/stall.py` part 1 (`unpushed_count`, the `unpushed.json` helpers),
   `check_queue(..., git=None)`, `tick(..., git=None)` passes it on. Tests (AS-4) with a fake git:
   2 ahead gives the Log line and note; 1 ahead says `commit`; 0 removes the note; git failure
   gives one board-log line and no Log line; no phase in `running.json` skips the check; vanished
   and over-time workers also trigger it; `git=None` makes no git call (existing tests untouched).
5. **F1 stall alarm.** `stall.reason` plus `stall_alarm` in the tick. Tests: AS-1 (no `Next:`
   line, and two `Next:` lines), AS-2 (same title already open gives no second issue and no second
   Log line), AS-3 (`Next: none` with an open `needs-gian` issue, and with the final PR open),
   `Next: none` with nothing open is a stall, case 3 beats the exemption, AS-10 (`gh` fails: result
   `idle`, exactly one log line, no issue), `stall.json` removed when the cause is gone and on any
   non-idle result, the issue is never closed by the tick.
6. **Board.** `Inputs.stall`, `Inputs.warnings`, the STALLED top line and the UNPUSHED warning.
   Tests: STALLED outranks IDLE and READY; WAITING FOR YOU outranks STALLED; no STALLED once
   `stall.json` is gone (section 3 no longer matches); UNPUSHED line appears and disappears with
   the count; `status_board` still does not import `chief_tick`; the hash ignores nothing new.
7. **Agent files (F4, F5b, F2 wording).** `builder.md`: the headless rule, 3 steps per run, push
   after each step, `next "builder continue Phase N from step K"`, one command per Bash call.
   `chief.md`: set Next only with the `next` command, exactly one `- Next:` line, `Running:` stays on
   its own line, a `builder continue` line means relaunch the builder and never a `needs-gian`
   question (AS-7). `code-reviewer.md` and `plan-reviewer.md`: one command per Bash call and prefer
   Read and Grep (plan-reviewer has no Bash, so the line says "if you are ever given Bash"). Tests
   read each file for the exact phrases. Keep `CLAUDE.md` under 6,000 bytes (existing test).
8. **F7 docs.** `docs/automation.md`: stall alarm (reasons, who gets told, Gian closes the issue),
   the `next` command, chunked builder runs, one command per Bash call, UNPUSHED, STATUS.md has
   exactly one `- Next:` line. Test that the doc names each. Add the O1 note (the first alarm may
   fire on day one).
9. **Finish.** Full `pytest`, `ruff check .`, smoke check, `git status`; ask `code-reviewer`
   (max 3 rounds); commit and push to `phase-a-fix-3`; open the PR into `auto/phases-7-10`.

## Out of scope (spec section 7)
The guard, the usage stop lines, who merges what, letting workers edit `ops/`, cleaning the 5 junk
ledger rows on the laptop, anything in `src/`.

## Risks
- The new idle-tick code runs only on the laptop after Gian merges and Phase 9 starts; nothing
  here can be proven live in the cloud. Mitigation: fakes for `gh` and `git`, plus the `git=None`
  switch so old behaviour is unchanged until `main()` passes the real git.
- A `Next:` line written by hand in a way my parser does not see gives a false "no valid Next
  line" alarm. That is the alarm working (spec O1).
- The guard test compares real `logs/` files, so it would fail if a real worker writes the ledger
  during a laptop test run. The spec says build in the cloud; the tick is `busy` while a worker
  runs, so in practice the ledger is not written then.
