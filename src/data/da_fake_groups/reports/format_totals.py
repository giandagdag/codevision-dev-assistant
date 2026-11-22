"""Made-up demo program (Fix G6 S7): formats the totals line of a report."""

import reports.build_report


def line(month: str) -> str:
    return f"{month}: {1 if reports.build_report else 0}"
