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
| X11 | **The guard hook only acts inside workers** (review Must fix 1). The launcher sets `DA_WORKER=1`; the hook does nothing (exit 0) when it is not set. So Gian's own sessions, this cloud build and the reviewers are never blocked. Registered in `.claude/settings.json` for every tool, harmless outside workers | Spec A1 says "a hook in every worker", not every session |
| X12 | **How a blocked worker saves state and stops** (review Must fix 2). When the guard says STOP, the hook still allows exactly one thing: Write or Edit of `ops/state/worker_note.md` (the same way a job writes its last log line before ending). Every other tool is blocked, and the block message says: "Usage line reached. Write your state to ops/state/worker_note.md, then stop." Backup: after the worker exits, `chief_tick` records the exit reason and the note (if any) in STATUS.md and the ledger, so state is saved even if the worker ignored the message. Every worker prompt carries the line "If the guard blocks you, write the note and stop at once". Work is committed per step by the builder, so nothing is lost | AC-2 |
| X13 | **Work-fact and paused stages** (review Should fix). The chief PROMPT decides what counts as a work fact (a judgment, not code). `chief_tick.py` provides two helpers the chief calls: `open_gian_issue(title, body, label)` (labels `needs-gian` or `needs-work-test`, no duplicate when an open issue has the same title) and `mark_paused(stage, issue)` (a line in STATUS.md). Tested with fake `gh`; `chief.md` is structure-tested for the rule | AC-4 |
| X14 | **Merge helper** refuses any base except `auto/phases-7-10` AND any head whose checks are not all green (`gh pr checks`, fake `gh` in tests) | Spec section 7 step 5, AC-5 |
| X15 | **Worker permissions.** The launcher runs `claude -p` with `--permission-mode dontAsk`, an allow list (Read, Grep, Glob, Edit, Write, the quiet runner, `git add/commit/push` to `auto/*` and `phase-*` only) and a deny list in `ops/worker_settings.json` (`git push` to `main`, `--force`, `.env`, plugin install). A test checks the deny rules exist and the launcher passes the flags. Prompts repeat the "Never" list; GitHub branch protection (O2) is the real wall. **Question 5** | Spec sections 4 and 6 |
| X16 | `ops/state/` is added to `.gitignore` in step 3 (checked with `git check-ignore`). The usage token is never printed or logged; its path points outside the repo; a test checks an error message does not contain the token | Safety rules |
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
   stale). Hook registered in `.claude/settings.json` for every tool (no matcher), acts only when `DA_WORKER=1` (X11), allows only the `worker_note.md` write on STOP (X12). `.gitignore` gets `ops/state/` (X16). Tests (AC-1, 2,
   3 parts): weekly 79 = GO, 80 = STOP; 5-hour 84 = GO, 85 = STOP; missing, stale or unreadable
   state = STOP with "guard blind"; reset time shown in SGT; hook exit 2 with a plain message on
   STOP and exit 0 on GO; **hook does nothing when `DA_WORKER` is not set, even if state is
   missing**; on STOP the `worker_note.md` write is allowed and every other tool is blocked;
   hook never crashes inside a worker (any error = block); error messages never contain the token. *Check:* `pytest tests/ops/test_usage_guard.py`.
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
   provides `open_gian_issue` and `mark_paused` (X13, AC-4), launches a worker (flags per X15,
   sets `DA_WORKER=1`) only if GO and work exists, after the worker exits records its exit reason
   and `worker_note.md` in STATUS.md (X12), writes a ledger line, and the merge helper refuses
   any base except `auto/phases-7-10` and any red or pending checks (X14, AC-5 code side).
   `ops/worker_settings.json` holds the deny rules (X15). Every worker prompt carries the
   "guard blocks you: write the note and stop" line. Tests with a fake runner, fake `gh` and fake clock.
   *Check:* `pytest tests/ops/test_chief_tick.py tests/ops/test_agent_files.py`.
7. **Windows Task Scheduler.** No script is built. The spec says Task Scheduler runs
   `ops/chief_tick.py`; I give Gian the exact `schtasks` command in `docs/automation.md`, to run
   at A-P1. Nothing here runs it.
