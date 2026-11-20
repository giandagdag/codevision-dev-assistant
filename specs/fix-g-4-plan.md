# Fix G4 plan: work test 20 Nov (spec `specs/fix-g-4.md`)

Branch `phase-g-fix-4`, PR into `auto/phases-7-10` (body from a file, `--body-file`). Commit subjects
"G4 step N". No new library, no new table. `ops/work_queue.json` is not touched. Section 2.1 (A6) first.

## Cause (read in the code)
`agents/da_llm_client.py::_build_body` always sends temperature 0.2 / top_p 0.2 and never says whether
Qwen3 should think, so the model loops in its thinking text. `_empty_reply_message` reads only
`reasoning_content`, and always says "Check DA_ONPREM_URL" even when the server answered.
Settings are read in `configs/da_config.py` (`load_settings`, `_parse_*` helpers).

## Design (reuse what exists)
- New `Settings` fields: `onprem_thinking` ("off" / "on" / ""), `onprem_temperature`, `onprem_top_p`,
  `onprem_presence_penalty` (float or None), `onprem_max_tokens_build` (int or None). New small
  parsers beside `_parse_max_tokens`; a bad value raises `ConfigError` naming the setting.
- `_build_body` gets the sampling values from one helper `sampling_for(settings)` (thinking `on` and
  empty temperature/top_p gives 0.6 / 0.95), logged once at client creation.
- `get_llm_client(..., build=False)`: `get_build_client` passes `build=True`; only then
  `onprem_max_tokens_build or onprem_max_tokens` is used.
- `_read_reply` reads `reasoning_content` or `reasoning`; `_empty_reply_message` picks the sentence by
  cause (no `choices` / loop / length / only thinking / other). Loop test: last 1,000 characters of
  the thinking text, one piece of 2 to 20 characters covering over 60%.
- HTTP 400 whose body mentions `chat_template_kwargs` or `enable_thinking` gives its own
  `LLMClientError` (not `ContextTooLargeError`), no retry.
- Later steps reuse the shared card component, `da_admin_styles.py` and the Phase 11 rulebook
  save path (one new version per Admin action).

## Decisions (from plan review)
- "Builder role" = every caller of `get_build_client` (build loop, Refine, Enhance, Safety net,
  Independent Tester): they all write or judge code. Understand, Discover, Approach, tagger do not.
- `LLMReply` gets optional `finish_reason`, `usage` (dict) and `had_thinking` fields with defaults, so
  the ping can print them and no other client changes. Never the key or a header.
- The sampling log line is written once per process (module-level flag; a test checks a 2nd client).
- Suggestion data (S2 to S4): new optional module-entry fields `new_name`, `new_description` in the tag
  versions (defaults, old versions still read), state `proposed`; no new table.
- C3: the empty catalog applies only on the first publish at work. `refresh_purpose` keeps the catalog
  (test). C4 lives in the shared rulebook-save path, so every capability removal returns approved tags.
- Work notes go to `docs/build-work-test.md` (note 1, 2) and `docs/discover-work-test.md` (note 3).
- Browser measurements and screenshots go in `tests/test_da_admin_screens_browser.py`.
- The re-check (S6) uses the shared job lock; a test proves a second job is refused.
- Labels: "AI thinks before answering" in Server settings (`da_admin_repo_tab.py`) and the Build tab's
  "AI thinking" line; both in the AF-2 scan.

## Steps
0. **Current phase** in `CLAUDE.md` set to Fix G4 (G3 merged, PR #110); keep under 6,000 bytes.
1. **T1, T2, T4, T5, T6, T7** (G4-1 to G4-5): settings and parsers, body, reply reading, error
   sentences, the 400 switch refusal. Tests in `test_da_config.py` and `test_da_llm_client_onprem.py`.
2. **T3, T8, T9** (G4-6, G4-7, G4-19 part): `DA_ONPREM_MAX_TOKENS_BUILD` and `build=True`;
   `da_llm_ping.py` prints thinking, sampling, finish reason, tokens (never key); Build tab and Admin
   read-only "AI thinking" line; `.env.example` lines (env-example test list updated);
   `docs/build-work-test.md` work notes (spec 5).
3. **C1 to C5** in sub-steps: 3a `starter_leftovers` + Remove actions + screens (G4-8); 3b empty work
   seed (G4-10); 3c approved tags back to the queue (G4-9); 3d fake-folder refusal in the red box
   (G4-18).
4. **S1 to S7** in sub-steps: 4a prompt, plain-code check, grouping, fake script (G4-11); 4b suggestion
   card, Create and assign, Assign to, Reject (G4-12); 4c approve-all skips, re-check (G4-13, G4-14).
5. **L1 to L4** (G4-15 to G4-17): even catalog rows, patterns side panel, Add modules modal.
6. **L5, L6** (G4-20, G4-21): charter layout and list rows.
7. **L7 to L10** (G4-22 to G4-25): Review queue view, scrolling box, search/filter/sort, bulk bar.
8. **L11, G4-19, G4-26**: screenshots at 1366 and 1920 px, layout fixes in one batch, AF-2 label scan.
Then code review (max 3 rounds), full pytest, ruff, smoke, PR.

Each run builds at most 3 steps; the rest continue on this branch.

## Checks
Every step: its tests, `pytest`, `ruff check .`. Tests use `FakePost` / the fake provider only.
