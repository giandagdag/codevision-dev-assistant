# Phase 11 fix 3: Admin console polish, one index job, real work embedder

Version 1.1 APPROVED, 17 Nov 2026 (19:35 SGT). Gian: "Go" (18:52). Every D-x below is option 1 (the
recommended one). v1.1: D-A changed after Gian's work photo of `a_vector.py` (19:25), see section 1 G2.

Branch `phase-11-fix-3`, cut from the newest `auto/phases-7-10` (fixes 1 and 2 are merged there).
PR into `auto/phases-7-10`. Build it the normal way: plan, plan review, small steps with tests, code
review (max 3 rounds), pytest, ruff, smoke check, screenshots.

## 0. What Gian found at work (17 Nov)

| # | Finding | Kind |
|---|---|---|
| G1 | No page title on any tab (on Project charter there is no "Project charter" heading) | Look |
| G2 | Rebuild index fails: "This only works inside CodeVision at work." | Bug (work) |
| G3 | Rebuild index button sits at the top; wants a right-hand job panel with progress % and time left | Look and feature |
| G4 | Wants Full rebuild and Delta rebuild (only new or changed programs) | Feature |
| G5 | Refresh tiles have different widths; only Manual can be picked | Look and feature |
| G6 | Most content sits on the page background; wants every section in its own white card, like Overview | Look |
| G7 | Catalog scan said "6 scanned, 2 proposals": where did 6 come from, and where are the proposals? | Bug |
| G8 | Tagging should happen during indexing; remove Scan all programs and Tag new or changed | Change |
| G9 | Two search modes; the demo has one search box for names or what the code does | Change |
| G10 | Brand constants are not editable; "UI rules: 2" shows but the rules are not on the screen | Bug and feature |
| G11 | The screens read like a text dump; the demo looks smooth | Look (all tabs) |

## 1. Root causes (the builder confirms each one before changing code)

