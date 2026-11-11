# Phase 9: Enhance an existing program (catalog, freshness, safety net, light P16)

Status: DRAFT v0.1 (9 Nov 2026). Written by the spec writer. Not yet approved by Gian. The chief applies
the decision rule (`specs/phase-a-automation.md` section 6) to D-A to D-N (section 17). The work facts
(section 18) need Gian and get no recommendation.
Depends on: Phase 8 (Refine, test set versions, edit protection), merged into `auto/phases-7-10`.
Next: Phase 10, Review my code, Handoff, Escalations inbox.
Source of truth: `specs/redesign-2026-10-31.md` sections 2 (Home card 2, switch offer), 5.1 (enhancement
mode), 5.2 (catalog, code index top 3, impact with light P16, freshness check), 5.8 (safety-net tests),
5.10 (safety-net gaps in the PR summary, stored now, shown in Phase 10), 7 (catalog "Unassigned" queue).
Facts: **no `specs/phase-9-facts.md` was given.** Facts here come only from the redesign and the approved
specs of Phases 3, 4, 5, 6 (v1.1 and the 6 Nov fixes), 7 and 8. Nothing new about work is assumed.
Visual reference: `docs/CodeVision_Developer_Assistant_Demo.html`. Read only: the `ENH` chat list
(`/*0*/` to `/*7*/`), the functions `tabEnhSummary` and `tabSafety`, and the four `ws({ws:"enh",...})`
screens. The demo's status pills PROGRAM CONFIRMED and SAFETY NET READY are not in the redesign status
table; see D-L. The demo's "Run git pull" line ignores ZIP workspaces (Phase 5 Q10); section 5 rewords it.
Build: worker team, branch `auto/phase-9`, merged into `auto/phases-7-10` by the chief.

## In plain words

Phases 2 to 8 build **new** code. Phase 9 lets a developer **change a program that already exists**
(Home card 2, "Enhance or fix an existing program"). A fix is just an enhancement whose change is "make
it work as intended".

1. **Find the program.** He names it (plain-code search of file and function names) or describes it
   (the code index, top 3). The app shows the candidates and the **capability** and **named senior**
   from the catalog. He always confirms. A file in no capability: he picks one, and the file goes to an
   **Unassigned** queue for Admin.
2. **Freshness check.** The browser reads the confirmed files from his folder and compares them with
   Bitbucket `main`. Different: "get the latest code first, or confirm your local changes are
   intentional."
3. **Enhancement questions.** The AI reads the code and drafts **what it does today**; he corrects it.
   Then **what should change** and, new, **what must NOT change**, then the usual inputs, outputs,
   success and failure.
4. **Discover** runs as before, plus **impact**: who calls the functions being changed (light P16, the
   standard-library `ast` module, no AI).
5. **Safety net.** Before anything changes, the Tester writes tests of **today's** behaviour. They must
   pass on the unchanged code (that proves the tests are right). He reviews them in plain words. Tests
   the change is meant to break are marked **expected to change** and linked to a criterion. Anything
   the net cannot cover (screens, database-heavy code) is listed as **not covered, check manually**.
6. From there the normal journey runs: Approach, Build and test, Your review. The Generator gets only
   the functions in scope, not whole files, and every safety-net test that is not "expected to change"
   must still pass.

AS400 comparisons:
- **Find the program** is `WRKOBJ` plus the application's owner list: you find the member, then look up
  which application area it belongs to and who signs off changes there.
- **Freshness** is checking your source member against the production library before you start
  (`CMPPFM` against the promoted copy). If someone promoted a change after you copied it, editing your
  old copy would undo their work.
- **Impact** is `DSPPGMREF` turned around: not "what does this program call" but "who calls this
  program". A where-used list before you change a parameter.
- **Safety net** is the **regression test pack** you build before touching a production program: run
  it on the current program first. If it does not pass on the current program, the test pack is wrong,
  not the program.
- **Expected to change** is the line on the test sheet that says "this result will differ after the
  change; see request item 1".

## Words used in this spec

| Word | Meaning |
|---|---|
| Enhance request | A request started from Home card 2. Same CVDA numbering, same record, with `kind` = `enhance` (or `fix`, D-M) |
| Target | A file the developer confirmed as "the program" in Find. One or more (D-C) |
| Function in scope | A function, class or method inside a target that the change touches. Found with the Phase 3 splitter; he confirms the list (D-D) |
| Capability | A business area in the catalog (for example "Limits", made up). Each has a named senior |
| Catalog | The plain-code lookup file path -> capability -> named senior (D-B) |
| Unassigned queue | Files found in no capability, with the capability the developer picked, waiting for Admin to confirm |
| `main` source | Where the server gets a file as it is on Bitbucket `main` (work fact WF-1). At home, a fake folder |
| Fresh | The target's fingerprint in his folder equals the fingerprint of the same path on `main` |
| Must-not-change item | One line of his answer to "What must NOT change?", numbered `NC-1`, `NC-2`... in the record |
| Safety-net test | A `unittest` method that captures today's behaviour of a function in scope. ID `S-1`, `S-2`... |
| Expected to change | A safety-net test that the requirement deliberately breaks, linked to one `AC-<n>` |
| Not covered | A function in scope, or a must-not-change item, that no proven safety-net test covers |
| Impact | The list of callers of the functions in scope, found by `ast` on the reference copy (D-F) |
| Reference copy | The server's copy of CodeVision's source that the Phase 6 sandbox already uses (Phase 6 D-A) |

## 1. Decisions already made (do not reopen)

