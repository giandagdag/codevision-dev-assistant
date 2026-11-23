"""Fix G6 S1: groups from code links, no AI, nothing tagged. Made-up modules only."""

from agents.da_code_clusters import MAX_GROUP, groups
from agents.da_code_graph import build_graph


def _build(tmp_path, files: dict[str, str]):
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    return build_graph(tmp_path, list(files)).graph


def _star(folder: str, hub: str, leaves: list[str]) -> dict[str, str]:
    files = {f"{folder}/{hub}.py": "".join(f"import {folder}.{n}\n" for n in leaves)}
    return files | {f"{folder}/{n}.py": f"import {folder}.{hub}\n" for n in leaves}


def _three_groups_and_a_loner() -> dict[str, str]:
    files = _star("md", "mdhub", ["mda", "mdb", "mdc"])
    files |= _star("pay", "payhub", ["paya", "payb", "payc"])
    files |= _star("rep", "rephub", ["repa", "repb", "repc"])
    files["rep/loner.py"] = "import rep.rephub\n"  # one link, to the rep group
    return files


def test_three_groups_and_the_loner_joins_its_most_linked_group(tmp_path):
    graph = _build(tmp_path, _three_groups_and_a_loner())

    found = groups(graph)

    assert len(found) == 3
    rep = next(g for g in found if "rep/rephub.py" in g.programs)
    assert "rep/loner.py" in rep.programs and rep.folders == ("rep",)
    assert rep.inside > 0 and rep.outside == 0
    assert groups(graph) == found  # same answer every time


def test_a_program_with_no_links_is_left_out(tmp_path):
    files = _star("md", "mdhub", ["mda", "mdb"]) | {"md/alone.py": "x = 1\n"}

    found = groups(_build(tmp_path, files))

    assert [p for g in found for p in g.programs if p.endswith("alone.py")] == []


def test_a_group_over_the_limit_is_split_once_by_top_folder(tmp_path):
    big = [f"leaf{i}" for i in range(MAX_GROUP)]
    files = _star("one", "hub", big)
    files["two/extra.py"] = "import one.hub\n"
    files["two/extra2.py"] = "import one.hub\nimport two.extra\n"

    found = groups(_build(tmp_path, files))

    assert sorted(g.folders for g in found) == [("one",), ("two",)]
