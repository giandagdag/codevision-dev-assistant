# Fix G4: work test 20 Nov (Qwen thinking loop, starter catalog leak, AI suggests new capabilities, catalog editor, charter and queue layout)

Version 1.1 APPROVED, 20 Nov 2026 (v1.0 21:50 SGT; v1.1 22:05 adds A7 and A8, section 2.5). Gian,
20 Nov 21:46: "Yes go ahead... I give you full approval." Written in the project chat from
`claude/work-test-2026-11-20-findings.md` (A1 to A8). Every choice below is decided; no D-x is open.

Branch `phase-g-fix-4`, cut from the newest `origin/auto/phases-7-10` (Fix G3 is merged there, PR #110).
PR into `auto/phases-7-10`; the chief merges it. Build it the normal way: plan
`specs/fix-g-4-plan.md` (a `## Steps` list), plan review, small steps with tests, code review (max 3
rounds), full pytest, ruff, smoke check, screenshots. Commit subjects "G4 step N". Builder: commit this
spec as the first commit on the branch (it was written to disk untracked). PR body with
`--body-file`. **Order: section 2.1 (A6) first**: it blocks every build at work.

## 0. What Gian found at work (20 Nov)

| # | Finding |
|---|---|
| A6 | Build CVDA-2026-0004 round 1 paused: "no choices[0].message.content ... stopped at its length limit. Raise DA_ONPREM_MAX_TOKENS". He raised it to 16000: same. Log: model `Qwen3.6-35B-A3B`, `finish_reason=length`, `completion_tokens=16000`, `content: null`, the whole budget in the `reasoning` field, which starts sensibly and then repeats `NON-NON-NON-...` until the limit |
| A1 | Full rebuild refused: the Folder scope still pointed at the made-up folder |
| A4 | The work catalog holds the home starter capabilities (Limits, Reports, Uploads, "Limits capability lead" seniors) and patterns for made-up files (`src/agents/docs_folder_to_md.py`, `src/agents/docs_markdown_export.py`). The AI forced real programs into them |
| A3 | The AI scan can only answer a name from the list or none; most real programs come back "No capability fits". Gian: "Let AI suggest a capability that isn't there. Then Admin can approve." |
| A5 | Catalog editor: uneven boxes; Add module is a tiny dropdown that cuts the names; all path patterns in one squeezed box |
| A2 | The A1 refusal shows as plain grey text, not the red error box |
| A7 | Project charter: Purpose and Glossary sit in a wide left column while In scope, Out of scope, Architecture principles and Constraints stack in the narrow right column. The page is lopsided, with a large empty area under the Glossary. Each one-column table carries a useless "Text" header |
| A8 | Capability catalog, Unassigned queue: 91 cards in the narrow side column push the page far down; no search, sort or filter, so finding one program means scrolling card by card |

## 1. Causes (read in the code on 20 Nov, `phase-g-fix-3` working copy)

- **A6.** `src/agents/da_llm_client.py` sends `temperature 0.2`, `top_p 0.2` (`ONPREM_TEMPERATURE`,
  `ONPREM_TOP_P`) and never says whether the model should think. The work model is a Qwen3 thinking
  model, so it thinks first. Qwen's own guidance: in thinking mode use temperature 0.6, top_p 0.95,
  top_k 20, **never near-greedy decoding** (it causes endless repetition), and `presence_penalty` (0 to
  2, 1.5 for loops) reduces repeats; `chat_template_kwargs: {"enable_thinking": false}` turns
  thinking off on vLLM and SGLang servers. Our near-greedy settings plus thinking = the loop. A bigger
  limit cannot help. Also: `_empty_reply_message` checks `reasoning_content` only; this server returns
  the field as `reasoning`. And the message always starts with "Check DA_ONPREM_URL", which is wrong
  when the server clearly answered.
- **A1.** `da_load_starter_rulebook.py::_with_work_purpose` clears `index_folder_scope`, but only when
  the seed is published into an **empty** database. The work database got its rulebook before that
  rule, so v3 to v5 kept the home scope.
- **A4.** The same function swaps only purpose and scope. The capability catalog (and its seniors and
  patterns) comes from `da_rulebook_seed.json`, the home seed, also at work.
- **A3.** `src/data/da_tagger_prompt.md`: "capability": "one exact name from the list above, or none".
  Checked in `da_admin_tagger.py`.
- **A5.** `layouts/da_admin_catalog_tab.py`: `_add_module_panel` is two `dmc.Select` (capability,
  path) in a `Group`; path patterns are one text box per capability.
- **A7, A8.** The charter and catalog tabs use the 2/3 + 1/3 grid from Phase 11 fix 3 (V4) for every
  tab, whatever the content; the queue is drawn in the 1/3 side column with every card at full height.

## 2. What we build

### 2.1 A6: the AI must answer (first)

| # | Piece |
|---|---|
| T1 | **Thinking setting.** New `.env` setting `DA_ONPREM_THINKING`: `off`, `on`, or empty. `off` adds `"chat_template_kwargs": {"enable_thinking": false}` to the body. `on` adds it with `true`. Empty sends nothing (today). `.env.example` shows `DA_ONPREM_THINKING=off` with a comment "Qwen3 models: off makes build answers faster and stops thinking loops". Plain label in Server settings: "AI thinks before answering" |
| T2 | **Sampling settings.** `DA_ONPREM_TEMPERATURE`, `DA_ONPREM_TOP_P`, `DA_ONPREM_PRESENCE_PENALTY` (empty = today's 0.2, 0.2, not sent). Checked as numbers (temperature 0 to 2, top_p over 0 up to 1, presence penalty 0 to 2); a bad value stops the app at start with the setting's name. When thinking is `on` and temperature and top_p are left empty, send 0.6 and 0.95 (Qwen's thinking values) instead of 0.2 and 0.2, and log once at start which values are used. Presence penalty is sent only when set |
| T3 | **Per-role length.** `DA_ONPREM_MAX_TOKENS_BUILD` (empty = `DA_ONPREM_MAX_TOKENS`) for the Builder role only (build code, contract, tests prompts). Others unchanged |
| T4 | **Read `reasoning` too.** An empty reply checks `reasoning_content` **and** `reasoning`. Never logs more than today (first 2,000 characters, key masked) |
| T5 | **Loop detection.** When `finish_reason` is `length` and the last 1,000 characters of the thinking text are mostly one short piece repeated (one piece of 2 to 20 characters making up over 60% of that tail), the error is: "The AI got stuck repeating itself while thinking and used its whole length limit. Set DA_ONPREM_THINKING=off (or add DA_ONPREM_PRESENCE_PENALTY=1.5), restart, and resume the build." No URL hint |
| T6 | **Right message for the right cause.** "Check DA_ONPREM_URL points at the chat endpoint" only when the body has no `choices` at all. `length` without a loop: "The AI stopped at its length limit before it wrote an answer. Raise DA_ONPREM_MAX_TOKENS, or set DA_ONPREM_THINKING=off." Only thinking and no answer: "The AI sent only its thinking and no answer. Set DA_ONPREM_THINKING=off." |
| T7 | **The server refuses the switch.** If the server answers HTTP 400 and the body mentions `chat_template_kwargs` or `enable_thinking`, the error says: "The AI server does not accept the thinking switch. Leave DA_ONPREM_THINKING empty." Never a silent retry without it |
| T8 | **Check command.** `python src\da_llm_ping.py` prints the thinking setting, the sampling values sent, `finish_reason`, the token counts, and whether the reply had thinking text, for one short "Reply with OK" call. Never prints the key or a header |
| T9 | **Build tab and Admin.** Build and test, Model per role: one read-only line "AI thinking: off / on / server default; temperature x, top_p y". No `DA_` names on the screen (AF-2 rule) |

### 2.2 A1 and A4: clean the starter data out of the work database

| # | Piece |
|---|---|
| C1 | **Starter check at work** (`DA_LLM_PROVIDER=onprem`). Plain function `starter_leftovers(rulebook) -> list[Leftover]` in `agents/da_admin_starter.py`: (a) folder scope inside `da_fake_codevision`; (b) a capability whose name, description and both seniors equal the home seed's; (c) a path pattern that names a file from `src/data/da_fake_codevision` or the home seed's made-up files. Matching is by the seed's own values, never a hard-coded list |
| C2 | **Shown, never silent.** Repository and index, Connection card: (a) shows in the red error box "The Folder scope is the made-up practice folder." with button **Clear and use CodeVision's folder**. Capability catalog: a card above the table "From the starter list (made-up, not CodeVision)": each leftover capability and pattern as a row, with **Remove all starter items** and per-row Remove. Each action saves **one** new rulebook version with a change note ("Removed starter items: 3 capabilities, 2 patterns"). Restore still works. Overview, Needs attention: "Starter items in the catalog" with a button |
| C3 | **Work seed.** At work, a fresh database gets an **empty** catalog (no capabilities) and an empty scope. The catalog's empty state: "No capabilities yet. Add one, or run an index build and let the AI suggest them." |
| C4 | **Approved AI tags into a removed capability** go back to the Unassigned queue as AI cards (state `proposed`), so nothing is lost. Tags history (T1, T2...) keeps its versions |
| C5 | **A2.** The fake-folder refusal from the index job shows in the job card's red error box with its fix hint, like every other job error |

### 2.3 A3: the AI may suggest a new capability

| # | Piece |
|---|---|
| S1 | **Prompt.** `da_tagger_prompt.md` reply becomes: `capability` = an exact name from the list, or `none`, or `new`. With `new`: `new_name` (2 to 40 characters, plain words, no path, no person's name) and `new_description` (max 120 characters). The list is still sent (name and description only) |
| S2 | **Plain code check.** `new` without a valid name or description: the module is skipped (today's rule). A `new_name` equal (ignoring case and spaces) to an existing capability becomes a normal proposal for that capability |
| S3 | **Grouping.** After a run, proposals with the same new name (ignoring case, spaces, plural "s") are one **suggestion** with all its modules. Two names that differ only by those are merged under the first one seen |
| S4 | **Card.** "New capability suggested: <name>" pill, the description, the module list (path chips, each with its own summary on hover and its own Remove from this suggestion), confidence (the lowest of its modules). Buttons: **Create and assign** (opens a small dialog with name and description to edit, named senior and backup senior pickers, empty allowed; Save creates the capability with exact-path patterns for the kept modules, **one** new rulebook version, note "AI suggestion: new capability <name> with N programs"), **Assign to** (an existing capability, all kept modules), **Reject** (all modules become `rejected`). Never created by itself |
| S5 | **Approve all high-confidence** never creates a capability: it skips suggestion cards and its confirm box says how many suggestions wait for review |
| S6 | **Re-tag after a new capability.** After Create and assign, the queue header offers "Re-check the No capability fits programs against the new list" (runs the tagger only on `none` modules, same job lock) |
| S7 | **Fake script** at home: a `new` reply for 3 made-up modules with two spellings of the same name, and one bad `new` reply |

### 2.4 A5: catalog editor layout

| # | Piece |
|---|---|
| L1 | **Even rows.** Capability rows in the shared card component: every input the same height, one line per capability with the description able to wrap inside a fixed-height box (shows 2 lines, expands on focus). Columns with fixed widths: Name 18%, Description 30%, Named senior 14%, Backup senior 14%, Patterns 14%, actions 10% |
| L2 | **Path patterns as a list.** The Patterns cell shows a count chip ("5 patterns") that opens a side panel for that capability: one row per pattern (chip **Exact file** or **Pattern**, the full text, how many indexed modules it matches now, Remove), an **Add pattern** field with a live "matches N modules" hint, Save. Saving is one rulebook version |
| L3 | **Add modules pop-up.** **Add modules** opens a modal (wide, about 70% of the screen): capability picker at the top, a search box, filter switches **Unassigned only** (on by default) and **Show AI summary**, a table of indexed modules (checkbox, full path never cut, current capability, AI summary), **Select all shown**, and "Add N modules to <capability>". One rulebook version with exact-path patterns. A module already in another capability says so in its row; adding it moves it (the row shows "moves from <name>") |
| L4 | Same colours and sizes as `styles/da_admin_styles.py`; screenshots of the catalog, the patterns panel and the modal added to the screenshot script |

### 2.5 A7 and A8: page layout (Operate-mode rules)

Layout rules for every change in this section (from the impeccable layout guidance, Operate mode: an
admin tool where scanning and consistency matter more than decoration):
- **Squint test:** with the detail blurred, the primary block, then the secondary blocks, read in order.
- **Pairs sit side by side, at the same height:** blocks that are read together share a row.
- **No empty half-page:** in any row, the two columns end within 120 px of each other at 1366 px and
  1920 px.
- **Long lists scroll inside their own box**, with their controls fixed at the top of that box, never
  stretching the page.
- One spacing scale (4, 8, 16, 24 from `da_admin_styles.py`); no one-off margins.

| # | Piece |
|---|---|
| L5 | **Project charter layout (A7).** Row 1, full width: **Purpose** (the size bar stays). Row 2, two equal columns: **In scope** and **Out of scope**, equal height. Row 3, two equal columns: **Architecture principles** and **Constraints**, equal height. Row 4, full width: **Glossary** (two-column table, Term and Meaning). Below 1100 px everything stacks in that same order. Same card component as the other tabs |
| L6 | **Lists, not one-column tables.** In scope, Out of scope, Architecture principles and Constraints show as rows with thin dividers (green tick for In scope, red dot for Out of scope, a small number for principles and constraints). No "Text" header. Edit mode keeps today's editing (one input per row, Add row, Remove) |
| L7 | **Review queue gets its own space (A8).** The Capability catalog tab gets two views in a segmented control at the top: **Capabilities** and **Review queue (N)** (N = open cards). The queue view uses the full width. Overview Needs attention and the catalog header link open the Review queue view |
| L8 | **Fixed scrolling list.** The queue cards sit in a box with its own scroll bar, height `calc(100vh - 260px)` (minimum 420 px). The control bar above the list stays visible while the list scrolls. Each card is compact: line 1 = path (full, never cut; wraps if it must), arrow, proposal pill, confidence pill, actions on the right; line 2 = the AI summary (one line, full text on hover); the AI's reason only on expand ("Why?"). Target: at least 8 cards visible at 1920 x 1080 |
| L9 | **Search, filter, sort, count.** Control bar: a search box (matches the path and the AI summary, any case, updates as you type, clear button); filter chips: **Source** (AI scan, From a request), **Proposal** (Has a capability, No capability fits, New capability suggested), **Confidence** (high, medium, low), **Folder** (top folders found in the paths, for example `agent_flows`, `web`); sort: Confidence (high first, default), Path A to Z, Newest first. A line "Showing 12 of 91". Empty result: "No programs match. Clear the filters." with a button. Search, filters and scroll position are kept while approving cards, so the list does not jump back to the top |
| L10 | **Select several at once.** A checkbox on each card and **Select all shown**. With any selected, a bar shows "N selected" with **Assign to** (one capability picker), **Approve proposals** (only cards that have a proposal; says how many it skips) and **Reject**. Each bulk action saves **one** rulebook version with the count in the note, after a confirm box listing the count per capability |
| L11 | **Builder check.** Before the PR, the builder looks at the rendered pages (screenshots at 1366 px and 1920 px) against the section 2.5 rules and fixes what it sees in one batch. If the impeccable skill is installed for the builder at home, it runs its layout critique on the two tabs; this is optional, and no new library is added to the app |

## 3. Edge rules

- No new library. No new database table (new rulebook fields with defaults; old versions still read).
- Never send the thinking switch unless the setting says so. Never log a key, a header, code or a
  prompt (today's rules).
- Fake AI at home only; `FakeLLMClient` never at work.
- Every Admin change is a new rulebook version with a plain change note; nothing silent.
- One job at a time (index, tagging, re-check share the lock).
- Never touch `main`.

## 4. Acceptance criteria (Given / When / Then)

| ID | Given / When / Then |
|---|---|
| G4-1 | Given `DA_ONPREM_THINKING=off`, when any on-prem call is built, then the body has `chat_template_kwargs.enable_thinking = false`; given empty, then the body has no `chat_template_kwargs` |
| G4-2 | Given `on` and empty temperature and top_p, then 0.6 and 0.95 are sent; given explicit values, those are sent; given `DA_ONPREM_TEMPERATURE=abc`, the app stops at start naming the setting |
| G4-3 | Given a reply with `content: null`, `finish_reason: "length"` and a `reasoning` field whose tail is "NON-" repeated, then the error is the T5 loop sentence and has no URL hint |
| G4-4 | Given `length` with varied thinking text, then the T6 length sentence; given only `reasoning` and `finish_reason: "stop"`, then the "only its thinking" sentence; given no `choices`, then the URL sentence |
| G4-5 | Given HTTP 400 with `enable_thinking` in the body, then the T7 sentence, and no second call without the switch |
| G4-6 | Given `DA_ONPREM_MAX_TOKENS_BUILD=24000` and `DA_ONPREM_MAX_TOKENS=8000`, then build calls send 24000 and Understand calls send 8000 |
| G4-7 | Given the fake server, when `da_llm_ping.py` runs, then it prints the thinking setting, sampling values, finish reason and token counts, and no key |
| G4-8 | Given a work database whose active rulebook has the home scope and the 3 home capabilities with 2 made-up patterns, when Admin opens Repository and index and the catalog, then both leftovers show; **Remove all starter items** saves one version without them; Restore of the old version brings them back |
| G4-9 | Given an approved AI tag into a capability that is then removed, then that module is back in the queue as an AI card |
| G4-10 | Given an empty database at work, when the starter rulebook loads, then the catalog is empty and the scope is empty |
| G4-11 | Given the fake tagger script (S7), when a scan runs, then one suggestion card lists the 3 modules under one name, the bad reply is skipped and named in the run log |
| G4-12 | Given a suggestion card, when Create and assign is saved with 2 of 3 modules kept and the name edited, then one new version holds the new capability, its 2 exact patterns and the note; the third module stays in the queue as "No capability fits" |
| G4-13 | Given suggestion cards and high-confidence proposals, when Approve all high-confidence runs, then no capability is created and the confirm box counts the waiting suggestions |
| G4-14 | Given a new capability just created, when "Re-check the No capability fits programs" runs, then only `none` modules are sent to the AI |
| G4-15 | Given the catalog in edit mode at 1366 px and 1920 px, then all row inputs in one row have the same height (Playwright measure, 2 px tolerance) and no module path in the Add modules modal is cut |
| G4-16 | Given the Add modules modal with **Unassigned only** on, when 3 modules are ticked and added, then one version holds 3 exact patterns; a module from another capability shows "moves from <name>" |
| G4-17 | Given the patterns panel, when a pattern is typed, then the live count matches the modules it would match; Save is one version |
| G4-18 | Given the fake-folder refusal, then it shows in the red error box with the fix hint |
| G4-19 | AF-2 label scan still passes on every new screen part (no `DA_`, no raw field names) |
| G4-20 | Given the Project charter at 1366 px and 1920 px, then Purpose is first and full width, In scope and Out of scope share a row at equal height, Architecture principles and Constraints share a row at equal height, Glossary is last and full width, and the two columns in a row end within 120 px of each other (Playwright measure) |
| G4-21 | Given the charter lists, then no "Text" header is drawn; edit mode still adds, edits and removes rows and saves one version |
| G4-22 | Given 91 open cards, when the catalog opens the Review queue view, then the page height does not grow with the cards (the list box scrolls), the control bar stays visible after scrolling the list, and at least 8 cards are visible at 1920 x 1080 |
| G4-23 | Given made-up cards, when searching "cobol", then only cards whose path or summary contains it show, and the count line says "Showing N of M"; each filter and each sort order gives the expected cards in the expected order |
| G4-24 | Given a filter set and a card approved, then the filter, the search text and the scroll position stay |
| G4-25 | Given 5 selected cards, 3 with a proposal, when Approve proposals is confirmed, then one version holds the 3 patterns, the note says 3, and the confirm box said 2 were skipped |
| G4-26 | Screenshots of the charter, the Review queue (with a filter on) and the bulk bar are added to the screenshot script |

## 5. Work notes (for `docs/discover-work-test.md` and `docs/build-work-test.md`)

1. In `.env`: `DA_ONPREM_THINKING=off`. Restart. Run `python src\da_llm_ping.py`: expect `finish_reason
   stop` and no thinking text. If it says the server does not accept the switch: leave it empty and set
   `DA_ONPREM_PRESENCE_PENALTY=1.5` instead.
2. Resume build on CVDA-2026-0004.
3. Admin, Capability catalog: **Remove all starter items**, then Full rebuild; review the AI's new
   capability suggestions in the Review queue view.

## 6. Out of scope

- Indexing straight from Bitbucket (parked, needs a read-only token and the WF-12 answer).
- Upgrade G cluster suggestions (G2 of #101) beyond reusing the suggestion card.
- Changing CodeVision's own settings or model.
- Restyling the other Admin tabs (only charter and catalog change here).
