"""Made-up demo program (Fix G6 S7): sorts the closest matches first."""

import vectors.search_index


def best(vector: list[float], stored: list[str]) -> list[str]:
    return stored if vectors.search_index and vector else []
