import pytest

from agents.da_understand_checks import (
    build_candidate,
    confirmation_gate_problems,
    contains_code,
    developer_message_problem,
    find_invented_names,
    find_reply_problems,
    find_secret,
    refresh_scope_conflicts,
)
from pydantic_classes.da_request_record_models import InterpreterReply, RequestRecord

# Made-up test value shaped like an API key: "sk-" followed by 24 key characters.
FAKE_KEY = "sk-" + "test0000fake1111notreal2"


def make_record(**changes):
    values = {"request_id": "CVDA-2026-0001", "rulebook_version": 1}
    values.update(changes)
    return RequestRecord(**values)


def reply(**values):
    return InterpreterReply.model_validate(values)


def criterion(id_, kind, **parts):
    values = {
        "id": id_,
        "kind": kind,
        "given": "an empty workbook",
        "when": "it is uploaded",
        "then": "it is rejected with the standard empty-file error",
    }
    return values | parts


def complete_record(**changes):
    values = {
        "title": "Add Excel document processing",
        "objective": "Let users upload Excel workbooks.",
        "reason": "Teams convert Excel to PDF by hand today.",
        "current_behaviour": "Only PDF and DOCX are accepted.",
        "expected_behaviour": "Excel content goes into the existing ingestion flow.",
        "inputs": ".xlsx workbooks",
        "outputs": "Content in the normal ingestion format",
        "functional_flow": ["The user uploads a workbook", "The content is extracted"],
        "acceptance_criteria": [
            criterion("AC-1", "success"),
            criterion("AC-2", "failure"),
        ],
        "answered_questions": [1, 2, 3, 4],
    }
    values.update(changes)
    return make_record(**values)


# --- developer messages: secrets and length (R8, R9) ---


@pytest.mark.parametrize(
    "text",
    [
        f"My key is {FAKE_KEY}",
        "password=Summer2026",
        "api_key: abc123",
        "-----BEGIN RSA PRIVATE KEY-----",
        "AKIAABCDEFGHIJKLMNOP",
    ],
)
def test_secrets_are_found(text):
    assert find_secret(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        "Skip the sk-ip step",
        "Use the task-list screen",
        "Reject password-protected workbooks",
        "The token is checked by the login screen",
    ],
)
def test_ordinary_text_is_not_a_secret(text):
    assert find_secret(text) is None


def test_secret_message_says_why_it_was_refused():
    problem = developer_message_problem(f"Use {FAKE_KEY} to connect")

    assert "an API key" in problem
    assert "not saved" in problem


def test_message_up_to_4000_characters():
    assert developer_message_problem("x" * 4000) is None
    assert "4,000" in developer_message_problem("x" * 4001)


def test_empty_message_is_refused():
    assert developer_message_problem("   ") == "Please type a message first."


# --- code (R1) ---


@pytest.mark.parametrize(
    "text",
    [
        "```python\nprint(1)\n```",
        "def check():",
        "  import os",
        "class Upload:",
        "from upload import check",
    ],
)
def test_code_is_found(text):
    assert contains_code(text)


@pytest.mark.parametrize(
    "text",
    [
        "Class sizes are not affected.",
        "Import the workbook from the upload screen.",
        "The definition of done is unchanged.",
    ],
)
def test_plain_sentences_are_not_code(text):
    assert not contains_code(text)


def test_reply_with_code_is_refused():
    problems = find_reply_problems(
        reply(updates={"objective": "def upload():\n    pass"}), make_record(), ""
    )

    assert any("contains code" in problem for problem in problems)


def test_code_in_an_ambiguity_option_is_refused():
    bad = reply(
        ambiguities=[
            {"text": "Which sheets?", "material": True, "options": ["import all", "```x```"]}
        ]
    )

    assert any("contains code" in p for p in find_reply_problems(bad, make_record(), ""))


# --- invented names (spec 3.5, review M3) ---


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("Call upload_check.py first", "upload_check.py"),
        ("Then check_type() runs", "check_type()"),
        ("Then check_type(file) runs", "check_type(file)"),
        ("Then upload.check_type validates it", "upload.check_type"),
    ],
)
def test_invented_names_are_found(text, name):
    assert find_invented_names(text, developer_text="") == [name]


