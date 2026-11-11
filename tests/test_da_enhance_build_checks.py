"""Phase 9 step 6: A8 scope, A9 locked signature, the safety-net failure wording and the Layer C NC
line (tests 9-39, 9-40, 9-41, 9-42 labels, 9-43; pure parts)."""

from agents.da_build_checks import build_failure_report, report_for_developer
from agents.da_enhance_build_checks import (
    failing_safety_cases,
    safety_notes,
    scope_problems,
    signature_problems,
)
from agents.da_tester_review import NC_NOT_COVERED_TEXT, check_nc_items, compute_label
from pydantic_classes.da_build_models import (
    FileEdit,
    LayerAResult,
    LayerBResult,
    TestOutcome,
)
from pydantic_classes.da_enhance_models import ImpactRow, SafetyCase, SafetyNet
from pydantic_classes.da_request_record_models import MustNotChange, RequestRecord

SOURCE = '''import os


def format_expiry(day, style):
    """Format a day."""
    return str(day) + style


def parse_date(text):
    return text.strip()


class Report:
    def title(self):
        return "t"

    def total(self, rows):
        return len(rows)
'''


def edit(find, replace="x"):
    return FileEdit(find=find, replace=replace)


# --- 9-39: A8 scope ---


def test_9_39_an_edit_inside_an_in_scope_function_passes():
    edits = [edit("return str(day) + style", "return style + str(day)")]

    assert scope_problems("src/a.py", SOURCE, edits, ["format_expiry"]) == []


def test_9_39_an_edit_outside_names_the_symbol():
    edits = [edit("return text.strip()", "return text")]

    problems = scope_problems("src/a.py", SOURCE, edits, ["format_expiry"])

    assert [(p.code, p.path) for p in problems] == [("A8", "src/a.py")]
    assert problems[0].text == "Edit block 1 changes `parse_date`, which is not in scope."


def test_9_39_module_level_code_is_not_in_scope():
    problems = scope_problems("src/a.py", SOURCE, [edit("import os", "import sys")], ["parse_date"])

    assert "module-level code" in problems[0].text


def test_9_39_a_class_in_scope_covers_its_methods_and_a_method_covers_only_itself():
    edits = [edit('return "t"', 'return "u"')]

    assert scope_problems("src/a.py", SOURCE, edits, ["Report"]) == []
    assert scope_problems("src/a.py", SOURCE, edits, ["Report.title"]) == []
    problems = scope_problems("src/a.py", SOURCE, edits, ["Report.total"])
    assert "`Report.title`" in problems[0].text


def test_9_39_insert_after_an_in_scope_function_is_allowed():
    last_line = "    return str(day) + style\n"
    added = last_line + "\n\ndef helper():\n    return 1\n"

    assert scope_problems("src/a.py", SOURCE, [edit(last_line, added)], ["format_expiry"]) == []
    # The blank lines right below the function are the insert-after spot too.
    gap = "style\n\n\ndef parse_date"
    assert scope_problems("src/a.py", SOURCE, [edit(gap, gap)], ["format_expiry"]) != []


def test_9_39_each_block_is_checked_on_the_text_after_the_blocks_before_it():
    edits = [
        edit("return str(day) + style", "total = 1\n    return str(total) + style"),
        edit("total = 1", "total = 2"),
    ]

    assert scope_problems("src/a.py", SOURCE, edits, ["format_expiry"]) == []


def test_9_39_a_block_that_does_not_match_is_left_to_the_edit_step():
    assert scope_problems("src/a.py", SOURCE, [edit("nothing like this")], ["format_expiry"]) == []


# --- 9-40: A9 locked signature ---


def impact_row(caller="src/caller.py", function="format_expiry", kind="direct"):
    return ImpactRow(
        caller_path=caller,
        caller_function="run",
        line=3,
        function_in_scope=function,
        kind=kind,
    )


def test_9_40_a_changed_argument_list_with_a_caller_outside_the_plan_fails():
    new_text = SOURCE.replace("(day, style)", "(day, style, extra)")

    problems = signature_problems("src/a.py", SOURCE, new_text, [impact_row()], ["src/a.py"])

    assert [p.code for p in problems] == ["A9"]
    assert problems[0].text == (
        "`format_expiry` is called by `src/caller.py`; its arguments cannot change "
        "unless that file is in the plan."
    )


def test_9_40_with_the_callers_file_in_the_plan_it_passes():
    new_text = SOURCE.replace("(day, style)", "(day, style, extra)")

    planned = ["src/a.py", "src/caller.py"]
    assert signature_problems("src/a.py", SOURCE, new_text, [impact_row()], planned) == []


