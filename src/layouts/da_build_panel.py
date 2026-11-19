"""The Build tab and the Tests tab on screen (spec section 12, demo `tabBuild`).

Presentation only (rule R12), like the other layout files: it turns what the Build flow already
decided (BuildView) into components. Nothing here judges code, runs a test or writes a file.
"""

import dash_mantine_components as dmc
from dash import dcc, html

from agents.da_check_words import CHECK_BOX_TITLE, CHECK_KIND
from agents.da_load_errors import reason_lines
from layouts.da_test_report_page import NO_REPORT_TEXT, report_link
from layouts.da_tester_panel import layer_c_state, tester_lines, tester_report
from pydantic_classes.da_build_models import (
    BuildView,
    LayerAResult,
    LayerBResult,
    ProgressLine,
    RoundRecord,
    TestRow,
)
from styles import da_styles

# Ids a test (and the page callbacks) can find.
POLL_ID = "da-build-poll"
POLL_MS = 3000
BANNER_ID = "da-build-banner"
PROGRESS_ID = "da-build-progress"
LAYERS_ID = "da-build-layers"
FAILURES_ID = "da-build-failures"
REASON_ID = "da-build-reason"
FILES_ID = "da-build-files"
TURN_ID = "da-build-turn"
EDIT_HINT_ID = "da-build-edit-hint"
SUMMARY_ID = "da-build-summary"
TESTS_LIST_ID = "da-tests-list"
TESTS_CODE_ID = "da-tests-code"
TESTS_VERSION_ID = "da-tests-version"
REPORT_LINE_ID = "da-tests-report-line"
REPORT_LINK_ID = "da-tests-report-link"
NO_REPORT_LINE = NO_REPORT_TEXT
ADD_CASE_ID = "da-add-case"
ADD_CASE_TYPE = "da-add-case-go"  # the button
ADD_CASE_FIELD_TYPE = "da-add-case-field"  # the criterion picker and the text box
ADD_CASE_LABEL = "Add a test case"

TESTS_NOT_RUN = "Not run: the code checks (Layer A) failed first. See the Build tab."
TESTS_NOTE = "These tests run on the CodeVision server. They are not copied to your folder."
TURN_TITLE = "Your turn"
TURN_LINES = (
    "Try it yourself: start CodeVision on your laptop and test the change by hand.",
    "Tell me if a requirement is missing.",
)
BANNER_COLOURS = {
    "blue": "blue",
    "red": "red",
    "green": "green",
    "orange": "orange",
    "yellow": "yellow",
    "gray": "gray",
}
# The Tester report can be acted on only on a finished build that waits for his review.
ACT_STEPS = ("b_done", "b_written", "b_write_stopped")
ACT_STATUSES = ("READY_FOR_REVIEW", "NOT_PASSING")
STATE_ICON = {"done": "✅", "running": "⏳", "failed": "❌", "pending": "⬜"}
RESULT_TEXT = {
    "pass": "Passed",
    "fail": "Failed",
    "error": "Error",
    "skipped": "Skipped",
    "expected_failure": "Expected to fail",
    "unexpected_success": "Passed, but expected to fail",
    "not_proven": "Not proven: no result recorded",
    "not_run": "Did not run",
    "": "-",
}
RESULT_COLOUR = {
    "pass": "green",
    "fail": "red",
    "error": "red",
    "skipped": "gray",
    "expected_failure": "gray",
    "unexpected_success": "red",
    "not_proven": "orange",
    "not_run": "orange",
    "": "gray",
}


def poll_interval(view: BuildView) -> dcc.Interval:
    """Asks the page to check the build every 3 seconds, whatever the step. Always drawn on: the
    browser can keep a stale `disabled` value from an earlier redraw (bug B6), so the callback
    (`poll_build`) decides whether to redraw, not this flag. `view` is kept for the callers."""
    return dcc.Interval(id=POLL_ID, interval=POLL_MS, disabled=False)


