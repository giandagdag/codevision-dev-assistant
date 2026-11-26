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

If Discovery says "The search index file could not be read", send us the message text and the piece
number (Fix G8). A piece may hold up to 2,000 characters; "Piece 212 has a snippet that is too long"
means the builder wrote more than that. The AI still sees at most 500 characters per hit.

## Keep the data outside the code folder (Fix G5 R9)

A new ZIP of the code must not wipe the index, the tags or the run history. In your work `.env` set:

- `DA_CODE_INDEX_DIR=C:\Users\<you>\CodeVisionDA\data\da_code_index` (index, tags, run history)
- `DA_DB_PATH=C:\Users\<you>\CodeVisionDA\data\devassist.db` (requests, rulebook, audit)

Both folders are outside the unzipped code. Copy them once from the old place, then every new ZIP keeps
them. At start the log prints one line, "Developer Assistant data: index folder ..., database ...",
paths only. If it shows a folder inside the new ZIP, the data was left behind.

## Tagger checks (Fix G5 R6 to R8)

- Each run row shows the Index result and the Tags result on separate lines: green when all programs are
  tagged, amber ("95 of 101 tagged, 6 could not be read"), red when the tag step crashed.
- Review queue, **Try the tagger on one program**: pick a program, press Try. It shows the AI reply (first
  2,000 characters), what the reader made of it and the reason when it could not. Nothing is saved.
- **Re-check** also tries the programs marked "could not be read" again.

## After the 20 Nov work test (Fix G4)

In Admin, Capability catalog: click **Remove all starter items** (the made-up Harbour Loans capabilities
and the demo folder), then run a **Full rebuild**. Open the **Review queue** view: the AI may now suggest
new capabilities (a suggestion card with Create and assign, Assign to, Reject). The Overview lists
"Starter items in the catalog" until they are removed. The home fake run shows no suggestion card
(only the tests use that script).
