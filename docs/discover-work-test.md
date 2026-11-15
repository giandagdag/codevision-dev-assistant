# Discover: the real CodeVision index at work (fix B1, section 9)

Why: at home Discover searches a made-up practice index. At work it must search CodeVision's own
Python code. That needs an index built once at work, with CodeVision's embedding call.

**PowerShell and the browser DevTools are blocked on the work laptop: use Command Prompt (`cmd`).**

AS400 picture: the piece list is a physical file; the vector file is a keyed logical over it.
Record N in one is key N in the other, so they are saved together or not at all.

## Build the index

1. Open Command Prompt, go to the Developer Assistant folder.
2. Set the source folder if it is not the running `src` folder: `set DA_CODE_INDEX_SOURCE=<folder>`.
3. Run: `.venv\Scripts\python src\da_build_code_index.py`
4. It prints progress every 50 pieces, then one line.

## What the summary means

- `Saved N pieces to ...`: the index is ready. Files are in `src/data/da_code_index/` (Git ignores them).
- `skipped: path symbol`: that piece could not be embedded (only the name is printed, never the code).
  A few skipped pieces are fine.
- `Not saved: ... over 10%`: too many pieces failed. The old index stays. Check the embedding service
  and run again.
- `Stopped: a vector of size ...`: the embedding model changed in the middle. Nothing saved.
- `This only works inside CodeVision at work.`: you ran it at home; use `--fake` for a practice build.

## Rebuild

Run the same command again. The new index replaces the old one only when it is complete.
(A Rebuild button in Admin is parked.)

## Check in the app

Set `DA_SEARCH_PROVIDER=codevision`, open Discover and run a search in both modes. With no index the
chat says: "The CodeVision index needs building: run `python src\da_build_code_index.py`." and the
request carries on. Setting `DA_CODE_INDEX_MAX_DISTANCE` (default 0.90) controls how close a meaning hit
must be.
