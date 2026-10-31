# Phase 3 build plan: Discover

Spec: `specs/phase-3-discover.md` (v1.1). Branch `phase-3`. Start: 452 tests pass.
Every step ends with: `pytest`, `ruff check .` green, then a commit on `phase-3`.
Test files are new `tests/test_da_*.py` unless a step says otherwise. Existing 2A/2B/2C files
get only the small edits listed (rule R7).

## Steps

| # | Build | Files | Proof (tests) |
|---|---|---|---|
| 0 | CLAUDE.md "Current phase" set to "Phase 3: Discover. Spec: `specs/phase-3-discover.md`" (first plan step, review 1 Must fix; done in the plan-fix commit) | edit `CLAUDE.md` | line reads as above |
| 1 | Settings: `DA_SEARCH_PROVIDER`, `DA_SEARCH_TOP_K`, `DA_DISCOVERY_MAX_ROUNDS`, with range checks and plain errors | edit `configs/da_config.py`, `.env.example`; tests added to `test_da_config.py`, `test_da_env_example.py` | defaults; bad provider, top_k 0 or 21, rounds 0 or 6 refused |
| 2 | Statuses and moves: six new statuses and the section 2 table, plus the `ALLOWED_MOVES` rows | edit `pydantic_classes/da_models.py`; `test_da_status_moves.py` | every allowed move works, every other move refused, CONFIRMED -> SEARCHING only |
| 3 | Models: `SearchHit`, `SearchFilters`, `Finding`, `DiscoveryResult` (+ `DiscoveryView`) | new `pydantic_classes/da_discovery_models.py`; `test_da_discovery_models.py` | snippet over 500 refused; score 0 to 1; kind and confidence values; caps (8 findings, text lengths) |
| 4 | Pretend index file (about 25 pieces, incl. deprecated, restricted, `.env`-like, whole-file standards; the `.env`-like and secret-looking pieces hold made-up filler only, nothing key-like) and loader with the gap/order check | new `data/da_fake_index.json`; new `agents/da_search_index.py` (loader part); `test_da_search_index.py` | gap or out-of-order `piece_no` refused with plain message |
| 5 | `SearchIndex` protocol, `FakeSearchIndex` (exact, meaning + synonyms, empty-filter fallback), `get_search_index`, `codevision` placeholder, hard safety filter | `agents/da_search_index.py`; same test file | exact and meaning each find the expected piece; filter drops deprecated, restricted, secret-looking; fallback to all permitted pieces; `codevision` gives "not configured" message; count logged, not path; `SearchHit.version` is filled from the index `build_id` when the piece has none |
| 6 | Python splitter and `split_folder` | new `agents/da_code_splitter.py`; `test_da_code_splitter.py` | functions, classes, methods with right symbols and line numbers; `<module>` piece; broken file gives one whole-file piece plus warning; `.venv`, `__pycache__`, secret paths skipped; order stable. Also checks fake index shape against the splitter's piece fields |
| 7 | Query builder and merge (merge key is (`source_path`, `symbol`), spec 3.3) | new `agents/da_discover_queries.py`; `test_da_discover_queries.py` | queries from title, references, objective, expected behaviour, hint; capped at 6; two functions in one file stay two hits; same path and symbol found twice keeps the best score; best 12; `hit_id` 1..12 |
| 8 | Checks for the AI reply | new `agents/da_discover_checks.py`; `test_da_discover_checks.py` | shape and values; caps; invented `hit_id`; missing citation; code in text (reuses Phase 2 `find_code`); hint check reuses `developer_message_problem` |
| 9 | Prompt, fake script, discover agent (one call, 2 attempts, fallback) and rejected-log `step` argument | new `data/da_discover_prompt.md` (contains the marker line "Task: sort search hits into findings"), `data/da_discover_fake_script.json`, `agents/da_discover_agent.py`; edit `agents/da_rejected_reply_log.py` (optional `step="understand"` in header); tests in `test_da_discover_agent.py`, `test_da_rejected_reply_log.py` | good reply gives findings; invented id, no citation, 9 findings, code each cause one retry with a plain note; 2 bad replies and `LLMClientError` give fallback (code/config -> Possible match low; standard/doc -> relevant standard); entries logged with step `discover`; old log tests unchanged; the prompt file contains the marker line; fallback findings (all four fallback cases) pass the step 8 checks |
| 10 | Storage: `da_discovery_results` table (append-only triggers, unique (request, round), `created_at` through the existing `to_db_time`) and the small `da_discovery_state` table holding the discovery revision (see decision 2) with a compare-and-swap bump, like `save_session` | new `db_table_functions/db_tbl_da_discovery.py`; `test_db_tbl_da_discovery.py` | insert and read; UPDATE and DELETE on results refused; duplicate round refused; created time stored in Singapore time; revision bump refused when the base revision is old; first bump from 0 refused if a row already exists |
| 11a | Outcome rule and fallback-proof findings: pure function from findings to SIMILAR_IMPLEMENTATION_FOUND or NO_RELIABLE_MATCH; app adds the "not proof" limitation | new `agents/da_discover_flow.py` (outcome part); `test_da_discover_flow_outcome.py` | existing or similar finding gives SIMILAR; only standard or area findings give NO_RELIABLE_MATCH with the limitation; no findings gives NO_RELIABLE_MATCH with the limitation; limitation not added when a match exists |
| 11b | `start_discovery` and the round transaction (search and AI run first with no DB lock; then ONE write transaction). From CONFIRMED: CONFIRMED to SEARCHING to outcome. From SEARCHING ("Search again"): ONLY SEARCHING to outcome | `agents/da_discover_flow.py`; `test_da_discover_flow_start.py` | demo record with the fake provider gives summary source `ai` and SIMILAR_IMPLEMENTATION_FOUND (proves the fake script ids exist, decision 7); status, audit events (`discovery_started`, `discovery_completed`, two `status_changed`) and round row saved together; start from SEARCHING writes only one `status_changed`; ATOMICITY: force a failure after the status write (monkeypatch the result insert to raise) and prove status, audit events, results and discovery revision are all unchanged; record v1 row and the stored session JSON are byte-identical after the action |
| 11c | `add_hint_and_search`, round cap, stale check | `agents/da_discover_flow.py`; `test_da_discover_flow_hint.py` | hint on demo record with fake provider gives summary source `ai` and SIMILAR_IMPLEMENTATION_FOUND; audit `discovery_hint_added` first; outcome to SEARCHING to new outcome in one transaction; hint with a secret or code refused; round 4 refused with a plain message; stale base revision refused with `STALE_MESSAGE` and nothing written; bad-AI path still gives a saved round with summary source `fallback` |
| 11d | `confirm_discovery`, `escalate_discovery`, `get_discovery_view` | `agents/da_discover_flow.py`; `test_da_discover_flow_finish.py` | confirm gives DISCOVERY_CONFIRMED with `discovery_confirmed` and `status_changed`; escalate gives ESCALATION_REQUIRED with `discovery_escalated` carrying the open item; the view shows the open item ("Escalated in Discover: ...") and the choices for each status; both refused from the wrong status and from a stale revision; record v1 row and session JSON byte-identical after every Discover action (start, hint, confirm, escalate) |
| 12 | Fake onprem server: discover marker routes to the discover reply; `bad-json` works | edit `web/da_fake_onprem_server.py`; `test_da_fake_onprem_server.py` | marker prompt gets discover reply; understand replies unchanged; bad-json mode gives bad discover reply |
| 13a | Screen parts: layout and components (Discovery tab, stepper on Discover, outcome banner, finding cards, limitations card, fallback banner, "Round N of 3", structural row greyed, disabled Readiness Gate button, hint box) | edit `layouts/da_developer_assistant_page.py`, `web/da_web_components.py`; tests in the matching existing page and component test files | cards show `path . symbol @ version` (version part only when known); structural row greyed "Coming later"; fallback banner text exact; Readiness Gate button disabled |
| 13b | Screen wiring: active Proceed button, chat divider and bubbles, busy text, confirm, escalate and hint buttons | edit `callbacks/.../da_developer_assistant_page_callbacks.py`; test in the matching existing callback test file | Proceed enabled only at CONFIRMED_FOR_DISCOVERY or SEARCHING; callbacks call only flow functions and show `SHOWN_ERRORS`; hint box hidden after the round cap; chat shows the Discover divider once |
| 14 | Smoke check items 15 to 17 | edit `da_smoke_check.py`; `test_da_smoke_check.py` | smoke prints 1 to 17; item 17 uses pretend onprem server in `bad-json` mode |
| 15 | README "How Phase 3 works", `.env.example` check, `specs/parked-items.md` (P15 to P18), `tests/da_play.py` only if it needs the new statuses | README.md, specs/parked-items.md | env-example test; manual hands-on list for Gian |
| 16 | Full run: pytest, ruff, smoke check; code-reviewer subagent (max 3 rounds); push `phase-3` | none | real output pasted |

