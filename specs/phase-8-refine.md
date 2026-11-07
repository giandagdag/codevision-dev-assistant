# Phase 8: Refine (3 lanes, revision mode, edit protection)

Status: DRAFT v0.1 (7 Nov 2026). Written by the spec writer. The chief applies the decision rule
(`specs/phase-a-automation.md` section 6) to D-A to D-N (section 16). The work facts (section 17)
need Gian and get no recommendation.
Depends on: Phase 7 (Layer C, labels, findings, Tests tab), merged into `auto/phases-7-10`.
Next: Phase 9, Enhance an existing program.
Source of truth: `specs/redesign-2026-10-31.md` sections 3 (statuses, Summary tab version history),
5.1 (revision mode), 5.4 (fresh budget per rebuild), 5.7 (Refine and re-scan, R1 to R6). Status
names come from the redesign status table.
Facts: **no `specs/phase-8-facts.md` was given.** Facts here come only from the approved specs of
Phases 2D, 4, 5, 6 (v1.1 and the 6 Nov fixes) and 7. Nothing new about work is assumed.
Visual reference: `docs/CodeVision_Developer_Assistant_Demo.html`. Read only: chat entries `/*38*/`
to `/*45*/`, the `tabBuild` states `rescan` and the last state (`v2`), and the "Your review" lane
buttons (`ws` entry at `upto:39`). **Ignore** every place the demo says the tests are written to the
workspace (for example `/*35*/` and the `rescan` banner): Q11 (3 Nov) moved tests into the app.
Build: worker team, branch `auto/phase-8`, merged into `auto/phases-7-10` by the chief.

## In plain words

After Phase 7 the developer has code in his folder and a label (green, yellow, red or grey). Today
he can only accept Should fix findings or ask for help. Phase 8 lets him **refine**:

1. **Re-scan after a build.** He edits a file, clicks Re-scan, and sees his changes side by side
   with what the app wrote.
2. **Check my edits.** His edited code goes through Layers A, B and C, exactly like AI code (R2).
   If his edit breaks a test he gets three ways out (R3).
3. **Tell me what to refine.** He types feedback. The AI suggests a **lane**, he confirms with a
   button:
   - **Requirement change:** Understand reopens in revision mode, asks only about the change, shows
     a diff, and saves **record v2** (same CVDA number). Approach and test plan are updated, then a
     rebuild.
   - **Approach change:** the approach gets a new version (the record does not), then a rebuild.
   - **Bug:** the Tester writes a test that shows the bug, he confirms it in one click, and the
     Generator fixes only what the test traces to.
4. **"Fix it"** on a Should fix finding now works (it was greyed in Phase 7).
5. **His edits are protected (R5):** never overwritten unscanned (built in Phase 5), rebuilds patch
   his current file, if the AI touches a line he edited he picks per conflict, and every version
   is kept on the server with one-click restore.
6. **Tests stay in the app (Q11).** His own extra test cases are added on the Tests tab in plain
   language, never as files in his folder.

AS400 comparisons:
- The **requirement lane** is amending the signed change request: the form gets revision 2, the
  same request number, and the reviewer sees what changed in the margin.
- The **approach lane** is changing the program spec (which members, which design) while the user's
  request stays the same.
- The **bug lane** is a problem report that must come with a **recreate step**. No recreate, no fix:
  the test that fails today is the recreate step.
- **Edit protection** is two programmers on one source member. Before the app saves, it compares the
  member with the version it last saw (like `CMPPFM`). If both changed the same lines, a person picks.
- **Restore** is restoring the member from the save file of an earlier build: one command, the
  earlier text is back.

## Words used in this spec

| Word | Meaning |
|---|---|
| Refine | One run of a lane: the developer's feedback, the chosen lane, and what followed, up to the rebuild's result. Numbered per request (Refine 1, 2...) |
| Lane | Requirement, Approach or Bug. Decides what changes before the rebuild |
| Revision mode | Understand started from the last confirmed record, asking only about the change |
| Record v2 | The next confirmed version of the request record, same CVDA number. `da_request_records` is keyed by (request_id, version) already |
| Rebuild | A Phase 6 build started by a lane. New build number, **fresh budget of 3 rounds** |
| Check run | Layers A, B and C on the files as they are in his folder. No Generator call, no fix rounds, no budget used |
| His lines | Lines that differ between the last version the app wrote and his scanned version (found with `difflib`) |
| Conflict | A place where the Generator's change touches or overlaps his lines |
| Last tested | The set of file fingerprints that the last finished build or check run tested. Phase 10's final fingerprint check compares with it |
| Repro test | The bug lane's test that shows the bug. It must fail on today's code (D-F) |

## 1. Decisions already made (do not reopen)