def build_tab(view: BuildView, edit_hint: str = "", refine_blocks: list | None = None) -> list:
    """The Build tab for a build that has started (any step after `start`). `edit_hint` is the
    Refine line "Edit anything, then click Re-scan." (empty when Refine is not offered)."""
    blocks: list = []
    if view.banner_text:
        blocks.append(_banner(view))
    if view.progress:
        blocks.append(_progress(view))
        blocks.append(_layer_boxes(view))
        blocks.append(reason_block(view))  # Fix NP: why Layer B is not clean (None when it is)
    failure = _failures(view)
    if failure is not None:
        blocks.append(failure)
    if view.state.step in ("b_done", "b_written", "b_write_stopped"):
        blocks.append(_files(view))
    if view.state.step == "b_written":
        blocks.append(_your_turn())
    if edit_hint:
        blocks.append(dmc.Text(edit_hint, size="sm", fw=600, id=EDIT_HINT_ID))
    blocks.extend(refine_blocks or [])
    if view.run is not None and view.run.ended_at is not None:
        blocks.append(_this_build(view))
    return [dmc.Stack(blocks, gap="sm")]


def tests_tab(view: BuildView | None) -> list:
    """The Tests tab: the only place the tests live (spec section 12)."""
    if view is None or not view.tests:
        return [
            dmc.Text(
                "The tests are written when the first build starts.",
                size="sm",
                c=da_styles.MUTED,
                id=TESTS_LIST_ID,
            )
        ]
    can_act = (
        view.state.step in ACT_STEPS
        and view.request_status in ACT_STATUSES
        and bool(view.tester and view.tester.layer_c_ran)
    )
    # Fix it and Add a test case work on the code in his folder: only at b_written (Phase 8).
    at_written = view.state.step == "b_written" and view.request_status in ACT_STATUSES
    report = tester_report(view.tester, can_act, can_act and at_written)
    rows = [_group_row("Requirement tests"), *[_test_row(item) for item in view.tests]]
    if view.code_tests:
        rows += [_group_row("Code tests"), *[_test_row(item) for item in view.code_tests]]
    not_run = (
        dmc.Text(TESTS_NOT_RUN, size="sm", c="orange", id="da-tests-not-run")
        if view.tests_not_run
        else None
    )
    table = dmc.Table(
        [
            dmc.TableThead(
                dmc.TableTr(
                    [
                        dmc.TableTh(t)
                        for t in ("Test", "Criterion", "What is expected", "Result", "Evidence")
                    ]
                )
            ),
            dmc.TableTbody(rows),
        ],
        id=TESTS_LIST_ID,
        withTableBorder=True,
    )
    code = dmc.Accordion(
        dmc.AccordionItem(
            [
                dmc.AccordionControl("View test code"),
                dmc.AccordionPanel(
                    dmc.Code(view.test_code, block=True, id=TESTS_CODE_ID),
                ),
            ],
            value="code",
        ),
        chevronPosition="left",
    )
    return [
        dmc.Stack(
            [
                *report,
                reason_block(view),
                _report_block(view),
                dmc.Text(f"{len(view.tests)} frozen tests", fw=600, size="sm"),
                dmc.Text(view.tests_note, size="xs", c=da_styles.MUTED, id=TESTS_VERSION_ID)
                if view.tests_note
                else None,
                not_run,
                table,
                dmc.Text(TESTS_NOTE, size="xs", c=da_styles.MUTED, id="da-tests-note"),
                code,
                add_case_form(view) if at_written else None,
            ],
            gap="sm",
        )
    ]


def add_case_form(view: BuildView) -> dmc.Stack:
    """Add a test case (spec section 11): pick a criterion, type the case in plain words. The
    ids are pattern ids, so the page has none of them on other screens."""
    criteria = sorted({row.criterion_id for row in view.tests})
    return dmc.Stack(
        [
            dmc.Text(ADD_CASE_LABEL, fw=600, size="sm"),
            dmc.Select(
                id={"type": ADD_CASE_FIELD_TYPE, "index": "criterion"},
                data=criteria,
                value=criteria[0] if criteria else None,
                placeholder="Pick the acceptance criterion",
                allowDeselect=False,
            ),
            dmc.Textarea(
                id={"type": ADD_CASE_FIELD_TYPE, "index": "text"},
                placeholder="Describe the case in plain words",
                autosize=True,
                minRows=2,
                maxRows=5,
                inputProps={"maxLength": 4000},
            ),
            dmc.Button(
                ADD_CASE_LABEL,
                id={"type": ADD_CASE_TYPE, "index": "go"},
                size="compact-xs",
                variant="default",
            ),
        ],
        gap="xs",
        id=ADD_CASE_ID,
    )


# --- pieces ---


def _banner(view: BuildView) -> dmc.Alert:
    lines = view.banner_text.split("\n")
    return dmc.Alert(
        [dmc.Text(line, size="sm") for line in lines],
        color=BANNER_COLOURS.get(view.banner_kind, "blue"),
        variant="light",
        id=BANNER_ID,
    )


