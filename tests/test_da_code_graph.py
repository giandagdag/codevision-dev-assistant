"""Upgrade G step 1: code links (G-1 to G-5, G-25). Made-up modules only."""

import time

from agents.da_code_graph import (
    CALLS,
    IMPORTS,
    USES_CLASS,
    build_graph,
    load_graph,
    save_graph,
)


def _write(root, files: dict[str, str]) -> list[str]:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return list(files)


def _edges(result) -> set[tuple]:
    return {tuple(e) for entry in result.graph["files"].values() for e in entry["edges"]}


def test_g1_import_and_call_edges(tmp_path):
    paths = _write(tmp_path, {
        "a.py": "from b import f\n\ndef caller():\n    f()\n",
        "b.py": "def f():\n    return 1\n",
    })
    edges = _edges(build_graph(tmp_path, paths))
    assert (IMPORTS, "a", "b") in edges
    assert (CALLS, "a.caller", "b.f") in edges


def test_alias_module_call_and_same_module_call(tmp_path):
    paths = _write(tmp_path, {
        "a.py": "import b as bb\n\ndef one():\n    bb.f()\n    two()\n\ndef two():\n    pass\n",
        "b.py": "def f():\n    pass\n",
    })
    edges = _edges(build_graph(tmp_path, paths))
    assert (CALLS, "a.one", "b.f") in edges
    assert (CALLS, "a.one", "a.two") in edges


def test_g2_unresolved_call_is_counted_not_drawn(tmp_path):
    paths = _write(tmp_path, {"a.py": "def caller():\n    mystery()\n    print('x')\n"})
    result = build_graph(tmp_path, paths)
    assert _edges(result) == set()
    assert result.graph["files"]["a.py"]["unresolved"] == 1  # print is a builtin, not counted


def test_g3_class_edges(tmp_path):
    paths = _write(tmp_path, {
        "a.py": "from b import B\n\nclass C(B):\n    pass\n",
        "c.py": "from b import B\n\ndef make():\n    return B()\n",
        "b.py": "class B:\n    pass\n",
    })
    edges = _edges(build_graph(tmp_path, paths))
    assert (USES_CLASS, "a.C", "b.B") in edges
    assert (USES_CLASS, "c.make", "b.B") in edges


def test_relative_import_in_package(tmp_path):
    paths = _write(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/x.py": "from .y import g\n\ndef h():\n    g()\n",
        "pkg/y.py": "def g():\n    pass\n",
    })
    edges = _edges(build_graph(tmp_path, paths))
    assert (CALLS, "pkg.x.h", "pkg.y.g") in edges


def test_g4_delta_rereads_only_the_changed_file(tmp_path):
    paths = _write(tmp_path, {
        "a.py": "from b import f\n\ndef caller():\n    f()\n",
        "b.py": "def f():\n    pass\n",
        "c.py": "def lone():\n    pass\n",
    })
    first = build_graph(tmp_path, paths)
    assert first.reread == 3
    (tmp_path / "c.py").write_text("def lone():\n    return 2\n", encoding="utf-8")
    second = build_graph(tmp_path, paths, old=first.graph)
    assert second.reread == 1
    assert second.graph["files"]["a.py"]["edges"] == first.graph["files"]["a.py"]["edges"]


def test_delta_drops_deleted_files_and_their_edges(tmp_path):
    paths = _write(tmp_path, {
        "a.py": "from b import f\n\ndef caller():\n    f()\n",
        "b.py": "def f():\n    pass\n",
    })
    first = build_graph(tmp_path, paths)
    second = build_graph(tmp_path, ["a.py"], old=first.graph)
    assert "b.py" not in second.graph["files"]
    assert _edges(second) == set()  # the link to b is gone, a's call is now unresolved
    assert second.graph["files"]["a.py"]["unresolved"] == 1


def test_g5_syntax_error_is_skipped_with_reason(tmp_path):
    paths = _write(tmp_path, {"bad.py": "def (:\n", "ok.py": "def f():\n    pass\n"})
    result = build_graph(tmp_path, paths)
    assert len(result.skipped) == 1 and result.skipped[0].startswith("bad.py: SyntaxError")
    assert "ok.py" in result.graph["files"]


def test_progress_is_reported(tmp_path):
    paths = _write(tmp_path, {"a.py": "x = 1\n", "b.py": "y = 2\n"})
    seen = []
    build_graph(tmp_path, paths, progress=lambda done, total: seen.append((done, total)))
    assert seen == [(1, 2), (2, 2)]


def test_save_and_load_round_trip_and_damaged_file(tmp_path):
    paths = _write(tmp_path, {"a.py": "x = 1\n"})
    graph = build_graph(tmp_path, paths).graph
    save_graph(graph, tmp_path / "out")
    assert load_graph(tmp_path / "out") == graph
    (tmp_path / "out" / "da_code_graph.json").write_text("{nope", encoding="utf-8")
    assert load_graph(tmp_path / "out") is None
    assert load_graph(tmp_path / "missing") is None


def test_g25_big_graph_loads_under_two_seconds(tmp_path):
    files = {}
    for n in range(5000):
        edges = [["calls", f"m{n}.f", f"m{(n + k) % 5000}.f"] for k in range(1, 4)]
        files[f"m{n}.py"] = {
            "hash": "h", "module": f"m{n}", "defs": {"f": "function"}, "refs": [],
            "edges": edges + ([["imports", f"m{n}", f"m{(n + 9) % 5000}"]] if n % 3 else []),
            "unresolved": 0,
        }
    save_graph({"version": 1, "files": files}, tmp_path)
    started = time.perf_counter()
    graph = load_graph(tmp_path)
    assert time.perf_counter() - started < 2
    assert sum(len(f["edges"]) for f in graph["files"].values()) >= 17000


def test_a_graph_entry_without_a_module_is_treated_as_damaged(tmp_path):
    import json

    from agents.da_code_graph import GRAPH_NAME, load_graph

    (tmp_path / GRAPH_NAME).write_text(json.dumps({"files": {"a.py": {}}}), encoding="utf-8")

    assert load_graph(tmp_path) is None
