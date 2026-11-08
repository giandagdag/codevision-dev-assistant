# Automation: how the agent team runs (Phase A)

AS400 comparison: a job schedule entry wakes a small job every 30 minutes. It checks a data area
(the usage guard) and only submits the real job when the answer is GO. Every job writes a log line.

## The pieces
| Piece | File | What it does |
|---|---|---|
| Usage guard | `ops/usage_guard.py`, `ops/guard_hook.py` | GO or STOP at 80% weekly or 85% of the 5-hour limit. Blind = STOP |
| Quiet runner | `ops/quiet.py`, `ops/quiet_hook.py` | Short summary of pytest, ruff, git status/diff/log. Full output in `logs/quiet/` |
| Safety hook | `ops/safety_hook.py` | No push to `main`, no force push, no `.env`, no deleting outside `logs/` and `ops/state/` |
| Chief and team | `.claude/agents/chief.md` and others, `ops/chief_tick.py` | The decision rule and the wake-up job |
| Memory | `STATUS.md` | The chief's whole memory (max 60 lines, has a `Usage:` line, exactly one `- Next:` line) |
| Ledger | `logs/usage-ledger.csv` | One line per worker run (stays on the laptop) |

All three hooks only act inside workers (`DA_WORKER=1`). Your own sessions are never blocked.

## Workers run in the background (Phase A fix 1)
AS400 comparison: `launch` is `SBMJOB` (submit and return). The tick is the job that looks at the
job queue on each wake-up.

A worker (builder, spec writer, reviewer) runs 1 to 3 hours, far longer than a Bash command in
Claude Code may run. So `chief_tick.py launch` only checks the guard and hooks, starts the worker as
its own detached process (`chief_tick.py run-worker`, not for you or the chief), prints
`started <agent>` and returns. The chief writes "Running: <agent> since <time>" in STATUS.md and
stops. The chief itself still runs in the foreground from `tick`.

Two notes in `ops/state/` (local, Git ignores them):
| File | Written by | Holds |
|---|---|---|
| `running.json` | `launch` | agent, stage, phase, first 200 characters of the prompt, process id, start time, usage before |
| `worker_done.json` | the runner | exit code, finish time, the reply (the reply also goes to `logs/workers/`) |

What the tick does first on every wake-up (zero tokens while a worker runs):
- **`busy`**: the worker is alive and younger than 6 hours (`MAX_WORKER_HOURS`). Nothing changes.
  `launch` also says `busy <agent>` while `running.json` exists: one worker at a time.
- **Finished** (`worker_done.json`): one Log line, one ledger line, both notes removed, then the
  normal tick goes on and the chief wakes up.
- **Vanished** (process gone, no `worker_done.json`, for example the laptop restarted): Log says
  `ended without a result (vanished)`, ledger outcome `vanished`. The chief relaunches once with
  "continue from your last commit"; a second time it opens a `needs-gian` issue.
- **Over the time limit**: the tick stops the whole process tree and logs `stopped: over the time
  limit`. Same relaunch rule.

**Stop a running worker by hand:** `.venv\Scripts\python ops\chief_tick.py stop` (Log says
`stopped: by hand`, the chief does not relaunch), or end `python.exe` and `claude.exe` in Task
Manager (the tick then logs it as vanished). Task Scheduler: keep "do not start a new instance".
Turns per worker are in `AGENT_MAX_TURNS` (builder 400, chief 60). Inside a worker a Bash command may
run 15 minutes (30 at most), because the full pytest run takes about 8.5 minutes.

## The "Team status" issue (Phase A fix 2)
AS400 comparison: a job that refreshes ONE message on a shared display at every wake-up. You look;
you do not run a report. Open GitHub on your phone and read the pinned issue **🤖 Team status**
(label `team-status`).

`ops/status_board.py` builds it from local files (STATUS.md, `ops/state/running.json`,
`ops/state/usage.json`, git, and `gh issue list`). Plain Python, zero tokens. The tick refreshes
it at the end of **every** wake-up (`busy`, `stopped`, `idle`, `ran`, `hooks-broken`,
`would-start`) and after `launch` and `stop`. It only edits when the text changed, plus once an
hour, so GitHub does not notify you for edits. If the board fails (for example `gh` is down) the
tick carries on, and one line goes to `logs/status_board.log`.

