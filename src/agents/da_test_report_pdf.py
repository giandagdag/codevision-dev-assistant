"""Lay the saved test report (`build_report` data) out as a PDF (Fix G5, F2 and F4).

Pure code: report dict in, PDF bytes out. Same columns in every section, one row per
evidence line, so a reader can run an eye down the page like a 5250 list screen.
"""

from agents.da_evidence_helper import hide_secret
from agents.da_model_label import model_label
from agents.da_pdf_writer import PdfReport

CUT = 500
SECTION_COLUMNS = [("Test", 8), ("Criterion or target", 22), ("Input", 17), ("Expected", 17),
                   ("Actual", 17), ("Match", 7), ("Result", 12)]  # fmt: skip
_LAYER_NAMES = {"requirement": "Against the requirement", "code": "Against the code",
                "safety": "Safety net"}  # fmt: skip


def pdf_file_name(request_id: str, build_number: int) -> str:
    # The request ID already starts with CVDA-.
    return f"{request_id}-build-{build_number}-test-report.pdf"


def _safe(value) -> str:
    """F4: secrets hidden, then cut at 500 characters."""
    return hide_secret(str(value))[:CUT]


def _section_rows(rows: list[dict]) -> list:
    out: list = []
    for row in rows:
        name = (row["id"] or row["name"]) + ("*" if row["negative"] else "")
        crit = _safe(row["criterion"])
        if row["evidence"]:
            for i, e in enumerate(row["evidence"]):
                out.append([name if i == 0 else "", crit if i == 0 else "",
                            _safe(e["given"]), _safe(e["expected"]), _safe(e["actual"]),
                            "yes" if e["match"] else "NO",
                            row["result"] if i == 0 else ""])  # fmt: skip
        else:
            out.append([name, crit, row["evidence_note"], "", "", "", row["result"]])
        if row["message"]:
            out.append(f"Message: {_safe(row['message'])}")
    return out


def report_pdf(report: dict) -> bytes:
    h = report["header"]
    pdf = PdfReport(f"{h['request_id']} build {h['build_number']} test report")
    pdf.heading(f"Test report: {h['request_id']} {h['title']}")
    models = ", ".join(f"{k}: {model_label(v)}" for k, v in h["models"].items()) or "-"
    pdf.paragraph(f"Build {h['build_number']}, round {h['round']}. {h['time']}. Models: {models}.")
    pdf.paragraph(f"Requirement / approach / test set version: {h['requirement_version']} / "
                  f"{h['approach_version']} / {h['test_set_version']}. Ran: {h['ran_where']}.")
    pdf.paragraph(f"Label: {h['label']}", bold=True)
    if h.get("reason"):
        pdf.paragraph(h["reason"])
    shown = {s["key"] for s in report["sections"]}
    summary = [[_LAYER_NAMES[k], str(c["passed"]), str(c["failed"]), str(c["other"]),
                str(c.get("dropped", 0)) if k == "code" else "-"]
               for k, c in report["summary"].items() if k != "safety" or k in shown]  # fmt: skip
    pdf.heading("Summary")
    pdf.table([("Layer", 40), ("Passed", 15), ("Failed", 15), ("Not proven", 15), ("Dropped", 15)],
              summary)
    load_error = report.get("load_error")
    if load_error:
        pdf.paragraph("Load error: " + load_error["text"], bold=True)
        for line in load_error["tail"]:
            pdf.paragraph(line)
    for section in report["sections"]:
        pdf.heading(section["title"])
        pdf.table(SECTION_COLUMNS, _section_rows(section["rows"]))
    if report["dropped_code_tests"]:
        pdf.heading("Dropped code tests")
        for name in report["dropped_code_tests"]:
            pdf.paragraph(f"- {name}")
    pdf.heading("The Tester's checks")
    pdf.table([("#", 6), ("Check", 54), ("Result", 20), ("Findings", 20)],
              [[str(c["number"]), c["name"], c["state"], str(c["findings"])]
               for c in report["checks"]])  # fmt: skip
    if report["findings"]:
        pdf.heading("Findings")
        pdf.table([("ID", 8), ("Severity", 10), ("Where", 22), ("Message", 45), ("Rule", 15)],
                  [[f["finding_id"], f["severity"],
                    f"{f['file']}:{f['line']}" if f["file"] else "",
                    _safe(f["message"]), str(f.get("cites", ""))]
                   for f in report["findings"]])  # fmt: skip
    pdf.paragraph(report["legend"])
    return pdf.to_bytes()
