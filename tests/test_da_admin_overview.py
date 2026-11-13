"""Phase 11c step 2: area status, Needs attention and last changed (spec 4 and 5; tests 11-11,
11-20, 11-28, 11-32), on made-up rulebooks."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agents.da_admin_diff import (
    AREA_BUILD,
    AREA_CATALOG,
    AREA_CHARTER,
    AREA_CODING,
    TimelineRow,
)
from agents.da_admin_forms import save_from_form
from agents.da_admin_overview import (
    AREA_ORDER,
    LEVEL_INFO,
    LEVEL_RED,
    NEVER_CHANGED,
    NOTHING_TO_DO,
    STATUS_AMBER,
    STATUS_GREEN,
    STATUS_RED,
    area_status,
    attention_items,
    build_overview,
    carried_retired_fields,
    last_changed,
    overview_from,
)
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_build import ensure_build_tables
from db_table_functions.db_tbl_da_enhance import add_unassigned
from db_table_functions.db_tbl_da_requests import create_request
from db_table_functions.db_tbl_da_rulebook import get_active_version, load_rulebook_file
from pydantic_classes.da_rulebook_models import (
    Capability,
    Rule,
    Rulebook,
    RulebookVersion,
    check_charter_size,
)

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
OLD_SHAPE = Path(__file__).parent / "data" / "da_rulebook_seed_phase1.json"


def calm(seed: Rulebook) -> Rulebook:
    """The seed made quiet: every capability has a backup, both models named, all triggers on."""
    policy = seed.policy.model_copy(
        update={
            "capabilities": [
                c.model_copy(update={"backup_senior": "backup-0001"})
                for c in seed.policy.capabilities
            ],
            "generator_model": "made-up-generator",
            "tester_model": "made-up-tester",
        }
    )
    return seed.model_copy(update={"policy": policy})


def with_judgement_rules(rulebook: Rulebook, count: int) -> Rulebook:
    template = next(r for r in rulebook.rules if r.kind == "judgement")
    others = [r for r in rulebook.rules if r.kind != "judgement"]
    rules = [
        Rule.model_validate(
            {**template.model_dump(), "rule_id": f"CV-PY-{number:03d}", "title": f"Rule {number}"}
        )
        for number in range(1, count + 1)
    ]
    return rulebook.model_copy(update={"rules": [*others, *rules]})


def with_charter_percent(rulebook: Rulebook, percent: float) -> Rulebook:
    charter = rulebook.charter
    others = check_charter_size(charter).characters - len(charter.purpose)
    target = int(6000 * percent / 100) - others
    return rulebook.model_copy(
        update={"charter": charter.model_copy(update={"purpose": "x" * target})}
    )


def texts(items):
    return [item.text for item in items]


def test_a_calm_rulebook_has_nothing_to_attend_to(seed_rulebook):
    rulebook = calm(seed_rulebook)

    assert attention_items(rulebook, [], NOW) == []
    overview = overview_from(_version(rulebook), [], [], NOW)
    assert [row.status for row in overview.areas] == [STATUS_GREEN] * 6
    assert NOTHING_TO_DO == "Nothing needs attention."


def test_the_overview_has_one_row_per_area_in_tab_order(seed_rulebook):
    overview = overview_from(_version(calm(seed_rulebook)), [], [], NOW)

    assert [row.area for row in overview.areas] == list(AREA_ORDER)
    assert len(overview.areas) == 6
    assert all(row.last_changed == NEVER_CHANGED for row in overview.areas)
    summaries = {row.area: row.summary for row in overview.areas}
    assert "capabilities, 0 Unassigned" in summaries[AREA_CATALOG]


def test_11_11_a_charter_at_81_percent_is_amber_with_the_percent(seed_rulebook):
    rulebook = with_charter_percent(calm(seed_rulebook), 81)

    [item] = attention_items(rulebook, [], NOW)

    assert (item.area, item.level) == (AREA_CHARTER, LEVEL_INFO)
    assert "81%" in item.text and "amber" in item.text
    assert area_status([item], AREA_CHARTER) == STATUS_AMBER


def test_a_charter_over_the_limit_is_red(seed_rulebook):
    rulebook = with_charter_percent(calm(seed_rulebook), 110)

    [item] = attention_items(rulebook, [], NOW)

    assert item.level == LEVEL_RED and area_status([item], AREA_CHARTER) == STATUS_RED


def test_11_20_a_trigger_that_is_off_gives_an_information_line(seed_rulebook):
    rulebook = calm(seed_rulebook)
    triggers = [
        t.model_copy(update={"on": t.name != "out_of_scope"})
        for t in rulebook.policy.escalation_triggers
    ]
    rulebook = rulebook.model_copy(
        update={"policy": rulebook.policy.model_copy(update={"escalation_triggers": triggers})}
    )

    items = attention_items(rulebook, [], NOW)

    assert texts(items) == ["Out of scope trigger is off."]
    assert area_status(items, AREA_BUILD) == STATUS_AMBER


def test_11_28_a_capability_without_a_backup_senior_is_named_and_the_area_is_amber(seed_rulebook):
    rulebook = calm(seed_rulebook)
    capabilities = [
        *rulebook.policy.capabilities,
        Capability(name="Reports", description="Made-up reports", named_senior="senior-0001",
                   path_patterns=["src/reports/*"]),
    ]
    rulebook = rulebook.model_copy(
        update={"policy": rulebook.policy.model_copy(update={"capabilities": capabilities})}
    )

    items = attention_items(rulebook, [], NOW)

    assert texts(items) == ["Capability 'Reports' has no backup senior."]
    assert area_status(items, AREA_CATALOG) == STATUS_AMBER


def test_an_empty_model_per_role_says_it_uses_the_server_default(seed_rulebook):
    rulebook = calm(seed_rulebook)
    rulebook = rulebook.model_copy(
        update={"policy": rulebook.policy.model_copy(update={"tester_model": ""})}
    )

    assert texts(attention_items(rulebook, [], NOW)) == ["Tester model: uses the server default."]


def test_judgement_rules_at_9_and_10_are_amber_and_over_the_cap_is_red(seed_rulebook):
    calm_book = calm(seed_rulebook)

    assert attention_items(with_judgement_rules(calm_book, 8), [], NOW) == []
    for count in (9, 10):
        [item] = attention_items(with_judgement_rules(calm_book, count), [], NOW)
        assert (item.area, item.level) == (AREA_CODING, LEVEL_INFO)
        assert f"{count} of 10" in item.text
    # 11 rules cannot be saved (the store refuses it), so the status function gets it in memory.
    [item] = attention_items(with_judgement_rules(calm_book, 11), [], NOW)
    assert item.level == LEVEL_RED and area_status([item], AREA_CODING) == STATUS_RED


def test_11_32_an_open_row_older_than_the_stale_days_makes_the_catalog_red(seed_rulebook):
    rulebook = calm(seed_rulebook)
    days = rulebook.policy.admin_unassigned_stale_days
    fresh = NOW - timedelta(days=days - 1)
    stale = NOW - timedelta(days=days + 1)

    young = attention_items(rulebook, [fresh], NOW)
    old = attention_items(rulebook, [fresh, stale], NOW)

    assert texts(young) == ["1 file waits for a capability (Capability catalog tab)."]
    assert area_status(young, AREA_CATALOG) == STATUS_AMBER
    assert area_status(old, AREA_CATALOG) == STATUS_RED
    assert texts(old)[0].startswith("2 files wait")
    assert f"1 Unassigned file waiting more than {days} days." in texts(old)


def test_retired_fields_are_empty_for_a_fresh_seed_and_reported_for_the_old_shape(seed_rulebook):
    assert carried_retired_fields(seed_rulebook) == []
    old = load_rulebook_file(OLD_SHAPE)

    carried = carried_retired_fields(old)
    items = attention_items(old, [], NOW)

    assert carried  # the Phase 1 seed holds the levels and zones
    assert all(item.area == AREA_BUILD for item in items if "Retired field" in item.text)
    assert any("Retired field" in text for text in texts(items))


def test_last_changed_names_the_newest_version_that_touched_each_area():
    def row(number, areas):
        return TimelineRow(
            version_number=number,
            saved_at=NOW - timedelta(days=10 - number),
            saved_by=f"admin-{number:04d}",
            change_note="made-up",
            restored_from=None,
            areas=areas,
            pinned_request_ids=[],
            is_active=number == 3,
        )

    timeline = [row(3, [AREA_BUILD]), row(2, [AREA_BUILD, AREA_CHARTER]), row(1, [])]

    changed = last_changed(timeline)

    assert changed[AREA_BUILD].startswith("v3 by admin-0003")
    assert changed[AREA_CHARTER].startswith("v2 by admin-0002")
    assert AREA_CODING not in changed  # never touched: the overview shows NEVER_CHANGED


def test_build_overview_on_a_real_database(db_path, published_rulebook, make_settings):
    settings = make_settings()
    request_id = create_request(db_path, "A made-up change", "dev-0001", now=NOW).request_id
    with open_db(db_path) as conn:
        ensure_build_tables(conn)
        add_unassigned(conn, "src/misc/odd.py", "Reports", request_id, NOW - timedelta(days=30))
    saved = save_from_form(db_path, "build", {"build_max_rounds": "4"}, 1, "admin-0002", "Four")
    assert saved.kind == "saved"

    overview = build_overview(settings, NOW)

    rows = {row.area: row for row in overview.areas}
    assert rows[AREA_BUILD].last_changed.startswith("v2 by admin-0002")
    assert rows[AREA_CHARTER].last_changed == NEVER_CHANGED
    assert "1 Unassigned" in rows[AREA_CATALOG].summary
    assert rows[AREA_CATALOG].status == STATUS_RED  # waiting 30 days, the stale limit is 14
    assert "max 4 fix rounds" in rows[AREA_BUILD].summary
    assert overview.version.version_number == get_active_version(db_path).version_number


def test_build_overview_without_a_published_rulebook_is_none(make_settings):
    assert build_overview(make_settings(), NOW) is None


def _version(rulebook):
    return RulebookVersion(
        version_number=1,
        rulebook=rulebook,
        change_note="made-up",
        saved_by="admin-0001",
        saved_at=NOW,
    )


@pytest.mark.usefixtures("published_rulebook")
def test_the_seed_itself_only_has_information_lines(seed_rulebook):
    # Not red anywhere, and no retired field, so a fresh install opens on a calm Overview.
    items = attention_items(seed_rulebook, [], NOW)

    assert not [item for item in items if item.level == LEVEL_RED]
    assert not [item for item in items if "Retired field" in item.text]
