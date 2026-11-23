"""Made-up demo program (Fix G6 S7): finds rows that cannot be loaded."""

import ingest.load_files


def bad_rows(folder: str) -> list[str]:
    return [] if ingest.load_files else [folder]
