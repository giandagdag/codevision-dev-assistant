# Enhance: live test at work (Phase 9)

Why: at home the AI calls of Enhance (the today-draft, the safety net and its repairs) are answered
by a script, and "main" is a made-up folder. Only the work server, the real models and the real
Bitbucket main show whether the net really describes today's behaviour and whether the freshness
check is trustworthy.

**PowerShell and the browser DevTools are blocked on the work laptop, so every step uses Command
Prompt (`cmd`) and the app itself.** Use a made-up change on a small, harmless program. No real code
in a photo.

AS400 picture: Enhance is changing a live RPG program. You first check your copy matches the
production library, write down what it does today, and promise the tests that today's behaviour
stays.

## Before you start

1. Open **Command Prompt** and go to the Developer Assistant folder.
2. Run the smoke check: `.venv\Scripts\python src\da_smoke_check.py`. Items 29 (card 2 to
   READY_FOR_REVIEW) and 30 (the card 1 switch offer) must print, then `Smoke check passed.`
3. Open questions WF-1 to WF-8 in `specs/phase-9-enhance.md` still need your answers: the Bitbucket
   main source (WF-1), the capability catalog (WF-2), the roles (WF-6, WF-7).

## Test 1: find (no AI call)

1. Press card 2, **Change an existing program**.
2. Type the program name. Check: is it listed, is **Best match** on the right one, is its capability
   right? Then type a description of it instead, and note whether the right program is in the list.
3. Pick a program that is not in the catalog. You must pick a capability for it.

## Test 2: freshness

1. Pick the program, press **Choose workspace folder** and then **Check against main**.
2. A program equal to main goes on. Edit one line in your copy, save, check again: the app must stop
   and say what differs. Test **My local changes are intentional**.
3. Write down: did the check reach the real main, or say "not configured"?

## Test 3: understand and the safety net

1. Read the today-draft. Is it right about what the program does? Tick the functions in scope.
2. Fill the boxes, including two "must NOT change" lines.
3. Read the safety net: one sentence per test. Do they describe today's behaviour? Look at the
   **Not covered** list and the **Impact** card (who calls the functions).

## Test 4: build

1. Accept the net, the approach and the test plan, then build.
2. Afterwards check in your folder: only the functions in scope changed; every other function is the
   same.
3. If an edit outside the scope, or a changed signature, is rejected, the failure report must name
   the rule (A8 or A9).

## What to write down for Claude

| What | Where |
|---|---|
| Was the Best match right? (3 tries) | Candidate table |
| Did the freshness check reach main? | Banner |
| Was the today-draft right? | Understand form |
| Did the net's tests describe today's code? | Safety net tab |
| Did the build touch only the functions in scope? | Your folder |

Rounds and tries are limited (rulebook policy: `enhance_find_max_rounds`, `safety_net_max_attempts`).
