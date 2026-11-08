"""What the Refine part of the screen offers at `b_written` (Phase 8 step 13a, tests 8-1/2/12).

Decisions only, no components (rule R12): the layout turns a RefineBox into buttons and a text box.

AS400 picture: the command-key line at the bottom of a 5250 screen. Which keys are lit depends on
the state of the job, and this file decides which ones.
"""

import ast
from dataclasses import dataclass, field

from agents.da_build_checks import case_ids_from_method, find_test_methods
from agents.da_refine_checks import (
    cap_message,
    criterion_marks,
    diff_records,
    refine_cap_reached,
)
from agents.da_refine_flow import (
    CHECK_KEY,
    CHECK_LABEL,
    EDIT_STATUSES,
    RESCAN_KEY,
    RESTORE_KEY,
    RESTORE_LABEL,
    EditView,
    FileDiff,
    VersionRow,
    get_edit_view,
    list_versions,
    rescan_label,
)
from agents.da_refine_lanes import get_refine_state
from agents.da_refine_picks import STEP as CONFLICT_STEP
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import read_approach_versions
from db_table_functions.db_tbl_da_audit import list_audit_events
from db_table_functions.db_tbl_da_refine import (
    read_all_records,
    read_conflicts,
    read_refines,
    read_test_sets,
)
from db_table_functions.db_tbl_da_requests import get_rulebook_for_request
from pydantic_classes.da_approach_models import ApproachVersion
from pydantic_classes.da_build_models import BuildView, TestRow
from pydantic_classes.da_refine_models import Conflict, RecordDiff, RefineRow, TestSet
from pydantic_classes.da_request_record_models import RequestRecord

REFINE_PLACEHOLDER = "Tell me what to change or fix, then press Send."
EDIT_HINT = "Edit anything, then click Re-scan."


@dataclass
class RefineBox:
    """`offered` False means no Refine controls at all (8-2). When the cap is reached the text box
    is closed and says why, but Re-scan and Check my edits still work (8-12)."""

    offered: bool = False
    text_open: bool = False
    placeholder: str = ""
    # (key, label): Re-scan runs in the browser, the others on the server.
    browser_buttons: list[tuple[str, str]] = field(default_factory=list)
    buttons: list[tuple[str, str]] = field(default_factory=list)
    hint: str = ""


def make_refine_box(
    status: str,
    step: str,
    refine_count: int,
    cap: int,
    mode: str = "picker",
    has_edits: bool = False,
) -> RefineBox:
    """Pure rule: Refine is offered only at `b_written` with READY_FOR_REVIEW or NOT_PASSING."""
    if step != "b_written" or status not in EDIT_STATUSES:
        return RefineBox()
    capped = refine_cap_reached(refine_count, cap)
    buttons = [(CHECK_KEY, CHECK_LABEL)] if has_edits else []
    buttons.append((RESTORE_KEY, RESTORE_LABEL))
    return RefineBox(
        offered=True,
        text_open=not capped,
        placeholder=cap_message(refine_count) if capped else REFINE_PLACEHOLDER,
        browser_buttons=[(RESCAN_KEY, rescan_label(mode))],
        buttons=buttons,
        hint=EDIT_HINT,
    )


def get_refine_box(settings, request_id: str, status: str, step: str, mode: str) -> RefineBox:
    """Reads the Refine count, the cap and whether re-scanned edits wait, then decides."""
    if step != "b_written" or status not in EDIT_STATUSES:
        return RefineBox()
    state = get_refine_state(settings, request_id)
    count = state.refine_count if state else 0
    cap = get_rulebook_for_request(settings.db_path, request_id).rulebook.policy
    edits = get_edit_view(settings, request_id)
    return make_refine_box(
        status, step, count, cap.refine_max_per_request, mode, has_edits=bool(edits.changed)
    )


# --- the Build tab parts (step 13d) ---

# The demo's "How your edits are protected" card, worded as built.
PROTECTION_RULES = [
    "Before every write the app checks that your files are the ones it expects. If not, it stops "
    "and says Re-scan first.",
    "A rebuild starts from the text you scanned and changes only the lines it needs.",
    "If the AI's change touches or sits next to your lines, you pick Keep mine or Take the AI's "
    "for each place. Nothing is written until you have picked.",
    "Every version is kept. You can put back a whole earlier set with Restore.",
]
LANE_WORDS = {"requirement": "requirement", "bug": "bug", "approach": "approach"}


@dataclass
class RefineBuildPanel:
    """Extra parts of the Build tab: his edits side by side, conflicts, Versions, the Refine tag."""

    tag: str = ""
    diffs: list[FileDiff] = field(default_factory=list)
    not_tested_line: str = ""
    only_planned_line: str = ""
    conflicts: list[Conflict] = field(default_factory=list)
    versions: list[VersionRow] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)


