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
- Comparisons to COBOL or mainframe ideas are welcome.
- After each step, say: what you did, why, and how Gian can check it.

## How we work: one phase at a time
1. Read ONLY the current phase spec in `specs/`. Do not build anything outside its scope.
2. Plan first. Wait for Gian to approve the plan before writing code.
3. If the spec is unclear or seems wrong, ask. Never assume.
4. Build in small steps, each with tests.
5. When done, run the tests and ruff, then ask the `code-reviewer` subagent to review.
6. Fix findings. Maximum 3 review rounds, then stop and report to Gian.
7. Commit to Git only when Gian says so.

## Current phase
Phase 1: Rulebook core. Spec: `specs/phase-1-rulebook-core.md`

| # | Phase | # | Phase |
|---|---|---|---|
| 0 | Foundations | 5 | Generate + Check |
| 1 | Rulebook core | 6 | Preliminary Review |
| 2 | Understand | 7 | Handoff |
| 3 | Discover | 8 | Paths 2 and 3, Escalations inbox |
| 4 | Readiness Gate | 9 | Admin console and health metrics |

## Technical rules
- Python 3.14 only, inside `.venv`. Never use Python 3.15 features.
- Windows PowerShell commands, for example:
  - run tests: `.venv\Scripts\python -m pytest`
  - check style: `.venv\Scripts\python -m ruff check .`
- Follow CodeVision's folder layout under `src/` (configs, agents, pydantic_classes,
  db_table_functions, callbacks, layouts, styles, web). New files start with `da_`.
- Pin library versions in `requirements.txt`. Ask before adding any new library.
- Keep code simple and readable. Short functions, clear names, comments that explain why.

## Safety rules (never break these)
- No real UOB code, data, names, or internal addresses. Use made-up examples only.
- No secrets in code, logs, or tests. Secrets only live in `.env`, which Git ignores.
- Tests never call a real AI or the internet. Use the `fake` provider or mocks.
- Never push to any remote repository.
