"""The test report page (Fix D1 spec E9): read only, print friendly, downloadable.

Presentation only. The report is ONE html text (`report_html`): the page shows it and the
Download button saves the very same text, so the two can never differ. Like an RPG spool file that
is both shown on screen and printed from the same output. No server path is ever in it.
"""

from html import escape

import dash_mantine_components as dmc
from dash import dcc, html

REPORT_PREFIX = "/dev-assistant/report/"
REPORT_SHELL_ID = "da-report-shell"
REPORT_BODY_ID = "da-report-body"
REPORT_PRINT_ID = "da-report-print"
REPORT_DOWNLOAD_ID = "da-report-download-button"
REPORT_FILE_ID = "da-report-download"
NO_REPORT_TEXT = "No report for this build (built before 17 Nov)."

# Print: A4, and no app chrome (header, side menu, buttons, chat).
PRINT_CSS = (
    "@page{size:A4;margin:12mm}"
    "@media print{.mantine-AppShell-header,.mantine-AppShell-navbar,.da-no-print,"
    "#da-demo-page-banner{display:none !important}"
    ".mantine-AppShell-main{padding:0 !important}}"
    ".da-report{font-family:sans-serif;font-size:13px}"
    ".da-report table{border-collapse:collapse;width:100%;margin:4px 0 12px}"
    ".da-report td,.da-report th{border:1px solid #bbb;padding:3px 6px;text-align:left;"
    "vertical-align:top}"
)


def parse_report_path(pathname: str | None) -> tuple[str, int] | None:
    """'/dev-assistant/report/CVDA-0001/3' gives ('CVDA-0001', 3); None for any other path."""
    if not pathname or not pathname.startswith(REPORT_PREFIX):
        return None
    parts = pathname[len(REPORT_PREFIX):].strip("/").split("/")
    if len(parts) != 2 or not parts[1].isdigit() or not parts[0]:
        return None
    return parts[0], int(parts[1])


def report_link(request_id: str, build_number: int) -> str:
    return f"{REPORT_PREFIX}{request_id}/{build_number}"


def _t(value) -> str:
    return escape(str(value))


def _table(head: list[str], rows: list[list[str]]) -> str:
    top = "".join(f"<th>{_t(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><tr>{top}</tr>{body}</table>"


def _evidence(row: dict) -> str:
    if not row["evidence"]:
        return f"<p><i>{_t(row['evidence_note'])}</i></p>"
    lines = [
        [_t(e["label"]), _t(e["given"]), _t(e["expected"]), _t(e["actual"]),
         "yes" if e["match"] else "NO"]
        for e in row["evidence"]
    ]  # fmt: skip
    return _table(["Check", "Input", "Expected", "Actual", "Match"], lines)


def _test(row: dict) -> str:
    star = "*" if row["negative"] else ""
    name = _t(row["id"] or row["name"])
    head = f"<h4>{name}{star} {_t(row['criterion'])}: {_t(row['result'])}</h4>"
    given, expect = _t(row["given"]), _t(row["expect"])
    text = f"<p>Given: {given}<br>Expect: {expect}</p>" if row["given"] else ""
    fail = f"<p>Message: {_t(row['message'])}</p>" if row["message"] else ""
    return head + text + _evidence(row) + fail


def _summary(report: dict) -> str:
    names = {"requirement": "Against the requirement", "code": "Against the code",
             "safety": "Safety net"}  # fmt: skip
    rows = []
    for key, count in report["summary"].items():
        if key == "safety" and not any(s["key"] == "safety" for s in report["sections"]):
            continue
        rows.append([names[key], str(count["passed"]), str(count["failed"]), str(count["other"]),
                     str(count.get("dropped", 0)) if key == "code" else "-"])  # fmt: skip
    return _table(["Layer", "Passed", "Failed", "Not proven", "Dropped"], rows)


def report_html(report: dict) -> str:
    """The whole report as one self-contained html text (no scripts, no outside files)."""
    h = report["header"]
    facts = [
        ("Request", f"{h['request_id']} {h['title']}"),
        ("Requirement / approach / test set version",
         f"{h['requirement_version']} / {h['approach_version']} / {h['test_set_version']}"),
        ("Build and round", f"{h['build_number']} / {h['round']}"),
        ("Time", h["time"]),
        ("AI models", ", ".join(f"{k}: {v}" for k, v in h["models"].items()) or "-"),
        ("Ran", h["ran_where"]),
        ("Label", h["label"]),
        ("File fingerprints", "; ".join(f"{p} {f}" for p, f in h["fingerprints"].items()) or "-"),
    ]  # fmt: skip
    parts = [f"<h2>Test report: {_t(h['request_id'])}, build {h['build_number']}</h2>",
             _table(["Fact", "Value"], [[_t(k), _t(v)] for k, v in facts]),
             "<h3>Summary</h3>", _summary(report)]  # fmt: skip
    for section in report["sections"]:
        parts.append(f"<h3>{_t(section['title'])}</h3>")
        parts.extend(_test(row) for row in section["rows"])
    if report["dropped_code_tests"]:
        parts.append("<h3>Dropped code tests</h3><ul>")
        parts.extend(f"<li>{_t(d)}</li>" for d in report["dropped_code_tests"])
        parts.append("</ul>")
    parts.append("<h3>The Tester's checks</h3>")
    parts.append(_table(["#", "Check", "Result", "Findings"],
                        [[str(c["number"]), _t(c["name"]), _t(c["state"]), str(c["findings"])]
                         for c in report["checks"]]))  # fmt: skip
    for f in report["findings"]:
        where = f"{f['file']}:{f['line']} " if f["file"] else ""
        said = f"{f['finding_id']} ({f['severity']}) {where}{f['message']}"
        parts.append(f"<p>{_t(said)}</p>")
    parts.append(f"<p>{_t(report['legend'])}</p>")
    return f'<div class="da-report">{"".join(parts)}</div>'


def report_document(report: dict) -> str:
    """The downloaded file: the same html inside a page that opens offline."""
    title = f"Test report {report['header']['request_id']}"
    head = f"<head><meta charset='utf-8'><title>{_t(title)}</title>"
    head += f"<style>{PRINT_CSS}</style></head>"
    return f"<!DOCTYPE html><html>{head}<body>{report_html(report)}</body></html>"


def report_shell() -> html.Div:
    """Drawn once at start-up (like the inbox shell), hidden until the URL is a report path."""
    buttons = dmc.Group(
        [dmc.Button("Print", id=REPORT_PRINT_ID, variant="light"),
         dmc.Button("Download", id=REPORT_DOWNLOAD_ID, variant="light")],
        className="da-no-print", p="md",
    )  # fmt: skip
    return html.Div(
        [dcc.Markdown(f"<style>{PRINT_CSS}</style>", dangerously_allow_html=True), buttons,
         dcc.Markdown(id=REPORT_BODY_ID, dangerously_allow_html=True, style={"padding": "16px"}),
         dcc.Download(id=REPORT_FILE_ID)],
        id=REPORT_SHELL_ID, style={"display": "none"},
    )  # fmt: skip
