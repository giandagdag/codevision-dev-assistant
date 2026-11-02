"""Workspace rules (Phase 5, spec sections 4 to 6). Plain facts in, plain decisions out."""

import pytest

from agents import da_workspace_checks as checks
from pydantic_classes.da_approach_models import PlannedFile
from pydantic_classes.da_workspace_models import (
    ABSENT,
    FileFact,
    FolderFacts,
    TestsFileFact,
    WriteReport,
    WriteStop,
    WrittenFile,
)

REQUEST_ID = "CVDA-2026-0001"
MODIFY = "src/callbacks/da_demo_callbacks.py"
CREATE = "src/web/da_demo_helper.py"
TESTS = "tests/cvda_2026_0001"


@pytest.fixture
def policy(seed_rulebook):
    return seed_rulebook.policy


def plan():
    return [
        PlannedFile(path=MODIFY, action="modify", purpose="Change it"),
        PlannedFile(path=CREATE, action="create", purpose="Add it"),
    ]


def good_facts(**changes) -> FolderFacts:
    values = {
        "folder_name": "codevision",
        "markers": {"src/web": True, "src/callbacks": True},
        "has_git": True,
        "files": [
            FileFact(path=MODIFY, exists=True, parent_exists=True, text="x = 1\n"),
            FileFact(path=CREATE, exists=False, parent_exists=True),
        ],
    }
    values.update(changes)
    return FolderFacts(**values)


def run_check(facts, policy, written=None, remembered=""):
    return checks.check_facts(facts, plan(), policy, REQUEST_ID, written, remembered)


def codes(result):
    return [item.code for item in result.blockers]


# --- fingerprints (5-14) ---


def test_line_endings_and_a_byte_order_mark_give_the_same_fingerprint():
    plain = checks.fingerprint("a = 1\nb = 2\n")

    assert checks.fingerprint("a = 1\r\nb = 2\r\n") == plain
    assert checks.fingerprint("\ufeffa = 1\nb = 2\n") == plain
    assert len(plain) == 64


def test_a_changed_character_changes_the_fingerprint():
    assert checks.fingerprint("a = 1\n") != checks.fingerprint("a = 2\n")


def test_the_known_sha256_of_a_short_text():
    # Also checked in the browser (test 5-15) against the same constant.
    assert checks.fingerprint("# hi\n") == (
        "045d2d07c2db3b9e6cef022457ee89434045a508c2dadccf9abe182ad633c273"
    )


# --- line endings kept (5-16, Python half) ---


def test_a_crlf_file_is_written_back_with_crlf():
    assert checks.line_ending_of("a\r\nb\r\n") == "\r\n"
    assert checks.apply_line_ending("a\nb\n", "\r\n") == "a\r\nb\r\n"


def test_a_new_file_and_a_file_without_line_breaks_use_lf():
    assert checks.line_ending_of("one line") == "\n"
    assert checks.apply_line_ending("a\r\nb\r\n", "\n") == "a\nb\n"


# --- paths (5-11, server half) ---


@pytest.mark.parametrize(
    "path", ["", "../x.py", "src/../x.py", "./x.py", "src//x.py", "/etc/x", "C:/x", "src\\x.py"]
)
def test_unsafe_paths_are_refused(path):
    assert checks.path_problem(path)


def test_a_plain_relative_path_is_allowed():
    assert checks.path_problem("src/web/da_x.py") == ""


# --- the workspace check: blockers (5-2 to 5-8) ---


def test_5_2_a_folder_without_a_marker_is_b1(policy):
    facts = good_facts(markers={"src/web": True, "src/callbacks": False})

    result = run_check(facts, policy)

    assert codes(result) == ["B1"]
    assert not result.passed
    assert "src/web" in result.blockers[0].text and "src/callbacks" in result.blockers[0].text


def test_5_3_the_src_folder_itself_is_b2(policy):
    facts = good_facts(looks_like_src=True, markers={"src/web": False, "src/callbacks": False})

    result = run_check(facts, policy)

    assert codes(result) == ["B2"]
    assert "Pick the folder above it" in result.blockers[0].text


def test_5_4_a_missing_modify_file_is_b3_and_names_the_path(policy):
    facts = good_facts(
        files=[
            FileFact(path=MODIFY, exists=False, parent_exists=True),
            FileFact(path=CREATE, exists=False, parent_exists=True),
        ]
    )

    result = run_check(facts, policy)

    assert codes(result) == ["B3"]
    assert MODIFY in result.blockers[0].text


def test_5_5_a_new_file_that_already_exists_is_b4(policy):
    facts = good_facts(
        files=[
            FileFact(path=MODIFY, exists=True, parent_exists=True, text="x\n"),
            FileFact(path=CREATE, exists=True, parent_exists=True, text="y\n"),
        ]
    )

    assert codes(run_check(facts, policy)) == ["B4"]


