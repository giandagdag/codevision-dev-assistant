# Build and test: live test at work (Phase 6, questions Q7, Q14, Q15)

Why: at home the build runs against a made-up folder and a pretend AI. Only the work server and the
real Qwen can answer the open questions below. **PowerShell and the browser DevTools are blocked on
the work laptop, so every step uses Command Prompt (`cmd`) and the app itself.** Nothing here needs
real code in a photo: cover names and paths first, or just write the answers.

## Part 1: questions for the CodeVision team (no tool needed)

These set how the sandbox is wired. Ask them, write the answers in the chat with Claude.

- **Q14 (b)** Which folder holds the deployed CodeVision source on the OCP server (the folder that
  contains `src`)? How close is it to Bitbucket `main`? This becomes `DA_SANDBOX_SOURCE_DIR`.
- **Q14 (c)** Does importing any CodeVision module connect to a database, the LLM or a file share
  at import time? (The sandbox copies the source and imports it to run the tests.)
- **Q14 (d)** Can child processes started by CodeVision be blocked from the network, or limited in
  memory? (The sandbox is a separate process with a time limit and no secrets, but it does not do
  either of these by itself.)
- **Q14 (e)** Does CodeVision run as **one copy** or **several copies** on OCP, and do the copies
  share one database? (If several: tell Claude **before** Phase 6 is trusted. The progress poll
  could reach a copy that is not running your build, and the "2 builds at once" limit counts per
  copy.)

## Part 2: how CodeVision starts on your laptop (Q15)

This decides the sandbox's working folder and how the test file imports CodeVision modules.

1. Open **Command Prompt** and go to your CodeVision folder, for example:

```
cd %USERPROFILE%\Desktop\codevision
dir
```

2. How do you start CodeVision on your laptop? Write down the exact command and the folder you run
   it from (for example `cd src` then `python web_server.py`).
3. Open any one module that imports another CodeVision module. In Command Prompt:

```
type src\callbacks\universal_callbacks.py | more
```

   Press the space bar to page; press `q` to stop. Write down only the import lines, for example
   `from web.web_components import ...`. Replace any real names with made-up ones before you
   share them.

## Part 3: Q7, the AI's context limit

Ask the CodeVision team: what is the largest prompt (in tokens) each model name accepts
(`reasoning-vlm` = Qwen, `default` = Llama)? Roughly 3 characters per token, minus room for the
reply, gives `build_max_prompt_chars` (starter value 60000). The app stops a build cleanly with
"This file is too big to send to the AI in one go." if a prompt is over the limit, and treats an
HTTP 400 reply the same way. Neither uses one of the 3 rounds.

## Part 4: try a build with the real AI (only after Parts 1 and 2 are answered)

Which AI decides whether you need a source folder:

- **FAKE build (`DA_LLM_PROVIDER=fake`): you do NOT set `DA_SANDBOX_SOURCE_DIR`.** The app uses its
  own made-up CodeVision folder for the sandbox. Leave the setting out.
- **ONPREM build (`DA_LLM_PROVIDER=onprem`): you MUST set `DA_SANDBOX_SOURCE_DIR`** to the folder
  that CONTAINS `src` (not `src` itself), for example `C:\Users\<you>\Desktop\codevision`.

1. For an ONPREM build, set it in `.env`. In Command Prompt, open the file in Notepad:

```
notepad .env
```

   Add the line `DA_SANDBOX_SOURCE_DIR=C:\Users\<you>\Desktop\codevision` (use your own folder
   from Q14 (b)), save, and close Notepad. Never commit `.env`. Then **restart the app** (stop it
   with Ctrl+C in its Command Prompt window and start it again). If a build already paused with
   "The sandbox could not start", reopen the request and press **Resume build**.
2. Use the **practice folder** from `docs/workspace-work-test.md` and a small made-up request.
   **A build writes into the practice folder**, so before a second run put the folder back as
   that document says: delete `src\agents\excel_processor.py` and run the one `echo` line again
   so `upload_validator.py` holds `def validate(path): return True`. Check it with
   `type C:\Dev\practice\src\agents\upload_validator.py`.
3. Press **Build**. Leave the page for a minute and come back from **My recent requests**.
4. Write down: how long each AI call took, whether round 1 passed, how many rounds were used, and
   whether the edit blocks matched the file (a miss shows "Edit block N did not match").