def _progress(view: BuildView) -> dmc.Paper:
    items = [
        dmc.Group(
            [
                dmc.Text(STATE_ICON.get(line.state, "⬜"), size="sm"),
                dmc.Text(line.text, size="sm", style={"flex": 1}),
                dmc.Text(_elapsed(line), size="xs", c=da_styles.MUTED),
            ],
            gap="xs",
            wrap="nowrap",
        )
        for line in view.progress
    ]
    return dmc.Paper(dmc.Stack(items, gap=4), p="sm", withBorder=True, id=PROGRESS_ID)


def _elapsed(line: ProgressLine) -> str:
    if line.started_at and line.ended_at:
        seconds = max(0, int((line.ended_at - line.started_at).total_seconds()))
        return f"{seconds // 60}:{seconds % 60:02d}"
    return ""


def _layer_boxes(view: BuildView) -> dmc.SimpleGrid:
    last = view.rounds[-1] if view.rounds else None
    return dmc.SimpleGrid(
        [
            _layer_box("Does it run?", *_layer_a_state(last.layer_a if last else None)),
            _layer_box("Does it behave?", *_layer_b_state(last.layer_b if last else None)),
            _layer_c_box(view),
        ],
        cols=3,
        id=LAYERS_ID,
    )


def _layer_c_box(view: BuildView) -> dmc.Paper:
    text, colour = layer_c_state(view)
    box = _layer_box("Matches the agreement?", text, colour)
    if view.tester is not None and view.tester.review is not None:
        box.children.append(dmc.Text("See the Tester report on the Tests tab.", size="xs"))
    return box


def _layer_a_state(result: LayerAResult | None) -> tuple[str, str]:
    if result is None:
        return "Waiting", "gray"
    if result.ok:
        return "Passed", "green"
    return f"{len(result.problems)} problem(s)", "red"


def _layer_b_state(result: LayerBResult | None) -> tuple[str, str]:
    if result is None:
        return "Waiting", "gray"
    if result.timed_out:
        return "Timed out", "red"
    text = f"{result.passed} of {len(result.tests)} passed"
    return text, "green" if result.ok else "red"


def reason_block(view: BuildView) -> dmc.Paper | None:
    """Fix NP (N3): the message and the end of the trace of a load error or a Not proven row,
    paths already shown as <sandbox>. Drawn again here so an older saved round is hidden too."""
    last = view.rounds[-1] if view.rounds else None
    lines = reason_lines(last.layer_b if last else None)
    if not lines:
        return None
    return dmc.Paper(
        dmc.Stack(
            [dmc.Text(lines[0], size="sm", c="orange")]
            + [dmc.Text(line, size="xs", ff="monospace") for line in lines[1:]],
            gap=2,
        ),
        p="sm",
        withBorder=True,
        id=REASON_ID,
    )


def _layer_box(title: str, text: str, colour: str) -> dmc.Paper:
    return dmc.Paper(
        [dmc.Text(title, size="xs", c=da_styles.MUTED), dmc.Text(text, fw=600, c=colour)],
        p="sm",
        withBorder=True,
    )


def _failures(view: BuildView) -> dmc.Paper | None:
    """The failure report of the newest failed round (demo `r1`), while there is one to show."""
    if view.state.step not in ("b_round_failed", "b_running", "b_done", "b_written"):
        return None
    last = view.rounds[-1] if view.rounds else None
    if last is None or last.failure_report is None:
        return None
    report = last.failure_report
    lines: list = []
    if report.timed_out:
        lines.append(
            dmc.Text(
                f"Timed out. The test running was {report.running_test or 'unknown'}.",
                size="sm",
                c="red",
            )
        )
    lines += [
        dmc.Text(f"{problem.path}: {problem.text}", size="xs", ff="monospace")
        for problem in report.layer_a
    ]
    if report.items:
        lines.append(_failure_table(last))
    return dmc.Paper(dmc.Stack(lines, gap="xs"), p="sm", withBorder=True, id=FAILURES_ID)


def _failure_table(record: RoundRecord) -> dmc.Table:
    head = dmc.TableThead(
        dmc.TableTr([dmc.TableTh(t) for t in ("Test", "Criterion", "Expected", "What happened")])
    )
    body = []
    for item in record.failure_report.items:
        name = f"{item.test_id} (Yours)" if item.yours else item.test_id
        body.append(
            dmc.TableTr(
                [
                    dmc.TableTd(dmc.Text(name, size="xs", fw=600)),
                    dmc.TableTd(dmc.Text(item.criterion_id, size="xs")),
                    dmc.TableTd(dmc.Text(item.expected, size="xs")),
                    dmc.TableTd(dmc.Text(item.message, size="xs", c="red")),
                ]
            )
        )
    return dmc.Table([head, dmc.TableTbody(body)], withTableBorder=True)


