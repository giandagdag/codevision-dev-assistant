# Phase A fix 6: STATUS.md stops blocking branch switches

Version 1.0 APPROVED, 11 Nov 2026 (16:02 SGT). Gian chose option 1 for D-A to D-D (section 5).
(Named fix 6 because fix 5 and 5b already exist: usage credits and Fable. The hold on #48 says "fix 5": it means this one.)
Written in the project chat after issue #48 (Phase 8 fix 1 builder blocked 3 times).
Branch `phase-a-fix-6` (from `auto/phases-7-10`). PR into `auto/phases-7-10`; **Gian merges it**
(it changes the team's machinery). Build it the normal way: plan, plan review, build, code review,
pytest, ruff, smoke check. Build in a **cloud** session, never on the laptop while a team worker runs.
**Do not touch `phase-8-fix-1`**: the laptop team is building it now.

## 1. Why (what went wrong on 11 Nov)

| # | When | What happened | Root cause |
|---|---|---|---|
| 1 | 11 Nov, 3 runs | Builder stopped before any work on Phase 8 fix 1 | The tick edits `STATUS.md` on disk at every wake, so it always has unsaved changes. `phase-8-fix-1` had an older committed copy, so `git switch` refused (git will not overwrite unsaved changes) |
| 2 | Same | Builder tried `git worktree add` | Refused by the safety hook. That refusal was correct and stays |
| 3 | 11 Nov | Gian had to merge `auto/phases-7-10` into `phase-8-fix-1` by hand (PR #49) | Same as 1 |
| 4 | Before | Builders sometimes commit `STATUS.md` (for example Phase 9 step 18, 84ab8c9) | Nothing stops it. Each such commit makes branches differ on `STATUS.md` again |

**Common thread:** `STATUS.md` is the chief's live notepad, but git treats it like source code.
AS400 comparison: it is like keeping a job's *data area* inside the *source file*. Every time you
change libraries, the system complains the member is in use. The fix: keep the data area as an
object on the machine, outside the source file.

`STATUS.md` does not need to be on GitHub: Gian reads progress in the Team status issue (#30),
which `ops/status_board.py` builds from local files.

## 2. What we build

| # | Piece | What it does |
|---|---|---|
| H1 | **Take STATUS.md out of git** | Add `STATUS.md` to `.gitignore` (with a comment: "the chief's live notepad, machine-only, Phase A fix 6"). `git rm --cached STATUS.md` (removes it from git, keeps the file on disk). Path and format do not change, so the chief, tick, board and hooks keep working with no path changes |
| H2 | **Template for a fresh copy** | New tracked file `ops/STATUS.template.md`: the empty layout (headings, `Stopped: no`, `Usage:` line, `- Next: none`), at most 60 lines |
| H3 | **Backup and self-heal** (zero tokens) | At the end of every tick, copy `STATUS.md` to `ops/state/STATUS.backup.md` (ignored by git already). At the start of every tick, if `STATUS.md` is missing: restore it from the backup if one exists, else create it from the template. One Log line either way: `STATUS.md restored from backup` or `STATUS.md created from template`. A template copy has `Next: none` and no open issue, so fix 3's stall alarm tells Gian (that is the alarm working) |
| H4 | **Workers never stage STATUS.md** | Safety hook: refuse `git add` that names `STATUS.md`, and refuse `git add -f` / `--force` (forcing an ignored file in). Reason text: "STATUS.md is not in git (Phase A fix 6)". `chief.md` and `builder.md`: one line, "STATUS.md is not in git. Never add or commit it" |
| H5 | **Docs** | `docs/automation.md`: STATUS.md is machine-only, the backup, the template, and the one-time laptop switch-over (section 4) |

## 3. Edge rules

- H3 uses plain file copy; it never calls git. A failing copy is logged once and never stops the tick.
- H3 restore never overwrites an existing `STATUS.md`.
- The backup is one file, replaced each tick (no growth).
- The existing test isolation (fix 3, F6) must cover the backup and template paths too: tests never
  touch the real `STATUS.md` or `ops/state/`.
- No change to the `STATUS.md` format, the 60-line limit, `chief_tick.py next`, or the board.

## 4. One-time laptop switch-over (Gian, at home, no worker running)

Why it is needed: when the laptop pulls the commit that removes `STATUS.md` from git, git would
delete the file on disk (or refuse, because it has unsaved changes). So save it first.
In PowerShell, inside the project folder:

1. `copy STATUS.md ops\state\STATUS.backup.md` (save the live notepad)
2. `git checkout -- STATUS.md` (drop the unsaved changes so git lets you move)
3. `git switch auto/phases-7-10` then `git pull` (now on the fixed machinery)
4. `copy ops\state\STATUS.backup.md STATUS.md` (put the notepad back)
5. Check: `git status` does **not** list `STATUS.md`, and `STATUS.md` still has your `- Next:` line.

If step 4 is forgotten, H3 restores the file at the next tick anyway.

## 5. Choices (D-x). DECIDED: option 1 for all (Gian, 11 Nov 16:02)

### D-A Where the live notepad lives
1. **Same path `STATUS.md`, ignored by git.** No path changes anywhere; smallest change.
2. Move it to `ops/state/STATUS.md`. Cleaner folder, but every reference (chief.md, hooks, tick,
   board, 20+ tests, docs) changes, and more can break.

### D-B Stop workers from committing it
1. **Ignore it plus a safety-hook refusal of `git add STATUS.md` and `git add -f`.** Belt and braces.
2. Ignore it only. `.gitignore` already stops `git add -A`, but not `git add -f`.

### D-C Fresh-copy behaviour (for example the work laptop, or a lost file)
1. **Backup first, then template, with a Log line.** Never loses more than one tick.
2. Template only. Simpler, but a deleted file loses the chief's memory.

### D-D When fix 6 goes live
1. **Build now in the cloud. Gian merges it after the `phase-8-fix-1` PR merges and before Phase 10
   starts, then does section 4 at home.** To make the gap exist, Gian tells the chief (comment on #48)
   to wait for him before starting Phase 10.
2. After Phase 10, before the final PR into `main`. No hold needed, but a branch switch could block
   again during Phase 10 (fix 3's alarm would still tell Gian).

## 6. Acceptance criteria (Given / When / Then)

- AS-1 Given the `.gitignore` file, then it lists `STATUS.md` (test reads `.gitignore`).
- AS-2 Given `ops/STATUS.template.md`, then it has exactly one `- Next:` line, a `Stopped:` line and
  a `Usage:` line, and 60 lines or fewer.
- AS-3 Given `STATUS.md` exists, when a tick ends, then `ops/state/STATUS.backup.md` has the same text.
- AS-4 Given `STATUS.md` is missing and a backup exists, when a tick starts, then `STATUS.md` equals
  the backup and the Log has `STATUS.md restored from backup`.
- AS-5 Given `STATUS.md` and the backup are both missing, when a tick starts, then `STATUS.md` equals
  the template and the Log has `STATUS.md created from template`.
- AS-6 Given `STATUS.md` exists, when a tick starts, then it is not overwritten.
- AS-7 Given a worker command `git add STATUS.md` or `git add -f x`, then the safety hook refuses it;
  `git add src/da_x.py` is still allowed.
- AS-8 Given a backup copy fails (for example a locked file), when the tick runs, then it still
  returns its normal result and logs one line.
- AS-9 Given the ops test suite runs, then the real `STATUS.md` and `ops/state/` are unchanged.

## 7. Out of scope

- Anything in `src/` (the product).
- Changing the guard, usage stop lines, who merges what, or the status board layout.
- Allowing `git worktree` (stays refused).
- History of `STATUS.md`: older versions stay in git history; nothing is rewritten.

## 8. Open items

- O1: branches made before fix 6 (`auto/phase-8`, `auto/phase-9`, `phase-8-fix-1`) still hold a
  tracked `STATUS.md`. Switching to them later is refused. They are done or nearly done, so the team
  should not need them; if it does, merge `auto/phases-7-10` into them first (as PR #49 did).
