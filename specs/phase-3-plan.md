# Phase 3 build plan: Discover

Spec: `specs/phase-3-discover.md` (v1.1). Branch `phase-3`. Start: 452 tests pass.
Every step ends with: `pytest`, `ruff check .` green, then a commit on `phase-3`.
Test files are new `tests/test_da_*.py` unless a step says otherwise. Existing 2A/2B/2C files
get only the small edits listed (rule R7).

## Steps

| # | Build | Files | Proof (tests) |
|---|---|---|---|
| 1 | Settings: `DA_SEARCH_PROVIDER`, `DA_SEARCH_TOP_K`, `DA_DISCOVERY_MAX_ROUNDS`, with range checks and plain errors | edit `configs/da_config.py`, `.env.example`; tests added to `test_da_config.py`, `test_da_env_example.py` | defaults; bad provider, top_k 0 or 21, rounds 0 or 6 refused |
| 2 | Statuses and moves: six new statuses and the section 2 table, plus the `ALLOWED_MOVES` rows | edit `pydantic_classes/da_models.py`; `test_da_status_moves.py` | every allowed move works, every other move refused, CONFIRMED -> SEARCHING only |
| 3 | Models: `SearchHit`, `SearchFilters`, `Finding`, `DiscoveryResult` (+ `DiscoveryView`) | new `pydantic_classes/da_discovery_models.py`; `test_da_discovery_models.py` | snippet over 500 refused; score 0 to 1; kind and confidence values; caps (8 findings, text lengths) |
| 4 | Pretend index file (about 25 pieces, incl. deprecated, restricted, `.env`-like, whole-file standards) and loader with the gap/order check | new `data/da_fake_index.json`; new `agents/da_search_index.py` (loader part); `test_da_search_index.py` | gap or out-of-order `piece_no` refused with plain message |
| 5 | `SearchIndex` protocol, `FakeSearchIndex` (exact, meaning + synonyms, empty-filter fallback), `get_search_index`, `codevision` placeholder, hard safety filter | `agents/da_search_index.py`; same test file | exact and meaning each find the expected piece; filter drops deprecated, restricted, secret-looking; fallback to all permitted pieces; `codevision` gives "not configured" message; count logged, not path |
| 6 | Python splitter and `split_folder` | new `agents/da_code_splitter.py`; `test_da_code_splitter.py` | functions, classes, methods with right symbols and line numbers; `<module>` piece; broken file gives one whole-file piece plus warning; `.venv`, `__pycache__`, secret paths skipped; order stable. Also checks fake index shape against the splitter's piece fields |
| 7 | Query builder and merge | new `agents/da_discover_queries.py`; `test_da_discover_queries.py` | queries from title, references, objective, expected behaviour, hint; capped at 6; merge by path keeping best score; best 12; `hit_id` 1..12 |
| 8 | Checks for the AI reply | new `agents/da_discover_checks.py`; `test_da_discover_checks.py` | shape and values; caps; invented `hit_id`; missing citation; code in text (reuses Phase 2 `find_code`); hint check reuses `developer_message_problem` |
| 9 | Prompt, fake script, discover agent (one call, 2 attempts, fallback) and rejected-log `step` argument | new `data/da_discover_prompt.md`, `data/da_discover_fake_script.json`, `agents/da_discover_agent.py`; edit `agents/da_rejected_reply_log.py` (optional `step="understand"` in header); tests in `test_da_discover_agent.py`, `test_da_rejected_reply_log.py` | good reply gives findings; invented id, no citation, 9 findings, code each cause one retry with a plain note; 2 bad replies and `LLMClientError` give fallback (code/config -> Possible match low; standard/doc -> relevant standard); entries logged with step `discover`; old log tests unchanged |
| 10 | Storage: `da_discovery_results` table, append-only triggers, unique (request, round) | new `db_table_functions/db_tbl_da_discovery.py`; `test_db_tbl_da_discovery.py` | insert and read; UPDATE and DELETE refused; duplicate round refused |
| 11 | Outcome rule and flow: start, hint, confirm, escalate, view; one transaction per round; stale-window check; round cap | new `agents/da_discover_flow.py`; `test_da_discover_flow.py` | see "Done when" map below |
| 12 | Fake onprem server: discover marker routes to the discover reply; `bad-json` works | edit `web/da_fake_onprem_server.py`; `test_da_fake_onprem_server.py` | marker prompt gets discover reply; understand replies unchanged; bad-json mode gives bad discover reply |
| 13 | Screen: active Proceed button, chat divider and bubbles, stepper on Discover, Discovery tab, outcome banner, finding cards, limitations, fallback banner, "Round N of 3", disabled Readiness Gate button, hint box | edit `layouts/da_developer_assistant_page.py`, `callbacks/.../da_developer_assistant_page_callbacks.py`, `web/da_web_components.py`; tests in the three matching existing page/callback/component test files | button enabled only at CONFIRMED_FOR_DISCOVERY or SEARCHING; callbacks call only flow functions and show `SHOWN_ERRORS`; cards show `path . symbol @ version`; structural row greyed "Coming later"; fallback banner text exact |
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
| queries from record and hint, cap 6; merge by path, cap 12 | 7 |
| good reply, retry cases, two bad replies and `LLMClientError` fallback | 8, 9 |
| outcome status per section 2 and the "not proof" limitation | 11 |
| round cap; hint refuses secrets and code | 11 (uses 8 checks) |
| one transaction per round, append-only, record v1 unchanged | 10, 11 |
| stale window refused; `codevision` message | 11, 5 |
| Gian's hands-on check (fake, hint round, bad-json fallback banner) | 13, 15 (checklist given to Gian) |
| Reviewer 0 Must fix, README, parked items | 15, 16 |

