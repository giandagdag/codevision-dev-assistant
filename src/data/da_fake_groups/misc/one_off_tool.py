"""Made-up demo program (Fix G6 S7): a small tool that touches two areas; it links to the
ingest group twice and the reports group once, so it joins ingest."""

import ingest.load_files
import ingest.read_csv
import reports.build_report


def run() -> tuple:  # the loner
    loaded = ingest.load_files.load_all("x"), ingest.read_csv.rows("x")
    return loaded, reports.build_report.build("m")
