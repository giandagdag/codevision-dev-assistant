"""Made-up demo program (Fix G6 S7): loads input files by calling its helpers."""

import ingest.check_rows
import ingest.read_csv
import ingest.read_json


def load_all(folder: str) -> int:
    return len(ingest.read_csv.rows(folder)) + len(ingest.read_json.rows(folder)) + len(
        ingest.check_rows.bad_rows(folder)
    )
