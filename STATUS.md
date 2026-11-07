# STATUS (the chief's whole memory, max 60 lines)

Usage: unknown (guard not run on this branch yet), stopped yes
Stopped: no

## Where we are
- main has Phases 0 to 6 and Phase A merged (PR #19, 7 Nov). Integration branch: auto/phases-7-10.
- Next: Phase 7 spec stage ONLY (pilot A-P3). Launch the spec-writer for Phase 7 with the facts in
  specs/phase-7-facts.md. Apply the decision rule to every D-x. Push the spec to auto/phase-7.
  Then set this line to "Next: none (A-P3: waiting for Gian's review)" and stop. Do NOT plan or build.

## Phase 7 facts
- specs/phase-7-facts.md (Q9 bake-off and Q7 context limit are work facts).

## Waiting on Gian at work (label needs-work-test)
- Q7: context limit per model.
- Q9: Tester bake-off, Llama vs Qwen.
- Q15: folder and command that start CodeVision on a developer laptop.

## Leftovers carried forward
- P26 (different-folder wording), P27, P28 (cosmetic).

## Log
- 7 Nov: Claude (project chat) created auto/phases-7-10 from main 0bbcb51 and set up A-P3.
