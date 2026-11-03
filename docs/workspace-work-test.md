# Workspace: live test at work (Phase 5, questions Q8, Q11, Q12)

Why: the cloud tests use a pretend folder picker. Only your real Chrome or Edge can prove the
real one works on a work laptop. This takes about 10 minutes. PowerShell and the browser DevTools
are blocked on the work laptop, so every step below uses **Command Prompt** and the app itself.

**Use the practice folder below. Do not pick a copy of the real CodeVision.** The made-up
(fake) plan changes `src\agents\upload_validator.py`, a file the real repo does not have. A copy of
the repo would always stop at "The plan changes src/agents/upload_validator.py, but your folder
does not have it" (blocker B3). The practice folder has exactly what the fake plan needs.

## Step 1: make the practice folder (Command Prompt)

Open **Command Prompt** (Start menu, type `cmd`). Copy each line, press Enter after it:

```
mkdir C:\Dev\practice\src\web
mkdir C:\Dev\practice\src\callbacks
mkdir C:\Dev\practice\src\agents
echo def validate(path): return True> C:\Dev\practice\src\agents\upload_validator.py
dir /s /b C:\Dev\practice
```

The last line lists what you made. You should see these five paths, in any order (the first four
are folders, the last one is the file):

```
C:\Dev\practice\src
C:\Dev\practice\src\agents
C:\Dev\practice\src\callbacks
C:\Dev\practice\src\web
C:\Dev\practice\src\agents\upload_validator.py
```

(`C:\Dev` is only an example. Any ordinary folder is fine. Chrome refuses some folders, for
example your whole user folder or system folders; see Q12.)

## Step 2: run the screen and reach READY TO BUILD

1. Start the screen with the fake provider (`DA_LLM_PROVIDER=fake`) as usual.
2. Take a request through Understand, Discover and Approach until the status is **READY TO BUILD**.

## Step 3: choose the practice folder (this answers Q8)

1. Press **Choose workspace folder**. Your browser opens its own folder window.
   - If **no window opens** and the chat says "I cannot reach your folder from this page", the
     browser has no folder picker (or IT switched it off). Write that down. The ZIP and upload
     buttons are the fallback.
   - If you **close or cancel** the window, the chat says "No folder chosen." That is not a
     problem with the browser. Just press the button again.
2. Pick `C:\Dev\practice` and click the allow button (usually **Edit files** or **Allow**).
3. Write down:
   - How many prompts did you see?
   - Was **Allow on every visit** offered?
   - Did the browser refuse the folder?
4. Expected: the chat says your folder passed the check and the tests folder was created. The
   header chip shows the folder name and a tick (it has no buttons; the buttons are under the
   chat). In Command Prompt, check that the app wrote only the tests folder:

```
dir /s /b C:\Dev\practice\tests
```

   You should see `C:\Dev\practice\tests\cvda_2026_0001\__init__.py` (the number is your request
   number). Nothing else in the practice folder changes.

Optional, in Edge: open `edge://policy` and search for `FileSystem`. Write down anything that is
set to blocked. (Skip this if the page does not open.)

## Step 4: change a file and Re-scan

1. In Command Prompt, add a line to the planned file:

```
echo # edited by me>> C:\Dev\practice\src\agents\upload_validator.py
```

2. In the app press **Re-scan** (a button under the chat). Expected: "1 file changed by you. It
   will be checked when the build runs (Phase 6 onwards)." The Build tab shows the file as
   "Changed by you".

## Step 5: come back later

1. Close the tab and open the request again from **My recent requests**.
2. The header chip may say **Needs your OK**. If so, a **Reconnect** button appears under the
   chat. Press it and allow the folder again. Expected: the chip shows the tick again.

## Questions to answer

- **Q8:** Did the folder window open in Chrome and in Edge? How many prompts? Was "Allow on every
  visit" offered?
- **Q11:** Where do CodeVision's own tests live? Does the top `tests\` folder have an
  `__init__.py`? (`python -m unittest` only goes into folders that have one. If `tests\__init__.py`
  is missing, our `tests\<id>\` tests will not be found from the top folder. That is a Phase 6
  problem, found now.) To look, in Command Prompt: `dir C:\path\to\your\codevision\tests`.
- **Q12:** Where do developers keep their clone? A folder like `C:\Dev\codevision` is fine.
  Chrome refuses some folders.

## If something goes wrong

- The folder window does not open, or the browser refuses the folder: use **Download ZIP** and
  **Upload folder to check**. Tell Claude, so Phase 6 can plan around it.
- Take a photo or copy the text of any error. No real code or names in what you share.

## Clean up

When you are done: `rmdir /s /q C:\Dev\practice`
