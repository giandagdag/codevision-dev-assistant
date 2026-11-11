# Phase 8 fix 1 plan

Spec: `specs/phase-8-fix-1.md` v1.1 (all D-x option 1, D-E option 2). Branch `phase-8-fix-1`,
built on top of Phase 9 (merge of `auto/phases-7-10` done by Gian, PR 49: this is step 0, done).
Each step: tests for it, `pytest`, `ruff check .`, commit, push. Runs build at most 3 steps, then
`chief_tick.py next "builder continue Phase 8 fix 1 from step K"`. Code review only after the last step.
Surgical: only files a fix needs. Phase 9 code is touched only where a fix reads or shows the same
thing (named per step). No new library, no new status, no database change (spec section 4).

## B6 plan (F10), cause first

No browser is installed here (the Refine browser test skips), so the cause is found by reading code
and the proof is written as a Playwright test that skips with no browser (like 7-35). Order of leads,
as the spec says: (1) the redraw replaces `dcc.Interval(id=da-build-poll)` (drawn `disabled=True` at
`b_written`, then `disabled=False`); (2) Refine bar path versus Build button path; (3) `poll_build`
refusing on falsy `n_intervals`. Step 1 writes down which lead it was before any fix. If the cause
cannot be shown in 2 attempts: stop and report to Gian (stop rule).

## Steps

1. **F10 / B6 + FX-1, FX-2.** Read both paths, name the cause in the commit message. Fix so the poll
   fires for every build kind. Add: a plain test that the page draws the Interval enabled for a running
   check run and a first build (component tree), and the Playwright tests FX-1 and FX-2 (skip with no
   browser). Files: `layouts/da_build_panel.py`, `layouts/da_developer_assistant_page.py`,
   `callbacks/.../da_developer_assistant_page_callbacks.py`, new `tests/test_da_poll_browser.py`.
2. **F6 words (FX-10) + F9 count (FX-11).** One constants place for the check-run words (pill TESTING,
   chat line, banner, Cancel test, This test run, Test run N). Screen-only: status stays BUILDING.
   Phase 9 reuses the constants. `_check_round` counts changed files only ("Testing n planned file(s)
   (m edited by you)", and "... with your new test" after `after_new_test`).
   Files: `agents/da_build_flow.py`, `agents/da_build_loop.py`, `layouts/da_build_panel.py`, a constants file.
3. **F8 order (FX-13) + F5 Restore / Undo my edits (FX-8, FX-9).** Refine bar order: Re-scan, Check my
   edits, Restore (or Undo my edits), Get help. Greyed Restore with the "Nothing to restore yet" line;
   Undo offered when a re-scan found untested edits, same restore write and warning; the server guard
   text stays. Files: `agents/da_refine_edit.py` (`open_restore`), `layouts/da_refine_panels.py`.
4. **F1 pending test row (FX-3) + F1b VAGUE (FX-4).** The Tests table reads the pending case from the
   Refine state (`own_confirm`, `own_fails`); nothing stored. Own-test Tester reply `VAGUE` + question
   (max 200 chars): "Describe the case more: ...", nothing run or stored, no case ID used; fake script
   `vague` switch. Files: `layouts/da_tester_panel.py`, `agents/da_refine_owntest.py`, fake script.
5. **F7 Tests tab layout (FX-12).** Findings table to 5 columns: ID nowrap, Where `overflow-wrap:
   anywhere`, check number and Cites under the message as one dimmed line. Layout test on the tree.
   Files: `layouts/da_tester_panel.py`, `styles/`.
6. **F2 draft before Confirm (FX-5, FX-6) + F3 tab mapping.** Chat diff lists added/changed/removed
   criteria with full Given/When/Then; Summary tab shows draft v(N+1) with the three tags; the right
   panel opens on Summary. One small step-to-tab mapping in the page code, applied only when the step
   changes (a tab he picked stays during the same step; the poll redraw keeps it). Check the Phase 9
   enhance request still works with the mapping. Files: `layouts/da_refine_panels.py`
   (`version_history_blocks` or a sibling), `layouts/da_developer_assistant_page.py`, Refine chat text.
7. **F4 Discover buttons after a revision (FX-7).** The three Phase 3 buttons at `req_findings`, reuse
   the Phase 3 handlers and round cap; Escalate -> ESCALATION_REQUIRED, open item `Escalated in Refine:
   Discover`, audit as Phase 3. Files: `agents/da_refine_hooks.py`, discover layout/callbacks.
8. **Finish.** Full `pytest`, `ruff check .`, smoke check, README/known-gap lines if the screen text
   changed, code review (max 3 rounds), STATUS/worker note.

Plan review (round 1): 0 Must fix, approved. Should fix taken in:
- B6: a fix is "done" only if a component-tree test fails before it and passes after. If the cause is
  only a guess, stop and report to Gian; never call an unproven fix done.
- Tests per step: 3 = FX-8, FX-9, FX-13 (tree and engine tests); 4 = FX-3, FX-4; 6 = FX-5, FX-6 plus a
  Phase 9 enhance request still drawing; 7 = FX-7 with tests for the round cap, the audit event and
  the open item (Escalate allowed from the status the request has at `req_findings`; name the exact
  Discover files when reading them in step 7).
- Step 4 also touches the own-test Tester prompt and reply parser (VAGUE, 200 character cap).
- Step 2 rule for `m`: files whose scanned fingerprint differs from the last written one (FX-11 test:
  2 planned files, 1 edited). Phase 9 reads the new constants only if it shows check-run words (none
  known; confirm by Grep in step 2).

Known limit: B6 cannot be reproduced without a browser here. The FX-1/FX-2 tests skip; Gian's check at
127.0.0.1:8050 is the final proof (same as Phase 8, plan decision P16).
