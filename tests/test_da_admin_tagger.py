"""Phase 11 fix 2, step 3: the tagger core (AG-4, AG-5, AG-9, AG-10). Made-up only, no real AI."""

import json
from pathlib import Path

import pytest

from agents.da_admin_tag_store import read_store, read_tags
from agents.da_admin_tagger import (
    FAKE_SCRIPT_FILE,
    ScriptedTaggerClient,
    build_prompt,
    is_sendable,
    parse_reply,
    paths_to_tag,
    read_reply,
    run_tagging,
)
from pydantic_classes.da_rulebook_models import Capability

FAKE_ROOT = Path(__file__).resolve().parents[1] / "src" / "data" / "da_fake_codevision"
CAPS = [
    Capability(name="Limits", description="Customer limits.", named_senior="boss-secret-1",
               backup_senior="backup-secret-2", path_patterns=["*limits*"]),
    Capability(name="Reports", description="Reports.", named_senior="s3",
               path_patterns=["*report*"]),
]
GOOD = {"summary": "Does a thing.", "capability": "Reports", "confidence": "high",
        "reason": "ok"}


def fake_paths() -> list[str]:
    return sorted(p.relative_to(FAKE_ROOT).as_posix() for p in FAKE_ROOT.rglob("*.py"))


def test_ag4_every_module_gets_a_summary_and_matching_ones_are_matched(tmp_path):
    paths = fake_paths()

    run = run_tagging(paths, FAKE_ROOT, CAPS, ScriptedTaggerClient(), "admin1", directory=tmp_path)

    tags = read_tags(tmp_path)
    assert run.saved and set(tags) == set(paths) and all(t["summary"] for t in tags.values())
    assert tags["src/agents/limits_batch.py"]["state"] == "matched"
    assert tags["src/agents/docs_markdown_export.py"]["state"] == "proposed"
    assert tags["src/agents/docs_folder_to_md.py"]["proposed_capability"] == ""  # "none"
    assert read_store(tmp_path)["runs"][0]["scanned"] == len(paths)


def make_modules(tmp_path: Path, count: int) -> list[str]:
    for n in range(count):
        (tmp_path / f"m{n}.py").write_text(f"x = {n}\n")
    return [f"m{n}.py" for n in range(count)]


def scripted(paths: list[str], bad: int) -> ScriptedTaggerClient:
    replies = {p: (GOOD if n >= bad else "not json") for n, p in enumerate(paths)}
    return ScriptedTaggerClient(replies)


