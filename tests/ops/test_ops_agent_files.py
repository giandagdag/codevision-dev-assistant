import re
from pathlib import Path

import pytest

AGENTS = Path(__file__).resolve().parents[2] / ".claude" / "agents"
EXPECTED = {"chief": "sonnet", "spec-writer": "opus", "builder": "sonnet",
            "status-digest": "haiku", "plan-reviewer": "sonnet", "code-reviewer": "sonnet"}


def front(name):
    text = (AGENTS / f"{name}.md").read_text(encoding="utf-8")
    block = re.match(r"---\n(.*?)\n---\n", text, re.S).group(1)
    return dict(line.split(": ", 1) for line in block.splitlines()), text


@pytest.mark.parametrize("name,model", EXPECTED.items())
def test_each_agent_has_its_model_and_a_description(name, model):
    meta, _ = front(name)
    assert meta["name"] == name and meta["model"] == model and meta["description"]


@pytest.mark.parametrize("name", ["chief", "spec-writer", "builder", "status-digest"])
def test_every_worker_prompt_tells_it_to_stop_when_the_guard_blocks(name):
    _, text = front(name)
    assert "ops/state/worker_note.md" in text and "stop at once" in text


def test_chief_has_every_row_of_the_decision_rule_and_the_never_list():
    _, text = front("chief")
    for row in ("Chosen by chief, 6.1", "work facts", "needs-gian", "needs-work-test",
                "`.env`", "no recommendation", "equally good", "2 fix attempts",
                "Guard says STOP", "Never assume"):
        assert row in text or row.replace("no recommendation", "has no recommendation") in text
    for never in ("Merge into `main`", "Force-push", "Rebase shared branches", "Edit `.env`",
                  "Install a plugin"):
        assert never in text


def test_chief_never_writes_product_code_and_knows_the_helpers():
    meta, text = front("chief")
    assert "never write product code" in text
    assert "chief_tick.py issue" in text and "chief_tick.py pause" in text
    assert "chief_tick.py merge" in text


DOCS = (AGENTS.parent.parent / "docs" / "automation.md").read_text(encoding="utf-8")


def test_docs_do_not_rely_on_branch_protection_which_this_repo_cannot_have():
    assert "Do not allow bypassing" not in DOCS
    assert "required status check" not in DOCS
    low = DOCS.lower()
    assert "private" in low and "free" in low and "branch protection is not available" in low
    for safety_net in ("hook", "deny list", "ZIP"):
        assert safety_net in DOCS


def test_docs_keep_the_unattended_run_checklist():
    for need in ("Before the first unattended run", "Download ZIP", "Revert",
                 "usage_raw.json"):
        assert need in DOCS
