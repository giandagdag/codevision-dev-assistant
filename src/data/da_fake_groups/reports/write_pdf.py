"""Made-up demo program (Fix G6 S7): picks the file name of a report."""

import reports.build_report


def name(month: str) -> str:
    return f"{month}.pdf" if reports.build_report else ""