def test_5_6_a_missing_parent_folder_is_b5(policy):
    facts = good_facts(
        files=[
            FileFact(path=MODIFY, exists=True, parent_exists=True, text="x\n"),
            FileFact(path=CREATE, exists=False, parent_exists=False),
        ]
    )

    result = run_check(facts, policy)

    assert codes(result) == ["B5"]
    assert "never creates folders" in result.blockers[0].text


def test_5_7_a_file_over_the_limit_and_a_file_that_is_not_utf8_are_b6(policy):
    big = "x" * (policy.workspace_max_file_kb * 1024 + 1)
    facts = good_facts(
        files=[
            FileFact(path=MODIFY, exists=True, parent_exists=True, text=big),
            FileFact(path=CREATE, exists=False, parent_exists=True),
        ]
    )
    not_utf8 = good_facts(
        files=[
            FileFact(path=MODIFY, exists=True, parent_exists=True, not_utf8=True),
            FileFact(path=CREATE, exists=False, parent_exists=True),
        ]
    )
    too_big_in_browser = good_facts(
        files=[
            FileFact(path=MODIFY, exists=True, parent_exists=True, too_big=True),
            FileFact(path=CREATE, exists=False, parent_exists=True),
        ]
    )

    assert codes(run_check(facts, policy)) == ["B6"]
    assert codes(run_check(not_utf8, policy)) == ["B6"]
    assert codes(run_check(too_big_in_browser, policy)) == ["B6"]


def test_5_8_a_tests_folder_with_a_foreign_file_is_b7(policy):
    facts = good_facts(
        tests_exists=True, tests_files=[TestsFileFact(name="test_old.py", text="pass\n")]
    )

    result = run_check(facts, policy, written={"__init__.py"})

    assert codes(result) == ["B7"]
    assert "tests/cvda_2026_0001/" in result.blockers[0].text


def test_files_this_request_wrote_do_not_block_the_tests_folder(policy):
    facts = good_facts(
        tests_exists=True, tests_files=[TestsFileFact(name="__init__.py", text="# x\n")]
    )

    assert run_check(facts, policy, written={"__init__.py"}).passed


def test_5_9_a_good_folder_without_git_passes_with_the_information_line(policy):
    result = run_check(good_facts(has_git=False), policy)

    assert result.passed
    assert not result.has_git
    assert "not a Git clone" in result.info[0]
    assert result.warnings == []


def test_a_good_folder_with_git_has_no_information_line(policy):
    result = run_check(good_facts(), policy)

    assert result.passed and result.info == [] and result.has_git


def test_a_different_remembered_folder_name_is_a_warning_not_a_blocker(policy):
    result = run_check(good_facts(), policy, remembered="old-clone")

    assert result.passed
    assert result.warnings == ["This request was linked to old-clone. You picked codevision."]


def test_no_file_checks_run_when_the_folder_is_wrong(policy):
    facts = good_facts(
        markers={"src/web": False, "src/callbacks": False},
        files=[
            FileFact(path=MODIFY, exists=False, parent_exists=False),
            FileFact(path=CREATE, exists=True, parent_exists=False),
        ],
    )

    assert codes(run_check(facts, policy)) == ["B1"]


# --- facts the server will not trust (W3, P13) ---


def test_a_path_outside_the_plan_is_refused():
    facts = good_facts(files=[FileFact(path="src/secret.py", exists=True, parent_exists=True)])

    with pytest.raises(checks.FactsProblem, match="not in the file plan"):
        checks.verify_facts(facts, [MODIFY, CREATE], REQUEST_ID)


def test_a_browser_fingerprint_that_differs_is_refused():
    facts = good_facts(
        files=[
            FileFact(path=MODIFY, exists=True, parent_exists=True, text="x\n", fingerprint="0" * 64)
        ]
    )

    with pytest.raises(checks.FactsProblem, match="disagree"):
        checks.verify_facts(facts, [MODIFY, CREATE], REQUEST_ID)


def test_a_correct_browser_fingerprint_is_accepted():
    good = checks.fingerprint("x\n")
    facts = good_facts(
        files=[
            FileFact(path=MODIFY, exists=True, parent_exists=True, text="x\r\n", fingerprint=good)
        ]
    )

    checks.verify_facts(facts, [MODIFY, CREATE], REQUEST_ID)


# --- the write job and the edit guard (5-11 to 5-13) ---


def test_the_job_expects_absent_for_a_new_file_and_the_known_fingerprint_otherwise():
    known = {MODIFY: (checks.fingerprint("x = 1\n"), "\r\n")}

    items = [(MODIFY, "x = 2\n"), (CREATE, "y\n")]
    job = checks.build_write_job(REQUEST_ID, "codevision", items, known)

    assert [(f.path, f.expected) for f in job.files] == [
        (MODIFY, checks.fingerprint("x = 1\n")),
        (CREATE, ABSENT),
    ]
    assert job.files[0].text == "x = 2\r\n"  # 5-16: the file's own style
    assert job.files[1].text == "y\n"
    assert job.creatable_folders == ["tests", TESTS]