@pytest.mark.parametrize(
    "text",
    [
        "Read each worksheet(s) in turn, e.g. the summary sheet.",
        "Works as in v1.2, i.e. no change.",
        "Reject the file (empty or corrupted).",
        "Accept .xlsx files and older file(s) stay rejected.",
        "The upload screen checks the file type.",
    ],
)
def test_ordinary_english_has_no_invented_names(text):
    assert find_invented_names(text, developer_text="") == []


def test_a_name_the_developer_typed_is_allowed():
    typed = "The Upload.Check_Type step rejects Excel."

    assert find_invented_names("Then upload.check_type accepts .xlsx", typed) == []


def test_invented_name_in_functional_flow_is_refused():
    bad = reply(updates={"functional_flow": ["Call excel_reader.py", "Save the content"]})

    problems = find_reply_problems(bad, make_record(), "Support Excel uploads")

    assert problems == [
        "Functional flow names 'excel_reader.py', which the developer did not type. "
        "Describe the step in plain words instead of naming files or functions."
    ]


def test_names_in_other_fields_are_not_checked():
    ok = reply(updates={"references": ["Existing pdf_reader.py processing"]})

    assert find_reply_problems(ok, make_record(), "") == []


# --- reply shape ---


def test_unknown_and_app_filled_fields_are_refused():
    bad = reply(updates={"colour": "blue", "open_items": ["x"]})

    problems = find_reply_problems(bad, make_record(), "")

    assert len(problems) == 2
    assert all("is not a field you may fill" in problem for problem in problems)


def test_wrong_value_type_is_refused():
    bad = reply(updates={"title": ["a list"], "in_scope": "text"})

    problems = find_reply_problems(bad, make_record(), "")

    assert "'title' must be text, not a list." in problems
    assert "'in_scope' must be a list of short items, not text." in problems


def test_limits_are_checked_on_the_whole_record():
    problems = find_reply_problems(reply(updates={"title": "x" * 81}), make_record(), "")

    assert len(problems) == 1
    assert problems[0].startswith("A value breaks a limit: title")


def test_material_ambiguity_needs_2_or_3_options():
    bad = reply(ambiguities=[{"text": "Hidden sheets?", "material": True, "options": ["Yes"]}])

    problems = find_reply_problems(bad, make_record(), "")

    assert problems == [
        'Ambiguity "Hidden sheets?" is material, so it needs 2 or 3 options (it has 1).'
    ]


def test_minor_ambiguity_needs_an_assumption():
    bad = reply(ambiguities=[{"text": "Which format?", "material": False}])

    problems = find_reply_problems(bad, make_record(), "")

    assert problems == [
        'Ambiguity "Which format?" is minor, so it needs an assumption with its basis.'
    ]


def test_good_reply_has_no_problems():
    good = reply(
        updates={"title": "Add Excel document processing", "in_scope": ["Accept .xlsx"]},
        ambiguities=[
            {"text": "Hidden sheets?", "material": True, "options": ["Visible", "All"]},
            {
                "text": "Which format?",
                "material": False,
                "assumption": {"text": "Excel means .xlsx", "basis": "Rulebook v1 glossary"},
            },
        ],
        hint="Which screen stops Excel files today?",
    )

    assert find_reply_problems(good, make_record(), "") == []


def test_candidate_adds_updates_and_new_assumptions_once():
    minor = {
        "text": "Which format?",
        "material": False,
        "assumption": {"text": "Excel means .xlsx", "basis": "Rulebook v1 glossary"},
    }
    record = build_candidate(make_record(), reply(updates={"title": "  Add Excel  "}))
    record = build_candidate(record, reply(ambiguities=[minor]))
    record = build_candidate(record, reply(ambiguities=[minor]))

    assert record.title == "Add Excel"
    assert [a.text for a in record.assumptions] == ["Excel means .xlsx"]


def test_candidate_does_not_change_the_original():
    original = make_record()

    build_candidate(original, reply(updates={"title": "New"}))

    assert original.title == ""


