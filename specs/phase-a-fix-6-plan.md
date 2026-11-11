# Phase A fix 6 plan: STATUS.md stops blocking branch switches

Spec: `specs/phase-a-fix-6.md` v1.0 (approved, D-A to D-D = option 1). Branch `phase-a-fix-6`
(from `auto/phases-7-10`, which has fixes 3, 4, 5 and 5b and Phase 9). PR into `auto/phases-7-10`;
Gian merges. Built in a cloud session. Nothing in `src/` changes. `phase-8-fix-1` is not touched.
Tests use fakes and `tmp_path` only (no real `gh`, `git` or `claude`). Zero tokens added to any tick.

## Design in plain words (AS400: the data area moves out of the source file into the library, with a daily save and a restore)

- **H1 (`.gitignore`, git index)**: add `/STATUS.md` (root only) with a one-line comment. The cloud
  session (not a team worker: the hook refuses `git rm` for workers) runs `git rm --cached STATUS.md`
  so git stops tracking it; the file on disk stays. No code path changes (`ops/chief_tick.py`,
  `ops/safety_hook.py`, the board and the agents keep using `ROOT / "STATUS.md"`).
- **H2 (new `ops/STATUS.template.md`)**: the empty layout: `# STATUS`, `Stopped: no`, `Usage: unknown`,
  `## Where we are` with exactly one `- Next: none`, `## Decisions`, `## Log`. Under 60 lines.
- **H3 (`ops/chief_tick.py`)**, both inside `tick()` (not `_tick`), so every wake is covered:
  - `TEMPLATE_FILE = ROOT / "ops" / "STATUS.template.md"`; `backup_path()` =
    `usage_guard.state_path().parent / "STATUS.backup.md"` (so `DA_STATE_DIR` sandboxes it in tests).
  - `ensure_status(status_file, now)` runs first. File exists: do nothing (AS-6). Missing and a backup
    exists: copy the backup in, Log `STATUS.md restored from backup` (AS-4). Missing, no backup: copy the
    template in, Log `STATUS.md created from template` (AS-5). Plain file copy, never git. A failure
    (for example template missing) is logged once with `status_board.log_failure` and the tick goes on.
  - `main()` passes `status_file=STATUS_FILE` to `tick()` explicitly (review Must fix 1): the default
    argument is bound when the module loads, so conftest's patch of `STATUS_FILE` would not reach it and
    a test through `main(["tick"])` could create a real `STATUS.md`.
  - `backup_status(status_file, now)` runs after `_tick` and before the board, in a try/except: write the
    text to a temp file, then `os.replace` (whole or nothing) (AS-3). Failure: one `log_failure` line, the tick's result is unchanged (AS-8).
- **H4 (`ops/safety_hook.py`, `_git_problem`)**: for `git add`, refuse `-f`, `--force`, and any short-flag
  group containing `f` (`-fA`), and refuse any argument that resolves to `STATUS_FILE`. Reason
  `STATUS.md is not in git (Phase A fix 6)` / `git add --force is not allowed`. `git add src/da_x.py`,
  `git add -A` and `git add .` stay allowed (`.gitignore` already keeps STATUS.md out of those) (AS-7).
- **H4 (agents)**: `.claude/agents/chief.md` and `.claude/agents/builder.md`: one line each,
  "STATUS.md is not in git. Never add or commit it."
- **H5 (`docs/automation.md`)**: the Memory row says machine-only; a short section with the backup,
  the template and the one-time laptop switch-over (spec section 4, 5 commands).

## Steps (each with its check)

| # | Step | Proof |
|---|---|---|
| 1 | H1: `.gitignore` line, `git rm --cached STATUS.md`. New test `tests/ops/test_ops_fix6_status_file.py::test_gitignore_lists_status` reads `.gitignore` | AS-1 test passes; `git ls-files STATUS.md` prints nothing; the file is still on disk |
| 2 | H2: `ops/STATUS.template.md` + test (one `- Next:`, `Stopped:`, `Usage:`, <= 60 lines, and `stall.next_lines` reads it as `Next: none`) | AS-2 test |
| 3 | H3: `ensure_status`, `backup_status`, wired in `tick()`; tests for AS-3, AS-4, AS-5, AS-6, AS-8 with fake reader/gh (same helpers as `test_ops_chief_tick.py`) | AS-3 to AS-6, AS-8 tests |
| 4 | H3 sandbox: `tests/ops/conftest.py` keeps the backup in `tmp_path` (it already sets `DA_STATE_DIR`); add `ops/state/STATUS.backup.md` and the real `STATUS.md` text to the session guard snapshot | AS-9: the guard test sees no change |
| 4b | Fresh-checkout run (review Must fix 2): move the real `STATUS.md` away, run the full test suite, put it back. Fix every test or code path that needed the real file (for example the board's `root / "STATUS.md"` default) to use `tmp_path`. Test: `main(["tick"])` with the real file absent leaves no `STATUS.md` in ROOT. The guard snapshot treats "missing before and after" as unchanged | Full suite green with no real `STATUS.md` |
| 5 | H4 hook + agent lines; tests in `tests/ops/test_ops_safety_hook.py` style for `git add STATUS.md`, `git add ./STATUS.md`, `git add -f x`, `git add --force x`, `git add -fA`, `git add -- STATUS.md`, `git -C . add STATUS.md` (refused) and `git add src/da_x.py`, `git add -A` (allowed). Every argument after `add` is checked, flags included | AS-7 tests; all old hook tests pass |
| 6 | H5 docs | Read-through; CLAUDE.md size test still passes |
| 7 | Full run: pytest, ruff, smoke check; then `code-reviewer` (max 3 rounds); push; PR into `auto/phases-7-10` | Real outputs pasted in the PR |

## Not doing (and why)

- **No "Current phase" edit in CLAUDE.md** (recorded in the PR body too). This is a machinery fix, not a phase, and the laptop team's
  `phase-8-fix-1` may edit CLAUDE.md too; leaving it alone avoids a merge conflict.
- No change to the STATUS.md format, `chief_tick.py next`, the board, the guard or the stop lines.
- Old branches keep their tracked copy (spec O1).

## Risks

- R1: the laptop switch-over (spec section 4) is manual. If Gian skips step 1, git deletes the file and
  H3 creates it from the template: the chief loses its notes, and fix 3's alarm fires. Mitigation: the
  PR body repeats the 5 commands.
- R2: merging `phase-8-fix-1` into `auto/phases-7-10` after fix 6: if that branch committed STATUS.md,
  GitHub shows a modify/delete conflict on STATUS.md. Resolution: keep it deleted. Noted in the PR body.
