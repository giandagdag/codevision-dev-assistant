# Phase A (Automation foundation): build plan

Spec: `specs/phase-a-automation.md` v1.0 (the only spec read). Branch: `phase-a` (from `origin/main`,
Phase 6 is merged there, so spec O5 is met). Baseline before any change: to be pasted in step 1
(pytest, ruff, smoke check).
House rules apply to every step: surgical changes, tests with each step, paste real results.
Stop rules apply to every step. Product code under `src/` is NOT touched (spec section 11).

## The shape of the change (in AS400 words)

Today Gian is the job scheduler. Phase A builds the scheduler: a small Python job that wakes every
30 min (like a `STRSBMJOB` with a job schedule entry), checks a data area (`ops/state/usage.json`)
before every step, starts one worker job only if the answer is GO, and writes a job log (the ledger).
No new library: only the Python standard library (`json`, `csv`, `subprocess`, `urllib`) and the
`gh` command line tool Gian already has.

## Facts checked in the Claude Code docs (6 Nov 2026) that shape the design

| # | Fact | Effect on the plan |
|---|---|---|
| F1 | A hook gets JSON on stdin (`tool_name`, `tool_input.command`). Exit code 2 blocks the call and sends stderr to the agent. A hook can also answer with JSON `permissionDecision: deny` | The guard hook blocks with exit 2 and a plain reason (AC-2) |
| F2 | A PreToolUse hook rewrites a Bash command with `hookSpecificOutput.updatedInput` (the whole input object). **Not tested in `-p` mode by the docs** | Quiet-runner rewrite is built and unit-tested on the hook's output. Real `-p` check is part of A-P1. The CLAUDE.md rule (D-E says "plus a rule") is the fallback |
| F3 | **`--bare` skips hooks** (settings and `--settings`) | Workers must NOT use `--bare`, or the guard would be switched off. Workers use `--strict-mcp-config` with an empty MCP file, `--setting-sources project,local` (no user plugins), `--disable-slash-commands`, `--model`, `--max-turns`, `--output-format json` |
| F4 | **No documented usage endpoint.** The only documented source of the plan % is the status line JSON (`rate_limits.five_hour.used_percentage`, `rate_limits.seven_day.used_percentage`, `resets_at`), only in an interactive session | Spec D-D option 1 (undocumented endpoint) is what Gian chose, so I build it, but **with no URL guessed**: the reader takes URL and token path from settings. Empty = guard blind = STOP (fails closed). See Question 1 |
| F5 | `--output-format json` returns `result`, `session_id`, `total_cost_usd`, `usage.*` (field names to be confirmed on the laptop build) | The ledger reads tokens defensively (missing = blank) and the field names are confirmed in A-P1 |

## Decisions I made where the spec is silent (none change an acceptance row)

