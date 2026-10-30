# Phase 3: Discover

Status: APPROVED v1.1 (30 Oct 2026). Decisions D-A to D-F chosen by Gian. v1.1 adds what the
work photos showed about CodeVision's search (section 9) and decisions D-E and D-F.
Depends on: Phase 2A, 2B, 2C
Next: Phase 4, Readiness Gate
Build: Saturday 31 Oct after P13, only if tokens allow. Merge only AFTER the Monday work test
(2 Nov) lessons are applied (handoff note section 13).

## In plain words

A confirmed request (record v1) says WHAT the developer wants. Discover answers: "does something
like this already exist, and what should be reused?" The app searches CodeVision's approved sources,
asks the AI once to sort the hits into plain findings, and shows them in the Discovery tab, each
with its source file and function or class. The developer says the findings look right, says something is
missing (search again with a hint), or escalates to a senior developer.

CodeVision's existing search index holds summaries of old-system programs, not CodeVision's own
Python code (section 9). So Discover gets its OWN index of the Python code, one piece per function
or class (D-E, D-F), built later at work with CodeVision's own embedding call and FAISS. At home,
as in 2C, we build against a small search interface plus a pretend index in the same shape. This
phase also builds the splitter that cuts Python files into pieces (standard library, testable).

AS400 comparison: like a cross-reference query (DSPPGMREF, or a where-used tool) run before you
write a new program, so you reuse an existing one instead of writing a copy. The app runs the
queries (CL), the AI writes the short report (one call), and the results are written to their own
journaled file keyed to the request. The request record itself is never changed.

Naming note: on screen, Discover is step 2 of the developer's 6 steps. In the build plan it is
Phase 3. The screen uses the developer's numbering.

## 1. Goal

- From a CONFIRMED_FOR_DISCOVERY request, the developer clicks "Proceed to Discovery" and gets
  findings in the Discovery tab, each tied to a source path and function or class, within one
  screen action.
- If the AI reply is bad (twice), the developer still gets a plain list of search hits. Discover
  never fails because the AI misbehaved.
- The developer can add a hint and search again (max 2 extra rounds), confirm, or escalate.
- Every round is saved append-only and every status move is audited.

## 2. Statuses and moves

| Status | Meaning | Can move to |
|---|---|---|
| CONFIRMED_FOR_DISCOVERY | From Phase 2 | SEARCHING |
| SEARCHING | A search round is running | SIMILAR_IMPLEMENTATION_FOUND, NO_RELIABLE_MATCH |
| SIMILAR_IMPLEMENTATION_FOUND | At least one "existing capability" or "similar implementation" finding | DISCOVERY_CONFIRMED, SEARCHING (hint), ESCALATION_REQUIRED |
| NO_RELIABLE_MATCH | No such finding (standards or areas may still show) | DISCOVERY_CONFIRMED, SEARCHING (hint), ESCALATION_REQUIRED |
| DISCOVERY_CONFIRMED | Developer accepted the findings. Final for Phase 3 | (Phase 4 adds moves) |
| ESCALATION_REQUIRED | Developer asked for a senior developer. Final for Phase 3 | (Phase 8 adds the inbox) |

- The app picks the outcome status from the findings, never the AI (rule R2 from Phase 2).
- A request left in SEARCHING (for example the app stopped mid-round) offers "Search again",
  which starts the same round over. No round is half-saved.
- Screen labels use spaces, as in the demo pills.

## 3. In scope

### 3.1 Search interface (`agents/da_search_index.py`)
- `SearchIndex` protocol with one method:
  `search(query: str, mode: "exact" | "meaning", filters: SearchFilters, top_k: int) -> list[SearchHit]`.
- `SearchHit` (pydantic, `pydantic_classes/da_discovery_models.py`): `hit_id` (set by the app,
  1, 2, 3...), `source_path`, `symbol` (function or class name, for example
  `UploadValidator.check_type`; empty for a whole non-code file), `line_start`, `version` (a commit
  ID when known, otherwise the index build ID; may be empty), `kind` (`code`, `doc`, `standard`,
  `config`), `language`,
  `snippet` (max 500 characters, refused if longer, never cut by the index), `score` (0 to 1),
  `mode`.
