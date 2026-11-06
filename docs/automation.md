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
| Memory | `STATUS.md` | The chief's whole memory (max 60 lines, has a `Usage:` line) |
| Ledger | `logs/usage-ledger.csv` | One line per worker run (stays on the laptop) |

All three hooks only act inside workers (`DA_WORKER=1`). Your own sessions are never blocked.

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
   `needs-gian` issue "hooks cannot start" is opened. Check the hooks' shell: Claude Code runs hook
   commands through Git Bash on Windows, so Git for Windows must be installed.
4. **Rewrite check:** in a worker (`$env:DA_WORKER = "1"`) run `claude -p "run pytest"` and check
   that a `logs/quiet/*.log` file appears. The Claude docs do not say whether the rewrite works in
   `-p` mode, so this is the real test. The CLAUDE.md rule is the fallback.
5. **Ledger:** run one worker and check `logs/usage-ledger.csv` has a line. Check the token
   column names against the real `--output-format json` output.
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
