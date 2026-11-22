"""Made-up demo program (Fix G6 S7): looks up similar text through its helpers."""

import vectors.embed_text
import vectors.rank_hits
import vectors.store_vectors


def find(question: str) -> list[str]:
    stored = vectors.store_vectors.load()
    return vectors.rank_hits.best(vectors.embed_text.embed(question), stored)