5. In Command Prompt check what the app wrote: `dir /s /b C:\Dev\practice`. Expected: the planned
   code files, and **no** `tests` folder (the tests stay on the Tests tab).

## If something goes wrong

- "The sandbox could not start" in the chat: the `DA_SANDBOX_SOURCE_DIR` folder is wrong or
  missing its `src` folder (it must be the folder that CONTAINS `src`). Fix `.env`, restart the
  app, press **Resume build**. (With the fake AI you do not set this at all.)
- The build pauses with "the AI did not answer": press **Resume build**. No round was used.
- The build ends "Not passing" and says "the tests never ran": the code checks (Layer A) failed in
  every round. Check that the practice file is back to its one line (see step 2 above).
- To drop a build, press **Cancel build**. Nothing is written to your folder, and the record of
  that build stays in the Audit tab.
- Anything else: copy the message text. No real code or names in what you share.

## After the Fix NP merge: resume CVDA-2026-0002

A build used to say "7 tests, 0 passed" when the frozen test file could not even load. After the
merge, resume `CVDA-2026-0002` at work (**Resume build**) and expect one of two things:

- The real reason, in plain words, with paths shown as `<sandbox>`. Most likely a missing library
  such as `openpyxl` or `pandas` ("CodeVision's Python is missing `openpyxl`"). That is for the
  CodeVision team to install; it is not a code change and uses no round. Use **Send to my senior**.
- Or real test results, if the server has the libraries.

The Layer B line says "0 of 6 ran: the test file could not load", and the test report shows a
"Load error" line, never "Not proven".

## Which Python runs the tests (Fix G3)

When `DA_CODEVISION_PYTHON` is set in `.env`, every test run (requirement tests, code tests, bug
repro, safety net) uses that Python, so CodeVision's own libraries are the ones that count. Do
**not** install them a second time in the Developer Assistant's `.venv`. Not set: the Developer
Assistant's own Python is used, as before. Needs Python 3.14 or newer; a missing file or an older
version stops the run with a plain message and uses no round.

- The Build tab shows "Tests run with: CodeVision's Python 3.14.x" (never the path); the Admin
  Overview settings list shows the same under "Tests run with".
- Layer A now also asks that Python whether each approved library is installed. If not, the AI is
  told "approved but not installed" and picks another library, and the Approach prompt lists those
  libraries as "do not use".

## The AI keeps thinking and never answers (Fix G4, A6)

Qwen3 models think first. With near-greedy settings they can repeat themselves until the length
limit, and no bigger limit helps.

1. In `.env` add `DA_ONPREM_THINKING=off` and restart. Run `python src\da_llm_ping.py`: expect
   `Finish reason: stop` and `thinking text: no`. If it says the server does not accept the thinking
   switch, leave it empty and set `DA_ONPREM_PRESENCE_PENALTY=1.5` instead.
2. Resume the build (for example CVDA-2026-0004).
3. Optional: `DA_ONPREM_MAX_TOKENS_BUILD` gives code-writing calls a longer limit than the rest.
   `DA_ONPREM_TEMPERATURE` and `DA_ONPREM_TOP_P` change the sampling (with thinking `on` and both
   empty, 0.6 and 0.95 are sent).
4. The Admin settings list ("AI thinks before answering") and the Build tab's model card show what
   is sent.

## Wiring the capability map into CodeVision's own page setup (Fix G1)

At home the map page is wired only in the home shell (`src/web/da_home_web_server.py`). CodeVision's
own page setup must add the same three things:

1. Page body: add `map_shell()` next to the other page shells
   (`from layouts.da_capability_map_view import map_shell`; home line 111).
2. Callbacks: call `register_da_capability_map_callbacks(app)` with the other `register_...` lines
   (`from callbacks.screen_callbacks.da_capability_map_callbacks import
   register_da_capability_map_callbacks`; home line 124).
3. Route: the page lives at `MAP_PATH` (`/dev-assistant/capability-map`, from
   `layouts.da_capability_map_view`). The shell shows itself when the URL path equals it, and the
   other pages hide on it (`da_admin_page_callbacks.py`, the `hidden = pathname in (...)` line).

After downloading the new code, run `pip install -r requirements.txt`, because `dash-cytoscape` is
new (the map is drawn with it).

## Clean up

`rmdir /s /q C:\Dev\practice`
