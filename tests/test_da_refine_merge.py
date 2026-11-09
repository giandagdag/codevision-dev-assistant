"""Phase 8 plain rules, code side (tests 8-22 fingerprints, 8-26, 8-27, 8-28, 8-35, restore set)."""

import pytest

from agents.da_build_checks import LayerAContext, check_layer_a
from agents.da_refine_merge import (
    MergeError,
    ai_text,
    append_test_method,
    build_restore_set,
    changed_ranges,
    generator_action,
    his_lines,
    marker_text,
    merge_picks,
    method_fingerprints,
    plan_merge,
    split_lines,
)
from pydantic_classes.da_build_models import Contract, ContractFile, ContractItem
from pydantic_classes.da_rulebook_models import Policy


def numbered(count: int) -> str:
    return "".join(f"line {n}\n" for n in range(1, count + 1))


WRITTEN = numbered(30)


def edit_line(text: str, number: int, new: str) -> str:
    lines = split_lines(text)
    lines[number - 1] = new
    return "".join(f"{line}\n" for line in lines)


# --- his lines ---


def test_his_lines_are_the_lines_that_differ_from_what_the_app_wrote():
    mine = edit_line(WRITTEN, 10, "MY CHANGE")

    assert his_lines(WRITTEN, mine) == [(9, 10)]
    assert his_lines(WRITTEN, WRITTEN) == []


def test_a_deleted_line_is_an_empty_range_at_its_place():
    mine = "".join(f"{line}\n" for line in split_lines(WRITTEN)[:4] + split_lines(WRITTEN)[5:])

    assert his_lines(WRITTEN, mine) == [(4, 4)]


def test_8_26_the_prompt_marks_his_lines():
    assert marker_text([(39, 44)]) == (
        "Lines 40 to 44 were written by the developer. "
        "Do not change them unless the failure report needs it."
    )
    assert marker_text([(9, 10)]).startswith("Line 10 was written by the developer.")
    assert marker_text([(4, 4)]).startswith("The developer removed lines after line 4.")
    assert marker_text([]) == ""


# --- conflicts ---


def make_plan(ai_changes: dict[int, str], mine_line: int = 10, distance: int = 3):
    his = edit_line(WRITTEN, mine_line, "MY CHANGE")
    ai = his
    for number, text in ai_changes.items():
        ai = edit_line(ai, number, text)
    return his, plan_merge("src/agents/x.py", WRITTEN, his, ai, distance, 3)


def test_8_27_a_change_on_his_line_is_a_conflict_with_both_sides_and_context():
    his, plan = make_plan({10: "AI VERSION"})

    assert len(plan.conflicts) == 1
    conflict = plan.conflicts[0]
    assert conflict.conflict_id == "C-1"
    assert (conflict.his_start, conflict.his_end) == (10, 10)
    assert conflict.his_lines == ["MY CHANGE"]
    assert conflict.ai_lines == ["AI VERSION"]
    assert conflict.context_before == ["line 7", "line 8", "line 9"]
    assert conflict.context_after == ["line 11", "line 12", "line 13"]


def test_a_change_on_the_line_next_to_his_lines_is_a_conflict():
    _, plan = make_plan({11: "AI NEXT TO MINE"}, distance=1)

    assert len(plan.conflicts) == 1
    assert (plan.conflicts[0].his_start, plan.conflicts[0].his_end) == (10, 11)


def test_a_change_far_away_is_no_conflict():
    his, plan = make_plan({25: "FAR AWAY"})

    assert plan.conflicts == []
    assert not plan.has_conflicts
    assert split_lines(ai_text(plan))[24] == "FAR AWAY"
    assert split_lines(ai_text(plan))[9] == "MY CHANGE"


def test_the_distance_decides_what_is_next_to_his_lines():
    # AI changes line 13; his change is line 10. Gap of 2 lines between them.
    assert make_plan({13: "AI"}, distance=1)[1].conflicts == []
    assert len(make_plan({13: "AI"}, distance=3)[1].conflicts) == 1


def test_8_28_all_picks_the_ai_gives_the_tested_result_as_it_is():
    his, plan = make_plan({10: "AI VERSION", 25: "FAR AWAY"})

    result = merge_picks(plan, {"C-1": "ai"})

    assert result == ai_text(plan)
    assert split_lines(result)[9] == "AI VERSION"
    assert split_lines(result)[24] == "FAR AWAY"


def test_keep_mine_keeps_his_lines_and_still_applies_the_free_changes():
    his, plan = make_plan({10: "AI VERSION", 25: "FAR AWAY"})

    result = merge_picks(plan, {"C-1": "mine"})

    assert split_lines(result)[9] == "MY CHANGE"
    assert split_lines(result)[24] == "FAR AWAY"
    assert len(split_lines(result)) == 30


def test_two_conflicts_are_numbered_and_picked_one_by_one():
    his = edit_line(edit_line(WRITTEN, 5, "MINE 5"), 25, "MINE 25")
    ai = edit_line(edit_line(his, 5, "AI 5"), 25, "AI 25")
    plan = plan_merge("src/a.py", WRITTEN, his, ai, 1, 1)

    assert [c.conflict_id for c in plan.conflicts] == ["C-1", "C-2"]
    result = split_lines(merge_picks(plan, {"C-1": "ai", "C-2": "mine"}))
    assert result[4] == "AI 5"
    assert result[24] == "MINE 25"


