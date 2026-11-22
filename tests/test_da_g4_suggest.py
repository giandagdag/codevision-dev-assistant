"""Fix G4 step 4a: the AI may suggest a new capability (S1 to S3, S7). Made-up only, no real AI."""

import json

from agents.da_admin_tag_store import read_store, read_tags
from agents.da_admin_tagger import (
    FAKE_SCRIPT_FILE,
    PROMPT_FILE,
    ScriptedTaggerClient,
    group_new_names,
    parse_reply,
    run_tagging,
)
from pydantic_classes.da_rulebook_models import Capability

CAPS = [Capability(name="Reports", description="Reports.", named_senior="s1",
                   path_patterns=["*report*"])]


def reply(**more) -> str:
    base = {"summary": "Does a thing.", "capability": "new", "confidence": "high", "reason": "ok",
            "new_name": "Document export", "new_description": "Writes documents."}
    return json.dumps({**base, **more})


def test_s1_prompt_offers_new():
    assert "or new" in PROMPT_FILE.read_text(encoding="utf-8")


def test_s2_valid_new_is_kept_with_name_and_description():
    got = parse_reply(reply(), CAPS)
    assert got["capability"] == "new"
    assert (got["new_name"], got["new_description"]) == ("Document export", "Writes documents.")


def test_s2_bad_new_is_skipped():
    for bad in (
        {"new_name": "src/agents/x.py"}, {"new_name": "A"}, {"new_name": "x" * 41},
        {"new_description": ""}, {"new_name": 5},  # a 121-character description is now cut (G5)
    ):
        assert parse_reply(reply(**bad), CAPS) is None
    no_fields = json.loads(reply())
    del no_fields["new_name"]
    assert parse_reply(json.dumps(no_fields), CAPS) is None


def test_s2_known_name_becomes_a_normal_proposal():
    got = parse_reply(reply(new_name=" reports "), CAPS)
    assert got["capability"] == "Reports" and got["new_name"] == ""


def test_s3_same_name_is_merged_under_the_first_spelling():
    entries = {"a": {"new_name": "Document export"}, "b": {"new_name": "document  exports"},
               "c": {"new_name": "Other area"}, "d": {}}
    group_new_names(entries, [])
    assert [e.get("new_name") for e in entries.values()] == [
        "Document export", "Document export", "Other area", None]


def test_s3_a_waiting_suggestion_keeps_its_name():
    entries = {"a": {"new_name": "document exports"}}
    group_new_names(entries, ["Document export"])
    assert entries["a"]["new_name"] == "Document export"


def test_s7_fake_script_groups_three_modules_and_skips_the_bad_one(tmp_path):
    script = json.loads(FAKE_SCRIPT_FILE.read_text(encoding="utf-8"))["new_replies"]
    script.pop("_about")
    plain = {"summary": "Pad.", "capability": "none", "confidence": "low", "reason": "-"}
    for n in range(7):  # pad: one bad reply in 11 is under the 10% limit
        script[f"pad{n}.py"] = plain
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    for path in script:
        (src / path).parent.mkdir(parents=True, exist_ok=True)
        (src / path).write_text("x = 1\n")
    paths = sorted(script)

    run = run_tagging(paths, src, CAPS, ScriptedTaggerClient(script), "admin1", directory=out)

    tags = read_tags(out)
    names = {t["new_name"] for t in tags.values() if t.get("new_name")}
    assert names == {"Document Export"}  # first spelling seen (notes_clean sorts first)
    assert sum(1 for t in tags.values() if t.get("new_name")) == 3
    assert run.saved and run.skipped == ["src/agents/notes_bad.py"]
    assert read_store(out)["runs"][0]["skipped"] == ["src/agents/notes_bad.py"]
