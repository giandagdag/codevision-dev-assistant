"""Fix G7 D1/D2: "Search again" once an index is available after a round with no index."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from agents import da_approach_flow as approach_flow
from agents import da_discover_flow as flow
from agents.da_discover_flow import start_discovery
from agents.da_search_index import FakeSearchIndex
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_approach import ensure_approach_tables, save_approach_state
from db_table_functions.db_tbl_da_discovery import get_results
from layouts.da_developer_assistant_page import discover_buttons
from pydantic_classes.da_approach_models import ApproachState
from tests.da_discover_play import confirmed_id, set_status

pytestmark = pytest.mark.usefixtures("published_rulebook")

SIMILAR = "SIMILAR_IMPLEMENTATION_FOUND"


@pytest.fixture
def after_no_index(make_settings, tmp_path, monkeypatch):
    """A request whose first round ran with no index; the index then 'appears' (build 3)."""
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path / "none"))
    settings = make_settings(search_provider="codevision")
    request_id = confirmed_id(make_settings())
    start_discovery(settings, request_id, 0)
    fake = FakeSearchIndex.from_file()
    monkeypatch.setattr(flow, "get_search_index", lambda _settings: fake)
    monkeypatch.setattr(flow, "current_build", lambda *a: 3)
    return settings, request_id


def test_g7_9_amber_line_button_and_a_new_round_that_uses_the_index(after_no_index):
    settings, request_id = after_no_index
    view = flow.get_discovery_view(settings, request_id)
    assert view.search_again_offered
    assert ("start", "Search again") in discover_buttons(view)

    again = start_discovery(settings, request_id, view.revision)

    assert again.result.round == 2 and again.result.hits
    assert len(get_results(settings.db_path, request_id)) == 2  # the old round stays
    assert not again.search_again_offered


def test_g7_9_from_discovery_confirmed_it_goes_back_to_searching(after_no_index):
    settings, request_id = after_no_index
    set_status(settings, request_id, "SEARCHING", SIMILAR, "DISCOVERY_CONFIRMED")
    view = flow.get_discovery_view(settings, request_id)
    assert view.search_again_offered
    assert ("search_again", "Search again") in approach_flow.get_approach_view(
        settings, request_id
    ).buttons

    again = start_discovery(settings, request_id, view.revision)

    assert again.request.status in (SIMILAR, "NO_RELIABLE_MATCH")
    assert again.result.round == 2


def test_g7_9_a_search_again_round_does_not_count_against_the_cap(after_no_index):
    settings, request_id = after_no_index
    capped = replace(settings, discovery_max_rounds=1)
    set_status(settings, request_id, "SEARCHING", SIMILAR, "DISCOVERY_CONFIRMED")
    view = flow.get_discovery_view(capped, request_id)

    assert start_discovery(capped, request_id, view.revision).result.round == 2


def test_g7_9_no_offer_once_a_plan_exists_or_with_no_index(after_no_index, monkeypatch):
    settings, request_id = after_no_index
    set_status(settings, request_id, "SEARCHING", SIMILAR, "DISCOVERY_CONFIRMED")
    with open_db(settings.db_path) as conn:
        ensure_approach_tables(conn)
        conn.execute("BEGIN")
        save_approach_state(conn, ApproachState(request_id=request_id), 0, datetime.now(UTC))
        conn.commit()
    assert not flow.get_discovery_view(settings, request_id).search_again_offered
    monkeypatch.setattr(flow, "current_build", lambda *a: None)
    assert not flow.get_discovery_view(settings, request_id).search_again_offered
