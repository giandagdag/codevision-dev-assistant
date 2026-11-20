"""Fix G1: one number per build (F5) and links cards after a tag run (F6). Made-up modules only."""

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agents import da_admin_rebuild as rebuild
from agents.da_admin_index import recent_runs
from agents.da_admin_tag_cards import ai_cards, reject_card
from agents.da_admin_tag_store import save_store
from agents.da_admin_tagger import ScriptedTaggerClient, text_hash
from agents.da_code_index import PIECES_NAME, FakeEmbedder
from agents.da_index_builds import (
    build_confirm_text,
    build_numbers,
    current_build,
    read_manifest,
)
from agents.da_tag_versions import restore_confirm_text, save_version
from db_table_functions.db_tbl_da_rulebook import SEED_RULEBOOK_FILE, load_rulebook_file


def _source(tmp_path, names=("a", "b", "c", "d")):
    """hub imports every other module and each of them imports hub (one link cluster)."""
    source = tmp_path / "code"
    source.mkdir(exist_ok=True)
    (source / "hub.py").write_text("".join(f"import {n}\n" for n in names), encoding="utf-8")
    for n in names:
        (source / f"{n}.py").write_text("import hub\n", encoding="utf-8")
    seed = load_rulebook_file(SEED_RULEBOOK_FILE).policy
    return seed.model_copy(update={"index_folder_scope": str(source), "index_exclusions": []})


def _rebuild(policy, out, client=None, settings=None):
    return rebuild.start_rebuild(
        policy, "Admin", embedder=FakeEmbedder(), directory=out, wait=True,
        settings=settings, tag_client=client,
    )


def test_g1_6_a_taken_number_is_never_overwritten(tmp_path):
    out = tmp_path / "idx"
    _rebuild(_source(tmp_path), out)  # build 1 is saved
    taken = out / "da_code_index_builds" / "6"
    taken.mkdir()
    (taken / "manifest.json").write_text('{"build": 6, "pieces": 99}', encoding="utf-8")
    before = (taken / "manifest.json").read_bytes()
    summary = SimpleNamespace(saved=True, link_skipped=[], mode="full")
    extra: dict = {}

    words = rebuild._save_build_copy(summary, out, 6, "Admin", rebuild.datetime.now(), extra)

    assert build_numbers(out) == [1, 6, 7] and (taken / "manifest.json").read_bytes() == before
    assert read_manifest(out, 7)["build"] == 7 and extra["build"] == 7
    assert json.loads((out / PIECES_NAME).read_text())["build"] == 7 == current_build(out)
    assert "Build 6 was already saved, so this is build 7." in words


def test_g1_4_use_build_confirm_names_the_build():
    manifest = {"build": 5, "time": "2026-11-20T03:10:00+08:00", "mode": "delta", "pieces": 1234}
    assert build_confirm_text(manifest, 5) == (
        "Use build 5 (20 Nov 03:10 SGT, Delta, 1,234 pieces)?"
    )
    assert build_confirm_text(None, 5) == "Use build 5?"
    # A damaged manifest (no time, or a time that cannot be read) still opens the box.
    assert build_confirm_text({"build": 5}, 5) == "Use build 5?"
    assert build_confirm_text({"time": "not a time"}, 5) == "Use build 5?"


def test_g1_5_restore_confirm_names_the_tag_version(tmp_path):
    when = datetime.fromisoformat("2026-11-20T02:40:00+08:00")
    save_version("Approve all", "admin1", tmp_path, when)
    assert restore_confirm_text(1, tmp_path) == (
        "Restore tag version 1 (20 Nov 02:40 SGT, Approve all by admin1)?"
    )
    assert restore_confirm_text(9, tmp_path) == "Restore tag version 9?"


def test_g1_5_a_damaged_tag_row_still_opens_the_restore_box(tmp_path):
    save_version("Approve all", "admin1", tmp_path, datetime.fromisoformat("2026-11-20T02:40:00"))
    assert restore_confirm_text(1, tmp_path)  # sanity: a good row names its time
    with patch("agents.da_tag_versions.list_versions", return_value=[{"version": 3}]):
        assert restore_confirm_text(3, tmp_path) == "Restore tag version 3?"


def test_g1_9_the_work_note_has_the_map_wiring_and_the_pip_line():
    text = (Path(__file__).parents[1] / "docs" / "build-work-test.md").read_text(encoding="utf-8")
    assert "map_shell()" in text and "pip install -r requirements.txt" in text
    assert "dash-cytoscape" in text


def test_g1_7_links_card_is_back_after_a_tag_run_and_a_rejected_one_is_not(
    tmp_path, make_settings
):
    policy = _source(tmp_path)
    capability = policy.capabilities[0].name
    tagged = {"summary": "x", "capability": capability, "confidence": "high", "reason": "ok"}
    untagged = {**tagged, "capability": "none"}
    client = ScriptedTaggerClient(
        {f"{n}.py": tagged for n in "abcd"} | {"hub.py": untagged}
    )
    out = tmp_path / "idx"
    # a to d are approved by Admin (same code, so the tag run keeps them); hub is the untagged one
    approved = {"state": "approved", "proposed_capability": capability,
                "file_hash": text_hash("import hub\n")}  # fmt: skip
    save_store({"modules": {f"{n}.py": dict(approved) for n in "abcd"}, "runs": []}, out)

    def links_cards():
        return {c.path for c in ai_cards(out) if c.reason.startswith("Suggested from code links")}

    _rebuild(policy, out, client, make_settings())
    assert "hub.py" in links_cards()

    _rebuild(policy, out, client, make_settings())  # the tag run rewrites hub's tag entry
    assert "hub.py" in links_cards()
    assert "capability suggestions from code links" in recent_runs(out)[0]["message"]

    reject_card("hub.py", out)
    _rebuild(policy, out, client, make_settings())
    assert "hub.py" not in links_cards()