def test_9_40_a_possible_caller_does_not_lock_and_a_body_change_does_not_count():
    new_text = SOURCE.replace("(day, style)", "(day, style, extra)")
    possible = [impact_row(kind="possible")]
    assert signature_problems("src/a.py", SOURCE, new_text, possible, ["src/a.py"]) == []

    body_only = SOURCE.replace("str(day) + style", "style")
    assert signature_problems("src/a.py", SOURCE, body_only, [impact_row()], ["src/a.py"]) == []


def test_9_40_a_removed_or_renamed_function_counts_as_changed():
    renamed = SOURCE.replace("def format_expiry", "def format_day")

    problems = signature_problems("src/a.py", SOURCE, renamed, [impact_row()], ["src/a.py"])

    assert [p.code for p in problems] == ["A9"]


def test_9_40_a_method_is_locked_by_its_class_dot_name():
    rows = [impact_row(function="Report.total")]
    new_text = SOURCE.replace("def total(self, rows)", "def total(self, rows, more)")

    problems = signature_problems("src/a.py", SOURCE, new_text, rows, ["src/a.py"])

    assert "`Report.total`" in problems[0].text


# --- 9-41: the failure report ---


def safety_net():
    return SafetyNet(
        cases=[
            SafetyCase(
                id="S-4",
                today_behaviour="Rows are sorted by expiry date.",
                function="format_expiry",
                nc_ids=["NC-2"],
            ),
            SafetyCase(id="S-5", today_behaviour="Empty gives nothing.", function="parse_date"),
        ]
    )


def test_9_41_the_report_names_the_case_today_s_behaviour_and_the_nc_id():
    result = LayerBResult(
        tests=[
            TestOutcome(name="test_s4_sorted", result="fail", message="'b' != 'a'"),
            TestOutcome(name="test_s5_empty", result="error", message="boom"),
            TestOutcome(name="test_s6_ok", result="pass"),
        ]
    )

    report = build_failure_report(
        LayerAResult(), result, [], "", ["src/a.py"], safety_notes(safety_net())
    )
    text = report_for_developer(report)

    assert (
        "Safety-net test S-4 (today: Rows are sorted by expiry date) now fails. "
        "You said this must not change (NC-2). Got: 'b' != 'a'"
    ) in text
    assert "Safety-net test S-5 (today: Empty gives nothing) now fails." in text
    assert "format_expiry" not in text
    assert "how parse_date worked before the change" in text
    assert [item.test_id for item in report.items] == ["S-4", "S-5"]


def test_9_41_failing_safety_cases_lists_each_case_once():
    result = LayerBResult(
        tests=[
            TestOutcome(name="test_s4_sorted", result="fail"),
            TestOutcome(name="test_s4_sorted_again", result="fail"),
            TestOutcome(name="test_t1_ac1_x", result="fail"),
            TestOutcome(name="test_s5_empty", result="pass"),
        ]
    )

    assert failing_safety_cases(result) == ["S-4"]


def test_the_old_report_wording_is_unchanged_without_notes():
    result = LayerBResult(tests=[TestOutcome(name="test_t1_ac1_x", result="fail", message="m")])

    report = build_failure_report(LayerAResult(), result, [], "", [])

    assert "T-1, AC-1: expected (no description) Got: m" in report_for_developer(report)


# --- 9-43: Layer C check 1 NC line ---


def nc_record():
    return RequestRecord(
        request_id="CVDA-2026-0001",
        version=1,
        rulebook_version=1,
        must_not_change=[
            MustNotChange(id="NC-1", text="Dates stay"),
            MustNotChange(id="NC-2", text="Totals stay"),
            MustNotChange(id="NC-3", text="Order stays"),
        ],
    )


def test_9_43_a_covered_nc_gives_nothing_and_a_not_covered_nc_gives_an_fyi():
    found = check_nc_items(nc_record(), {"NC-1", "NC-3"}, {"NC-2"})

    assert [(f.check, f.severity, f.cites) for f in found] == [(1, "fyi", "NC-2")]
    assert NC_NOT_COVERED_TEXT in found[0].message
    assert "Totals stay" in found[0].message


def test_9_43_the_fyi_does_not_lower_the_label():
    found = check_nc_items(nc_record(), set(), {"NC-1", "NC-2", "NC-3"})

    label = compute_label(found, [], "ok", 1, [])

    assert label == compute_label([], [], "ok", 1, [])


def test_9_43_an_nc_neither_run_nor_listed_is_a_should_fix():
    found = check_nc_items(nc_record(), {"NC-1"}, {"NC-2"})

    assert [(f.cites, f.severity) for f in found] == [("NC-2", "fyi"), ("NC-3", "should_fix")]
