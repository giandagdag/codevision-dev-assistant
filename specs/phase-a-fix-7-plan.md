# Phase A fix 7 plan: standing orders

Spec: `specs/phase-a-fix-7.md` v1.0 (approved, D-A to D-E = option 1). Branch `phase-a-fix-7` (from
`auto/phases-7-10`). PR into `auto/phases-7-10`; Gian merges (same window as fix 6). Cloud session.
Nothing in `src/`. `phase-8-fix-1` untouched. Tests use fakes and `tmp_path` only. Zero tokens added
to any tick. No CLAUDE.md "Current phase" edit (machinery fix; avoids a conflict, same as fix 6).

## Design in plain words (AS400: a reply list with standing answers, so known messages never wait in MSGW)

- **S1 (`.claude/agents/chief.md`)**: the decision table gets rows SO-1 to SO-6 (spec section 3 wording,
  shortened to one line each) plus "When unsure, SO-6 wins: ask." Each use: one Log line `SO-n: ...`,
  and a "Standing orders used" list in the PR body. The old row "A test still failing after 2 fix
  attempts ... Stop that phase" is replaced by SO-2 (it contradicts it).
- **S1/S4 (`.claude/agents/builder.md`)**, who writes what (review Must fix + Should fix):
  - "SO-2 overrides the CLAUDE.md 2-fix stop rule for ONE step." (CLAUDE.md stays untouched: its
    6,000-byte limit, and the laptop branch edits it.)
  - SO-1: merge `auto/phases-7-10` into its own branch; the conflict rule of spec section 3.
  - SO-2: write `PARKED step K: <reason, what was tried>` in the plan file, commit, continue. Write
    `SO-2: parked step K` in `ops/state/worker_note.md`. Set Next with
    `chief_tick.py next "builder continue Phase N from step K+1 (step K parked)"` (S4: names the parked
    step). A third parked step, or a parked step whose bug is Critical or High in the spec (no severity
    column = High, spec O1): finish the other steps, then stop before code review and say so in the note.
  - A parked Medium-or-lower step goes into the PR body as a known gap (spec SO-2).
  - SO-3 continue, never split; SO-4 finish the scope, Should fix included.
- **S1 (`.claude/agents/chief.md`)**, the chief's side: on `SO-2` in the worker note it opens a
  `gian-later` issue "SO-2: Phase N step K parked" and writes the Log line; on the builder's "stopped
  before code review" it opens `needs-gian`. SO-5 issues are titled "SO-5: ...". The chief fills the PR's
  "Standing orders used" list from the Log `SO-n` lines. The old row "A test still failing after 2 fix
  attempts, a review cap reached, the spec unclear: stop" keeps "review cap reached" and "spec unclear";
  only the test-failure part moves to SO-2.
- **S2 (`ops/chief_tick.py`)**: `LABELS` gets `"gian-later"` (so `issue --label gian-later` works; others
  still refused by argparse `choices` and `open_issue`).
- **S2 (`ops/status_board.py`)**: `Inputs.later: list[Issue]` (last field, default empty); `gather` reads
  `_issues(gh, "gian-later")`; `build_body` adds `📌 For you later: N` right under `Updated` when N > 0,
  and a section `### For you later (does not block)` after "Waiting for you". `top_line` is unchanged,
  so `gian-later` never makes WAITING FOR YOU (AS-5).
- **S3 (`ops/answers.py`)**: new `later_questions(gh)` (open `gian-later` issues); `find_new_answer` checks
  `open_questions(gh) + later_questions(gh)`. `open_questions` itself is unchanged, so `waiting_for_gian`
  and the stall check still see only `needs-gian` (AS-4, AS-7).
- **S5 (`docs/automation.md`)**: a short "Standing orders" section and the two labels.

## Steps (each with its check)

| # | Step | Proof |
|---|---|---|
| 1 | S2 label in `chief_tick.py` + test: `open_issue(..., "gian-later", ...)` opens with that label; `"other"` still raises | AS-3 |
| 2 | S3 `answers.py` + tests (also: a stall-title issue with `gian-later` stays out; an answer already `remember`ed is not woken again): owner comment on a `gian-later` issue is found (AS-6, through `tick` with a fake launcher, same as the fix 4 G2 test); `waiting_for_gian` is False with only a `gian-later` issue and `Next: wait for Gian` (AS-4) | AS-4, AS-6 |
| 3 | S2 board + tests: one `gian-later` issue gives `📌 For you later: 1`, the section lists it, top line not WAITING FOR YOU (AS-5); `Inputs.later` defaults to empty; a failing `gian-later` read is handled like the other `_issues` calls; existing board tests pass | AS-5 |
| 4 | AS-7 test: `Next: none`, no `needs-gian`, one `gian-later`: the stall check still says NOT_FINISHED | AS-7 |
| 5 | S1/S4 agent text + tests reading the files: rows SO-1..SO-6, "SO-6 wins", "review cap" and "spec unclear" still stop, SO-5 title rule; builder: SO-2 overrides the 2-fix rule, PARKED line, worker note, Next names the parked step, third parked / Critical or High / no severity = High stops before code review | AS-1, AS-2 |
| 6 | S5 docs | read-through |
| 7 | pytest (ops, then full), ruff, smoke; `code-reviewer` (max 3 rounds); push; PR | real outputs in the PR; AS-8 by `tests/ops/test_ops_zz_real_logs.py` (ledger, workers, and fix 6's STATUS.md guard once merged); all new tests use `tmp_path` and fake `gh` |

## Not doing (and why)
- No troubleshooter (spec out of scope). No change to SO-6 cases, the guard, stop lines or merge rights.
- No new `builder` permission: merging `auto/phases-7-10` into its own branch and pushing that branch is
  already allowed (safety rules: push only to `phase-N`/`auto/phase-N`).

## Risks
- R1: an agent may stretch SO-5. Mitigation: SO-5 needs all of "in-app, no work fact, no library, no
  outside message", and every use is a `gian-later` issue Gian can overrule.
- R2: fix 6 and fix 7 both touch `docs/automation.md` and `chief.md`/`builder.md`: the second PR to merge
  may conflict. Merge order fixed: **fix 6 first, then fix 7**. Before Gian merges fix 7, I check it
  against fix 6 and merge `auto/phases-7-10` in if needed (SO-1 by hand).
