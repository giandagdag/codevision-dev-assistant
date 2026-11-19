"""Upgrade G step 3: compare builds (G-17), roll back the index (G-19, G-20). Made-up code only."""

import json
from datetime import datetime

from agents import da_admin_rebuild as rebuild
from agents.da_admin_audit import INDEX_ROLLED_BACK, read_admin_events
from agents.da_admin_index import recent_runs, run_line
from agents.da_code_index import PIECES_NAME, FakeEmbedder
from agents.da_index_builds import build_numbers, compare_builds, compare_text, has_copy
from agents.da_index_rollback import BUSY, roll_back
from db_table_functions.db_tbl_da_rulebook import SEED_RULEBOOK_FILE, load_rulebook_file


def _policy(source):
    seed = load_rulebook_file(SEED_RULEBOOK_FILE).policy
    return seed.model_copy(update={"index_folder_scope": str(source), "index_exclusions": []})


def _build(source, out, files: dict[str, str]):
    for name, text in files.items():
        (source / name).write_text(text, encoding="utf-8")
    rebuild.start_rebuild(
        _policy(source), "Admin", embedder=FakeEmbedder(), directory=out, wait=True
    )


def _seven_builds(tmp_path):
    source, out = tmp_path / "code", tmp_path / "idx"
    source.mkdir()
    for n in range(7):
        files = {"a.py": f"def f():\n    return {n}\n"}
        if n == 5:
            files["extra.py"] = "def g():\n    pass\n"  # only builds 6 and 7 have this module
        _build(source, out, files)
    return out


def test_g17_compare_lists_added_removed_changed(tmp_path):
    out = _seven_builds(tmp_path)
    result = compare_builds(out, 5, 6)
    assert result["added"] == ["extra.py"] and result["changed"] == ["a.py"]
    assert result["removed"] == [] and result["pieces"] > 0
    assert compare_builds(out, 6, 5)["removed"] == ["extra.py"]
    assert "1 modules added" in compare_text(result, 5, 6)
    assert compare_builds(out, 5, 99) is None
    assert "no saved manifest" in compare_text(None, 5, 99)


def test_g19_roll_back_restores_files_audits_and_logs(tmp_path):
    out = _seven_builds(tmp_path)
    copy = (out / "da_code_index_builds" / "5" / PIECES_NAME).read_bytes()
    ok, text = roll_back(out, 5, "Admin", datetime(2026, 11, 20, 10, 0))
    assert ok and text == "Rolled back to build 5"
    assert (out / PIECES_NAME).read_bytes() == copy
    assert json.loads(copy)["build"] == 5
    assert [e["kind"] for e in read_admin_events(out)] == [INDEX_ROLLED_BACK]
    assert "Rolled back to build 5" in run_line(recent_runs(out)[0])
    assert build_numbers(out) == [1, 2, 3, 4, 5, 6, 7] and has_copy(out, 7)  # nothing deleted
    assert not rebuild._lock_path(out).exists()


def test_roll_back_refused_without_a_copy(tmp_path):
    out = _seven_builds(tmp_path)
    ok, text = roll_back(out, 1, "Admin")
    assert not ok and "no saved copy" in text and read_admin_events(out) == []


def test_g20_roll_back_refused_while_a_job_runs(tmp_path):
    out = _seven_builds(tmp_path)
    before = (out / PIECES_NAME).read_bytes()
    now = datetime.now()
    assert rebuild._take_lock(now, out)
    ok, text = roll_back(out, 5, "Admin", now)
    assert not ok and text == BUSY
    assert (out / PIECES_NAME).read_bytes() == before
    assert rebuild._lock_path(out).exists()  # the running job's lock is not ours to free
