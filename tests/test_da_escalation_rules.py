"""Phase 10 step 6: escalation table, routing, senior access and triggers (spec sections 7 to 9)."""

import logging
from datetime import UTC, datetime

import pytest

from agents import da_escalation_triggers as triggers_module
from agents.da_escalation_routing import matches_senior, route_for
from agents.da_escalation_triggers import (
    add_reason,
    cap_hit_twice,
    dispute,
    get_help,
    out_of_scope_approach,
    out_of_scope_understand,
    status_blocks_triggers,
)
from agents.da_senior_access import catalog_senior_labels, is_senior
from configs.da_config import ConfigError, load_settings
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_escalation import (
    EscalationAlreadyOpenError,
    insert_escalation,
    last_fired_count,
    read_escalations,
    read_open_escalation,
    update_escalation,
)
from db_table_functions.db_tbl_da_requests import create_request
from db_table_functions.db_tbl_da_understand import StaleRevisionError
from pydantic_classes.da_escalation_models import UNASSIGNED, EscalationRow, Guidance
from pydantic_classes.da_rulebook_models import Capability, EscalationTrigger

NOW = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
ALL_ON = [
    EscalationTrigger(name=name, on=True)
    for name in ("cap_hit_twice", "out_of_scope", "dispute", "tester_unable_twice", "get_help")
]
ALL_OFF = [EscalationTrigger(name=item.name, on=False) for item in ALL_ON]


def caps() -> list[Capability]:
    return [
        Capability(
            name="Limits",
            description="d",
            named_senior="lim-lead",
            backup_senior="lim-deputy",
            path_patterns=["*limits*"],
        ),
        # An old saved version can hold a blank named senior (model_copy skips the check).
        Capability(
            name="Reports",
            description="d",
            named_senior="x",
            backup_senior="rep-deputy",
            path_patterns=["*report*"],
        ).model_copy(update={"named_senior": ""}),
        Capability(
            name="Orphans", description="d", named_senior="x", path_patterns=["*orphan*"]
        ).model_copy(update={"named_senior": ""}),
    ]


# --- the table ---


@pytest.fixture
def request_id(db_path, published_rulebook):
    created = create_request(db_path, "Add a limit check", "dev-home-01", NOW).request_id
    with open_db(db_path) as conn:
        ensure_build_tables(conn)  # also creates the escalations table
    return created


def new_row(request_id: str, **changes) -> EscalationRow:
    values = {
        "request_id": request_id,
        "from_status": "NOT_PASSING",
        "triggers": ["cap_hit_twice"],
        "reasons": ["Round cap hit twice: builds 1 and 2"],
        "fired_count": 2,
    }
    return EscalationRow(**{**values, **changes})


def test_a_row_round_trips_and_has_its_own_revision(db_path, request_id):
    with open_db(db_path) as conn:
        conn.execute("BEGIN")
        saved = insert_escalation(conn, new_row(request_id, senior_label="lim-lead"), NOW)
        again = read_open_escalation(conn, request_id)

    assert saved.escalation_id >= 1
    assert again == saved
    assert again.revision == 1
    assert again.outcome == "open"


def test_a_second_open_row_for_one_request_is_refused(db_path, request_id):
    with open_db(db_path) as conn:
        conn.execute("BEGIN")
        insert_escalation(conn, new_row(request_id), NOW)
        with pytest.raises(EscalationAlreadyOpenError):
            insert_escalation(conn, new_row(request_id), NOW)


def test_a_stale_save_is_refused_and_close_allows_a_new_open_row(db_path, request_id):
    with open_db(db_path) as conn:
        conn.execute("BEGIN")
        first = insert_escalation(conn, new_row(request_id), NOW)
        taken = update_escalation(
            conn, first.model_copy(update={"taken_over_by": "lim-lead"}), 1, NOW
        )
        assert taken.revision == 2
        with pytest.raises(StaleRevisionError):
            update_escalation(conn, first, 1, NOW)  # revision 1 is old now
        closed = taken.model_copy(update={"outcome": "returned", "close_note": "Looked at it."})
        done = update_escalation(conn, closed, 2, NOW)
        assert done.closed_at == NOW
        assert read_open_escalation(conn, request_id) is None
        insert_escalation(conn, new_row(request_id), NOW)  # allowed again
        assert [r.outcome for r in read_escalations(conn, request_id)] == ["returned", "open"]


