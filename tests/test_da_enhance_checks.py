"""Phase 9, step 2: plain rules for finding the program.

Covers 9-2 (pure part), 9-5 to 9-8, 9-10, 9-11 and 9-21."""

import pytest

from agents.da_enhance_checks import (
    available_symbols,
    find_round_allowed,
    keep_known_symbols,
    lookup_capability,
    meaning_candidates,
    merge_candidates,
    name_candidates,
    next_nc_number,
    number_keep_items,
    parse_keep_lines,
    scope_problems,
    switch_offer_candidate,
    target_problems,
    with_catalog,
)
from pydantic_classes.da_discovery_models import SearchHit
from pydantic_classes.da_request_record_models import MustNotChange, RequestRecord


def hit(path, symbol="", score=0.5, **flags):
    values = {"kind": "code", "mode": "exact"} | flags
    return SearchHit(source_path=path, symbol=symbol, score=score, **values)


HITS = [
    hit("src/agents/limits_expiry_report.py", "format_expiry"),
    hit("src/agents/limits_expiry_report.py", "<module>"),
    hit("src/agents/upload_checker.py", "UploadChecker.check_type"),
    hit("src/agents/old_report_tool.py", "run", deprecated=True),
    hit("src/agents/report_secret_keys.py", "load"),
    hit("docs/limits_expiry_report.md", kind="doc"),
]


@pytest.fixture
def make_policy(seed_rulebook):
    def build(**changes):
        values = {"allowed_folders": ["src/agents", "src/layouts"], "max_files": 2}
        return seed_rulebook.policy.model_copy(update=values | changes)

    return build


# --- 9-5 / 9-2 pure part: by name ---


def test_9_5_a_file_stem_is_the_best_match_found_by_name():
    found = name_candidates("please change limits_expiry_report", HITS, top_k=5)

    assert found[0].path == "src/agents/limits_expiry_report.py"
    assert found[0].best_match is True
    assert found[0].how_found == "name"


def test_9_5_a_symbol_is_a_best_match_and_whole_words_only():
    assert name_candidates("fix format_expiry", HITS, 5)[0].best_match is True
    # "expiry" alone is only part of a name: found, but not Best match.
    partial = name_candidates("expiry", HITS, 5)
    assert partial[0].best_match is False


def test_9_5_a_method_name_alone_is_a_best_match():
    assert name_candidates("the check_type bit", HITS, 5)[0].path.endswith("upload_checker.py")


def test_9_5_at_most_top_k_files_one_per_file():
    many = [hit(f"src/agents/limits_{n}.py", "f") for n in range(8)]

    found = name_candidates("limits", many, top_k=3)

    assert len(found) == 3
    assert len({c.path for c in found}) == 3


def test_9_5_no_words_no_candidates():
    assert name_candidates("the and for", HITS, 5) == []


# --- 9-7: safety filter ---


def test_9_7_deprecated_secret_and_non_code_files_are_never_candidates():
    found = name_candidates("report secret keys old tool limits_expiry_report", HITS, 5)
    paths = {c.path for c in found}

    assert "src/agents/old_report_tool.py" not in paths
    assert "src/agents/report_secret_keys.py" not in paths
    assert "docs/limits_expiry_report.md" not in paths
    assert meaning_candidates(HITS, 3)[0].path.startswith("src/agents/")
    assert all("secret" not in c.path for c in meaning_candidates(HITS, 9))


# --- 9-6: meaning, merge ---


def test_9_6_meaning_gives_at_most_k_files_and_merges_with_name_hits():
    meaning_hits = [
        hit("src/agents/a.py", "f", score=0.9, mode="meaning"),
        hit("src/agents/a.py", "g", score=0.4, mode="meaning"),
        hit("src/agents/limits_expiry_report.py", "f", score=0.6, mode="meaning"),
        hit("src/agents/b.py", "f", score=0.5, mode="meaning"),
        hit("src/agents/c.py", "f", score=0.2, mode="meaning"),
    ]
    by_meaning = meaning_candidates(meaning_hits, top_k=3)
    by_name = name_candidates("limits_expiry_report", HITS, 5)

    merged = merge_candidates(by_name, by_meaning)

    assert len(by_meaning) == 3
    assert [c.path for c in merged].count("src/agents/limits_expiry_report.py") == 1
    assert merged[0].how_found == "name+meaning"
    assert merged[0].best_match is True
    assert {c.how_found for c in merged} == {"name+meaning", "meaning"}


# --- 9-2 pure part: switch offer only on a Best match ---


def test_9_2_switch_offer_needs_a_best_match():
    best = switch_offer_candidate("the limits_expiry_report is wrong", HITS)

    assert best is not None
    assert best.path == "src/agents/limits_expiry_report.py"
    assert switch_offer_candidate("some expiry thing", HITS) is None
    assert switch_offer_candidate("a brand new screen", HITS) is None


# --- 9-8: catalog ---


