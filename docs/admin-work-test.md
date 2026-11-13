# Admin console: live test at work (Phase 11)

Why: at home the console runs on a made-up Admin list, a made-up catalog, a made-up SonarQube list
and one SQLite file. Only the work server shows whether the real people, the real database and the
real browser behave the same. Each test below answers one open question (WF-1 to WF-8) in
`specs/phase-11-admin-console.md`.

**PowerShell and the browser DevTools are blocked on the work laptop, so every step uses Command
Prompt (`cmd`) and the app itself.** Use made-up values. No real names, folders or code in a photo.

AS400 picture: the console is like the WRKSYSVAL screen plus a journal of changes. You change a value,
write down why, and the system keeps every earlier version you can compare or restore.

## Before you start

1. Open **Command Prompt** and go to the Developer Assistant folder.
2. Run the smoke check: `.venv\Scripts\python src\da_smoke_check.py`. Items 31 to 39 must print, then
   `Smoke check passed.`
3. Start the app and open `/admin` (the path may differ at work, see WF-6).

## WF-1: one shared database

1. Admin A saves a small change on **Build and test** (for example Max fix rounds 3 to 4).
2. A developer, on another laptop, starts a new request.
3. Check: the request is pinned to the new version. Write down whether both laptops use the same
   database. If they do not, an Admin save will not reach the developers.

## WF-2: who is Admin

1. Open `/admin` as a person who is on the Admin list: the Overview opens.
2. Open it as a person who is not: only "This page is for the CodeVision core team." shows.
3. Write down how the work login names a user, and where the Admin list should come from.

## WF-3: the real capability list

1. Open **Capability catalog**. Compare the made-up capabilities with the real ones.
2. Write down who owns the real list, the named seniors and the backups. Do not type real names into
   the app until the owner agrees.

## WF-4: SonarQube

1. Open **Coding standards**, scroll to the SonarQube severity map.
2. Check: is the sample list clearly marked as sample? Change one severity and save.
3. Write down whether the server can read SonarQube (web API, an exported file, or nothing).

## WF-5: model names per role

1. Open **Build and test**, Model per role. Type the model name for the Generator and the Tester,
   save with a note.
2. Start one request. Check in the log (or ask the server owner) which model each role really used.
3. Write down the names that worked.

## WF-6: where the console sits in the menu

1. Look in the CodeVision side menu. Is there a place for the Developer Assistant Admin entry?
2. Write down the path the console answers on and who may add the menu entry.

## WF-7: telling Admin about a new Unassigned file

1. Make a request that creates a new file outside every capability pattern.
2. Open **Overview**. Check: **Needs attention** names the open row and links to the catalog.
3. Write down whether Admin also wants a message (email, Teams).

## WF-8: the work browser

1. In the work browser open each of the eight tabs in turn.
2. Check: tables, tabs, the Edit, Save and Cancel buttons and the confirm dialogs all show and work.
   On **Overview**, switch the health numbers between **Last 30 days** and **All time**.
3. Write down anything that looks different from the picture in the README.

## After the tests

Write the answers into the open questions list. Do not change code at work; bring the notes home.