| Top line | Meaning |
|---|---|
| 🔴 WAITING FOR YOU | an open `needs-gian` issue, or STATUS.md `Next:` says "waiting for Gian". It outranks the rest, so during a blind guard or broken hooks it is normally red (the tick opens a `needs-gian` issue for those) |
| ⚫ GUARD BLIND | the usage cannot be read, nothing starts |
| 🟡 PAUSED: usage | the guard said STOP; the line shows which limit and the reset time (SGT) |
| 🟠 HOOKS BROKEN | the safety hooks cannot start, no worker launched |
| 🟢 WORKING | a worker is running (agent, phase, running time) |
| ⚪ IDLE | nothing running and `Next:` is none |
| 🔵 READY FOR NEXT STEP | work exists; the next tick starts it |

**Progress bars** are 10 characters of `▓░`, rounded down. Phase progress: Spec 15%, Plan 10%,
Build 55% (by step: highest "Phase N step K" commit over the plan's numbered steps), Code review
15% (5% per "code review round" commit; the full 15% when the branch is pushed and the last round
says "0 Must fix", a stand-in because the board cannot run tests), Merged 5%. Overall =
(merged phases x 100 + current phase %) / 4. A stage that cannot be read counts as not done and the
line says "(estimate)". The usage bars show the guard's numbers next to the stop lines (85% for 5h,
80% weekly), or `blind`.

**A stale "Updated" time means check the laptop**: the tick has stopped running (laptop off or
asleep, Task Scheduler stopped).

The issue is created on the first tick if it does not exist (found by number in
`ops/state/status_issue.json`, then by title), pinned once, and never closed by the tick.
Nothing from `usage_raw.json`, `.env` or worker reply files is put into it.

The runner starts `claude` with `CREATE_NO_WINDOW` on Windows, so no black window appears.

## No more silent stalls (Phase A fix 3)
AS400 comparison: a job waiting on a message (MSGW) looks the same as a quiet job until someone
runs WRKACTJOB. Fix 3 is the alarm that rings, so "stuck" no longer looks like "nothing to do".
Plain Python, zero tokens: it never starts Claude. Live on the laptop once `auto/phases-7-10` with
fix 3 is pulled there (Phase 9 starts from it).

**The stall alarm** (`ops/stall.py`, run by `ops/chief_tick.py` on a tick that ends `idle`). The team
is stalled, first match wins, when:
1. STATUS.md has no `- Next:` line, or more than one: "no valid Next line".
2. `Next: none`, no open `needs-gian` issue, and the final PR (`auto/phases-7-10` into `main`) is not
   open: "nothing to do, but the job is not finished".
3. A finished worker left commits that `origin` lacks: "unpushed commits on auto/phase-N". This one
   is checked even while a `needs-gian` issue is open.

A stall opens ONE `needs-gian` issue `🔴 Team stalled: <reason>` (phone notification, same channel as
questions), one Log line, and a note the board reads. No second issue while one with that title is
open. The tick never closes it: **you close it** once the cause is fixed. The board stops showing
STALLED the moment the rule no longer matches. Because the issue itself is `needs-gian`, the board
normally shows WAITING FOR YOU; STALLED shows alone only if `gh` was down. If `gh` or `git` fails
inside the alarm, one line goes to `logs/status_board.log` and the tick still returns `idle`.
Expect one alarm on day one if some STATUS.md was made by hand (spec O1): that is the alarm working.
A doubled `Next:` line raises it only when the first one says `none` (the tick reads the first line).

**Unpushed commits.** When the tick records a finished, vanished or over-time worker, it compares
`auto/phase-N` with `origin/auto/phase-N` (`git rev-list --count`, no fetch). More than 0 gives the Log
line `UNPUSHED: 2 commits on auto/phase-8` and a board warning line, re-counted each tick, so it goes
away after a push.

**One `Next:` line.** STATUS.md has exactly one `- Next:` line under "## Where we are". Set it with
`.venv\Scripts\python ops\chief_tick.py next "builder continue Phase 8 from step 10"` (empty text is
refused; keep the text plain: no quotes inside and no `;` `&` `|` `>`, the safety hook cannot read
them). It replaces the line and its indented continuation lines, never appends, so STATUS.md stays at
60 lines or fewer. The chief and builder use this command and never hand-edit the line.

**Builder runs are small.** The builder builds at most 3 plan steps per run, tests, commits and
pushes after each, then runs `next "builder continue Phase N from step K"` and stops. The chief sees
that line and relaunches the builder (never a `needs-gian` question). Code review starts only after
the last plan step. Phase 8's 15 steps become 5 runs.

**Fewer denied calls.** Workers may now run read-only `grep`, `head`, `tail`, `wc`, `git show`,
`git rev-parse`, `git rev-list`, `git branch`, `git ls-remote` and the smoke check. The deny list is
unchanged, and the safety hook still blocks workers from editing `ops/`. Agents are told **one
command per Bash call**: no `;`, `&&` or pipes (they are refused), and to use the Read and Grep tools
to look at files. Note: `git branch` can still rename or force-move a branch (`-m`, `-f`); only the
delete flags are blocked by the safety hook.