## Flow design notes (step 11)
- `start_discovery`: reads session and record v1 (via existing readers), checks revision, builds
  queries, searches with no DB lock held, calls agent, then ONE write transaction: status
  CONFIRMED -> SEARCHING (audit `discovery_started`, `status_changed`), insert round, then
  SEARCHING -> outcome (audit `discovery_completed`, `status_changed`).
- Search and AI run before the write, so no half-saved round (spec section 2).
- Outcome: any `existing_capability` or `similar_implementation` finding gives
  SIMILAR_IMPLEMENTATION_FOUND, else NO_RELIABLE_MATCH plus the "not proof" limitation (app adds it).
- Round number = rows for the request + 1; refused beyond `DA_DISCOVERY_MAX_ROUNDS`.
- Reuse `StaleRevisionError`, `STALE_MESSAGE` and the `_Turn`-style helper pattern from
  `da_understand_flow.py`; do not edit that file except where D3 below says.

## Spec ambiguities and proposed choices (become section 11)
1. **SEARCHING is a real saved status, but the round runs before the write.** The spec says
   SEARCHING means "a round is running" and "no round is half-saved". Choice: one transaction
   writes CONFIRMED -> SEARCHING -> outcome together, so SEARCHING is only ever seen after a crash
   between a status write and a round write (which the single transaction prevents) or after a hint
   click. Simplest safe reading; "Search again" from SEARCHING stays supported and tested by
   setting the status directly in a test.
2. **Who owns the revision for the stale check.** Choice: Phase 3 reuses the request's `version`
   field / session revision already used by Phase 2 (the number the screen carries in its state);
   each Discover action bumps it. Exact field confirmed when reading `UnderstandSession` in step 11.
3. **Hint moves.** Spec lists SEARCHING as a move from SIMILAR_IMPLEMENTATION_FOUND and
   NO_RELIABLE_MATCH. Choice: hint action moves outcome -> SEARCHING -> new outcome inside the same
   transaction as the new round; audit `discovery_hint_added` first.
4. **"Hits merged by path".** Two methods in one file would collapse into one hit. Choice: follow
   the spec literally (merge by `source_path`, keep best score), so one hit per file; noted as a known
   limit in README. Alternative (merge by path plus symbol) is easy later.
5. **Existing-status guard.** `Request.status` and `STATUSES` are in `da_models.py` and `ALLOWED_MOVES`
   currently ends CONFIRMED with `()`; Phase 3 adds the moves there (spec 2 says so) and nothing else.
6. **Search "Filters" and `languages` default Python.** Choice: `FakeSearchIndex` treats `config`,
   `doc`, `standard` pieces as language-neutral so standards and settings pieces still show.
7. **Fake provider for discover.** `get_understand_client` returns a scripted client keyed by step;
   Choice: discover agent gets its own `get_discover_client` (same pattern, `da_discover_fake_script.json`),
   generator role for real providers. Fake script is built for the pretend index, ignoring the prompt,
   so its `hit_ids` must exist: queries from the demo example are tested to return those ids; if they
   do not, the app's invented-id check triggers the fallback, which is by design.
8. **Fallback titles.** Spec gives "Possible match" for code/config. Choice: title = "Possible match: <symbol or file name>"
   trimmed to 80, explanation = first 300 chars of the snippet's plain description line (no code):
   because snippets are code, the fallback explanation is the fixed text "Found by search. Check the source before reuse." to
   keep the no-code rule true.
9. **Confidence on fallback relevant_standard.** Choice: `medium` for standard, `low` for doc.
10. **Escalation open item.** Spec says "open item" on the record; record v1 is never changed. Choice:
    store it as an `open_item` field in the `discovery_escalated` audit event and in the chat message,
    not in the record. Shown in `get_discovery_view`.
11. **`DiscoveryView` and the existing `UnderstandView`.** Choice: separate view class; the page picks
    which to render by status (CONFIRMED and later -> Discover workspace with the chat history shared).
12. **Chat messages for Discover** reuse the existing chat table with a divider message
    (speaker `system`); no new chat table.
13. **Pretend-index `version`.** Choice: leave per-piece version empty and use the index `build_id`,
    so screens show `@ <build_id>`.
14. **Python 3.14 `ast`.** Splitter targets 3.14 only; nothing newer.

## Risks and stop points
- If a Done-when line cannot be met without editing more of 2A/2B/2C than listed, stop and ask Gian.
- No new libraries. Cap: plan review 1 fix round, code review 3 rounds. Test fails twice: stop.
