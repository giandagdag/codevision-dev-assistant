"""The Tester's report on the Tests tab (spec section 9), and the Layer C box helpers.

Presentation only (rule R12): it draws what da_tester_flow decided. Buttons carry a pattern id,
`accept:F-2`, `reopen:F-2` or `dispute:F-1`; the page callback turns that back into one flow call.
Like the review sheet that comes back from the second programmer: findings on top, his comments
beside them, and a line for your written answer.
"""

import dash_mantine_components as dmc

from pydantic_classes.da_tester_models import (
    ACCEPT_MAX_CHARS,
    ACCEPT_MIN_CHARS,
    SEVERITY_TEXT,
    FindingRow,
    TesterView,
)
from styles import da_styles

FINDING_ACT_TYPE = "da-finding-act"
FINDING_REASON_TYPE = "da-finding-reason"
REPORT_ID = "da-tester-report"
CHECKS_ID = "da-tester-checks"
FINDINGS_ID = "da-tester-findings"
DROPPED_ID = "da-tester-dropped"
EARLIER_ID = "da-tester-earlier"

REPORT_NOTE = "This report stays in the app. Nothing from it is written to your folder."
FIX_IT_TEXT = "Fix it"
LABEL_COLOURS = {
    "Ready for your review": "green",
    "Ready with warnings": "yellow",
    "Not passing": "red",
    "Unable to assess": "gray",
}
SEVERITY_COLOUR = {"must_fix": "red", "should_fix": "orange", "fyi": "gray"}
CHECK_STATE_TEXT = {
    "passed": "Passed",
    "failed": "Failed",
    "warning": "Warning",
    "not_run": "Not run",
}
ID_STYLE = {"whiteSpace": "nowrap"}  # F7: F-12 never breaks across two lines
WHERE_STYLE = {"overflowWrap": "anywhere"}  # F7: a long path wraps instead of widening the table
CHECK_STATE_COLOUR = {"passed": "green", "failed": "red", "warning": "yellow", "not_run": "gray"}


def layer_c_state(view) -> tuple[str, str]:
    """(text, colour) of the Layer C box on the Build tab (spec section 10)."""
    report = view.tester
    if view.state.step == "b_tester_review":
        return "Reviewing", "blue"
    if report is None or report.review is None or not report.layer_c_ran:
        return "Waiting", "gray"
    if report.label == "Unable to assess":
        return "Unable to assess", "gray"
    kept = [row.finding for row in report.rows]
    if any(item.severity == "must_fix" for item in kept):
        return "Must fix found", "red"
    open_should = any(
        r.finding.severity == "should_fix" and r.state != "accepted" for r in report.rows
    )
    if open_should or report.review.zone_warnings:
        return "Warnings", "yellow"
    return "Passed", "green"


def tester_lines(view) -> list[str]:
    """The extra lines of the "This build" box: findings by severity, and the model used."""
    report = view.tester
    if report is None or report.review is None:
        return []
    counts = {
        key: sum(1 for r in report.rows if r.finding.severity == key) for key in SEVERITY_TEXT
    }
    lines = [
        "Tester findings: "
        + ", ".join(
            f"{counts[key]} {SEVERITY_TEXT[key]}" for key in ("must_fix", "should_fix", "fyi")
        )
    ]
    if report.review.model:
        lines.append(f"Tester model: {report.review.model}")
    return lines


def tester_report(report: TesterView | None, can_act: bool, can_fix: bool = False) -> list:
    """The report blocks for the top of the Tests tab. Empty before any review. `can_fix`: Fix it
    is live (Phase 8: only at `b_written`, when the code is in his folder)."""
    if report is None or report.review is None:
        return []
    review = report.review
    blocks: list = [
        dmc.Alert(
            [
                dmc.Text(report.label or "Tester review", fw=600, size="sm"),
                dmc.Text(report.summary, size="sm"),
            ],
            color=LABEL_COLOURS.get(report.label, "blue"),
            variant="light",
            id=REPORT_ID,
        )
    ]
    if not report.layer_c_ran:
        blocks.append(
            dmc.Text(
                "Layer C did not run in the last round: the tests did not pass.",
                size="sm",
                c="orange",
            )
        )
    blocks.append(_checks_table(report))
    if report.rows:
        blocks.append(_findings_table(report.rows, can_act, can_fix))
    for warning in review.zone_warnings:
        blocks.append(dmc.Text(warning, size="sm", c="orange"))
    blocks += _dropped(report)
    blocks.append(
        dmc.Text(
            f"Reviewed by {review.model or 'the Tester'} in {review.calls} call(s).",
            size="xs",
            c=da_styles.MUTED,
        )
    )
    blocks += _earlier(report)
    blocks.append(dmc.Text(REPORT_NOTE, size="xs", c=da_styles.MUTED, id="da-tester-note"))
    return blocks


# --- pieces ---


def _checks_table(report: TesterView) -> dmc.Table:
    head = dmc.TableThead(dmc.TableTr([dmc.TableTh(t) for t in ("#", "Check", "Result")]))
    body = []
    for check in report.review.checks:
        text = CHECK_STATE_TEXT[check.state]
        if check.state in ("failed", "warning") and check.findings:
            text += f" ({check.findings})"
        body.append(
            dmc.TableTr(
                [
                    dmc.TableTd(dmc.Text(str(check.number), size="xs")),
                    dmc.TableTd(dmc.Text(check.name, size="xs")),
                    dmc.TableTd(dmc.Text(text, size="xs", c=CHECK_STATE_COLOUR[check.state])),
                ]
            )
        )
    return dmc.Table([head, dmc.TableTbody(body)], id=CHECKS_ID, withTableBorder=True)


