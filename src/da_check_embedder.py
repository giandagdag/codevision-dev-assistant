"""Check that the work embedder answers, before a rebuild (fix 11-3).

Run at work: python src\\da_check_embedder.py
Prints only the vector size and the time taken, or the real cause in plain words. Never the text.
"""

import sys
import time

from agents.da_code_index import Embedder, WorkEmbedder


def check(embedder: Embedder | None = None, say=print) -> int:
    embedder = embedder or WorkEmbedder()
    started = time.monotonic()
    try:
        vector = embedder.embed("hello")
    except RuntimeError as error:
        say(f"Embedder check failed: {error}")
        return 1
    finally:
        if isinstance(embedder, WorkEmbedder):
            embedder.close()
    if vector is None:
        say("Embedder check failed: CodeVision's embedder gave no vector (service did not answer).")
        return 1
    say(f"Embedder works: vector size {len(vector)}, took {time.monotonic() - started:.1f} s.")
    return 0


if __name__ == "__main__":
    sys.exit(check())
