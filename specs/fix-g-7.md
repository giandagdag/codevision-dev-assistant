# Fix G7: Approach tells the truth, forgives long text, knows the standard library

Version 1.0 APPROVED, 22 Nov 2026 03:03 SGT. Gian: "Go queue it up on the fix." Written in the project
chat from Gian's work test of 21 Nov (CVDA-2026-0005 "MS Word to Markdown Conversion Module",
photos 21:44 to 01:47) and `logs/da_rejected_replies.log` on the work laptop. Findings W21-24 to
W21-28 in `claude/work-test-2026-11-21-findings.md`. Every choice below is decided; no D-x is open.

Branch `phase-g-fix-7`, cut from the newest `origin/auto/phases-7-10` **after Fix G6 is merged** (it
reuses G5's `agents/da_reply_reader.py::read_json_object`). Queue order: **G5, then G6, then G7**
(Gian, 22 Nov 10:48: keep the order agreed for G5 and G6). PR into `auto/phases-7-10`; the chief
merges it. Normal build: plan `specs/fix-g-7-plan.md`, plan review, small steps with tests, code
review (max 3 rounds), full pytest, ruff, smoke check, screenshots. Commit subjects "G7 step N".
Builder: commit this spec as `specs/fix-g-7.md` as the first commit on the branch.

## 0. What Gian saw (21 and 22 Nov)

Approach failed 6 times in a row with "I couldn't make a plan. The AI could not be reached or gave an
answer the app could not use." The AI was reached every time. The rejected-reply log showed:

| Time | Attempt | Problem | Fair? |
|---|---|---|---|
| 23:47 | 1 | Library `python-docx` not on the approved list | Yes (policy) |
| 23:48 | 2 | AI switched to `zipfile` + `xml`, but 2 options were over 100 characters ("String should have at most 100 characters") | **No**: a good plan thrown away over button text length |
| 00:48 (limit raised to 300 by hand) | 2 | `Library 'xml.etree.ElementTree' is not in the Python standard library` | **No: bug** |

Also: after setting `DA_SEARCH_PROVIDER=codevision`, Try again re-ran Approach only; Discovery still
showed the old "No CodeVision index is connected" result, with no way to search again.

## 1. Code facts (read 22 Nov at 3ee024d, `phase-g-fix-5`)

- `agents/da_approach_agent.py::generate_approach`: 2 attempts; on bad replies returns
  `ApproachResult(None, provider, model, MAX_ATTEMPTS, problems)` with an **empty message**.
- `agents/da_approach_flow.py`: `NOT_REACHABLE` (line 178) and `_failure_text_plain` (line 1166) show
  `message or NOT_REACHABLE`, so a rejected plan reads as "could not be reached". The problems are
  only in the log file `logs/da_rejected_replies.log` (`agents/da_rejected_reply_log.py`).
- `pydantic_classes/da_approach_models.py`: `OPTION_LIMIT = 100`, `TEXT_LIMIT = 200`,
  `SUMMARY_LIMIT = 300`, `PATH_LIMIT = 200`. Over-long text fails `ApproachReply.model_validate`
  and the whole reply is rejected ("The reply has the wrong shape: ...").
- `agents/da_approach_checks.py::_library_problems`: compares the full name against
  `sys.stdlib_module_names`, which holds top-level names only (`xml`, not `xml.etree.ElementTree`).
- Same "not usable: N problems" pattern (count only, no reason) in `da_tester_agent.py:247`,
  `da_build_agent.py:492`, `da_discover_agent.py:144`, `da_understand_agent.py:160`.

## Part 1. Say the real reason (W21-24)

| # | Piece |
|---|---|
| R1 | `ApproachResult` gets a `kind`: `unreachable` (the call failed) or `rejected` (the AI answered, the checks refused it). `NOT_REACHABLE` is used **only** for `unreachable` |
| R2 | For `rejected`, the chat says: "The AI answered, but its plan broke these rules:" then up to 3 problems in plain words, then "Press Try again, or change the request." The problems are the app's own check sentences (never the AI's reply text). More than 3: "...and N more (see the Approach tab)" |
| R3 | Plain-word map for the shape errors: "String should have at most N characters" at `design_choices.0.options.1` becomes "Option 2 of design question 1 is too long". No raw field paths on screen (AF-2 label scan) |
| R4 | **Library hint:** when a problem is a library not on the approved list, add one line: "Ask your admin to approve <name> in Admin, Coding standards, Libraries (it must also be installed), or change the request to use the standard library." |
| R5 | The log line names the problem kinds, not only the count: `Approach reply 1 was not usable: 1 problem (library)`. Kinds: `json`, `shape`, `too_long`, `library`, `folder`, `protected`, `file_name`, `reuse`, `design`, `other`. Same change in the Tester, Build, Discover and Understand log lines (one shared helper) |

## Part 2. Forgive long text (W21-25)