## "Done when" map

| Spec line | Step |
|---|---|
| pytest and ruff clean | every step, final run in 16 |
| smoke prints 1 to 17 | 14 |
| exact and meaning find expected piece; filter drops bad hits | 4, 5 |
| splitter pieces, broken file, skipped folders | 6 |
| gap or out-of-order index refused; empty filter fallback | 4, 5 |
| queries from record and hint, cap 6; merge by path and symbol (two functions in one file stay two hits), cap 12 | 7 |
| good reply, retry cases, two bad replies and `LLMClientError` fallback | 8, 9 |
| outcome status per section 2 and the "not proof" limitation | 11a, 11b |
| round cap; hint refuses secrets and code | 11c (uses 8 checks) |
| one transaction per round, append-only, record v1 unchanged | 10, 11b, 11d |
| stale window refused; `codevision` message | 11c, 11d, 5 |
| Gian's hands-on check (fake, hint round, bad-json fallback banner) | 13a, 13b, 15 (checklist given to Gian) |
| Reviewer 0 Must fix, README, parked items | 15, 16 |

## Flow design notes (step 11)
- `start_discovery`: reads the request, record v1 (via existing readers) and the discovery revision,
  checks the revision, builds queries, searches with no DB lock held, calls the agent, then ONE write
  transaction. From CONFIRMED: CONFIRMED -> SEARCHING (audit `discovery_started`, `status_changed`),
  insert round, SEARCHING -> outcome (audit `discovery_completed`, `status_changed`), bump discovery
  revision. From SEARCHING ("Search again"): only SEARCHING -> outcome (no second `discovery_started`
  status move, because the status is already SEARCHING).
