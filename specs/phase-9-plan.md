# Phase 9 plan: Enhance an existing program

Spec: `specs/phase-9-enhance.md` (D-A to D-N chosen by chief, option 1 each; Gian approved, see Q-a).
Branch `auto/phase-9`. Pattern: copy Phases 6 to 8. Plain-code rules in pure files, one storage file,
thin flows (read with no lock, slow work outside, ONE write transaction, own revision, F1 to F3).
The spec has 50 "done when" lines (9-1 to 9-50). Order: **pure rules first, then storage, then flows,
then screen**. Each step ends with `pytest`, `ruff check .`, a commit and a push to `auto/phase-9`.
Runs build at most 3 steps, then `chief_tick.py next "builder continue Phase 9 from step K"`.
Code review only after the last step (max 3 rounds). A stop rule firing is written to
`ops/state/worker_note.md`.

## Design in plain words

- **No new status** (D-L). `da_enhance_state` holds the step (`e_find` ... `s_accepted`) and its own
  revision, like `da_refine_state`. During `e_*` the request stays at the status a new request has
  before Understand (`STATUS_DRAFT`, to confirm in step 1 by reading `ALLOWED_MOVES`); during `s_*` it
  stays DISCOVERY_CONFIRMED. The header pill shows the step label.
- **Kind** (`enhance`, `fix`) and the other new record fields are optional with empty defaults, so old
  records and old rulebooks load (9-22, 9-47).
- **Catalog** is a rulebook part `Capability` copied from `FlagReviewZone` (fnmatch on lower-case path).
  Starter data: 3 made-up capabilities. Real content is WF-2.
- **Find** reuses the Phase 3 `SearchIndex` (exact for names, meaning for description) and the Phase 3
  safety filter. Name scoring and catalog lookup are pure functions.
- **Freshness** compares his text with `get_main_source(settings)` using the Phase 5 fingerprint.
  Providers: `fake` (folder `DA_FAKE_MAIN_DIR`) and `bitbucket` placeholder that raises "not configured"
  (WF-1). Never a silent pass.
- **Impact** is `agents/da_impact.py`, `ast` only, over the Phase 6 reference copy
  (`sandbox_source_dir`, env `DA_SANDBOX_SOURCE_DIR`). Never reads his folder (R1).
- **Safety net** is one Tester call with code, kept separate from criterion Tester calls (W6, 9-29).
  Proof runs in the Phase 6 sandbox on baseline laid over the reference copy. Failing cases get up to
  `safety_net_max_attempts` fix calls, then are dropped and listed as not covered.
- **Scoped Generator** gets in-scope bodies, imports, other signatures only. A8 (scope) and A9 (locked
  signature) are new Layer A checks in `da_build_checks.py`.
- **Expected-to-change** tests are left out of Layer B and run once for information after it passes.
- **Roles (WF-7):** the today-draft uses a role setting named in one place (`TODAY_ROLE = "generator"`),
  nothing hard-coded elsewhere. The safety net uses the Tester role (WF-6).
- **Browser reads** (9-48): the existing read path is told to accept confirmed targets before a plan
  exists. Nothing is written by Find, freshness, impact or the net.
- **No new library.** `ast`, `fnmatch`, `difflib` are standard library.
- **Not touched:** WF-1 to WF-8 stay open; the plan builds the placeholders named in spec section 18.

## Steps

1. **Plan, models, policy, catalog.** Update CLAUDE.md "Current phase". `pydantic_classes/da_enhance_models.py`
   (`TodayDraft`, `SafetyNet`, `SafetyCase`, `ImpactRow`, `FreshnessResult`, `EnhanceState`,
   `Candidate`). Record fields in `da_request_record_models.py` (kind, targets, today, `NC-n` items,
   functions in scope, capability, senior, freshness). `Capability` part and 8 `Policy` fields with
   defaults in `da_rulebook_models.py`; seed JSON with 3 made-up capabilities. Settings
   `DA_MAIN_SOURCE`, `DA_FAKE_MAIN_DIR` in `da_config.py` and `.env.example`. Tests 9-22, 9-47.
2. **Plain rules A (`agents/da_enhance_checks.py`): find.** Name scoring and Best match (stem and
   symbol), merge by path, safety filter use, catalog lookup (first match wins), target validation
   (allowed folders, `.py`, `max_files`), switch-offer decision (only on Best match), functions-in-scope
   filter (refuse unknown symbols, at least one), NC numbering never reusing an ID, find round cap.
   Tests 9-2 (pure part), 9-5, 9-6, 9-7, 9-8, 9-10, 9-11, 9-21.
