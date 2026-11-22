"""Fix G6 S3: merge step. Same names merge, at most 12 areas, nothing is created."""

import json
from types import SimpleNamespace

from agents.da_capability_suggest import (
    STEP_GROUPING,
    STEP_MERGING,
    STEP_NAMING,
    NamedGroup,
    cap_count,
    suggest,
)
from agents.da_code_graph import build_graph


def _star(folder: str, leaves: int) -> dict[str, str]:
    names = [f"l{i}" for i in range(leaves)]
    files = {f"{folder}/hub.py": "".join(f"import {folder}.{n}\n" for n in names)}
    return files | {f"{folder}/{n}.py": f"import {folder}.hub\n" for n in names}


def _graph(tmp_path, folders: dict[str, int], extra=None):
    files = {}
    for folder, leaves in folders.items():
        files |= _star(folder, leaves)
    files |= extra or {}
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    return build_graph(tmp_path, list(files)).graph


class _Client:
    """Names a group by its folder; the merge call returns the scripted merges."""

    def __init__(self, names: dict[str, str], merges=()):
        self.names, self.merges, self.merge_calls = names, list(merges), 0

    def complete(self, prompt, system=None):
        if "Suggested areas" in prompt:
            self.merge_calls += 1
            return SimpleNamespace(text=json.dumps({"merges": self.merges}))
        folder = prompt.split("- ", 1)[1].split("/", 1)[0]
        reply = {"name": self.names[folder], "description": "d", "not_in_group": [],
                 "confidence": "high"}  # fmt: skip
        return SimpleNamespace(text=json.dumps(reply))


def test_same_name_ignoring_case_and_plural_gives_one_card(tmp_path):
    graph = _graph(tmp_path, {"a": 3, "b": 2, "c": 3})
    client = _Client({"a": "Markdown export", "b": "Markdown Exports", "c": "Reports"})

    cards = suggest(graph, {}, client, known=[])

    assert {c.name: len(c.programs) for c in cards} == {"Markdown export": 4 + 3, "Reports": 4}


def test_the_ai_merge_call_joins_areas_and_renames(tmp_path):
    graph = _graph(tmp_path, {"a": 3, "b": 3, "c": 3})
    merges = [{"names": ["Intake", "Upload"], "name": "Ingestion", "description": "Takes files in"}]
    client = _Client({"a": "Intake", "b": "Upload", "c": "Reports"}, merges)

    cards = suggest(graph, {}, client, known=[])

    assert {c.name for c in cards} == {"Ingestion", "Reports"}
    assert client.merge_calls == 1


def test_fifteen_groups_give_at_most_twelve_cards(tmp_path):
    folders = {f"f{i:02d}": 2 + (i % 3) for i in range(15)}
    graph = _graph(tmp_path, folders, {"f00/x.py": "import f01.hub\n"})
    client = _Client({f: f"Area {f}" for f in folders})

    cards = suggest(graph, {}, client, known=[])

    assert len(cards) == 12
    assert sum(len(c.programs) for c in cards) == sum(n + 1 for n in folders.values()) + 1


def test_g6_3_the_smallest_group_joins_its_most_linked_neighbour_not_the_biggest():
    def group(name, programs):
        return NamedGroup(name, "d", tuple(programs), "high", (), 0, 0)

    big = group("Big", ["b1", "b2", "b3", "b4"])
    near = group("Near", ["n1", "n2", "n3"])
    tiny = group("Tiny", ["t1", "t2"])
    weights = {"t1": {"n1": 5}, "n1": {"t1": 5}}  # Tiny talks to Near only

    result = {g.name: g.programs for g in cap_count([big, near, tiny], weights, limit=2)}

    assert result == {"Big": big.programs, "Near": ("n1", "n2", "n3", "t1", "t2")}


def test_a_name_equal_to_a_catalog_capability_is_a_proposal_for_it(tmp_path):
    graph = _graph(tmp_path, {"a": 3, "b": 3})
    client = _Client({"a": "Limit checks", "b": "Reports"})

    cards = suggest(graph, {}, client, known=["Limit Check"])

    assert {c.name: c.existing for c in cards} == {"Limit checks": "Limit Check", "Reports": ""}


def test_progress_names_the_three_steps(tmp_path):
    graph = _graph(tmp_path, {"a": 3})
    steps: list[str] = []

    suggest(graph, {}, _Client({"a": "Area"}), known=[], progress=steps.append)

    assert steps == [STEP_GROUPING, STEP_NAMING, STEP_MERGING]
