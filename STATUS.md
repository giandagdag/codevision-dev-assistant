# STATUS (the chief's whole memory, max 60 lines)

Usage: 5h 4% / weekly 39% (as of 08 Nov 12:51 SGT), stopped no
Stopped: no

## Where we are
- main has Phases 0 to 6 and Phase A merged (PR #19, 7 Nov). Integration branch: auto/phases-7-10.
- Phase 7 spec approved v1.0, built, PR #23 merged into auto/phases-7-10 (7 Nov).
  Known: 1 Windows-only failure in Phase 6 test_da_sandbox child-process test (CI Linux green). Not done: Playwright 7-35, smoke script run by hand.
- Issues opened (needs-work-test): #20 WF-1 (Q9 Tester model), #21 WF-2 (Q7 context limit).
- Phase A fix 1 (PR #22) and fix 2 (PR #24) merged into auto/phases-7-10.
- Phase 8 spec APPROVED v1.0 by Gian (7 Nov 19:30, all D-x as chosen, D-A option 1), on auto/phase-8 (2a9d8de).
  Issues: #25 WF-1, #26 WF-2, #27 WF-3, #29 WF-5 (needs-work-test), #28 WF-4 (needs-gian, server version storage: keep every version for now, NOT a blocker).
- UNBLOCKED 8 Nov 12:50: Claude (project chat) merged auto/phases-7-10 into auto/phase-8 in the cloud and pushed (a452cea, has ops/status_board.py).
- Running: builder (Phase 8) since 08 Nov (tick after 12:51 SGT). Spec marked APPROVED v1.0 (uncommitted edit on auto/phase-8, builder to carry it). Local auto/phase-8 reset to a452cea.
- Next after builder ends: check Log result, open PR into auto/phases-7-10, merge via helper when green.
- (done) `git fetch origin` then `git checkout -B auto/phase-8 origin/auto/phase-8` (allowed; no merge needed). Mark the Phase 8 spec APPROVED v1.0,
  then launch the builder on auto/phase-8: plan, plan-reviewer, build, code review, tests, push, PR into auto/phases-7-10.

## Phase 7 facts
- specs/phase-7-facts.md (Q9 bake-off and Q7 context limit are work facts).

## Waiting on Gian at work (label needs-work-test)
- Q7: context limit per model.
- Q9: Tester bake-off, Llama vs Qwen.
- Q15: folder and command that start CodeVision on a developer laptop.

## Leftovers carried forward
- P26 (different-folder wording), P27, P28 (cosmetic).
- P31 (Gian, 7 Nov 18:13): Windows-only failure in tests/test_da_sandbox.py (child process not ended). Accepted on auto/phases-7-10; MUST be fixed before the final merge into main. Ask at work: CodeVision server OS.

## Log (old rows trimmed 8 Nov)
- 07 Nov: Phase 7 built and merged (PR #23). Phase 8 spec written, committed, approved by Gian (19:30).
- 07 Nov 14:07 SGT: Gian decided: a Tester re-run that finds a Must fix ends NOT_PASSING, no extra round.
- 07 Nov 18:20 SGT: Gian: P31 accepted. Status board (Phase A fix 2) built in parallel in the cloud.
- 07 Nov 19:55 to 08 Nov 00:51: chief ticks repeated; merge denied 3x, nothing changed each time. Waiting for Gian.
- 08 Nov SGT: chief: fetched, origin/auto/phase-8 still lacks origin/auto/phases-7-10. No retry. Trimmed Log to fit 60 lines.
## Log
- 08 Nov 01:21 SGT: chief: I didn't do the next step. `origin/auto/phase-8` still doesn't contain `origin/auto/phases-7-10`: I fetched origin and checked, and it isn't an ancestor. -> logs/workers/20261107-172101-chief.json
- 08 Nov 12:51 SGT: chief: I started the builder on Phase 8 and then stopped, as the launch step requires. It is running in the background. [1 tool call denied] -> logs/workers/20261108-045101-chief.json