3. **Main source and freshness rules (`agents/da_main_source.py`, freshness part of checks).** Fake and
   placeholder providers, fingerprint compare (line endings and BOM equal), results: equal, differs,
   not on main, missing in folder, unreachable. Made-up files: `src/data/da_fake_main/` and a small
   made-up package under `src/data/` (target plus two callers). Tests 9-12, 9-13, 9-16 (pure part).
4. **Impact (`agents/da_impact.py`).** `ast` walk: Direct (imported name, module alias), Possible
   (method by name), Imports only, target skipped, cap with "and N more", capability and zone of caller,
   fixed limits line, signature-lock list. Tests 9-23, 9-24, 9-25 (pure part), 9-26 (pure part).
5. **Safety-net rules.** Reply checks (real in-scope function, real NC and AC IDs, method-to-case
   mapping, max tests), not-covered builder (plain code adds every unproven function and NC item),
   proof result merge, drop after attempts, frozen test-file building with expected-to-change marks.
   Tests 9-28 (pure part), 9-33, 9-37 (pure part).
6. **Build checks.** A8 scope check (inside, outside, insert-after) and A9 locked signature in
   `da_build_checks.py`; test-set rule leaving expected-to-change out of Layer B; failure report
   wording naming S-n and NC; Layer C check 1 NC line and FYI. Tests 9-39, 9-40, 9-41 (pure),
   9-43 (pure), 9-42 (pure labels).
7. **Storage (`db_table_functions/db_tbl_da_enhance.py`).** 5 tables (state, candidates, freshness
   checks, safety nets, unassigned files), `list_unassigned()`, one open row per path, guarded
   `impact` column on `da_discovery_results` (`ALTER TABLE` guard, old DB tested), safety-net
   markers on `da_test_sets`, `ensure_*_tables` wiring. Tests 9-9 (storage part), 9-46 (revision).
8. **Prompts and AI calls.** `data/da_today_prompt.md`, `da_safety_net_prompt.md`,
   `da_safety_net_fix_prompt.md`; `agents/da_enhance_agent.py` (today draft, safety net, fix, correct)
   with attempts and unusable handling; fake script and pretend-server answers; test-only switches
   (case keeps failing, edit outside scope, signature change, main unreachable). Prompt tests 9-18
   (prompt part), 9-19, 9-27 (prompt part), 9-29, 9-38.
9. **Find and freshness flow (`agents/da_enhance_flow.py`).** Card 2 start, switch offer (switch and
   decline), search, pick, This is a fix, capability pick with Unassigned row, confirm, freshness run,
   `e_stale` buttons (check again, intentional, continue without check), baseline save. Audit events.
   Tests 9-1, 9-3, 9-4, 9-9, 9-14, 9-15, 9-16, 9-17, 9-49.
10. **Understand in enhance mode.** Today-draft call, new form boxes, NC items, functions-in-scope
    checkpoint, record save, revision-mode NC numbering. Edit `da_understand_flow.py` surgically.
    Tests 9-18, 9-20, 9-21 (flow), 9-22.
11. **Discover with impact.** Extra queries (targets, symbols) within the cap, impact stored with the
    round, `zones_touched` reason, reference-copy-unavailable path. Tests 9-23 to 9-26 (flow).
12. **Safety-net flow.** Write, check, proof in sandbox, fix calls, drop, not-covered, review actions
    (Continue, Correct something, mark change), accepted state, F2 parallel count, restart recovery.
    Tests 9-27, 9-28, 9-30, 9-31, 9-32, 9-33, 9-35.
13. **Approach and gate.** Approach gets targets, scope, impact and case list; target `modify`; test plan
    shows net read-only; gate check 4 needs `safety_net_accepted`. Tests 9-36, 9-9 file plan line.
14. **Build integration.** Scoped Generator prompt, A8 and A9 wired, frozen set with net methods,
    expected-to-change info run after Layer B, Layer C NC line wired. Tests 9-37, 9-38, 9-39 to 9-43.
15. **Refine and Get help.** Requirement lane re-marks AC links only, net extended for new NC items
    against baseline, bug and approach lanes unchanged, Get help at each step, stale refusal on every
    action. Tests 9-44, 9-45, 9-46.