| # | Decision | Source |
|---|---|---|
| 1 | Home has three cards; card 2 is "Enhance or fix an existing program". A fix is an enhancement whose change is "make it work as intended" | Redesign 2 |
| 2 | Understand offers to switch from card 1 to card 2 if the description matches an existing program | Redesign 2 |
| 3 | Enhancement mode asks: what does it do today (AI pre-fills from the code, developer corrects), what should change, what must NOT change, then inputs, outputs, success and failure | Redesign 5.1 |
| 4 | Find the program by name (plain-code catalog search) or description (code index, top 3). The developer always confirms | Redesign 5.2 |
| 5 | Catalog lookup is plain code: file -> capability -> named senior. Not in the catalog: the developer picks a capability, Admin is notified ("Unassigned" queue) | Redesign 5.2, 7 |
| 6 | Impact: who calls the functions being changed, found with the standard-library `ast` (light P16) | Redesign 5.2 |
| 7 | Freshness check before an enhancement: the browser reads the target files and compares with Bitbucket `main`; different -> update first or confirm local changes are intentional | Redesign 5.2 |
| 8 | Safety-net steps E6.1 to E6.5: the Tester writes tests of today's behaviour (it may see the current code for this), they must pass on the unchanged code, the developer reviews them in plain language, deliberately changed ones are "expected to change" and linked to a criterion, every other one must still pass after the change | Redesign 5.8 |
| 9 | Anything not covered is listed as "Not covered by safety net, check manually"; it goes into the PR summary | Redesign 5.8, 5.10 |
| 10 | The Generator gets only the functions in scope, not whole files | Redesign 5.8 |
| 11 | The Tester never sees code when writing **criterion** tests (Phase 6). The safety-net call is the only Tester call that sees code, and it is a separate call | Redesign 5.8, Phase 6 D-B |
| 12 | Tests stay in the app and run only in the server sandbox; nothing test-related goes to the folder or Bitbucket | Q11 (3 Nov), Phase 6 15.1 |
| 13 | The browser reads only planned files (R1). For an enhance request before Approach, "planned" means the confirmed targets | Redesign 5.6, 5.2 |
| 14 | Edit blocks for existing files (Phase 6 D-C); the edit guard and R5 protection (Phases 5 and 8) apply unchanged | Phases 5, 6, 8 |
| 15 | The app never runs Git, never commits, pushes, pulls or deletes a file | Phases 5, 6, 8 |
| 16 | A workspace may be a Git clone or a ZIP from Bitbucket (no `.git`); both are valid | Phase 5 Q10 |
| 17 | The AI never sees the chat; each call sends the record, the one question and the answer | Redesign 4 |
| 18 | Developer-facing instructions use Command Prompt only | Phase 6 v1.1 |
| 19 | Flag-for-review zones never block; they make the named senior a required PR reviewer | Redesign 5.11 (X3), Phase 4 D-E |

## 2. The flow

```
Home card 2 (or the switch offer from card 1, section 3)
  -> Find the program (section 4)          step e_find, e_pick
  -> Freshness check (section 5)           step e_fresh, e_stale
  -> Understand, enhancement mode (6)      status as Understand today
  -> Discover + impact (section 7)         status as Discover today
  -> Safety net (section 8)                step s_writing, s_review
  -> Approach (section 9)                  APPROACH_PROPOSED, gate, READY_TO_BUILD
  -> Workspace check, Build, Tester, Refine as Phases 5 to 8, with the rules of section 10
```

The order follows the demo: the safety net comes after Discover (it needs the criteria IDs for
"expected to change", and the impact list) and before Approach ("before any change").

Get help is offered at every Phase 9 step: status ESCALATION_REQUIRED, open item
`Escalated in Enhance: <step>`, as Phase 8.

## 3. Where an enhance request starts

**Home card 2.** Clicking it creates a request with `kind` = `enhance` and opens the chat at
`e_find` with: "Name the CodeVision program, or describe it. I'll find it, protect what works today,
and change only what you agree." The workspace chip shows as from Phase 5; a folder must be chosen
before the freshness check (section 5), because the browser reads the target from it. If none is chosen
yet, **Choose workspace folder** is shown at `e_pick` (Phase 5 flow, the folder is remembered, Phase 5
D-B).

**Switch offer from card 1 (D-N).** After the opening statement of a new request, plain code runs the
name search of section 4 on the opening statement and the 4-box form answers. If a candidate scores as
**Best match** (section 4), the chat says: "This sounds like a change to `<path>`, which already
exists. Switch to Enhance or fix?" Buttons **Switch to Enhance or fix** and **No, this is new**. Switch:
the same CVDA number, `kind` becomes `enhance`, the opening statement is kept, the flow goes to `e_pick`
with that candidate first. Audit `switched_to_enhance`. No, this is new: never asked again on this
request, audit `switch_declined`. No AI call.

**Fix (D-M).** On card 2 the first message can be a fix ("the report shows the wrong date"). One flow:
the developer may press **This is a fix** at `e_pick`; then "What should change?" is pre-filled with
"Make it work as intended: <his opening statement>" and `kind` = `fix` (for metrics only, Phase 11).

## 4. Find the program

1. His message goes through the usual message checks (empty, length, secrets; Phase 4 G7).
2. **By name (plain code, D-B):** case-insensitive whole-word match of his words against the **path and
   symbol list of the code index** (the Phase 3 `SearchIndex`, exact mode), keeping only `code` pieces.
   Up to `enhance_name_top_k` (5) files. A word that equals a file name stem (`limits_expiry_report`) or
   a symbol (`format_expiry`) is a **Best match**.
3. **By description:** the same message as a meaning search, top `enhance_meaning_top_k` (3) files.
4. Merge by path (a file found both ways says "Name + meaning"). Phase 3 safety filter applies
   (secret-looking, deprecated and restricted files are never shown).
5. For each candidate, **catalog lookup** (plain code, section 11): capability and named senior, or
   "Not in the catalog".
6. Chat: "Best match: `<path>` in the `<capability>` capability. Is this the right program?" Summary tab:
   the candidate table as the demo (`tabEnhSummary` "Program found"). Buttons **Yes, that's it**,
   **Show other matches** (the rest of the table becomes selectable, more than one can be ticked, D-C),
   **Search again** (typing is the action, 6 Nov pattern), **Get help**.
7. No candidates: "I could not find that program. Try its file name, or describe what it does in other
   words." Up to `enhance_find_max_rounds` (3) searches, then only Get help.
8. **Not in the catalog:** before confirming, he picks a capability from the catalog list (a dropdown).
   The file goes into the Unassigned queue (section 11) with his pick; the request continues with that
   capability and its senior, marked "capability not yet confirmed by Admin" (D-J).
9. **Confirm:** targets saved, audit `targets_confirmed` (paths, capability, how found). Then the
   freshness check runs at once.

At most `max_files` (Phase 4 policy, 5) targets. A target must be a `.py` file under the allowed
folders (Phase 4 policy); other files are refused with the reason.

## 5. Freshness check

1. The browser reads each target from his folder (Phase 5 read path, size and UTF-8 limits, R1).
   Missing in his folder: "Your folder does not have `<path>`. Get the latest code, or choose another
   folder." (like Phase 5 B3). Step `e_stale`.
2. The server gets the same path from the **`main` source** (`get_main_source(settings)`, provider
   switch `DA_MAIN_SOURCE`: `fake` at home, `bitbucket` a placeholder that raises "Bitbucket main is
   not configured yet", exactly as Phase 3's `codevision` search provider did). How the real one works
   is work fact WF-1.
3. Both texts are normalised and fingerprinted as Phase 5 D-G (line endings and byte-order mark do not
   count).
4. **All equal:** banner "Freshness check passed. Your copy matches Bitbucket main." Step `e_fresh`.
5. **Any different, or not on main:** step `e_stale`. Banner and chat (the demo's line, reworded for
   ZIP folders, D-E): "Your copy of `<path>` differs from Bitbucket main. Building on an old copy could
   undo someone else's change. Get the latest code first (`git pull` in Command Prompt, or download a
   fresh ZIP from Bitbucket), or confirm your local changes are intentional." For a path not on main:
   "`<path>` is not on Bitbucket main yet."
   Buttons: **I've updated, check again** (runs steps 1 to 4 again) and **My local changes are
   intentional** (D-E: step `e_fresh` with the flag `local_changes_confirmed`, audited, stored for the
   Phase 10 PR summary).
