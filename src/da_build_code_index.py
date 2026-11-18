"""Builds the real CodeVision index: one vector per code piece (fix B1, I2 and I3).

Run at work: python src\\da_build_code_index.py
AS400 picture: the piece list is the physical file, the vector file is a keyed logical over it.
Record N in one is key N in the other, so both are saved together or not at all.
"""

import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

import faiss
import numpy as np

from agents.da_code_index import (
    DEFAULT_INDEX_DIR,
    FAISS_NAME,
    PIECES_NAME,
    Embedder,
    FakeEmbedder,
    WorkEmbedder,
)
from agents.da_code_splitter import split_folder
from da_logging import get_logger

logger = get_logger(__name__)

MAX_FAILED_SHARE = 0.10
PROGRESS_EVERY = 50


@dataclass
class BuildSummary:
    saved: bool
    count: int = 0
    skipped: list[str] = field(default_factory=list)  # "path symbol", never the text
    message: str = ""


def _is_product_code(path: str) -> bool:
    # The assistant itself (da_ files and folders) is not product code.
    return not any(part.startswith("da_") for part in Path(path).parts)


def _is_excluded(path: str, patterns: Sequence[str]) -> bool:
    # The leading "/" lets a pattern like "*/build/*" match a top-level build folder too.
    return any(fnmatch(path, p) or fnmatch("/" + path, p) for p in patterns)


def build_index(
    source: Path,
    out_dir: Path,
    embedder: Embedder,
    now: datetime | None = None,
    say=print,
    extra_exclusions: Sequence[str] = (),
) -> BuildSummary:
    pieces = [
        p for p in split_folder(source)
        if _is_product_code(p.path) and not _is_excluded(p.path, extra_exclusions)
    ]
    vectors: list[list[float]] = []
    kept = []
    skipped: list[str] = []
    for number, piece in enumerate(pieces, start=1):
        vector = embedder.embed(f"{piece.path} {piece.symbol}\n{piece.snippet}")
        if vector is None:
            skipped.append(f"{piece.path} {piece.symbol}")
        elif vectors and len(vector) != len(vectors[0]):
            return BuildSummary(
                False, 0, skipped,
                f"Stopped: a vector of size {len(vector)} came after size {len(vectors[0])} "
                f"(at {piece.path} {piece.symbol}). Nothing saved; the old index stays.",
            )
        else:
            vectors.append(vector)
            kept.append(piece)
        if number % PROGRESS_EVERY == 0:
            say(f"  {number} of {len(pieces)} pieces done")
    if not pieces or len(skipped) > MAX_FAILED_SHARE * len(pieces):
        return BuildSummary(
            False, 0, skipped,
            f"Not saved: {len(skipped)} of {len(pieces)} pieces could not be embedded "
            f"(over {int(MAX_FAILED_SHARE * 100)}%, or no pieces). The old index stays.",
        )
    _save(out_dir, source, kept, vectors, now or datetime.now())
    return BuildSummary(True, len(kept), skipped, f"Saved {len(kept)} pieces to {out_dir}.")


def _save(out_dir: Path, source: Path, kept, vectors, now: datetime) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    index = faiss.IndexFlatL2(len(vectors[0]))
    index.add(np.array(vectors, dtype="float32"))
    record = {
        "build_id": "cv-" + now.strftime("%Y%m%d-%H%M%S"),
        "built_at": now.isoformat(timespec="seconds"),
        "source": str(source),
        "vector_size": len(vectors[0]),
        "count": len(kept),
        "pieces": [
            {
                "piece_no": n, "path": p.path, "symbol": p.symbol, "line_start": p.line_start,
                "kind": "code", "language": "python", "snippet": p.snippet,
            }
            for n, p in enumerate(kept)
        ],
    }
    side_faiss, side_json = out_dir / (FAISS_NAME + ".new"), out_dir / (PIECES_NAME + ".new")
    faiss.write_index(index, str(side_faiss))
    side_json.write_text(json.dumps(record, indent=1), encoding="utf-8")
    os.replace(side_faiss, out_dir / FAISS_NAME)
    os.replace(side_json, out_dir / PIECES_NAME)


def main() -> int:
    source = Path(os.environ.get("DA_CODE_INDEX_SOURCE") or Path(__file__).resolve().parent)
    out_dir = Path(os.environ.get("DA_CODE_INDEX_DIR") or DEFAULT_INDEX_DIR)
    if "--fake" in sys.argv and os.environ.get("DA_LLM_PROVIDER") == "onprem":
        # A made-up index at work would be used silently by the codevision search (F7).
        print("--fake is for home only. At work, run it without --fake.")
        return 1
    embedder = FakeEmbedder() if "--fake" in sys.argv else WorkEmbedder()
    try:
        summary = build_index(source, out_dir, embedder)
    except RuntimeError as error:  # e.g. "This only works inside CodeVision at work."
        print(error)
        return 1
    finally:
        if isinstance(embedder, WorkEmbedder):
            embedder.close()
    print(summary.message)
    for name in summary.skipped:
        print(f"  skipped: {name}")
    return 0 if summary.saved else 1


if __name__ == "__main__":
    sys.exit(main())
