# Independent Tester: live test at work (Phase 7, questions Q9 and Q7)

Why: at home the Tester review is answered by a script (the fake AI). Only the work server and the
real models can answer two open questions:

- **Q9** Which model should be the Tester at work: `default` (Llama-4-Maverick) or `reasoning-vlm`
  (Qwen3.6)? (Issue #20.)
- **Q7** How big can the Tester's input be before the server answers HTTP 400? (Issue #21.)

**PowerShell and the browser DevTools are blocked on the work laptop, so every step uses Command
Prompt (`cmd`) and the app itself.** Nothing here needs real code in a photo. Use made-up requests.

## Part 1: set the Tester model (a setting, never hard-coded)

1. Open **Command Prompt** and go to the Developer Assistant folder.
2. Open the `.env` file in Notepad (`notepad .env`). Set, for the model you want to try:

```
DA_ONPREM_TESTER_MODEL=default
```

   Empty means "use the same model as the Generator". Save, then restart CodeVision.
3. The model name each review used is shown on the **Tests** tab ("Reviewed by ...") and in the
   **This build** box, so you can see what really ran.

## Part 2: the bake-off (Q9)

Use the same 3 made-up sample requests for each model. For example:

1. "Reject an upload when the sheet is empty."
2. "Add a size limit to the upload check."
3. "Show the row count after the upload."

For each model (set it as in Part 1, restart), for each sample request, do a full build and then
write down on a sheet of paper:

| What to note | Where to look |
|---|---|
| The label | Banner on the Tests tab |
| Findings kept, by severity | Findings table |
| Findings dropped | "N Tester findings were dropped" line, then **Show dropped** |
| Calls (more than 1 means the review was split file by file) | "in N call(s)" line |
| Seconds the review took | Build tab, the Layer C progress line |
| Were the kept findings real? | Read each one against the code |

Good Tester: few dropped findings, no invented Must fix, a review that finishes in one go. A model
that over-uses **Must fix** burns the 3 rounds; a model whose findings are mostly dropped needs a
bigger `tester_quote_window` (a rulebook policy value).

Write the results in the chat with Claude. Gian decides the model.

## Part 3: how big is too big (Q7)

1. Pick the biggest change you have (many planned files, long files). Build it.
2. If the Layer C progress line says **Reviewed file by file (N calls)**, the review was split
   because the input was over `tester_max_prompt_chars` (60000 characters, a made-up starter value).
3. If the build pauses with "This change is too big for the Tester to review in one go.", one file
   alone was too big for the server. Write down which file and roughly how many lines.
4. Ask the CodeVision team the context limit (in tokens) for each model. Rough rule: 3 characters
   per token, minus room for the reply. Claude then sets `tester_max_prompt_chars` per model.

## Part 4: other things to try

- **Unable to assess.** If the label is **Unable to assess** (grey), press **Run the Tester review
  again**. It makes a new review of the same round and uses no round.
- **Accept a Should fix.** Type a reason of 10 to 300 characters and press **Accept, with reason**.
  The label turns green when no Should fix and no flag-for-review zone is left. **Reopen** undoes it.
- **Dispute a Must fix.** The request goes to a senior (the inbox itself comes in Phase 10).
- **The report stays in the app.** Check your folder: no report and no test file is written there.

## What the home build looks like (so you can compare)

At home the fake Tester follows a fixed script: round 1 the tests fail, round 2 the Tester finds
1 Must fix, round 3 passes with 1 Should fix and 1 FYI (yellow). At work the real model decides, so
your build will look different. That is the point of this test.
