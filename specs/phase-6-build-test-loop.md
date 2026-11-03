# Phase 6: Build + test loop

Status: APPROVED v1.1 (3 Nov 2026). Decisions D-A to D-F chosen by Gian: option 1 for all six
(section 17). Defaults D-G to D-L (section 18) were set by Claude and not objected to.

**What changed in v1.1 (Gian's work-test answers, 3 Nov 2026):**
1. Q11 decided: **tests run only in the server sandbox.** CodeVision has no automated tests today;
   developers test their changes by hand on their laptop. Test files are never written to the
   workspace and never go to Bitbucket. The write job writes planned code files only. Tests and
   their results stay in the app (Tests tab). Changed: sections "In plain words", 3, 8, 9, 12, 14,
   20, 21.
2. Phase 6 removes Phase 5's tests-folder behaviour (new section 15.1, tests 6-35 to 6-40). Phase 5's
   D-A purpose (prove the write door) was met by the 3 Nov work test. Phase 5 merges as is.
3. The sandbox always creates `tests/__init__.py` and `tests/<id>/__init__.py` inside its own
   temporary folder (section 6), since CodeVision has no `tests/` folder.
4. Q15 reworded (section 19).
5. Work laptop limits: PowerShell and DevTools are blocked. Developer instructions use Command
   Prompt only (sections 14, 19, 21).
6. Q12 answered, Q8 answered, Q14 (a) answered: Linux, the OCP server (section 19).
7. Phase 8 carry-forward note added (section 15.2).
Depends on: Phase 5 (`ws_ready`, the write job, the edit guard). **Phase 5 is built on branch
`phase-5` but not merged yet. Do not start this build until `phase-5` is merged into `main`.**
Next: Phase 7, Independent Tester (Layer C, `specs/redesign-2026-10-31.md` section 5.5).
Source of truth for the design: `specs/redesign-2026-10-31.md` section 5.4, section 6 (models and
roles) and section 7 (the "Build and test" Admin row: only its limits become rulebook policy fields
here; the Admin screen is Phase 11). Status names come from the redesign's status table (section 3).
Visual reference: `docs/CodeVision_Developer_Assistant_Demo.html`. Read only the function `tabBuild`,
states `running`, `r1` and `written`. Ignore its `rescan` state and its last state (Phase 8), and
ignore the Tests tab (Phase 7).
Build: fresh Claude Code session, Sonnet, branch `phase-6`.

**Decision D-M (Gian, 3 Nov 2026, while building): Build reuses the Phase 4 lists.** Section 11 listed
`build_protected_files` and `build_approved_libraries` as new policy fields. Phase 4 already has
`protected_files` and `approved_libraries`, with different lists, and two lists could disagree
(Approach would allow a library that Build then blocks). Build now reads the **Phase 4 fields**
(wherever this spec says `build_protected_files` or `build_approved_libraries`, read `protected_files`
and `approved_libraries`); only the other six policy fields are new. Their starter values are the
Phase 4 seed values. A module in `build_blocked_imports` is **never** allowed, even if it is also in
`approved_libraries` (the seed approves `requests`; `requests` is blocked). This changes section 5
(A3, A4), section 11, section 21 and the wording of row 6-31 (it checks the six new fields only).

## In plain words

After Phase 5 the app knows the file plan, the accepted test plan, and has a live connection to the
developer's folder. Phase 6 is where code finally gets written:

1. The Tester turns the accepted test plan into real `unittest` code. Those tests are then **frozen**.
2. The Generator (Qwen) writes the code, **one file per AI call**.
3. **Layer A** (plain Python, no AI) checks the code: does it parse, are the imports allowed, does it
   touch a protected file, does it match the agreed function names.
4. **Layer B** runs the frozen tests on the CodeVision server in a **separate process**, in a
   temporary folder, with a **60-second time limit** (Q13 allows this).
5. Tests fail: a plain failure report goes back to the Generator, which fixes **only the failing
   files**. One shared budget of **3 rounds**.
6. At pass, or when the budget runs out (with a red label), the **code files** are written to the
   developer's folder through the **Phase 5 write job**. That write job is the only door to the
   workspace. Phase 6 adds no new way to write.
7. **The tests never leave the app.** CodeVision has no automated tests, so the tests and their
   results live on the Tests tab only. The developer tests the change by hand on his laptop, as
   today.

Layer C (the Independent Tester's review) is Phase 7. In Phase 6 its slot on screen says "Coming in
Phase 7" (D-F decides the label this gives).

AS400 comparisons:
- The frozen tests are like a signed-off UAT script: the programmer may not edit the script to make
  his program pass. The script stays with the test team (the app); only the program goes into the
  developer's library.
- Layer A is like the compile step: CRTBNDRPG either gives a clean listing or a list of errors.
- Layer B is like `SBMJOB` into a separate batch subsystem with its own `QTEMP` and a maximum CPU
  time: the job cannot touch the interactive session, its scratch library vanishes when it ends,
  and the system ends it if it runs too long.
- The whole build is a batch job: the developer can sign off and come back, like checking
  `WRKSBMJOB` later.

## Words used in this spec

| Word | Meaning |
|---|---|
| Build | One run of the loop for one approach version: tests, code, Layer A, Layer B, rounds, result |
| Round | One pass of: write or fix code, Layer A, Layer B. A build has at most 3 rounds |
| Contract | The agreed public names in each planned code file (functions, classes, arguments), names only, no bodies. Written before the tests (D-B) |
| Generator | The AI role that writes code. Qwen at work (`reasoning-vlm`) |
| Tester | The AI role that writes the tests. Uses the existing `tester` role settings (empty = the generator's model) |
| Frozen | Saved with a fingerprint and never changed by the Generator. Any AI output that tries to change a test is refused |
| Sandbox | A temporary folder on the server plus a separate Python process that runs the tests there, with a time limit and no secrets |
| Reference copy | The CodeVision source folder on the server that the sandbox copies from (D-A) |
| Edit block | A "find this exact text, replace it with this text" instruction for a file that already exists (D-C) |
| Failure report | Plain-language list of failed tests: test ID, criterion ID, what was expected, what happened |
| Label | The result shown to the developer: Ready for your review, Ready with warnings, Not passing, Unable to assess. Never "Approved" |

## 1. The flow (one step at a time)

Same screen as Phase 5. The build has its own small state (section 13) with its own revision number,
like the workspace.

| Step | Where | The developer sees | Then |
|---|---|---|---|
| start | READY_TO_BUILD and workspace `ws_ready` | Button **Build** (replaces "Build (coming in Phase 6)") | Pre-build re-scan (B1) |
| `b_prescan` | Build clicked | Chat: "Checking your folder before I start." | Browser re-scans (Phase 5 section 6). Results saved, then the build starts on the server |
| `b_running` | status BUILDING | Build tab: live progress list (demo `running`). Chat: "Building. This takes a few minutes. You can leave this page." Button **Stop build** | Server works in the background (section 10) |
| `b_round_failed` | a round failed, budget left | Build tab: red banner and failure report (demo `r1`). Chat: "Round 1: 2 of 9 tests failed. Fixing only the failing file." | Next round starts by itself |
| `b_interrupted` | AI or sandbox could not run (not the code's fault) | "The build paused: the AI did not answer." Buttons **Try again**, **Stop build**, **Get help** | Try again resumes at the same step. No round is used |
| `b_done` | pass, or budget used up | Result banner with the label. Chat line as demo `/*35*/` (adjusted for Phase 6) | The write (section 9) |
| `b_written` | the write job finished | Build tab: demo `written` (file table, "Your turn", "This build") | End of Phase 6 |
| `b_write_stopped` | edit guard stopped the write | "You changed `<path>` while I was building. Nothing after it was written." Buttons **Re-scan and build again**, **Get help** | B9 |
| `b_unable` | tests could not be written (section 3) | "I could not write tests from your plan." Buttons **Try again**, **Change the approach**, **Get help** | Nothing is written to the workspace |

Rules for the flow:
- B1: Build is allowed only at READY_TO_BUILD with workspace step `ws_ready` and folder permission
  present (the pre-build re-scan needs the browser). If the re-scan finds a planned file changed by
  the developer, his current text becomes the starting text for the build (saved as `scanned`, and
  used as `expected` at write time). Nothing has been written yet, so nothing is lost (D-K).
- B2: Every step allows one kind of input, as in Phases 2 to 5. Wrong input gets a plain message.
- B3: Every action follows the Approach and Workspace pattern: read with no lock, do the slow work
  (AI call, sandbox run, browser file work) outside any transaction, then ONE write transaction
  saves state, rows, audit events and chat lines. Build revision is used for the stale check
  (the same `STALE_MESSAGE`).
- B4: One build at a time per request. Clicking Build twice starts one build.
- B5: **Stop build** ends the build with no label, writes nothing, and returns to READY_TO_BUILD.
  Audited. A new Build after a Stop is a new build number with a fresh budget (visible in the metrics
  later).
- B6: **Get help** moves the request to ESCALATION_REQUIRED with open item
  `Escalated in Build: <step>`, as Approach and Workspace do.
- B7: **Change the approach** (only from `b_unable`) moves the request back to APPROACH_PROPOSED and
  opens the change box, using the Phase 4 change counter (G9), as Phase 5 rule W5 does.
- B8: While the build runs, the chat asks once: "Please don't edit the planned files until I
  finish." The edit guard protects him if he does (B9).
- B9: **Re-scan and build again** re-scans, takes the new text as the starting text, and starts a new
  build with a fresh budget. Phase 6 never overwrites a file the developer changed. Choosing between
  his version and the AI's is Phase 8.

## 2. Statuses

From the redesign status table. New statuses: **BUILDING**, **READY_FOR_REVIEW**, **NOT_PASSING**.
TESTING and TESTER_REVIEW are not used in Phase 6 (D-L). New moves (add to `ALLOWED_MOVES`, every
move audited as today):

- READY_TO_BUILD to BUILDING (Build, B1)
- BUILDING to READY_TO_BUILD (Stop build, B5; and `b_unable`, which then offers the buttons above)
- BUILDING to READY_FOR_REVIEW (pass, section 8)
- BUILDING to NOT_PASSING (budget used up, section 8)
- BUILDING to ESCALATION_REQUIRED (Get help from `b_interrupted` or `b_unable`)
- READY_TO_BUILD to APPROACH_PROPOSED already exists (Phase 5, W5); reused by B7
- READY_FOR_REVIEW and NOT_PASSING to ESCALATION_REQUIRED (Get help, B6)
- READY_FOR_REVIEW and NOT_PASSING to BUILDING (Re-scan and build again, B9, only from `b_write_stopped`)

The status moves at `b_done` (the result is known), before the write. Whether the files are in the
folder is the build's own write state (`not_written`, `written`, `stopped`), shown on the Build tab.

## 3. Tests first

Happens once per approach version, at the start of the first build. A later build of the same
approach version reuses the same frozen tests (B5, B9).

**Step 1, the contract (D-B).** One Generator call. Input: the accepted approach (file plan, design
choices), the confirmed request record, and the current text of every `modify` file. Output, as JSON:
for each planned code file, the public names it will have (or already has) with their arguments,
and one line each on what they do. Plain-code checks: valid JSON, only planned code files, names are
valid Python names, `modify` files keep every existing public name they list. Saved and frozen.

**Step 2, the tests.** One Tester call. Input: the accepted test plan, the criteria, and the contract.
**Never any code text.** Output: one test file, using only `unittest` (built in) and
`unittest.mock`. It is stored in the app and only ever placed on disk inside the sandbox, as
`tests/<id>/test_<id>.py` (section 6). It is never written to the workspace. Plain-code checks:
- it parses (`ast`),
- every case in the accepted test plan has exactly one test method, named
  `test_<case id>_<criterion id>_<short words>`, for example `test_t6_ac4_empty_sheets_rejected`.
  Cases the developer added in Approach keep their "Yours" tag,
- it imports only `unittest`, `unittest.mock`, standard library modules not on the blocked list
  (section 5), and the names in the contract,
- it does not read or write files outside a temporary folder it creates itself, and makes no network
  calls (Layer A import and call rules, section 5).

A failed check gets one more Tester call with the problems listed (max 2 attempts). Still failing:
step `b_unable`, label "Unable to assess" in the chat, nothing written.

**Step 3, freeze.** The test file text and fingerprint are saved. From now on every Layer B run uses
this saved text. Any Generator output that names a path under `tests/` is refused by Layer A.

## 4. Generating the code

- **One file per AI call**, in file-plan order (B1 in the redesign).
- What each call sends (D-C and Q7): the charter slice (as today), the confirmed request record, the
  accepted approach, the contract, the frozen tests, the current text of THIS file (for `modify`),
  and for the other planned files only their contract lines. Not the full text of other files.
- Before each call, plain code measures the prompt. Over `build_max_prompt_chars`: the build stops at
  `b_interrupted` with "This file is too big to send to the AI in one go." and offers Get help. A
  reply of HTTP 400 ("too much context" at work) is treated the same way. Neither uses a round.
- **New files** (`create`): the reply is the whole file text.
- **Existing files** (`modify`), D-C option 1: the reply is a list of edit blocks. Plain code applies
  them to the starting text. Each block's "find" text must appear exactly once, else the round fails
  Layer A with "Edit block 2 did not match the file." The result keeps the file's line-ending style
  (Phase 5 D-G).
- **Fix rounds:** only the failing files are sent again (section 7), with the failure report and that
  file's current version from this build. The other files stay as they are.

## 5. Layer A (plain code, no AI)

Runs on every code file of the round. Any problem fails the round (one round used) and goes into the
failure report.

| Check | Rule |
|---|---|
| A1 Syntax | `ast.parse` succeeds |
| A2 Planned files only | the file is in the accepted file plan; never `tests/`, never a protected file |
| A3 Protected files | not in `build_protected_files` (policy, section 11) |
| A4 Imports | each import is the standard library, a library in `build_approved_libraries`, or a CodeVision module (path under the reference copy's `src/`). Never a module in `build_blocked_imports` |
| A5 Risky calls | none of `eval`, `exec`, `compile`, `__import__`, `os.system`, `os.popen`, `os.exec*`, `os.spawn*` |
| A6 Contract | every contract name for this file exists with the agreed arguments |
| A7 Rulebook rules | the rulebook's existing plain-code rules that apply to code text (the plan lists which ones exist today and which apply; none are invented here) |

Flag-for-review zones (redesign section 7) never block. Phase 6 only records which planned files fall
in a zone if the rulebook already has zones; the PR summary uses it in Phase 10.

## 6. Layer B (the sandbox, Q13)

**What goes in the temporary folder (D-A option 1):**
1. A copy of the reference copy's Python source tree (`src/`). Never `.env`, `*.db`, `.git`, or
   anything matching `build_sandbox_exclude`.
2. On top: this round's version of every planned code file.
3. The sandbox's own tests folder, always created here (CodeVision has no `tests/` folder, Q11):
   empty `tests/__init__.py` and `tests/<id>/__init__.py`, plus the frozen test file as
   `tests/<id>/test_<id>.py`. These exist only inside the temporary folder.
4. Our small runner script (new, `src/agents/da_sandbox_runner.py`), copied in.

Where `tests/` sits (top folder or inside `src/`) and the working folder follow the Q15 answer, so
that the test file imports CodeVision modules the same way CodeVision imports its own.

**How it runs:**
- A separate process: the server's own Python (`sys.executable`) running the runner script in
  isolated mode (`-I`), working folder = the temporary folder.
- **No secrets:** the process gets a fresh, nearly empty environment (only what Python needs to
  start on the Linux OCP server, such as `PATH`, with `HOME` and `TMPDIR` pointing at the temporary
  folder). No `DA_*` keys, no API keys.
- **Time limit:** `build_test_timeout_seconds` (60). At the limit the whole process tree is ended,
  the run is "Timed out", the report names the test that was running, and the round counts as failed.
- **Output limit:** captured output is cut at 200 KB.
- The runner runs `unittest` discovery on `tests/<id>/` only and writes one `results.json`: per test,
  its name, result (pass, fail, error, skipped), the assertion message, and the last 20 lines of the
  traceback. The server reads only that file and the cut output.
- The temporary folder is deleted at the end, whatever happened.

**Honest limits (say them in the plan, do not hide them):** a separate process with a time limit and
no secrets is not a full jail. It does not block the network at the operating-system level and does
not cap memory. Layer A's import and call rules plus "no keys in the environment" are the guard.
Q14 (d) asks the CodeVision team whether the OCP server can add more.

**A run that cannot start** (Python missing, folder cannot be made, reference copy not found) is not
the code's fault: step `b_interrupted`, no round used.

## 7. Rounds, budget and the failure report

- One shared budget of `build_max_rounds` (3) per build. Round 1 is the first full write.
- A round fails if Layer A finds a problem, or Layer B has any test that fails, errors or times out.
- Things that are not the code's fault never use a round: AI not answering after the existing retries
  (407 retry, MAX_RETRY), prompt too big, sandbox cannot start. They pause at `b_interrupted`.
- **Which files are fixed (D-J):** the planned code files named in the failing tests' tracebacks. If
  none is named (for example a plain assertion failure), the files whose contract names the failing
  tests use. Never the tests.
- **The failure report** is built by plain code, not AI, in two forms:
  - for the developer (Build tab, demo `r1`): test ID, "Yours" tag, criterion ID, one plain sentence
    from the test method's docstring of what was expected, and the assertion message,
  - for the Generator: the same, plus the cut traceback lines, plus any Layer A problems.
- Rounds and tests are saved per round, so the Build tab can show the history.

## 8. Results and labels

| Situation | Status | Label (D-F option 1) | Written to workspace? |
|---|---|---|---|
| All tests pass, Layer A clean | READY_FOR_REVIEW | **Ready with warnings**, with the fixed warning "The independent Tester review (Layer C) is not built yet." | Yes, code files only |
| Budget used, still failing | NOT_PASSING | **Not passing** (red). The last round's failure report stays on the Build tab | Yes, code files only (redesign B4), with the red label in the app |
| Tests could not be written | READY_TO_BUILD (step `b_unable`) | Unable to assess (chat only) | No |

The label lives in the app, never inside the code files (no generated comments about it).

## 9. Writing to the workspace (Phase 5 write job only)

- One write job per build, built by the Phase 5 job builder: **every planned code file, nothing
  else.** The test file is never in a write job (the job builder refuses any path under `tests/`).
- `expected` per file: for `modify`, the starting text's fingerprint (baseline, or the pre-build
  re-scan, B1); for `create`, "absent" on the first write of this request, else the last `written`
  fingerprint.
- No folder is ever created. Every planned file's parent folder already exists (Phase 5 blocker B5).
- The browser runs it exactly as Phase 5 section 5: walk the path, refuse anything not in the job,
  edit guard, write, read back, report fingerprints. The server saves `written` rows and the audit
  event as in Phase 5.
- **When the write happens (D-E option 1):** as soon as the build reaches `b_done` and the page is
  open with permission, the page runs the write job by itself and says so in the chat. If the page is
  closed, it runs the next time he opens this request. If permission is gone, the chip shows
  **Reconnect** (Phase 5 W4); after his click the write runs.
- **Edit guard stop:** `b_write_stopped` (B9). Files before the stop stay written, the message lists
  both groups, as in Phase 5.
- **Download mode** (Phase 5 fallback): Download ZIP holds the build's code files only, with full
  paths, with the same "upload your folder before every new download" line.

## 10. Running in the background (D-D option 1)

- The build runs in a background thread inside the server process. Each step writes its progress to
  the database before and after (section 13), so the database, not the thread, is the truth.
- The page asks for progress every 3 seconds with a Dash `dcc.Interval` while the step is
  `b_running` or `b_round_failed`, and stops asking otherwise.
- At most `build_max_parallel` (2) builds run at once on the server (the AI is shared). A third waits
  with "Waiting for a free slot (1 ahead of you)."
- **Server restart during a build:** at start-up, any build still marked running is set to
  `b_interrupted` with "The server restarted during your build." **Try again** resumes from the last
  saved step (finished files are not regenerated, the round count is kept).
- No new library.

## 11. Rulebook policy additions

Same pattern as Phase 4 section 7 and Phase 5 section 8: new `Policy` fields with defaults equal to
the starter values, so older rulebook versions still load. Admin screens for them are Phase 11.

| Field | Meaning | Starter value (made up, real values set at work) |
|---|---|---|
| `build_max_rounds` | Shared round budget per build | 3 |
| `build_test_timeout_seconds` | Layer B time limit per run | 60 |
| `build_max_prompt_chars` | Largest prompt sent in one AI call (Q7 guard) | 60000 |
| `build_max_parallel` | Builds running at once on the server | 2 |
| `build_protected_files` | Files the AI may never write | `.env`, `src/web_server.py`, `src/configs/llm_config.py` |
| `build_approved_libraries` | Third-party libraries generated code may import | `dash`, `dash_mantine_components`, `pydantic`, `pandas`, `openpyxl` |
| `build_blocked_imports` | Modules generated code and tests may never import | `subprocess`, `socket`, `ctypes`, `multiprocessing`, `urllib`, `http`, `requests`, `ftplib`, `smtplib`, `telnetlib`, `webbrowser` |
| `build_sandbox_exclude` | Patterns never copied into the sandbox | `.env`, `*.db`, `.git`, `*.key`, `*.pem` |

The reference copy's location is a server setting, not a rulebook field: `DA_SANDBOX_SOURCE_DIR` in
`.env`. At home it points at a small made-up CodeVision-shaped folder the builder creates for tests
(for example `tests/fixtures/da_reference_codevision/`), matching the paths the fake plan uses.

## 12. Screen

Use the existing `da_web_components` helpers where they exist.

- **Build tab** (demo `tabBuild`):
  - `running`: blue banner "Round 1 of 3. Running on the server. You can leave this page and come
    back." Progress list: tests written (🔒 Frozen), one line per file, Layer A, Layer B (with "Time
    limit 60 seconds per run"), Layer C "Coming in Phase 7". Elapsed time per line.
  - Three layer boxes: "Does it run?" (A), "Does it behave?" (B), "Matches the agreement?" (C:
    "Coming in Phase 7").
  - `r1`: red banner and the failure report table, with "Only `<file>` is regenerated. Tests stay
    frozen. 1 shared budget of 3 rounds."
  - `written`: green banner (or red for NOT_PASSING), the Phase 5 file table with Status "Written",
    "Your turn": "Try it yourself: start CodeVision on your laptop and test the change by hand.",
    then "Edit anything, then click Re-scan" and "Tell me if a requirement is missing". No line about
    running tests (they stay in the app). "This build" (rounds used, tests passing, time taken).
  - `not_written`: "Built, not written yet. Open this request with your workspace allowed."
- **Tests tab:** the only place the tests live. In Phase 6: the frozen test list (test ID, criterion
  ID, "Yours" tag, one-line description), the result of each round, and a **View test code** toggle
  that shows the frozen test file read-only. One line under the list: "These tests run on the
  CodeVision server. They are not copied to your folder." The Tester's 7-check report is Phase 7.
- **Header chip:** unchanged from Phase 5, plus P26's new wording (section 15).
- **Composer:** buttons only on every build step (2D control).
- "My recent requests" reopens at the same step, with live progress if the build is still running.

## 13. Storage

New file `db_table_functions/db_tbl_da_build.py`, same style as `db_tbl_da_workspace.py`. New tables,
`CREATE TABLE IF NOT EXISTS`. Nothing in existing tables changes. The Phase 5 tables are reused for
everything that touches the folder (`scanned` and `written` rows).

| Table | Holds | Rule |
|---|---|---|
| `da_build_state` | request ID, current build number, step, own revision, write state | one row per request, revision goes up by 1 with every save |
| `da_build_runs` | request ID, build number, approach version, started, ended, rounds used, result status, label, stop reason | one row per build; updated only to close it |
| `da_build_files` | request ID, build number, round, path, kind (`contract`, `test`, `code`), text, fingerprint, made by (generator, tester), created time | append-only |
| `da_build_rounds` | request ID, build number, round, Layer A result JSON, Layer B results JSON, failure report text, timed out (yes/no), created time | append-only |
| `da_build_progress` | request ID, build number, line number, text, state, started, ended | append-only lines for the live progress list |

Audit events (actor in brackets): `build_started` (developer), `build_prescan` (system, counts),
`contract_written` (system), `tests_written` (system, test count), `tests_frozen` (system,
fingerprint), `code_generated` (system, path, round), `layer_a_result` (system), `layer_b_result`
(system, passed and failed counts, timed out), `round_failed` (system), `build_passed` (system),
`build_not_passing` (system), `build_interrupted` (system, why), `build_resumed` (developer),
`build_stopped` (developer), `workspace_written` and `workspace_write_stopped` (reused from Phase 5),
`approach_reopened`, `escalated`. Every status move is audited, as today.

## 14. Testing without work

- **pytest, plain rules:** contract checks, test-file checks (one method per case, naming, imports),
  Layer A (each check with good and bad made-up code), edit-block apply (match once, no match, two
  matches, keeps `\r\n`), file-to-fix choice, failure report wording, round and budget counting,
  "not the code's fault" never uses a round, prompt-size guard.
- **pytest, the real sandbox:** runs real subprocesses on the made-up reference folder (no AI, no
  internet, allowed by the house rules): a passing test file, a failing one, one that sleeps past a
  short time limit (the test sets the limit to 2 seconds), one that prints 1 MB, one that reads an
  environment variable and finds no key. Proves the folder is deleted afterwards.
- **Fake provider (home):** a fixed script. Contract and tests first; round 1 fails one test; round 2
  passes. Test-only switches (in tests, not the app) force: always failing (cap), a timeout, a bad
  edit block, a Tester that writes a bad test file twice, an AI that does not answer.
- **Pretend work server** (127.0.0.1:8070): answers the build prompts with the same fixed script, so
  the onprem connector path is tested end to end.
- **Playwright (cloud session only):** as in Phase 5, the private test folder stands in for the
  picker. A full request from READY_TO_BUILD reaches `b_written`; the code files exist in that
  folder with the reported fingerprints, and no `tests/` folder exists there.
- **Smoke check:** a full request from `ws_ready` through BUILDING (fake provider, real sandbox, fake
  browser bridge) to READY_FOR_REVIEW, then `b_written`.
- **Home check by Gian:** on `http://127.0.0.1:8050` with `DA_LLM_PROVIDER=fake` and a COPY of the
  repo as the workspace. Leave the page during the build and come back. Check that only code files
  were written (no `tests/` folder), then open the Tests tab to see the tests and their results.
- **Instructions for work developers** (README, `docs/build-work-test.md`, any on-screen command):
  Command Prompt only. PowerShell and DevTools are blocked on work laptops.

## 15. Carried forward

| ID | What |
|---|---|
| P26 | A different folder with the same name as the linked one currently gets "Re-scan first". The browser compares the picked folder with the remembered one (`isSameEntry`). Different folder, same name: "This is a different folder that is also called codevision. Use **Change** to link it." Test: same name, different folder gives the new wording; same folder still passes |
| Q7 | Server context limit per model: still unknown. Phase 6 does not depend on the answer: `build_max_prompt_chars` and the HTTP 400 handling (section 4) stop cleanly. When the limit is known, set the policy value from it (roughly 3 characters per token, minus room for the reply) |

### 15.1 Phase 5 tests-folder behaviour removed (v1.1)

Phase 5 merges as is. Phase 6 then removes everything that touches a tests folder in the workspace,
because tests never go there (Q11). Phase 5's D-A purpose, proving the write door on a real laptop,
was met by the 3 Nov work test.

| ID | Phase 5 behaviour | Phase 6 change |
|---|---|---|
| C1 | The workspace check writes `tests/<id>/__init__.py` (Phase 5 section 4, D-A) | No write at the workspace check. A passing check saves baselines only, then `ws_ready`. Chat drops "Tests folder created"; the Build tab file table drops the tests folder row |
| C2 | The writer may create `tests/` and `tests/<id>/` (Phase 5 section 5 step 1) | The writer creates **no folders at all**. A job path whose parent folder is missing is refused |
| C3 | Blocker B7 "Tests folder in use" | Dropped. The browser no longer collects tests folder facts |
| C4 | Re-scan reads planned files and the tests folder; result "New in tests folder" | Re-scan reads **planned files only**. The "New in tests folder" result is dropped |
| C5 | Fallback ZIP holds `tests/<id>/__init__.py`; upload sends planned and tests folder files | ZIP holds **code files only**; upload sends **planned files only** |
| C6 | Phase 5 "Words": the tests folder is "the only folder the app may create" | Word removed: the app creates no folder in the workspace |

Old rows already saved for `tests/<id>/__init__.py` (home test data only) stay in the tables and are
ignored. Requests already at `ws_ready` keep working. Developers who got the file from the Phase 5
work test delete it by hand.

### 15.2 Note for the Phase 8 spec (no work in Phase 6)

The developer adds test cases **in the app** (as in Phase 4 "Add a test case"), not as files in his
folder. Redesign section 5.7's "his new tests", and the tests-folder parts of R2 and R4, need
rewording in the Phase 8 spec.

## 16. Out of scope

- Layer C, the Independent Tester's 7 checks and its Must fix / Should fix findings (Phase 7). The
  Tester bake-off (Q9) is a work-test item, not code.
- Sending the developer's own edits through the layers, patching his current file on a rebuild,
  side-by-side conflict choice, restore, the three Refine lanes (Phase 8).
- Enhance: safety-net tests first, "what must NOT change" (Phase 9).
- Auto-escalation on "cap hit twice in a row", the Escalations inbox, Handoff and the final
  fingerprint check (Phase 10).
- Admin screens for the new policy fields, the new metrics (Phase 11).
- Any Git command. The app never commits, pushes or pulls.
- Writing tests to the workspace or Bitbucket, in any phase (Q11). Tests stay in the app.
- Building again from READY_FOR_REVIEW or NOT_PASSING (except B9). That is Refine (Phase 8).

## 17. Decisions (chosen by Gian, 3 Nov 2026: option 1 for all six)

| # | Question | Options (ranked) | Recommendation |
|---|---|---|---|
| D-A | What does the sandbox run the tests against? The server cannot see the laptop, and the browser may only read planned files (Phase 5 R1) | 1. A copy of the server's own CodeVision source (the reference copy) with this build's planned files laid on top. 2. Only the planned files and the tests; the Tester must mock every other CodeVision import. 3. Upload the whole workspace from the browser | **1**: the tests can import real CodeVision modules, as the developer's own run will. Risk: the server copy can be older than his folder (an import error in a file outside the plan). Phase 9's freshness check narrows that. Option 2 makes tests fragile and mock-heavy. Option 3 breaks Phase 5 R1 (read only planned files) |
| D-B | Tests come first, but how does the Tester know the function names before any code exists? | 1. A contract step: one Generator call writes the public names and arguments per file (names only), frozen with the tests; the Tester sees the contract, never code; Layer A A6 checks the code matches. 2. The Tester invents the names and the code must follow. 3. Use names already in the Phase 4 file plan | **1**: it keeps "the Tester never sees code" and gives both sides one agreement. Option 2 breaks on `modify` files (the Tester cannot know existing names without code). Option 3 only if the Phase 4 file plan already lists function names: **the builder checks this first** and, if it does, uses it as the contract and skips the extra call |
| D-C | How does the Generator change a file that already exists? | 1. Edit blocks (find exact text, replace); whole text for new files. 2. Whole file every time. 3. Whole file if under N lines, edit blocks above | **1**: smaller replies (a 400-line file is not retyped), untouched lines stay byte for byte, and Phase 8 needs exactly this to patch the developer's edited file. Risk: the model gets the "find" text slightly wrong; that fails Layer A with a clear message and uses a round. If the bake-off shows frequent misses, switch to option 3 later |
| D-D | How does a build that takes minutes run? | 1. A background thread in the server, progress saved to the database, the page polls every 3 s. 2. Dash background callbacks (needs `diskcache` or Celery, a new library). 3. A separate worker program on the server | **1**: no new library, nothing new for the CodeVision team to run, and the database keeps the truth across a restart (section 10). Option 3 is sturdier at scale; revisit if many developers build at once |
| D-E | When are the files written to the folder? | 1. Automatically as soon as the build is done and the page is open with permission (else on next open, or after Reconnect). 2. A **Write to my workspace** button. 3. Each file as soon as it is generated | **1**: matches the redesign ("written at pass") and the demo; the edit guard makes it safe. Option 2 adds a click every build. Option 3 writes code that has not passed, mid-round |
| D-F | Which label at pass, while Layer C does not exist yet? | 1. **Ready with warnings**, with the fixed warning "The independent Tester review (Layer C) is not built yet." 2. **Ready for your review** (green) 3. A temporary fifth label "Tests passing" | **1**: honest and uses only the four agreed labels. Green would claim a check that never ran. Option 3 adds a label Phase 7 must remove |

**v1.1 check of the choices against the 3 Nov answers:** D-A, D-B, D-C, D-E and D-F stand unchanged
(D-E now writes code files only; D-A's sandbox always builds its own tests folder). **D-D stands but
has one new risk:** OCP can run several copies of CodeVision and restarts them on every deploy. The
restart is already handled (section 10). If Q14 (e) says "several copies", the builder stops and
asks before building section 10, because the progress poll may reach a copy that is not running the
build, and `build_max_parallel` would count per copy.

## 18. Defaults Claude chose (say if you disagree)

| # | Choice | Alternative | Why |
|---|---|---|---|
| D-G | The Tester writes ONE test file per request, in one AI call, max 2 attempts; failing that is `b_unable`, not a round | One call per test case | Fewer slow calls; the round budget is for the code, not for test writing |
| D-H | Problems that are not the code's fault (AI down, prompt too big, sandbox cannot start, server restart) pause the build and never use a round | Count them as failed rounds | The budget measures the code's quality, not the network's |
| D-I | Layer A blocks risky imports and calls (A4, A5); the sandbox runs with no secrets. No OS-level network block in Phase 6 | Wait for an OS-level jail | Q13 allows a separate process; Q14 asks for more. Honest limits stated in section 6 |
| D-J | Files to fix = planned files named in the failing tracebacks, else the files whose contract names the failing tests use | Regenerate every file each round | Matches "fix only the failing files" and keeps rounds fast |
| D-K | A pre-build re-scan takes the developer's latest edits as the starting text | Block the build until he re-runs the workspace check | Nothing is written yet, so his edit is simply the new starting point |
| D-L | Only BUILDING while the loop runs (TESTING and TESTER_REVIEW unused); the live progress list shows the sub-step | Flip BUILDING and TESTING every round | Fewer status moves and audit noise; TESTER_REVIEW arrives with Phase 7 |

## 19. Open questions (for the work test, round 2)

- **Q7** (carried): the server's context limit per model name. Sets `build_max_prompt_chars`.
- **Q11 Decided (Gian, 3 Nov):** CodeVision has no automated tests and no `tests/` folder.
  Developers test their changes by hand on their laptop. Tests run only in the server sandbox and
  stay in the app (section 15.1).
- **Q14** (for the CodeVision team): (a) **Answered (Gian, 3 Nov): Linux, the OCP server.** Still
  open: (b) the folder of the deployed CodeVision source on the OCP server (the reference copy,
  D-A), and how close it is to Bitbucket `main`; (c) does importing any CodeVision module connect to
  a database, the LLM or a file share at import time; (d) can child processes started by CodeVision
  be blocked from the network, or limited in memory; (e) does CodeVision run as one copy or several
  copies on OCP, and do the copies share one database? (Affects D-D, see section 17 note.)
- **Q15** (reworded, 3 Nov): Which folder and command do developers use to start CodeVision on their
  laptop, and how do CodeVision modules import each other (for example
  `from web.web_components import ...` run from `src`)? This sets the sandbox's working folder and
  the test file's imports.
- **Q8 Answered (Gian, 3 Nov):** the folder picker works in Chrome on the work laptop, and "Allow on
  every visit" is offered.
- **Q12 Answered (Gian, 3 Nov):** developers keep CodeVision on the C drive, usually
  `Desktop\codevision`. Chrome allows folders inside the Desktop, but not the Desktop itself. The
  picker hint can say: "Pick your codevision folder, for example Desktop\codevision."
- **Work laptop limits (3 Nov):** PowerShell and DevTools are blocked. Every developer instruction
  uses Command Prompt only.

Questions about photos: none needed for this spec. If Q15 is easier to answer with a photo of
CodeVision's start command or one module's first 10 lines, cover names and paths first.

## 20. Done when (every line becomes a test, Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| 6-1 | READY_TO_BUILD with workspace `ws_ready` | the screen is drawn | Build is active; without `ws_ready` it is not |
| 6-2 | a planned file edited on disk before Build | Build is clicked | the pre-build re-scan saves it as `scanned` and the build starts from that text |
| 6-3 | Build | it starts | status BUILDING, step `b_running`, audit `build_started` |
| 6-4 | an approach | the contract step runs (fake) | the contract is saved, frozen, and lists only planned code files |
| 6-5 | a contract | the Tester writes tests | one test method per test-plan case, named with case and criterion IDs; Tester input holds no code text |
| 6-6 | a Tester reply missing one case, twice | tests are checked | step `b_unable`, nothing written, no round used |
| 6-7 | frozen tests | a Generator reply names a path under `tests/` | refused by Layer A |
| 6-8 | a `create` file | generated | the whole text is used; one AI call per file |
| 6-9 | a `modify` file and edit blocks that each match once | applied | the result is correct and keeps `\r\n` if the file had it |
| 6-10 | an edit block matching zero or two places | applied | Layer A fails the round with "Edit block N did not match" |
| 6-11 | code with a syntax error, a blocked import, `eval`, a protected path, a missing contract name | Layer A runs | each is named in the failure report; the round fails |
| 6-12 | a prompt over `build_max_prompt_chars`, or an HTTP 400 reply | the call is about to run or returns | `b_interrupted` with the "too big" message; no round used |
| 6-13 | a passing test file | Layer B runs | results saved per test; the temporary folder is gone afterwards |
| 6-14 | a test that sleeps past the limit | Layer B runs | the process is ended, "Timed out" names the test, the round fails |
| 6-15 | a test that reads an API-key environment variable | Layer B runs | the variable is not there |
| 6-16 | the reference copy holding `.env` and a `.db` file | the sandbox is built | neither is copied |
| 6-17 | a test printing 1 MB | Layer B runs | output saved is cut at 200 KB |
| 6-18 | round 1 fails one test (fake) | the round ends | step `b_round_failed`, failure report shows test ID, criterion, expected; only the traced file is regenerated in round 2 |
| 6-19 | the AI does not answer after retries | mid-build | `b_interrupted`, round count unchanged; Try again resumes at the same step |
| 6-20 | round 2 passes (fake) | the build ends | status READY_FOR_REVIEW, label Ready with warnings with the Layer C warning (if D-F is 1) |
| 6-21 | always-failing code (fake switch) | 3 rounds end | status NOT_PASSING, label Not passing, files still written |
| 6-22 | `b_done` and the page open with permission | the step is reached | the Phase 5 write job writes the planned code files only (no test file, no folder), reads back, saves `written` rows, step `b_written` |
| 6-23 | `b_done` with the page closed | the request is opened later with permission | the write runs then |
| 6-24 | a planned file edited during the build | the write job runs | edit guard stops at that file, both lists shown, `b_write_stopped`, Re-scan and build again offered |
| 6-25 | Re-scan and build again | clicked | new build number, fresh budget, starts from his text, same frozen tests |
| 6-26 | a build running | Stop build | status READY_TO_BUILD, nothing written, audit `build_stopped` |
| 6-27 | a build marked running at server start-up | the server starts | it becomes `b_interrupted` with the restart message; Try again does not regenerate finished files |
| 6-28 | 2 builds running and `build_max_parallel` 2 | a third Build is clicked | it waits with the "free slot" message, then runs |
| 6-29 | any build action | sent with an old revision | refused with the stale message |
| 6-30 | `b_interrupted`, `b_unable` or a finished build | Get help | ESCALATION_REQUIRED with open item `Escalated in Build: <step>` |
| 6-31 | a rulebook version saved before Phase 6 | it is loaded | the new fields hold the starter values |
| 6-32 | a different folder with the same name as the linked one (P26) | it is picked | the "different folder" wording shows; the same folder still passes |
| 6-33 | the onprem provider pointed at the pretend work server | a full build runs | it reaches READY_FOR_REVIEW through the onprem connector |
| 6-34 | Playwright with the private test folder | a full request runs from READY_TO_BUILD | `b_written`; the code files exist with the reported fingerprints; no `tests/` folder exists |
| 6-35 | a good folder (C1) | the workspace check passes | baselines saved, step `ws_ready`, no file written, no `tests/` folder created, no "Tests folder created" line |
| 6-36 | a write job whose path has a missing parent folder (C2) | the writer runs | refused on both the browser and server side; no folder is created |
| 6-37 | a write job that includes a path under `tests/` | the job is built | the job builder refuses it |
| 6-38 | a folder holding an old `tests/cvda_2026_0001/` with files (C3) | the check runs | it passes; no B7; the tests folder is not read |
| 6-39 | `ws_ready` and a `tests/` folder in the workspace (C4) | Re-scan is pressed | only planned files are read; no "New in tests folder" result exists |
| 6-40 | fallback (C5) | Download ZIP is pressed, then a folder is uploaded | the ZIP holds only code files and `READ_ME_FIRST.txt`; the upload sends only planned files |
| 6-41 | the sandbox is built for a reference copy with no `tests/` folder | Layer B runs | `tests/__init__.py`, `tests/<id>/__init__.py` and the test file exist in the temporary folder only, and discovery finds the tests |
| 6-42 | the Build tab at `b_written` | it is drawn | "Try it yourself: start CodeVision on your laptop and test the change by hand." shows; no "run the tests" line |

Plus: `pytest` 0 failures, `ruff check` 0 problems, smoke check passes, code reviewer 0 Must fix, and a
home check by Gian on `127.0.0.1:8050` with a COPY of the repo as the workspace.

## 21. Files the builder will touch (for planning, not a limit)

`pydantic_classes/da_models.py` (statuses and moves), `da_build_models.py` (new),
`da_rulebook_models.py` and `data/da_rulebook_seed.json` (policy fields), `agents/da_build_flow.py`,
`da_build_checks.py` (Layer A, contract and test-file checks, edit blocks, failure report),
`da_sandbox.py` (Layer B), `da_sandbox_runner.py` (copied into the sandbox), the Generator and Tester
prompts under `data/`, `agents/da_llm_client.py` (fake script and pretend-server answers for the build
prompts), `db_table_functions/db_tbl_da_build.py` (new), `agents/da_workspace_flow.py`,
`da_workspace_checks.py` and `web/da_workspace.js` (reuse the write job; P26; section 15.1
removals), `layouts/da_developer_assistant_page.py`, the page
callbacks, `web/da_web_components.py` (Build and Tests tabs), `da_smoke_check.py`, the made-up
reference folder under `tests/fixtures/`, `.env.example` (`DA_SANDBOX_SOURCE_DIR`), `README.md`,
`CLAUDE.md` ("Current phase"), `docs/build-work-test.md` (new: Q14 and Q15 steps, Command Prompt
only), `docs/workspace-work-test.md` (drop DevTools steps, mark Q8 done), and the matching
tests.