- `SearchFilters`: `languages` (default Python), `include_deprecated` false, `include_restricted`
  false. Phase 3 always uses the defaults.
- Provider switch `DA_SEARCH_PROVIDER`: `fake` (default, home and tests) or `codevision`
  (placeholder that raises "CodeVision search is not configured yet", exactly as 2C's onprem did
  before it was built). Built in `get_search_index(settings)`.
- Hard safety filter in OUR code, after any index: drop hits whose path looks like a secret or
  environment file (`.env`, `*.pem`, `*.key`, paths containing `secret` or `credential`), and drop
  deprecated or restricted hits even if the index returned them. Logged as a count, never the path.

### 3.2 Pretend index (D-A: exact + meaning; shape per D-F)
- `src/data/da_fake_index.json`, in the same shape the real index will have (section 9):
  - `build_id` and `built_at` for the whole index
  - `pieces`: a list where the position is the piece number (like the row number CodeVision uses
    to link vectors to names). About 25 made-up pieces of a made-up CodeVision-like codebase, one
    per function or class (for example an upload validator, a PDF processor, a batching helper,
    an ingestion router), plus a few whole-file pieces for standards and settings.
  - Each piece: `piece_no`, path, symbol, line_start, kind, language, deprecated, restricted,
    tags, snippet.
  - Include at least one deprecated, one restricted and one `.env`-like piece.
- Loading checks: `piece_no` must equal the position in the list, with no gaps. If not, the index
  is refused with a plain message. This guards the "rows out of order point to the wrong file"
  trap seen in CodeVision's design.
- `FakeSearchIndex` in `agents/da_search_index.py`, standard library only:
  - exact: case-insensitive whole-word match on path, tags and snippet; score by matches.
  - meaning: word overlap after a small built-in synonym list (for example extract, parse, read;
    validate, check; ingest, load). Good enough to prove the pipeline, not real semantic search.
