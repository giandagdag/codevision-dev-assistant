# Phase 4: Approach, build plan

Spec: `specs/phase-4-approach.md` (the only spec read). Branch: `claude/hopeful-einstein-5ebqp7`
(the session's designated branch; CLAUDE.md would call it `phase-4`).
Pattern copied from Discover: read with no lock, AI call, ONE write transaction, own revision.

## Decisions I made where the spec is silent (all small, none change a Done-when row)

| # | Choice | Why |
|---|---|---|
| P1 | Design-choice answer and every Generator call (settle, change) is ONE read, ONE AI call, ONE write. If the AI call fails nothing is saved and a plain message shows (G3, "step stays where it was") | G2 says one write transaction; the only exception is Accept approach, which saves twice (accept, then the Tester) because spec step `tests_pending` is a saved step |
| P2 | First-call failure writes a chat line and an `approach_failed` audit event, no state row, no status change. The button reads "Try again" while the latest approach audit event is `approach_failed` | G3 needs a label that survives a reload |
| P3 | Test case numbers (T-n) come from the highest number used in any saved plan version, plus 1. Developer cases keep their number across a new Tester plan (G4); new Tester cases continue after the highest | "keeps a case's number for the rest of the request" |
| P4 | A typed case the Tester says fits no criterion: the chat shows the exact spec sentence "This does not match any acceptance criterion. If it is a new requirement, the requirement has to change first (a later phase).", step goes back to `tests`, nothing saved | Avoids a dead end in `case_text`, which has no button |
| P5 | `Add a test case` is refused (error line) when 5 developer cases already exist (message: "You already added 5 test cases of your own. That is the limit."); refused again on submit | 4-23 |
| P6 | A change reply may contain design choices (then step `choices`); a settle reply may not (rule 10) | Spec step table + check 10 |
| P7 | The state stores `accepted_*` versions, `change_count`, `open_item`, `limit_reason`, `draft_case`, `change_from_tests` | section 10 |
| P8 | Library names are compared whole (no splitting on a dot) | Spec says top-level names |
| P9 | Fake script paths are under `src/...` (policy allowed folders). The `modify` path will not be a Discover hit path, so the fake demo shows the "Not found in Discover" warning on purpose | Spec 4: warning path is exercised |
| P10 | `is_vague_then` becomes public in `da_understand_checks.py` (rename of the private helper, same body; its one call site in the same file is updated in the same step) so check 4 of the test plan reuses it | Spec 5 rule 4 says "the same rule" |
| P11 | `Policy.new_file_name_pattern` gets a validator that it compiles as a regular expression | A bad pattern would crash the checks |

## Steps (each ends with its tests, ruff clean)

0. **Done and pushed:** `CLAUDE.md` "Current phase" now says Phase 4 (commit on the session branch).

1. **Statuses and moves** (`da_models.py`): APPROACH_PROPOSED, READY_TO_BUILD, the 3 new moves. Tests: moves table, `test_da_status_moves.py`. Done: DISCOVERY_CONFIRMED can move to APPROACH_PROPOSED; READY_TO_BUILD has no moves out.
2. **Policy fields** (`da_rulebook_models.py`, `da_rulebook_seed.json`): 7 new fields with starter defaults, `FlagReviewZone`. Tests (4-27): old JSON without the fields loads with defaults; seed has them; bad regex refused.
3. **Tester role and settings** (`da_llm_client.py`, `da_config.py`, `.env.example`): role `tester`; empty tester model means the generator's model (Claude and onprem). Tests: role accepted, fallback, env example lists both names.
4. **Models** (`da_approach_models.py`): ApproachReply and parts, ApproachVersion, ApproachDecision, TestPlanReply, TestCase, TestPlanVersion, ApproachState, ApproachView. Tests: limits refused not cut, extra fields forbidden.
5. **Storage** (`db_tbl_da_approach.py`): 3 tables, append-only triggers, revision check (base 0 inserts). Tests: round trip, append-only, stale save refused, audit helpers (`approach_failed`, last `discovery_confirmed` round).
6. **Checks** (`da_approach_checks.py`): reply checks 1-11 (4-3 to 4-8, 4-14), warnings and zones (4-9, 4-10, 4-11), Tester checks (4-19, 4-20), typed-text limits, the gate (4-25, 4-26). Pure functions, table-driven tests, one per Done-when row.
7. **Agents** (`da_approach_agent.py`, `da_tester_agent.py`, 3 prompt files, 2 fake scripts): build prompt in one pass, parse (fence, think block), 2 attempts with retry note, rejected-reply log with `step="approach"` or `"tester"`, scripted clients for `fake`. Tests: 4-18 (Tester prompt has criteria and decisions, not the file plan, reuse decisions or chat), retry once, failure after 2.
8. **Flow** (`da_approach_flow.py`): `start_approach`, `choose_design_option`, `submit_text`, `accept_approach`, `request_change`, `request_help`, `write_test_plan`, `request_case`, `keep_case`, `discard_case`, `request_plan_change`, `accept_test_plan`, `get_approach_view`. One test file per group: start (4-1, 4-2), choices (4-12, 4-13, 4-15), change and limit (4-16, 4-17), tests (4-21 to 4-24), gate (4-25 status and audit, 4-26, 4-28), escalate (G6). Rows 4-9 to 4-11 are also tested through the flow and storage (a saved version holds the warnings and zones). Accept approach: first save keeps step `tests_pending`; if the Tester call fails only a chat line is written and the button **Write the test plan** is offered (own test).
9. **Pretend work server** (`da_fake_onprem_server.py`): answers the 5 new task markers; `bad-json` mode is bad on every try for them, the same as Discover's pattern today (Understand's retry-passes pattern would make failure path 4-2 and the Tester failure unreachable). The onprem replies come from the same scripted Excel example as the fake provider, so they cite the real Discover hit numbers (the script names hits by symbol and the client maps them to the numbers in the prompt) and cover every criterion ID in the prompt. Tests: hit numbers and criterion IDs line up; a full onprem run (Proceed to Approach, answer, accept, accept plan) reaches READY_TO_BUILD; bad-json leaves DISCOVERY_CONFIRMED with "Try again".
10. **Screen** (`da_web_components.py`, `da_developer_assistant_page.py`, callbacks): new stepper labels, tabs, chip text, active Proceed to Approach, Approach workspace and tab, composer per step, pills for the 2 new statuses. Tests 4-30, 4-31, the Build button disabled with the Phase 5 text at READY_TO_BUILD (second half of 4-25), and callback routing (state key `approach`).
11. **Smoke check** (`da_smoke_check.py`): items 19 to 21: fake run to READY_TO_BUILD, onprem run against the pretend server, Tester prompt proof read from `server.seen`. Test update in `test_da_smoke_check.py`. Covers 4-29.
12. **Docs**: README section; this plan's "How to check" notes into the final report.
13. **Finish**: full `pytest`, `ruff`, smoke check, browser check on the fake provider (4-29 browser line) with the Playwright already installed in this cloud container (a one-off tool, not added to `requirements.txt`, no new library), `code-reviewer` (max 3 rounds), commit, push to the session branch.

## Files touched (spec section 16 plus tests)

New: `da_approach_models.py`, `da_approach_checks.py`, `da_approach_agent.py`, `da_tester_agent.py`, `da_approach_flow.py`, `db_tbl_da_approach.py`, `da_approach_prompt.md`, `da_test_plan_prompt.md`, `da_test_case_prompt.md`, `da_approach_fake_script.json`, `da_tester_fake_script.json`, matching tests.
Edited: the files named in the steps above, and the existing tests that assert old names (stepper labels, tab names, chip text, the disabled Readiness Gate button, "generator, reviewer", Discover's confirmed message).

## Out of scope (spec section 12), not touched

Workspace folder, any file write, code writing, Tester review, requirement revision, Admin screens, inbox.

## Risks

- `da_developer_assistant_page.py` is 770 lines; the Approach panel goes into a new section, not a rewrite.
- The pretend-server prompt markers must not collide with Discover's marker; each is a distinct full line.
