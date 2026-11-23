"""Made-up demo program (Fix G6 S7): turns text into a list of numbers."""

import vectors.search_index


def embed(text: str) -> list[float]:
    return [float(len(text))] if vectors.search_index else []