- No new library. Real embeddings come with the real index.
- If a filter leaves nothing to search, meaning search falls back to ALL permitted pieces, never
  to zero results (CodeVision's own fallback is switched off; we do not copy that).

### 3.2a Python splitter (`agents/da_code_splitter.py`, D-F)
- `split_python_file(path, text) -> list[CodePiece]` using the standard `ast` module: one piece
  per top-level function, per class, and per method (symbol `Class.method`). Module-level code
  that is not inside any function or class becomes one `<module>` piece if it is not empty.
- Each piece: path, symbol, line_start, line_end, and the source text of that piece cut to 2,000
  characters for the index snippet (the full text stays in the file).
- A file that does not parse gives one whole-file piece and a warning, never a crash.
- `split_folder(root)`: every `.py` file under a folder, skipping `.venv`, `__pycache__`, and the
  secret-looking paths from 3.1. Sorted by path, so the piece numbers are stable.
- Phase 3 uses it only in tests and to check the pretend index. Writing vectors with CodeVision's
  `create_embeddings` and FAISS is the work adapter (P15).

### 3.3 Building the searches (app only, no AI)
- From record v1: exact queries from the title and each `references` item; meaning queries from
  `objective` and `expected_behaviour`; one more pair from the developer's hint when there is one.
- Max 6 queries per round, `DA_SEARCH_TOP_K` (default 5) hits each. Merge by `source_path`
  (keep the best score), keep the best 12. Number them 1 to 12 (`hit_id`).
- Structural search (callers, imports) is shown on screen as "Coming later", greyed out.

### 3.4 The one AI call (D-B: 1 call + safe fallback)
- `agents/da_discover_agent.py`, prompt `src/data/da_discover_prompt.md`. Uses the existing
  `get_llm_client` (fake, claude, onprem) with the `generator` role, the same one Understand's
  interpreter uses (check `get_understand_client` and follow it).
- Input: a short record summary (title, objective, expected behaviour, references, decisions)
  and the numbered hits (path, symbol, kind, snippet).
- Output, JSON only:
  `findings`: list of `{kind, title, explanation, hit_ids, confidence}` where kind is
  `existing_capability`, `similar_implementation`, `relevant_standard` or `affected_area`,
  confidence is `high`, `medium` or `low`; and `limitations`: list of short strings.
- Checks (`agents/da_discover_checks.py`), each failure a plain retry note:
  - JSON shape and allowed values; max 8 findings; title max 80, explanation max 300,
    limitation max 300 characters, max 4 limitations.
  - Every `hit_ids` value must be a hit we sent. Existing, similar and standard findings must cite
    at least one hit. The AI cannot invent a source.
  - No code in any text: reuse the Phase 2 no-code check.
- Retry once with a note (as `da_understand_agent`, MAX_ATTEMPTS 2). Every rejected reply goes to
  the existing rejected-reply log. Surgical change to `agents/da_rejected_reply_log.py`: an optional
  `step` argument (default `understand`) printed in the entry header, so discover entries are told
  apart. Existing callers and tests keep working unchanged.
- Fallback after 2 bad replies or an `LLMClientError`: build findings from the hits by the app:
  `code` and `config` hits become "Possible match" (kind `similar_implementation`, confidence low),
  `standard` and `doc` hits become `relevant_standard`. Banner: "AI summary unavailable. Showing
  plain search results." Outcome status still follows section 2.
- The app always adds this limitation when no existing or similar finding is found:
  "No reliable match was found in approved sources. That is not proof it does not exist."

### 3.5 Developer choices (D-C: hint and re-search)
- After a round: "✅ Findings look right", "✏️ Something's missing", "🙋 Escalate to a senior developer".
- Something's missing: the box asks "What's missing? Name a feature, file or term." Max 300
  characters, same secret and no-code checks as Phase 2. Then a new round runs with the hint.
  Max `DA_DISCOVERY_MAX_ROUNDS` (default 3, so 2 extra). After the cap, only confirm and escalate
  are offered, with a line saying why.
- Escalate: status ESCALATION_REQUIRED, open item "Escalated in Discover: <latest limitation or
  'developer request'>", chat says a senior developer will pick it up (the inbox is Phase 8).
- Confirm: status DISCOVERY_CONFIRMED, chat confirms with the round number. A disabled
  "🚦 Proceed to Readiness Gate (coming in Phase 4)" button shows.

### 3.6 Storage (D-D: own table, record v1 untouched)
- `db_table_functions/db_tbl_da_discovery.py`, table `da_discovery_results`, one row per round:
  request ID, round, record version, rulebook version, search provider, queries (JSON), hits
  (JSON), findings (JSON), limitations (JSON), summary source (`ai` or `fallback`), model,
  hint (or empty), created time (Singapore time). Append-only with SQLite triggers, as the audit
  trail. Unique on (request ID, round).
- Each round is saved together with its status move and audit events in ONE transaction.
- The request record v1 and its row are never changed.
- Audit events: `discovery_started`, `discovery_completed` (round, hit count, outcome, summary
  source), `discovery_hint_added`, `discovery_confirmed`, `discovery_escalated`, plus
  `status_changed` for every move (rule R6).

### 3.7 Flow functions (`agents/da_discover_flow.py`)
Thin, like `da_understand_flow.py`; the screen calls only these:
- `start_discovery(settings, request_id, base_revision)`: from CONFIRMED_FOR_DISCOVERY or SEARCHING
- `add_hint_and_search(settings, request_id, hint, base_revision)`
- `confirm_discovery(settings, request_id, base_revision)`
- `escalate_discovery(settings, request_id, base_revision)`
- `get_discovery_view(settings, request_id)`: latest round, findings, limitations, outcome,
  rounds used, choices, summary source
- Stale-window protection as Phase 2 (a second window cannot act on an old view).

### 3.8 Screen (`layouts/`, `callbacks/`, `web/da_web_components.py`)
Surgical changes to the 2B files, matching the demo's Envisioned Discover screens:
- The "Proceed to Discovery (coming in Phase 3)" button becomes active. Clicking it runs the
  round; busy text "⏳ Searching approved sources…".
- Chat: divider "🔍 Discover", the demo's two messages (searching, then the result line that
  names the outcome), and the developer's choices as chat bubbles.
