"""Fix G7 step 1: dotted standard library names (S1) and problem kinds in log lines (R5)."""

import logging

from agents.da_approach_agent import ApproachContext, generate_approach
from agents.da_approach_checks import PROPOSE, find_approach_problems
from agents.da_problem_kinds import problem_kind, problem_kinds
from pydantic_classes.da_approach_models import ApproachReply
from tests.da_approach_samples import good_plan, sample_discovery, sample_record
from tests.da_stub_client import StubClient


def _problems(policy, libraries):
    reply = ApproachReply.model_validate(good_plan(libraries=libraries))
    return find_approach_problems(reply, policy, sample_discovery(), set(), PROPOSE)


def test_g7_6_dotted_standard_library_names_pass(seed_rulebook):
    names = ["xml.etree.ElementTree", "os.path", "email.mime.text", "zipfile"]

    assert _problems(seed_rulebook.policy, names) == []


def test_g7_6_an_unknown_dotted_name_is_one_problem_naming_it(seed_rulebook):
    found = _problems(seed_rulebook.policy, ["python_docx.api"])

    assert len(found) == 1
    assert "python_docx.api" in found[0]


def test_kinds_name_each_sort_of_problem():
    assert problem_kind("The reply was not valid JSON. Reply with JSON only.") == "json"
    assert problem_kind("The reply has the wrong shape: summary: oops") == "shape"
    assert problem_kind("wrong shape: options.1: String should have at most 100 characters") == (
        "too_long"
    )
    assert problem_kind("Library 'x' is not in the Python standard library") == "library"
    assert problem_kind("src/a.py is protected. List it") == "protected"
    assert problem_kind("src/a.py is not in an allowed folder.") == "folder"
    assert problem_kind("a new file name must match ^x$") == "file_name"
    assert problem_kind("Discover hit 3 needs a reuse decision") == "reuse"
    assert problem_kind("There are 4 design choices.") == "design"
    assert problem_kind("something else") == "other"


def test_kinds_line_counts_and_lists_kinds():
    text = problem_kinds(["Library 'x' is not in the Python standard library", "odd"])

    assert text == "2 problems (library, other)"
    assert problem_kinds(["odd"]) == "1 problem (other)"


def test_g7_11_the_approach_log_line_names_kinds_and_never_the_reply_text(
    seed_rulebook, caplog, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)  # the rejected-reply log goes under the working folder
    secret = "SECRET-REPLY-TEXT"
    bad = good_plan(summary=secret, libraries=["python-docx"])
    context = ApproachContext(
        charter=seed_rulebook.charter, record=sample_record(),
        discovery=sample_discovery(), policy=seed_rulebook.policy,
    )

    with caplog.at_level(logging.WARNING):
        result = generate_approach(StubClient(bad, bad), PROPOSE, context)

    assert not result.ok
    assert "was not usable: 1 problem (library)" in caplog.text
    assert secret not in caplog.text
