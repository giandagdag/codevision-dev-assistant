from pathlib import Path

import pytest
from pydantic import ValidationError

from db_table_functions.db_tbl_da_rulebook import SEED_RULEBOOK_FILE, load_rulebook_file
from pydantic_classes.da_rulebook_models import (
    ESCALATION_TRIGGER_NAMES,
    RETIRED_POLICY_FIELDS,
    Charter,
    EscalationTrigger,
    GlossaryEntry,
    Rule,
    Rulebook,
    check_charter_size,
    find_rulebook_problems,
    without_retired_fields,
)

# Fix G5 P5 added the third zone to both seeds and to the defaults.
ZONE_NAMES = ["Security", "Login", "Destructive data change"]


def with_policy(rulebook: Rulebook, **changes) -> Rulebook:
    return rulebook.model_copy(update={"policy": rulebook.policy.model_copy(update=changes)})


def judgement_rule(number: int) -> Rule:
    return Rule(
        rule_id=f"CV-PY-{number:03d}",
        title=f"Made-up rule {number}",
        kind="judgement",
        tags=["general"],
        severity="fyi",
        why="Example only.",
        good_example="good()",
        bad_example="bad()",
        source="Written by Admin",
    )


def charter_of_length(characters: int) -> Charter:
    return Charter(
        purpose="x" * characters,
        in_scope=[],
        out_of_scope=[],
        architecture_principles=[],
        constraints=[],
        glossary=[],
    )


# --- The seed file ---


def test_seed_rulebook_has_no_problems(seed_rulebook):
    assert find_rulebook_problems(seed_rulebook) == []


def test_seed_rulebook_has_the_contents_the_spec_asks_for(seed_rulebook):
    kinds = [rule.kind for rule in seed_rulebook.rules]
    policy = seed_rulebook.policy

    assert kinds.count("judgement") == 5
    assert kinds.count("ui_convention") == 2
    assert [zone.name for zone in policy.flag_review_zones] == ZONE_NAMES
    # 11-27: no retired field; five triggers, all on; the new fields hold their defaults.
    assert policy.default_level is None
    assert policy.max_level is None
    assert policy.max_review_rounds is None
    assert policy.never_generate_zones == []
    assert [trigger.name for trigger in policy.escalation_triggers] == list(
        ESCALATION_TRIGGER_NAMES
    )
    assert all(trigger.on for trigger in policy.escalation_triggers)
    assert (policy.generator_model, policy.tester_model) == ("", "")
    assert policy.admin_unassigned_stale_days == 14


def test_seed_file_text_has_no_retired_field():
    text = SEED_RULEBOOK_FILE.read_text(encoding="utf-8")

    for name in RETIRED_POLICY_FIELDS:
        assert f'"{name}"' not in text


def test_seed_charter_is_green(seed_rulebook):
    assert check_charter_size(seed_rulebook.charter).status == "green"


# --- Rule R3 checks, one at a time ---


def test_retired_fields_are_no_longer_checked(seed_rulebook):
    # Old values (a locked level, nine review rounds) are carried but never complained about.
    rulebook = with_policy(
        seed_rulebook, default_level="L3", max_level="L1", max_review_rounds=9
    )

    assert find_rulebook_problems(rulebook) == []


def test_ten_judgement_rules_are_allowed(seed_rulebook):
    rulebook = seed_rulebook.model_copy(
        update={"rules": [judgement_rule(n) for n in range(1, 11)]}
    )

    assert find_rulebook_problems(rulebook) == []


def test_eleven_judgement_rules_is_a_problem(seed_rulebook):
    rulebook = seed_rulebook.model_copy(
        update={"rules": [judgement_rule(n) for n in range(1, 12)]}
    )

    assert find_rulebook_problems(rulebook) == [
        "There are 11 judgement rules. The pilot allows at most 10."
    ]


def test_ui_conventions_do_not_count_toward_the_judgement_cap(seed_rulebook):
    ui_rules = [rule for rule in seed_rulebook.rules if rule.kind == "ui_convention"]
    rules = [judgement_rule(n) for n in range(1, 11)] + ui_rules

    assert find_rulebook_problems(seed_rulebook.model_copy(update={"rules": rules})) == []


def test_missing_trigger_is_a_problem(seed_rulebook):
    # Built by hand: a loaded rulebook always has five, but a hand-built one may not.
    two = seed_rulebook.policy.escalation_triggers[:2]

    problems = find_rulebook_problems(with_policy(seed_rulebook, escalation_triggers=two))

    assert len(problems) == 1
    assert "must be exactly these 5" in problems[0]