| # | Decision | Source |
|---|---|---|
| 1 | Three lanes: Requirement (new record version), Approach (new approach version, no new record version), Bug (neither) | Redesign 5.7 |
| 2 | The AI suggests the lane; the developer confirms with a button | Redesign 5.7 |
| 3 | Revision mode starts from the last confirmed record, asks only about the change, shows a diff; confirm saves the next version, same CVDA number | Redesign 5.1 |
| 4 | Every rebuild after a Refine gets a fresh budget of `build_max_rounds` | Redesign 5.4 (B3) |
| 5 | Tests are written once per approach version and frozen. The Generator never edits any test, including the developer's own | Redesign 5.4 (B2), 5.7 (R4) |
| 6 | His edits go through all three layers like AI code | Redesign 5.7 (R2) |
| 7 | If his edit breaks a test: Fix my edit (bug lane), My edit is right (requirement lane), I'll fix it myself | Redesign 5.7 (R3) |
| 8 | Edit protection R5.1 to R5.4. R5.1 (edit guard) is already built in the Phase 5 writer and is not changed | Redesign 5.7, Phase 5 D-C |
| 9 | Bug lane: the Tester writes a test that reproduces the bug; the developer confirms in one click | Redesign 5.7 (R6) |
| 10 | Conflicts are found with the standard-library `difflib`; he picks per conflict | Redesign 5.7 (R5.3) |
| 11 | Tests never go to the workspace. His extra test cases are added **in the app**, as in Phase 4 "Add a test case". The "his new tests" and tests-folder parts of R2 and R4 are reworded that way | Q11 (3 Nov), Phase 6 section 15.2 |
| 12 | Re-scan reads planned files only. Re-scan comes back after a build in Phase 8 | Phase 6 C4, 6 Nov fixes F7 |
| 13 | The app never deletes a file, never runs Git, never commits or pushes | Phases 5 and 6 |
| 14 | Must fix cannot be accepted away; the only way past is Dispute (built in Phase 7) | Redesign 5.5, Phase 7 D-F |
| 15 | The AI never sees the chat. Each call sends the record, the one question and the answer (the record is the memory) | Redesign 4, Phase 4 G8 |
| 16 | Developer-facing instructions use Command Prompt only | Phase 6 v1.1 |

## 2. Where Refine starts

Refine is offered only when the request is **READY_FOR_REVIEW** or **NOT_PASSING** and the build
step is `b_written` (the code is in his folder). Not during a build, not at `b_write_stopped`
(Phase 6 B9 handles that), not after HANDED_OFF (Phase 10).

Composer at `b_written` (2D control, the 6 Nov "typing is the action" pattern):

| Control | Does |
|---|---|
| Text box, Send button labelled **Refine** | Starts the lane suggestion (section 4). Placeholder: "Tell me what to change, then press Refine." |
| **Re-scan** | Section 3 |
| **Check my edits** | Shown only after a re-scan found changed files (section 3) |
| **Restore an earlier version** | Section 9 |
| **Get help** | As Phase 6 B6 |

Phase 7 buttons stay (Dispute, Run the Tester review again when grey). The Build tab "Your turn"
text gets back: "Edit anything, then click Re-scan." (removed on 6 Nov, F7, until Phase 8).

## 3. Re-scan and Check my edits

**Re-scan** at `b_written`: the browser reads every planned file (Phase 6 C4, R1), compares each with
the last `written` fingerprint, and saves `scanned` rows as Phase 5 section 6. New in Phase 8:

- The Build tab shows each changed file **side by side**: left the last version the app wrote, right
  his version, changed lines marked. Plain code builds the view with `difflib` (no new library).
- A fixed line under the result: "Only the planned files are read. Edits in other files are not
  picked up." (D-M).
- His scanned version becomes the **starting text** of any later rebuild (Phase 6 D-K, R5.2).
- The label does not change yet, but a line says: "Your edits are not tested yet. Press Check my
  edits." A changed folder means the folder no longer equals "last tested".

**Check my edits** (D-I): a check run on his versions of the planned files.

1. Status READY_FOR_REVIEW or NOT_PASSING to BUILDING, build kind `check`, new build number.
2. Layer A on every planned file (A1 to A7 as Phase 6). A6 (contract) applies: if he renamed an
   agreed function, A6 says so in plain words.
3. Layer B with the frozen tests of the current approach version (plus appended cases, section 7).
4. Layer C as Phase 7 (a fresh full review of his files).
5. No Generator call, no fix rounds. One pass. Not counted in any budget.

| Result | Then |
|---|---|
| A, B and C pass | Phase 7 label rules (green or yellow). "Last tested" = his files. Nothing is written (the files are already his) |
| Layer A or B fails | Red banner "Your edit breaks <n> tests" with the failure report, then the three R3 buttons below. Label **Not passing**, status NOT_PASSING |
| Layer C Must fix | As above, with the finding. Buttons R3 plus Dispute |
| Tester unusable twice | Unable to assess, as Phase 7 D-D |

**R3 buttons:**
- **Fix my edit**: the bug lane, with the failing tests as the repro (no new repro test needed; the
  failing frozen test already shows the problem). Goes straight to the rebuild (section 7, step 4).
- **My edit is right, the requirement was wrong**: the requirement lane, with the feedback box
  pre-filled "My edit to `<path>` is intended: <test name> expects the old behaviour."
- **I'll fix it myself**: no status change. Chat: "Edit the file, then press Re-scan."

## 4. Choosing the lane

1. He types feedback and presses **Refine**. The text goes through the usual message checks (empty,
   4,000 characters, secrets; Phase 4 G7).
2. One AI call (D-B). Sent: charter slice, the current confirmed record (with criterion IDs), the
   accepted approach (file plan, design decisions as `DD-<n>`), the test plan case list, the latest
   label and finding list (IDs, one line each), and his feedback between lines, as information.
   Never the chat, never code.
3. Reply (JSON, `LaneSuggestion`): `lane` (`requirement`, `approach`, `bug`), `reason` (one plain
   sentence, up to 300 characters), and for `bug` the criterion ID it breaks (`AC-<n>`, or none).
4. Plain-code checks: lane in the list, reason not empty, the criterion exists. A bug with no
   criterion is turned into a suggestion of `requirement` with the reason "No criterion covers this,
   so it is a missing requirement." (the demo's `/*38*/` case).
5. Chat: the reason, then three equal buttons **Requirement change**, **Approach change**, **Bug**,
   the suggested one in the primary style, plus **Cancel**. Unusable reply twice, or no answer: no
   suggestion, the same three buttons, "I could not suggest a lane. Pick one." He always decides.