def test_guidance_is_kept_with_its_used_in_mark(db_path, request_id):
    note = Guidance(text="Use the shared helper.", sent_by="lim-lead", sent_at=NOW)
    with open_db(db_path) as conn:
        conn.execute("BEGIN")
        saved = insert_escalation(conn, new_row(request_id, guidance=[note]), NOW)
        again = read_open_escalation(conn, request_id)

    assert again.guidance == saved.guidance
    assert again.guidance[0].used_in == ""


def test_last_fired_count_can_leave_out_returned_rows(db_path, request_id):
    with open_db(db_path) as conn:
        conn.execute("BEGIN")
        row = insert_escalation(conn, new_row(request_id), NOW)
        assert last_fired_count(conn, request_id, "cap_hit_twice") == 2
        update_escalation(conn, row.model_copy(update={"outcome": "returned"}), 1, NOW)
        assert last_fired_count(conn, request_id, "cap_hit_twice") == 2
        assert last_fired_count(conn, request_id, "cap_hit_twice", ("open", "abandoned")) == 0
        assert last_fired_count(conn, request_id, "get_help") == 0


# --- routing (10-30, 10-31) ---


def test_an_enhancement_goes_to_its_capability_senior_and_backup():
    route = route_for(caps(), "Limits", [])

    assert (route.capability, route.senior_label, route.backup_label) == (
        "Limits",
        "lim-lead",
        "lim-deputy",
    )


def test_a_new_request_uses_the_first_planned_file_and_lists_the_others():
    route = route_for(caps(), "", ["src/a/limits_check.py", "src/a/report_x.py", "src/a/z.py"])

    assert route.capability == "Limits"
    assert route.other_capabilities == ["Reports"]


def test_no_named_senior_falls_back_to_the_backup_and_no_one_is_unassigned():
    backup = route_for(caps(), "Reports", [])
    nobody = route_for(caps(), "Orphans", [])

    assert (backup.senior_label, backup.backup_label) == ("rep-deputy", "")
    assert nobody.senior_label == UNASSIGNED
    assert nobody.capability == "Orphans"
    assert route_for(caps(), "", ["src/a/z.py"]).senior_label == UNASSIGNED
    assert route_for(caps(), "", []).capability == ""


def test_unassigned_rows_show_to_every_senior_and_others_only_to_their_own():
    assert matches_senior(UNASSIGNED, "", "anyone")
    assert matches_senior("lim-lead", "lim-deputy", "lim-deputy")
    assert not matches_senior("lim-lead", "lim-deputy", "other")


# --- senior access (10-33, rules part) ---


def settings_with(**env):
    return load_settings(env_file=None, environ={"DA_LLM_PROVIDER": "fake", **env})


def test_env_list_and_catalog_names_let_a_user_in(db_path, published_rulebook):
    settings = settings_with(DA_DB_PATH=str(db_path), DA_SENIOR_IDS="boss-01, boss-02")
    labels = catalog_senior_labels(settings)

    assert is_senior(settings, "boss-02")
    assert labels  # the made-up starter catalog names seniors
    assert is_senior(settings, sorted(labels)[0])
    assert not is_senior(settings, "stranger")
    assert not is_senior(settings, "")


def test_codevision_placeholder_refuses_everybody_and_logs(caplog):
    settings = settings_with(DA_SENIOR_SOURCE="codevision", DA_SENIOR_IDS="boss-01")

    with caplog.at_level(logging.WARNING):
        assert not is_senior(settings, "boss-01")

    assert "Senior access is not configured yet" in caplog.text


