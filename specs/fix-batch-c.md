# Fix batch C: clean up before `main` (sandbox on Windows, parked tests, board without old branches)

Version 1.0 APPROVED, 17 Nov 2026 (10:29 SGT). Gian: "Go ahead with C." Every D-x below is option 1.

Branch `phase-c-fixes`, cut from `auto/phases-7-10` at 270bccb (Phase 11 fix 1 and fix 2 merged).
PR into `auto/phases-7-10`. Build it the normal way: plan, plan review, small steps with tests, code
review (max 3 rounds), full pytest, ruff, smoke check. **No product screen changes.** When everything
is green the chief may merge the PR (Gian approved the batch), then opens a `gian-later` issue
"Fix batch C merged: ready for main" with the evidence.

## 0. Why

Phase 11 is merged and signed off. Phase 10b (Review my code) stays on hold (Gian's director). Before
`auto/phases-7-10` can go into `main`, the test suite must be fully green on Gian's Windows laptop,
with no skip markers hiding real failures. Gian also wants the leftover branches gone, but the Team
status board still reads `auto/phase-7` to `auto/phase-11c` to know those phases are merged.

## 1. Decisions

| # | Question | Decision |
|---|---|---|
| D-A | P27: a child process survives on Windows after its test run ended | **1: a real fix with a Windows Job Object** through `ctypes` (standard library, no new package): the sandbox puts each test process in a job with "kill on job close", and ending the run closes the job, so every descendant ends. Linux keeps `killpg`. If it still fails after 2 attempts (SO-2): 2, skip that one test on Windows only, with the reason "the sandbox runs on the Linux OCP server only (decided 3 Nov)", and say so in the PR |
| D-B | #57 (test 8.42 clicks Apply too fast) | **1: test only:** wait for the "Picked:" line before clicking Apply my choices |
| D-C | #56 (test 9.50 sets the wrong function in scope) | **1: test only:** the 9.50 setup puts `ExpiryReport.build_line` in scope, the function the scripted edit changes |
| D-D | How does the board know a phase is merged without its branch? | **1: a small record** `ops/state/merged_phases.json` (a list of phase names). The chief's merge helper adds the phase when it merges `auto/phase-N`. The board counts a phase as merged when the branch check says so **or** the record lists it. Seed it with `7, 8, 9, 10, 11a, 11b, 11c`. Git ignores `ops/state/`, so the seed is also written by `chief_tick.py` at start when the file is missing |
| D-E | #74 (B1 step 12, needs a browser at work) | **1: not a home task.** Relabel it `needs-work-test`, no code change |

## 2. What to build

| # | Piece | Proof |
|---|---|---|
| C1 | P27 Job Object in the sandbox runner (Windows branch only). Keep every Linux path unchanged | `tests/test_da_sandbox.py::test_a_child_left_running_by_a_test_that_ended_normally_is_still_ended` passes on Windows **without** a skip marker; the full sandbox tests pass on Windows and in the cloud (Linux) |
| C2 | Remove the three skip markers from commit e2aaab4 (8.42, 9.50, the sandbox child test) | All three run and pass |
| C3 | #57: 8.42 waits for "Picked:" before Apply | 8.42 passes 5 times in a row alone and once in the full run |
| C4 | #56: 9.50 scope setup | 9.50 passes alone and in the full run; the smoke check still passes |
| C5 | D-D merged-phases record in `ops/status_board.py` and the chief's merge helper | New ops tests: with `auto/phase-7` missing and the record listing 7, the board still says 100% (all merged); a merge through the helper adds its phase; a missing record is seeded |
| C6 | Close #56, #57, #80, #81 with the commit that fixed each; relabel #74 | Issue comments name the commits |
| C7 | `specs/parked-items.md`: P27 closed (or the skip reason, if D-A option 2 was used) | The row says what was done |

## 3. Edge rules

- Tests only for C3 and C4: no change to the Refine or Enhance product code.
- The sandbox change must not change what a developer sees. It changes only how processes end.
- No new library. `ctypes` is part of Python.
- Never touch `main`. Never delete a branch (Gian deletes old branches himself on GitHub).

## 4. After the merge (Gian, on GitHub, not the team)

1. Settings, General, "Automatically delete head branches": on.
2. Delete `auto/phase-7`, `-8`, `-9`, `-10`, `-11a`, `-11b`, `-11c` (the board no longer needs them).
3. After his work test passes: merge `auto/phases-7-10` into `main` himself.