**Tests no longer write to the real files.** `tests/ops/conftest.py` points the ledger, worker reply
folder, state folder, quiet logs, board log and STATUS.md at a temp folder for every ops test, and a
last test (`test_ops_zz_real_logs.py`) checks that the real `logs/usage-ledger.csv` and `logs/workers/`
did not change. The 5 junk rows already in the laptop ledger are not touched; remove them by hand.

## How questions reach you
One GitHub issue per question, label `needs-gian` (or `needs-work-test` for things that need the
work laptop). You get a phone notification and answer in a comment. The chief reads it on its next wake-up.

## Pilot A-P1 (laptop, you present). Do these in order
1. **Check the guard reads your real usage.** Nothing to set up: it reads your Claude login from
   `%USERPROFILE%\.claude\.credentials.json` (read only, never written) and asks
   `GET https://api.anthropic.com/api/oauth/usage` with the header `anthropic-beta: oauth-2025-04-20`.
   Log in to Claude Code once on the laptop first. Run `.venv\Scripts\python ops\usage_guard.py`.
   - Expect `GO: within the usage lines`. Then run it with a Python prompt to see the numbers:
     `.venv\Scripts\python -c "import sys; sys.path.insert(0,'ops'); import usage_guard as g; print(g.endpoint_reader())"`
   - **Compare the 5-hour and weekly numbers with Settings, Usage in Claude.** They must match
     (`utilization` is a percent from 0 to 100).
   - **Open `ops\state\usage_raw.json`.** Every read saves the raw reply there (local, Git
     ignores it, it never holds your token). Check the layout: the guard understands
     `five_hour` / `seven_day` with `used_percentage` or `utilization`. If the reply is a `limits`
     list instead, that layout is not supported yet and the guard says "guard blind". Send me the
     file (no secrets in it) and I add it.
   - On a 401 the guard runs `claude -p "/usage"` once and tries again. If it still fails you get
     `STOP: guard blind` and nothing starts (that is the safe answer).
   - This endpoint is not an official API and can change. The guard understands two reply shapes
     (the status-line shape with `used_percentage`, and a `utilization` shape). Anything else, a
     missing value, or a value outside 0 to 100 is "guard blind". The token's place in the
     credentials file (`claudeAiOauth.accessToken`) is my assumption, so this step is the proof.
2. **Fake STOP:** edit the stop lines at the top of `ops/usage_guard.py` to 1, run it again,
   expect `STOP`, then put them back to 85 and 80.
3. **Hook interpreter.** The three hooks in `.claude/settings.json` run with `$DA_PYTHON`, which
   `chief_tick.py` sets to the Python that runs it (use your `.venv\Scripts\python.exe` in the
   scheduled task). Outside a worker it is unset, so the hooks do nothing. Before every worker the
   chief proves the three hooks start and fail closed; if not, no worker starts and a
   `needs-gian` issue "hooks cannot start" is opened.
   **The hook strings are bash syntax, and on Windows Claude Code runs them in Git Bash.** It finds
   Git Bash like this (Claude Code docs, checked 6 Nov): first the default folders
   `C:\Program Files\Git` and `C:\Program Files (x86)\Git` (`bin\bash.exe`), then the `git` on PATH.
   So it works even when `bash` is not on your PowerShell PATH. To point it at another one, set
   `CLAUDE_CODE_GIT_BASH_PATH` (in settings.json: `{"env": {"CLAUDE_CODE_GIT_BASH_PATH":
   "C:\\Program Files\\Git\\bin\\bash.exe"}}`). A wrong path is ignored with a warning you can see
   with `claude --debug`. No screen names the bash it picked, so check it yourself:
   - `where.exe git` and look for `C:\Program Files\Git\bin\bash.exe`.
   - `.venv\Scripts\python -m pytest tests\ops -k settings_hooks -rs`: it must PASS, not skip.
     It runs the three real hook strings in that bash.
   - **Without Git Bash the hooks run in PowerShell, fail, and the docs say a failed PreToolUse
     hook then BLOCKS the tool call.** That would also block your own sessions in this repo, so
     install Git for Windows before turning on the hooks.