def test_unknown_senior_source_is_refused_at_start():
    with pytest.raises(ConfigError, match="DA_SENIOR_SOURCE is 'ldap'"):
        settings_with(DA_SENIOR_SOURCE="ldap")


# --- triggers (10-20 to 10-29, rules part) ---


def test_cap_hit_twice_fires_at_two_with_the_build_numbers():
    decision = cap_hit_twice(ALL_ON, 2, 5, 0)

    assert decision.fire
    assert decision.reason == "Round cap hit twice: builds 4 and 5"
    assert decision.count == 2
    assert not cap_hit_twice(ALL_ON, 1, 5, 0).fire


def test_cap_hit_twice_does_not_fire_again_at_three_but_does_after_a_reset():
    assert not cap_hit_twice(ALL_ON, 3, 6, 2).fire  # fired at 2 already (X2)
    assert cap_hit_twice(ALL_ON, 2, 9, 0).fire  # count reset by Return, returned row left out
    assert not cap_hit_twice(ALL_ON, 1, 8, 0).fire  # 10-22: only one NOT_PASSING since


def test_a_switched_off_trigger_reports_it_instead_of_firing():
    decision = cap_hit_twice(ALL_OFF, 2, 3, 0)

    assert decision.switched_off
    assert not decision.fire
    assert not cap_hit_twice(ALL_OFF, 1, 3, 0).switched_off  # nothing to report, condition unmet


def test_out_of_scope_from_the_understand_record():
    items = ["Something else", 'Scope conflict: "export to PDF" is both in scope and out of scope.']
    decision = out_of_scope_understand(ALL_ON, items)

    assert decision.fire
    assert decision.reason.startswith('Out of scope: "export to PDF"')
    assert not out_of_scope_understand(ALL_ON, ["Something else"]).fire
    assert out_of_scope_understand(ALL_OFF, items).switched_off


def test_out_of_scope_from_the_approach_needs_the_change_cap_used_up():
    paths = ["src/other/secret.py"]

    assert not out_of_scope_approach(ALL_ON, paths, 2, 3).fire
    assert not out_of_scope_approach(ALL_ON, [], 3, 3).fire
    decision = out_of_scope_approach(ALL_ON, paths, 3, 3)
    assert decision.fire
    assert decision.reason == "Out of scope: src/other/secret.py"
    assert out_of_scope_approach(ALL_OFF, paths, 3, 3).switched_off


def test_dispute_and_get_help_use_their_texts_and_switches():
    assert dispute(ALL_ON, "F-2").reason == "Disputed Must fix: F-2"
    assert dispute(ALL_OFF, "F-2").switched_off
    assert get_help(ALL_ON, "Build", "building").reason == "Escalated in Build: building"
    assert get_help(ALL_OFF, "Build", "building").switched_off


def test_tester_unable_twice_fires_at_two_not_three_and_again_at_four():
    first = triggers_module.tester_unable_twice(ALL_ON, [1, 3], 0)

    assert first.fire
    assert first.reason == "Tester unable to assess twice: reviews 1 and 3"
    assert not triggers_module.tester_unable_twice(ALL_ON, [1], 0).fire
    assert not triggers_module.tester_unable_twice(ALL_ON, [1, 3, 4], 2).fire
    assert triggers_module.tester_unable_twice(ALL_ON, [1, 3, 4, 6], 2).fire
    assert triggers_module.tester_unable_twice(ALL_OFF, [1, 3], 0).switched_off


def test_a_second_trigger_adds_a_reason_instead_of_a_row():
    row = new_row("CVDA-2026-0001")
    more = add_reason(row, "get_help", "Escalated in Build: building")
    same = add_reason(more, "get_help", "Escalated in Build: building")

    assert more.triggers == ["cap_hit_twice", "get_help"]
    assert len(more.reasons) == 2
    assert same == more


def test_no_trigger_fires_at_handed_off_or_escalated():
    assert status_blocks_triggers("HANDED_OFF")
    assert status_blocks_triggers("ESCALATION_REQUIRED")
    assert not status_blocks_triggers("NOT_PASSING")