8. **Finish.** Full `pytest`, `ruff check .`, smoke check (all through the quiet runner once it
   exists, plus the plain commands pasted), `code-reviewer` (max 3 rounds), commit, push `phase-a`,
   and Gian's A-P1 check list (laptop) in the final report.

## What cannot be proven in this cloud session (honest list)

- Guard reading the real plan % (needs the laptop login, O1).
- The quiet hook's rewrite actually working inside `claude -p` (F2, untested by the docs).
- GitHub refusing a merge into `main` (O2, Gian sets branch protection himself).
- A-P2 to A-P4 (pilot) are after this phase.

## Plan review

Round 1: 2 Must fix (guard hook would block every session, not only workers; a blocked worker
had no way to save state). Both fixed above (X11, X12), plus the Should fix items (X13 to X16).
Round 2: both round 1 items confirmed fixed. **1 new Must fix**, so the plan is NOT approved and
the cap (1 fix round) is reached. STOPPED for Gian.
- **Must fix:** nothing refreshes `ops/state/usage.json` while a worker runs, and X3 treats a
  reading older than 10 minutes as blind. Every worker running longer than 10 minutes would be
  blocked, and AC-2 could not see a live 85% crossing.
- **Reviewer's proposed fix (not applied yet):** the guard hook re-reads the usage itself through
  the injected reader when the file is older than 2 to 3 minutes, and blocks if that re-read
  fails. Tests: fresh state = GO, stale state triggers a re-read, failed re-read = block.
- **Should fix (to fold in with the above):** test that only the exact resolved path
  `ops/state/worker_note.md` is allowed on STOP (`ops/state/../x` is blocked); and the guard
  decision wins when the guard hook and the quiet rewrite hook both run on Bash.
- **FYI:** `git push` cannot be filtered by branch name in permission rules, so GitHub branch
  protection (O2) is the real wall. Question 5 should say so.

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
5. **Worker permissions (X15).** OK that unattended workers run with `dontAsk` plus an allow list
   and a deny list, instead of `bypassPermissions`? *Recommended:* yes. It is stricter, and a
   worker that needs something outside the list stops and asks through an issue.

## Gian's answers, 6 Nov 2026 (plan APPROVED, build)

- Reviewer's fix approved, with the 2 smaller items, no second plan review: **X17** the guard hook
  re-reads usage through the injected reader when `usage.json` is older than 3 minutes, and blocks
  if the re-read fails (tests: fresh = GO, stale = re-read, failed re-read = block). **X18** only the
  exact resolved path `ops/state/worker_note.md` is allowed on STOP (`ops/state/../x` blocked).
  **X19** when the guard and quiet hooks both run on Bash, the guard decision wins.
- Q1 yes (endpoint empty, blind = STOP until A-P1). Q2 yes (6,000 bytes). Q3 yes (logs local),
  plus **STATUS.md has a `Usage:` line the chief updates each run**:
  `Usage: 5h X% / weekly Y% (as of <time SGT>), stopped yes/no`.
- Q4: handoff note lives in the claude.ai project. Do not look for it or archive anything.
  STATUS.md is created from Gian's facts (main has 0 to 6; next Phase 7; waiting on Q7, Q9, Q15
  with label `needs-work-test`; leftovers P26, P27, P28).
- Q5 yes (`dontAsk`, allow and deny lists). Deny list must include: push or merge to `main`,
  force push, editing `.env`, deleting files outside `logs/` and `ops/state/`.
  Honest limit: permission rules cannot filter `git push` by branch, so GitHub branch protection
  (O2) is the real wall.

## Gian's decisions, 6 Nov 2026 (second batch)

