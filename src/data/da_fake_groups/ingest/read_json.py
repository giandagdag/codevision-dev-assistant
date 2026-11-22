"""Made-up demo program (Fix G6 S7): reads JSON files."""

import ingest.load_files


def rows(folder: str) -> list[str]:
    return [f"{folder}/a.json"] if ingest.load_files else []
