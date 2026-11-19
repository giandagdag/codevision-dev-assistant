"""Upgrade G step 5: clusters and capability suggestions (G-6, G-7). Made-up modules only."""

from agents.da_admin_tag_cards import ai_cards, reject_card
from agents.da_admin_tag_store import read_store, save_store
from agents.da_code_clusters import clusters, write_suggestions
from agents.da_code_graph import build_graph


def _graph(tmp_path, names: list[str]):
    """hub imports every other module, and each of them imports hub."""
    files = {"src/hub.py": "".join(f"import {n}\n" for n in names)}
    files |= {f"src/{n}.py": "import hub\n" for n in names}
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    return build_graph(tmp_path, list(files)).graph


def _tag(names: list[str], capability: str = "Limits") -> dict:
    entry = {"state": "approved", "proposed_capability": capability}
    return {"modules": {f"src/{n}.py": dict(entry) for n in names}, "runs": []}


def test_clusters_are_the_same_every_time(tmp_path):
    graph = _graph(tmp_path, ["a", "b", "c", "d"])

    assert clusters(graph) == clusters(graph) == [["a", "b", "c", "d", "hub"]]


def test_g6_untagged_module_gets_a_card_and_nothing_is_tagged(tmp_path):
    directory = tmp_path / "index"
    graph = _graph(tmp_path, ["a", "b", "c", "d"])
    save_store(_tag(["a", "b", "c", "d"]), directory)  # hub is the untagged one

    assert write_suggestions(graph, directory) == 1

    (card,) = ai_cards(directory)
    assert card.path == "src/hub.py" and card.capability == "Limits"
    assert card.reason == "Suggested from code links: 4 of 4 linked modules are Limits"
    assert read_store(directory)["modules"]["src/hub.py"]["state"] == "proposed"  # not a tag yet


def test_a_small_or_split_cluster_gives_no_card(tmp_path):
    directory = tmp_path / "index"
    graph = _graph(tmp_path, ["a", "b", "c", "d"])
    save_store(_tag(["a", "b"]), directory)  # only 2 tagged

    assert write_suggestions(graph, directory) == 0

    split = _tag(["a", "b", "c"]) | {"runs": []}
    split["modules"]["src/c.py"]["proposed_capability"] = "Menus"
    split["modules"]["src/d.py"] = {"state": "approved", "proposed_capability": "Menus"}
    save_store(split, directory)  # 2 Limits, 2 Menus: no majority
    assert write_suggestions(graph, directory) == 0


def test_g7_a_rejected_card_stays_away_until_the_cluster_changes(tmp_path):
    directory = tmp_path / "index"
    graph = _graph(tmp_path, ["a", "b", "c", "d"])
    save_store(_tag(["a", "b", "c", "d"]), directory)
    write_suggestions(graph, directory)

    reject_card("src/hub.py", directory)

    assert write_suggestions(graph, directory) == 0  # next build, same cluster
    assert ai_cards(directory) == []
    bigger = _graph(tmp_path, ["a", "b", "c", "d", "e"])  # the cluster changed
    save_store(_tag(["a", "b", "c", "d", "e"]), directory)
    assert write_suggestions(bigger, directory) == 1


def test_an_undecided_ai_tag_does_not_hide_the_links_card(tmp_path):
    directory = tmp_path / "index"
    graph = _graph(tmp_path, ["a", "b", "c", "d"])
    store = _tag(["a", "b", "c", "d"])
    ai = {"summary": "Hub text", "proposed_capability": "Menus", "confidence": "low",
          "reason": "AI", "state": "proposed", "file_hash": "h1"}
    store["modules"]["src/hub.py"] = dict(ai)
    save_store(store, directory)

    assert write_suggestions(graph, directory) == 1

    entry = read_store(directory)["modules"]["src/hub.py"]
    assert entry["summary"] == "Hub text" and entry["proposed_capability"] == "Limits"
    assert entry["reason"].startswith("Suggested from code links")
    small = _graph(tmp_path, ["a"])  # the cluster is gone: the AI tag comes back untouched
    assert write_suggestions(small, directory) == 0
    assert read_store(directory)["modules"]["src/hub.py"] == ai


def test_a_rejected_links_card_does_not_bring_the_ai_tag_back(tmp_path):
    directory = tmp_path / "index"
    graph = _graph(tmp_path, ["a", "b", "c", "d"])
    store = _tag(["a", "b", "c", "d"])
    store["modules"]["src/hub.py"] = {
        "summary": "Hub text", "proposed_capability": "Menus", "confidence": "low",
        "reason": "AI", "state": "proposed", "file_hash": "h1",
    }
    save_store(store, directory)
    write_suggestions(graph, directory)
    reject_card("src/hub.py", directory)

    assert write_suggestions(graph, directory) == 0

    assert read_store(directory)["modules"]["src/hub.py"]["state"] == "rejected"
    assert ai_cards(directory) == []