6. His click starts the lane: status REVISION_IN_PROGRESS (D-A), a Refine row is saved, audit
   `refine_started` (lane suggested, lane chosen).

Refine cap (D-E): at most `refine_max_per_request` (5) Refines per request, all lanes together,
counted at the click. After that the Refine box is disabled with "This request has been refined 5
times. Get help, or hand off what you have." Check my edits and Re-scan stay.

## 5. Requirement lane (revision mode)

**Understand in revision mode:**
1. Starts from the last confirmed record (v1, or vN). His feedback is the answer to "What should
   change?". No 4-box form (the 6 Nov U1 form is for new requests only).
2. One interpreter call with: the record, his feedback, and the instruction to return **changes
   only** (D-C): `criteria_ops` (each `add` with given, when, then; `change` with an existing ID and
   the new parts; `remove` with an existing ID) and `field_updates` (only the record fields that
   change). Plus clarifying questions as today, asked one at a time, capped by
   `max_material_decisions`.
3. Plain code applies the operations to a copy of the record. Unchanged criteria are copied as they
   are. New criteria get the next free number: one more than the highest ID in **any** version of
   this record, so an ID is never reused. Removed IDs are kept in the version history as "removed".
   The existing criterion checks apply (Phase 2D 1.4: observable "then", no duplicates, at most 12).
4. **Checkpoint:** the Summary tab shows the diff of vN to v(N+1): fields changed (old and new),
   criteria added, changed (old and new parts), removed. Buttons **Confirm v2** and **Cancel
   revision**; typing plus Send **Correct something**.
5. Confirm saves record v(N+1), audit `record_revised` (from, to, the diff). Cancel saves nothing,
   status goes back to where Refine started, audit `refine_cancelled`.

**Then, automatically (6 Nov F3 pattern):**
6. **Discover** runs again on record v(N+1) (D-D) and shows its findings with "Findings look right"
   (one click). This keeps gate check 2 (N2: the Discover round matches the latest record version)
   true without a special case.
7. **Approach:** one Generator call with the accepted approach, the record diff and the new
   Discover round. Saved as a new approach version with source `revision`. Not counted in the Phase 4
   change cap (G9). He accepts it as in Phase 4 (Accept approach, Change something, Get help).
8. **Test plan:** cases of unchanged criteria are kept as they are (including his "Yours" cases).
   Cases of changed or removed criteria are dropped. The Tester writes cases for new and changed
   criteria only. New cases are marked **New** on the plan. He must accept the test plan again
   (redesign: new cases need his approval).
9. Gate (all 4) to READY_TO_BUILD. Then the **workspace check runs again** on the new file plan
   (Phase 5 section 4: new `modify` files get a baseline, a new `create` file that already exists is
   B4). Then Build is pressed by him (the 6 Nov F3 rule: Build is never automatic).
10. Rebuild: a new approach version, so new contract and new frozen tests (decision 5), then the
    Phase 6 loop with patching (section 8).

Files that were in the old plan but not in the new one are never deleted. The chat lists them: "These
files are no longer in the plan. Delete them yourself if you do not need them: `<paths>`."

## 6. Approach lane

1. His feedback goes to the Phase 4 `change` call (same prompt), with the current approach. New
   approach version, source `refine`. Not counted in G9 (the Refine cap counts it instead).
2. He accepts it (Phase 4 review step). If the design decisions changed, the Tester writes a new
   test plan version as Phase 4 G4 (his own cases stay). He accepts the test plan.
3. Gate, workspace check on the new plan, Build, rebuild as section 5 steps 9 and 10.
4. The record version does not change. If the Generator's reply changes what the request does (a
   criterion would need to change), the plain-code check refuses it once with "This changes the
   requirement. Use the requirement lane." and offers **Switch to requirement change**.

## 7. Bug lane and "Fix it"

**Bug lane from feedback:**
1. One Tester call (D-G). Sent: the record (with the criterion the lane suggestion named), the
   contract, the test plan cases of that criterion, his feedback. **Never code** (same independence
   as Phase 6; W6 still watched, section 18).
2. Reply: one new test case in plain language (given, expect, criterion ID) and one test method,
   `unittest` only, named `test_<case id>_<criterion id>_<short words>`. Case ID: the next free
   T-number, tag **Bug**. Phase 6 test-file checks apply (parses, imports, naming).
3. **Proof (D-F):** plain code runs the new method in the sandbox against his current files (the
   last scan). It must **fail**. If it passes: "This test passes on your current code, so it does not
   show the bug. Describe it again, or pick another lane." Two tries
   (`refine_repro_max_attempts`, 2), then Get help is offered. Not a round.
4. **One-click confirm (R6):** the chat shows the case in plain words and the failure it gives
   today. Buttons **Yes, this is the bug** and **No, describe again**. Yes appends the method to the
   frozen test set as a new **test set version** (the earlier methods stay byte for byte the same,
   their fingerprints are checked). Audit `repro_test_confirmed`.
5. Rebuild: status REVISION_IN_PROGRESS to BUILDING, new build number, fresh budget. Round 1 is a
   **fix round**, not a full write: only the planned files named in the failing test's traceback
   (Phase 6 D-J) are sent, with the failure report and his current text. Same approach version, so
   the contract and the existing tests do not change.

**Fix my edit (R3):** step 5 only, with the frozen tests that his edit broke.

