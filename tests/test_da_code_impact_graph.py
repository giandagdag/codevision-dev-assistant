"""Upgrade G step 4: who uses a module (G-8, G-9, G-10). Made-up modules only."""

from agents import da_enhance_flow as enhance
from agents.da_code_graph import build_graph, save_graph
from agents.da_code_impact_graph import impact_of, who_uses, with_used_by
from layouts.da_enhance_panel import impact_card
from pydantic_classes.da_discovery_models import Finding, SearchHit
from pydantic_classes.da_enhance_models import ImpactResult
from web.da_web_components import finding_card, used_by_block


def test_used_by_wording_for_one_many_and_none():  # G1-2
    one = str(used_by_block(["a"]))
    assert "Used by 1 module" in one and "1 modules" not in one
    assert "Used by 3 modules" in str(used_by_block(["a", "b", "c"]))
    none = str(used_by_block([]))
    assert "Not used by other modules" in none and "Details" not in none

FILES = {
    "src/agents/limits.py": "def check():\n    return 1\n",
    "src/agents/screen.py": "from agents.limits import check\n\ndef show():\n    return check()\n",
    "src/agents/menu.py": "from agents import screen\n\ndef run():\n    return screen.show()\n",
    "src/agents/lonely.py": "def alone():\n    return 0\n",
}
TAGS = {
    "src/agents/screen.py": {"state": "approved", "proposed_capability": "Limits"},
    "src/agents/menu.py": {"state": "proposed", "proposed_capability": "Menus"},
}


def _graph(tmp_path):
    for name, text in FILES.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    return build_graph(tmp_path, list(FILES)).graph


def test_g8_impact_of_gives_two_levels_with_approved_capability_only(tmp_path):
    graph = _graph(tmp_path)

    users = impact_of(graph, "agents.limits", TAGS)

    assert [(u.module, u.level, u.capability) for u in users] == [
        ("agents.screen", 1, "Limits"),
        ("agents.menu", 2, ""),  # a proposal is not a tag yet
    ]
    assert who_uses(graph, "agents.limits") == ["agents.screen"]
    assert who_uses(graph, "agents.limits.check") == ["agents.screen"]
    assert impact_of(graph, "agents.lonely") == []


def test_g9_a_discover_hit_shows_used_by(tmp_path):
    graph = _graph(tmp_path)
    hit = SearchHit(
        hit_id=1, source_path="src/agents/limits.py", symbol="check", kind="code",
        score=0.5, mode="exact",
    )
    other = hit.model_copy(update={"hit_id": 2, "source_path": "src/agents/lonely.py"})

    shown, plain = with_used_by([hit, other], graph)

    assert shown.used_by == ["agents.screen"] and plain.used_by == []
    assert with_used_by([hit], None) == [hit]  # no graph: unchanged
    finding = Finding(
        kind="similar_implementation", title="Reuse check", explanation="x", hit_ids=[1],
        confidence="high",
    )
    assert "Used by 1 module" in str(finding_card(finding, {1: shown}))
    assert "Used by" not in str(finding_card(finding, {1: hit}))


def test_g10_enhance_impact_uses_the_graph_only_when_there_is_one(tmp_path, monkeypatch):
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path / "index"))
    assert enhance.graph_users(["src/agents/limits.py"]) == []  # no graph: today's answer

    save_graph(_graph(tmp_path), tmp_path / "index")
    users = enhance.graph_users(["src/agents/limits.py"])

    assert [(u.module, u.level) for u in users] == [("agents.screen", 1), ("agents.menu", 2)]
    text = str(impact_card(ImpactResult(users=users)))
    assert "agents.screen" in text and "agents.menu" in text
    assert "Uses a user" not in str(impact_card(ImpactResult()))