- **No bot account, no workshop repo.** Agents use Gian's own GitHub login. The safety hook and
  deny list stay as they are. (The fine-grained token step in the guide is removed; the guide now
  says to tick "Do not allow bypassing" so GitHub refuses even Gian's login.)
- **X20 GitHub Action** `.github/workflows/ci.yml`: pytest, ruff, smoke check; runs on `auto/**`,
  `phase-*` and on PRs into `auto/phases-7-10` and `main`; Python 3.14; `DA_LLM_PROVIDER=fake`; no
  secrets; read-only permissions. Closes the "no CI" gap for the merge helper.
- **X21 Usage endpoint:** `GET https://api.anthropic.com/api/oauth/usage`, header
  `anthropic-beta: oauth-2025-04-20`, token read only from `%USERPROFILE%\.claude\.credentials.json`,
  two reply shapes, on 401 run `claude -p "/usage"` once and retry, else guard blind. Replaces
  the empty-endpoint setup of Question 1. Assumptions to prove at A-P1: the second reply shape
  (`utilization`, read as percent), and the token's place (`claudeAiOauth.accessToken`).
- **X22** The child `claude -p "/usage"` runs without `DA_WORKER` and with `DA_USAGE_REFRESHING=1`,
  so its own hooks do nothing and the refresh can never loop back into the guard.
- **X23 Docs:** "Before the first unattended run" (ZIP backup of main, no pulling while agents run,
  how to revert a bad merge).

## Gian's decisions, 6 Nov 2026 (third batch)

- **X24 Raw reply saved:** every usage read writes the raw reply to `ops/state/usage_raw.json`
  (local, Git ignores `ops/state/`), before parsing, so A-P1 can check the real layout. `utilization`
  is a percent from 0 to 100 (confirmed). The "limits" list layout is unconfirmed and NOT supported
  (guard blind). A value that is missing, not a plain number (text, true/false), or outside 0 to 100
  is guard blind (I also reject text numbers like "12": my choice, fail closed).
- **X25 No branch protection** (private repo, free plan). The "Do not allow bypassing" step and the
  "required status check" step are removed from the guide. Safety net: hook, deny list, ZIP backup
  of `main`, merge helper. **AC-5's "refused by GitHub" part cannot be met on this plan**; the hook,
  deny list and merge helper refuse it instead.
- **X26 Remote changes denied:** `git remote add / set-url / remove / rm` are in the deny list and
  blocked by the safety hook (also behind `git -C` and `git -c`). I also block `git config` keys
  starting with `remote.` or `url.` (e.g. `insteadOf`), which would change a remote the same way.

## A-P1 results and fixes, 6 Nov 2026 (Windows laptop)

A-P1: step 1 PASS (GO, 5h 20%, weekly 19%, reply uses `five_hour`/`seven_day` with `utilization`),
step 2 PASS, step 3 PASS (Git Bash found). Step 4 FAIL (launch printed "ran", no `logs/quiet`,
349 output tokens, so pytest never ran: cause not yet proven, see X27). Step 5: ledger line written,
`input_tokens=4` is uncached only. Hook-string test failed on Windows (bash not on PATH): fixed in `bf6823a`.

- **X27 See why a worker stopped.** Every worker's whole reply (result text, `permission_denials`,
  usage, stderr, crash) is saved to `logs/workers/<time>-<agent>.json` (local, gitignored); STATUS.md's
  Log gets one line: first line of the result, number of denied tool calls, file name. The ledger
  outcome also shows "(N tool calls denied)". `launch` prints where to look. The cause of step 4 is a
  hypothesis (PowerShell tool or a command form not in the allow list under `dontAsk`) until the
  first saved reply is read. The field name `permission_denials` is from memory of the CLI output and
  is NOT verified here (no logged-in worker in the cloud); the whole reply is saved either way.
- **X28 Worker environment.** Windows only: `CLAUDE_CODE_USE_POWERSHELL_TOOL=0`, and
  `CLAUDE_CODE_GIT_BASH_PATH=C:\Program Files\Git\bin\bash.exe` when that file exists and Gian has not
  set his own. All platforms: the venv folder goes first on PATH so plain `pytest`/`ruff` resolve (my
  addition). `PowerShell` is in the deny list.
- **X29 Allow list.** Added `.venv/Scripts/python`, `python -m pytest`, `python -m ruff`,
  `python ops/quiet.py`. `builder.md` tells the builder to use plain `pytest` / `ruff check .` (the hook
  routes them) or `"$DA_PYTHON" ops/quiet.py pytest`, never the interpreter path, never PowerShell.
- **X30 Ledger.** New columns `cache_read_input_tokens`, `cache_creation_input_tokens`. A ledger with
  the old header is renamed `usage-ledger.old-<time>.csv`, so rows never misalign.

