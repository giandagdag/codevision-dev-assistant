"""Made-up demo program (Fix G6 S7): the title block of a report page."""

import reports.build_report


def title(month: str) -> str:
    return f"Report {month}" if reports.build_report else ""