def test_two_zones_with_the_same_name_are_a_problem(seed_rulebook):
    zones = seed_rulebook.policy.flag_review_zones
    twin = zones[0].model_copy(update={"name": zones[0].name.upper()})

    problems = find_rulebook_problems(
        with_policy(seed_rulebook, flag_review_zones=[*zones, twin])
    )

    assert problems == [f"Flag-for-review zone '{zones[0].name.upper()}' is listed more than once."]


def test_unknown_or_repeated_trigger_is_a_problem(seed_rulebook):
    triggers = [
        *seed_rulebook.policy.escalation_triggers,
        EscalationTrigger(name="out_of_scope", on=False),
    ]

    problems = find_rulebook_problems(with_policy(seed_rulebook, escalation_triggers=triggers))

    assert len(problems) == 1
    assert "each listed once" in problems[0]


def test_triggers_may_be_switched_off(seed_rulebook):
    triggers = [
        trigger.model_copy(update={"on": False})
        for trigger in seed_rulebook.policy.escalation_triggers
    ]

    assert find_rulebook_problems(with_policy(seed_rulebook, escalation_triggers=triggers)) == []


def test_two_rules_sharing_an_id_is_a_problem(seed_rulebook):
    rules = [*seed_rulebook.rules, seed_rulebook.rules[0]]

    problems = find_rulebook_problems(seed_rulebook.model_copy(update={"rules": rules}))

    assert problems == ["Rule ID CV-PY-001 is used by more than one rule."]


def test_rule_id_must_match_its_kind(seed_rulebook):
    wrong = seed_rulebook.rules[0].model_copy(update={"kind": "ui_convention"})
    rules = [wrong, *seed_rulebook.rules[1:]]

    problems = find_rulebook_problems(seed_rulebook.model_copy(update={"rules": rules}))

    assert problems == [
        "Rule CV-PY-001 is a ui_convention rule, so its ID must start with CV-UI."
    ]


def test_every_problem_is_listed_together(seed_rulebook):
    # 11-7: two problems at once, both listed.
    rules = [judgement_rule(n) for n in range(1, 12)]
    rulebook = with_policy(
        seed_rulebook.model_copy(update={"rules": rules}),
        escalation_triggers=seed_rulebook.policy.escalation_triggers[:4],
    )

    problems = find_rulebook_problems(rulebook)

    assert len(problems) == 2
    assert any("11 judgement rules" in problem for problem in problems)
    assert any("must be exactly these 5" in problem for problem in problems)


# --- Phase 11: old versions, trigger mapping, retired fields ---


def old_shape_rulebook() -> Rulebook:
    return load_rulebook_file(Path(__file__).parent / "data" / "da_rulebook_seed_phase1.json")


def test_old_shape_version_loads_with_retired_fields_kept_but_unshown():
    policy = old_shape_rulebook().policy

    # The retired values are still there for the record; they are just not used or shown.
    assert (policy.default_level, policy.max_review_rounds) == ("L2", 3)
    assert [zone.name for zone in policy.never_generate_zones] == ["Security", "Login"]


def test_old_shape_triggers_are_mapped_to_five_and_missing_ones_are_on():
    triggers = {t.name: t.on for t in old_shape_rulebook().policy.escalation_triggers}

    assert triggers == {
        "cap_hit_twice": True,
        "out_of_scope": False,
        "dispute": True,
        "tester_unable_twice": True,
        "get_help": True,
    }


def test_old_shape_gets_the_phase_4_to_9_defaults():
    policy = old_shape_rulebook().policy

    assert policy.build_max_rounds == 3
    assert policy.max_files == 5
    assert policy.capabilities == []
    assert [zone.name for zone in policy.flag_review_zones] == ZONE_NAMES
    assert find_rulebook_problems(old_shape_rulebook()) == []


def test_saved_json_leaves_out_empty_retired_fields(seed_rulebook):
    policy_json = seed_rulebook.model_dump(mode="json")["policy"]

    for name in RETIRED_POLICY_FIELDS:
        assert name not in policy_json


def test_without_retired_fields_empties_an_old_shape_rulebook():
    clean = without_retired_fields(old_shape_rulebook())

    policy_json = clean.model_dump(mode="json")["policy"]
    assert all(name not in policy_json for name in RETIRED_POLICY_FIELDS)
    assert len(policy_json["escalation_triggers"]) == 5


def test_build_max_rounds_9_is_refused_with_its_bound(seed_rulebook):
    # 11-19: the bound (1 to 5) comes from the model.
    data = seed_rulebook.model_dump(mode="json")
    data["policy"]["build_max_rounds"] = 9

    with pytest.raises(ValidationError, match="less than or equal to 5"):
        Rulebook.model_validate(data)


