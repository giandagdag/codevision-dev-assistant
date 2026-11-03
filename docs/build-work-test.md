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

1. Set `DA_SANDBOX_SOURCE_DIR` in `.env` to the folder from Q14 (b). Never commit `.env`.
2. Use the **practice folder** from `docs/workspace-work-test.md` and a small made-up request.
3. Press **Build**. Leave the page for a minute and come back from **My recent requests**.
4. Write down: how long each AI call took, whether round 1 passed, how many rounds were used, and
   whether the edit blocks matched the file (a miss shows "Edit block N did not match").
5. In Command Prompt check what the app wrote: `dir /s /b C:\Dev\practice`. Expected: the planned
   code files, and **no** `tests` folder (the tests stay on the Tests tab).

## If something goes wrong

- "The sandbox could not start" in the chat: the `DA_SANDBOX_SOURCE_DIR` folder is wrong or
  missing its `src` folder. Fix `.env`, restart the app, press **Try again**.
- The build pauses with "the AI did not answer": press **Try again**. No round was used.
- Anything else: copy the message text. No real code or names in what you share.

## Clean up

`rmdir /s /q C:\Dev\practice`
