# Fix G8 plan: the real index must load

Spec: `specs/fix-g-8.md`. Branch `phase-g-fix-8`. Commit subjects "G8 step N".

Note: the spec says import the splitter's limit into `da_search_index`. The splitter already
imports `looks_secret` from `da_search_index`, so that would be a circular import. Instead the
number 2000 lives once in `da_search_index.PIECE_TEXT_LIMIT` and the splitter imports it
(`SNIPPET_LIMIT = PIECE_TEXT_LIMIT` stays as its name). Same effect, one source of truth.

Review fixes (round 1): step 0 added; error raised `from None` with the list position (not
`piece_no`), tests check the text is not in message or cause; local name `HIT_SNIPPET_LIMIT` for the
500; no-space hard cut; Discovery-level test for G8-5; the import flip is listed in the PR body.

## Step 0: CLAUDE.md "Current phase" says Fix G8 in build, G7 merged (PR #116). Stay under 6,000 bytes.

## Step 1: loader accepts up to 2000, honest error (S1, S3, S4, G8-3, G8-7)
- `da_search_index.py`: add `PIECE_TEXT_LIMIT = 2000`; `IndexPiece.snippet` uses it.
- `da_code_splitter.py`: `SNIPPET_LIMIT = PIECE_TEXT_LIMIT`.
- In `load_index_file`, check pieces one by one; a snippet-length failure raises
  "Piece N has a snippet that is too long: L characters, the limit is 2,000" (no text shown).
  Other problems keep today's message (its trailing "500 characters" hint changes to 2,000).
- Tests: replace the 501 test: 501 and 2000 accepted, 2001 refused; 2,350 error names piece number,
  length, limit, never the text; another shape problem still refuses the whole file.
- Proof: pytest tests/test_da_search_index.py.

## Step 2: cut when making a hit (S2, G8-2, G8-4, G8-6)
- `_to_hit` cuts at a word boundary to 500 incl. "…"; short snippets unchanged.
- Tests: long piece gives hit <= 500 ending "…", other hit fields unchanged; 80 chars unchanged;
  stored piece keeps full text (Enhance sees it).

## Step 3: real splitter path, smoke check, docs (S5, S6, G8-1, G8-5)
- Test: build a 1,800-char function with the real splitter + `build_index` (FakeEmbedder), load via
  `CodeVisionSearchIndex`, search finds a hit of <= 500.
- Smoke check item 40: make `loans.py` also hold a ~1,800-char function; still passes.
- `docs/discover-work-test.md`: note for "index file could not be read".

Then full pytest, ruff, smoke check, code review, PR into `auto/phases-7-10`.
