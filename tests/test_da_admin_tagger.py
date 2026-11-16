"""Phase 11 fix 2, step 3: the tagger core (AG-4, AG-5, AG-9, AG-10). Made-up only, no real AI."""

import json
from pathlib import Path

import pytest

from agents.da_admin_tag_store import read_store, read_tags
from agents.da_admin_tagger import (
    FAKE_SCRIPT_FILE,
    NOT_SAVED,
    ScriptedTaggerClient,
    build_prompt,
    is_sendable,
    parse_reply,
    paths_to_tag,
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
    assert len(read_tags(out)) == 19 and read_store(out)["runs"][0]["skipped"] == ["m0.py"]


def test_ag5_three_bad_in_20_is_not_saved_and_old_tags_stay(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    paths = make_modules(src, 20)
    run_tagging(paths[:5], src, CAPS, scripted(paths, 0), "admin1", directory=out)
    before = read_store(out)

    run = run_tagging(paths, src, CAPS, scripted(paths, 3), "admin1", directory=out)

    assert (run.saved, run.message) == (False, NOT_SAVED)
    assert read_store(out) == before


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
        json.dumps({**GOOD, "summary": "x" * 121}), json.dumps({**GOOD, "reason": "y" * 161}),
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
