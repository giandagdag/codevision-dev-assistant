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
4. "Code review round" commits: subjects with `code review round`. Full 15% when tests are green
   and pushed: I use "the branch has at least one such commit AND `auto/phase-N` equals
   `origin/auto/phase-N`", since the board cannot run tests (zero tokens, read only). Green
   cannot be proven locally, so this part is an estimate and the line says "(estimate)" only
   when nothing else is known. To keep it simple: pushed + a code-review commit = 15%.
5. Overall = (merged phases among 7..10 x 100 + current phase %) / 4, rounded down. When all
   four are merged: 100% and the top line is IDLE.
6. The `Next:` text and the Log lines from STATUS.md are cut at 160 characters each.

## Steps (each ends with pytest, ruff, commit)

0. **Done:** merge `origin/auto/phases-7-10` into the branch; this plan; CLAUDE.md "Current phase".
1. **Progress maths** (`ops/status_board.py`, pure): `bar`, `stage_shares`, `phase_progress`,
   `overall`, plan-step counter, commit-message markers. Tests AS-13, AS-14 (bar part), AS-15.
2. **Top line and body** (pure): `top_line`, `build_body`, section texts, cuts at 160/200.
   Tests AS-1 to AS-6.
3. **Gathering** (read only, fakes): files, `git`, `gh`; never touches `usage_raw.json`/`.env`.
   Test AS-12, plus "damaged running.json", "no usage.json" cases.
4. **Writer**: find/create/pin/edit, hash and hourly rule, `status_issue.json`. Tests AS-7, AS-8,
   "issue deleted by hand is re-created", "pin failure ignored".
5. **Wire into the tick**: `tick(board=...)`, `main` for `tick`/`launch`/`stop`, failure log.
   Tests AS-9, AS-10 (all five results, plus after launch and stop).
6. **Hidden window**: `real_launcher` creationflags on Windows only. Test AS-11 (mocked platform,
   fake `subprocess.run`), plus "not passed on Linux".
7. **Docs**: `docs/automation.md` section (what the issue shows, colours, stale time rule), the
   `tests/ops/conftest.py` stub also covers `status_board`, CLAUDE.md `Current phase` line.
8. **Full run and code review**: pytest (whole suite), ruff, smoke check, `code-reviewer`
   (max 3 rounds). Push `phase-a-fix-2`. No PR merge (Gian merges).

## Risks
- The `gh` JSON field names (`number,title,url,labels`) are as documented by GitHub CLI; tests use
  fakes, so a real run on the laptop (spec section 7) is the proof.
- `git show` of a branch that does not exist yet fails: handled as "not readable".
- The percent for Code review is an estimate (see interpretation 4).
