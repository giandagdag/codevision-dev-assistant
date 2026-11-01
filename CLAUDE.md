# CodeVision Developer Assistant: house rules

## What this project is
The Developer Assistant is a new capability inside CodeVision, UOB's AI tool for modernizing
legacy hostcentric applications. It helps developers understand a change, reuse existing code,
get starter code, and get early review feedback. CodeVision is a Python Plotly Dash app
(Dash Mantine Components) that uses Qwen and Llama at work.

This folder is a clean-room build at home. It is later copied into CodeVision at work.

## Who you are working with
Gian is an experienced bank programmer (hostcentric background) but new to Python and Claude Code.
- Explain in plain language. No jargon without a one-line meaning.
- Comparisons to AS400 (IBM i) ideas such as RPG, CL, DDS, data areas, journals and 5250 screens
  are welcome. Do not use mainframe comparisons.
- After each step, say: what you did, why, and how Gian can check it.

## How we work: one phase at a time
1. Read ONLY the current phase spec in `specs/`. Do not build anything outside its scope.
2. Plan first. First plan step: update "Current phase" below.
3. Ask the `plan-reviewer` subagent to review the plan. 0 Must fix = approved, no need to wait
   for Gian. Must fix found: fix once and review again; still failing = stop and ask Gian.
4. If the spec is unclear or seems wrong, ask. Never assume.
5. Build in small steps on a `phase-N` branch (for example `phase-2b`), each step with tests.
6. When done, run the tests, ruff and the smoke check, then ask the `code-reviewer` subagent.
7. Fix findings. Maximum 3 review rounds, then stop and report to Gian.
8. Commit and push to the phase branch. Gian signs off by merging into `main` himself.

## Stop rules (never loop)
Stop, push the work so far to the phase branch, and tell Gian what you need when:
- a test still fails after 2 fix attempts,
- the spec is unclear, wrong, or needs a decision only Gian can make,
- a cap is reached (plan review 1 fix round, code review 3 rounds), or
- you need a photo of work code. Ask for all photos in one list, never one at a time.

## Working habits
- Surgical changes: touch only what the step needs. Mention unrelated problems, don't fix them.
- Checkable goals: every step says how to prove it is done, usually a test.
- Find the cause first: when something fails, explain why before changing code.
- Evidence before "done": paste the real test, ruff and smoke check results. Never claim a pass
  you did not see.

## Current phase
Phase 5: Workspace. Spec: `specs/phase-5-workspace.md` (Phase 4 is merged into `main`). Plan: `specs/phase-5-plan.md`

Phases 4 onwards were redesigned on 31 Oct 2026 (LLM writes 100% of the code, built-in testing,
laptop workspace). Source of truth: `specs/redesign-2026-10-31.md`.

| # | Phase | # | Phase |
|---|---|---|---|
| 0 | Foundations | 6 | Build + test loop |
| 1 | Rulebook core | 7 | Independent Tester |
| 2 | Understand | 8 | Refine (3 lanes, edit protection) |
| 3 | Discover | 9 | Enhance existing program |
| 4 | Approach | 10 | Review my code, Handoff, Escalations inbox |
| 5 | Workspace | 11 | Admin console and health metrics |

## Technical rules
- Python 3.14 only, inside `.venv`. Never use Python 3.15 features.
- On Gian's laptop (Windows PowerShell):
  - run tests: `.venv\Scripts\python -m pytest`
  - check style: `.venv\Scripts\python -m ruff check .`
  - smoke check: `.venv\Scripts\python src\da_smoke_check.py`
- In a cloud session (Linux). `scripts/da_cloud_setup.sh` builds `.venv` at start-up:
  - run tests: `.venv/bin/python -m pytest`
  - check style: `.venv/bin/python -m ruff check .`
  - smoke check: `.venv/bin/python src/da_smoke_check.py`
- Follow CodeVision's folder layout under `src/` (configs, agents, pydantic_classes,
  db_table_functions, callbacks, layouts, styles, web). New files start with `da_`.
- Pin library versions in `requirements.txt`. Ask before adding any new library.
- Keep code simple and readable. Short functions, clear names, comments that explain why.

## Safety rules (never break these)
- No real UOB code, data, names, or internal addresses. Use made-up examples only.
- No secrets in code, logs, or tests. Secrets only live in `.env`, which Git ignores.
- Tests never call a real AI or the internet. Use the `fake` provider or mocks.
- Push only to `phase-N` or setup branches on `origin`. Never push to `main`, never force-push.
- Never commit `.env`, database files (`*.db`), keys or tokens.
