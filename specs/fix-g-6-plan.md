# Fix G6 plan: catalog from code links, a module in more than one capability, a readable map

Spec `specs/fix-g-6.md` (approved, no open D-x). Branch `phase-g-fix-6` from `origin/auto/phases-7-10`
(has G5); PR into it with `--body-file`. Commit subjects "G6 step N". No new library, no new table.
New rulebook field `kind` has a default, so old versions still read. At most 3 steps per run; push
each step to `origin phase-g-fix-6`. The spec is already tracked upstream, so there is no spec commit.

## Code facts (read 22 Nov)
- `da_code_clusters.py`: `module_weights`, `clusters` (label propagation, 20 rounds, sorted), cards in
  the tag store with `source="links"`. `groups()` is added beside them and reuses both.
- `da_admin_tagger.py`: `read_reply` uses `da_reply_reader.read_json_object` (G5), `name_key` (ignores
  case, spaces, plural s), `ScriptedTaggerClient` (home fake, answers by the module line).
- `da_admin_meaning.capability_of` calls `da_admin_modules.modules_by_capability` (all matches) and
  returns the first; `add_modules_to_form` moves a pattern; `module_chips` prints "x2".
- `Capability` (`da_rulebook_models.py`) gets `kind: str = "Business"`.
- Map data `agents/da_capability_map.py`; drawing only in `layouts/da_capability_map_view.py`.
- Job lock, G5 job watcher (`da_admin_watch.watch_step`) and `job_bar` are reused for the new job.

## Decisions (plan review, 22 Nov)
- **Where cards live:** group cards and "Also add" cards are NOT in the per-program tag store (one entry
  per path would clash with a program's own tag card). They live in one new JSON file beside
  `da_cluster_rejects.json` in the index folder (`da_group_cards.json`: open cards, plus rejected card
  fingerprints so Reject survives a reload). No database table.
- `not_in_group` paths leave that card and stay unassigned. Fake data: 12 grouped programs + 1 loner =
  13 programs (S7 and G6-1 agree this way). The "x2" shared marker stays in the "module chip", next to "Also in".
- `kind` accepts only "Business" or "Shared foundation" (default Business). Double click = two taps
  close together on `tapNode` (timestamp); the Open button is the sure way.
- Capability colours: small palette list in `styles/da_admin_styles.py`, picked by hash of the name.
- `clusters()` and `groups()` share one label-propagation helper (a loner has no weights, so `groups()`
  adds unlinked modules itself).
- The suggest agent uses the "Tagger" role model.

## Steps (each: tests, ruff, commit, push)
0. "Current phase" in CLAUDE.md names Fix G6 (under 6,000 bytes; size test runs).
### Part 1, suggest a catalog
1. S1 `groups(graph, store)` in `da_code_clusters.py`: label propagation without `MIN_TAGGED`;
   singletons join the group they link to most; groups over 25 split once by top folder; each group
   returns programs, top folders, links inside/outside. Test: 12-program fake graph, 3 groups + loner (G6-1 part).
2. S2/S6 naming: new `agents/da_capability_suggest.py` + prompt `data/da_group_prompt.md`: one call per
   group, paths and saved one-line summaries only, JSON name/description/not_in_group/confidence via
   `read_json_object`, one retry. Empty catalog line for the tagger prompt (S6). Scripted fake client.
3. S3 merge: second call merges names; code merges names equal by `name_key`, caps at 12 by merging the
   smallest into the most-linked neighbour; existing-capability names become a normal proposal. Tests G6-2, G6-3.
4. S4/S5 job and cards: button (fewer than 5 capabilities or over 30% unassigned, plus once after a Full
   rebuild with empty catalog), job with steps "Grouping programs", "Naming groups", "Merging" on the
   G5 bar and lock; cards with chips, Remove from this suggestion, Create and assign (one rulebook version,
   exact patterns, note names the suggestion), Reject; offer Re-check afterwards. Tests G6-1, 4, 5.
5. S7 fake data (12 programs, 3 groups, 1 loner) under the fake codevision data folder.

### Part 2, a module in more than one capability
6. M1 `capabilities_of(path, capabilities) -> (main, also)`; `capability_of` returns main; Unassigned
   count never counts a module with a main. Test G6-6.
7. M2 chips "Also in: X" in the catalog; meaning search and Discover label list main first then also.
8. M3 Browse modules: **Move here** and **Also add here** (new helper beside `add_modules_to_form`). Test G6-7.
9. M4 tagger reply `also` (one exact name) becomes a separate "Also add <path> to <name>?" card;
   Approve all high-confidence skips it. Test G6-8.
10. M5 test that escalation, flag zones, required reviewers use main only; each change = one version with a note.

### Part 3, readable map
11. C3 `kind` field (Business / Shared foundation), catalog edit, one rulebook version, old versions read Business.
12. C1/C2 map data: Unassigned hidden by default + header count with link to Review queue; min-calls
    slider (1 to 20, default 3), "Top 3 links per capability" switch; foundations as bottom chips. Test G6-9.
13. C4 click to focus (neighbours bright, `.faded` rest, arrows on its links), side panel with links in
    and out, top 5 calling programs, Open / double click moves in. Test G6-10.
14. C5 drawing: palette colour per name from `styles/`, labels below on white, wrap at spaces only,
    12 px, log edge width 1 to 6, `concentric` layout most-linked in the middle, size capped at 3x the
    smallest. Tests G6-11, G6-12.
15. C6 Links table view (sortable, filter by capability, "also" marked). Test G6-13.
16. C7 Playwright at 1366 and 1920 px on the 13-capability fake catalog: no overlap, at most 3 links
    per capability, Unassigned not drawn (G6-14). AF-2 label scan on new parts (G6-15). Work notes in `docs/`.

## Additions from plan review (they belong to the steps named)
- Step 2 tests: prompt holds paths and summaries only; name 2 to 40, description at most 120; one retry;
  empty-catalog line. Step 4: card shows "N programs, M links inside" and confidence; Create and assign
  edits name and description and picks seniors (G6-4 test covers them).
- Step 5 also builds the **13-capability fake catalog** (made-up names incl. "Embedding and Vector";
  Config, Classes, Database as Shared foundation) used by steps 12 to 16.
- Step 7 test: chip "Also in: Ingestion"; main listed first. Step 11 test: old version reads Business.
- Step 12 adds the dashed also-in edge and "weaker links only around a focused capability".
  Step 13 adds "click on empty space clears the focus".
- Step 16 ends with full pytest, ruff, smoke check and screenshots, then code review.

## Rules
- Labels and buttons come from constants. Prompts hold paths and one-line summaries only; nothing
  logs a prompt, reply or code. Fake AI at home only. AI never creates a capability itself.
- Steps over 3 per run: `ops/chief_tick.py next` names the next step; code review after step 16 only.