# --- scope conflicts ---


def test_item_in_both_scopes_becomes_an_open_item():
    record = refresh_scope_conflicts(
        make_record(in_scope=["Hidden sheets"], out_of_scope=["hidden sheets "])
    )

    assert record.open_items == [
        'Scope conflict: "Hidden sheets" is both in scope and out of scope.'
    ]
    # Not fixed silently: both lists stay as they were.
    assert record.in_scope == ["Hidden sheets"]


def test_scope_conflict_clears_when_fixed():
    record = refresh_scope_conflicts(make_record(in_scope=["A"], out_of_scope=["A"]))

    record = refresh_scope_conflicts(record.model_copy(update={"out_of_scope": ["B"]}))

    assert record.open_items == []


def test_other_open_items_are_kept():
    record = make_record(open_items=["Help requested: Hidden sheets?"])

    assert refresh_scope_conflicts(record).open_items == ["Help requested: Hidden sheets?"]


# --- confirmation gate ---


def test_complete_record_passes_the_gate():
    assert confirmation_gate_problems(complete_record(), waiting_decisions=0) == []


def test_gate_lists_every_missing_item():
    problems = confirmation_gate_problems(make_record(answered_questions=[1, 3]), 1)

    assert problems == [
        "Question 2 has not been answered yet.",
        "Question 4 has not been answered yet.",
        "Title is empty.",
        "Objective is empty.",
        "Reason is empty.",
        "Current behaviour is empty.",
        "Expected behaviour is empty.",
        "Inputs is empty.",
        "Outputs is empty.",
        "The functional flow needs at least 2 steps (it has 0).",
        "At least 1 success criterion is needed.",
        "At least 1 negative scenario is needed.",
        "Decisions still waiting for your choice: 1.",
    ]


def test_gate_lists_open_items():
    record = complete_record(open_items=["Help requested: confirmation"])

    assert confirmation_gate_problems(record, 0) == ["Open item: Help requested: confirmation"]


def test_code_problem_names_the_line_to_rephrase():
    bad = reply(updates={"functional_flow": ["Open the file", "import the workbook"]})

    problems = find_reply_problems(bad, make_record(), "")

    assert problems == [
        'The reply contains code: "import the workbook". Describe the change in plain words '
        "only, and do not start a line with def, class, import or from ... import."
    ]


# --- acceptance criteria (Phase 2D, spec 1.3 to 1.5) ---


def ai_criterion(**parts):
    """A criterion as the AI writes it: no id."""
    values = {
        "kind": "failure",
        "given": "an empty workbook",
        "when": "it is uploaded",
        "then": "it is rejected with the standard empty-file error",
    }
    return values | parts


def with_criteria(*items):
    return reply(acceptance_criteria=list(items))


def test_the_app_numbers_the_criteria_in_the_order_given():
    """2D-1."""
    three = with_criteria(
        ai_criterion(given="a"), ai_criterion(given="b"), ai_criterion(given="c")
    )

    assert find_reply_problems(three, make_record(), "") == []
    record = build_candidate(make_record(), three)

    assert [c.id for c in record.acceptance_criteria] == ["AC-1", "AC-2", "AC-3"]
    assert [c.given for c in record.acceptance_criteria] == ["a", "b", "c"]


def test_a_new_list_replaces_the_old_one_and_renumbers():
    old = make_record(
        acceptance_criteria=[criterion("AC-1", "success"), criterion("AC-2", "failure")]
    )

    record = build_candidate(old, with_criteria(ai_criterion(given="only one")))

    assert [(c.id, c.given) for c in record.acceptance_criteria] == [("AC-1", "only one")]


@pytest.mark.parametrize("silent", [reply(), reply(acceptance_criteria=None)])
def test_a_reply_without_the_key_leaves_the_criteria_unchanged(silent):
    """2D-3."""
    old = make_record(acceptance_criteria=[criterion("AC-4", "success")])

    assert build_candidate(old, silent).acceptance_criteria == old.acceptance_criteria