6. **`main` source unavailable** (placeholder, timeout, error): "I could not reach Bitbucket main, so
   freshness is not checked." Buttons **Continue without the check** (audited, stored for the PR summary
   like step 5) and **Try again**. Never a silent pass.
7. The text he confirmed (his folder's version) becomes the **baseline** of each target
   (`da_workspace_files` kind `baseline`, Phase 5), and is the "today's code" for the rest of Phase 9
   (D-G).
8. The check runs again for every `modify` file at the Phase 5 workspace check before the first build
   (D-E). A file that changed in his folder since the baseline gets the Phase 6 pre-build re-scan
   treatment as today; a file whose `main` version changed since step 4 shows the step 5 banner again.

Audit: `freshness_checked` (paths, result per path, `main` source name), `freshness_override`
(developer, which button).

## 6. Understand, enhancement mode

Same engine and record as Phase 2D, with these changes for `kind` `enhance` or `fix`:

1. **Pre-fill "What does it do today?" (one AI call).** Sent: the charter slice, the target paths, the
   text of each target's functions, cut to the functions the splitter finds (Phase 3 `split_python_file`),
   line-numbered, within `build_max_prompt_chars`. Too big: only the function list (names, lines,
   docstrings) is sent, and the chat says the draft is from names only. Reply (JSON `TodayDraft`):
   `today` (plain sentences, up to 600 characters, no code: the Phase 2 no-code check) and
   `functions_in_scope_guess` (symbols that exist in the split, D-D). Two unusable replies: the box is
   left empty and he writes it himself.
2. **The form (6 Nov U1 pattern, new boxes for this kind):** What it does today (pre-filled, he edits),
   What should change, **What must NOT change** (one item per line, at most `enhance_max_keep_items`
   (8); may be "Nothing special"), then the usual inputs, outputs, success and failure boxes, and the
   optional box. One Submit. Each box has the usual answer checks.
3. **Record fields (new, optional, default empty, so older records load):** `kind`, `targets` (paths),
   `today` (text), `must_not_change` (list of `NC-<n>` with text), `functions_in_scope` (D-D),
   `capability`, `named_senior`, `freshness` (result and override flag).
4. **Functions in scope (D-D):** the checkpoint shows the AI's guess as a tick list of the real
   functions in each target (from the split). He ticks or unticks. At least one. Plain code refuses
   symbols that are not in the split. Saved in the record.
5. **Criteria:** as Phase 2D (testable Given / When / Then, at most 12). "What should change" becomes
   criteria. Must-not-change items are **not** criteria; they are covered by the safety net (D-H).
6. Confirm saves record v1 as today. The Summary tab shows the demo's "Enhancement summary" card (today,
   change, must not change) above the record.

Revision mode (Phase 8 requirement lane) works the same on an enhance record. NC items follow the same
rule as criteria: new ones get the next free number, never reused.

## 7. Discover and impact (light P16)

Discover runs as Phase 3 on the record. New for enhance requests:

1. **Queries:** the targets' paths and the in-scope symbols are added as exact queries (within the
   Phase 3 cap of 6).
2. **Impact (plain code, no AI, D-F):** `agents/da_impact.py` walks every `.py` file of the **reference
   copy** with `ast` and lists, for each function in scope:
   - **Calls:** `name(...)` where `name` was imported from the target module, and `module.name(...)`
     where `module` is the target module imported under any alias. Marked **Direct**.
   - **Method calls** `x.name(...)` where `name` is a method in scope and the file imports the
     target module: marked **Possible** (by name only; `ast` cannot know the type of `x`).
   - **Imports** of the target module with no call found: marked **Imports only**.
   The target files themselves are skipped. Up to `impact_max_callers` (30) rows, then "and N more".
3. Result rows: caller path, caller function, line, the function in scope it calls, kind (Direct,
   Possible, Imports only), and the caller's capability and flag-for-review zone if any.
4. **Fixed limits line** (always shown): "Impact is found by reading the code, not by running it.
   It cannot see calls made by name in text, Dash callbacks wired by component IDs, or `getattr`."
5. **Reference copy differs from his folder:** impact reads the reference copy, never his folder (R1).
   The tab says which copy and its date (if known; WF-3).
6. **Reference copy unavailable:** "Impact could not be checked." on the tab; the request continues and
   the gap is stored for the PR summary. Never blocks.
7. Discovery tab: the demo's "Impact" card under the findings. Saved with the Discover round
   (new column `impact`, JSON, append-only like the round).

Effects of impact (D-F):
- Callers are shown and stored for the PR summary. They are never added to the file plan by the app.
- A **Direct** caller in another file means the in-scope function's **signature is locked** (name and
  arguments), unless the accepted file plan also lists that caller's file as `modify`. Layer A checks
  it (section 10).
- A caller inside a flag-for-review zone adds that zone to `zones_touched` with the reason "a caller is
  in this zone" (warning only, decision 19).

## 8. Safety net

Runs automatically after "Findings look right" on an enhance request. Step `s_writing`.

1. **One Tester call (separate from every other Tester call).** Sent: the record (today, should change,
   must not change with NC IDs, criteria with AC IDs, functions in scope), the in-scope functions'
   text **line-numbered** (decision 8: it may see the current code here), the names and signatures
   (not bodies) of other functions in the target files, and the impact rows. Not sent: the chat,
   Discover snippets. Within `tester_max_prompt_chars`.