def _findings_table(rows: list[FindingRow], can_act: bool, can_fix: bool) -> dmc.Table:
    heads = ("ID", "Severity", "Where", "Message", "Action")
    head = dmc.TableThead(dmc.TableTr([dmc.TableTh(t) for t in heads]))
    body = [_finding_row(row, can_act, can_fix) for row in rows]
    return dmc.Table([head, dmc.TableTbody(body)], id=FINDINGS_ID, withTableBorder=True)


def _finding_row(row: FindingRow, can_act: bool, can_fix: bool) -> dmc.TableTr:
    item = row.finding
    where = f"{item.file}:{item.line}" if item.file else "-"
    # F7: the check number and the cited rule sit under the message as one dimmed line.
    detail = f"Check {item.check} · Cites: {item.cites or '-'}"
    message = [dmc.Text(item.message, size="xs")]
    if item.quote:
        message.append(dmc.Text(item.quote, size="xs", ff="monospace", c=da_styles.MUTED))
    message.append(dmc.Text(detail, size="xs", c=da_styles.MUTED))
    return dmc.TableTr(
        [
            dmc.TableTd(dmc.Text(item.finding_id, size="xs", fw=600, style=ID_STYLE)),
            dmc.TableTd(
                dmc.Text(SEVERITY_TEXT[item.severity], size="xs", c=SEVERITY_COLOUR[item.severity])
            ),
            dmc.TableTd(dmc.Text(where, size="xs", ff="monospace", style=WHERE_STYLE)),
            dmc.TableTd(dmc.Stack(message, gap=2)),
            dmc.TableTd(_actions(row, can_act, can_fix)),
        ]
    )


def _actions(row: FindingRow, can_act: bool, can_fix: bool):
    item = row.finding
    if item.severity == "fyi":
        return dmc.Text("-", size="xs")
    if item.severity == "must_fix":
        if row.state == "disputed":
            return dmc.Text(f"Disputed: {row.reason}", size="xs")
        return _with_reason(item.finding_id, "dispute", "Dispute", can_act)
    if row.state == "accepted":
        return dmc.Stack(
            [
                dmc.Text(f"Accepted: {row.reason}", size="xs"),
                _button(f"reopen:{item.finding_id}", "Reopen", can_act),
            ],
            gap=4,
        )
    return dmc.Stack(
        [
            _with_reason(item.finding_id, "accept", "Accept, with reason", can_act),
            _button(f"fixit:{item.finding_id}", FIX_IT_TEXT, can_fix, variant="default"),
        ],
        gap=4,
    )


def _with_reason(finding_id: str, action: str, label: str, can_act: bool) -> dmc.Stack:
    return dmc.Stack(
        [
            dmc.Textarea(
                id={"type": FINDING_REASON_TYPE, "index": finding_id},
                placeholder=f"Reason ({ACCEPT_MIN_CHARS} to {ACCEPT_MAX_CHARS} characters)",
                autosize=True,
                minRows=1,
                maxRows=4,
                disabled=not can_act,
                inputProps={"maxLength": ACCEPT_MAX_CHARS},
            ),
            _button(f"{action}:{finding_id}", label, can_act),
        ],
        gap=4,
    )


def _button(index: str, label: str, can_act: bool, variant: str = "filled") -> dmc.Button:
    return dmc.Button(
        label,
        id={"type": FINDING_ACT_TYPE, "index": index},
        size="compact-xs",
        variant=variant,
        disabled=not can_act,
    )


def _dropped(report: TesterView) -> list:
    if not report.dropped:
        return []
    count = len(report.dropped)
    lines = [
        dmc.Text(
            f"{count} Tester finding{'s were' if count != 1 else ' was'} dropped because "
            "their evidence did not check out.",
            size="sm",
            id=DROPPED_ID,
        )
    ]
    items = [
        dmc.Text(
            f"{item.file or '-'}:{item.line} {item.cites or '-'}: {item.message} "
            f"(dropped: {item.reject_reason})",
            size="xs",
            c=da_styles.MUTED,
        )
        for item in report.dropped
    ]
    lines.append(
        dmc.Accordion(
            dmc.AccordionItem(
                [dmc.AccordionControl("Show dropped"), dmc.AccordionPanel(dmc.Stack(items, gap=2))],
                value="dropped",
            ),
            chevronPosition="left",
        )
    )
    return lines


def _earlier(report: TesterView) -> list:
    if not report.earlier:
        return []
    items = []
    for review in report.earlier:
        counts = {
            key: sum(1 for f in review.findings if f.kept and f.severity == key)
            for key in SEVERITY_TEXT
        }
        items.append(
            dmc.Text(
                f"Review {review.review_number} (round {review.round}): "
                f"{counts['must_fix']} Must fix, {counts['should_fix']} Should fix, "
                f"{counts['fyi']} FYI. {review.label}",
                size="xs",
            )
        )
    return [
        dmc.Accordion(
            dmc.AccordionItem(
                [
                    dmc.AccordionControl("Earlier reviews"),
                    dmc.AccordionPanel(dmc.Stack(items, gap=2)),
                ],
                value="earlier",
            ),
            chevronPosition="left",
            id=EARLIER_ID,
        )
    ]
