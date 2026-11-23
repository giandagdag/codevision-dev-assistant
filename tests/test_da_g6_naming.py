"""Fix G6 S2 and S6: the AI names a group from paths and summaries; empty-catalog prompt line."""

import json
from types import SimpleNamespace

from agents.da_admin_tagger import NO_CAPABILITIES, build_prompt
from agents.da_capability_suggest import build_group_prompt, name_group
from agents.da_code_clusters import Group

GROUP = Group(("md/a.py", "md/b.py", "md/odd.py"), ("md",), 4, 1)


class _Client:
    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def complete(self, prompt, system=None):
        self.prompts.append(prompt)
        return SimpleNamespace(text=self.replies.pop(0))


def _reply(**over):
    base = {"name": "Markdown export", "description": "Writes markdown files",
            "not_in_group": ["md/odd.py"], "confidence": "high"}  # fmt: skip
    return json.dumps({**base, **over})


def test_prompt_has_paths_and_summaries_only():
    prompt = build_group_prompt(["md/a.py"], {"md/a.py": "Writes one file"})

    assert "- md/a.py: Writes one file" in prompt


def test_prompt_is_cut_at_40_programs():
    paths = [f"md/p{i}.py" for i in range(45)]

    assert build_group_prompt(paths, {}).count("- md/p") == 40


def test_named_group_drops_the_paths_that_do_not_fit():
    named = name_group(GROUP, {}, _Client(_reply()))

    assert named.name == "Markdown export" and named.programs == ("md/a.py", "md/b.py")
    assert named.inside == 4 and named.confidence == "high"


def test_one_retry_then_named():
    client = _Client("not json", _reply())

    assert name_group(GROUP, {}, client).name == "Markdown export"
    assert len(client.prompts) == 2


def test_two_bad_replies_give_none():
    assert name_group(GROUP, {}, _Client("x", "y")) is None


def test_name_and_description_limits():
    assert name_group(GROUP, {}, _Client(_reply(name="X"), _reply(name="X"))) is None
    long = name_group(GROUP, {}, _Client(_reply(description="word " * 40)))
    assert len(long.description) <= 120


def test_assistant_files_are_never_sent():
    client = _Client(_reply(not_in_group=[]))
    name_group(Group(("md/a.py", "md/da_secret.py"), ("md",), 1, 0), {}, client)

    assert "da_secret" not in client.prompts[0]


def test_empty_catalog_tells_the_ai_to_suggest_a_new_area(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    assert NO_CAPABILITIES in build_prompt("a.py", "x = 1\n", [])
