"""Fix G5 step 7c (R8, R9): the start-up storage line, and the re-check tries unreadable again."""

import json
from pathlib import Path

from agents.da_admin_index import storage_line
from agents.da_admin_recheck import recheck_paths, start_recheck
from agents.da_admin_tag_store import read_tags
from tests.test_da_admin_tagger_job import GOOD, _job, _setup


def test_storage_line_names_index_folder_and_database_only(monkeypatch, tmp_path):
    monkeypatch.setenv("DA_CODE_INDEX_DIR", str(tmp_path / "idx"))

    line = storage_line(Path("data/devassist.db"))

    assert str(tmp_path / "idx") in line and "devassist.db" in line


def test_recheck_tries_unreadable_programs_again(tmp_path, make_settings):
    policy, _, _ = _setup(tmp_path)
    out = tmp_path / "idx"

    class Down:
        def complete(self, prompt, system=None):
            raise RuntimeError("down")

    class Reply:
        text = json.dumps(GOOD)

    class Up:
        def complete(self, prompt, system=None):
            return Reply()

    _job(policy, out, Down(), make_settings())
    assert recheck_paths(out) == ["m0.py", "m1.py", "m2.py"]  # unreadable ones are in the list

    started, _ = start_recheck(policy, make_settings(), "admin1", directory=out, wait=True,
                               client=Up())

    assert started and "unreadable" not in {t["state"] for t in read_tags(out).values()}
