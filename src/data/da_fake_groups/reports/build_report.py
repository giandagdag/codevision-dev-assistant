"""Made-up demo program (Fix G6 S7): builds a monthly report from its helpers."""

import reports.format_totals
import reports.page_header
import reports.write_pdf


def build(month: str) -> str:
    return reports.page_header.title(month) + reports.format_totals.line(month) + (
        reports.write_pdf.name(month)
    )