def test_a_job_with_an_unsafe_path_is_never_built():
    with pytest.raises(checks.FactsProblem):
        checks.build_write_job(REQUEST_ID, "codevision", [("../x.py", "a")], {})


def test_5_12_the_edit_guard_stops_a_file_that_changed():
    expected = checks.fingerprint("old\n")

    assert checks.edit_guard_allows("old\r\n", expected)  # only the line ending differs
    assert not checks.edit_guard_allows("developer edit\n", expected)
    assert not checks.edit_guard_allows(None, expected)  # the file is gone


def test_5_13_a_new_file_that_now_exists_is_stopped():
    assert checks.edit_guard_allows(None, ABSENT)
    assert not checks.edit_guard_allows("", ABSENT)


def job_of(*paths):
    return checks.build_write_job(REQUEST_ID, "codevision", [(p, "t\n") for p in paths], {})


def written(path, text="t\n"):
    return WrittenFile(path=path, text=text, fingerprint=checks.fingerprint(text))


def test_5_11_a_report_naming_a_path_outside_the_job_is_refused():
    job = job_of(CREATE)

    with pytest.raises(checks.FactsProblem, match="not in the write job"):
        checks.verify_report(job, WriteReport(written=[written("src/other.py")]))
    with pytest.raises(checks.FactsProblem):
        checks.verify_report(job, WriteReport(written=[written("../x.py")]))


def test_a_report_with_a_hash_the_server_cannot_reproduce_is_refused():
    job = job_of(CREATE)
    bad = WrittenFile(path=CREATE, text="t\n", fingerprint="1" * 64)

    with pytest.raises(checks.FactsProblem, match="disagree"):
        checks.verify_report(job, WriteReport(written=[bad]))


def test_a_report_in_a_different_order_is_refused():
    job = job_of(MODIFY, CREATE)

    with pytest.raises(checks.FactsProblem, match="different order"):
        checks.verify_report(job, WriteReport(written=[written(CREATE)]))


def test_5_12_a_stopped_report_names_both_lists():
    job = job_of(MODIFY, CREATE)
    report = WriteReport(
        written=[written(MODIFY)], stopped=WriteStop(path=CREATE, reason="Changed since last time.")
    )

    checks.verify_report(job, report)
    message = checks.stop_message(job, report)

    assert f"Written: {MODIFY}" in message
    assert f"Not written: {CREATE}" in message
    assert "Re-scan first" in message


# --- re-scan (5-17, 5-18) ---


def scan(facts, written_names=None):
    known = {
        MODIFY: checks.fingerprint("x = 1\n"),
        f"{TESTS}/__init__.py": checks.fingerprint("# x\n"),
    }
    return checks.rescan_results(
        facts, [MODIFY, CREATE], known, REQUEST_ID, written_names or {"__init__.py"}
    )


def outcomes(result):
    return {item.path: item.outcome for item in result.items}


def test_5_17_an_edited_file_is_changed_and_an_untouched_one_is_unchanged():
    facts = good_facts(
        files=[
            FileFact(path=MODIFY, exists=True, parent_exists=True, text="x = 99\n"),
            FileFact(path=CREATE, exists=False, parent_exists=True),
        ]
    )

    result = outcomes(scan(facts))

    assert result[MODIFY] == "changed"
    assert result[CREATE] == "missing"


def test_a_file_with_only_a_line_ending_flip_is_unchanged():
    facts = good_facts(
        files=[
            FileFact(path=MODIFY, exists=True, parent_exists=True, text="x = 1\r\n"),
            FileFact(path=CREATE, exists=False, parent_exists=True),
        ]
    )

    assert outcomes(scan(facts))[MODIFY] == "unchanged"


def test_5_18_an_extra_file_in_the_tests_folder_is_new_in_tests():
    facts = good_facts(
        tests_files=[
            TestsFileFact(name="__init__.py", text="# x\n"),
            TestsFileFact(name="test_mine.py", text="pass\n"),
        ]
    )

    result = outcomes(scan(facts))

    assert result[f"{TESTS}/test_mine.py"] == "new_in_tests"
    assert result[f"{TESTS}/__init__.py"] == "unchanged"


def test_a_tests_file_the_app_wrote_that_is_gone_is_missing():
    assert outcomes(scan(good_facts()))[f"{TESTS}/__init__.py"] == "missing"


def test_5_18_a_scan_with_a_path_outside_the_plan_is_refused():
    facts = good_facts(files=[FileFact(path="src/other.py", exists=True, parent_exists=True)])

    with pytest.raises(checks.FactsProblem):
        scan(facts)
