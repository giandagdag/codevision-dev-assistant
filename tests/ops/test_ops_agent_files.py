import json
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


def test_builder_is_told_the_exact_test_commands_to_use():
    _, text = front("builder")
    assert "plain `pytest`" in text and "`ruff check .`" in text
    # Don't-ask mode refuses any command with a `$` variable (A-P3, 7 Nov), so none is suggested.
    assert "$DA_PYTHON" not in text
    assert "not the interpreter path" in text and "PowerShell" in text


def test_docs_say_where_to_look_when_a_worker_did_nothing():
    assert "logs\\workers" in DOCS and "permission_denials" in DOCS


def test_builder_can_start_its_reviewers():
    # Pilot A-P4 (7 Nov): without the Agent tool the builder stopped at the plan-review gate.
    meta, text = front("builder")
    assert "Agent" in meta["tools"]
    settings_file = AGENTS.parents[1] / "ops" / "worker_settings.json"
    settings = json.loads(settings_file.read_text(encoding="utf-8"))
    assert "Agent" in settings["permissions"]["allow"]
    assert "One command per Bash call" in text


# ---- Phase A fix 3: small builder runs, the Next helper, one command per Bash call ----

def test_builder_builds_at_most_three_steps_pushes_each_and_sets_next_with_the_command():
    _, text = front("builder")
    for need in ("at most **3 plan steps**", "push at once", "chief_tick.py next",
                 "builder continue Phase N from step K", "exactly one",
                 "Code review starts only after", "do not open a question for Gian"):
        assert need in text


def test_builder_keeps_the_headless_rule_about_background_subagents():
    _, text = front("builder")
    assert "Headless rule: never start a subagent in the background" in text


def test_as7_a_builder_continue_line_means_relaunch_the_builder_and_no_issue():
    _, text = front("chief")
    assert "`Next: builder continue Phase N from step K` means **relaunch the builder**" in text
    assert "Never turn it into a `needs-gian` question" in text


def test_chief_sets_next_only_with_the_command_and_keeps_running_on_its_own_line():
    _, text = front("chief")
    assert "exactly one `- Next:` line" in text and "chief_tick.py next" in text
    assert "never by hand-editing" in text
    assert "Never write, edit or trust a `Running:` line" in text and "never put `Next`" in text


@pytest.mark.parametrize("name", ["builder", "chief", "code-reviewer", "plan-reviewer"])
def test_every_agent_that_may_use_bash_is_told_one_command_per_call(name):
    _, text = front(name)
    assert "one command per" in text.lower()
    assert "`;`" in text and "`&&`" in text


def test_docs_explain_fix_3():
    for need in ("No more silent stalls", "🔴 Team stalled", "no valid Next line",
                 "nothing to do, but the job is not finished", "unpushed commits on",
                 "UNPUSHED: 2 commits on auto/phase-8", "chief_tick.py next",
                 "exactly one `- Next:`",
                 "at most 3 plan steps", "one\ncommand per Bash call", "you close it",
                 "test_ops_zz_real_logs.py", "spec O1"):
        assert need in DOCS, need


# ---- Phase A fix 4 (G7, G9) ----

@pytest.mark.parametrize("name", ["builder", "chief", "code-reviewer"])
def test_g7_one_refusal_is_not_bash_is_off(name):
    _, text = front(name)
    assert "refuses only that command" in text
    assert "three different allowed commands in a row" in text
    assert ".venv/Scripts/python" in text


def test_g1_chief_never_owns_the_running_line_and_uses_the_answer_command():
    _, text = front("chief")
    assert "Only the tick owns it" in text
    assert "chief_tick.py answer N" in text and "waiting for Gian, see #N" in text
    assert "write\n\"Running:" not in text


def test_docs_explain_fix_4():
    for need in ("The chief never sits still by mistake", "Running line removed: no worker",
                 "ANSWER #N", "Only comments by the repo owner", "chief_tick.py answer N",
                 "chief made no progress twice", "Waiting costs nothing", "quotes",
                 "three different allowed commands", "step 13d of 15", "Live from Phase 9"):
        assert need in " ".join(DOCS.split()), need