def test_an_empty_list_clears_the_criteria():
    old = make_record(acceptance_criteria=[criterion("AC-1", "success")])

    assert build_candidate(old, reply(acceptance_criteria=[])).acceptance_criteria == []


def test_a_vague_then_is_refused_with_the_exact_note():
    """2D-2 (the retry itself is tested with the interpreter)."""
    vague = with_criteria(ai_criterion(), ai_criterion(then="It works."))

    assert find_reply_problems(vague, make_record(), "") == [
        "AC-2: the 'then' part must say something a person or a test can see, for example a "
        "message, a saved value, or a rejected file."
    ]


@pytest.mark.parametrize(
    "then",
    ["works", "Works correctly!", "as expected", "Success", "no error", "OK", "it succeeds"],
)
def test_vague_or_too_short_then_parts_are_refused(then):
    problems = find_reply_problems(with_criteria(ai_criterion(then=then)), make_record(), "")

    assert len(problems) == 1 and problems[0].startswith("AC-1: the 'then' part")


def test_a_two_word_then_is_refused_even_if_not_on_the_list():
    problems = find_reply_problems(with_criteria(ai_criterion(then="done fine")), make_record(), "")

    assert len(problems) == 1


def test_a_then_with_three_words_that_is_not_on_the_list_passes():
    ok = with_criteria(ai_criterion(then="a message is shown"))

    assert find_reply_problems(ok, make_record(), "") == []


def test_kind_and_lengths_are_checked_in_plain_words():
    bad = with_criteria(
        ai_criterion(kind="maybe"), ai_criterion(given=""), ai_criterion(when="w" * 301)
    )

    assert find_reply_problems(bad, make_record(), "") == [
        "AC-1: 'kind' must be success or failure.",
        "AC-2: 'given' must be 1 to 300 characters (it has 0).",
        "AC-3: 'when' must be 1 to 300 characters (it has 301).",
    ]


def test_more_than_12_criteria_are_refused():
    many = with_criteria(*[ai_criterion(given=f"case {n}") for n in range(13)])

    assert find_reply_problems(many, make_record(), "") == [
        "There are 13 acceptance criteria. The limit is 12."
    ]


def test_a_repeated_criterion_is_refused_ignoring_case_and_spaces():
    twice = with_criteria(ai_criterion(), ai_criterion(given="An  EMPTY workbook"))

    assert find_reply_problems(twice, make_record(), "") == [
        "AC-2 repeats AC-1: same given, when and then."
    ]


def test_code_and_invented_names_are_checked_in_all_three_parts():
    code = with_criteria(ai_criterion(when="import the workbook"))
    names = with_criteria(ai_criterion(then="upload.check_type rejects it with a message"))

    assert any("contains code" in p for p in find_reply_problems(code, make_record(), ""))
    assert find_reply_problems(names, make_record(), "") == [
        "AC-1 names 'upload.check_type', which the developer did not type. "
        "Describe the case in plain words instead of naming files or functions."
    ]
    assert find_reply_problems(names, make_record(), "I call upload.check_type today") == []


def test_an_id_from_the_ai_is_not_allowed():
    with pytest.raises(ValueError):
        reply(acceptance_criteria=[ai_criterion() | {"id": "AC-9"}])


def test_gate_asks_for_a_negative_scenario_when_only_success_exists():
    """2D-4."""
    record = complete_record(acceptance_criteria=[criterion("AC-1", "success")])

    assert confirmation_gate_problems(record, 0) == ["At least 1 negative scenario is needed."]


def test_gate_accepts_a_reason_instead_of_a_negative_scenario():
    """B2-13."""
    record = complete_record(
        acceptance_criteria=[criterion("AC-1", "success")], no_negative_reason="No inputs"
    )
    assert confirmation_gate_problems(record, 0) == []
    blank = record.model_copy(update={"no_negative_reason": "   "})
    assert confirmation_gate_problems(blank, 0) == ["At least 1 negative scenario is needed."]


def test_gate_asks_for_a_success_criterion_when_only_failure_exists():
    record = complete_record(acceptance_criteria=[criterion("AC-1", "failure")])

    assert confirmation_gate_problems(record, 0) == ["At least 1 success criterion is needed."]
