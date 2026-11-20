"""Fix G4 step 4c: re-check the "No capability fits" programs (S6, G4-14). Made-up only."""

import json
from datetime import datetime

from agents.da_admin_rebuild import _take_lock
from agents.da_admin_recheck import recheck_paths, start_recheck
from agents.da_admin_tag_store import read_tags, save_store
from agents.da_admin_tagger import ScriptedTaggerClient, text_hash
from db_table_functions.db_tbl_da_rulebook import get_active_version


def _entry(capability="", new_name="", state="proposed"):
    entry = {"summary": "Old.", "proposed_capability": capability, "confidence": "low",
             "reason": "r", "state": state, "file_hash": "x"}
    return {**entry, "new_name": new_name} if new_name else entry


GOOD = {"summary": "Now it fits.", "capability": "Uploads", "confidence": "high", "reason": "ok"}


class Spy(ScriptedTaggerClient):
    def __init__(self, replies):
        super().__init__(replies)
        self.asked = []

    def complete(self, prompt, system=None):
        self.asked.append(next(ln for ln in prompt.splitlines() if ln.startswith("Module: ")))
        return super().complete(prompt, system)


def _seed(tmp_path):
    save_store({"modules": {
        "none1.py": _entry(), "none2.py": _entry(),
        "has_cap.py": _entry("Uploads"), "suggest.py": _entry(new_name="Docs"),
        "done.py": _entry(state="rejected"),
    }, "runs": []}, tmp_path)


def test_only_the_no_fit_programs_are_picked(tmp_path):
    _seed(tmp_path)

    assert recheck_paths(tmp_path) == ["none1.py", "none2.py"]


def test_g4_14_recheck_sends_only_none_modules_and_takes_the_lock(
    db_path, published_rulebook, make_settings, tmp_path
):
    _seed(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    for name in ("none1.py", "none2.py"):
        (src / name).write_text("x = 1\n")
    settings = make_settings(codevision_src=str(src))
    policy = get_active_version(db_path).rulebook.policy
    policy = policy.model_copy(update={"index_folder_scope": str(src)})
    spy = Spy({"none1.py": GOOD, "none2.py": json.dumps(GOOD)})

    started, _ = start_recheck(policy, settings, "admin1", directory=tmp_path, wait=True,
                               client=spy)

    assert started and [a.removeprefix("Module: ") for a in spy.asked] == ["none1.py", "none2.py"]
    tags = read_tags(tmp_path)
    assert tags["none1.py"]["proposed_capability"] == "Uploads"
    assert tags["has_cap.py"]["summary"] == "Old."  # not sent
    assert text_hash("x = 1\n") == tags["none1.py"]["file_hash"]
    assert not (tmp_path / "da_code_index.lock").exists()  # freed


def test_a_second_job_is_refused_while_the_lock_is_held(
    db_path, published_rulebook, make_settings, tmp_path
):
    _seed(tmp_path)
    assert _take_lock(datetime.now(), tmp_path)
    policy = get_active_version(db_path).rulebook.policy

    started, text = start_recheck(policy, make_settings(), "admin1", directory=tmp_path,
                                  client=Spy({}))

    assert not started and "already running" in text
