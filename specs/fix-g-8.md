# Fix G8: the real index must load (snippet length mismatch)

Version 1.1 APPROVED, 26 Nov 2026 19:20 SGT. Gian 25 Nov 14:51: "park it, make sure this gets
queued and fixed"; 26 Nov 19:15: resume all pending fixes. Every choice below is decided; no D-x is
open. Small fix. Queue order: **after G7 is merged**. Branch `phase-g-fix-8`, cut from the newest
`origin/auto/phases-7-10` after G7 is merged. Builder: commit this spec as `specs/fix-g-8.md` as the
first commit on the branch. Normal build: plan `specs/fix-g-8-plan.md`, plan review, small steps with
tests, code review (max 3 rounds), full pytest, ruff, smoke check. Commit subjects "G8 step N". PR into
`auto/phases-7-10`; the chief merges.

## 0. What Gian saw (25 Nov, CVDA-2026-0006 "CLI Text Uppercase Converter", Discover step)

Chat: "The search index file could not be read (ValidationError). Check that it has build_id and a
list of pieces, and that no snippet is longer than 500 characters." Then "Discovery did not start.
Press Try again to search approved sources." Try again cannot help: the file is the problem.

## 1. Root cause (read in code at `auto/phases-7-10` da159ef, 23 Nov; not yet seen on the work file)

| Part | Fact |
|---|---|
| Builder | `src/agents/da_code_splitter.py`: `SNIPPET_LIMIT = 2000`. Each piece keeps up to 2,000 characters. `src/da_build_code_index.py` writes `"snippet": p.snippet` into `da_code_index.json` as is |
| Loader | `src/agents/da_search_index.py`: `IndexPiece.snippet` has `max_length=SNIPPET_LIMIT` taken from `pydantic_classes/da_discovery_models.py` where **`SNIPPET_LIMIT = 500`** (the limit for a search hit shown to the AI) |
| Result | One function or class over 500 characters makes `load_index_file` raise for the **whole file**. The error text blames the file and hides the real reason |
| Why not seen at home | The made-up index has short snippets (home tests never build a piece over 500) |

Two constants share the name `SNIPPET_LIMIT` with different values (2000 in the splitter, 500 in the
models). That is the trap.

## 2. What we build

| # | Piece |
|---|---|
| S1 | **Two names, two jobs.** In `da_search_index.py`, `IndexPiece.snippet` allows up to the splitter's limit (import it as `PIECE_TEXT_LIMIT`, 2000). The index file is storage; its pieces may hold what the builder wrote |
| S2 | **Cut when making a hit.** `FakeSearchIndex._to_hit` cuts the snippet to the hit limit (500) at a word boundary and adds "…". A hit shown to the AI or the developer never exceeds 500. Nothing else that reads pieces (Enhance, tagger suggestions) loses text |
| S3 | **Honest error.** If a piece still fails to load, the message names the piece number and the field in plain words ("Piece 212 has a snippet that is too long: 2,350 characters, the limit is 2,000"), not only the exception name. Other shape problems keep today's text |
| S4 | **A damaged file is still refused.** Any other shape problem still refuses the whole file (it may be damaged). Only the length mismatch is fixed |
| S5 | **Home test gap.** The home smoke check and the loader tests gain a piece with a 1,800-character snippet built by the real splitter path |
| S6 | **Docs:** `docs/discover-work-test.md` notes: if Discovery says the index file could not be read, send the message text and the piece number |

## 3. Edge rules

- No new library, no new setting, no change to the index file format (old files read as they are).
- Never log or show the snippet text in an error, only its length and the piece number.
- Tests use made-up code only. AF-2 label scan still passes.
- Fake AI at home only. Never touch `main`.

## 4. Acceptance criteria (Given / When / Then)

| ID | Given / When / Then |
|---|---|
| G8-1 | Given an index file built by the real splitter from a 1,800-character function, when it loads, then no error |
| G8-2 | Given that piece found by a search, then the hit snippet is at most 500 characters, ends at a word with "…", and no other hit field changes |
| G8-3 | Given a piece with a 2,350-character snippet, when the file loads, then the error names the piece number, the length and the limit 2,000, and never shows the text |
| G8-4 | Given a short snippet (80 characters), then the hit shows it unchanged, no "…" |
| G8-5 | Given a built index with pieces over 500, when Discovery runs with provider `codevision`, then it starts and finds hits |
| G8-6 | Given Enhance reads a long piece for its impact section, then it still sees the full stored text |
| G8-7 | Given the old test that refused a 501-character snippet, then it is replaced: 2,001 refused, 501 accepted |

## 5. Work-laptop workaround until G8 is merged (test only, undo after)

PowerShell is not allowed on the work laptop, so no check script is needed. Just edit one file:

- `src\pydantic_classes\da_discovery_models.py` line 15: `SNIPPET_LIMIT = 500` to `SNIPPET_LIMIT = 2000`.
- Restart the app, then press **Try again** on Discover.
- Undo this edit after G8 arrives (G8 makes it unnecessary, and the AI would then see 2,000-character snippets).

## 6. Out of scope

- A Rebuild that cuts snippets (the 2,000 stays useful for Enhance and the tagger).
- Any change to how many hits or how much text goes to the AI.
