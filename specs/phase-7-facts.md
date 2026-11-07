# Phase 7 facts (from Gian's handoff note, 7 Nov 2026)

Facts for the Phase 7 spec writer. Phase 7 = Independent Tester (Layer C, report, labels).
Source of truth for scope: `specs/redesign-2026-10-31.md` sections 5.4, 5.5 and 6. Format to copy:
`specs/phase-6-build-test-loop.md`. Facts marked **work fact** are Gian's to decide: give options,
no recommendation, and the chief opens a `needs-gian` or `needs-work-test` issue.

## What is already built (main, Phases 0 to 6)
- Phase 4 created the `tester` role. Its model settings (`DA_CLAUDE_TESTER_MODEL`,
  `DA_ONPREM_TESTER_MODEL`) are optional; empty = use the generator's model.
- Phase 4: the Tester writes the test plan from the criteria without seeing code; the developer
  accepts it. Status stays APPROACH_PROPOSED until "Accept test plan".
- Phase 6: Layers A and B, one shared budget of 3 rounds. Layer C shows "Coming in Phase 7". At pass,
  the label is "Ready with warnings" with the fixed warning "The independent Tester review
  (Layer C) is not built yet." Phase 7 must remove that warning. Status TESTER_REVIEW is unused
  until Phase 7 (Phase 6 D-L).
- Q11 (decided 3 Nov): tests run ONLY in the server sandbox. Test files never go to the developer's
  folder or Bitbucket. The report and the tests live in the app (Tests tab).

## Models at work (work test 30 Oct)
- `reasoning-vlm` = Qwen3.6-35B-A3B: replies 10 to 20 s, did well in Understand.
- `default` = Llama-4-Maverick-17B-128E: replies 2 to 5 s, repetitive, overlapping questions,
  stopped at the 5-decision limit (W1, W2).
- Roles: Generator = Qwen. Tester = Llama **tentatively**. The model per role is an Admin setting.

## Open items Phase 7 must respect
- **Q9, work fact:** the Tester bake-off (Llama vs Qwen, same 3 sample requests, separate call) has
  NOT been run. It needs Gian at work. Build so the Tester model is a setting; never hard-code one.
- **Q7, work fact:** the server context limit per model is unknown. The Tester gets record,
  approach, test plan, code and test results, so the spec must say what happens when the input is
  too big (CodeVision returns HTTP 400 for too much context).
- **W6:** the Tester sees the Generator's design question text, which could name a file. Watch it.
- The Tester never sees the Generator's chat (redesign 5.5).
- Work laptop: PowerShell and DevTools are blocked. Any developer-facing instructions use Command
  Prompt.
- Leftovers, not Phase 7 scope: P26, P27, P28.

## House style for the spec
Plain language, AS400 comparisons (never mainframe), short sections, ranked D-x options with one
recommendation each, Given/When/Then criteria, no em dashes.