16. **Screen.** Card 2 active, candidate table, freshness banner, enhancement summary, impact card,
    Safety net tab, test plan section, header pill labels, composer for each step, callbacks wired
    in the same step (rule R12). `web/da_workspace.js` target read. Tests 9-1, 9-34, 9-48.
17. **Smoke, docs, Playwright.** `da_smoke_check.py` (card 2 to READY_FOR_REVIEW, then a card 1 switch
    offer), `docs/enhance-work-test.md` (Command Prompt only), README, CLAUDE.md. Playwright 9-50
    written, skipped when no browser (cloud only).
18. **Full run, code review (max 3 rounds), push to `auto/phase-9`, stop.** Gian's home check on
    `127.0.0.1:8050` is named in the final report.

Steps may be split (a, b) when a step grows past what one commit can test; the split is noted here.

### Code review round 1 (4 Must fix) and the fix steps (added 11 Nov)
The engine is fine; the screen is not wired (same kind of gap as Phase 8 round 1). Fix steps, each with
a click-through style test that calls the callback, not the engine:
- 18a. Card 1 switch: `switch_to_enhance` must drop or reset card 1's Understand session so
  `start_understand` works (test: switch to `e_fresh` to `start_understand`). Add the two buttons
  "Switch to Enhance or fix" and "No, this is new" with callbacks.
- 18b. Safety net wiring: start `run_safety_net` in the background after Discover confirm, buttons
  Continue to Approach, Correct something (text), Try again, Get help, the mark dropdown; call
  `recover_interrupted_safety_nets` at server start.
- 18c. Render `impact_card`, `safety_net_tab`, `test_plan_net_section`, `pill_text`; route the `s_*`
  steps to a screen. Functions-in-scope tick list wired to `set_functions_in_scope`.
- 18d. Should fix: multi-tick of candidates with "Show other matches"; README known-gap text; re-run
  full pytest, ruff, smoke; code review round 2.

## Plan review 1 (0 Must fix) and what I take from it
- Pre-split: 9a (start, switch offer, search, pick, fix, capability), 9b (confirm, freshness run, stale
  buttons, baseline, server-side list of paths the browser may read: targets before Approach, planned
  files after; test for 9-48 read list lives here). 12a (write, check, fix calls, drop), 12b (proof in
  sandbox, review actions, accept, restart recovery). 14a (scoped Generator prompt, A8, A9 wired, frozen
  set), 14b (expected-to-change info run, Layer C line, freshness re-check at the first workspace check:
  a `modify` file whose `main` version changed since Find shows the `e_stale` banner again, working with
  the Phase 6 pre-build re-scan). 16a (card 2, candidate table, freshness banner, enhancement summary),
  16b (impact card, Safety net tab, test plan section, header pill), 16c (composer, callbacks, JS).
- 9-2 flow test: the switch-offer hook is a call in `da_understand_flow.py` after the card 1 form
  submit (step 9a); the test asserts the offer shows with the path and the fake client got no call.
- Step 8 adds a test that the safety-net call and the criterion calls are built from separate inputs.
- Q-c is settled: pre-Understand status is `STATUS_DRAFT` (`ALLOWED_MOVES` allows DRAFT to CLARIFICATION);
  step 1 adds a check that the `e_*` steps work with it.
- Step 13 done (cd52d73). Step 14a done (b46a156): `frozen_set_with_net`, `scoped_view` in
  `da_enhance_build_checks.py`; the build loop freezes the net as test set version 1, shows the scoped
  view, runs A8 in `_write_file` and A9 in `_layer_a`. New split **14c** (after 14b): scripted fake
  build replies for the made-up target (contract, criterion tests, edit blocks, plus switches
  `edit_outside_scope` and `signature_change`) so a full enhance build runs end to end with the fake
  provider. Without 14c the loop wiring of 14a is covered only by pure tests, and the smoke check
  (step 17) cannot build a card 2 request.
- Q-a: the spec header edit is Gian's (the builder does not change an approved spec).

## Open questions (decided in the plan, Gian can change)
- Q-a: the spec file header still says "DRAFT v0.1, not yet approved" though the chief records v1.0
  approved. The plan follows the chief. Gian may want the header updated.
- Q-b: today-draft uses the Generator role (WF-7 a); one setting to change.
- Q-c: pre-Understand status is `STATUS_DRAFT` unless step 1 finds a better existing one.
- Q-d: the Unassigned queue assumes one database (Q2, as Phase 8).
