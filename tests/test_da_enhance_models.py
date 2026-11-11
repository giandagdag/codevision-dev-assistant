"""Phase 9, step 1: models, record fields, policy fields, catalog and settings."""

import pytest
from pydantic import ValidationError

from configs.da_config import ConfigError, load_settings
from pydantic_classes.da_enhance_models import (
    EnhanceState,
    FreshnessResult,
    PathFreshness,
    SafetyCase,
    step_label,
)
from pydantic_classes.da_models import (
    STATUS_CLARIFICATION,
    STATUS_DRAFT,
    STATUS_READY_FOR_REVIEW,
    StatusMoveError,
    check_status_move,
)
from pydantic_classes.da_request_record_models import RequestRecord
from pydantic_classes.da_rulebook_models import Rulebook

ENHANCE_FIELDS = {
    "enhance_name_top_k": 5,
    "enhance_meaning_top_k": 3,
    "enhance_find_max_rounds": 3,
    "enhance_max_keep_items": 8,
    "safety_net_max_tests": 20,
    "safety_net_max_attempts": 2,
    "safety_net_max_corrections": 2,
    "impact_max_callers": 30,
}


def test_9_47_a_rulebook_saved_before_phase_9_loads_with_starter_values_and_empty_catalog(
    seed_rulebook,
):
    old = seed_rulebook.model_dump(mode="json")
    for name in (*ENHANCE_FIELDS, "capabilities"):
        del old["policy"][name]

    loaded = Rulebook.model_validate(old)

    for name, value in ENHANCE_FIELDS.items():
        assert getattr(loaded.policy, name) == value
    assert loaded.policy.capabilities == []


def test_the_seed_has_three_made_up_capabilities(seed_rulebook):
    names = [item.name for item in seed_rulebook.policy.capabilities]

    assert names == ["Limits", "Reports", "Uploads"]
    assert all(item.named_senior for item in seed_rulebook.policy.capabilities)


@pytest.mark.parametrize(
    ("name", "bad"),
    [
        ("enhance_name_top_k", 0),
        ("enhance_find_max_rounds", 11),
        ("safety_net_max_tests", 51),
        ("safety_net_max_attempts", 0),
        ("impact_max_callers", 0),
    ],
)
def test_phase_9_numbers_outside_their_limits_are_refused(seed_rulebook, name, bad):
    data = seed_rulebook.model_dump(mode="json")
    data["policy"][name] = bad

    with pytest.raises(ValidationError):
        Rulebook.model_validate(data)


def test_a_capability_without_path_patterns_is_refused(seed_rulebook):
    data = seed_rulebook.model_dump(mode="json")
    data["policy"]["capabilities"][0]["path_patterns"] = []

    with pytest.raises(ValidationError):
        Rulebook.model_validate(data)


def test_9_22_a_record_saved_before_phase_9_loads_with_empty_new_fields():
    record = RequestRecord.model_validate({"request_id": "CVDA-2026-0001", "rulebook_version": 1})

    assert record.kind == "new"
    assert record.targets == []
    assert record.today == ""
    assert record.must_not_change == []
    assert record.functions_in_scope == []
    assert record.freshness.override == ""


def test_a_record_keeps_the_new_fields_through_a_round_trip():
    record = RequestRecord.model_validate(
        {
            "request_id": "CVDA-2026-0001",
            "rulebook_version": 1,
            "kind": "fix",
            "targets": ["src/agents/limits_expiry_report.py"],
            "must_not_change": [{"id": "NC-1", "text": "Column order"}],
            "freshness": {"result": "differs", "override": "intentional"},
        }
    )

    again = RequestRecord.model_validate(record.model_dump(mode="json"))

    assert again == record


def test_a_bad_must_not_change_id_is_refused():
    with pytest.raises(ValidationError):
        RequestRecord.model_validate(
            {
                "request_id": "CVDA-2026-0001",
                "rulebook_version": 1,
                "must_not_change": [{"id": "NC-0", "text": "x"}],
            }
        )


def test_step_labels_follow_the_spec_table():
    assert step_label("e_find") == "FIND THE PROGRAM"
    assert step_label("e_stale") == "FRESHNESS CHECK"
    assert step_label("e_fresh") == "PROGRAM CONFIRMED"
    assert step_label("s_review") == "SAFETY NET READY"
    # The accepted step shows the normal status pill.
    assert step_label("s_accepted") == ""


def test_the_e_steps_work_with_the_draft_status():
    """Q-c: no new status. A new request sits at DRAFT, which can move on to Understand."""
    check_status_move(STATUS_DRAFT, STATUS_CLARIFICATION)
    with pytest.raises(StatusMoveError):
        check_status_move(STATUS_DRAFT, STATUS_READY_FOR_REVIEW)


def test_enhance_state_starts_at_find_with_revision_one():
    state = EnhanceState(request_id="CVDA-2026-0001")

    assert (state.step, state.revision, state.find_rounds_used) == ("e_find", 1, 0)


def test_an_unknown_step_is_refused():
    with pytest.raises(ValidationError):
        EnhanceState(request_id="CVDA-2026-0001", step="e_nowhere")


def test_safety_case_ids_must_look_like_s_numbers():
    SafetyCase(id="S-1", today_behaviour="Rows sorted by date", function="format_rows")
    with pytest.raises(ValidationError):
        SafetyCase(id="T-1", today_behaviour="x", function="f")


def test_freshness_all_equal_needs_at_least_one_path():
    equal = PathFreshness(path="a.py", state="equal")
    differs = PathFreshness(path="b.py", state="differs")

    assert FreshnessResult(paths=[equal]).all_equal
    assert not FreshnessResult(paths=[equal, differs]).all_equal
    assert not FreshnessResult().all_equal


def test_settings_default_to_the_fake_main_source():
    settings = load_settings(env_file=None, environ={})

    assert settings.main_source == "fake"
    assert settings.fake_main_dir.as_posix().endswith("src/data/da_fake_main")


def test_settings_accept_the_bitbucket_placeholder_and_refuse_other_words():
    assert load_settings(env_file=None, environ={"DA_MAIN_SOURCE": "Bitbucket"}).main_source == (
        "bitbucket"
    )
    with pytest.raises(ConfigError, match="DA_MAIN_SOURCE"):
        load_settings(env_file=None, environ={"DA_MAIN_SOURCE": "ftp"})
