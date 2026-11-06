# Phase 6 fixes batch (work test 6 Nov 2026)

Version 1.0, APPROVED by Gian 6 Nov 2026. Build on branch `phase-6`, before `phase-6` is merged.
Source: Gian's FAKE and ONPREM work tests on 6 Nov, reviewed item by item in the project chat.
All decisions below are made. If anything is unclear or clashes with an earlier spec, STOP and ask
(house rules). This file wins over older specs for the items it names.

Item IDs: F = found in the FAKE test, O = found in the ONPREM test, T = test code only.

## 1. Understand: 4-box form first, AI questions after (O2, O3, O4, O1)

**Today:** after the opening statement the app asks the 4 mandatory questions one at a time, and
after every answer it asks any waiting AI clarifying question (material decision) BEFORE the next
mandatory question. A vague opening ("I need an Excel ingestion module") used all 5 AI questions
before mandatory question 1, then hit the "many open decisions" stop at question 2. Each Qwen reply
takes 10 to 20 s.

**Change:**
- U1. Right after the opening statement, show ONE form: the 4 mandatory questions as 4 labelled
  boxes (their current wording), plus the optional area (constraints, exclusions, references) as a
  5th box that may stay empty (replaces the Skip button). One Submit button.
- U2. The existing answer checks still apply to each box. A box that fails shows its message under
  that box; the form stays filled in.
- U3. AI calls: at most ONE interpreter call between the opening statement and the first AI
  question (or the checkpoint, if there are none). That call sees the opening statement and all
  form answers together.
- U4. AI clarifying questions are asked only AFTER the form, one at a time, as today (buttons plus
  type your own). Only questions that are still open after the form answers are asked.
- U5. Duplicate guard: each interpreter call is told which decisions are already made and which
  questions are already queued, and must return only NEW ones. Keep the exact-text check as a
  second guard.
- U6. Move the limit `MAX_MATERIAL_DECISIONS = 5` into the rulebook policy as
  `max_material_decisions` (default 5, allowed 1 to 10, same pattern as `max_files`; older rulebook
  versions must still load). The stop at the limit stays as it is.
- U7. Remove the chat line "Noted as a confirmed decision." in Understand AND Approach
  (`da_understand_flow.py`, `da_approach_flow.py`). The right panel already shows the change.
- U8. Summary tab: after Submit, all fields the form answered are revealed at once (replaces the
  one-by-one reveal for the 4 questions). Progress bar segments still make sense.
- Old saved requests in the middle of the one-at-a-time questions must still open and finish (they
  may finish the old way). Say in the plan how.

**Done when (tests):** a fake run with a vague opening reaches the checkpoint with the 4 questions
answered first; the AI question count is read from the policy; a duplicate AI question is not asked
twice; "Noted as a confirmed decision." appears nowhere; one interpreter call per Submit.

## 2. Typing is the "correct / change / add" path (F2, F5)

**Today:** checkpoints show a "Correct something" style button that then opens the text box. Discover
already works the new way (buttons "Findings look right" and "Escalate", Send = "Something's
missing").

**Change:** at these 3 steps the text box is open and the Send button carries the action name:

| Step | Buttons | Send button label (typing + Send means) |
|---|---|---|
| Understand checkpoint | Proceed with this understanding, I need help deciding | Correct something |
| Approach review | Accept approach, Get help | Change something |
| Test plan | Accept test plan, Go back and change the approach, Get help | Add a test case |

- Remove the old "Correct something", "Change something" and "Add a test case" buttons.
- Placeholder text in the box says what typing does, for example "Type what should change, then
  press Correct something."
- Approach change limit (3): when reached, the box is disabled and shows the existing cap message.
- F5: at the test plan step, "Change the approach" stays but is renamed "Go back and change the
  approach" and drawn as a secondary (outline) button, not a main one.
- Discover is not changed.

**Done when:** tests for each of the 3 steps: Send runs the action, empty text does nothing, the
capped box is disabled, the old buttons are gone.

## 3. Start the next step automatically (F3)

- After "Proceed with this understanding" succeeds, Discover starts by itself. No "Proceed to
  Discovery" click.
- After "Findings look right", Approach starts by itself. No "Proceed to Approach" click.
- If the started step's AI call fails, show a "Try again" button for that step (as Approach already
  does on failure). That is the only time a start button appears.