def test_9_8_first_matching_capability_wins(seed_rulebook):
    caps = seed_rulebook.policy.capabilities

    found = lookup_capability("src\\agents\\Limits_Expiry_Report.py", caps)

    assert found is not None
    assert found.name == "Limits"  # also matches *report*, but Limits is first
    assert lookup_capability("src/agents/other.py", caps) is None


def test_9_8_candidate_shows_capability_and_senior_or_stays_empty(seed_rulebook):
    caps = seed_rulebook.policy.capabilities
    known = name_candidates("limits_expiry_report", HITS, 5)[0]
    unknown = name_candidates("expiry", [hit("src/agents/expiry.py", "f")], 5)[0]

    shown = with_catalog(known, caps)

    assert shown.capability == "Limits"
    assert shown.named_senior == "Limits capability lead"
    assert with_catalog(unknown, caps).capability == ""


def test_g6_m5_senior_comes_from_the_main_capability_only(seed_rulebook):
    # A module in two capabilities: the first is main; "also" never adds a second senior.
    first, second = seed_rulebook.policy.capabilities[:2]
    both = [
        first.model_copy(update={"path_patterns": ["*shared_x*"]}),
        second.model_copy(update={"path_patterns": ["*shared_x*"]}),
    ]
    shown = with_catalog(name_candidates("shared_x", [hit("src/shared_x.py", "f")], 5)[0], both)

    assert shown.capability == first.name
    assert shown.named_senior == first.named_senior


# --- 9-10: round cap ---


def test_9_10_three_empty_searches_leave_only_get_help(make_policy):
    policy = make_policy()

    assert find_round_allowed(2, policy) is True
    assert find_round_allowed(3, policy) is False


# --- 9-11: targets ---


def test_9_11_targets_must_be_py_files_in_allowed_folders(make_policy):
    policy = make_policy()

    assert target_problems(["src/agents/limits.py", "src\\layouts\\screen.py"], policy) == []
    assert "allowed folder" in target_problems(["src/other/x.py"], policy)[0]
    assert ".py" in target_problems(["src/agents/readme.md"], policy)[0]
    assert "relative" in target_problems(["../src/agents/x.py"], policy)[0]
    assert "relative" in target_problems(["C:/src/agents/x.py"], policy)[0]
    assert target_problems([], policy)


def test_9_11_more_than_max_files_and_duplicates_are_refused(make_policy):
    policy = make_policy()
    three = ["src/agents/a.py", "src/agents/b.py", "src/agents/c.py"]

    assert "At most 2" in target_problems(three, policy)[0]
    twice = target_problems(["src/agents/A.py", "src/agents/a.py"], policy)
    assert any("more than once" in problem for problem in twice)


def test_9_11_a_protected_file_is_refused(make_policy):
    policy = make_policy(protected_files=["src/agents/locked*.py"])

    assert "protected" in target_problems(["src/agents/locked_one.py"], policy)[0]


# --- 9-21: functions in scope ---

SOURCE = '''
def format_expiry(day):
    return day

class Checker:
    def check(self):
        return 1
'''


def test_available_symbols_come_from_the_split():
    assert available_symbols("src/agents/x.py", SOURCE) == [
        "format_expiry",
        "Checker",
        "Checker.check",
    ]


def test_9_21_an_unknown_symbol_is_dropped_and_at_least_one_must_stay():
    real = available_symbols("src/agents/x.py", SOURCE)

    kept, dropped = keep_known_symbols(["format_expiry", "ghost", "ghost", "format_expiry"], real)

    assert kept == ["format_expiry"]
    assert dropped == ["ghost"]
    assert scope_problems(["format_expiry"], real) == []
    assert "not a function" in scope_problems(["ghost"], real)[0]
    assert "at least one" in scope_problems([], real)[0]


# --- NC numbering ---


def make_record(version, items):
    return RequestRecord(
        request_id="CVDA-2026-0001",
        version=version,
        rulebook_version=1,
        must_not_change=[MustNotChange(id=i, text=t) for i, t in items],
    )


def test_keep_lines_one_per_line_nothing_special_and_the_cap(make_policy):
    policy = make_policy(enhance_max_keep_items=2)

    assert parse_keep_lines("- Dates stay\n\n  Totals stay  \n", policy)[0] == [
        "Dates stay",
        "Totals stay",
    ]
    assert parse_keep_lines("Nothing special.", policy) == ([], [])
    assert "At most 2" in parse_keep_lines("a\nb\nc", policy)[1][0]


def test_nc_ids_are_never_reused_even_after_a_removal():
    v1 = make_record(1, [("NC-1", "Dates stay"), ("NC-2", "Totals stay")])
    v2 = make_record(2, [("NC-1", "Dates stay")])  # NC-2 was removed

    assert next_nc_number([v1, v2]) == 3

    numbered = number_keep_items(["dates  stay", "New rule"], v2.must_not_change, [v1, v2])

    assert [(i.id, i.text) for i in numbered] == [("NC-1", "Dates stay"), ("NC-3", "New rule")]
