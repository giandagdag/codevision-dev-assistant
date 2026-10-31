# Phase 2D plan

Spec: `specs/phase-2d-understand-updates.md` (APPROVED v1.0). Branch: `claude/sweet-babbage-osne6q`
(the session's branch; it starts at the same commit as `main`, so it plays the role of `phase-2d`).

Every step ends with its tests, then `pytest`, `ruff`. Step 1 is the failing-test-first step (W4).

| Step | What | Proof (test) |
|---|---|---|
| 1 | **W4.** Write the failing test first: reply pushes the 6th material ambiguity, nothing pending, so the senior message must be in the chat once (2D-9) and once after the last decision when 2 decisions are pending (2D-10). Run it, show it fails with 2 copies and say why (`_apply_result` and `_advance` both say it). Then fix: say it only in `_advance`, only when the step changes to `senior`. | 2D-9, 2D-10 |
| 2 | **P13.** `parse_reply` parses the text as it is first; only on failure strip a leading think block (first `</think>`) or a lone closing tag, then parse again. `strip_think_block` becomes non-greedy and leading-only. | 2D-13, 2D-14, old think tests updated |
| 3 | **Model.** `AcceptanceCriterion` (id, kind, given, when, then) on the record, replacing `success_scenarios` and `failure_scenarios`. `InterpreterReply.acceptance_criteria` (optional, no ids). `build_candidate` renumbers `AC-1..n` when the reply gives the list; absent or null keeps it. Labels updated. | 2D-1, 2D-3 |
| 4 | **Checks.** Kind, 1 to 300 characters per part, max 12, observable "then" (fewer than 3 words or the vague list), duplicates, code and invented-name checks on all three parts. Gate lines "At least 1 success/failure criterion is needed." | 2D-2, 2D-4 |
| 5 | **Prompt and fake script.** New prompt section and reply shape. Fake script: `question_4` has 6 criteria, new `decision` entry adds the hidden-sheet criterion (third) and puts hidden sheets out of scope, 7 criteria at the checkpoint. | 2D-15 (part) |
| 6 | **Old saved requests.** A session or record that still holds the scenario fields raises a plain `UnderstandError` ("Request ... was saved before the Understand update (2D) and cannot be opened. Please start a new request."). The page already shows `UnderstandError` as a plain message; "My recent requests" reads only the request table so it still lists it. Nothing deleted. | 2D-5 |
| 7 | **W3 and D-C.** At a decision step a typed answer (checks as any message, max 300 characters) is saved as the choice with `"custom": true` in the `decision_recorded` audit event. After any decision except "I need help deciding": save 1 records it, interpreter called once with no lock (question = decision question, answer = choice, step name `decision`), save 2 applies the reply and moves on. AI failure keeps the decision and says the "will be picked up" message. New material ambiguities are queued as usual. `submit_answer` routes a decision-step text to this path so the page callback stays thin. `UnderstandView.custom_choice_allowed` opens the text box with "Other, type here". | 2D-6, 2D-7, 2D-8 |
| 8 | **W5.** `visible_fields` on `UnderstandView`, plain code in the flow module, by the table in spec section 4. Newly visible fields with a value are added to the changed fields, so they are highlighted. The page shows "Waiting for your answer" for hidden fields. | 2D-11, 2D-12 |
| 9 | **Screen.** Summary section "Acceptance criteria (each one gets tested)" under "Requirement summary": ID badge, "failure" tag, empty text. Confirmed message gets "Acceptance criteria: N". Question 4 gets the app hint. | page tests |
| 10 | **Smoke check and README.** Smoke check: full fake run reaches CONFIRMED_FOR_DISCOVERY with 7 criteria; new item for W5 (after question 1 only objective and reason visible). README scenario wording. | 2D-15 |
| 11 | Run `pytest`, `ruff`, smoke check. Ask `code-reviewer` (max 3 rounds). Commit and push. | |

## Things I will do that the spec leaves open (flagged for review)
- State between save 1 and save 2 of a decision: if no decision is left waiting, save 1 parks the
  session at the `correction` step (a valid text step), so a crash between the saves leaves a
  usable request. Save 2 always sets the real next step.
- A typed answer equal to a button label counts as that button (not `custom`).
- `acceptance_criteria` inside `updates` is refused like any unknown field.
- A stray `id` key inside a reply criterion is refused as a wrong shape ("no IDs from the AI").
- The Summary panel has no "Decisions" or "Constraints" section today; I do not add one (not in
  the spec). `visible_fields` still lists them as the spec table says.

## Not touched
Discover, status list, database tables, revision mode, stable IDs (spec section 7).
