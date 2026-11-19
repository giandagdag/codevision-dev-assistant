"""Upgrade G step 6: tag versions and Restore T (G-23). Made-up only."""

from datetime import datetime

from agents.da_admin_audit import read_admin_events
from agents.da_admin_rebuild import _take_lock
from agents.da_admin_tag_cards import approve_all_high, approve_card, reject_card
from agents.da_admin_tag_store import read_tags, save_store
from agents.da_tag_versions import (
    compare_text,
    compare_versions,
    list_versions,
    restore_version,
)
from callbacks.screen_callbacks.da_admin_tag_history_callbacks import compare_action
from layouts.da_admin_tag_history_panel import version_options

ADMIN = "admin-0001"


def _entry(capability, confidence="high"):
    return {
        "summary": "x", "proposed_capability": capability, "confidence": confidence,
        "reason": "because", "state": "proposed",
    }


def test_g23_approve_all_saves_a_version_and_restore_brings_old_tags_back(
    db_path, published_rulebook, make_settings, tmp_path
):
    save_store({"modules": {f"zz/m{n}.py": _entry("Uploads") for n in range(12)}, "runs": []},
               tmp_path)
    assert list_versions(tmp_path) == []

    approve_all_high(make_settings(), ADMIN, 1, directory=tmp_path)

    start, approved = list_versions(tmp_path)[::-1]  # version 1 is the tags BEFORE the Approve all
    assert start["version"] == 1 and start["who"] == "system"
    assert approved["version"] == 2 and approved["who"] == ADMIN
    assert approved["note"] == "AI scan: 12 programs approved (high confidence)"
    reject_card("zz/m0.py", tmp_path, ADMIN)  # a later change, as version 3
    assert [v["version"] for v in list_versions(tmp_path)] == [3, 2, 1]

    ok, text = restore_version(2, ADMIN, tmp_path)

    assert ok and "version 4" in text
    newest = list_versions(tmp_path)[0]
    assert newest["version"] == 4 and newest["note"] == "Restored from 2"
    assert read_tags(tmp_path)["zz/m0.py"]["state"] == "approved"  # the rejection is undone
    (event,) = read_admin_events(tmp_path)
    assert event["kind"] == "tags_restored" and event["who"] == ADMIN
    assert restore_version(1, ADMIN, tmp_path)[0]  # and the first Approve all can be undone too
    assert read_tags(tmp_path)["zz/m0.py"]["state"] == "proposed"


def test_assign_to_saves_the_chosen_capability_and_compare_lists_what_moved(
    db_path, published_rulebook, make_settings, tmp_path
):
    save_store({"modules": {"zz/a.py": _entry("Uploads")}, "runs": []}, tmp_path)
    approve_card(make_settings(), "zz/a.py", "Uploads", ADMIN, 1, directory=tmp_path)
    store = {"modules": {**read_tags(tmp_path), "zz/b.py": _entry("Nothing fits")}, "runs": []}
    save_store(store, tmp_path)  # a new proposal; Admin assigns it to Uploads (not the AI's pick)
    approve_card(make_settings(), "zz/b.py", "Uploads", ADMIN, 2, directory=tmp_path)

    diff = compare_versions(2, 3, tmp_path)  # 1 = starting tags, 2 = a approved, 3 = b assigned

    assert read_tags(tmp_path)["zz/b.py"]["proposed_capability"] == "Uploads"
    assert diff == {"added": ["zz/b.py"], "removed": [], "moved": []}
    assert "1 added (zz/b.py)" in compare_text(diff, 2, 3)
    assert compare_versions(1, 99, tmp_path) is None
    assert compare_action("1", None) == "Pick two versions to compare."
    assert len(version_options(tmp_path)) == 3


def test_restore_is_refused_while_a_job_runs_and_for_a_missing_version(tmp_path):
    save_store({"modules": {"zz/a.py": _entry("Uploads")}, "runs": []}, tmp_path)
    assert restore_version(7, ADMIN, tmp_path) == (False, "Tag version 7 was not found.")
    reject_card("zz/a.py", tmp_path, ADMIN)
    assert _take_lock(datetime.now(), tmp_path)

    ok, text = restore_version(1, ADMIN, tmp_path)

    assert not ok and text.startswith("A rebuild or tag job is running")
    assert read_admin_events(tmp_path) == []
