"""Fix G6 M4: the tagger's `also` becomes its own "Also add ... ?" card (G6-8). Made-up only."""

import json

from agents.da_admin_tag_cards import (
    also_cards,
    approve_all_high,
    approve_also,
    reject_also,
)
from agents.da_admin_tag_store import read_tags, save_store
from agents.da_admin_tagger import read_reply
from db_table_functions.db_tbl_da_rulebook import get_active_version, list_versions
from pydantic_classes.da_rulebook_models import Capability

ADMIN = "admin-0001"


def _reply(**extra) -> str:
    base = {"summary": "Does a thing.", "capability": "Uploads", "confidence": "high"}
    return json.dumps({**base, **extra})


def _caps():
    return [Capability(name=n, description="d", named_senior="Ana", path_patterns=["x/*.py"])
            for n in ("Uploads", "Reports")]  # fmt: skip


def test_the_reply_keeps_one_exact_also_name_and_drops_the_rest():
    assert read_reply(_reply(also="reports"), _caps())[0]["also"] == "Reports"
    assert read_reply(_reply(also="Nonsense"), _caps())[0]["also"] == ""
    assert read_reply(_reply(), _caps())[0]["also"] == ""


def test_g6_8_also_card_shows_and_approve_all_does_not_take_it(
    db_path, published_rulebook, make_settings, tmp_path
):
    save_store({"runs": [], "modules": {"zz/a.py": {
        "summary": "s", "proposed_capability": "Uploads", "confidence": "high",
        "reason": "", "state": "proposed", "also": "Reports"}}}, tmp_path)  # fmt: skip
    cards = also_cards(tmp_path)
    approve_all_high(make_settings(), ADMIN, 1, directory=tmp_path)

    assert [(c.path, c.capability) for c in cards] == [("zz/a.py", "Reports")]
    assert len(list_versions(db_path)) == 2  # only the main approval; no also-add version
    assert read_tags(tmp_path)["zz/a.py"].get("also") == "Reports"  # card still open


def test_add_saves_one_version_and_reject_just_closes(
    db_path, published_rulebook, make_settings, tmp_path
):
    other = get_active_version(db_path).rulebook.policy.capabilities[0].name
    entry = {"summary": "s", "proposed_capability": "", "confidence": "low", "reason": "",
             "state": "proposed", "also": other}
    save_store({"runs": [], "modules": {"zz/a.py": entry, "zz/b.py": dict(entry)}}, tmp_path)

    result = approve_also(make_settings(), "zz/a.py", other, ADMIN, 1, tmp_path)
    reject_also("zz/b.py", tmp_path)

    assert result.kind == "resolved" and result.new_version == 2
    assert also_cards(tmp_path) == []
    assert "also add zz/a.py" in get_active_version(db_path).change_note
