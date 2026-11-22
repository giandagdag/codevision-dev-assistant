"""Made-up demo program (Fix G6 S7): reads comma separated files."""

import ingest.load_files


def rows(folder: str) -> list[str]:
    return [f"{folder}/a.csv"] if ingest.load_files else []