- Stepper: Discover highlighted. The Discovery tab unlocks and opens automatically.
- Discovery tab: input banner (request ID and record version); search rows (Exact ✅, Meaning ✅,
  Filters ✅, Structural "Coming later" greyed); outcome banner (green or amber); one card per
  finding (kind icon and label, title, explanation, `source_path · symbol` (plus `@ version` when known) for each cited hit,
  confidence pill); limitations card; fallback banner when used; "Round N of 3".
- Earlier rounds are not shown on screen (they are in the table and the audit trail).

### 3.9 Pretend onprem server and fake script
- `src/data/da_discover_fake_script.json`: replies for the fake provider that match the pretend
  index (one good reply, and one that cites a hit that was not sent, for the retry test).
- Extend `src/web/da_fake_onprem_server.py` surgically: a prompt carrying the discover marker
  line ("Task: sort search hits into findings") gets the discover reply. `bad-json` mode works
  for discover too.

### 3.10 Settings (`configs/da_config.py`, `.env.example`)
| Setting | Default | Meaning |
|---|---|---|
| `DA_SEARCH_PROVIDER` | `fake` | `fake` or `codevision` (placeholder) |
| `DA_SEARCH_TOP_K` | `5` | Hits per query, 1 to 20 |
| `DA_DISCOVERY_MAX_ROUNDS` | `3` | Rounds per request, 1 to 5 |

### 3.11 Smoke check (extend `da_smoke_check.py`)
15. The pretend index loads (piece numbers checked), returns hits for an exact and a meaning
    query, and drops the deprecated, restricted and `.env` pieces
16. A full conversation reaches CONFIRMED_FOR_DISCOVERY, then Discover reaches DISCOVERY_CONFIRMED
    with the fake provider, and record v1 is unchanged
17. With the pretend onprem server in `bad-json` mode, Discover falls back to plain results and
    still reaches an outcome status

### 3.12 README
"How Phase 3 works": the flow in 5 lines, how to run it at home, and how the pretend index works.