def test_nothing_is_merged_until_every_conflict_has_a_pick():
    _, plan = make_plan({10: "AI VERSION"})

    with pytest.raises(MergeError, match="C-1"):
        merge_picks(plan, {})


def test_lines_the_ai_does_not_touch_stay_byte_for_byte_his():
    his, plan = make_plan({25: "FAR AWAY"})
    result = split_lines(merge_picks(plan, {}))

    for number in range(1, 31):
        if number != 25:
            assert result[number - 1] == split_lines(his)[number - 1]


def test_a_file_without_a_final_line_break_stays_without_one():
    his = edit_line(WRITTEN, 10, "MY CHANGE").rstrip("\n")
    ai = his.replace("line 25\n", "FAR AWAY\n")
    plan = plan_merge("src/a.py", WRITTEN, his, ai, 1, 1)

    result = merge_picks(plan, {})

    assert "FAR AWAY" in result and not result.endswith("\n")


def test_the_files_own_line_ending_is_kept():
    his = edit_line(WRITTEN, 10, "MY CHANGE").replace("\n", "\r\n")
    ai = his.replace("line 25\r\n", "FAR AWAY\r\n")
    plan = plan_merge("src/a.py", WRITTEN, his, ai, 1, 1)

    result = merge_picks(plan, {})

    assert "\r\n" in result and "\n" not in result.replace("\r\n", "")
    assert "FAR AWAY" in result


def test_an_ai_insert_and_delete_next_to_his_lines_are_conflicts_too():
    his = edit_line(WRITTEN, 10, "MY CHANGE")
    ai = "".join(
        f"{line}\n" for line in split_lines(his)[:10] + ["INSERTED"] + split_lines(his)[10:]
    )
    plan = plan_merge("src/a.py", WRITTEN, his, ai, 1, 1)

    assert len(plan.conflicts) == 1
    assert (
        plan.conflicts[0].ai_lines[-1:] == ["INSERTED"] or "INSERTED" in plan.conflicts[0].ai_lines
    )


# --- every file is modify after the first write (R5.2) ---


def test_8_26_every_planned_file_with_a_known_text_is_a_modify_for_the_generator():
    known = {"src/agents/x.py"}

    assert generator_action("src/agents/x.py", "create", known) == "modify"
    assert generator_action("src/agents/y.py", "create", known) == "create"
    assert generator_action("src/agents/y.py", "modify", known) == "modify"


# --- 8-35: the Generator may not write under tests/ (Layer A, his tests included) ---


def test_8_35_a_generator_file_under_tests_is_refused_by_layer_a():
    context = LayerAContext(
        planned_paths=["src/agents/x.py"],
        policy=Policy.model_validate(_policy_data()),
        contract=Contract(
            files=[
                ContractFile(
                    path="src/agents/x.py",
                    items=[ContractItem(name="run", kind="function", args=[], summary="Runs.")],
                )
            ]
        ),
        codevision_modules=set(),
    )

    result = check_layer_a({"tests/cvda/test_cvda.py": "x = 1\n"}, context)

    assert not result.ok
    assert result.problems[0].code == "A2"
    assert "frozen" in result.problems[0].text


def _policy_data() -> dict:
    return {
        "default_level": "L1",
        "max_level": "L3",
        "never_generate_zones": [],
        "max_review_rounds": 3,
        "escalation_triggers": [],
    }


# --- the frozen test set grows (8-22) ---

TEST_FILE = '''import unittest


class TestCvda(unittest.TestCase):
    def test_t1_ac1_first(self):
        """The first thing is expected."""
        self.assertTrue(True)

    def test_t2_ac2_second(self):
        """The second thing is expected."""
        self.assertEqual(1, 1)
'''

NEW_METHOD = '''def test_t3_ac2_bug(self):
    """The bug is shown."""
    self.assertEqual(1, 2)
'''


def test_8_22_an_appended_method_leaves_earlier_methods_byte_for_byte_the_same():
    before = method_fingerprints(TEST_FILE)

    after_text = append_test_method(TEST_FILE, NEW_METHOD)
    after = method_fingerprints(after_text)

    assert set(after) == set(before) | {"test_t3_ac2_bug"}
    for name, value in before.items():
        assert after[name] == value
    assert after_text.startswith(TEST_FILE.rstrip("\n"))


def test_an_appended_method_must_be_one_new_test_method():
    with pytest.raises(MergeError, match="already"):
        append_test_method(TEST_FILE, NEW_METHOD.replace("t3_ac2_bug", "t1_ac1_first"))
    with pytest.raises(MergeError, match="exactly one"):
        append_test_method(TEST_FILE, "x = 1\n")
    with pytest.raises(MergeError, match="syntax"):
        append_test_method(TEST_FILE, "def test_t9_ac1_x(self:\n")


# --- restore ---


def test_a_restore_set_is_the_whole_set_in_plan_order_and_names_what_it_lacks():
    planned = ["src/a.py", "src/b.py", "src/c.py"]
    saved = {"src/c.py": "C1", "src/a.py": "A1"}

    write, left = build_restore_set(planned, saved)

    assert list(write) == ["src/a.py", "src/c.py"]
    assert left == ["src/b.py"]


def test_changed_ranges_of_equal_texts_is_empty():
    assert changed_ranges(WRITTEN, WRITTEN) == []
