"""start_discovery and the round transaction (step 11b)."""

import pytest

from agents import da_discover_flow as flow
from agents.da_discover_flow import (
    DISCOVER_DIVIDER,
    NOT_PROOF_LIMITATION,
    start_discovery,
)
from agents.da_search_index import IndexFormatError
from db_table_functions.da_db import open_db
from db_table_functions.db_tbl_da_discovery import (
    DiscoveryError,
    get_results,
    read_discovery_revision,
)
from db_table_functions.db_tbl_da_requests import get_request
from db_table_functions.db_tbl_da_understand import (
    STALE_MESSAGE,
    StaleRevisionError,
    list_messages,
)
from tests.da_discover_play import (
    confirmed_id,
    event_types,
    events_of,
    moves,
    record_state,
    set_status,
)
from tests.da_stub_client import StubClient

pytestmark = pytest.mark.usefixtures("published_rulebook")

SIMILAR = "SIMILAR_IMPLEMENTATION_FOUND"


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def request_id(settings):
    return confirmed_id(settings)


def test_demo_record_with_the_fake_provider_gives_ai_findings_and_similar_found(
    settings, request_id
):
    view = start_discovery(settings, request_id, 0)

    assert view.request.status == SIMILAR
    assert view.result.summary_source == "ai"
    assert view.result.round == 1 and view.rounds_used == 1
    assert {f.kind for f in view.result.findings} >= {"existing_capability", "relevant_standard"}
    cited = {i for f in view.result.findings for i in f.hit_ids}
    assert cited and cited <= {h.hit_id for h in view.result.hits}
    assert view.revision == 1 and view.demo_mode


def test_the_round_is_saved_with_queries_hits_and_versions(settings, request_id):
    start_discovery(settings, request_id, 0)

    saved = get_results(settings.db_path, request_id)[0]
    assert saved.search_provider == "fake" and saved.record_version == 1
    assert saved.rulebook_version == 1 and saved.hint == ""
    assert saved.queries and all(q.startswith(("exact: ", "meaning: ")) for q in saved.queries)
    assert saved.hits[0].version == "fake-index-001"
    assert saved.created_at is not None


def test_status_audit_and_chat_are_saved_together(settings, request_id):
    start_discovery(settings, request_id, 0)

    types = event_types(settings, request_id)
    assert types[-4:] == [
        "discovery_started", "status_changed", "status_changed", "discovery_completed",
    ]
    status_moves = moves(settings, request_id)
    assert status_moves[-2:] == [
        ("CONFIRMED_FOR_DISCOVERY", "SEARCHING"),
        ("SEARCHING", SIMILAR),
    ]
    done = events_of(settings, request_id, "discovery_completed")[0].details
    assert done["round"] == 1 and done["outcome"] == SIMILAR and done["summary_source"] == "ai"
    texts = [m.text for m in list_messages(settings.db_path, request_id)]
    assert texts[-3] == DISCOVER_DIVIDER
    assert "Searching approved sources" in texts[-2]
    assert texts[-1].startswith("Round 1: found")


def test_record_v1_and_the_session_are_byte_identical_after_the_round(settings, request_id):
    before = record_state(settings, request_id)

    start_discovery(settings, request_id, 0)

    assert record_state(settings, request_id) == before


def test_no_match_gets_the_not_proof_limitation(settings, request_id):
    class NoHits:
        def search(self, query, mode, filters, top_k):
            return []

    view = start_discovery(settings, request_id, 0, index=NoHits())

    assert view.request.status == "NO_RELIABLE_MATCH"
    assert view.result.limitations[-1] == NOT_PROOF_LIMITATION
    assert view.result.hits == [] and view.result.findings == []
    assert "not proof" in view.messages[-1].text


def test_a_bad_ai_gives_plain_results_and_still_an_outcome(settings, request_id):
    client = StubClient("not json", "still not json")

    view = start_discovery(settings, request_id, 0, client=client)

    assert view.result.summary_source == "fallback"
    assert view.result.findings
    assert view.request.status in (SIMILAR, "NO_RELIABLE_MATCH")


def test_start_from_searching_only_moves_searching_to_the_outcome(settings, request_id):
    set_status(settings, request_id, "SEARCHING")

    view = start_discovery(settings, request_id, 0)

    assert view.request.status == SIMILAR and view.result.round == 1
    status_moves = moves(settings, request_id)
    assert status_moves[-1] == ("SEARCHING", SIMILAR)
    assert ("CONFIRMED_FOR_DISCOVERY", "SEARCHING") not in status_moves[-2:]
    assert event_types(settings, request_id)[-3:] == [
        "discovery_started", "status_changed", "discovery_completed",
    ]
    assert DISCOVER_DIVIDER not in [m.text for m in view.messages]


