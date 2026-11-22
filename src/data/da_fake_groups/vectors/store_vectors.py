"""Made-up demo program (Fix G6 S7): keeps the saved vectors."""

import vectors.search_index


def load() -> list[str]:
    return ["v1"] if vectors.search_index else []