4. **Rewrite check:** run `.venv\Scripts\python ops\chief_tick.py launch --agent builder --stage test --prompt "Run pytest -q and tell me the last line"`.
   The Claude docs do not say whether the rewrite works in `-p` mode, so this is the real test.
   Look for a file in `logs\quiet\`. **If nothing appears, read what the worker said:**
   - `STATUS.md`, the Log section: one line per worker with the first line of its answer, how many tool
     calls were denied, and the file name.
   - `logs\workers\<time>-<agent>.json`: the whole reply (`result` text, `permission_denials`,
     `usage`, errors). Local only, Git ignores it. `permission_denials` lists every tool call the
     permission rules refused, with the command.
   Workers start with the PowerShell tool switched off and the `.venv` folder first on PATH (so plain
   `pytest` works); Git Bash is pointed at `C:\Program Files\Git\bin\bash.exe` when it is there.
5. **Ledger:** run one worker and check `logs/usage-ledger.csv` has a line. `input_tokens` counts
   only the uncached input: the real input is `input_tokens + cache_read_input_tokens +
   cache_creation_input_tokens` (separate columns). An older ledger file with the old columns is set
   aside as `usage-ledger.old-<time>.csv`, never mixed.
6. **Dry tick:** `.venv\Scripts\python ops\chief_tick.py tick` (no `--launch`) prints what it would do.
7. **Schedule it** (only when you are happy). Replace `C:\path` with the repo folder:
   `schtasks /Create /TN "CodeVision chief tick" /SC MINUTE /MO 30 /TR "C:\path\.venv\Scripts\python.exe C:\path\ops\chief_tick.py tick --launch"`
   Stop it with `schtasks /Delete /TN "CodeVision chief tick"`.

## Things you set once in GitHub (O2)
**Branch protection is not available** (private repo on the free GitHub plan), so GitHub itself
will not refuse a push or merge into `main`. Only your own rules and tools do. The safety net is:
1. **The safety hook** (`ops/safety_hook.py`): checks every command a worker runs.
2. **The deny list** (`ops/worker_settings.json`): no push or merge to `main`, no force push, no
   `git remote add / set-url / remove`, no `.env`, no deleting outside `logs/` and `ops/state/`.
3. **The ZIP backup of `main`** (see "Before the first unattended run").
4. **The merge helper** only merges into `auto/phases-7-10`, and only when the check is green.

What to do once:
1. **Agents use your own GitHub login** (`gh auth login`; your decision, 6 Nov: no bot account).
   They have your rights, including admin on this repo, so the three items above matter.
2. **Create the labels** `needs-gian` and `needs-work-test` in the repo (Issues, Labels).
3. **Create the branch `auto/phases-7-10`** from `main` (the chief merges phase PRs into it).

## Honest limits of the safety hook
`ops/safety_hook.py` is best-effort. A worker can run Python (`.venv` python is allowed because it
must run pytest), and a program can build a forbidden path from pieces. With no branch protection
available, nothing on GitHub catches that. So the ZIP backup of `main` is not optional: take it
before the first unattended run, and again before each A-P4 round. Also check at A-P1 that the
permission layer accepts the quiet runner's rewritten command (it uses an absolute path).
Spec AC-5 ("a merge into `main` is refused by GitHub") therefore cannot be met on this plan; the
hook, the deny list and the merge helper refuse it instead.

## Laptop power (O3)
Settings, System, Power: set "sleep" to Never while plugged in, during the hours the team works.

## Checks (GitHub Action)
`.github/workflows/ci.yml` runs pytest, ruff and the smoke check (Python 3.14, fake AI, no secrets)
on every push to `auto/**` and `phase-*`, and on pull requests into `auto/phases-7-10` and `main`.
The chief's merge helper only merges when this check is green, and it still refuses when a PR has
no checks.
It has not run on GitHub yet: its first run is the push of branch `phase-a`. Look at the Actions
tab, and if it is red, tell me before A-P1 (for example if Python 3.14 is not available there).

## Before the first unattended run
Do these once, in this order:
1. **Backup.** On GitHub open the repo, switch to the `main` branch, Code, **Download ZIP**.
   Keep the file somewhere outside the repo folder (name it with today's date). This is your
   "save library before the upgrade" copy.
2. **Do not pull or switch branches on the laptop while agents run.** The workers use the same repo
   folder, so a `git pull`, `git switch` or file edit under them breaks their work. For your own
   reading or testing, use a second clone in another folder. Pull `main` only when the team is stopped.
3. **If a bad merge happens, revert it, do not delete history.**
   - A bad merge into `auto/phases-7-10`: on GitHub open the merged pull request, press **Revert**,
     and merge the revert pull request it creates. Or on the laptop (team stopped):
     `git switch auto/phases-7-10`, `git revert -m 1 <merge commit id>`, `git push`.
     Find the id with `git log --merges --oneline`.
   - A bad merge into `main` (you merged it): the same, through a revert pull request.
   - Never force-push. If everything is lost, unzip the backup from step 1 into a new folder.
4. Confirm the labels and the `auto/phases-7-10` branch exist (O2 above), then follow the pilot list.