| # | Choice | Why |
|---|---|---|
| X1 | New code lives in `ops/` (plain scripts, spec names `ops/usage_guard.py`, `ops/quiet.py`, `ops/chief_tick.py`), **not** under `src/` (it is not the product and is not copied to CodeVision). Tests in `tests/ops/`; `pyproject.toml` `pythonpath` gets `"ops"` added. New files start with `da_`? **No**: the spec names them without `da_`, and they are outside `src/`. Spec wins | Spec section 3 names, section 11 scope |
| X2 | Guard answer is one function `decide(state, now, limits) -> Decision(go, reason, resets_at)`, pure and easy to test. The reader (network) is separate and is injected | Tests never call the internet (safety rule) |
| X3 | Stop lines are constants in `ops/usage_guard.py`: weekly 80, five-hour 85 (Gian's decision 2). Stale reading (older than 10 min) counts as blind | Fail closed |
| X4 | Reset times shown in Singapore time (SGT, UTC+8, `zoneinfo` is standard library, with a fixed +8 fallback if tz data is missing on Windows) | AC-1 text |
| X5 | `chief_tick.py` is **decision logic only plus a worker launcher that tests replace with a fake**. It never runs a real `claude` in tests. GitHub questions use `gh issue create/list` through `subprocess` (no library, token comes from `gh`'s own login) | No new library, safe tests |
| X6 | STATUS.md is written by code (`ops/status.py` helper) in a fixed template, max 60 lines, trimmed oldest-first. The "Haiku digest" worker is only a prompt file in `.claude/agents/`, not run in Phase A | Spec A3 and A4, pilot is later |
| X7 | CLAUDE.md size budget: a test fails if CLAUDE.md is over 6,000 bytes (it is 4,695 today; the rule additions for O4 and the quiet runner must fit). The budget number is my choice | Spec A3 says "a size budget" without a number. Question 2 |
| X8 | Ledger columns: `time_sgt, phase, stage, model, five_hour_before, five_hour_after, weekly_before, weekly_after, input_tokens, output_tokens, cost_usd, outcome`. Written by `ops/ledger.py`, one line per worker run, also when the worker failed or the guard stopped it (AC-7) | Spec A5 |
| X9 | `logs/` is already ignored by Git, so the ledger and quiet logs stay on the laptop. I keep that (they are machine-specific, may hold code snippets) | Question 3 |
| X10 | The chief agent file and worker prompts are prompts, so they are not unit-testable. They get a **structure test** (front matter, model, tool list, the section 6 table rows present, the "Never" list present) | Checkable without a real AI |

## Steps (each ends with tests and ruff clean; one commit per step; push `phase-a` after each group)

1. **Baseline and CLAUDE.md "Current phase".** Done in this plan step: CLAUDE.md "Current phase"
   updated, this plan written. Next: `plan-reviewer`. Then paste baseline pytest, ruff, smoke check.
2. **A3 Lean context pack.** `STATUS.md` (template, 60 line cap) and `ops/status.py` (read and
   write, trim). CLAUDE.md: add the O4 safety rule (`auto/phase-N` and `auto/phases-7-10`, only the
   chief merges, only into `auto/phases-7-10`), the quiet-runner rule, the Ponytail one-liner
   ("end every reply with what you skipped, and risks"), and move the Phase 6 detail out of
   "Current phase" if needed to fit the budget. Handoff note: archive and point to STATUS.md
   (Question 4: I find no handoff file in the repo). `.claude/mcp-empty.json` (`{"mcpServers": {}}`)
   for workers. Tests: STATUS.md over 60 lines is trimmed to 60; CLAUDE.md under the budget;
   the O4 words are present. *Check:* `pytest tests/ops/test_status.py`.
3. **A1 Usage guard.** `ops/usage_guard.py`: `read_usage` (injected reader), `decide`,
   `write_state` (`ops/state/usage.json`, ignored by Git), `main` (prints GO or STOP, exit 0 or 1),
   and `ops/guard_hook.py` (PreToolUse hook: reads state, exit 2 when over the line or blind or
   stale). Hook registered in `.claude/settings.json` for every tool (no matcher). Tests (AC-1, 2,
   3 parts): weekly 79 = GO, 80 = STOP; 5-hour 84 = GO, 85 = STOP; missing, stale or unreadable
   state = STOP with "guard blind"; reset time shown in SGT; hook exit 2 with a plain message on
   STOP and exit 0 on GO; hook never crashes (any error = block). *Check:* `pytest tests/ops/test_usage_guard.py`.
4. **A2 Quiet runner.** `ops/quiet.py pytest|ruff|git ...`: runs the command, writes the full
   output to `logs/quiet/<time>.log`, prints a short summary plus failures only, returns the real
   exit code. Only `pytest`, `ruff`, `git status|diff|log` are allowed (anything else is refused
   with a plain message). `ops/quiet_hook.py`: PreToolUse hook on Bash that rewrites those
   commands via `updatedInput` (whole input object kept, F2). Tests (AC-6): a tiny pytest project
   with 1 failure shows summary plus that one failure, and the log file exists; 0 failures shows
   one line; ruff and git summaries; hook rewrites `pytest -x` and leaves `echo hi` alone;
   `git commit` and `git push` are NOT rewritten. *Check:* `pytest tests/ops/test_quiet.py`.
5. **A5 Token ledger.** `ops/ledger.py`: append one line, header written once, safe if the file
   is missing or the numbers are missing. Tests (AC-7): two runs give two lines; a failed run still
   gets a line. *Check:* `pytest tests/ops/test_ledger.py`.
6. **A4 Chief rulebook and team.** `.claude/agents/chief.md` (Sonnet, never writes product code,
   spec section 6 table and "Never" list), `spec-writer.md` (Opus), `builder.md` (Sonnet),
   `status-digest.md` (Haiku); the existing reviewers stay as they are. `docs/automation.md`: the
   pipeline (section 7), how questions reach Gian (`needs-gian` issues), laptop power setting (O3),
   and the step-by-step for O2 (fine-grained token, branch protection on `main`). `ops/chief_tick.py`:
   guard check first (zero tokens when STOP), writes STATUS.md "Stopped: weekly 8x%, resets
   <time SGT>" (AC-1), opens a `guard blind` issue once (AC-3, no duplicate when one is open),
   opens `needs-gian` issues for work-fact items (AC-4 logic), launches a worker only if GO and
   work exists, writes a ledger line, and the merge helper refuses any base branch except
   `auto/phases-7-10` (AC-5, code side). Tests with a fake runner, fake `gh` and fake clock.
   *Check:* `pytest tests/ops/test_chief_tick.py tests/ops/test_agent_files.py`.
7. **Windows Task Scheduler.** `ops/install_chief_task.ps1`? **Not built.** The spec says Task
   Scheduler runs `ops/chief_tick.py` but Gian runs PowerShell commands himself, so I give him the
   exact `schtasks` command in `docs/automation.md`, to run at A-P1. Nothing here runs it.
8. **Finish.** Full `pytest`, `ruff check .`, smoke check (all through the quiet runner once it
   exists, plus the plain commands pasted), `code-reviewer` (max 3 rounds), commit, push `phase-a`,
   and Gian's A-P1 check list (laptop) in the final report.

## What cannot be proven in this cloud session (honest list)

- Guard reading the real plan % (needs the laptop login, O1).
- The quiet hook's rewrite actually working inside `claude -p` (F2, untested by the docs).
- GitHub refusing a merge into `main` (O2, Gian sets branch protection himself).
- A-P2 to A-P4 (pilot) are after this phase.

## Questions for Gian

1. **Usage endpoint (D-A, F4).** The docs name no usage endpoint, and I will not guess one. Is it
   OK that the guard ships with the endpoint URL and token path empty in settings (it then says
   "guard blind" and STOPS everything until you fill them in at A-P1)? FYI, the official
   alternative is the status-line `rate_limits` numbers (your D-D option 2). I do not switch to it
   unless you say so. *Recommended:* yes, ship empty, fill at A-P1.
2. **CLAUDE.md size budget.** OK with 6,000 bytes (today 4,695)? *Recommended:* yes.
3. **Ledger and quiet logs stay local** (Git ignores `logs/`). OK? *Recommended:* yes.
4. **Handoff note.** I cannot find a handoff file in the repo (it may be in your project chat). Send it
   when ready, or tell me there is nothing to archive. Phase A does not depend on it.
