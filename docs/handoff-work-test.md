# Handoff and Escalations inbox: live test at work (Phase 10)

Why: at home the senior list is a made-up list in `.env`, the database is one SQLite file on one
laptop, and the pretend folder replaces the browser's folder picker. Only the work server shows
whether the real people, the shared database and the real Chrome behave the same. Each test below
answers one open question in `specs/phase-10-handoff-escalations.md` section 19 (WF-1 to WF-6).

**PowerShell and the browser DevTools are blocked on the work laptop, so every step uses Command
Prompt (`cmd`) and the app itself.** Use made-up values. No real names, folders or code in a photo.

AS400 picture: Handoff is the promotion request (compare the tested member with the library one, then
promote and lock it). The inbox is the help-desk operator's message queue.

## Before you start

1. Open **Command Prompt** and go to the Developer Assistant folder.
2. Run the smoke check: `.venv\Scripts\python src\da_smoke_check.py`. Items 28a and 28b must print,
   then `Smoke check passed.`
3. Start the app with `.venv\Scripts\python src\web\da_home_web_server.py`.

## WF-1: who is a senior

1. Open `/inbox` as a person on the senior list (`DA_SENIOR_IDS`) or named in the catalog: the list
   opens.
2. Open it as anyone else: only "This page is for capability seniors." shows.
3. Write down how the work login names a user and where the senior list should come from. With
   `DA_SENIOR_SOURCE=codevision` nobody gets in and the log says why: that is expected until decided.

## WF-2: telling the senior

The inbox shows `Inbox (2)` in the menu and a banner on Home for seniors only. There is no email or
Teams message. Write down whether the bank allows either and who would approve it.

## WF-3: one shared database

1. A developer on laptop A presses **Get help** on a request.
2. A senior on laptop B opens `/inbox`.
3. Check: the row shows on B. If it does not, the two laptops do not share one database and the inbox
   cannot work across laptops.

## WF-4: the real capability list

Compare the made-up capabilities with the real ones. Write down who owns the named seniors and the
backups. Do not type real names into the app until the owner agrees. A capability with nobody named
shows its rows under "Nobody is named for this capability".

## WF-5: copy the summary

1. Reach HANDED OFF on a made-up request. Open the **Audit** tab.
2. Press **Copy summary** and paste into Notepad. Check the text is whole.
3. If nothing was copied, the text is selected: press Ctrl+C and paste again. Write down which one
   worked and whether the Bitbucket pull-request box accepts that much text.

## WF-6: folder permission at the final check

1. Build a request, then work in Refine for a while.
2. Press **Ready for handoff**, then **Check my folder**.
3. Write down whether Chrome asks for the folder again (Reconnect) every time.

## The guidance reaches the Generator

On the pretend work server (`127.0.0.1:8070`): escalate a build that stopped twice, send guidance
from `/inbox`, **Return to developer**, press Refine. The fix round's request to the server must carry
the line "Guidance from your senior:". Write down whether the work model follows it.
