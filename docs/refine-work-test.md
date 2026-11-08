# Refine: live test at work (Phase 8)

Why: at home the AI calls of Refine (lane suggestion, record changes, repro test) are answered by a
script. Only the work server and the real models show whether the lane suggestions are sensible
and whether a repro test really fails on the old code.

**PowerShell and the browser DevTools are blocked on the work laptop, so every step uses Command
Prompt (`cmd`) and the app itself.** Use made-up requests. No real code in a photo.

AS400 picture: Refine is like changing a program after the first compile. Your own edits are like
a PTF-style local fix: the tool keeps them, tells you where it would clash, and never overwrites
them without your pick.

## Before you start

1. Open **Command Prompt** and go to the Developer Assistant folder.
2. Run the smoke check first: `.venv\Scripts\python src\da_smoke_check.py`. Items 27 (bug lane)
   and 28 (requirement lane) must print, then `Smoke check passed.`
3. Do one full request up to **The code files are in your folder** (a made-up one).

## Test 1: protect my edit (no AI call)

1. Open one written file in your folder. Change one line. Save.
2. In the app press **Re-scan**. The file shows as **Changed by you**, side by side.
3. Press **Check my edits**. The sandbox runs the frozen tests on your version.
4. Write down: did the label change, and is your line still in the file?

## Test 2: the bug lane

1. Type a short bug, for example: "The upload check says yes to a file it should reject."
2. Press **Refine**. Note the lane the assistant suggests. You decide; pick **Bug**.
3. The assistant writes one test and runs it on the OLD code. It must **fail** (that proves the
   bug). Note the failure text. Press **Yes, this is the bug**.
4. Watch the fix build. Afterwards check: is your edited line from Test 1 still there?

## Test 3: the requirement lane

1. Type: "Also reject files over 5 MB."
2. Pick **Requirement**. Read the diff of the request record (v2). Press **Confirm v2**.
3. Discover runs by itself, then a new Approach. Only new and changed criteria get new test cases.
4. Note any file the old plan had that the new one dropped ("no longer in the plan").

## What to write down for Claude

| What | Where |
|---|---|
| Was the suggested lane right? (3 tries) | Chat line after Refine |
| Did the repro test fail on the old code? | Bug lane confirm step |
| Did the Tester model write a test that imports the right module? | The shown test |
| Did the rebuild touch only the traced file? | Build tab, Written files |
| Was your edit kept? | Your folder |

Rounds and tries are limited (rulebook policy: `refine_repro_max_attempts`, the Refine cap). Reaching
a cap stops the text box but **Re-scan** and **Check my edits** keep working.

## Known gap (home build)

The Refine buttons are drawn on the page, but their click callbacks are not wired yet, so the
steps above are checked at work only after those callbacks exist. The engine itself is covered by
the tests and the smoke check.
