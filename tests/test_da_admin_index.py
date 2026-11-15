"""Fix 11-1, AF-6: Repository and index shows Connection, Refresh, Exclusions, health and runs."""

import json
from datetime import datetime

from agents.da_admin_forms import RESULT_SAVED, save_from_form
from agents.da_admin_index import (
    KEPT_RUNS,
    NEEDS_BUILDING,
    read_health,
    recent_runs,
    record_run,
    run_line,
)
from agents.da_code_index import PIECES_NAME
from db_table_functions.db_tbl_da_rulebook import get_active_version
from layouts.da_admin_page import repo_view
from tests.test_da_admin_page import all_text

NOW = datetime(2026, 11, 15, 12, 0)


def test_no_index_files_say_the_index_needs_building(tmp_path, monkeypatch, published_rulebook):
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path))

    text = all_text(repo_view(published_rulebook, []))

    assert NEEDS_BUILDING in text
    assert "No refreshes yet." in text


def test_health_comes_from_the_piece_list(tmp_path):
    record = {
        "built_at": "2026-11-15T09:00:00",
        "source": "src/data/da_fake_codevision",
        "pieces": [{"path": "a.py"}, {"path": "a.py"}, {"path": "b.py"}],
    }
    (tmp_path / PIECES_NAME).write_text(json.dumps(record), encoding="utf-8")

    health = read_health(tmp_path)

    assert (health.modules, health.pieces) == (2, 3)
    assert health.is_fresh(NOW) and health.pill(NOW) == "Index is fresh, built 3 hours ago"


def test_runs_keep_the_last_ten_and_never_store_code_text(tmp_path):
    for n in range(12):
        record_run("admin", NOW, True, n, ["x.py f"], "ok", tmp_path)
    record_run("admin", NOW, False, 0, [], "Not saved: over 10% failed", tmp_path)

    runs = recent_runs(tmp_path)

    assert len(runs) == KEPT_RUNS and runs[0]["saved"] is False
    assert "❌ Not saved" in run_line(runs[0])
    assert "⚠️ 1 piece skipped" in run_line(runs[1])


def test_repo_view_shows_connection_refresh_and_fixed_skips(
    tmp_path, monkeypatch, published_rulebook
):
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path))

    text = all_text(repo_view(published_rulebook, [("DA_SEARCH_TOP_K", "20")]))

    assert "Branch indexed: main 🔒" in text
    assert "Folder scope:" in text and "src/data/da_fake_codevision" in text  # path in a code chip
    assert "On every merge to main" in text and "Not connected yet" in text
    assert "🔒 da_*" in text and "Always skipped." in text
    assert "Search results per query: 20" in text


def test_saving_scope_and_exclusions_changes_only_those(db_path, published_rulebook):
    form = {
        "index_folder_scope": "src/data/da_fake_main",
        "index_exclusions": [
            {"pattern": "*/config/*", "reason": "Settings", "kind": "Config"},
            {"pattern": "", "reason": "", "kind": "Config"},  # untouched new row: dropped
        ],
    }

    result = save_from_form(db_path, "repo", form, 1, "admin-0001", "Scope")

    assert result.kind == RESULT_SAVED
    policy = get_active_version(db_path).rulebook.policy
    assert policy.index_folder_scope == "src/data/da_fake_main"
    assert [e.pattern for e in policy.index_exclusions] == ["*/config/*"]
