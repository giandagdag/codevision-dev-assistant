"""Phase 11 fix 3, code review round 1 fixes. Made-up paths only; no AI, no network."""

from datetime import UTC, datetime

from agents.da_admin_rebuild import pick_embedder, source_folder
from agents.da_admin_scheduler import first_day
from agents.da_code_index import FakeEmbedder, WorkEmbedder
from da_load_starter_rulebook import load_starter_rulebook
from db_table_functions.db_tbl_da_rulebook import get_active_version


def test_the_work_seed_leaves_the_folder_scope_empty(db_path):
    load_starter_rulebook(db_path, at_work=True)
    assert get_active_version(db_path).rulebook.policy.index_folder_scope == ""


def test_the_home_seed_keeps_the_practice_scope(db_path):
    load_starter_rulebook(db_path, at_work=False)
    assert "da_fake_codevision" in get_active_version(db_path).rulebook.policy.index_folder_scope


def test_nightly_under_onprem_uses_the_passed_settings_for_the_work_embedder(make_settings):
    settings = make_settings(
        llm_provider="onprem", codevision_src="C:/made up/cv src", codevision_python="py.exe"
    )
    embedder = pick_embedder("onprem", settings)
    assert isinstance(embedder, WorkEmbedder)
    assert (embedder._src, embedder._python) == ("C:/made up/cv src", "py.exe")
    assert isinstance(pick_embedder("fake", settings), FakeEmbedder)


def test_the_work_source_comes_from_the_passed_settings(make_settings, published_rulebook):
    settings = make_settings(llm_provider="onprem", codevision_src="C:/made up/cv src")
    policy = published_rulebook.rulebook.policy.model_copy(update={"index_folder_scope": ""})
    assert str(source_folder(policy, "onprem", settings)).replace("\\", "/") == "C:/made up/cv src"


def test_a_server_started_before_the_nightly_time_still_runs_tonight(
    make_settings, published_rulebook
):
    settings = make_settings()
    # the seed's Nightly time is 02:00 Singapore time = 18:00 UTC the day before
    early = datetime(2026, 11, 17, 17, 0, tzinfo=UTC)  # 01:00 SGT on the 18th
    late = datetime(2026, 11, 17, 19, 0, tzinfo=UTC)  # 03:00 SGT on the 18th
    assert first_day(settings, early) is None
    assert first_day(settings, late).isoformat() == "2026-11-18"