def _files(view: BuildView) -> dmc.Table:
    head = dmc.TableThead(dmc.TableTr([dmc.TableTh(t) for t in ("File", "Action", "Status")]))
    body = [
        dmc.TableTr(
            [
                dmc.TableTd(dmc.Text(row.path, size="xs", ff="monospace")),
                dmc.TableTd(dmc.Text(row.action, size="xs")),
                dmc.TableTd(dmc.Text(row.status, size="xs")),
            ]
        )
        for row in view.rows
    ]
    return dmc.Table([head, dmc.TableTbody(body)], id=FILES_ID, withTableBorder=True)


def _your_turn() -> dmc.Paper:
    return dmc.Paper(
        [
            dmc.Text(TURN_TITLE, fw=600, size="sm"),
            *[dmc.Text(line, size="sm") for line in TURN_LINES],
        ],
        p="sm",
        withBorder=True,
        id=TURN_ID,
    )


def _this_build(view: BuildView) -> dmc.Paper:
    run = view.run
    minutes, seconds = divmod(view.seconds_taken, 60)
    check = run.kind == CHECK_KIND  # F6: a test run has no rounds line
    lines = [
        *([] if check else [f"Rounds used: {run.rounds_used} of {view.max_rounds}"]),
        f"Tests passing: {view.tests_passing or '-'}",
        f"Time taken: {minutes}:{seconds:02d}",
        *tester_lines(view),
    ]
    title = CHECK_BOX_TITLE if check else "This build"
    return dmc.Paper(
        [dmc.Text(title, fw=600, size="sm"), *[dmc.Text(t, size="sm") for t in lines]],
        p="sm",
        withBorder=True,
        id=SUMMARY_ID,
    )


def _report_block(view: BuildView):
    """The summary line and the Open report link, or the sentence for a build with no report."""
    if not view.has_report:
        if not any(item.layer_b is not None for item in view.rounds):
            return None  # the tests have not run yet: nothing to report
        return dmc.Text(NO_REPORT_LINE, size="sm", c=da_styles.MUTED, id=REPORT_LINE_ID)
    link = dcc.Link(
        "Open report", href=report_link(view.state.request_id, view.state.build_number),
        target="_blank", id=REPORT_LINK_ID,
    )  # fmt: skip
    return dmc.Group([dmc.Text(view.report_summary, size="sm", id=REPORT_LINE_ID), link], gap="sm")


def _group_row(title: str) -> dmc.TableTr:
    cells = [dmc.TableTd(dmc.Text(title, size="xs", fw=700))]
    return dmc.TableTr(cells + [dmc.TableTd("") for _ in range(4)])


def _evidence_cell(item: TestRow):
    """'3 checks', click to open the lines. Nothing recorded: say so (an old test)."""
    if not item.evidence:
        return dmc.Text("Evidence not recorded", size="xs", c=da_styles.MUTED)
    lines = [
        html.Div(f"{e.label}: input {e.given}, expected {e.expected}, actual {e.actual}"
                 f" ({'match' if e.match else 'NO match'})", style={"fontSize": "11px"})
        for e in item.evidence
    ]  # fmt: skip
    return html.Details([html.Summary(f"{len(item.evidence)} checks"), *lines])


def _test_row(item: TestRow) -> dmc.TableTr:
    tag = item.tag or ("Yours" if item.yours else "")
    name = f"{item.test_id} ({tag})" if tag else item.test_id
    return dmc.TableTr(
        [
            dmc.TableTd(dmc.Text(name, size="xs", fw=600)),
            dmc.TableTd(dmc.Text(item.criterion_id, size="xs")),
            dmc.TableTd(dmc.Text(item.description, size="xs")),
            dmc.TableTd(_result_cell(item)),
            dmc.TableTd(_evidence_cell(item)),
        ]
    )


def _result_cell(item: TestRow) -> dmc.Text:
    if item.pending:
        return dmc.Text(item.pending, size="xs", c="orange")
    return dmc.Text(
        RESULT_TEXT.get(item.result, item.result), size="xs", c=RESULT_COLOUR.get(item.result)
    )