- Search and AI run before the write, so no half-saved round (spec section 2).
- Discover chat lines (divider, result line, confirm, escalate) are written with `add_message` on the
  same connection inside the same transaction, so a failed round leaves no orphan chat line. The
  atomicity test in 11b also checks the chat count.
- Name the new `da_discovery_state` table in spec section 11 when the decisions are copied there.
- Outcome: any `existing_capability` or `similar_implementation` finding gives
  SIMILAR_IMPLEMENTATION_FOUND, else NO_RELIABLE_MATCH plus the "not proof" limitation (app adds it).
- Round number = rows for the request + 1; refused beyond `DA_DISCOVERY_MAX_ROUNDS`.
- Reuse `StaleRevisionError` and `STALE_MESSAGE` from `db_tbl_da_understand.py`; do not edit
  `da_understand_flow.py` or `db_tbl_da_understand.py` (no 2A edit is needed, decision 2).

## Spec ambiguities and decisions (become section 11 of the spec)
1. **SEARCHING is a real saved status, but the round runs before the write.** The spec says
   SEARCHING means "a round is running" and "no round is half-saved". Choice: one transaction writes
   CONFIRMED -> SEARCHING -> outcome together. So SEARCHING is only reachable after a crash or a
   direct status set (for example in a test). "Search again" from SEARCHING stays supported and is
   tested by setting the status directly.