# --- Shape checks (Pydantic) ---


def test_unknown_severity_is_refused():
    with pytest.raises(ValidationError):
        Rule.model_validate({**judgement_rule(1).model_dump(), "severity": "urgent"})


def test_unknown_rule_kind_is_refused():
    with pytest.raises(ValidationError):
        Rule.model_validate({**judgement_rule(1).model_dump(), "kind": "style"})


def test_badly_formed_rule_id_is_refused():
    with pytest.raises(ValidationError):
        Rule.model_validate({**judgement_rule(1).model_dump(), "rule_id": "PY-1"})


def test_misspelt_field_is_refused_not_dropped():
    with pytest.raises(ValidationError):
        GlossaryEntry.model_validate({"term": "Request", "meaning": "A change", "meening": "x"})


# --- Charter size check ---


@pytest.mark.parametrize(
    ("characters", "percent", "status"),
    [
        (4740, 79.0, "green"),
        (4800, 80.0, "amber"),
        (6000, 100.0, "amber"),
        (6060, 101.0, "red"),
    ],
)
def test_charter_size_status_at_the_boundaries(characters, percent, status):
    size = check_charter_size(charter_of_length(characters))

    assert (size.characters, size.percent, size.status) == (characters, percent, status)


def test_charter_size_counts_text_in_every_section():
    charter = Charter(
        purpose="ab",
        in_scope=["cde"],
        out_of_scope=["f"],
        architecture_principles=["gh"],
        constraints=["i"],
        glossary=[GlossaryEntry(term="jk", meaning="lmn")],
    )

    # 2 + 3 + 1 + 2 + 1 + 2 + 3: only the written text, no brackets or field names.
    assert check_charter_size(charter).characters == 14


# --- Phase 4 policy fields (spec section 7, row 4-27) ---


def test_seed_has_the_phase_4_policy_values(seed_rulebook):
    policy = seed_rulebook.policy

    assert "src/agents" in policy.allowed_folders
    assert "src/web/web_server.py" in policy.protected_files
    assert "openpyxl" in policy.approved_libraries
    assert (policy.max_files, policy.max_design_choices) == (5, 3)
    assert [zone.name for zone in policy.flag_review_zones] == ZONE_NAMES


def test_seed_has_the_phase_5_policy_values(seed_rulebook):
    policy = seed_rulebook.policy

    assert policy.workspace_markers == ["src/web", "src/callbacks"]
    assert policy.workspace_max_file_kb == 512


def test_a_rulebook_saved_before_phase_5_loads_with_the_starter_values(seed_rulebook):
    """Test 5-26."""
    old = seed_rulebook.model_dump(mode="json")
    del old["policy"]["workspace_markers"]
    del old["policy"]["workspace_max_file_kb"]

    loaded = Rulebook.model_validate(old)

    assert loaded.policy.workspace_markers == ["src/web", "src/callbacks"]
    assert loaded.policy.workspace_max_file_kb == 512


# --- Phase 6 policy fields (spec section 11, row 6-31) ---

PHASE_6_FIELDS = (
    "build_max_rounds",
    "build_test_timeout_seconds",
    "build_max_prompt_chars",
    "build_max_parallel",
    "build_blocked_imports",
    "build_sandbox_exclude",
)


def test_seed_has_the_phase_6_policy_values(seed_rulebook):
    policy = seed_rulebook.policy

    assert (policy.build_max_rounds, policy.build_test_timeout_seconds) == (3, 60)
    assert (policy.build_max_prompt_chars, policy.build_max_parallel) == (60000, 2)
    assert "requests" in policy.build_blocked_imports
    assert ".env" in policy.build_sandbox_exclude


def test_a_rulebook_saved_before_phase_6_loads_with_the_starter_values(seed_rulebook):
    """Test 6-31."""
    old = seed_rulebook.model_dump(mode="json")
    for name in PHASE_6_FIELDS:
        del old["policy"][name]

    loaded = Rulebook.model_validate(old)

    assert loaded.policy == seed_rulebook.policy


def test_build_reuses_the_phase_4_lists_instead_of_new_copies(seed_rulebook):
    """Decision D-M: no second protected-file or approved-library list exists."""
    fields = set(type(seed_rulebook.policy).model_fields)

    assert "build_protected_files" not in fields
    assert "build_approved_libraries" not in fields