def test_a_failure_after_the_status_write_leaves_nothing_behind(settings, request_id, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("disk problem")

    before = (
        event_types(settings, request_id),
        len(list_messages(settings.db_path, request_id)),
        get_request(settings.db_path, request_id),
        record_state(settings, request_id),
    )
    monkeypatch.setattr(flow, "insert_result", fail)

    with pytest.raises(RuntimeError):
        start_discovery(settings, request_id, 0)

    assert event_types(settings, request_id) == before[0]
    assert len(list_messages(settings.db_path, request_id)) == before[1]
    assert get_request(settings.db_path, request_id) == before[2]
    assert get_request(settings.db_path, request_id).status == "CONFIRMED_FOR_DISCOVERY"
    assert record_state(settings, request_id) == before[3]
    assert get_results(settings.db_path, request_id) == []
    with open_db(settings.db_path) as conn:
        assert read_discovery_revision(conn, request_id) == 0


def test_a_stale_window_is_refused_and_nothing_is_written(settings, request_id):
    start_discovery(settings, request_id, 0)
    set_status(settings, request_id, "SEARCHING", SIMILAR, "SEARCHING")  # allow a second start

    with pytest.raises(StaleRevisionError, match=STALE_MESSAGE):
        start_discovery(settings, request_id, 0)

    assert len(get_results(settings.db_path, request_id)) == 1


@pytest.mark.parametrize("status", ["DISCOVERY_CONFIRMED", "ESCALATION_REQUIRED"])
def test_start_is_refused_from_a_finished_status(settings, request_id, status):
    set_status(settings, request_id, "SEARCHING", SIMILAR, status)

    with pytest.raises(DiscoveryError, match="cannot be searched"):
        start_discovery(settings, request_id, 0)


def test_unknown_request_is_refused(settings, request_id):
    with pytest.raises(DiscoveryError, match="does not exist"):
        start_discovery(settings, "CVDA-2026-9999", 0)


def test_b1_20_codevision_provider_without_index_says_to_build_and_carries_on(
    make_settings, published_rulebook, tmp_path, monkeypatch
):
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path / "none"))
    fake = make_settings()
    request_id = confirmed_id(fake)
    settings = make_settings(search_provider="codevision")

    view = start_discovery(settings, request_id, 0)

    assert any("needs building" in text for text in view.result.limitations)
    assert view.result.hits == []
    assert get_request(settings.db_path, request_id).status != "CONFIRMED_FOR_DISCOVERY"


def test_g8_real_index_with_a_long_function_starts_discovery_and_hits_stay_short(
    make_settings, published_rulebook, tmp_path, monkeypatch
):
    from agents.da_code_index import FakeEmbedder
    from da_build_code_index import build_index

    # A made-up function of about 1,800 characters, written to the real splitter path.
    words = "excel upload validate check batch ingest process extract file type"
    body = "".join(f"    total_{n} = len('{words}') + {n}\n" for n in range(45))
    source = tmp_path / "src"
    source.mkdir()
    (source / "big.py").write_text(f"def check_excel_upload():\n{body}    return 1\n")
    out = tmp_path / "idx"
    build_index(source, out, FakeEmbedder(), say=lambda _text: None)
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(out))
    request_id = confirmed_id(make_settings())

    view = start_discovery(make_settings(search_provider="codevision"), request_id, 0)

    assert not any("could not be read" in text for text in view.result.limitations)
    assert view.result.hits and all(len(h.snippet) <= 500 for h in view.result.hits)


def test_a_broken_index_file_is_a_plain_message(settings, request_id, monkeypatch):
    def broken(settings):
        raise IndexFormatError("The search index is out of order: made-up test message.")

    monkeypatch.setattr(flow, "get_search_index", broken)

    with pytest.raises(DiscoveryError, match="out of order"):
        start_discovery(settings, request_id, 0)


def test_ai_setup_problem_gives_plain_results_not_a_crash(settings, request_id, monkeypatch):
    from configs.da_config import ConfigError

    def broken(settings):
        raise ConfigError("DA_ONPREM_URL is not set.")

    monkeypatch.setattr(flow, "get_discover_client", broken)

    view = start_discovery(settings, request_id, 0)

    assert view.result.summary_source == "fallback" and view.result.findings


# --- Phase 6 fixes, section 7: say when the index is made up ---


def test_the_chat_message_of_a_round_on_the_fake_index_says_so(settings, request_id):
    view = start_discovery(settings, request_id, 0)

    lines = [m.text for m in view.messages if m.speaker == "assistant"][-1].split("\n")

    assert lines[-1] == "Practice index (made-up code), not CodeVision."
    assert lines[0].startswith("Round 1: found ")


def test_the_notice_is_only_for_the_fake_index(settings, request_id):
    view = start_discovery(settings, request_id, 0)
    real = view.result.model_copy(update={"search_provider": "codevision"})

    assert "Practice index" in flow._result_line(view.result, SIMILAR)
    assert "Practice index" not in flow._result_line(real, SIMILAR)
