# Fix batch B1: trust fixes from Gian's work testing (11 to 14 Nov)

Version 1.0 APPROVED, 14 Nov 2026 (22:15 SGT). Written in the project chat from
`claude/findings-2026-11-14-decisions.md` (agreed item by item with Gian on 14 Nov, the source of
truth: do not re-open those decisions unless the code proves one wrong).
Gian, 14 Nov 20:01: D-A option 2 (build the real CodeVision index now), all other D-x option 1.
Section 9 (P15) written from Gian's work photos of 14 Nov 22:01 (shapes only, no work code copied).

Branch `phase-b1-fixes` (from `auto/phases-7-10`, after PR #73). PR into `auto/phases-7-10`; the
chief merges it. Build it the normal way: plan, plan review, build in small steps with tests, code
review (max 3 rounds), pytest, ruff, smoke check. Laptop team. Builder plans straight from this spec
(no spec-writer run).

Naming: the findings file has two "item 6". Here **A6** = the contract check (B1), **B6** =
Explain simply / Help me decide (batch B2, not here).

## 1. The problems

| # | Severity | What Gian saw | Root cause (checked in code on 14 Nov) |
|---|---|---|---|
| 12 (+11, 15b) | Critical | Check 2 says Passed, but 5 of 8 tests show "-" | (a) `RecordingResult` in `agents/da_sandbox_runner.py` handles only success, failure, error and skip. Expected failure, unexpected success and failing sub-tests are never recorded (a test whose sub-test fails gets no row at all). (b) `LayerBResult.ok` (`pydantic_classes/da_build_models.py`) = ran, not timed out, 0 failed, at least 1 test. It never checks that every frozen test has a result |
| A6 | Critical | Calculator build NOT PASSING, Layer A failed 3 rounds | `_class_args` in `agents/da_build_checks.py` reads only `__init__`. A Pydantic model (or dataclass) has fields and no `__init__`, so the contract check says "takes ()". Our false alarm, and Get help blamed the developer |
| 9 | High | His own test "trailing space = Success" quietly became Expect Fail | Requirement says exact match only, so the AI changed his test to fit it, silently |
| 15a | High | Approach failed with "no choices[0].message.content" | Attempt 1 planned files in `src/upload`, `src/ingestion`, copied from Discovery's practice index (`fake-index-001`), refused by the folder check. Attempt 2 came back with empty content. `_read_reply` (`agents/da_llm_client.py`) never reads `finish_reason` and logs nothing of the reply. At work `DA_SEARCH_PROVIDER=codevision` is still a placeholder (P15), so Discovery silently used the practice index |
| 17 | High | The AI asks about the "Harbour Loans demo application" at work | `data/da_rulebook_seed.json` purpose and scope describe the made-up app. The seed is published once as v1, so the work database already holds it |
| 14 + new | High | Home stops working; Home link and title disappear | Reproducible at work: open a request, Home, open the same request again (with an error, or while still waiting on the AI). Cause not found yet (section 3) |
| 5 | Medium | A requirement change stops with "... already exists" | The new plan says `create` for a file the DA itself wrote in Build 1. Blocker B4 (`_one_file_blockers` in `agents/da_workspace_checks.py`) refuses every `create` on an existing file; it does not know the DA wrote it |
| 13 | Low | "Checking your folder" shows for every click | One busy text per page stage (`WS_BUSY_TEXT`, `BUSY_ID` in `layouts/da_developer_assistant_page.py`) |

## 2. What we build

| # | Fix |
|---|---|
| F1 (12) | **Record every outcome.** The sandbox runner records `expected_failure`, `unexpected_success` and each failing sub-test (`addSubTest` with an error: the parent test gets `fail` with the sub-test's message; a parent whose sub-tests all pass gets `pass` once). Still standard library only |
| F2 (12) | **Pass means proven.** `LayerBResult` gets the list of frozen test names it expected. `ok` is true only when every expected test has a result **and** every result is `pass`. `skipped`, `expected_failure` and `unexpected_success` are not a pass. A frozen test with no result is **"Not proven"**: shown in its row (orange, "Not proven: no result recorded"), and it blocks the pass |
| F3 (12, D-D) | **Not proven is the system's problem.** A run where any frozen test is Not proven ends like an interrupted run (`b_interrupted` path): no repair round is used, the AI is not asked to fix it, and the chat says "Some tests did not report a result. This is a problem in the Developer Assistant, not in your code. Run the tests again, or Get help." |
| F4 (A6) | **Contract check reads fields.** `_class_args` returns the `__init__` arguments when there is one; otherwise the annotated class-level fields of a Pydantic model or dataclass (in order, without `ClassVar` and names starting with `_`). Any other class without `__init__` keeps today's behaviour |
| F5 (A6) | **Get help says whose fault it is.** When a failure comes from the DA's own check (F3, or a check flagged `system=True`), Get help starts with "This looks like a problem in the Developer Assistant, not your code." and offers Send to my senior. Developer-caused failures keep today's wording |
| F6 (9) | **Never rewrite his test silently.** When the Tester sees his own test disagrees with a criterion, it answers `CONFLICT` with the criterion ID and one line why. Plain code shows: "Your test expects <his expectation>, but AC-n says <criterion>. Change the requirement, or change your test." with two buttons: **Change what it does** (opens the requirement lane with his test text as the starting point) and **Change my test**. Nothing is stored and no case ID is used up until he chooses. The fake Tester script gets a `conflict` switch |
| F7 (15a, D-A, D-B) | **No silent practice index at work.** "At work" = `DA_LLM_PROVIDER=onprem` (D-B, no new setting). At work with `DA_SEARCH_PROVIDER=fake`, Discovery does not search; it says "No CodeVision index is connected yet, so Discovery found nothing to reuse. Ask your admin to set it up." and the request carries on. With `codevision` it uses the real index (section 9). At home (`fake` provider) a banner on every page: **"Demo mode: made-up data, not CodeVision."** |
| F8 (15a, D-E) | **Log empty replies.** `_read_reply` reads `finish_reason`. When `content` is empty or missing, the log line has the model, `finish_reason`, the token counts and the **first 2,000 characters** of the raw reply body (never headers, never the key). The error text adds the reason in plain words (for example "the AI stopped at its length limit"). Leads to check, in this order: `finish_reason = "length"`; reply holds only a thinking or `reasoning_content` part |
| F9 (17, D-C) | **Work rulebook describes CodeVision.** New `data/da_rulebook_seed_work.json`: same rules as today's seed, with purpose and scope describing CodeVision (the bank's modernization tool, Python Dash), no made-up app names. `da_load_starter_rulebook.py` uses the work seed when `DA_LLM_PROVIDER=onprem`. New flag `--refresh-purpose`: publishes the work seed's purpose and scope as a **new** rulebook version, only when the active version still mentions "Harbour Loans"; otherwise it prints "Nothing to change" and writes nothing. Old versions stay (restore still works) |
| F10 (14) | **Home always works.** Find the cause first (section 3), then fix it. Rule: from any request page, in any state, Home goes back to the request list, and opening the same request again shows the Home link, the title and the request |
| F11 (5) | **Update what the DA wrote.** B4 changes: a planned `create` on an existing file is allowed **when the file's text matches the DA's last written version** of that path for this request (the `WrittenFile` fingerprint); the plan action becomes `modify` and the build uses edit blocks. When the developer edited it since, use the Phase 8 **Keep mine / Take the AI's** flow. A file the DA never wrote keeps today's B4 refusal. No silent overwrite, no archive copies in the folder |
| F12 (13) | **Each action has its own busy text.** Every button that waits on the server carries its own line (for example "Re-scanning your folder...", "Asking the AI for an approach...", "Starting the build..."). One constant table for the words. No button shows another button's text |

## 3. Item 14: find the cause first

Facts from work: open a request, press Home, open the same request again while it shows an error or
is still waiting on the AI. After that the Home link and the title are missing and Home does nothing.
The Home link is a `dcc.Link` with `href="?"` (`layouts/da_developer_assistant_page.py`).

Leads to check, in this order (say which one it was before changing code):
1. Going back to the same URL: the page callback does not run again because the URL did not change,
   so the old, half-drawn layout stays.
2. A callback still waiting on the AI finishes after Home and writes into the page it left (stale
   output overwriting the header).
3. The `?as=` switch (Phase 10) or a store kept between pages hides the header.

Proof: a Playwright test (skipped when no browser): fake AI server with a slow reply, open request,
Home, open the same request, then check the Home link, the title and the request ID show, and Home
works. Also the error case. Standing order SO-2 applies: if not reproduced or not fixed in 2 attempts,
park F10, keep building the rest, tell Gian (`gian-later`), and list the work steps or photos needed.

## 4. Edge rules

- No new status, no `ALLOWED_MOVES` change. Database change only if F2 needs to store the expected
  test names (say so in the plan; prefer reading them from the frozen test file).
- Old build records (before this fix) are drawn as they are; F2 applies to new runs only.
- F11 never deletes files and never writes over a developer edit without his choice.
- F8 logs never hold a key, a header or more than 2,000 characters of the reply.
- F9 never changes the home seed or home databases; tests use a copy.
- Words for F3, F5, F6, F7, F12 come from one constants place each, so batch B2 can reuse them.
- New libraries, only for section 9, pinned to work's versions (approved by Gian 14 Nov):
  `faiss-cpu==1.12.0` and `numpy==2.4.1` (faiss needs numpy). Both have Python 3.14 wheels for
  Windows and Linux. Nothing else.

## 5. Choices (D-x). DECIDED 14 Nov 20:01: D-A option 2, all others option 1

- **D-A Work Discovery:** 1. Say "no index", P15 later. **2. Build P15 now (CHOSEN)** with work photos.
- **D-B How the DA knows it is at work:** **1. `DA_LLM_PROVIDER=onprem` (CHOSEN).** 2. New `DA_MODE`.
- **D-C Work rulebook:** **1. Work seed plus `--refresh-purpose` (CHOSEN).** 2. Edit in Admin by hand.
- **D-D Not proven:** **1. System problem, no repair round (CHOSEN).** 2. Count as a failed test.
- **D-E Empty reply log:** **1. `finish_reason`, tokens, first 2,000 characters (CHOSEN).** 2. Full body.
- **D-F Item 9:** **1. In B1 (CHOSEN).** 2. In B2.
- **D-G Flow:** **1. Builder plans straight from this spec (CHOSEN).** 2. Spec writer first.

## 6. Build order

F1 to F3 (item 12), F4 to F5 (A6), F6 (item 9), F8, F7 then F9, F11, F12, F10, then section 9.
Trust fixes first: if section 9 runs into a surprise, SO-2 parks it and B1 still ships.

## 7. Acceptance criteria (Given / When / Then)

| ID | Given / When / Then |
|---|---|
| B1-1 | Given a frozen test with a failing sub-test, when Layer B runs, then that test's row says fail with the sub-test message, and the build is not passing |
| B1-2 | Given tests marked expected failure, unexpected success and skipped, when Layer B runs, then each has its own row and none counts as a pass |
| B1-3 | Given 8 frozen tests and results for only 5, when the run ends, then 3 rows say "Not proven", the build is not passing, no repair round is used, and the chat says it is the DA's problem |
| B1-4 | Given every frozen test passed, when the run ends, then check 2 says Passed (unchanged) |
| B1-5 | Given a contract with a Pydantic model `Loan(amount: float, rate: float)` and code that defines it, when Layer A runs, then the contract check passes; a dataclass passes too; a plain class with `__init__(self, x)` is checked as today |
| B1-6 | Given a failure flagged as the system's, when Get help opens, then the first line says it is a problem in the DA, not his code |
| B1-7 | Given his own test conflicts with AC-n (fake Tester `conflict`), when he adds it, then the chat names AC-n, shows both buttons, nothing is stored and no case ID is used |
| B1-8 | Given `onprem` and search provider `fake`, when Discovery runs, then no practice-index hit appears and the "No CodeVision index" line shows; given `fake` provider, the demo banner shows on every page |
| B1-9 | Given the onprem client gets `content: null` with `finish_reason: "length"`, when it reads the reply, then the log has the model, reason, token counts and at most 2,000 characters of the body, no key, and the error names the length limit |
| B1-10 | Given an active rulebook mentioning "Harbour Loans", when `--refresh-purpose` runs at work, then a new version describes CodeVision and the old one can be restored; run again, it prints "Nothing to change" |
| B1-11 | Given a request open while waiting on the slow fake AI, when he goes Home and opens it again, then the Home link, title and ID show and Home works (Playwright; skipped with no browser) |
| B1-12 | Given a file the DA wrote in Build 1 and not edited since, when a revision plans `create` for it, then no B4 blocker appears and the build updates it in place |
| B1-13 | Given that same file edited by the developer, when the revision builds, then Keep mine / Take the AI's is offered and nothing is overwritten before he picks |
| B1-14 | Given a file the DA never wrote, when the plan says `create`, then B4 refuses it as today |
| B1-15 | Given each button that waits on the server, when it is clicked, then the busy line is that button's own text |
| B1-16 | Given a made-up folder of 3 Python files and the fake embedder, when `da_build_code_index.py` runs, then the vector file and the piece list are written, vector N matches piece N, and `da_` files, `__pycache__` and secret-looking paths are not in it |
| B1-17 | Given the fake embedder fails for 1 of 20 pieces, when the build runs, then the index is saved with 19 pieces and the summary names the 1 skipped piece by path and symbol (never its text); given 3 of 20 fail (over 10%), nothing is saved and the old index stays |
| B1-18 | Given a built index, when Discovery runs a meaning search with provider `codevision`, then hits come from the index, only hits within the distance limit are kept, filters apply after the vector search, and an empty filter never means "no results" (the trap in spec 3, section 3.2) |
| B1-19 | Given a built index, when an exact search runs, then it uses the same word matching as the practice index, on the real piece list |
| B1-20 | Given provider `codevision` and no index files (or a piece list whose count differs from the vector file), when Discovery runs, then it says the index needs building (names the command), and the request carries on |
| B1-21 | Given the embedding call fails during a search, when Discovery runs, then exact search still runs and the chat says the meaning search was not available |

## 8. Out of scope

- Batch B2 (items 1 to 4, B6, 7, 8, 10, 16, D1, D2). Director item D4 (rule versioning and rollback).
- "Review my code" (on hold). The Audit tab timeline (P22).
- An Admin "Rebuild index" button (park it as a new P item).
- P16 structural search, P18 old-system summaries.
- CodeVision's own `a_vector.py` (its retry count check and the text it prints on failure are
  CodeVision's code, not ours: mention to Gian, do not change).

## 9. Real CodeVision index (P15, D-A option 2)

### 9.1 What the work photos showed (14 Nov 22:01, shapes only)
- `agents/a_vector.py` has `create_embeddings(text)`: one HTTP call per text to CodeVision's
  embedding endpoint, with its own header, payload, retries and certificate check (all from
  CodeVision's own settings). It returns a numpy array of shape **(1, size)**, `float32`, or
  **None** when every retry failed (and then it prints the text it was given).
- The same file builds FAISS `IndexFlatL2` indexes (`faiss.read_index`, `write_index`).
  `update_existing_vector_db.py` changes an index by rebuilding it in full. There is no batch call.
- `query_vector_db(embedding, index_file, k, relevant_idx_list)` keeps hits with distance <= 0.90
  **and** in the allowed list. An empty list returns nothing, so we do not call it (trap, spec 3
  section 3.2): we call `index.search` ourselves.
- CodeVision code lives in `imagebuild/src` with the same folders as ours (agents, agent_flows,
  callbacks, configs, db_functions, db_table_functions, layouts, pydantic_classes, styles, tools,
  web). Python 3.14, `faiss-cpu==1.12.0`, `numpy==2.4.1`, `requests==2.32.5`.

AS400 comparison: the piece list is the physical file, the vector file is a keyed logical over it.
Record N in one is key N in the other, so both are always rebuilt together.

### 9.2 What we build
| # | Part |
|---|---|
| I1 | **Embedder interface** in `agents/da_code_index.py`: `embed(text) -> list[float] or None`. `WorkEmbedder` imports CodeVision's `agents.a_vector` **only when called** (at home it does not exist; the error says "This only works inside CodeVision at work."). `FakeEmbedder` for tests: same text, same vector, no network. Our code never logs the text it embeds |
| I2 | **Build command** `src/da_build_code_index.py` (C1): runs `split_folder` over the source folder (setting `DA_CODE_INDEX_SOURCE`, default: the `src` folder the DA runs in), skips `da_` files (the assistant itself is not product code), `__pycache__` and secret-looking paths. Embeds each piece (path, symbol and the piece text, cut to 2,000 characters). Prints progress every 50 pieces |
| I3 | **Saved together, or not at all.** Two files in `DA_CODE_INDEX_DIR` (default `src/data/da_code_index/`, Git ignores it): `da_code_index.faiss` and `da_code_index.json` (same shape as the practice index: `build_id` `cv-<date>-<time>`, `built_at`, `pieces`, plus `source`, `vector_size`, `count`). Written to side files, then both replaced. Pieces whose embedding failed are left out and listed (path and symbol) in the summary. More than 10% failed: nothing is saved, the old index stays, and the summary says so |
| I4 | **`CodeVisionSearchIndex`** replaces the placeholder. Exact mode: the practice index's word matching, run on the real piece list (share the code, do not copy it). Meaning mode: embed the query, `index.search` for `top_k x 4`, keep distance <= `DA_CODE_INDEX_MAX_DISTANCE` (default 0.90, same as CodeVision), then filters, then the top `top_k`. Score shown = `1 - distance / 2`, cut to 0..1. The safety filter (`drop_unsafe_hits`) runs as today |
| I5 | **Honest when missing.** No index files, or the piece count differs from the vector count: Discovery says "The CodeVision index needs building: run `python src\da_build_code_index.py`." and the request carries on (F7). The embedding call fails during a search: exact search still runs and the chat says the meaning search was not available |
| I6 | **Smoke check item** (home): build a tiny index from a made-up folder with the fake embedder, then one exact and one meaning search |
| I7 | **Docs:** `docs/discover-work-test.md` gets a short section: build the index at work, what the summary means, how to rebuild. New parked item: Admin "Rebuild index" button |

### 9.3 Edge rules for section 9
- Tests use `FakeEmbedder` and real FAISS on made-up files only (no network, no work code).
- Never change or read CodeVision's own vector files; ours sit in our own folder.
- The vector size comes from the first vector; a different size later stops the build with a clear
  message (no silent mix).
- No change to Discover's rounds, caps, findings or the AI prompts.