- **G2 (confirmed from the code and a work photo, 17 Nov 19:25).** Two clashes, not one:
  1. `WorkEmbedder` (`agents/da_code_index.py`) runs `from agents.a_vector import create_embeddings`.
     The DA has **its own** `agents` package (`src/agents/__init__.py`), so Python looks inside the
     DA's `agents`, finds no `a_vector`, and the ImportError is hidden behind one generic sentence.
  2. CodeVision's `a_vector.py` itself starts with `from tools import payload_generation, spirare,
     dataframe_functions` and `from configs import llm_config, app_config`, plus `numpy` and `faiss`.
     The DA also has its own `configs` package, so even with CodeVision's folder on the path,
     `configs` would resolve to the DA's. `tools` may also pull in libraries the DA's `.venv` lacks.
  So adding a folder to the search path **cannot** work inside the DA's own Python process.
  CodeVision's code is in `...\Desktop\CodeVision\CodeVision 61\imagebuild\src` (the folder that
  holds `agents`, `tools`, `configs`). **Bitbucket has nothing to do with it**: the index reads a
  folder on disk.
- **G7.** With no built index, the module list falls back to the folder scope. The seed sets the
  scope to the made-up folder `src/data/da_fake_codevision`, which travels in the ZIP. So at work the
  tagger read the 6 made-up programs, with the real Qwen model. The 2 proposals should show as
  "From the AI scan" cards in the Unassigned queue and in Overview Needs attention; find out why they
  do not.
- **G10.** The UI conventions list is counted but not drawn (find out why). Brand constants have no
  edit mode.
- **G11.** Fixes 1 and 2 checked that each panel **exists**, not that it **looks like** the demo.
  There is no shared card component, so each tab draws its own loose text.

## 2. Decisions (DECIDED 17 Nov 18:52, all option 1)

| # | Question | Decision |
|---|---|---|
| D-A | How does the DA reach CodeVision's embedder at work? | **1: a separate helper process.** New settings `DA_CODEVISION_SRC` (CodeVision's `src` folder, the one holding `agents`, `tools`, `configs`) and `DA_CODEVISION_PYTHON` (the Python that runs CodeVision on that laptop or server; empty = the DA's own `.venv` Python). `WorkEmbedder` starts one helper, `src/da_embed_worker.py`, with that Python, **working folder = `DA_CODEVISION_SRC`** and only that folder on its search path (so `agents`, `tools`, `configs` are CodeVision's, never the DA's). The DA sends texts and gets vectors back as JSON lines over stdin and stdout; one helper serves the whole build (started once, closed at the end, restarted once if it dies). The helper never prints or logs the text. Errors name the real cause in plain words (for example "CodeVision's embedder could not start: No module named 'pandas'. Set the Python that runs CodeVision"), never a key, a header or text. AS400 comparison: like SBMJOB into CodeVision's own library list instead of adding its library to ours, where our same-named objects would win. 2: copy the DA into CodeVision's folder (rejected: the same-name clash) |
| D-B | Delta rebuild | **1: yes.** Store each piece's file hash. Delta re-embeds only pieces from new or changed files, reuses the saved vectors for the rest (`index.reconstruct_n`, flat index), drops deleted files, then writes the whole index file again (cheap). Full re-embeds everything. Full is forced when the vector size or the embedder changed |
| D-C | Tagging | **1: part of the index job.** Step 1 builds the index; step 2 tags programs: Full re-tags every module, Delta tags only new or changed ones. The index is saved before tagging starts, so a tagging failure never loses the index. Remove "Scan all programs" and "Tag new or changed programs" from the catalog |
| D-D | Refresh modes | **1: Manual and Nightly work; On every merge stays disabled** with the reason "Needs Bitbucket to tell the server about merges (WF-12)". Nightly runs a Delta job at an Admin-set time (default 02:00 Singapore time), only while the DA server is running, with the same lock file |
| D-E | Search | **1: one box.** Runs the name search and the meaning search together on Enter (not per key press, because meaning search calls the embedder). Name matches first, then meaning matches labelled "Matches what the code does" |
| D-F | Brand constants | **1: editable in edit mode** (name fixed, value, source), saved as a new version. They tell the AI what to use in new screen code; they **do not recolour the running app** (that is CodeVision's own styles module). The screen says so in one line. The Generator prompt for Screen files gets the brand constants and the UI conventions |
| D-G | Stop a running job | **1: yes, a Stop button.** Stopping keeps the old index and old tags (all or nothing, B1's rule) |

## 3. Shared look (G1, G6, G11), applies to all 8 tabs

One component in `layouts/` (for example `da_admin_card.py`), used by every tab. No tab draws
loose text on the page background.

| Rule | What |
|---|---|
| V1 | **Page title** on every tab, under the header row: tab name (22 px, semibold) and one plain line saying what the tab is for |
| V2 | **Every section is a white card**: white background, 1 px light border, rounded corners (12 px), 20 px inside padding, a soft shadow, on the light grey page background (same as Overview) |
| V3 | **Card header**: icon tile, title (16 px semibold), optional count pill, actions on the right. Body text 14 px, hints 12 px grey |
| V4 | **Grid**: main column 2/3 and side column 1/3, 16 px gaps, like Overview and the 25 Oct concept |
| V5 | **Rows, not paragraphs**: lists are rows with thin dividers; tables have a tinted header row |
| V6 | **Equal tiles**: tiles in one row have the same width and height (Refresh tiles, health tiles) |
| V7 | **Empty states**: icon, one plain line, and the action button, inside the card |
| V8 | Colours and sizes only from `styles/da_admin_styles.py` |

## 4. Repository and index

Main column (cards): **Connection**, **Refresh**, **Exclusions**, **Allowed folders and markers**,
**Server settings** (collapsed). Side column: one card, **Index job**.

**Index job card**, top to bottom:
1. Health pill ("Index is fresh, built 2 h ago" or amber "The code index needs building").
2. Buttons **Delta rebuild** (primary) and **Full rebuild**, each with a confirm box saying what it
   does and the estimate from the last run ("Last full rebuild took about 3 h 10 min").
3. While running: "Step 1 of 2: reading the code, 340 of 1,200 pieces (28%)" with a progress bar,
   then "Step 2 of 2: tagging programs, 12 of 300 (4%)". **Time left** shows after the first 20 items
   ("About 2 h 15 min left"), from the measured speed. Who started it and when. **Stop**.
3a. Progress is written to a small status file by the background job; the page polls every 5 s and
   survives leaving and reopening the page.
4. Last error, if any, in a red box in plain words, with the fix hint (for example "Set Where
   CodeVision's code lives in Server settings").
5. Index health tiles (equal width): built at, programs, pieces, source folder.
6. Recent refreshes (last 10): Full or Delta, Manual or Nightly, who, when, result, duration,
   pieces re-read, programs tagged.

**Refresh card**: three equal tiles. Manual and Nightly selectable in edit mode (Nightly shows a time
field); On every merge disabled with its reason (D-D).

**Work safety (G7)**: with `DA_LLM_PROVIDER=onprem`, a folder scope inside `da_fake_codevision` is
refused ("The made-up practice folder cannot be used at work"), and an empty scope means
`DA_CODEVISION_SRC`. The work seed leaves the scope empty.

**Check command**: `src/da_check_embedder.py` embeds the word "hello" with the work embedder and
prints only the vector size and the time taken, or the real import or connection error. For Gian
to run at work before a rebuild.

## 5. Capability catalog

- One search box (D-E). Placeholder: "Search capability, program, person, or what the code does".
- Remove the two scan buttons (D-C). The catalog header shows "Programs last tagged <time>, with
  index build <id>" and a link to Repository and index.
- AI proposals show in the Unassigned queue as "From the AI scan" cards and in Overview Needs
  attention (G7: fix whatever stops them showing). Approved and rejected states are kept when a
  file changes; only the summary is refreshed.

## 6. UI standards

- Brand constants card: swatch, name, value, source; editable in edit mode (D-F); a one-line note
  "These guide the AI's new screen code. They do not recolour the running app."
- UI conventions card: every rule drawn as a row (ID chip, text, severity pill), editable as in
  fix 1. The count in the header matches the rows drawn.

## 7. Acceptance criteria (Given / When / Then)

| ID | Given / When / Then |
|---|---|
| AH-1 | Given any of the 8 tabs, when drawn, then a page title with the tab name and a one-line purpose shows |
| AH-2 | Given any tab, when drawn, then every section sits inside the shared card component; a test fails if a tab's top-level children are not cards (page title excepted) |
| AH-3 | Given `DA_CODEVISION_SRC` points at a made-up folder with its own `agents/a_vector.py`, `configs/llm_config.py` and `tools/` (fakes with the same names as the DA's packages), when the work embedder is called, then the helper process imports CodeVision's fakes (not the DA's `agents` or `configs`) and returns a vector; one helper serves many texts |
| AH-4 | Given `DA_CODEVISION_SRC` empty or wrong, or the fake `tools` importing a missing library, when a rebuild or the check command runs, then the error names the setting or the missing module in plain words, and no key, header or text is shown |
| AH-4b | Given the helper dies mid-build, then it is restarted once; a second death stops the build with "Not saved" and the old index stays |
| AH-5 | Given an index built from 3 files, when 1 file changes and Delta runs, then only that file's pieces are embedded (fake embedder counts calls), vector N still matches piece N, and the saved index searches the same as a Full rebuild |
| AH-6 | Given a deleted file, when Delta runs, then its pieces are gone from both files |
| AH-7 | Given a running job, when the page is opened, then step, count, percentage and (after 20 items) time left show; when Stop is clicked, the old index and tags stay |
| AH-8 | Given Full, when it finishes, then every module is re-tagged; given Delta, only new or changed modules are sent to the tagger |
| AH-9 | Given tagging fails over 10% of modules, then the new index is still saved and the run row says tagging was not saved |
| AH-10 | Given Nightly at 02:00, when the scheduler time passes with the server running, then one Delta job runs and a row says "Nightly"; a second server process does not start a second job (lock file) |
| AH-11 | Given `onprem` and a scope inside `da_fake_codevision`, when a rebuild starts, then it is refused with the plain line in section 4 |
| AH-12 | Given one search box, when "creates markdown" is entered, then meaning matches show labelled; when a senior's name is entered, name matches show first; no search runs per key press |
| AH-13 | Given AI proposals exist, when the catalog and Overview are drawn, then the cards and the "N AI proposals to review" row show |
| AH-14 | Given UI standards in edit mode, when a brand colour value is changed and saved with a note, then a new version holds it and the swatch shows the new colour |
| AH-15 | Given UI conventions with 2 rules, when drawn, then 2 rows show and the header count says 2 |
| AH-16 | Given a Generator prompt for a Screen file, then it holds the brand constants and UI conventions once |
| AH-17 | Given Refresh in edit mode, then the three tiles are the same width, Manual and Nightly can be picked, On every merge is disabled with its reason |
| AH-18 | Screenshots of all 8 tabs (read and edit) at 1366 by 768; the code-reviewer compares each with the matching demo screen against rules V1 to V8 and lists every miss as Must fix |

## 8. Edge rules

- B1's rules stay: saved together or not at all, the 10% rule, `da_` files never indexed, text never
  logged. Fix 1 and fix 2 tests keep passing, or the plan lists each changed test and why.
- `FakeEmbedder` and `FakeLLMClient` never at work.
- One job at a time (index and tagging share one lock).
- No new library. No new database table (status and runs are JSON files next to the index).
- Layouts in `layouts/`, logic in `agents/`, styles in `styles/`.

## 9. Work facts (do not stop the build)

- WF-11 (part answered 17 Nov 19:25): CodeVision's `src` is `...\Desktop\CodeVision\CodeVision 61\imagebuild\src`; `a_vector` imports `tools` (`payload_generation`, `spirare`, `dataframe_functions`), `configs` (`llm_config`, `app_config`), `os`, `numpy`, `faiss`. Still open: which Python runs CodeVision on the laptop (its own `.venv`?), and whether `tools` or `configs` need libraries or settings files the DA's `.venv` lacks. `da_check_embedder.py` answers this at work.
- WF-12: can Bitbucket tell the server about merges (a webhook to the OCP server)? Decides "On every
  merge".
- WF-9 (still open): how many programs and how long one embed and one tagger call take on Qwen.
