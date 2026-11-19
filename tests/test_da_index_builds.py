"""Upgrade G step 2: code links inside the rebuild job, build numbers, saved copies (G-18).

Fake embedder only, made-up modules, tmp_path."""

import json
from datetime import datetime

from agents import da_admin_job as job
from agents import da_admin_rebuild as rebuild
from agents.da_admin_index import recent_runs, run_line
from agents.da_code_graph import load_graph
from agents.da_code_index import PIECES_NAME, FakeEmbedder
from agents.da_index_builds import (
    KEPT_INDEX_COPIES,
    build_numbers,
    has_copy,
    next_build_number,
    read_manifest,
)
from db_table_functions.db_tbl_da_rulebook import SEED_RULEBOOK_FILE, load_rulebook_file


def _source(tmp_path):
    source = tmp_path / "code"
    source.mkdir()
    (source / "a.py").write_text("from b import f\n\ndef caller():\n    f()\n", encoding="utf-8")
    (source / "b.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    return source


def _policy(source):
    seed = load_rulebook_file(SEED_RULEBOOK_FILE).policy
    return seed.model_copy(update={"index_folder_scope": str(source), "index_exclusions": []})


def _rebuild(policy, out, mode="full"):
    return rebuild.start_rebuild(
        policy, "Admin", embedder=FakeEmbedder(), directory=out, wait=True, mode=mode
    )


def test_rebuild_saves_graph_manifest_and_build_number(tmp_path):
    source, out = _source(tmp_path), tmp_path / "idx"
    _rebuild(_policy(source), out)
    graph = load_graph(out)
    assert ["calls", "a.caller", "b.f"] in graph["files"]["a.py"]["edges"]
    manifest = read_manifest(out, 1)
    assert manifest["mode"] == "full" and manifest["modules"] == 2 and manifest["edges"] == 2
    assert set(manifest["files"]) == {"a.py", "b.py"}
    assert json.loads((out / PIECES_NAME).read_text())["build"] == 1
    assert has_copy(out, 1)
    assert "(Build 1)" in run_line(recent_runs(out)[0])


def test_delta_build_gets_next_number_and_keeps_links(tmp_path):
    source, out = _source(tmp_path), tmp_path / "idx"
    _rebuild(_policy(source), out)
    (source / "b.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    _rebuild(_policy(source), out, "delta")
    assert build_numbers(out) == [1, 2] and next_build_number(out) == 3
    assert read_manifest(out, 2)["mode"] == "delta"
    assert ["calls", "a.caller", "b.f"] in load_graph(out)["files"]["a.py"]["edges"]


def test_g5_bad_file_is_listed_and_build_is_saved(tmp_path):
    source, out = _source(tmp_path), tmp_path / "idx"
    (source / "bad.py").write_text("def (:\n", encoding="utf-8")
    _rebuild(_policy(source), out)
    run = recent_runs(out)[0]
    assert run["saved"] and run["link_skipped"][0].startswith("bad.py: SyntaxError")
    assert read_manifest(out, 1) is not None


def test_g18_only_the_newest_five_builds_keep_copies(tmp_path):
    source, out = _source(tmp_path), tmp_path / "idx"
    for n in range(7):
        (source / "b.py").write_text(f"def f():\n    return {n}\n", encoding="utf-8")
        _rebuild(_policy(source), out)
    assert build_numbers(out) == [1, 2, 3, 4, 5, 6, 7]
    assert [has_copy(out, n) for n in range(1, 8)] == [False, False] + [True] * KEPT_INDEX_COPIES
    assert read_manifest(out, 1) is not None  # manifests are never dropped


def test_not_saved_run_takes_no_number(tmp_path):
    out = tmp_path / "idx"
    empty = tmp_path / "empty"
    empty.mkdir()
    _rebuild(_policy(empty), out)
    assert build_numbers(out) == [] and next_build_number(out) == 1


def test_job_panel_shows_graph_step_build_and_tagging_step_3():
    status = {"step": 2, "done": 3, "total": 10, "build": 4}
    line = job.progress_line(status)
    assert line.startswith("Build 4. Step 2 of 3: reading code links, 3 of 10 files")
    assert "Step 3 of 3: tagging programs" in job.progress_line({"step": 3, "done": 1, "total": 2})


def test_current_build_reads_the_pieces_record(tmp_path):
    from agents.da_code_index import PIECES_NAME
    from agents.da_index_builds import current_build

    assert current_build(tmp_path) is None  # no index
    (tmp_path / PIECES_NAME).write_text('{"build": 6, "pieces": []}', encoding="utf-8")
    assert current_build(tmp_path) == 6
    (tmp_path / PIECES_NAME).write_text('{"build": 0, "pieces": []}', encoding="utf-8")
    assert current_build(tmp_path) is None  # command-line build: not numbered


def test_job_status_carries_build_number(tmp_path):
    job.begin(tmp_path, datetime(2026, 11, 20, 9, 0), "Admin", "full", "Manual", 5)
    assert job.read_status(tmp_path)["build"] == 5
