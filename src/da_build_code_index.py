"""Builds the real CodeVision index: one vector per code piece (fix B1, I2 and I3).

Run at work: python src\\da_build_code_index.py
AS400 picture: the piece list is the physical file, the vector file is a keyed logical over it.
Record N in one is key N in the other, so both are saved together or not at all.
"""

import hashlib
import json
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

import faiss
import numpy as np

from agents.da_code_graph import build_graph, load_graph, save_graph
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
    reread: int = 0  # pieces sent to the embedder (Delta: only new or changed files)
    mode: str = "full"  # what actually ran: Delta falls back to full when it cannot be trusted
    link_skipped: list[str] = field(default_factory=list)  # "path: reason", files without links


def _is_product_code(path: str) -> bool:
    # The assistant itself (da_ files and folders) is not product code.
    return not any(part.startswith("da_") for part in Path(path).parts)


def _is_excluded(path: str, patterns: Sequence[str]) -> bool:
    # The leading "/" lets a pattern like "*/build/*" match a top-level build folder too.
    return any(fnmatch(path, p) or fnmatch("/" + path, p) for p in patterns)


def _file_hashes(source: Path, pieces) -> dict[str, str]:
    """One hash per source file: a file that did not change keeps its saved vectors (Delta)."""
    return {
        path: hashlib.sha256((source / path).read_bytes()).hexdigest()
        for path in {p.path for p in pieces}
    }


def _load_old(out_dir: Path, embedder_name: str):
    """The saved index as (record, vectors), or None when Delta cannot trust it (then run Full)."""
    try:
        record = json.loads((out_dir / PIECES_NAME).read_text(encoding="utf-8"))
        index = faiss.read_index(str(out_dir / FAISS_NAME))
        vectors = index.reconstruct_n(0, index.ntotal)
    except (OSError, ValueError, RuntimeError):
        return None
    pieces = record.get("pieces", [])
    # Indexes saved before fix 3 have no hashes or embedder name: only a Full build can be trusted.
    if record.get("embedder") != embedder_name or len(pieces) != len(vectors):
        return None
    if not all("file_hash" in p for p in pieces):
        return None
    return record, vectors


def build_index(
    source: Path,
    out_dir: Path,
    embedder: Embedder,
    now: datetime | None = None,
    say=print,
    extra_exclusions: Sequence[str] = (),
    mode: str = "full",
    progress: Callable[[int, int], None] | None = None,
    stop: Callable[[], bool] | None = None,
    build: int = 0,
    graph_progress: Callable[[int, int], None] | None = None,
) -> BuildSummary:
    """Full embeds every piece. Delta embeds only pieces of new or changed files and reuses the
    saved vectors for the rest (flat index: vector N belongs to piece N). Both save the whole
    index again, both files together or not at all."""
    pieces = [
        p for p in split_folder(source)
        if _is_product_code(p.path) and not _is_excluded(p.path, extra_exclusions)
    ]
    hashes = _file_hashes(source, pieces)
    name = type(embedder).__name__
    old = _load_old(out_dir, name) if mode == "delta" else None
    reuse: dict[tuple, list[float]] = {}
    if old is not None:
        record, old_vectors = old
        unchanged = {
            n: old_vectors[n] for n, p in enumerate(record["pieces"])
            if hashes.get(p["path"]) == p["file_hash"]
        }
        reuse = {
            (p["path"], p["symbol"], p["line_start"]): [float(v) for v in unchanged[n]]
            for n, p in enumerate(record["pieces"]) if n in unchanged
        }
    to_embed = sum(1 for p in pieces if (p.path, p.symbol, p.line_start) not in reuse)
    vectors: list[list[float]] = []
    kept = []
    skipped: list[str] = []
    attempted = 0
    for piece in pieces:
        saved_vector = reuse.get((piece.path, piece.symbol, piece.line_start))
        if saved_vector is not None:
            vector = saved_vector
        else:
            if stop is not None and stop():
                return BuildSummary(False, 0, skipped, "Stopped. The old index stays.")
            attempted += 1
            vector = embedder.embed(f"{piece.path} {piece.symbol}\n{piece.snippet}")
            if progress is not None:
                progress(attempted, to_embed)
            if attempted % PROGRESS_EVERY == 0:
                say(f"  {attempted} of {to_embed} pieces done")
        if vector is None:
            skipped.append(f"{piece.path} {piece.symbol}")
        elif vectors and len(vector) != len(vectors[0]):
            if reuse:  # the embedder now gives another size: the saved vectors are useless
                return build_index(
                    source, out_dir, embedder, now, say, extra_exclusions, "full", progress, stop,
                    build, graph_progress,
                )
            return BuildSummary(
                False, 0, skipped,
                f"Stopped: a vector of size {len(vector)} came after size {len(vectors[0])} "
                f"(at {piece.path} {piece.symbol}). Nothing saved; the old index stays.",
            )
        else:
            vectors.append(vector)
            kept.append(piece)
    if not pieces or len(skipped) > MAX_FAILED_SHARE * max(attempted, 1):
        return BuildSummary(
            False, 0, skipped,
            f"Not saved: {len(skipped)} of {len(pieces)} pieces could not be embedded "
            f"(over {int(MAX_FAILED_SHARE * 100)}%, or no pieces). The old index stays.",
        )
    # Code links come after the pieces; Delta reuses the saved links of files that did not change.
    links = build_graph(
        source, hashes, load_graph(out_dir) if old is not None else None, graph_progress
    )
    _save(out_dir, source, kept, vectors, now or datetime.now(), hashes, name, build, links.graph)
    return BuildSummary(
        True, len(kept), skipped, f"Saved {len(kept)} pieces to {out_dir}.",
        reread=attempted, mode="delta" if old is not None else "full",
        link_skipped=links.skipped,
    )


def _save(
    out_dir: Path, source: Path, kept, vectors, now: datetime, hashes: dict[str, str],
    embedder: str, build: int = 0, graph: dict | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    index = faiss.IndexFlatL2(len(vectors[0]))
    index.add(np.array(vectors, dtype="float32"))
    record = {
        "build_id": "cv-" + now.strftime("%Y%m%d-%H%M%S"),
        "built_at": now.isoformat(timespec="seconds"),
        "source": str(source),
        "embedder": embedder,
        "build": build,
        "vector_size": len(vectors[0]),
        "count": len(kept),
        "pieces": [
            {
                "piece_no": n, "path": p.path, "symbol": p.symbol, "line_start": p.line_start,
                "kind": "code", "language": "python", "snippet": p.snippet,
                "file_hash": hashes[p.path],
            }
            for n, p in enumerate(kept)
        ],
    }
    side_faiss, side_json = out_dir / (FAISS_NAME + ".new"), out_dir / (PIECES_NAME + ".new")
    faiss.write_index(index, str(side_faiss))
    side_json.write_text(json.dumps(record, indent=1), encoding="utf-8")
    if graph is not None:
        save_graph(graph, out_dir)  # its own .new then replace, done just before the others
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