2. **Revision for the stale-window check (decided now).** The Understand revision lives on
   `da_understand_sessions`, and `save_session` rewrites the whole session JSON, record included.
   Choice: Discover keeps its OWN revision in a small new table `da_discovery_state`
   (request ID, revision), in the new `db_tbl_da_discovery.py`. Revision 0 means no row yet. Each
   Discover action does a compare-and-swap bump inside its transaction, like `save_session`, and
   raises the existing `StaleRevisionError`. `DiscoveryView.revision` carries it to the screen.
   No 2A edit at all: the session row and the record JSON are never written by Discover, and tests
   prove they are byte-identical after every Discover action (steps 11b, 11d).
3. **Hint moves.** Spec lists SEARCHING as a move from SIMILAR_IMPLEMENTATION_FOUND and
   NO_RELIABLE_MATCH. Choice: the hint action moves outcome -> SEARCHING -> new outcome inside the
   same transaction as the new round; audit `discovery_hint_added` first.
4. **Merge key.** Spec 3.3 (corrected in review 1): merge by (`source_path`, `symbol`), keep the best
   score. Two functions in one file stay two hits. Step 7 tests it. No README limit note.
5. **Existing-status guard.** `Request.status` and `STATUSES` are in `da_models.py` and
   `ALLOWED_MOVES` currently ends CONFIRMED with `()`; Phase 3 adds the moves there (spec 2) and
   nothing else.
6. **Search "Filters" and `languages` default Python.** Choice: `FakeSearchIndex` treats `config`,
   `doc`, `standard` pieces as language-neutral so standards and settings pieces still show.
7. **Fake provider for discover.** Choice: the discover agent gets its own `get_discover_client`
   (same pattern as `get_understand_client`, script `da_discover_fake_script.json`; generator role
   for real providers). The invented-id check stays strict. The script is written for the pretend
   index and PROVED: the demo record through the full flow with the fake provider gives summary
   source `ai` and SIMILAR_IMPLEMENTATION_FOUND, and the same for a hint round (tests in 11b, 11c).
8. **Fallback findings text.** Because snippets are code, no fallback explanation may quote them
   (no-code rule). The fixed explanation "Found by search. Check the source before reuse." is used
   for ALL fallback findings (code, config, standard, doc). Titles: code and config:
   "Possible match: <symbol or file name>" (kind `similar_implementation`, confidence low);
   standard: "Standard to check: <symbol or file name>"; doc: "Related document: <symbol or file
   name>" (both kind `relevant_standard`). Each title trimmed to 80. Tests (step 9) prove all four
   pass the step 8 checks.
9. **Confidence on fallback `relevant_standard`.** `medium` for standard, `low` for doc.
10. **Escalation open item.** Settled by the spec (3.5, corrected in review 1): the record is NOT
    changed. The open item ("Escalated in Discover: <latest limitation or 'developer request'>")
    is stored in the `discovery_escalated` audit event and the chat message, and shown by
    `get_discovery_view`. Step 11d tests the view shows it and the record is unchanged.
11. **`DiscoveryView` and `UnderstandView`.** Separate view class; the page picks which to render by
    status (CONFIRMED and later: Discover workspace, with the chat history shared).
12. **Chat messages for Discover** reuse the existing chat table with a divider message (speaker
    `system`); no new chat table.
13. **Pretend-index `version`.** Leave per-piece version empty and use the index `build_id`, so
    screens show `@ <build_id>`. Step 5 tests it.
14. **Python 3.14 `ast`.** Splitter targets 3.14 only; nothing newer.

## Risks and stop points
- If a Done-when line cannot be met without editing more of 2A/2B/2C than listed, stop and ask Gian.
- No new libraries. Cap: plan review 1 fix round, code review 3 rounds. Test fails twice: stop.
