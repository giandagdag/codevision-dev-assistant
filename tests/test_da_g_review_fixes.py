"""Upgrade G code review round 1: catalog patterns, Save notice, audit safety, link skips."""

import json

from agents.da_admin_audit import add_admin_event, read_admin_events
from agents.da_admin_tag_cards import ai_cards
from agents.da_admin_tag_store import save_store
from agents.da_capability_map import UNASSIGNED, capabilities_view
from agents.da_code_clusters import write_suggestions
from agents.da_code_graph import build_graph
from agents.da_code_impact_graph import with_catalog_tags as with_catalog
from layouts.da_admin_index_panels import recent_refreshes
from layouts.da_admin_page import saved_notice
from pydantic_classes.da_rulebook_models import Capability

LIMITS = Capability(
    name="Limits", description="d", named_senior="s", path_patterns=["src/*.py"]
)


def _graph(tmp_path, names):
    files = {"src/hub.py": "".join(f"import {n}\n" for n in names)}
    files |= {f"src/{n}.py": "import hub\n" for n in names}
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    return build_graph(tmp_path, list(files)).graph


def test_a_module_the_catalog_patterns_place_is_not_unassigned_on_the_map(tmp_path):
    graph = _graph(tmp_path, ["a", "b"])

    plain = capabilities_view(graph, {})
    placed = capabilities_view(graph, with_catalog(graph, {}, [LIMITS]))

    assert [n["id"] for n in plain.nodes] == [UNASSIGNED]
    assert [(n["id"], n["size"]) for n in placed.nodes] == [("Limits", 3)]


def test_an_approved_tag_wins_over_the_catalog_pattern(tmp_path):
    graph = _graph(tmp_path, ["a"])
    tags = {"src/a.py": {"state": "approved", "proposed_capability": "Other"}}

    merged = with_catalog(graph, tags, [LIMITS])

    assert merged["src/a.py"]["proposed_capability"] == "Other"
    assert merged["src/hub.py"]["proposed_capability"] == "Limits"


def test_cluster_cards_skip_modules_the_catalog_already_places(tmp_path):
    directory = tmp_path / "index"
    graph = _graph(tmp_path, ["a", "b", "c", "d"])
    save_store({"modules": {}, "runs": []}, directory)

    assert write_suggestions(graph, directory, [LIMITS]) == 0  # every module has a capability
    assert ai_cards(directory) == []


def test_save_notice_shows_open_requests_per_version():
    alert = saved_notice(4, [], ["2 open requests use v3 and keep it"]).to_plotly_json()
    assert "2 open requests use v3 and keep it" in json.dumps(alert, default=str)


def test_a_damaged_audit_file_is_kept_not_overwritten(tmp_path):
    (tmp_path / "da_admin_audit.json").write_text("{not json at all", encoding="utf-8")

    add_admin_event("tags_restored", "admin-0001", "x", tmp_path)

    assert [e["kind"] for e in read_admin_events(tmp_path)] == ["tags_restored"]
    damaged = tmp_path / "da_admin_audit.json.damaged"
    assert damaged.read_text(encoding="utf-8") == "{not json at all"


def test_files_without_code_links_show_in_the_refresh_list():
    run = {"started": "2026-11-20T01:00:00", "link_skipped": ["src/bad.py: invalid syntax"]}
    text = json.dumps(recent_refreshes([run]).to_plotly_json(), default=str)
    assert "No code links: src/bad.py: invalid syntax" in text
