# Phase A fix 1: workers run in the background

Version 1.0 APPROVED, 7 Nov 2026. Gian chose option 1 (background launch) in the project chat.
Branch `phase-a-fix-1` (made from `auto/phases-7-10`). PR into `auto/phases-7-10`; **Gian merges this
one himself**, because it changes the chief's own machinery. Build it the normal way: plan,
plan review, build, code review, pytest, ruff, smoke check.

## 1. The problem (found in pilot A-P3, 7 Nov)

The chief starts a worker with `chief_tick.py launch` inside its own Bash tool and WAITS for it.
- Claude Code stops a Bash command after 2 minutes (10 at most). A builder runs 1 to 3 hours.
- Every worker gets `--max-turns 60`. A whole-phase builder needs far more.
- If the laptop sleeps or restarts mid-run, nothing records what happened.

AS400 comparison: today the chief does a `CALL` to a 3-hour batch program from an interactive job
with a 10-minute time-out. It must `SBMJOB` instead and look at the job queue on its next wake-up.

## 2. What we build

| # | Piece | What it does |
|---|---|---|
| F1 | **Background launch** | `launch` (the chief's command) checks the guard and hooks as today, then starts the worker as its own detached process and returns at once, printing `started <agent>`. The chief records "worker running" in STATUS.md and stops |
| F2 | **Runner** | New subcommand `chief_tick.py run-worker` (the detached process). It runs `claude -p` exactly as `real_launcher` does today, then writes `ops/state/worker_done.json` (exit code, finish time). Reply saved to `logs/workers/` as today |
| F3 | **Running note** | `ops/state/running.json`: agent, stage, phase, prompt (first 200 chars), process id, start time, usage before. One worker at a time: `launch` refuses with `busy <agent>` while it exists |
| F4 | **Tick looks at the queue first** | Before anything else, `tick` checks `running.json`: worker still alive = print `busy`, change nothing, start nothing (zero tokens). Worker finished (`worker_done.json` present) = write the STATUS.md Log line and the ledger line (moved here from `launch_worker`), remove both notes, then continue the normal tick so the chief wakes up and acts on the result |
| F5 | **Vanished worker** | Process gone and no `worker_done.json` (laptop restarted, crash): Log line `<agent> ended without a result (vanished)`, ledger outcome `vanished`, notes removed, chief wakes (D-A) |
| F6 | **Time limit** | A worker running longer than `MAX_WORKER_HOURS` (D-B) is stopped by the tick (whole process tree), logged as `stopped: over the time limit`, chief wakes |
| F7 | **Turns per agent** | `AGENT_MAX_TURNS`: chief 60, spec-writer 80, builder 400, status-digest 20, reviewers 80 |
| F8 | **Bash time-outs inside workers** | `ops/worker_settings.json` gets `"env": {"BASH_DEFAULT_TIMEOUT_MS": "900000", "BASH_MAX_TIMEOUT_MS": "1800000"}` (15 and 30 min), because the full pytest run takes about 8.5 minutes on the laptop |
| F9 | **Chief rulebook** | `chief.md`: launching starts a worker and ENDS your step: write "Running: <agent> since <time>" in STATUS.md and stop. The work after a worker (for example "After the spec writer returns") happens on the next wake-up, when the Log shows its result. Vanished or over-time: relaunch once with "continue from your last commit"; a second time, open a `needs-gian` issue |
| F10 | **Docs** | `docs/automation.md`: background launch, the two notes in `ops/state/`, what `busy` means, how to stop a running worker by hand (Task Manager, or `chief_tick.py stop`) |

Details:
- Windows: start the runner with `DETACHED_PROCESS`, `CREATE_NEW_PROCESS_GROUP` and
  `CREATE_NO_WINDOW`, so it survives the tick ending and shows no window. Linux: `start_new_session`.
- "Alive" check: the process id exists AND `running.json` is younger than the time limit. A reused
  process id after a restart is caught by the time limit and by `worker_done.json`.
- New subcommand `chief_tick.py stop`: stops the running worker and records it like F6.
- The chief itself still runs in the foreground from `tick` (a chief step is a few minutes, and
  `tick` is started by Task Scheduler, which has no Bash time-out).
- Task Scheduler: keep the default "do not start a new instance" (a tick is now seconds long).
- Allow list: `run-worker` is NOT for the chief; only `launch` starts it. `stop` is for Gian.

## 3. Choices (D-x), recommended options already applied

| # | Question | Options (ranked) | Chosen |
|---|---|---|---|
| D-A | Vanished worker | 1. Log, wake the chief; it relaunches once, then opens `needs-gian`. 2. Open `needs-gian` at once. 3. Relaunch automatically from the tick | **1**: a laptop restart is common and harmless when the builder commits after every step; a second loss is a real problem worth Gian's eyes |
| D-B | Time limit per worker | 1. 6 hours. 2. 3 hours. 3. None | **1**: a phase build plus 3 review rounds can pass 3 hours; no limit lets a stuck worker burn the week's usage (the guard still stops it at 80/85%) |

Gian may overrule either before the build.

## 4. Done when (each row becomes a test; no real `claude`, use a fake worker command)

| # | Given | When | Then |
|---|---|---|---|
| AF-1 | No worker running, guard GO, hooks ready | the chief runs `launch --agent builder ...` | it returns within seconds, prints `started builder`, `running.json` exists with the process id |
| AF-2 | A worker is running | `launch` is called again | it prints `busy builder` and starts nothing |
| AF-3 | A worker is running | `tick --launch` runs | it prints `busy`, STATUS.md and the ledger are unchanged, no chief starts |
| AF-4 | The worker finished with `worker_done.json` | `tick --launch` runs | one Log line and one ledger line are written, both notes are gone, then the chief is started |
| AF-5 | Process gone, no `worker_done.json` | `tick` runs | Log says `vanished`, ledger outcome `vanished`, notes gone, chief wakes |
| AF-6 | A worker older than `MAX_WORKER_HOURS` | `tick` runs | the process tree is stopped, Log says `over the time limit`, chief wakes |
| AF-7 | Any agent | the worker command is built | `--max-turns` comes from `AGENT_MAX_TURNS` (builder 400, chief 60) |
| AF-8 | `ops/worker_settings.json` | read | it has the two Bash time-out values from F8 |
| AF-9 | `chief.md` | read | it says a launch ends the step, and the vanished/over-time rule from F9 |
| AF-10 | Guard says STOP | `launch` is called | nothing starts, no `running.json` (as today) |
| AF-11 | Windows (mocked) | the runner is started | the three creation flags from section 2 are passed |
| AF-12 | `stop` with a running worker | run | process stopped, recorded like AF-6 |

## 5. Out of scope
- Running two workers at once.
- Any change to `src/` or to Phase 7.
- Starting the chief itself in the background.

## 6. Home check (Gian, laptop, about 15 min)
1. `git fetch origin`, `git switch phase-a-fix-1` (stash STATUS.md first if Git asks:
   `git stash push -m "status" -- STATUS.md`, then `git stash pop` after the switch).
2. `.venv\Scripts\python -m pytest tests\ops -q`: all pass (the parked Windows sandbox test is outside `tests\ops`).
3. `.venv\Scripts\python ops\chief_tick.py launch --agent builder --stage test --prompt "Run pytest -q and tell me the last line"`:
   returns at once with `started builder`. Then `tick` (no `--launch`) prints `busy`.
4. Wait about 10 minutes, run `tick` again: one Log line with the pytest result, `ops\state\running.json` gone.
5. Merge the PR into `auto/phases-7-10`. Then A-P4.

## 7. Open items
- O1: Claude Code may move a long command into the background on its own. If a worker reply shows
  that, add `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` to F8 (check the setting name in the Claude Code
  docs first).
