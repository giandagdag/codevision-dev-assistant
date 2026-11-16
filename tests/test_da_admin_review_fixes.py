"""Phase 11 fix 2, review rounds 1 and 2: tests for the fixes. Made-up data only."""

import json
from datetime import datetime, timedelta

from agents.da_admin_rebuild import TAGGER_LOCK_NAME, _take_lock, running_since
from agents.da_admin_tag_cards import approve_card, reject_card
from agents.da_admin_tag_store import read_tags, save_store
from agents.da_admin_tagger import ScriptedTaggerClient, paths_to_tag, run_tagging, text_hash
from callbacks.screen_callbacks.da_admin_scan_callbacks import confirm_state
from layouts.da_admin_scan_controls import HIDDEN, SCAN_NEW_BTN, SHOWN
from pydantic_classes.da_rulebook_models import Capability

CAPS = [Capability(name="Reports", description="Reports.", named_senior="s3", path_patterns=["*report*"])]
GOOD = {"summary": "Does a thing.", "capability": "Reports", "confidence": "high", "reason": "ok"}


class RejectsWhileScanning(ScriptedTaggerClient):
    """Admin rejects the card for m0.py while the scan is still running."""

    def __init__(self, out):
        super().__init__({"m0.py": json.dumps(GOOD)})
        self.out = out

    def complete(self, prompt, system=None):
        reject_card("m0.py", self.out)
        return super().complete(prompt, system)


def test_a_card_rejected_during_a_scan_stays_rejected(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    (src / "m0.py").write_text("x = 1\n")
    entry = {"file_hash": text_hash("x = 1\n"), "summary": "Old.", "proposed_capability": "Reports",
             "confidence": "high", "reason": "r", "state": "proposed"}
    save_store({"modules": {"m0.py": entry}, "runs": []}, out)

    run_tagging(["m0.py"], src, CAPS, RejectsWhileScanning(out), "admin1", directory=out)

    # the code is unchanged, so the decision made during the scan survives it
    assert read_tags(out)["m0.py"]["state"] == "rejected"


def test_programs_never_sent_do_not_use_up_places(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("x = 2\n")
    paths = ["da_secret_tool.py", "skip/me.py", "a.py", "b.py"]

    todo, waiting = paths_to_tag(
        paths, {"modules": {}}, tmp_path, False, 2, exclusions=["skip/*"]
    )

    assert todo == ["a.py", "b.py"] and waiting == 0


def test_untagged_programs_go_first(tmp_path):
    store = {"modules": {"a.py": {"file_hash": "x"}}}

    todo, waiting = paths_to_tag(["a.py", "b.py"], store, tmp_path, False, 1)

    assert todo == ["b.py"] and waiting == 1


def test_a_three_hour_old_scan_lock_still_counts_but_a_day_old_one_does_not(tmp_path):
    started = datetime.now()
    assert _take_lock(started, tmp_path, TAGGER_LOCK_NAME)

    three = running_since(started + timedelta(hours=3), tmp_path, TAGGER_LOCK_NAME)
    assert three == started.replace(microsecond=0)
    assert running_since(started + timedelta(hours=13), tmp_path, TAGGER_LOCK_NAME) is None


def test_approving_a_path_another_capability_holds_names_that_capability(
    published_rulebook, make_settings, tmp_path
):
    # "src/agents/limits_batch.py" is already matched by the seeded catalog
    path = "src/agents/limits_batch.py"
    entry = {"summary": "s", "proposed_capability": "Uploads", "confidence": "high",
             "reason": "r", "state": "proposed"}
    save_store({"modules": {path: entry}, "runs": []}, tmp_path)

    result = approve_card(make_settings(), path, "Uploads", "admin-0001", 1, directory=tmp_path)

    assert result.kind == "resolved" and result.new_version is None
    assert "already matches" in result.message


def test_the_confirm_box_text_follows_the_button():
    assert confirm_state(SCAN_NEW_BTN) == (True, "new", HIDDEN, SHOWN)
    assert confirm_state("adm-scan-all-btn") == (True, "all", SHOWN, HIDDEN)