def refine_tag(rows: list[RefineRow], build_number: int) -> str:
    """Pure rule: "Refine 2: bug" for the build a Refine produced, else empty."""
    for row in reversed(rows):
        if row.build_number == build_number and row.chosen_lane:
            return f"Refine {row.refine_number}: {LANE_WORDS.get(row.chosen_lane, row.chosen_lane)}"
    return ""


def get_refine_build_panel(settings, request_id: str, build: BuildView) -> RefineBuildPanel:
    step = build.state.step
    number = build.state.build_number
    edits = get_edit_view(settings, request_id) if step == "b_written" else EditView()
    with open_db(settings.db_path) as conn:
        tag = refine_tag(read_refines(conn, request_id), number)
        conflicts = read_conflicts(conn, request_id, number) if step == CONFLICT_STEP else []
    versions = list_versions(settings, request_id) if step == "b_written" else []
    return RefineBuildPanel(
        tag=tag,
        diffs=edits.diffs,
        not_tested_line=edits.not_tested_line,
        only_planned_line=edits.only_planned_line if edits.diffs else "",
        conflicts=conflicts,
        versions=versions,
        rules=PROTECTION_RULES if step in ("b_written", CONFLICT_STEP) else [],
    )


# --- tags on the Tests tab (step 13c) ---


def _method_docs(text: str) -> dict[str, str]:
    """case id -> first line of the test method's docstring."""
    docs: dict[str, str] = {}
    try:
        methods = find_test_methods(ast.parse(text))
    except SyntaxError:
        return docs
    for name, method in methods.items():
        ids = case_ids_from_method(name)
        if ids:
            docs[ids[0]] = (ast.get_docstring(method) or "").split("\n")[0]
    return docs


def _row_tag(row: TestRow, new_ids: set[str]) -> str:
    if row.yours:
        return "Yours"
    return "New" if row.test_id in new_ids else ""


def tag_tests(
    build: BuildView, new_ids: set[str], yours_ids: set[str], test_sets: list[TestSet]
) -> BuildView:
    """Pure rule: New (requirement lane), Bug (repro test) or Yours on every test, repro and
    own tests that live only in the appended test sets get a row too, and a line says which test
    set version and approach version the list belongs to."""
    rows = [row.model_copy(update={"tag": _row_tag(row, new_ids)}) for row in build.tests]
    if not test_sets:
        return build.model_copy(update={"tests": rows})
    latest = test_sets[-1]
    docs = _method_docs(latest.text)
    results = {row.test_id: row.result for row in build.tests}
    seen = {row.test_id for row in rows}
    for item in test_sets:
        for case_id in item.added_case_ids:
            if case_id in seen:
                continue
            seen.add(case_id)
            rows.append(
                TestRow(
                    test_id=case_id,
                    criterion_id="",
                    tag="Yours" if case_id in yours_ids else "Bug",
                    description=docs.get(case_id, ""),
                    result=results.get(case_id, ""),
                )
            )
    note = f"Test set version {latest.test_set_version}, approach version {latest.approach_version}"
    return build.model_copy(update={"tests": rows, "tests_note": note})


def get_tagged_build(settings, request_id: str, build: BuildView, plan) -> BuildView:
    """Reads the test sets and the audit trail, then tags. `plan` is the saved test plan or None."""
    new_ids = {case.test_id for case in plan.cases if case.new} if plan else set()
    with open_db(settings.db_path) as conn:
        test_sets = read_test_sets(conn, request_id)
    events = list_audit_events(settings.db_path, request_id) if test_sets else []
    yours = {e.details.get("case") for e in events if e.event_type == "own_test_added"}
    return tag_tests(build, new_ids, yours, test_sets)


# --- version history for the Summary and Approach tabs (step 13b) ---


@dataclass
class VersionHistory:
    """Record diffs and the approach versions. Empty when nothing was refined."""

    diffs: list[RecordDiff] = field(default_factory=list)
    marks: dict[str, list[str]] = field(default_factory=dict)
    # (approach version, source, record version)
    approaches: list[tuple[int, str, int]] = field(default_factory=list)


def make_history(records: list[RequestRecord], approaches: list[ApproachVersion]) -> VersionHistory:
    """Pure rule: one diff for each step from a record version to the next."""
    diffs = [diff_records(old, new) for old, new in zip(records, records[1:], strict=False)]
    listed = [(a.approach_version, a.source, a.record_version) for a in approaches]
    return VersionHistory(
        diffs=diffs,
        marks=criterion_marks(diffs),
        approaches=listed,
    )


def get_history(settings, request_id: str) -> VersionHistory:
    with open_db(settings.db_path) as conn:
        return make_history(
            read_all_records(conn, request_id), read_approach_versions(conn, request_id)
        )
