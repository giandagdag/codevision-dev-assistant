"""Fix batch B1 step 8 (F7, B1-8): no silent practice index at work, and the demo banner."""

import pytest

from agents.da_discover_flow import NO_INDEX_MESSAGE, start_discovery
from db_table_functions.db_tbl_da_understand import list_messages
from layouts.da_developer_assistant_page import DEMO_PAGE_BANNER
from tests.da_discover_play import confirmed_id
from tests.da_stub_client import StubClient
from tests.da_tree import all_text
from tests.test_da_home_web_server import make_app

pytestmark = pytest.mark.usefixtures("published_rulebook")


def test_b1_8_onprem_with_the_practice_index_searches_nothing_and_says_so(make_settings):
    settings = make_settings(llm_provider="fake")
    request_id = confirmed_id(settings)
    work = make_settings(llm_provider="onprem", search_provider="fake")

    view = start_discovery(work, request_id, 0, client=StubClient(""))

    assert view.result.hits == [] and view.result.search_provider == "none"
    assert NO_INDEX_MESSAGE in view.result.limitations
    assert view.request.status == "NO_RELIABLE_MATCH"  # the request carries on
    said = [m.text for m in list_messages(work.db_path, request_id)]
    assert NO_INDEX_MESSAGE in said


def test_the_practice_index_still_answers_at_home(make_settings):
    settings = make_settings()
    view = start_discovery(settings, confirmed_id(settings), 0)

    assert view.result.hits and NO_INDEX_MESSAGE not in view.result.limitations


def test_b1_8_the_demo_banner_shows_with_the_fake_provider_only(make_settings, monkeypatch):
    fake = make_app(make_settings, monkeypatch)
    assert DEMO_PAGE_BANNER in all_text(fake.layout)

    work = make_settings(llm_provider="onprem", onprem_url="https://x.example/v1", onprem_model="m")
    monkeypatch.setattr("web.da_home_web_server.get_settings", lambda: work)
    from web import da_home_web_server as server

    assert DEMO_PAGE_BANNER not in all_text(server.create_app().layout)