- Remove the chat hints "Press Proceed to Discovery..." and "Press Proceed to Approach...".
- The Build button is NOT changed: the developer still presses Build himself (Gian's decision).

**Done when:** tests show one click goes from checkpoint to Discover results, and from findings to
the approach; a failing AI call shows Try again.

## 4. Design choice buttons look equal (F4)

**Today:** the first design-choice option is drawn as the primary (dark) button only because it is
first (`number == 0` in `da_developer_assistant_page.py`).

**Change:** all options of a design choice use the normal (light) style. Primary style stays for
real main actions (Accept approach, Accept test plan, Proceed with this understanding, Build).

## 5. Workspace wording and buttons (F6, F7, F8)

- F6. "I cannot use this folder yet" becomes "This folder doesn't match the plan yet:".
  Offer "Change the approach" only when a blocker is about a planned file (B3, B4, B5, B6). For
  B1 and B2 (wrong folder, picked `src`) offer only "Choose another folder" and "Get help".
- F7. Hide the manual "Re-scan" button at Ready to build and during the Build step (Build already
  re-scans by itself and stops on a change). There is no working Re-scan after a build in Phase 6
  (that is Phase 8, Refine), so also remove "then click Re-scan" from the Build tab "Your turn"
  text. Phase 8 brings Re-scan back after a build.
- F8. The folder button label "Change" becomes "Change folder" (`CHANGE_FOLDER_LABEL`). The
  New/Change action column in file tables stays as it is.

## 6. Build messages that tell the truth (F9a to F9c, O7)

What happened at work: the practice file did not match the fake plan, so Layer A failed in all 3
rounds, Layer B never ran, and the screen was confusing.

- F9a. When tests never ran in the last round, the final chat line must not say "0 test(s) still
  fail". Say: "The code checks failed in every round, so the tests never ran. Result: Not passing.
  ..." (keep the rest of the current sentence). When tests did run, keep today's wording.
- F9b. Tests tab: when a frozen test has no result, show one line above the table: "Not run: the
  code checks (Layer A) failed first. See the Build tab."
- F9c. Bug: the chat header badge "No code is written yet" stayed after the files were written
  (photo, NOT PASSING with 2 files Written). The badge must follow the real write state.
- O7. Rename "Try again" to "Resume build" and "Stop build" to "Cancel build" in the Build step.
  The cancel message keeps "Nothing was written to your folder" and adds "The record of this build
  stays in the Audit tab."

**Done when:** tests for each wording, and a test that the badge changes after a write.

## 7. Discovery: say when the index is made up (O5)

`DA_SEARCH_PROVIDER` defaults to `fake`, also when the AI is on-prem, so Discovery at work showed
made-up pieces (`fake-index-001`). Add a clear banner on the Discovery tab and in the Discover chat
message when the fake index is used: "Practice index (made-up code), not CodeVision." No other
change (the real adapter, P15, is a later item).

## 8. Docs (F9d, O6)

- F9d. `docs/workspace-work-test.md` and `docs/build-work-test.md`: give the ONE exact line that
  creates `upload_validator.py`, a step that shows its content (`type ...` must print
  `def validate(path): return True`), and a warning that a build writes into the practice folder,
  so the file must be recreated (and `excel_processor.py` deleted) before another run.
- O6. `docs/build-work-test.md`: make clear that the FAKE build needs NO `DA_SANDBOX_SOURCE_DIR`,
  and the ONPREM build needs it set to the folder that CONTAINS `src` (for example
  `C:\Users\<you>\Desktop\codevision`), then restart the app and press Resume build.
- All work instructions use Command Prompt, never PowerShell or DevTools.

## 9. Test code only (T1)

`tests/test_da_sandbox.py` `is_alive` uses `os.kill(pid, 0)` when `/proc` is missing. On Windows
signal 0 is CTRL_C_EVENT, so the test sends Ctrl+C to pytest itself (`KeyboardInterrupt` at test
821 on Gian's home laptop). Make `is_alive` Windows-safe using the standard library only (for
example `tasklist /FI "PID eq <pid>"`, or `ctypes` OpenProcess), so the full suite runs on Windows.
Do not touch app code for this.

## 9a. Answers to the 3 open decisions in the Phase 6 build report

1. P26 (plan item P19), "different folder, same name" check: CONFIRMED as built. It applies when a
   folder is already linked and the developer picks through Choose; Change links on purpose and is
   also shown at `start`. (The button is now called "Change folder", item F8.)
2. "Edit anything, then click Re-scan" on the Build tab: remove it (see F7). Keep "Try it
   yourself: start CodeVision on your laptop and test the change by hand." and "Tell me if a
   requirement is missing."
3. Approach tab line about `tests/<id>/` from Phase 4: remove it. Since Q11, test files are never
   written to the workspace, so the line is wrong.

## 10. Not in this batch (decided)

- F1 lock the chat after "I need help deciding" until a senior unlocks: Phase 10 (with the
  escalations inbox), for all 3 help buttons.
- Freshness check against Bitbucket main: Phase 9.
- Real search adapter (P15), P26, P28: later.
- Raising the 5 AI question limit: no; only moved to the policy (U6).

## 11. Finish

- Update "Current phase" in CLAUDE.md to point at this file as well.
- Full `pytest`, `ruff check .` and the smoke check, results pasted. Plan review and code review as
  the house rules say.
- Gian's home check list (write it in the final report): vague opening reaches the 4-box form; one
  click to Discover and to Approach; Send labels at the 3 steps; equal design-choice buttons;
  "Change folder"; no Re-scan before Build; fake build ends Ready for review; full pytest on
  Windows finishes without `KeyboardInterrupt`.
