# Phase 3 plan review, round 1 (30 Oct 2026)

Result: CHANGES NEEDED (1 Must fix). Reviewer: `plan-reviewer` (Sonnet), reviewing
`specs/phase-3-plan.md` (commit 022ed24) against spec v1.1.

This is the ONE allowed fix round (CLAUDE.md). Fix the plan, then ask `plan-reviewer` again.
0 Must fix = approved, build. Still failing = stop and ask Gian.

The spec was corrected by its author in the same commit as this file (3.3 merge rule, the matching
"Done when" line, and 3.5 escalation wording). Re-read the spec.

## Must fix
1. CLAUDE.md "Current phase" still says Phase 2C P13 (the planning commit did not change it).
   First plan step: set it to "Phase 3: Discover. Spec: `specs/phase-3-discover.md`".

## Required change (agreed with the spec author)
2. Planning decision 4 is wrong. Merge hits by (`source_path`, `symbol`), not by path alone
   (spec 3.3 is now corrected). Update step 7 and its test (two functions in one file stay two
   hits), the Done-when map row, and drop the README "known limit" note from step 15.

## Should fix
3. Revision number (step 11, ambiguity 2): decide now, not during the build. The revision lives on
   the `da_understand_sessions` row and `save_session` rewrites the whole session JSON, record
   included. Choose either a revision-only update that leaves the record JSON alone, or a separate
   revision for discovery. Name the exact 2A edit if any. Add a test that the stored record is
   byte-identical after every Discover action.
4. Split step 11 into: (a) outcome rule and the "not proof" limitation; (b) `start_discovery` and
   the transaction; (c) hint, round cap and stale check; (d) confirm, escalate and view. Each with
   its own named tests.
5. Atomicity test: force a failure after the status write (for example a duplicate round) and prove
   status, audit and results are all unchanged. State that `start_discovery` from SEARCHING does
   only SEARCHING to outcome.
6. Decision 7: keep the invented-id check strict and fix the script, but PROVE it: a test that the
   demo record through the full flow with the fake provider gives summary source `ai` and
   SIMILAR_IMPLEMENTATION_FOUND, and the same for a hint round. Delete the "fallback by design"
   sentence.
7. Escalation open item (ambiguity 10): settled by the spec author, spec 3.5 now says it lives in
   the audit event, chat and view, not the record. Test that the view shows it and the record is
   unchanged.

## FYI (do if cheap)
- Decision 8: say the same fixed text applies to standard and doc fallback findings and give their
  titles; test fallback findings pass the step 8 checks.
- Step 9: name the marker line "Task: sort search hits into findings" in the prompt; test it is there.
- Step 13 is large: consider splitting components/layout from callbacks.
- Step 4: `.env`-like and secret-looking pieces hold made-up filler only, nothing key-like.
- Decisions 6 and 13 are sound; test `SearchHit.version` is filled from `build_id`.
- Step 10: created time in Singapore time via the existing `to_db_time`; test it.
- Ambiguity 1: reword; SEARCHING is only reachable after a crash or a direct status set.

## Also known (from P13 code review, not Phase 3 scope)
- `strip_think_block` strips anywhere in the reply; a JSON value containing `</think>` would be
  damaged. Parked until after Monday: try parsing as-is first, strip only on failure.
