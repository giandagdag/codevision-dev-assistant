"""The Build tab and the Tests tab on screen (spec section 12, demo `tabBuild`).

Presentation only (rule R12), like the other layout files: it turns what the Build flow already
decided (BuildView) into components. Nothing here judges code, runs a test or writes a file.
"""

import dash_mantine_components as dmc
from dash import dcc

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
FILES_ID = "da-build-files"
TURN_ID = "da-build-turn"
EDIT_HINT_ID = "da-build-edit-hint"
SUMMARY_ID = "da-build-summary"
TESTS_LIST_ID = "da-tests-list"
TESTS_CODE_ID = "da-tests-code"
TESTS_VERSION_ID = "da-tests-version"

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
RESULT_TEXT = {"pass": "Passed", "fail": "Failed", "error": "Error", "skipped": "Skipped", "": "-"}
RESULT_COLOUR = {"pass": "green", "fail": "red", "error": "red", "skipped": "gray", "": "gray"}


def poll_interval(view: BuildView) -> dcc.Interval:
    """Asks the page to redraw every 3 seconds while the build runs; off at every other step."""
    return dcc.Interval(id=POLL_ID, interval=POLL_MS, disabled=not view.polling)


def build_tab(view: BuildView, edit_hint: str = "") -> list:
    """The Build tab for a build that has started (any step after `start`). `edit_hint` is the
    Refine line "Edit anything, then click Re-scan." (empty when Refine is not offered)."""
    blocks: list = []
    if view.banner_text:
        blocks.append(_banner(view))
    if view.progress:
        blocks.append(_progress(view))
        blocks.append(_layer_boxes(view))
    failure = _failures(view)
    if failure is not None:
        blocks.append(failure)
    if view.state.step in ("b_done", "b_written", "b_write_stopped"):
        blocks.append(_files(view))
    if view.state.step == "b_written":
        blocks.append(_your_turn())
    if edit_hint:
        blocks.append(dmc.Text(edit_hint, size="sm", fw=600, id=EDIT_HINT_ID))
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
    report = tester_report(
        view.tester,
        view.state.step in ACT_STEPS
        and view.request_status in ACT_STATUSES
        and bool(view.tester and view.tester.layer_c_ran),
    )
    rows = [_test_row(item) for item in view.tests]
    not_run = (
        dmc.Text(TESTS_NOT_RUN, size="sm", c="orange", id="da-tests-not-run")
        if view.tests_not_run
        else None
    )
    table = dmc.Table(
        [
            dmc.TableThead(
                dmc.TableTr(
                    [dmc.TableTh(t) for t in ("Test", "Criterion", "What is expected", "Result")]
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
                dmc.Text(f"{len(view.tests)} frozen tests", fw=600, size="sm"),
                dmc.Text(view.tests_note, size="xs", c=da_styles.MUTED, id=TESTS_VERSION_ID)
                if view.tests_note
                else None,
                not_run,
                table,
                dmc.Text(TESTS_NOTE, size="xs", c=da_styles.MUTED, id="da-tests-note"),
                code,
            ],
            gap="sm",
        )
    ]


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
    lines = [
        f"Rounds used: {run.rounds_used} of {view.max_rounds}",
        f"Tests passing: {view.tests_passing or '-'}",
        f"Time taken: {minutes}:{seconds:02d}",
        *tester_lines(view),
    ]
    return dmc.Paper(
        [dmc.Text("This build", fw=600, size="sm"), *[dmc.Text(t, size="sm") for t in lines]],
        p="sm",
        withBorder=True,
        id=SUMMARY_ID,
    )


def _test_row(item: TestRow) -> dmc.TableTr:
    tag = item.tag or ("Yours" if item.yours else "")
    name = f"{item.test_id} ({tag})" if tag else item.test_id
    return dmc.TableTr(
        [
            dmc.TableTd(dmc.Text(name, size="xs", fw=600)),
            dmc.TableTd(dmc.Text(item.criterion_id, size="xs")),
            dmc.TableTd(dmc.Text(item.description, size="xs")),
            dmc.TableTd(
                dmc.Text(
                    RESULT_TEXT.get(item.result, item.result),
                    size="xs",
                    c=RESULT_COLOUR.get(item.result),
                )
            ),
        ]
    )