@pytest.mark.parametrize(
    ("name", "bad"),
    [
        ("build_max_rounds", 0),
        ("build_max_rounds", 6),
        ("build_test_timeout_seconds", 0),
        ("build_test_timeout_seconds", 601),
        ("build_max_prompt_chars", 999),
        ("build_max_parallel", 0),
    ],
)
def test_phase_6_numbers_outside_their_limits_are_refused(seed_rulebook, name, bad):
    data = seed_rulebook.model_dump(mode="json")
    data["policy"][name] = bad

    with pytest.raises(ValidationError):
        Rulebook.model_validate(data)


def test_7_32_a_rulebook_saved_before_phase_7_loads_with_the_starter_values(seed_rulebook):
    old = seed_rulebook.model_dump(mode="json")
    for name in ("tester_max_prompt_chars", "tester_max_attempts", "tester_quote_window"):
        del old["policy"][name]

    loaded = Rulebook.model_validate(old)

    assert loaded.policy.tester_max_prompt_chars == 60000
    assert loaded.policy.tester_max_attempts == 2
    assert loaded.policy.tester_quote_window == 2
    assert loaded.policy == seed_rulebook.policy


@pytest.mark.parametrize(
    ("name", "bad"),
    [("tester_max_prompt_chars", 999), ("tester_max_attempts", 0), ("tester_quote_window", 11)],
)
def test_7_tester_numbers_outside_their_limits_are_refused(seed_rulebook, name, bad):
    data = seed_rulebook.model_dump(mode="json")
    data["policy"][name] = bad

    with pytest.raises(ValidationError):
        Rulebook.model_validate(data)


REFINE_FIELDS = {
    "refine_max_per_request": 5,
    "refine_lane_max_attempts": 2,
    "refine_repro_max_attempts": 2,
    "refine_conflict_context_lines": 3,
}


def test_8_39_a_rulebook_saved_before_phase_8_loads_with_the_starter_values(seed_rulebook):
    old = seed_rulebook.model_dump(mode="json")
    for name in REFINE_FIELDS:
        del old["policy"][name]

    loaded = Rulebook.model_validate(old)

    for name, value in REFINE_FIELDS.items():
        assert getattr(loaded.policy, name) == value
    assert loaded.policy == seed_rulebook.policy


@pytest.mark.parametrize(
    ("name", "bad"),
    [
        ("refine_max_per_request", 0),
        ("refine_lane_max_attempts", 6),
        ("refine_repro_max_attempts", 0),
        ("refine_conflict_context_lines", 11),
    ],
)
def test_8_refine_numbers_outside_their_limits_are_refused(seed_rulebook, name, bad):
    data = seed_rulebook.model_dump(mode="json")
    data["policy"][name] = bad

    with pytest.raises(ValidationError):
        Rulebook.model_validate(data)


def test_a_rulebook_saved_before_phase_4_loads_with_the_starter_values(seed_rulebook):
    old = seed_rulebook.model_dump(mode="json")
    for name in (
        "allowed_folders",
        "new_file_name_pattern",
        "protected_files",
        "approved_libraries",
        "max_files",
        "max_design_choices",
        "flag_review_zones",
    ):
        del old["policy"][name]

    loaded = Rulebook.model_validate(old)

    assert loaded.policy == seed_rulebook.policy


def test_a_broken_file_name_pattern_is_refused(seed_rulebook):
    data = seed_rulebook.model_dump(mode="json")
    data["policy"]["new_file_name_pattern"] = "([unclosed"

    with pytest.raises(ValidationError, match="regular expression"):
        Rulebook.model_validate(data)


# --- Phase 6 fixes batch, item U6: the AI question limit lives in the policy ---


def test_seed_has_the_ai_question_limit(seed_rulebook):
    assert seed_rulebook.policy.max_material_decisions == 8  # fix 11-1: new seed default


def test_a_rulebook_saved_before_the_limit_existed_loads_with_8(seed_rulebook):
    old = seed_rulebook.model_dump(mode="json")
    del old["policy"]["max_material_decisions"]

    loaded = Rulebook.model_validate(old)

    # B2-8: the model default is now 8, so a work database whose rulebook has no key runs with 8.
    assert loaded.policy.max_material_decisions == 8
    assert loaded.policy == seed_rulebook.policy


@pytest.mark.parametrize("value", [1, 15])
def test_ai_question_limit_accepts_1_to_15(seed_rulebook, value):
    data = seed_rulebook.model_dump(mode="json")
    data["policy"]["max_material_decisions"] = value

    assert Rulebook.model_validate(data).policy.max_material_decisions == value


@pytest.mark.parametrize("value", [0, 16, -1])
def test_ai_question_limit_outside_1_to_15_is_refused(seed_rulebook, value):
    data = seed_rulebook.model_dump(mode="json")
    data["policy"]["max_material_decisions"] = value

    with pytest.raises(ValidationError):
        Rulebook.model_validate(data)
