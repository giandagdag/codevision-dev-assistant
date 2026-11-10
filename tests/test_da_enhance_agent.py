"""Phase 9 step 8: the today-draft and safety-net AI calls (tests 9-18 and 9-27 prompt parts, 9-19,
9-29, 9-38). No real AI: the scripted fake client or a counting stand-in."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from agents import da_build_agent as build_agent
from agents import da_enhance_agent as enhance
from agents.da_approach_agent import fill_template
from agents.da_build_agent import ScriptedBuildClient
from agents.da_llm_client import LLMReply
from agents.da_safety_net_checks import kept_case_problems
from agents.da_tester_agent import build_plan_prompt
from pydantic_classes.da_enhance_models import ImpactRow, SafetyNet
from pydantic_classes.da_request_record_models import (
    AcceptanceCriterion,
    MustNotChange,
    RequestRecord,
)
from web.da_fake_onprem_server import reply_text

FAKE = Path(__file__).resolve().parents[1] / "src" / "data" / "da_fake_codevision"
TARGET = "src/agents/limits_expiry_report.py"
CHAT_LINE = "SECRET CHAT LINE: please also change the colours"
HIT_LINE = "DISCOVER SNIPPET: def unrelated_hit(): pass"


@pytest.fixture
def files():
    return {TARGET: (FAKE / TARGET).read_text(encoding="utf-8")}


@pytest.fixture
def record():
    return RequestRecord(
        request_id="CVDA-2026-0001",
        rulebook_version=1,
        today="It builds the limits expiry report.",
        functions_in_scope=["days_left", "format_expiry", "ExpiryReport.build_line"],
        must_not_change=[
            MustNotChange(id="NC-1", text="Days left never goes below zero"),
            MustNotChange(id="NC-2", text="The date keeps two digits"),
        ],
        acceptance_criteria=[
            AcceptanceCriterion(id="AC-1", kind="success", given="a", when="b", then="c")
        ],
    )


@pytest.fixture
def impact():
    return [
        ImpactRow(
            caller_path="src/layouts/limits_screen.py",
            caller_function="show",
            line=7,
            function_in_scope="format_expiry",
            kind="direct",
        )
    ]


class Counting:
    """A client that counts calls and gives a fixed reply."""

    model = "fake"

    def __init__(self, text):
        self.text = text
        self.prompts = []

    def complete(self, prompt, system=None):
        self.prompts.append(prompt)
        return LLMReply(text=self.text, provider="fake", model="fake")


def switches(monkeypatch, *names):
    monkeypatch.setattr(build_agent, "FAKE_SWITCHES", frozenset(names))


def scripted():
    return ScriptedBuildClient("tester")


def run_net(tmp_path, files, net):
    """Run a net's test file on the made-up code in a plain subprocess; return failing methods."""
    for path, text in files.items():
        target = tmp_path / path.removeprefix("src/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (tmp_path / "net_checks.py").write_text(net.test_code, encoding="utf-8")
    done = subprocess.run(
        [sys.executable, "-m", "unittest", "net_checks"],
        cwd=tmp_path, capture_output=True, text=True, timeout=60,
    )
    return set(re.findall(r"^(?:FAIL|ERROR): (test_\w+)", done.stderr, re.MULTILINE))


# --- the today-draft ---


def test_the_roles_are_named_in_one_place():
    assert enhance.TODAY_ROLE == "generator"  # WF-7 (a): one line to change
    assert enhance.NET_ROLE == "tester"  # WF-6


def test_the_today_prompt_holds_the_function_text_line_numbered(files):
    prompt, names_only = enhance.build_today_prompt("Modernise.", "Fix the date", files, 100_000)

    assert not names_only
    assert "Symbol: days_left" in prompt
    assert "  11 | def days_left(expiry_day, today_day):" in prompt
    assert "Fix the date" in prompt


def test_a_file_too_big_for_the_limit_sends_the_function_list_only(files):
    prompt, names_only = enhance.build_today_prompt("Modernise.", "Fix", files, 1700)

    assert names_only
    assert "Symbol: days_left" in prompt
    assert "max(expiry_day - today_day, 0)" not in prompt  # no body
    assert "def days_left(expiry_day, today_day)" in prompt  # the signature stays


def test_a_scripted_today_draft_is_checked_and_its_guess_holds_real_symbols(files):
    result = enhance.draft_today(
        scripted(), "Modernise.", "CVDA-2026-0001", "Fix the date", files, 100_000
    )

    assert result.value is not None and result.attempts == 1
    known = {"format_expiry", "days_left", "ExpiryReport", "ExpiryReport.build_line"}
    assert result.value.functions_in_scope_guess
    assert set(result.value.functions_in_scope_guess) <= known


def test_an_unknown_symbol_in_the_guess_is_dropped(files):
    reply = '{"today": "It builds a report.", "functions_in_scope_guess": ["ghost", "days_left"]}'

    result = enhance.draft_today(Counting(reply), "p", "CVDA-2026-0001", "x", files, 100_000)

    assert result.value.functions_in_scope_guess == ["days_left"]


def test_a_draft_with_code_in_it_is_sent_back_and_two_bad_replies_leave_the_box_empty(files):
    reply = '{"today": "def days_left(a, b):\\n    return 1", "functions_in_scope_guess": []}'
    client = Counting(reply)

    result = enhance.draft_today(client, "p", "CVDA-2026-0001", "x", files, 100_000)

    assert result.value is None and result.kind == "bad_reply"
    assert len(client.prompts) == 2 and "no code" in client.prompts[1]


def test_9_19_two_unusable_scripted_replies_give_no_draft(files, monkeypatch):
    switches(monkeypatch, "today_unusable")

    result = enhance.draft_today(scripted(), "p", "CVDA-2026-0001", "x", files, 100_000)

    assert result.value is None and result.attempts == 2 and result.kind == "bad_reply"


def test_a_names_only_draft_says_so(files):
    reply = '{"today": "It builds a report.", "functions_in_scope_guess": []}'

    result = enhance.draft_today(Counting(reply), "p", "CVDA-2026-0001", "x", files, 1700)

    assert result.value is not None and result.message == enhance.NAMES_ONLY_NOTE


# --- the safety-net prompt (9-29: apart from the criterion Tester calls) ---


def test_the_net_prompt_holds_in_scope_bodies_and_other_signatures_only(
    record, files, impact, seed_rulebook
):
    in_scope = record.model_copy(update={"functions_in_scope": ["days_left"]})

    prompt = enhance.build_net_prompt(in_scope, files, impact, seed_rulebook.policy)

    assert "max(expiry_day - today_day, 0)" in prompt  # the in-scope body
    assert "format_expiry(day, month, year)" in prompt  # another function: signature ...
    assert 'f"{day:02d}/{month:02d}/{year}"' not in prompt  # ... but not its body
    assert "AC-1" in prompt and "NC-1" in prompt
    assert "src/layouts/limits_screen.py line 7" in prompt  # the impact row
    assert enhance.NET_MARKER in prompt.splitlines()


def test_9_29_the_criterion_tester_prompt_still_holds_no_code(record, files):
    plan = build_plan_prompt(record, [])

    assert "def days_left" not in plan and "max(expiry_day" not in plan


def test_9_29_the_net_prompt_has_no_room_for_the_chat_or_discover_snippets(
    record, files, impact, seed_rulebook
):
    # The builder takes no chat and no hits, so nothing of them can get in.
    prompt = enhance.build_net_prompt(record, files, impact, seed_rulebook.policy)

    assert CHAT_LINE not in prompt and HIT_LINE not in prompt
    parameters = enhance.build_net_prompt.__code__.co_varnames[
        : enhance.build_net_prompt.__code__.co_argcount
    ]
    assert parameters == ("record", "files", "impact", "policy")


def test_every_placeholder_of_the_prompt_files_is_filled(record, files, impact, seed_rulebook):
    text = enhance.build_net_prompt(record, files, impact, seed_rulebook.policy)
    net = SafetyNet()
    fix = enhance.build_net_fix_prompt(
        record, files, impact, seed_rulebook.policy, net, "S-1 failed", ["S-2"], "my note"
    )

    for prompt in (text, fix):
        assert "{{" not in prompt
    assert enhance.CORRECT_MARKER in fix.splitlines()
    assert "S-2" in fix and "my note" in fix
    assert fill_template  # the same one-pass filler the other agents use


# --- the safety-net calls ---


def test_a_scripted_net_is_accepted_and_all_but_one_case_pass_on_today_s_code(
    record, files, impact, seed_rulebook, tmp_path
):
    result = enhance.write_safety_net(scripted(), record, files, impact, seed_rulebook.policy)

    assert result.value is not None and result.attempts == 1
    assert len(result.value.cases) == 3
    failing = run_net(tmp_path, files, result.value)
    # The demo's "fails at first": the first case (the date format) is wrong until the fix call.
    assert [name.split("_")[1] for name in failing] == ["s1"]


def test_9_27_the_fix_call_repairs_the_failing_case_and_keeps_the_proven_ones_byte_for_byte(
    record, files, impact, seed_rulebook, tmp_path
):
    policy = seed_rulebook.policy
    first = enhance.write_safety_net(scripted(), record, files, impact, policy).value

    fixed = enhance.revise_safety_net(
        scripted(), record, files, impact, policy, first, "S-1 failed", ["S-2", "S-3"]
    )

    assert fixed.value is not None
    assert run_net(tmp_path, files, fixed.value) == set()
    assert kept_case_problems(first, fixed.value, ["S-2", "S-3"]) == []


def test_a_case_that_keeps_failing_still_fails_after_the_fix_call(
    record, files, impact, seed_rulebook, tmp_path, monkeypatch
):
    switches(monkeypatch, "net_case_keeps_failing")
    policy = seed_rulebook.policy
    first = enhance.write_safety_net(scripted(), record, files, impact, policy).value

    again = enhance.revise_safety_net(
        scripted(), record, files, impact, policy, first, "S-1 failed", ["S-2", "S-3"]
    )

    assert again.value is not None
    assert len(run_net(tmp_path, files, again.value)) == 1


def test_a_fix_reply_that_changes_a_proven_case_is_sent_back(
    record, files, impact, seed_rulebook
):
    policy = seed_rulebook.policy
    first = enhance.write_safety_net(scripted(), record, files, impact, policy).value
    changed = first.model_copy(
        update={"test_code": first.test_code.replace("5 days left", "6 days left")}  # S-3's text
    )
    client = Counting(changed.model_dump_json())

    result = enhance.revise_safety_net(
        client, record, files, impact, policy, first, "S-1 failed", ["S-2", "S-3"]
    )

    assert result.value is None and result.kind == "bad_reply"
    assert any("already proven" in problem for problem in result.problems)
    assert "already proven" in client.prompts[1]


def test_two_unusable_net_replies_give_bad_reply(record, files, impact, seed_rulebook, monkeypatch):
    switches(monkeypatch, "net_unusable")

    result = enhance.write_safety_net(scripted(), record, files, impact, seed_rulebook.policy)

    assert result.value is None and result.kind == "bad_reply" and result.attempts == 2


def test_a_net_that_names_a_function_out_of_scope_is_sent_back(
    record, files, impact, seed_rulebook
):
    first = enhance.write_safety_net(
        scripted(), record, files, impact, seed_rulebook.policy
    ).value
    ghost = first.cases[0].model_copy(update={"function": "ghost"})
    bad = first.model_copy(update={"cases": [ghost, *first.cases[1:]]})

    result = enhance.write_safety_net(
        Counting(bad.model_dump_json()), record, files, impact, seed_rulebook.policy
    )

    assert result.value is None
    assert any("ghost" in problem for problem in result.problems)


def test_a_net_prompt_over_the_tester_limit_is_not_sent(record, files, impact, seed_rulebook):
    policy = seed_rulebook.policy.model_copy(update={"tester_max_prompt_chars": 500})
    client = Counting("{}")

    result = enhance.write_safety_net(client, record, files, impact, policy)

    assert result.kind == "too_big" and client.prompts == []


def test_the_pretend_work_server_answers_the_four_enhance_prompts(
    record, files, impact, seed_rulebook
):
    policy = seed_rulebook.policy
    today, _ = enhance.build_today_prompt("p", "Fix", files, 100_000)
    net_prompt = enhance.build_net_prompt(record, files, impact, policy)
    first = enhance.write_safety_net(scripted(), record, files, impact, policy).value
    fix = enhance.build_net_fix_prompt(record, files, impact, policy, first, "x", ["S-1"])
    correct = enhance.build_net_fix_prompt(record, files, impact, policy, first, "", [], "note")

    assert '"today"' in reply_text(today, "ok")
    assert '"cases"' in reply_text(net_prompt, "ok")
    assert '"cases"' in reply_text(fix, "ok")
    assert '"cases"' in reply_text(correct, "ok")
    assert all(enhance.is_enhance_prompt(p) for p in (today, net_prompt, fix, correct))
    assert not enhance.is_enhance_prompt("Task: something else")
