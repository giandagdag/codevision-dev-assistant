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
1. **Fill in the usage settings.** The endpoint is not documented by Anthropic, so nothing is
   guessed in the code. Set two environment variables (Windows PowerShell, this window only):
   - `$env:DA_USAGE_URL = "<https address of the usage endpoint>"`
   - `$env:DA_USAGE_TOKEN_FILE = "<path to a file outside the repo holding your login token>"`
   Then run `.venv\Scripts\python ops\usage_guard.py`. Expect `GO: ...`. If it says `STOP: guard blind`,
   the reply shape differs: send the reply shape (no token!) and the reader gets a small fix.
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
1. **Branch protection on `main`:** Settings, Branches, add a rule for `main`: require a pull
   request and your approval, and include administrators. This is the real wall: permission
   rules cannot filter `git push` by branch.
2. **A fine-grained token for this one repo only:** Settings, Developer settings, Personal access
   tokens, Fine-grained. Repository access: only this repo. Permissions: Contents read/write,
   Pull requests read/write, Issues read/write. Log in `gh` with it on the laptop
   (`gh auth login`). Never put the token in the repo.
3. **Create the labels** `needs-gian` and `needs-work-test` in the repo (Issues, Labels).
4. **Create the branch `auto/phases-7-10`** from `main` (the chief merges phase PRs into it).

## Laptop power (O3)
Settings, System, Power: set "sleep" to Never while plugged in, during the hours the team works.

## Known gap: no CI yet
The merge helper only merges when GitHub shows every check green, and it refuses when there are
no checks at all (it cannot prove green). The repo has no GitHub Actions yet, so every merge is
refused until you decide: add a small GitHub Action that runs pytest and ruff, or accept the
worker's local results. Until then the chief opens a `needs-gian` issue instead of merging.