2. **Reply (JSON `SafetyNet`):**
   - `cases`: each with ID (`S-<n>`), today's behaviour in plain words (one sentence), the function in
     scope it covers, the NC IDs it covers (zero or more), and `expected_to_change` (an `AC-<n>` or
     none).
   - `test_code`: one test file, `unittest` only, one method per case named
     `test_<S id>_<short words>`. Phase 6 test-file checks apply (parses, allowed imports, naming, no
     network, no file writes outside the sandbox temp folder).
   - `not_covered`: each with the function or NC ID and a one-line reason (for example "a Dash screen
     layout").
3. **Plain-code checks:** every case names a real in-scope function; every NC and AC ID exists; every
   method maps to one case and back; at most `safety_net_max_tests` (20) cases. Failures are a retry
   note. Two unusable replies: step `s_unable`, "The safety net could not be written." Buttons
   **Try again** and **Get help** (D-I).
4. **Proof (decision 8.2, D-I):** plain code runs the test file in the Phase 6 sandbox against the
   **baseline** (section 5, step 7) laid over the reference copy, as Phase 6 D-A. Same time limit
   (`build_test_timeout_s`).
   - A case that **passes**: proven.
   - A case that **fails or errors** on the unchanged code: the test is wrong, not the program. One
     more Tester call with the failure report asks for corrected cases for the failing ones only (the
     proven ones are kept byte for byte). Still failing after `safety_net_max_attempts` (2) calls:
     the case is **dropped**, and its function or NC item goes to "not covered" with the reason
     "Test could not be made to pass on today's code" (D-I).
   - A run that hits the time limit is handled as Phase 6 (stopped, named, the cases in it count as
     failing).
5. **Not covered, plain code (not only the AI's list):** every function in scope with no proven case,
   and every NC item with no proven case, is added to "not covered" even if the Tester did not list it.
6. **Review (step `s_review`, decision 8.3).** Safety net tab (demo `tabSafety`): the banner "Safety
   net: <n> tests capture today's behaviour. All <n> pass on the unchanged code." The table: Test,
   Today's behaviour, After the change ("Must still pass" or "Expected to change (AC-1)"). Below: the
   "Not covered by the safety net, check manually" card.
   Controls: **Continue to Approach** (accepts the net, audit `safety_net_accepted`), typing plus
   Send (**Correct something**: one Tester call with his note, then the proof again; at most
   `safety_net_max_corrections` (2)), **Get help**.
   He may change an "After the change" mark himself (a dropdown of the AC IDs, or "Must still pass").
   Plain code saves his choice; audit `expected_change_marked` (case, from, to).
7. **Frozen:** accepted safety-net tests are frozen for the request, exactly as criterion tests (Phase
   6 B2, Phase 8 decision 5). The Generator never edits them. They capture the **original** behaviour,
   so a Refine never rewrites them; only the "expected to change" marks are revisited (section 10).

Audit: `safety_net_written` (system, case count, attempt), `safety_net_proved` (system, passed,
dropped), `safety_net_corrected` (developer), `safety_net_accepted` (developer), `expected_change_marked`
(developer).

## 9. Approach for an enhance request

Phase 4 unchanged except:
- The Approach call gets the targets, the functions in scope, the impact rows and the safety-net case
  list (IDs and plain sentences only).
- File plan: each target appears as `modify`. A `modify` file that is not a target or a caller from
  impact gets the Phase 4 "Not seen in Discover" warning as today.
- **Test plan:** the Tester writes cases for the criteria as Phase 4 (never code). The test plan view
  shows the safety-net cases in their own section, read-only ("Accepted in the safety net"). Gate check
  4 ("test plan accepted") needs both: the criterion cases accepted **and** `safety_net_accepted` for
  this record version. The gate stays four checks.
- A criterion with an "expected to change" safety-net case must have at least one criterion case
  (Phase 4 rule "one or more cases per criterion" already says so; a test proves it holds here).

## 10. Build, Tester and Refine for an enhance request

**Build (Phase 6):**
1. The frozen test set of the approach version = criterion tests + safety-net tests that are **not**
   expected to change. Expected-to-change tests are kept in the app but not run in Layer B (D-G).
2. **The Generator gets only the functions in scope (decision 10, D-K).** For each target: the text of
   each in-scope function with its line numbers, the file's import lines, and the names and signatures
   of the other functions (no bodies). The reply is edit blocks (Phase 6 D-C). New functions may be
   added to a target only as a new edit block placed directly after an in-scope function.
3. **Layer A, new checks (plain code):**
   - **A8 Scope:** every edit block's "find" text must lie inside an in-scope function (by the split
     line ranges of the current text) or be the "insert after an in-scope function" form. Else:
     "Edit block N changes `<symbol>`, which is not in scope."
   - **A9 Locked signature (from impact):** a function in scope with a Direct caller outside the plan
     keeps its name and arguments. Else: "`<symbol>` is called by `<caller path>`; its arguments cannot
     change unless that file is in the plan."
4. **Layer B failure report** names safety-net tests in their own words: "Safety-net test S-4 (today:
   rows sorted by expiry date) now fails. You said this must not change (NC-2)."
5. A safety-net failure counts as a failed round like any test (shared budget, Phase 6 B3).

**Layer C (Phase 7), new plain-code line in check 1:** every NC item has at least one proven
safety-net test that is run, **or** is listed as not covered. A not-covered NC item is an FYI finding
"Not covered by the safety net, check manually" (it never blocks; the developer was shown it at review).
The AI checks (4 to 6) also get the NC list as information.

**After the build, expected-to-change tests (D-G):** they are run **once, for information**, after
Layer B passes. The Tests tab shows each as "Changed, as expected" (now fails) or "Still the old
behaviour" (now passes) next to its AC. "Still the old behaviour" adds an FYI line: "AC-1 was meant to
change this; S-2 still shows the old result. Check the AC-1 tests." It never changes the label.

**Refine (Phase 8):**
- Requirement lane on an enhance record: after Confirm v(N+1), the Tester re-marks only the "expected to
  change" links (no code sent, plain sentences only): cases linked to a removed or changed AC are shown
  for his one-click confirm. The safety-net tests themselves never change. He confirms the marks with
  the test plan. If he adds NC items, the safety net is extended (section 8, steps 1 to 5 for the new
  items only, against the **baseline**, never his edited code).
