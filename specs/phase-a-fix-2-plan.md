# Phase A fix 2 plan: the "Team status" issue

Spec: `specs/phase-a-fix-2.md` v1.1 (approved). Branch `phase-a-fix-2`. Phase 7 is already in
`auto/phases-7-10` (PR #23), merged into this branch first, so the current phase is **8**.
Nothing in `src/` changes. All new code is plain Python, zero tokens, no real `gh`/`git`/`claude`
in tests (fakes only).

## Design in plain words (AS400: one message on a shared display, refreshed by a job)

- **New file `ops/status_board.py`**, in four small layers, each with tests:
  1. *Progress* (pure): `phase_progress(...)`, `overall(...)`, `bar(pct)`. Bar = 10 chars,
     `int(pct/10)` filled, rounded down.
  2. *Text* (pure): `build_body(inputs)` returns the issue text; `top_line(...)` picks the state
     (first match wins, spec section 3 order).
  3. *Gathering* (reads only): `gather(root, gh, git, now, ...)` reads STATUS.md, `running.json`
     (+ pid alive check), `usage.json` (via `usage_guard.read_state`), `git log -5`, and
     `gh issue list` for the two labels. It never opens `usage_raw.json`, `.env`, worker reply
     files; the prompt text is cut at 200 characters.
  4. *Writing*: `write_issue(body, gh, now)` finds/creates/pins/edits the issue and keeps
     `ops/state/status_issue.json` = `{number, hash, written_at}`.
- **`refresh(tick_result, ...)`** = gather + build + write, wrapped so any exception is logged as
  one line in `logs/status_board.log` and swallowed (AS-9).
- **Tick wiring**: `chief_tick.tick(..., board=None)`. The old body moves to `_tick`; `tick` calls
  it, then `board(result)` inside try/except. `main()` passes the real `status_board.refresh` for
  `tick`, and calls it after `launch` and `stop` too. Default `board=None` keeps all existing tests
  free of extra `gh` calls (they assert exact `gh` calls).
- **Which state to show**: `refresh` gets the tick result. `stopped` + no readable usage = GUARD
  BLIND; `stopped` + usage = PAUSED (line and reset time from `usage_guard.decide`);
  `hooks-broken` = HOOKS BROKEN; else from files (running = WORKING; `Next:` none = IDLE; else
  READY). WAITING FOR YOU outranks all of them (open `needs-gian` issue, or `Next:` says
  "waiting for Gian").
- **Hash rule (S4)**: hash of the body with the "Updated ..." line removed. Write when the hash
  changed, or the last write is over 1 hour old (so a stale time means the laptop stopped).
- **Issue lookup (S3)**: number from `status_issue.json`; if missing or `gh issue view` says it is
  gone, `gh issue list --search` by title; else `gh issue create --label team-status`. Pin once
  (`gh issue pin`, failure ignored, remembered as `pinned`). Never closed. The label is created
  on the first run if missing (`gh label create`, failure ignored).
- **Progress inputs** are read from the **phase branch** with `git show auto/phase-N:path` (the
  laptop may be on another branch), falling back to `origin/auto/phase-N`, then the working tree.
  Current phase = lowest N in 7..10 whose `auto/phase-N` is not an ancestor of `auto/phases-7-10`.
  A marker that cannot be read counts as not done. "(estimate)" is added when a stage that follows
  a finished stage cannot be read (for example the plan file is missing but the spec is approved,
  AS-15). A brand-new phase with nothing yet is a plain 0%, not "(estimate)".
- **Hidden window (S5)**: `real_launcher` passes `creationflags=CREATE_NO_WINDOW` on Windows. The
  runner's own flags (`WIN_FLAGS`) stay as they are; only the `claude` child needed it.

## Interpretations I made (the plan-reviewer should check these)

1. The spec says the plan's "`Step` headings". Real plans use a numbered list under `## Steps`
   (Phase 6, 7), and step 0 means "Done". I count numbered items `1.` and up under `## Steps`, and
   also `### Step N` headings, whichever is found.
2. Phase 7 step commits read "Phase 7 step 5: ...", and some "step 8a". I take the highest
   number K from `Phase N step K` (letters ignored), capped at the plan's step count.
3. "Plan approved" marker: a commit subject on `auto/phase-N` that has `plan-reviewer approved`
   (case-insensitive). Phase 7 has "Phase 7 plan: plan-reviewer approved (0 Must fix)".
4. Code review: follow the spec literally. 5% per commit whose subject has `code review round`,
   max 15%. Full 15% when `auto/phase-N` equals `origin/auto/phase-N` (pushed) AND the last
   round commit says `0 Must fix`. The board cannot run tests (zero tokens), so "tests green" is
   proven only by that commit message. This is a local proxy, said so in the docs.
5. Overall = (merged phases among 7..10 x 100 + current phase %) / 4, rounded down. When all
   four are merged: 100% and the top line is IDLE.
6. The `Next:` text and the Log lines from STATUS.md are cut at 160 characters each.

## Steps (each ends with pytest, ruff, commit)

0. **Done:** (check `ops/state/running.json` is absent before building) merge `origin/auto/phases-7-10` into the branch; this plan; CLAUDE.md "Current phase".
1. **Progress maths** (`ops/status_board.py`, pure): `bar`, `stage_shares`, `phase_progress`,
   `overall`, plan-step counter, commit-message markers. Tests AS-13, AS-14 (bar part), AS-15 (progress side), a real Phase 7-style plan (step 0 not
   counted, nested numbered items not counted, "step 8a" counts as 8), code review 5%/15% rule.
2. **Top line and body** (pure): `top_line`, `build_body`, section texts, cuts at 160/200.
   Tests AS-1 to AS-6, AS-14 (34% with stop lines 85% and 80%; `blind` bars).
3. **Gathering** (read only, fakes): files, `git`, `gh`; never touches `usage_raw.json`/`.env`.
   Test AS-12, plus "damaged running.json", "no usage.json" cases.
4. **Writer**: find/create/pin/edit, hash and hourly rule, `status_issue.json`. Tests AS-7, AS-8,
   "issue deleted by hand is re-created", "pin failure ignored", "damaged status_issue.json acts
   as no state", AS-15 at writer level (plan file missing: "(estimate)" shown, edit still made).
5. **Wire into the tick**: FIRST extend the `tests/ops/conftest.py` stub to `status_board` and add
   an autouse fixture that makes `status_board.refresh` a no-op, so the existing `main()` tests
   never touch real `git`/`gh` or write `status_issue.json`/`status_board.log`. Then
   `tick(board=...)`, and `main` calls `status_board.refresh(result, gh=<the gh main already has>)`
   for `tick`, `launch` and `stop`. New AS-9/AS-10 tests switch the board back on with fakes
   (all of busy/stopped/idle/ran/hooks-broken/would-start, plus after launch and stop).
6. **Hidden window**: `real_launcher` creationflags on Windows only. Test AS-11 (mocked platform,
   fake `subprocess.run`), plus "not passed on Linux".
7. **Docs**: `docs/automation.md` section (what the issue shows, colours, stale time rule, a red
   top line during a blind guard is expected because the guard opens a `needs-gian` issue, the
   code-review % is a proxy).
8. **Full run and code review**: pytest (whole suite), ruff, smoke check, `code-reviewer`
   (max 3 rounds). Push `phase-a-fix-2`. No PR merge (Gian merges).

## Risks
- The `gh` JSON field names (`number,title,url,labels`) are as documented by GitHub CLI; tests use
  fakes, so a real run on the laptop (spec section 7) is the proof.
- `git show` of a branch that does not exist yet fails: handled as "not readable".
- The Code review percent is a proxy (interpretation 4). `usage_guard.read_state` decides blind vs known; file age is not used.