def test_ag5_one_bad_reply_in_20_is_skipped_and_named(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    paths = make_modules(src, 20)

    run = run_tagging(paths, src, CAPS, scripted(paths, 1), "admin1", directory=out)

    assert run.saved and run.skipped == ["m0.py"]
    tags = read_tags(out)
    assert len(tags) == 20 and tags["m0.py"]["state"] == "unreadable"  # Fix G5: saved as unreadable
    assert read_store(out)["runs"][0]["skipped"] == ["m0.py"]


def test_g5_8_most_bad_still_saves_the_good_tags_and_counts_the_reasons(tmp_path, caplog):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    paths = make_modules(src, 10)
    run_tagging(paths[:5], src, CAPS, scripted(paths, 0), "admin1", directory=out)  # old, good

    with caplog.at_level("INFO"):
        run = run_tagging(paths, src, CAPS, scripted(paths, 7), "admin1", directory=out)

    tags = read_tags(out)
    assert run.saved and run.reasons == {"no_json": 7}
    assert run.message == (
        "Tags: 3 of 10 tagged, 7 could not be read. Many programs could not be read: "
        "check the AI model."
    )
    assert "10 programs, 3 tagged, 7 could not be read (no_json 7)" in caplog.text
    assert "not json" not in caplog.text  # never the reply text
    # the first five were tagged before: a failed re-read never replaces a good tag
    assert all(tags[p]["state"] != "unreadable" for p in paths[:5])
    assert [p for p in paths[5:7] if tags[p]["state"] == "unreadable"] == paths[5:7]
    assert tags["m8.py"]["summary"] == GOOD["summary"]
    assert tags["m5.py"]["summary"] == "AI could not read this program"
    assert tags["m5.py"]["reason"] == "no_json"


def test_g5_7_a_reply_with_no_json_is_asked_twice_then_unreadable(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    prompts = []

    class Silent(ScriptedTaggerClient):
        def complete(self, prompt, system=None):
            prompts.append(prompt)
            return super().complete(prompt)

    client = Silent({"a.py": "sorry"})
    run = run_tagging(["a.py"], tmp_path, CAPS, client, "a", directory=tmp_path / "o")

    assert len(prompts) == 2 and prompts[1].endswith("Reply with the JSON object only.")
    assert "Reply with the JSON" not in prompts[0]
    assert run.skipped == ["a.py"] and read_tags(tmp_path / "o")["a.py"]["state"] == "unreadable"


def test_g5_an_unreadable_program_is_a_card_and_is_tried_again_in_delta(tmp_path):
    from agents.da_admin_tag_cards import ai_cards

    (tmp_path / "a.py").write_text("x = 1\n")
    out = tmp_path / "o"
    client = ScriptedTaggerClient({"a.py": "sorry"})
    run_tagging(["a.py"], tmp_path, CAPS, client, "a", directory=out)

    (card,) = ai_cards(out)
    assert (card.unreadable, card.summary, card.reason) == (
        True, "AI could not read this program", "no_json",
    )
    todo, _ = paths_to_tag(["a.py"], read_store(out), tmp_path, only_changed=True, limit=10)
    assert todo == ["a.py"]  # the code did not change, but it was never read


def test_a_failed_call_is_not_asked_twice_and_is_named(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    calls = []

    class Down:
        def complete(self, prompt, system=None):
            calls.append(1)
            raise ConnectionError("down")

    run = run_tagging(["a.py"], tmp_path, CAPS, Down(), "a", directory=tmp_path / "o")

    assert len(calls) == 1 and run.reasons == {"call_failed": 1}


def test_g5_6_five_odd_replies_are_all_tagged_and_cleaned(tmp_path):
    new = {"capability": "new", "new_name": "Upload & Ingestion", "new_description": "Files in."}
    replies = {
        "a.py": "Sure! Here is the tag: " + json.dumps(GOOD) + " Hope it helps.",
        "b.py": "<think>hmm {not json}</think>\n" + json.dumps(GOOD),
        "c.py": json.dumps({**GOOD, "summary": "word " * 30, "reason": "r " * 100}),
        "d.py": json.dumps({**GOOD, "confidence": "High", "capability": " reports "}),
        "e.py": json.dumps({**GOOD, **new}),
    }
    for name in replies:
        (tmp_path / name).write_text("x = 1\n")

    run = run_tagging(list(replies), tmp_path, CAPS, ScriptedTaggerClient(replies), "a",
                      directory=tmp_path / "o")

    tags = read_tags(tmp_path / "o")
    assert run.skipped == [] and set(tags) == set(replies)
    assert len(tags["c.py"]["summary"]) <= 120 and tags["c.py"]["summary"].endswith("...")
    assert len(tags["c.py"]["reason"]) <= 160 and tags["c.py"]["reason"].endswith("...")
    assert (tags["d.py"]["confidence"], tags["d.py"]["proposed_capability"]) == ("high", "Reports")
    assert tags["e.py"]["new_name"] == "Upload and Ingestion"


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ({**GOOD, "capability": "Invented"}, "bad_capability"),
        ({**GOOD, "confidence": "certain"}, "bad_confidence"),
        ({**GOOD, "summary": " "}, "empty_summary"),
        ({**GOOD, "capability": "new", "new_name": "x", "new_description": "d"}, "bad_new_name"),
        ({**GOOD, "capability": "new", "new_name": "n" * 41, "new_description": "d"}, "bad_new_name"),  # noqa: E501
    ],
)
def test_each_refusal_has_one_reason_word(reply, reason):
    assert read_reply(json.dumps(reply), CAPS) == (None, reason)


def test_ag9_an_unchanged_file_is_not_sent_again(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    paths = make_modules(src, 3)
    run_tagging(paths, src, CAPS, scripted(paths, 0), "admin1", directory=out)
    (src / "m1.py").write_text("x = 'changed'\n")

    todo, waiting = paths_to_tag(paths, read_store(out), src, only_changed=True, limit=500)

    assert (todo, waiting) == (["m1.py"], 0)
    assert paths_to_tag(paths, read_store(out), src, False, 2) == (paths[:2], 1)


def test_ag10_the_prompt_is_cut_at_200_lines_and_names_no_senior():
    text = "\n".join(f"line {n}" for n in range(300))

    prompt = build_prompt("src/a.py", text, CAPS)

    assert "line 199" in prompt and "line 200" not in prompt and "first 200 of 300" in prompt
    assert "Limits: Customer limits." in prompt
    assert "boss-secret-1" not in prompt and "backup-secret-2" not in prompt


@pytest.mark.parametrize(
    "path", ["src/da_tagger.py", "da_x/a.py", "src/.env", "src/secret_keys.py", "src/skip/a.py"]
)
def test_ag10_assistant_secret_and_excluded_paths_are_never_sent(path):
    assert not is_sendable(path, ["src/skip/*"])


def test_ag10_a_skipped_path_never_reaches_the_ai(tmp_path):
    (tmp_path / "da_own.py").write_text("x = 1\n")
    seen: list[str] = []

    class Spy(ScriptedTaggerClient):
        def complete(self, prompt, system=None):
            seen.append(prompt)
            return super().complete(prompt)

    run = run_tagging(["da_own.py"], tmp_path, CAPS, Spy({}), "a", directory=tmp_path / "o")

    assert seen == [] and run.scanned == 0


@pytest.mark.parametrize(
    "reply",
    [
        "not json", "{}", json.dumps({**GOOD, "capability": "Invented"}),
        json.dumps({**GOOD, "confidence": "certain"}), json.dumps({**GOOD, "summary": ""}),
    ],
)
def test_a_bad_reply_is_refused(reply):
    assert parse_reply(reply, CAPS) is None


def test_a_good_reply_passes_even_in_a_fence():
    assert parse_reply("```json\n" + json.dumps(GOOD) + "\n```", CAPS)["capability"] == "Reports"
    assert parse_reply(json.dumps({**GOOD, "capability": "none"}), CAPS)["capability"] == "none"


def test_the_shipped_script_covers_every_made_up_module():
    shipped = json.loads(FAKE_SCRIPT_FILE.read_text(encoding="utf-8"))["replies"]
    assert set(fake_paths()) == set(shipped)
