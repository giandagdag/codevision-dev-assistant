"""Work embedder helper process (fix 11-3, AH-3, AH-4, AH-4b). A made-up CodeVision folder only."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import da_check_embedder
from agents import da_admin_rebuild as rebuild
from agents.da_admin_index import recent_runs
from agents.da_code_index import HELPER_DIED_MESSAGE, PIECES_NAME, WorkEmbedder
from db_table_functions.db_tbl_da_rulebook import SEED_RULEBOOK_FILE, load_rulebook_file

A_VECTOR = """
import os
from tools import payload_generation
from configs import llm_config

def create_embeddings(text):
    print("noise on stdout must not break the talk")
    if text == "NONE":
        return None
    if text == "DIE" and not os.path.exists(os.environ.get("DIE_MARK", "mark_once")):
        open("mark_once", "w").close()
        os._exit(1)
    if text == "DIE2":
        os._exit(1)
    return [[float(len(text)), float(llm_config.SIZE), float(payload_generation.TAG)]]
"""


def _codevision(tmp_path: Path, tools_extra: str = "") -> Path:
    """Fake CodeVision with the DA's package names (agents, configs) and a path with a space."""
    src = tmp_path / "CodeVision 61" / "imagebuild" / "src"
    for name in ("agents", "configs", "tools"):
        (src / name).mkdir(parents=True)
        (src / name / "__init__.py").write_text("", encoding="utf-8")
    (src / "agents" / "a_vector.py").write_text(A_VECTOR, encoding="utf-8")
    (src / "configs" / "llm_config.py").write_text("SIZE = 7\n", encoding="utf-8")
    tools_file = src / "tools" / "payload_generation.py"
    tools_file.write_text(tools_extra + "TAG = 5\n", encoding="utf-8")
    return src


def test_helper_imports_codevisions_packages_and_serves_many_texts(tmp_path):
    embedder = WorkEmbedder(str(_codevision(tmp_path)), sys.executable)
    try:
        assert embedder.embed("abc") == [3.0, 7.0, 5.0]  # DA's agents/configs have none of these
        pid = embedder._process.pid
        assert embedder.embed("abcd") == [4.0, 7.0, 5.0]
        assert embedder.embed("NONE") is None
        assert embedder._process.pid == pid  # one helper for the whole build
    finally:
        embedder.close()


def test_unset_or_wrong_folder_names_the_setting(tmp_path, monkeypatch):
    empty = SimpleNamespace(codevision_src="", codevision_python="")
    monkeypatch.setattr("agents.da_code_index.load_settings", lambda: empty)
    for src in ("", str(tmp_path / "nope")):
        with pytest.raises(RuntimeError, match="DA_CODEVISION_SRC"):
            WorkEmbedder(src).embed("SECRET-TEXT")


def test_missing_library_is_named_without_text(tmp_path):
    src = _codevision(tmp_path, tools_extra="import library_that_is_not_there\n")
    with pytest.raises(RuntimeError) as caught:
        WorkEmbedder(str(src), sys.executable).embed("SECRET-TEXT")
    message = str(caught.value)
    assert "library_that_is_not_there" in message and "DA_CODEVISION_PYTHON" in message
    assert "SECRET-TEXT" not in message


def test_helper_dies_once_is_restarted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # the fake writes its once-only marker in the helper's folder
    src = _codevision(tmp_path)
    monkeypatch.setenv("DIE_MARK", str(src / "mark_once"))
    embedder = WorkEmbedder(str(src), sys.executable)
    try:
        assert embedder.embed("DIE") == [3.0, 7.0, 5.0]
    finally:
        embedder.close()


def test_second_death_stops_the_build_and_old_index_stays(tmp_path):
    src = _codevision(tmp_path)
    source = tmp_path / "code"
    source.mkdir()
    (source / "a.py").write_text("def f():\n    return 'DIE2'\n", encoding="utf-8")
    out = tmp_path / "idx"
    out.mkdir()
    (out / PIECES_NAME).write_text("OLD", encoding="utf-8")
    policy = load_rulebook_file(SEED_RULEBOOK_FILE).policy.model_copy(
        update={"index_folder_scope": str(source), "index_exclusions": []}
    )
    embedder = WorkEmbedder(str(src), sys.executable)
    # every text contains the piece path, so "DIE2" never matches exactly: force the death text
    embedder.embed = _always_die(embedder)
    rebuild.start_rebuild(policy, "Admin", embedder=embedder, directory=out, wait=True)
    row = recent_runs(out)[0]
    assert not row["saved"] and HELPER_DIED_MESSAGE in row["message"]
    assert (out / PIECES_NAME).read_text(encoding="utf-8") == "OLD"
    assert not (out / rebuild.LOCK_NAME).exists()


def _always_die(embedder):
    real = embedder.embed
    return lambda _text: real("DIE2")


def test_check_command_prints_size_and_time_only(tmp_path):
    shown: list[str] = []
    embedder = WorkEmbedder(str(_codevision(tmp_path)), sys.executable)
    assert da_check_embedder.check(embedder, say=shown.append) == 0
    assert "vector size 3" in shown[0] and "hello" not in shown[0]


def test_check_command_says_the_real_error(tmp_path):
    shown: list[str] = []
    assert da_check_embedder.check(WorkEmbedder(str(tmp_path / "nope")), say=shown.append) == 1
    assert "DA_CODEVISION_SRC" in shown[0]