## 4. Out of scope (do NOT build in 3)
- Writing real vectors (CodeVision's `create_embeddings` and FAISS) and the work adapter (P15).
  Structural search. Searching CodeVision's existing old-system summaries (P18).
- Path 3 "quick discovery", the Readiness Gate (Phase 4), the escalations inbox (Phase 8).
- The demo's "functional flow with reference labels" card (parked, see section 10).
- Changing the Understand prompt or engine. Showing earlier rounds on screen.
- P10, P11, P12 and the deferred demo look items.

## 5. Rules
- R1. The AI suggests, the app decides: queries, statuses and the outcome are app decisions.
- R2. No invented sources: every finding shown links to a hit the index really returned, shown as
  `source_path` and symbol, plus `@ version` when a version is known.
- R3. Secrets, environment files, deprecated and restricted content are never shown, even if an
  index returns them (our own filter, 3.1).
- R4. Record v1 is never changed. Discovery results are append-only.
- R5. Tests never call a real AI, a real index or the internet.
- R6. Every status move writes an audit event in the same transaction.
- R7. Surgical changes: 2A, 2B and 2C files are touched only where this spec says.
- R8. No new library. Standard library for the pretend index.
- All earlier phase rules still apply.

## 6. Done when
- [ ] `pytest` 0 failures (all earlier tests included), `ruff check` 0 problems
- [ ] The smoke check prints items 1 to 17
- [ ] Tests prove: exact and meaning search each find the expected made-up chunk; the safety filter
      drops deprecated, restricted and secret-looking hits
- [ ] Tests prove: the splitter makes one piece per function, class and method with correct
      symbols and line numbers; a broken file gives one whole-file piece; skipped folders are skipped
- [ ] Tests prove: an index with a gap or out-of-order piece number is refused; an empty filter
      result falls back to all permitted pieces
- [ ] Tests prove: queries are built from the record fields and the hint, capped at 6; hits are
      merged by path and capped at 12
- [ ] Tests prove: a good AI reply becomes findings; an invented `hit_id`, a missing citation, too
      many findings or code in the text causes one retry with a plain note; two bad replies and an
      `LLMClientError` both give the fallback
- [ ] Tests prove: the outcome status follows section 2, including the "not proof" limitation
- [ ] Tests prove: round cap enforced; hint checks refuse secrets and code
- [ ] Tests prove: each round, status move and audit event are saved in one transaction; results
      cannot be updated or deleted; record v1 is unchanged after Discover
- [ ] Tests prove: a stale window is refused; `codevision` provider gives the "not configured" message
- [ ] Gian's hands-on check at home: fake provider, full flow to DISCOVERY_CONFIRMED on the screen;
      one hint round; with the pretend onprem server in `bad-json` mode, the fallback banner shows
- [ ] Reviewer: 0 Must fix. README written. Parked items updated.

## 7. Monday link
- Monday tests 2C only (the ZIP is `main`). Phase 3 stays on its branch.
- If Monday shows Qwen or Llama struggle with JSON, apply the same lesson to the discover prompt
  and checks before merging (for example a shorter output shape, or JSON pulled out of extra text).

## 8. Decisions

| # | Question | Decision |
|---|---|---|
| D-A | Which search kinds | Exact and meaning, plus filters. Structural later, after the photos (Gian, 30 Oct) |
| D-B | How Discover uses the AI | App builds the searches. One AI call sorts hits into findings. Bad reply falls back to a plain hit list (Gian, 30 Oct) |
| D-C | "Something's missing" | Developer types a hint, search runs again. Max 2 extra rounds, then confirm or escalate (Gian, 30 Oct) |
| D-D | Where findings are saved | Own append-only table linked to request and record version. Record v1 untouched (Gian, 30 Oct) |
| D-E | What Discover searches | Our own index of CodeVision's Python code, not the existing old-system summaries (Gian, 30 Oct) |
| D-F | Size of an indexed piece | One per function or class (methods too), not one per file (Gian, 30 Oct) |

Set in this spec by Claude (veto any before the build): the six statuses in section 2; escalation
only sets a status and an open item; 12 hits and 8 findings caps; no new library.

## 9. What the work photos showed (30 Oct)
CodeVision's search, in plain words (no addresses or names copied):
- Builder (`load_md_to_vector_db.py`): for each markdown summary of an OLD-SYSTEM program, take its
  overview, make ONE vector for the whole file with `a_vector.create_embeddings`, add it to a
  FAISS index (`IndexFlatL2`) and add the name to a spreadsheet. The spreadsheet row number is the
  vector number. No chunking, no commit IDs.
- Embedding: one HTTP call per text to the embedding endpoint (model bge-m3), reply at
  `data[0].embedding`, retried up to 3 times.
- Search (`a_vector.query_vector_db`): nearest K vectors, keep distance <= 0.90, and keep only
  those in a list of allowed numbers. An empty list returns NOTHING (the fallback is commented out).
- Allowed numbers come from `a_retriever.retrieve_relevant_metadata_files`: records in a
  `metadata.json` matched on fields with "and" or "or".
- `agent_flows/flw_metadata_filtering.main(prompt, max_count)`: a LangGraph flow that pulls filter
  values out of the question, scores, filters, searches, reranks and writes the answer.
- `a_retriever` "yellow pages": a spreadsheet of program name, app code, source library and file
  type, used to find a program's source file and its markdown summary.
Conclusion: the content is old-system programs, so Discover needs its own Python code index (D-E).
The shape (vectors + numbered list + metadata) is reused, with two traps avoided (3.2).

## 10. New parked items (add to `specs/parked-items.md`)
- P15. Work adapter behind `DA_SEARCH_PROVIDER=codevision`: run the splitter over CodeVision's
  Python code, make vectors with CodeVision's `create_embeddings`, store them in FAISS with our
  numbered piece list, and search them. Needs `faiss-cpu` (on the work list); ask before adding.
- P16. Structural search (callers, imports, configuration links). After P15 shows what the index holds.
- P18. Optional second source: CodeVision's existing old-system summaries, as background for a
  change that touches an old-system program. Only if Gian wants it later.
- P17. Discovery tab "functional flow with reference labels" card from the demo. After Monday, if wanted.

## 11. Decisions made during planning
(Added by the planner.)