**"Fix it" on a Should fix (D-H):** the greyed Phase 7 button becomes active. It starts a bug lane
with no repro test: the finding (ID, file, line, quote, cite, message; already proven by the Phase 7
evidence rule) is the fix input, like a Must fix line in the Phase 7 Generator report. Fix round on
the cited file only, then A, B and a fresh C. If the finding is gone in the new review, it is marked
`fixed`. It counts in the Refine cap.

## 8. Rebuilds and edit protection (R5)

**R5.1 (built, Phase 5):** before every write, each file's fingerprint must equal the expected one;
else stop, "Re-scan first". Phase 8 adds tests only (8-30).

**R5.2 Patch, do not rewrite:** every rebuild starts with the Phase 6 pre-build re-scan (B1); his
scanned text is the starting text. After the first write, every planned file is treated as `modify`
for the Generator: it returns edit blocks (Phase 6 D-C), never the whole file. Lines it does not
touch stay byte for byte his.

**R5.3 Conflicts (D-J, D-K):**
1. Before the Generator call, plain code computes **his lines** per file (last app-written version
   vs his scanned version, `difflib`). The prompt marks them: "Lines 40 to 44 were written by the
   developer. Do not change them unless the failure report needs it."
2. After the rebuild finishes (`b_done`, any label) and **before the write**, plain code compares the
   Generator's result with his version. Any edit block that overlaps his lines, or touches the line
   next to them, is a conflict. Numbered C-1, C-2... per file.
3. No conflict: the write runs as Phase 6.
4. Conflicts: step `b_conflicts`. The Build tab shows each conflict side by side: **Yours** and
   **AI's**, with 3 lines of context. Per conflict: **Keep mine** or **Take the AI's**. Nothing is
   written until every conflict has a pick. Then **Apply my choices**.
5. All picks "Take the AI's": the tested result is written as it is.
6. Any "Keep mine": the merged files are what will be in his folder, but they were not tested. A
   **check run** (section 3) runs on the merged files first (D-K). Pass: write, label from that check
   run. Fail: the merged files are still written (he chose them), label Not passing, and the R3
   buttons are offered.
7. Every pick is audited (`conflict_resolved`, conflict ID, choice).

**R5.4 Every version kept, one-click restore:** section 9.

**Download mode** (Phase 5 fallback): the same rules, with **Upload folder to re-scan** instead of
Re-scan, and the "upload your folder before every new download" line (no edit guard in this mode).

## 9. Restore

- The server already keeps the text of every `written` and `scanned` version (Phase 5 D-H). Phase 8
  adds a **Versions** list on the Build tab: one row per build or check run that ended in a write or
  a "last tested" set: build number, kind (build, rebuild, check), time, label, files.
- **Restore** (D-L) restores **one whole set**: every planned file as that set had it, because the
  files were tested together.