- Bug and approach lanes: no change.
- Edit protection (R5) and the A8 scope check both apply: his own edits outside scope are his (Check my
  edits does not run A8 on lines he wrote; A8 checks the Generator's edit blocks only).

**Stored for Phase 10 (PR summary):** targets, capability, named senior, capability-not-confirmed flag,
freshness result and override, impact rows and limits, safety-net cases with results, not-covered list.

## 11. Catalog and the Unassigned queue

**Catalog (D-B):** a new rulebook part `Capability`, same pattern as `FlagReviewZone` (Phase 4):
`name`, `description`, `named_senior` (a role or person label, text), `path_patterns` (fnmatch, matched
by plain code on the lower-case path). Starter catalog in `data/da_rulebook_seed.json`: 3 made-up
capabilities ("Limits", "Reports", "Uploads") with made-up senior labels ("Limits capability lead").
Older rulebook versions load with an empty catalog. Admin screens are Phase 11.

Lookup: the first capability (in catalog order) whose patterns match. None: "Not in the catalog".

**Unassigned queue:** table `da_unassigned_files` (section 14): path, the capability the developer
picked, request ID, created, state (`open`, `confirmed`, `changed`), resolved by, resolved time. One open
row per path (a second request with the same path links to the same row). Phase 9 builds the queue and
a read-only function `list_unassigned()`; the Admin screen to confirm is Phase 11 (WF-4 covers how Admin
is told).

## 12. Statuses and steps

No new status in `ALLOWED_MOVES` (D-L). Phase 9 keeps its own state (`da_enhance_state`) with steps,
like the Phase 5 workspace and the Phase 8 Refine state:

| Step | Meaning | Header pill shows |
|---|---|---|
| `e_find` | Waiting for a name or description | FIND THE PROGRAM |
| `e_pick` | Candidates shown, waiting for confirm | FIND THE PROGRAM |
| `e_stale` | Freshness differs or `main` unreachable | FRESHNESS CHECK |
| `e_fresh` | Targets confirmed and fresh (or overridden) | PROGRAM CONFIRMED |
| `s_writing` | Safety net being written or proven | WRITING SAFETY NET |
| `s_unable` | Safety net could not be written | SAFETY NET NOT READY |
| `s_review` | Waiting for Continue to Approach | SAFETY NET READY |
| `s_accepted` | Net accepted for this record version | (normal status pill) |

The request status during `e_*` steps is the status a new request has before Understand (the plan
confirms the exact name in `da_models.py`); during `s_*` steps it stays DISCOVERY_CONFIRMED. The header
pill shows the step label from the table while a Phase 9 step is open, else the normal status.

Rules (as Phase 8 F1 to F3):
- F1: every action reads with no lock, does slow work (AI call, sandbox run, `ast` walk, `main` fetch)
  outside any transaction, then ONE write transaction for state, rows, audit and chat. Own revision
  for the stale check (`STALE_MESSAGE`).
- F2: one safety-net write or proof at a time per request; it counts towards `build_max_parallel`
  (it uses the sandbox).
- F3: a server restart during a Phase 9 AI call or sandbox run leaves the step with **Try again**.

## 13. Rulebook policy additions

New `Policy` fields with defaults equal to the starter values, so older rulebook versions still load.
Admin screens are Phase 11.

| Field | Meaning | Starter value (made up, real values set at work) |
|---|---|---|
| `enhance_name_top_k` | Candidates from the name search | 5 |
| `enhance_meaning_top_k` | Candidates from the description search | 3 |
| `enhance_find_max_rounds` | Searches in Find before only Get help | 3 |
| `enhance_max_keep_items` | Must-not-change items | 8 |
| `safety_net_max_tests` | Safety-net cases per request | 20 |
| `safety_net_max_attempts` | Tester calls to fix cases that fail on today's code | 2 |
| `safety_net_max_corrections` | "Correct something" rounds at safety-net review | 2 |
| `impact_max_callers` | Impact rows shown and stored | 30 |

New settings (`configs/da_config.py`, `.env.example`): `DA_MAIN_SOURCE` (`fake` default, or
`bitbucket` placeholder), `DA_FAKE_MAIN_DIR` (home only, default `src/data/da_fake_main`). The reference
copy setting is the one Phase 6 already has (the plan confirms its name). No new library.

## 14. Storage

New file `db_table_functions/db_tbl_da_enhance.py`, same style as `db_tbl_da_refine.py`. New tables,
`CREATE TABLE IF NOT EXISTS`. Existing tables get new values or nullable columns only.

| Table | Holds | Rule |
|---|---|---|
| `da_enhance_state` | request ID, kind, step, own revision, find rounds used, safety-net corrections used | one row per request, revision goes up by 1 with every save |
| `da_enhance_candidates` | request ID, find round, candidates JSON (path, how found, score, capability) | append-only |
| `da_freshness_checks` | request ID, check number, record version, per path: his fingerprint, main fingerprint, result; `main` source name; override (none, `intentional`, `unchecked`) | append-only |
| `da_safety_nets` | request ID, net version, record version, cases JSON, test file text, fingerprint, proof results JSON, not covered JSON, accepted | append-only; the latest accepted row per record version is in force |
| `da_unassigned_files` | section 11 | one open row per path; updated only to resolve |

Changed: `da_discovery_results` gets a nullable `impact` column (JSON). `da_test_sets` (Phase 8) gets the
safety-net methods as part of each set; the set records which methods are safety-net and which are
expected to change.

Audit events (actor in brackets): `switched_to_enhance` (developer), `switch_declined` (developer),
`enhance_search` (system, round, counts), `targets_confirmed` (developer), `capability_picked`
(developer, path, capability), `freshness_checked` (system), `freshness_override` (developer, which),
`today_drafted` (system, attempt), `functions_in_scope_set` (developer), `impact_found` (system, counts,
copy), plus the section 8 events. Every status move is audited, as today.

## 15. Testing without work

- **pytest, plain rules:** name search scoring (Best match by stem and by symbol); merge of name and
  meaning hits; catalog lookup (first match wins, no match); the Unassigned row is one per path;
  freshness compare with line-ending and BOM differences (equal), real differences, missing in folder,
  missing on main, `main` unreachable; the switch offer fires only on a Best match; functions-in-scope
  refuse unknown symbols; NC numbering never reuses an ID; impact on a made-up package (direct call,
  aliased module call, `from x import y as z`, method call by name = Possible, import only, the target
  itself skipped, the cap); A8 (inside scope, outside scope, insert-after form); A9 (locked when a Direct
  caller is outside the plan, free when it is in the plan); expected-to-change tests are left out of
  Layer B; the not-covered list includes every untested function and NC item even when the Tester
  omits them; the pre-fill and Generator prompts hold only in-scope function bodies; the criterion
  Tester prompt still holds no code.
- **Fake provider (home):** the demo's story with made-up names. Opening "The limits expiry report
  shows the wrong date when a limit expires on a weekend" -> Best match `reports/limits_expiry_report.py`
  (Limits, made-up senior) -> freshness differs (the fake main folder has one changed line) -> "I've
  updated" after the test changes the folder -> fresh -> today drafted -> NC-1 columns, NC-2 sort order
  -> impact shows two callers -> safety net of 6 cases, one fails on today's code at first and is fixed
  on attempt 2, two are expected to change (AC-1), the screen layout is not covered -> Approach -> build
  green; S-2 and S-3 "Changed, as expected". Test-only switches force: a safety-net case that keeps
  failing (dropped), a Generator edit block outside scope (A8), a signature change (A9), `main`
  unreachable.
- **Real sandbox:** the safety-net proof on the made-up target (pass on baseline; a deliberately wrong
  case fails).
- **Pretend work server** (127.0.0.1:8070): answers the today-draft, safety-net and safety-net-fix
  prompts with the same script, with `DA_ONPREM_TESTER_MODEL` set and empty.
- **Made-up files:** a small made-up CodeVision-like package under `src/data/` (the reference copy at
  home, as Phase 6) holds the target and its two callers; `src/data/da_fake_main/` holds the "main"
  version of the target. All names made up.
- **Playwright (cloud session only):** private test folder as the workspace holding the made-up target.
  Card 2, confirm the target, freshness differs, change the file in the private folder, check again,
  through the safety net to a green build; the in-scope function changed, other functions byte for byte
  the same.
- **Smoke check:** one enhance request from card 2 to READY_FOR_REVIEW with the fake provider, then
  one card 1 request that gets the switch offer.
- **Home check by Gian:** on `http://127.0.0.1:8050` with `DA_LLM_PROVIDER=fake` and the practice folder
  (Phase 5 P29) extended with the made-up target: card 2, name the program, see the freshness banner,
  confirm, read the safety net, build.
- **Work test** (`docs/enhance-work-test.md`, new, Command Prompt only): the steps for section 18.

## 16. Out of scope

- Review my code, Handoff, the PR summary text, the final fingerprint check, the Escalations inbox,
  auto-escalation (Phase 10). Phase 9 stores what the PR summary needs (section 10).
- Admin screens: catalog editing, confirming the Unassigned queue, the new policy fields, the metric
  "enhance vs fix" (Phase 11). Phase 9 stores the data.
- The real Bitbucket adapter behind `DA_MAIN_SOURCE=bitbucket` (needs WF-1), and the real code index
  adapter (P15). Phase 9 builds the placeholders and the fake.
- Full structural search (P16 beyond calls and imports: configuration links, Dash callback wiring,
  runtime calls).
- Any Git command (the app never pulls; it tells him to). Deleting files. Writing tests to the folder.
- Reading files outside the targets and the file plan from his folder (R1). Impact reads the reference
  copy only.
- A new CVDA linked to an older one ("follows CVDA-...", Phase 10).
- Changing non-Python files (screens defined in other formats, SQL, configuration files).

## 17. Decisions (D-x), for the chief's decision rule

None of D-A to D-N decides a work fact, and each can be undone later (a code or policy change). Where a
choice **depends** on a work fact, the column says so; the work fact itself is in section 18 with no
recommendation.

| # | Question | Options (ranked) | Recommendation | Rule |
|---|---|---|---|---|
| D-A | Where does the enhance flow put Find and freshness? | 1. Before Understand (the demo's order), so the AI can pre-fill "today" from the code. 2. After Understand, as part of Discover | **1**: decision 3 needs the code before the first question, and the demo shows it. Option 2 makes the developer describe today's behaviour with no help | Chosen by chief, 6.1 (option 1) |
| D-B | What is the catalog, and what does the name search search? | 1. A rulebook part `Capability` with path patterns (like flag zones); the name search runs over the code index's paths and symbols, then the catalog gives the capability. 2. An explicit file list per capability (like CodeVision's "yellow pages" spreadsheet), searched by name. 3. Both | **1**: new files fall into the right capability with no list to maintain, and it reuses the tested flag-zone matching. Option 2 goes stale with every new file. Depends on WF-2 (the real catalog content) | Chosen by chief, 6.1 (option 1); the content itself stays WF-2 |
| D-C | How many targets per enhance request? | 1. One or more, up to `max_files`, ticked from the candidates. 2. Exactly one | **1**: a change often touches a module and its helper. Option 2 is simpler but forces a split the developer did not want | Chosen by chief, 6.1 (option 1) |
| D-D | How is "functions in scope" chosen? | 1. The AI guesses during the today-draft call, plain code keeps only real symbols, he ticks the final list. 2. He picks from the list with no guess. 3. Whole targets are in scope | **1**: one fewer step for him and still his decision. Option 3 breaks decision 10 | Chosen by chief, 6.1 (option 1) |
| D-E | Freshness: wording, override, and when it runs | 1. Wording covers Git and ZIP folders; "My local changes are intentional" is one audited click, stored for the PR summary; runs at Find and again at the first workspace check. 2. Override needs a typed reason. 3. Check at Find only | **1**: matches the demo's one click and Phase 5 Q10 (ZIP folders), and a request can sit for days before Build. Option 2 if Gian wants a reason on record | Chosen by chief, 6.1 (option 1) |
| D-F | Impact: where it reads, and what it does | 1. `ast` over the reference copy; show and store callers; lock the signature (A9) of functions with Direct callers outside the plan; flag zones of callers added as warnings. 2. Show only, no A9. 3. The browser reads every `.py` in his folder | **1**: a changed signature with an unchanged caller is the classic break this whole phase exists to stop. Option 3 breaks R1. Depends on WF-3 (does the reference copy exist and how fresh is it) | Chosen by chief, 6.1 (option 1); the facts stay WF-3 |
| D-G | What happens to "expected to change" tests? | 1. Not run in Layer B; run once after pass for information ("Changed, as expected" or "Still the old behaviour", FYI). 2. Must fail after the change (a hard check). 3. Dropped entirely | **1**: the criterion tests already prove the new behaviour; option 2 fails on a partial change that is still correct (a test that checked two things). Option 3 loses a useful cross-check | Chosen by chief, 6.1 (option 1) |
| D-H | Are must-not-change items criteria? | 1. No: a separate `NC-<n>` list covered by the safety net and by a new line in Layer C check 1. 2. Yes, turned into Given / When / Then criteria | **1**: criteria get new tests from the Tester without code; NC items describe today's behaviour, which only the code-reading safety-net call can test. Option 2 mixes the two Tester calls | Chosen by chief, 6.1 (option 1) |
| D-I | A safety-net case that fails on today's code | 1. One fix call for the failing cases only, up to `safety_net_max_attempts`, then drop and list as not covered. 2. Block until all pass. 3. Drop at once | **1**: a wrong test is the Tester's fault, not the program's; a dropped case is honest because it is listed. Option 2 can be a dead end | Chosen by chief, 6.1 (option 1) |
| D-J | A target in no capability | 1. He picks a capability, the request continues, the file is queued for Admin, marked "not yet confirmed" for the PR summary. 2. Block until Admin confirms | **1**: the redesign says Admin is notified, not that the developer waits. Option 2 stops work on Admin's speed | Chosen by chief, 6.1 (option 1) |
| D-K | How the Generator gets "only the functions in scope" | 1. In-scope bodies plus imports and other signatures; plain-code check A8 refuses edit blocks outside scope; new functions only right after an in-scope one. 2. In-scope bodies, prompt rule only. 3. Whole file with in-scope functions marked | **1**: a prompt rule alone is a request, A8 makes it a rule (W2 showed drift). Option 3 breaks decision 10 | Chosen by chief, 6.1 (option 1) |
| D-L | Statuses for the new steps | 1. No new status; own step table, the header pill shows the step label (PROGRAM CONFIRMED, SAFETY NET READY as the demo). 2. Add PROGRAM_CONFIRMED and SAFETY_NET_READY to `ALLOWED_MOVES` | **1**: same as Phase 5 D-I and Phase 8; the redesign status table has no such statuses, and the build and gate rules keep checking the statuses they know. The pill still looks like the demo | Chosen by chief, 6.1 (option 1) |
| D-M | Fix vs enhance | 1. One flow; a "This is a fix" button pre-fills "What should change?" and sets `kind` = `fix` for metrics. 2. A fourth Home card. 3. No distinction stored | **1**: decision 1 says a fix is an enhancement; the stored kind lets Phase 11 count fixes for free | Chosen by chief, 6.1 (option 1) |
| D-N | How the switch offer from card 1 detects a match | 1. Plain-code name search on the opening statement and the form, offered only on a Best match. 2. One AI call. 3. Only after Discover finds an existing capability | **1**: no AI call, predictable, testable. Option 3 comes too late (Understand is already done the "new" way) | Chosen by chief, 6.1 (option 1) |

"To chief": the chief writes "Chosen by chief, 6.1" (recommended option) or opens an issue, per
section 6 of the automation spec. D-B and D-F depend on work facts; if the chief reads that as touching
a work fact, he opens the issue instead.

## 18. Work facts (no recommendation, Gian decides)

The chief opens one issue per row with the label shown and builds everything around it.

| # | Question | Options (not ranked) | What Phase 9 builds meanwhile | Label |
|---|---|---|---|---|
| WF-1 | How can the CodeVision server read a file as it is on Bitbucket `main`? (CodeVision internals and bank policy: network access from the OCP server to Bitbucket, a service account or token, who owns it) | a. Bitbucket REST API with a read-only service account. b. The server's reference copy, if it is kept equal to `main`. c. A scheduled copy of `main` on the server. d. Not allowed: the check cannot run at work | `DA_MAIN_SOURCE` with `fake` and a `bitbucket` placeholder that says "not configured". "Continue without the check" is audited and stored for the PR summary (section 5 step 6) | `needs-gian` |
| WF-2 | The real capability list and named seniors, and who keeps them (bank org data) | Unknown. Not guessed here | A made-up starter catalog in the seed; the shape is the rulebook part. No real names anywhere in code or tests | `needs-gian` |
| WF-3 (Q14 b, c, carried) | Does a reference copy of CodeVision's source exist on the OCP server, how close is it to `main`, and does importing modules touch a database, the LLM or a file share? Impact and the safety-net proof both read it | Unknown | The Phase 6 reference-copy setting. "Impact could not be checked" and safety-net proof errors are shown plainly, never a silent pass | `needs-work-test` |
| WF-4 | How is Admin told about a new Unassigned file? (CodeVision internals: email, Teams, only the in-app queue) | a. In-app queue only (Phase 11 screen). b. Also an email or chat message. c. Other | The queue table and `list_unassigned()`. No message is sent | `needs-gian` |
| WF-5 (Q7, carried) | The server's context limit per model name. The today-draft, safety-net and scoped Generator prompts carry real code | Unknown. Not guessed here | The existing guards (`build_max_prompt_chars`, `tester_max_prompt_chars`, HTTP 400). Too big for the today-draft: names only (section 6). Too big for the safety net: step `s_unable` with Get help | `needs-work-test` |
| WF-6 (Q9, carried) | Which model is the Tester at work, now also reading code for the safety net | As Phase 7 WF-1: a. `default`, b. `reasoning-vlm`, c. empty (= the generator's model) | The model stays a setting. Attempts and dropped cases are saved per net, so the bake-off can compare | `needs-work-test` |
| WF-7 | Which on-prem model drafts "what it does today", and is it good enough on real CodeVision code? | a. the Generator's role setting. b. the Tester's role setting. c. a new role setting | A role setting chosen in the plan; nothing hard-coded. A bad draft costs him an edit, never a wrong record (he confirms) | `needs-work-test` |
| WF-8 | Does the code index at work (P15) hold CodeVision's own Python code with paths and symbols, so name and description search find real programs? | Unknown until P15 is built at work | The `SearchIndex` interface and the fake index, extended with the made-up target | `needs-work-test` |

## 19. Open items

- **W6 (watch, carried):** the safety-net call is the first Tester call that sees code, by design
  (decision 8). The criterion test call must still hold no code; a test proves it (9-29). The two calls
  must never share a conversation.
- **Demo out of date:** "Run git pull" ignores ZIP workspaces (Phase 5 Q10); section 5 rewords it. The
  demo is not changed by this phase.
- **Reference copy vs his folder:** impact and the safety-net proof read the reference copy plus his
  baseline. If the reference copy is older than `main`, a caller added on `main` is missed. WF-3.
- **Screens and database code** are often not covered by the safety net. This is expected (redesign
  5.8); the not-covered list is the honest answer. If most real targets come out "not covered", Gian
  may want a lighter path. Watch at the work test.
- **Q2** (shared server database) is still open; the Unassigned queue assumes one database (as Phase 8).
- No facts file was given for Phase 9. If the chief has facts, compare them with sections 1 and 18
  before the plan.

Photos: none needed for this spec. WF-1 and WF-3 are questions for the CodeVision team, not photos.

## 20. Done when (every line becomes a test, Given / When / Then)

| # | Given | When | Then |
|---|---|---|---|
| 9-1 | Home | the screen is drawn | card 2 "Enhance or fix an existing program" is active; clicking it creates a request with `kind` `enhance` at `e_find` |
| 9-2 | a card 1 opening statement naming a made-up file stem | the form is submitted | the switch offer shows with the path; no AI call was made for it |
| 9-3 | 9-2 | Switch to Enhance or fix | same CVDA number, `kind` `enhance`, step `e_pick` with that candidate first, audit `switched_to_enhance` |
| 9-4 | 9-2 | No, this is new | no offer again on this request, audit `switch_declined` |
| 9-5 | a message naming a file stem | Find runs | that file is Best match, found by "Name"; at most `enhance_name_top_k` name candidates |
| 9-6 | a description only | Find runs | at most 3 meaning candidates, merged by path with any name hits |
| 9-7 | a deprecated, restricted or secret-looking file in the index | Find runs | it is never a candidate |
| 9-8 | a candidate matching a catalog pattern | shown | its capability and named senior show |
| 9-9 | a candidate in no capability | confirmed | a capability must be picked; an `open` Unassigned row exists with his pick; a second request on the same path links to the same row |
| 9-10 | no candidates three times | Find | only Get help is offered |
| 9-11 | a target outside the allowed folders, or not `.py` | confirm | refused with the reason |
| 9-12 | his file equals the fake main except line endings and a BOM | freshness | passed, step `e_fresh` |
| 9-13 | his file differs from the fake main | freshness | step `e_stale`, the banner names the file and mentions both `git pull` and a fresh ZIP |
| 9-14 | 9-13, the folder then updated | I've updated, check again | passed |
| 9-15 | 9-13 | My local changes are intentional | `e_fresh`, override `intentional` stored and audited |
| 9-16 | `DA_MAIN_SOURCE=bitbucket` | freshness | "I could not reach Bitbucket main"; Continue without the check stores override `unchecked`; never a silent pass |
| 9-17 | a confirmed target | freshness passes | his text is saved as the `baseline` and is the code used for the today-draft and the safety net |
| 9-18 | a fresh target | Understand starts | one today-draft call; the prompt holds the target's function bodies and no chat; the draft is in the box; it holds no code |
| 9-19 | a today-draft prompt over `build_max_prompt_chars` | the call is built | only names, lines and docstrings are sent and the chat says so |
| 9-20 | the form | shown | it has What it does today, What should change, What must NOT change plus the usual boxes; NC items are numbered NC-1... |
| 9-21 | an AI guess naming a symbol not in the split | functions in scope | that symbol is dropped; he must keep at least one ticked |
| 9-22 | a record saved before Phase 9 | loaded | it loads; the new fields are empty |
| 9-23 | a made-up package with a direct call, an aliased module call, a method call by name and an import only | impact runs | rows Direct, Direct, Possible and Imports only; the target itself is not listed; the limits line shows |
| 9-24 | more callers than `impact_max_callers` | impact | the cap and "and N more" |
| 9-25 | no reference copy | impact | "Impact could not be checked", the request continues, the gap is stored |
| 9-26 | a caller inside a flag-for-review zone | impact | that zone is in `zones_touched` with "a caller is in this zone" |
| 9-27 | Findings look right on an enhance request | pressed | the safety-net call runs; the prompt holds in-scope bodies, NC and AC lists, and no chat |
| 9-28 | a safety-net reply naming an unknown function, NC or AC ID | checked | a retry note; two unusable replies give `s_unable` with Try again and Get help |
| 9-29 | the criterion test-plan and criterion test-writing Tester prompts on an enhance request | built | they hold no code text (W6) |
| 9-30 | a safety net of 6 cases | the proof runs on the baseline | all 6 pass and are marked proven |
| 9-31 | one case that fails on the baseline, fixed on attempt 2 (fake) | the proof runs | one fix call for that case only; the other 5 stay byte for byte the same |
| 9-32 | one case still failing after `safety_net_max_attempts` (fake switch) | the proof ends | the case is dropped; its function or NC is in not covered with "could not be made to pass on today's code" |
| 9-33 | a function in scope and an NC item with no proven case, not listed by the Tester | the net is saved | both are in not covered |
| 9-34 | `s_review` | the Safety net tab is drawn | banner, table with Must still pass or Expected to change (AC-n), the not-covered card, Continue to Approach |
| 9-35 | `s_review` | he changes a mark to another AC | saved, audit `expected_change_marked` |
| 9-36 | an enhance request without `safety_net_accepted` for the latest record version | the gate runs | check 4 fails |
| 9-37 | an accepted net | the approach version's test set is built | it holds the safety-net methods except expected-to-change ones, byte for byte as accepted |
| 9-38 | the Generator prompt for a target | built | it holds in-scope bodies, imports and other signatures only, no other bodies |
| 9-39 | an edit block outside any in-scope function (fake switch) | Layer A | A8 fails the round, naming the symbol |
| 9-40 | an in-scope function with a Direct caller outside the plan, and a changed signature (fake switch) | Layer A | A9 fails the round naming the caller; with the caller's file in the plan, it passes A9 |
| 9-41 | a change that breaks a must-still-pass safety-net test | Layer B | a failed round; the report names S-n, today's behaviour and the NC ID |
| 9-42 | a green build | the expected-to-change tests run for information | the Tests tab shows "Changed, as expected" or "Still the old behaviour"; the label does not change |
| 9-43 | an NC item that is not covered | Layer C | an FYI "Not covered by the safety net, check manually"; the label is not lowered by it |
| 9-44 | a requirement lane that changes AC-1 on an enhance record | Confirm v2 | the safety-net tests are unchanged; cases linked to AC-1 are shown for his confirm |
| 9-45 | Get help at any Phase 9 step | pressed | ESCALATION_REQUIRED, open item `Escalated in Enhance: <step>` |
| 9-46 | any Phase 9 action | sent with an old revision | refused with the stale message |
| 9-47 | a rulebook version saved before Phase 9 | loaded | the eight new policy fields hold the starter values; the catalog is empty |
| 9-48 | any Phase 9 browser read | built | only targets (before Approach) or planned files are read; nothing is written by Find, freshness, impact or the safety net |
| 9-49 | This is a fix | pressed at `e_pick` | `kind` `fix`; What should change is pre-filled "Make it work as intended: ..." |
| 9-50 | Playwright with the private test folder | card 2 through to a green build | the in-scope function changed; every other function in the target is byte for byte the same |

Plus: `pytest` 0 failures, `ruff check` 0 problems, smoke check passes, code reviewer 0 Must fix, and a
home check by Gian on `127.0.0.1:8050` with the practice folder.

## 21. Files the builder will touch (for planning, not a limit)

`pydantic_classes/da_models.py` (kind, record fields), `pydantic_classes/da_request_record_models.py`
(today, NC items, targets, functions in scope), `pydantic_classes/da_enhance_models.py` (new:
`TodayDraft`, `SafetyNet`, `ImpactRow`, `FreshnessResult`), `da_rulebook_models.py` and
`data/da_rulebook_seed.json` (`Capability`, policy fields), `agents/da_enhance_flow.py` (new: find,
freshness, switch offer, safety net), `agents/da_enhance_checks.py` (new: name scoring, catalog lookup,
safety-net checks, not covered), `agents/da_impact.py` (new, `ast`), `agents/da_main_source.py` (new:
fake and placeholder), `agents/da_understand_flow.py` (enhancement mode), `agents/da_discover_flow.py`
(queries, impact column), `agents/da_approach_flow.py` and `agents/da_approach_checks.py` (gate check 4
on enhance), `agents/da_build_flow.py` (test set with safety net, scoped prompt, A8, A9,
expected-to-change run), `agents/da_tester_review.py` (check 1 NC line), `agents/da_refine_flow.py`
(re-mark on revision), the today-draft and safety-net prompts under `data/`, `agents/da_llm_client.py`
(fake script and pretend-server answers), `db_table_functions/db_tbl_da_enhance.py` (new),
`db_table_functions/db_tbl_da_discovery.py` (impact column), `web/da_workspace.js` (read targets before a
plan exists), `layouts/da_developer_assistant_page.py`, the page callbacks, `web/da_web_components.py`
(Home card 2, candidate table, freshness banner, enhancement summary, impact card, Safety net tab),
`configs/da_config.py`, `.env.example`, made-up files under `src/data/`, `da_smoke_check.py`,
`README.md`, `CLAUDE.md` ("Current phase"), `docs/enhance-work-test.md` (new, Command Prompt only), and
the matching tests.