| # | Piece |
|---|---|
| L1 | **Options get a short label and a full detail.** The prompt asks for each option as `{"label": "...", "detail": "..."}`: `label` at most 60 characters (button text), `detail` at most 300 (the full explanation). A plain string is still read (old replies, a model that ignores the shape): it becomes `detail`, and `label` is made from it (L2) |
| L2 | **Cut, never reject, for length.** Before validation, a pre-step cuts any over-long text field in the reply (summary, purpose, reason, question, impact, option label, option detail) **at a word boundary** to its limit and adds "…". A label made from a detail takes the first words up to 60 characters. The uncut text (up to 1,000 characters) is kept in a `full_text` map next to the field so the screen can show it. Length is never again a rejection reason in Approach |
| L3 | **Hover shows the full text.** Option buttons show the label; a `dmc.Tooltip` shows the detail on mouse hover **and on keyboard focus**. Any cut field (summary, purpose, question, impact) shows the full text in a tooltip on the cut line |
| L4 | **The full text is what is saved.** The chosen option's `detail` goes into `ApproachDecision.choice`, the chat line and the audit. The label is display only |
| L5 | **Tell the AI the limits up front.** The Approach prompt lists: summary 300, question and impact 200, option label 60, option detail 300. The retry note says "Keep option labels under 60 characters" when a cut happened (a cut is not a problem, so no retry is spent on it) |
| L6 | Count limits stay checks (files 12, design choices 3, libraries 12): they are rules, not formatting. Library names over 50 characters stay a problem |
| L7 | Old saved plans (plain string options) still open and show as before |

## Part 3. Standard library names with dots (W21-27)

| # | Piece |
|---|---|
| S1 | `_library_problems` compares the **top-level part** (before the first dot) with `sys.stdlib_module_names` and the approved list: `xml.etree.ElementTree` → `xml`, `os.path` → `os`, `email.mime.text` → `email` |
| S2 | Same rule wherever imports are checked against the approved list or the blocked list in Build (`da_build_checks.py`): check it reads the top-level part; fix and test it if not |
| S3 | The Approach prompt says: "List libraries by their top-level import name (for example xml, not xml.etree.ElementTree)" (a hint only; S1 is the real fix) |

## Part 4. Search again after the index is connected (W21-26, W21-28)

| # | Piece |
|---|---|
| D1 | **Search again** button on the Discovery tab, and in the Approach failure message when the last Discovery result has the limitation "No CodeVision index is connected" or "needs building". It runs a fresh Discover round 1 (old results stay in the audit), then Approach starts again as after a normal Discover |
| D2 | When the request's Discovery ran without an index and an index is now available, the Discovery tab shows one amber line: "The CodeVision index is available now. Search again to look for code to reuse." |
| D3 | **Admin, Repository and index:** when the search setting is not `codevision` (`DA_SEARCH_PROVIDER=fake` at work), the Index health card shows an amber line: "Discover is not using this index. Set the search provider to codevision in the server settings and restart." (W21-28) |

## 2. Edge rules

- No new library, no new table, no new setting. Old saved plans and decisions still read.
- Never show or log the AI's reply text outside `logs/da_rejected_replies.log` (unchanged).
- Labels, chat lines and hints come from constants; AF-2 label scan passes.
- Fake AI at home only. Never touch `main`.

## 3. Acceptance criteria (Given / When / Then)

| ID | Given / When / Then |
|---|---|
| G7-1 | Given the fake Generator replies twice with `python-docx` in libraries, then the chat says "The AI answered, but its plan broke these rules:", names python-docx, shows the library hint, and never says "could not be reached" |
| G7-2 | Given the fake client raises a connection error, then the chat still says "The AI could not be reached" |
| G7-3 | Given a reply whose option is a 150-character plain string, then the plan is accepted on attempt 1, the button label is at most 60 characters and ends at a word with "…", and the tooltip shows all 150 characters |
| G7-4 | Given a reply with `{"label", "detail"}` options, when the developer picks one, then the decision, the chat line and the audit hold the full detail |
| G7-5 | Given a 450-character summary, then the plan is accepted, the summary is cut at a word to 300 with "…", and the full text shows on hover |
| G7-6 | Given libraries `xml.etree.ElementTree`, `os.path`, `email.mime.text`, `zipfile`, then no library problem. Given `python_docx.api`, then one problem naming it |
| G7-7 | Given a Build import of `xml.etree.ElementTree` and an approved-list check, then it passes (S2) |
| G7-8 | Given 4 design choices with policy max 3, then it is still a problem (count rules unchanged) |
| G7-9 | Given a request whose Discovery said "No CodeVision index is connected" and a built index with provider `codevision`, then the Discovery tab shows the amber line and Search again runs a new round 1 that uses the index |
| G7-10 | Given provider `fake` at work, then Admin Index health shows "Discover is not using this index" |
| G7-11 | Given each "not usable" log line (Approach, Tester, Build, Discover, Understand), then it names the problem kinds, never reply text |
| G7-12 | Tooltip opens on keyboard focus (Playwright, skipped with no browser); screenshots of the Approach chat with a cut option and the tooltip open are added to the screenshot script |
| G7-13 | An old saved plan with plain-string options opens and shows as before |

## 4. Work notes (for `docs/build-work-test.md`)

1. Take the new ZIP into a new folder; the hand edits from 21 Nov (`OPTION_LIMIT = 300`, the
   `.split(".")[0]` line, `MAX_SKIPPED_SHARE = 1.0`) are not carried over.
2. Copy `src\data\da_code_index\` and `logs\` from the old folder (or set `DA_CODE_INDEX_DIR`).
3. Open CVDA-2026-0005, Discovery tab, **Search again**; then Approach should give a plan with
   `zipfile` and `xml` and short option buttons.

## 5. Out of scope

- Approving or installing `python-docx` (an admin and bank decision; R4 only points to it).
- Length forgiveness outside Approach (Tester, Build): park as P-item if seen at work.