- Steps: a re-scan first (the edit guard needs today's fingerprints). If he has edits not in any
  saved version, the chat warns: "Your current edits in `<path>` will be replaced. They stay saved on
  the server and can be restored." Buttons **Restore build 2** and **Cancel**.
- The write goes through the Phase 5 write job (`expected` = the re-scan fingerprints), mode
  `restore`. "Last tested" and the label become that set's. Audit `version_restored` (from, to).
- Files that the restored set did not have are not deleted (decision 13); the chat lists them.
- Restore never touches the frozen tests or the record version.

## 10. Statuses

REVISION_IN_PROGRESS is now used (D-A). New moves (add to `ALLOWED_MOVES`, every move audited as
today; the plan confirms the exact status names already in `da_models.py`):

- READY_FOR_REVIEW and NOT_PASSING to REVISION_IN_PROGRESS (a lane is chosen)
- READY_FOR_REVIEW and NOT_PASSING to BUILDING (Check my edits; Restore runs no build)
- REVISION_IN_PROGRESS to the Understand checkpoint status, then the normal path to Discover,
  Approach (APPROACH_PROPOSED) and READY_TO_BUILD (requirement lane, after Confirm v2)
- REVISION_IN_PROGRESS to APPROACH_PROPOSED (approach lane, after the new version is saved)
- REVISION_IN_PROGRESS to BUILDING (bug lane after Yes, this is the bug; Fix my edit; Fix it)
- REVISION_IN_PROGRESS back to the status Refine started from (Cancel, Cancel revision)
- REVISION_IN_PROGRESS to ESCALATION_REQUIRED (Get help, open item `Escalated in Refine: <step>`)
- No new status for conflicts: `b_conflicts` is a build step. The status moves at `b_done` as in
  Phases 6 and 7 (READY_FOR_REVIEW or NOT_PASSING), and the write waits for his picks

Rules:
- F1: Every Refine action follows the Phase 6 B3 pattern: read with no lock, slow work outside any
  transaction, ONE write transaction for state, rows, audit and chat. The Refine state has its own
  revision for the stale check (`STALE_MESSAGE`).
- F2: One Refine at a time per request. One build at a time (Phase 6 B4).
- F3: A server restart during a lane's AI call leaves the lane at its step with **Try again**. During
  the rebuild, Phase 6 section 10 applies.
- F4: The count of rebuilds that ended NOT_PASSING in a row is stored per request (escalation
  trigger 1, "cap twice in a row", acts in Phase 10).

## 11. Screen

- **Summary tab:** version history (v1, v2...) with the diff of each version (redesign section 3).
  Criterion IDs shown with "added in v2", "changed in v2", "removed in v2".
- **Approach tab:** version list with source (`proposal`, `change`, `revision`, `refine`).
- **Tests tab:** cases tagged New (requirement lane), Bug (repro tests), Yours. The test set version
  and the approach version it belongs to. **Add a test case** (D-N) at `b_written`.
- **Build tab:** re-scan side by side (section 3), conflicts (section 8), Versions and Restore
  (section 9), "Refine 2: bug" tag on the current build. The demo's "How your edits are protected"
  card with the 4 rules, worded as built.
- **Header:** the status pill shows REVISION IN PROGRESS during a lane.
- "My recent requests" reopens at the same lane step.

**Add a test case (D-N):** he types a case in plain language for an existing criterion (he picks
the criterion). The Tester writes the method (as section 7 step 2, tag **Yours**). Plain code runs
it on his current files. Passes: he confirms, it is appended to the frozen set, a check run follows
so the label covers it. Fails: "Your new test fails on the current code. Treat it as a bug?" with
**Yes, fix it** (bug lane step 4 onwards, the test is the repro) and **Drop this test**. It counts in
the Refine cap only when it becomes a bug lane.

## 12. Rulebook policy additions

Same pattern as Phases 4 to 7: new `Policy` fields with defaults equal to the starter values, so
older rulebook versions still load. Admin screens are Phase 11.

| Field | Meaning | Starter value (made up, real values set at work) |
|---|---|---|
| `refine_max_per_request` | Refines per request, all lanes together (D-E) | 5 |
| `refine_lane_max_attempts` | Lane-suggestion calls when the reply is unusable | 2 |
| `refine_repro_max_attempts` | Repro-test tries before Get help (D-F) | 2 |
| `refine_conflict_context_lines` | Context lines around a conflict, and the "next to his lines" distance | 3 |

Prompt sizes reuse `build_max_prompt_chars` (Generator) and `tester_max_prompt_chars` (Tester): no
new size field (Q7, section 17).

## 13. Storage

New file `db_table_functions/db_tbl_da_refine.py`, same style as `db_tbl_da_tester.py`. New tables,
`CREATE TABLE IF NOT EXISTS`. Existing tables get new values only (build kind `check`, workspace
file mode `restore`, test plan source `revision` and `refine`, step `b_conflicts`).

| Table | Holds | Rule |
|---|---|---|
| `da_refine_state` | request ID, current Refine number, step, own revision, Refine count | one row per request, revision goes up by 1 with every save |
| `da_refines` | request ID, Refine number, source (`feedback`, `finding`, `failed_check`, `added_test`), feedback text, suggested lane, reason, chosen lane, from status, record version before and after, approach version before and after, build number, result, created, closed | one row per Refine; updated only to close it |
| `da_test_sets` | request ID, test set version, approach version, added case IDs, test file text, fingerprint, created | append-only; a new row per appended repro or Yours test |
| `da_refine_conflicts` | request ID, build number, path, conflict ID, his lines, AI's lines, context, choice, created | append-only; the latest row per conflict is its state |

Audit events (actor in brackets): `refine_started` (developer, lanes), `lane_suggested` (system),
`lane_unusable` (system, attempt), `refine_cancelled` (developer), `record_revised` (developer, from,
to, diff), `approach_revised` (system, source), `repro_test_written` (system), `repro_test_passed_today`
(system, attempt), `repro_test_confirmed` (developer), `test_case_added` (developer), `check_run_started`
(developer), `conflicts_found` (system, count), `conflict_resolved` (developer, choice),
`version_restored` (developer, from, to), `finding_fixed` (system), plus the Phase 6 and 7 build
events for rebuilds. Every status move is audited, as today.

## 14. Testing without work

- **pytest, plain rules:** criterion operations (add, change, remove; IDs never reused across
  versions; unchanged criteria byte for byte); record diff; lane-reply checks (bug without criterion
  becomes requirement); Refine cap; his-lines computation and conflict detection with `difflib`
  (overlap, touching line, far away is no conflict); merge of picks; restore set building; the test
  set append keeps earlier methods' fingerprints; every-file-is-modify after the first write; the
  lane prompt holds no chat and no code; the bug-lane Tester prompt holds no code.
- **Fake provider (home):** a fixed script for each lane. Requirement: feedback "Reject files over
  5 MB" becomes AC-6 added, v2, approach v2 with one new case, rebuild green. Approach: one design
  choice changed, rebuild green. Bug: repro test fails today, fix in round 1, green. Test-only
  switches force: unusable lane reply twice, a repro test that passes today twice, a Generator edit
  block that overlaps his lines (conflict), an approach-lane reply that changes a criterion.
- **Real sandbox:** the repro proof (fails today) and the check run on edited files.
- **Pretend work server** (127.0.0.1:8070): answers the lane, revision, repro and fix prompts with
  the same script, with `DA_ONPREM_TESTER_MODEL` set and empty.
- **Playwright (cloud session only):** private test folder as the workspace. Build, edit one line of a
  planned file in the folder, Re-scan (side by side shows it), Check my edits (green), Refine with a
  bug, confirm the repro, rebuild; his line is still there.
- **Smoke check:** a full request to `b_written`, then one bug lane to READY_FOR_REVIEW, then one
  requirement lane to record v2 and READY_FOR_REVIEW.
- **Home check by Gian:** on `http://127.0.0.1:8050` with `DA_LLM_PROVIDER=fake` and a COPY of the
  repo as the workspace: edit a written file, Re-scan, Check my edits; then try each lane once; then
  Restore build 1.
- **Work test** (`docs/refine-work-test.md`, new, Command Prompt only): the steps for section 17.

## 15. Out of scope

- Enhancement mode, safety-net tests, freshness check, light P16 (Phase 9).
- Review my code, "Let AI fix" there, Handoff, the final fingerprint check, PR summary, the
  Escalations inbox, auto-escalation triggers, a new linked CVDA after handoff (Phase 10). Phase 8
  only stores what they need ("last tested", the NOT_PASSING-in-a-row count).
- Admin screens for the new policy fields and the "requirement revisions per request" and "files
  edited by developers" metrics (Phase 11). Phase 8 stores the data.
- Deleting files, any Git command, writing tests or reports to the workspace.
- Detecting edits outside the planned files (D-M).
- Leftovers P26, P27, P28 (STATUS.md).

## 16. Decisions (D-x), for the chief's decision rule

None of D-A to D-N touches a work fact, and each can be undone later (a code or policy change). Each
has one recommendation. The "Rule" column is for the chief (section 6 of the automation spec).

| # | Question | Options (ranked) | Recommendation | Rule |
|---|---|---|---|---|
| D-A | Which status during a lane? | 1. REVISION_IN_PROGRESS from the lane click until the lane hands over (requirement: Confirm v2; approach: new version saved; bug: repro confirmed), then the normal statuses (APPROACH_PROPOSED, BUILDING...). 2. REVISION_IN_PROGRESS for the whole lane including the rebuild, with sub-steps. 3. No new status, only a Refine tag | **1**: the Phase 4 to 7 flows check their own statuses; reusing them means no second copy of the build and gate rules. Risk: the demo shows REVISION IN PROGRESS during the rebuild (option 2); the "Refine 2: bug" tag covers that need | Chosen by chief, 6.1 (recommended option) |
| D-B | How is the lane suggested? | 1. One AI call returns lane, reason and criterion; all three buttons are always shown, the suggested one highlighted. 2. Plain-code keywords. 3. No suggestion, he picks | **1**: the redesign says the AI suggests; showing all three buttons means a wrong guess costs one click. Option 2 is brittle on plain-English feedback. The model behind it is a role setting (section 17) | Chosen by chief, 6.1 (recommended option) |
| D-C | How does revision mode change the criteria? | 1. The AI returns operations (add, change, remove by ID); plain code applies them; IDs never reused. 2. The AI returns the full list, each item with its ID or "new". 3. Plain code matches old and new by text | **1**: the AI can only touch what it names, so unchanged criteria cannot drift (W2 showed drift); the diff falls out directly. Option 2 lets the AI quietly reword a criterion | Chosen by chief, 6.1 (recommended option) |
| D-D | Discover after record v2? | 1. Runs again automatically on v2, one-click "Findings look right". 2. The old round is carried forward, he confirms in one click. 3. He starts Discover himself | **1**: a changed requirement may change what can be reused, and the N2 gate check stays true without a special case. Cost: one Discover run per requirement lane. Option 2 is faster but may reuse stale findings | Chosen by chief, 6.1 (recommended option) |
| D-E | How many Refines per request? | 1. A new policy cap `refine_max_per_request` (5), all lanes together, separate from the Phase 4 G9 cap. 2. Reuse G9 (3 approach changes per request). 3. No cap | **1**: a developer who used his 3 Approach changes can still refine; a cap stops endless loops and feeds the escalation idea later. Option 2 blocks Refine for exactly the developers who needed changes. Option 3 can loop | Chosen by chief, 6.1 (recommended option) |
| D-F | Must the repro test fail on today's code? | 1. Yes, proven in the sandbox before he confirms. 2. No, he confirms on its text | **1**: a test that passes today does not show the bug, and the fix round would have nothing to fix; same idea as the safety-net proof in redesign 5.8. Cost: one sandbox run, no round | Chosen by chief, 6.1 (recommended option) |
| D-G | What does the Tester see for a repro test? | 1. Record, contract, the criterion's cases, his feedback. No code. 2. Also the code of the file he names | **1**: keeps the Tester independent of the code, as in Phase 6. Risk: a bug that depends on code detail is hard to reproduce; the "passes today" retry and Get help catch it. Switching to option 2 later is small | Chosen by chief, 6.1 (recommended option) |
| D-H | What does "Fix it" on a Should fix do? | 1. A bug lane with no repro test: the proven finding is the fix input, fix round on the cited file, fresh C review. 2. A repro test first, as the bug lane. 3. Only for check-3 findings | **1**: most Should fix findings (checks 4 to 6, judgement rules) are not behaviour a test can show; the Phase 7 evidence rule already proved the finding is real. Option 2 would often fail the D-F proof | Chosen by chief, 6.1 (recommended option) |
| D-I | How are his edits checked (R2)? | 1. A **Check my edits** button after a re-scan finds changes: Layers A, B, C once, no Generator, no budget. 2. Automatically right after every re-scan. 3. Layers A and B only | **1**: he may still be mid-edit, and Layer C takes minutes. R2 says all three layers. Risk: he forgets; the "not tested yet" line and Phase 10's fingerprint check catch it | Chosen by chief, 6.1 (recommended option) |
| D-J | How are his lines protected in a rebuild? | 1. The prompt marks his lines, and plain code still checks for conflicts before the write. 2. Plain-code conflict check only. 3. Refuse any edit block that touches his lines | **1**: telling the Generator avoids most conflicts; the check catches the rest. Option 3 can make a real fix impossible when his line is the bug | Chosen by chief, 6.1 (recommended option) |
| D-K | What happens after "Keep mine" picks? | 1. A check run on the merged files before the write; written either way (he chose), label from the check run. 2. Write and mark "not tested". 3. Re-run the whole rebuild | **1**: the label always describes what is in his folder. Option 2 makes "last tested" untrue. Option 3 can bring the same conflict back | Chosen by chief, 6.1 (recommended option) |
| D-L | What does Restore restore? | 1. One whole set (build or check run), all planned files together. 2. One file. 3. Both | **1**: the files were tested together; restoring one file can give a mix no test ever saw. Option 3 later if developers ask | Chosen by chief, 6.1 (recommended option) |
| D-M | Edits outside the planned files? | 1. A fixed line "Only the planned files are read. Edits in other files are not picked up." 2. The browser lists names and change times of other files in the planned folders and warns | **1**: keeps R1 (only planned files are ever read) strictly. Risk: a needed edit in another file goes unseen until he notices; the requirement or approach lane is the way to add a file to the plan | Chosen by chief, 6.1 (recommended option) |
| D-N | How does he add his own test case after the build? | 1. On the Tests tab, in plain language for an existing criterion; the Tester writes the method; a run on today's code; passes: appended and a check run; fails: offered as a bug. 2. Only through the bug lane. 3. Not in Phase 8 | **1**: matches Phase 6 15.2 (cases in the app) and R4 (his tests are frozen too), and one path covers both "add a check" and "found a bug" | Chosen by chief, 6.1 (recommended option) |

## 17. Work facts (no recommendation, Gian decides)

The chief opens one issue per row with the label shown and builds everything around it.

| # | Question | Options (not ranked) | What Phase 8 builds meanwhile | Label |
|---|---|---|---|---|
| WF-1 (Q7, carried) | The server's context limit per model name. Revision, rebuild (his marked lines) and repro prompts add text | Unknown. Not guessed here | The existing guards (`build_max_prompt_chars`, `tester_max_prompt_chars`, HTTP 400) stop cleanly at `b_interrupted` or the lane step with Get help | `needs-work-test` |
| WF-2 (Q9, carried) | Which model is the Tester at work (now also writing repro tests) | As Phase 7 WF-1: a. `default`, b. `reasoning-vlm`, c. empty (= the generator's model) | The model stays a setting. The repro "passes today" count is saved per Refine, so the bake-off can compare | `needs-work-test` |
| WF-3 | Which on-prem model suggests the lane, and is it good enough? | a. the Generator's role setting. b. the Tester's role setting. c. a new role setting | The lane call uses a role setting chosen in the plan; nothing is hard-coded. All three buttons are always shown, so a weak suggestion costs one click. Suggested vs chosen lane is saved for comparison | `needs-work-test` |
| WF-4 | How long may the CodeVision server keep every written and scanned code version (restore), and how much space may it use? Bank policy and CodeVision internals | Unknown. Not guessed here | Phase 8 keeps every version (Phase 5 D-H) and deletes nothing. No clean-up is built | `needs-gian` |
| WF-5 (Q14 e, carried) | Does CodeVision run as one copy or several on OCP? Rebuilds and check runs use the Phase 6 background thread | Unknown | Phase 6 section 10 unchanged. If the answer is "several", the Phase 6 stop applies to Phase 8 too | `needs-work-test` |

## 18. Open items

- **W6 (watch, carried from Phase 7):** the Tester sees design decision text, which could name a
  file. Phase 8 adds two Tester prompts (repro test, Add a test case); both get the "no code text"
  test (8-15). W6 stays open.
- **Demo out of date:** the demo writes tests into the workspace (`/*35*/`, `rescan`). Q11 wins.
  The demo is not changed by this phase.
- **D-A vs the demo:** the demo shows REVISION IN PROGRESS during the rebuild. If Gian prefers that,
  choose D-A option 2.
- **"Last tested"** is stored for Phase 10. Phase 10 decides what Handoff does when the folder
  differs from it.
- **Q2** (shared server database) is still open; Restore and the version list depend on the server
  database keeping text (WF-4).
- No facts file was given for Phase 8. If the chief has facts, compare them with sections 1 and 17
  before the plan.

Photos: none needed for this spec.

## 19. Done when (every line becomes a test, Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| 8-1 | a request at `b_written`, READY_FOR_REVIEW | the screen is drawn | the Refine box, Re-scan, Restore an earlier version and Get help are offered; "Edit anything, then click Re-scan." is on the Build tab |
| 8-2 | a request at BUILDING, or HANDED_OFF | the screen is drawn | no Refine box |
| 8-3 | one planned file edited in the folder | Re-scan | it shows side by side, a `scanned` row is saved, "Your edits are not tested yet" shows, Check my edits appears, the status is unchanged |
| 8-4 | a re-scan | the browser reads files | only planned files are read; the "Edits in other files are not picked up" line shows |
| 8-5 | an edit that keeps all tests passing | Check my edits | BUILDING with kind `check`, A, B and C run, no Generator call, the budget is not touched, label green or yellow, "last tested" = his files, nothing written |
| 8-6 | an edit that breaks one test | Check my edits | label Not passing, status NOT_PASSING, the failure report, buttons Fix my edit, My edit is right, I'll fix it myself |
| 8-7 | 8-6 | I'll fix it myself | no status change, the chat line "Edit the file, then press Re-scan." |
| 8-8 | 8-6 | My edit is right | the requirement lane starts with the feedback pre-filled |
| 8-9 | feedback typed | Refine | one lane call; the prompt holds no chat and no code; three equal lane buttons with the suggestion highlighted, and Cancel |
| 8-10 | a lane reply of `bug` with no criterion | checked | it is shown as a requirement suggestion with the "No criterion covers this" reason |
| 8-11 | an unusable lane reply twice | Refine | no suggestion, the three buttons and "Pick one" |
| 8-12 | `refine_max_per_request` Refines done | the screen is drawn | the Refine box is disabled with the cap message; Re-scan and Check my edits still work |
| 8-13 | the requirement lane and an "add AC-6, change AC-2" reply | revision runs | v2 holds AC-6 new, AC-2 changed, the others byte for byte the same; the Summary tab diff shows both |
| 8-14 | a v3 after AC-6 was removed in v2 | a criterion is added | it gets AC-7, never AC-6 |
| 8-15 | the repro-test and Add-a-test-case Tester prompts | built | they hold no code text (W6) |
| 8-16 | v2 confirmed | the lane goes on | Discover runs on v2 by itself; after "Findings look right" a new approach version with source `revision` is shown; G9 count unchanged |
| 8-17 | v2 with AC-2 changed and AC-6 new | the test plan is updated | cases of unchanged criteria (and Yours cases) are kept; AC-2 and AC-6 get new cases marked New; acceptance is required again |
| 8-18 | Cancel revision | pressed | no new record version, status back to where Refine started, audit `refine_cancelled` |
| 8-19 | a new plan with a file the old plan had | the rebuild is written | the old file is not deleted and is listed in the chat |
| 8-20 | the approach lane | the new version is accepted | record version unchanged, test plan rewritten only if decisions changed, then the gate and the workspace check run |
| 8-21 | an approach-lane reply that changes a criterion (fake switch) | checked | refused with "Use the requirement lane" and Switch to requirement change |
| 8-22 | the bug lane | the repro test is written | it runs on the current files and fails; the case is shown with the failure; Yes, this is the bug appends it as a new test set version; earlier methods keep their fingerprints |
| 8-23 | a repro test that passes today, twice (fake switch) | the proof runs | the "does not show the bug" message twice, then Get help; no round used |
| 8-24 | a confirmed repro test | the rebuild runs | new build number, fresh budget, round 1 regenerates only the traced file, the tests are not changed |
| 8-25 | a Should fix | Fix it | no repro test; a fix round on the cited file with the finding as input; a fresh C review; the finding is `fixed` when it is gone |
| 8-26 | a rebuild after his edit | the Generator is called | his scanned text is the starting text, the reply is edit blocks for every file, and the prompt marks his lines |
| 8-27 | a Generator edit block overlapping his lines (fake switch) | the build finishes | step `b_conflicts`, nothing written, each conflict side by side with Keep mine and Take the AI's |
| 8-28 | all conflicts picked "Take the AI's" | Apply my choices | the tested result is written, no check run |
| 8-29 | one conflict picked "Keep mine" | Apply my choices | a check run on the merged files, then the write; the label comes from the check run; picks audited |
| 8-30 | a file edited after the last scan | any Phase 8 write (rebuild, restore) | the Phase 5 edit guard stops it with "Re-scan first" |
| 8-31 | two finished builds | Restore build 1 | after a re-scan and the warning, every planned file gets build 1's text through the write job with mode `restore`; label and "last tested" are build 1's; frozen tests and record version unchanged |
| 8-32 | unsaved edits in a file | Restore is chosen | the warning names the file and says the edits stay saved |
| 8-33 | Add a test case that passes today | confirmed | appended (tag Yours, frozen), then a check run |
| 8-34 | Add a test case that fails today | the run ends | "Treat it as a bug?" with Yes, fix it and Drop this test |
| 8-35 | any Generator output in a rebuild naming a path under `tests/` | Layer A runs | refused (frozen tests, his included) |
| 8-36 | a lane at any step | Get help | ESCALATION_REQUIRED with open item `Escalated in Refine: <step>` |
| 8-37 | any Refine action | sent with an old Refine revision | refused with the stale message |
| 8-38 | two rebuilds in a row ending NOT_PASSING | the second ends | the in-a-row count is 2, stored |
| 8-39 | a rulebook version saved before Phase 8 | loaded | the four new fields hold the starter values |
| 8-40 | download mode | a lane runs | Upload folder to re-scan replaces Re-scan; the ZIP holds code files only |
| 8-41 | any write job in Phase 8 | built | code files only; no test file, no report, no folder created |
| 8-42 | Playwright with the private test folder | build, edit a line, Re-scan, Check my edits, bug lane, rebuild | his edited line is still in the file at the end |

Plus: `pytest` 0 failures, `ruff check` 0 problems, smoke check passes, code reviewer 0 Must fix, and a
home check by Gian on `127.0.0.1:8050` with a COPY of the repo as the workspace.

## 20. Files the builder will touch (for planning, not a limit)

`pydantic_classes/da_models.py` (moves), `da_refine_models.py` (new: `LaneSuggestion`,
`CriteriaOps`, `Conflict`), `da_rulebook_models.py` and `data/da_rulebook_seed.json` (policy fields),
`agents/da_refine_flow.py` (new: lanes, cap, restore), `agents/da_refine_checks.py` (new: criterion
ops, record diff, his lines, conflicts, merge), `agents/da_understand_flow.py` (revision mode),
`agents/da_approach_flow.py` (sources `revision`, `refine`; G9 untouched),
`agents/da_build_flow.py` (build kind `check`, rebuild as patch, `b_conflicts`, test sets),
`agents/da_tester_review.py` (reused, not changed unless the plan shows a need), the lane, revision
and repro prompts under `data/`, `agents/da_llm_client.py` (fake script and pretend-server answers),
`db_table_functions/db_tbl_da_refine.py` (new), `web/da_workspace.js` (restore mode only),
`layouts/da_developer_assistant_page.py`, the page callbacks, `web/da_web_components.py` (Summary
diff, side by side, conflicts, Versions), `da_smoke_check.py`, `README.md`, `CLAUDE.md` ("Current
phase"), `docs/refine-work-test.md` (new, Command Prompt only), and the matching tests.
