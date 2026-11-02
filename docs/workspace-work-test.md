# Workspace: live test at work (Phase 5, questions Q8, Q11, Q12)

Why: the cloud tests use a pretend folder picker. Only your real Chrome or Edge can prove the
real one works on a work laptop. This takes about 10 minutes. **Pick a scratch folder or a COPY of
CodeVision. Never your working folder.**

## Part 1: does the folder picker exist? (Q8)

Do this in Chrome first, then in Edge, on the CodeVision page (or any `https` page).

1. Press **F12** to open DevTools, then open the **Console** tab.
2. Type `typeof window.showDirectoryPicker` and press Enter.
   - Expect `"function"`. If you see `"undefined"`, write that down. The app will use the ZIP and
     upload fallback on this laptop.
3. Type `await showDirectoryPicker({mode: "readwrite"})` and press Enter. A window opens.
4. Pick a **scratch folder** (an empty one you made for this). Click **Allow** / **Edit files**.
5. Write down:
   - How many prompts did you see?
   - Was **Allow on every visit** offered?
   - Did Chrome refuse the folder? (It refuses some, for example your whole user folder or system
     folders. See Q12.)
6. In Edge, also check `edge://policy` and search for `FileSystem`. Write down anything that is
   set to blocked.

## Part 2: try the real screen

1. Start the screen, take a request to READY TO BUILD (the fake provider is fine).
2. Press **Choose workspace folder** and pick a COPY of CodeVision.
3. Expected: the chat says the folder passed the check and the tests folder was created. Look in
   the copy: there should be a new folder `tests/<request id>/` holding `__init__.py`. Nothing
   else in the copy changes.
4. Open one of the planned files in your editor, change a line, save. Press **Re-scan**. Expected:
   "1 file changed by you."
5. Close the tab, open the request again from **My recent requests**. Expected: the chip may say
   **Needs your OK**; press **Reconnect**.

## Questions to answer

- **Q8:** Did the picker exist in Chrome and in Edge? How many prompts? Was "Allow on every visit"
  offered?
- **Q11:** Where do CodeVision's own tests live? Does the top `tests/` folder have an
  `__init__.py`? (`python -m unittest` only goes into folders that have one. If `tests/__init__.py`
  is missing, our `tests/<id>/` tests will not be found from the top folder. That is a Phase 6
  problem, found now.)
- **Q12:** Where do developers keep their clone? A folder like `C:\Dev\codevision` is fine. Chrome
  refuses some folders.

## If something goes wrong

- The picker is `"undefined"` or refused: use **Download ZIP** and **Upload folder to check**.
  Tell Claude, so Phase 6 can plan around it.
- Take a photo or copy the text of any error. No real code or names in what you share.
