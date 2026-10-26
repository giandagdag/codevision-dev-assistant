import subprocess
import sys
from types import SimpleNamespace

import anthropic
import pytest

from agents.da_llm_client import LLMClientError, get_llm_client
from configs.da_config import PROJECT_ROOT, ConfigError


class FakeAnthropic:
    """Stands in for anthropic.Anthropic. Records what was sent and replies with fixed text."""

    last = None

    def __init__(self, api_key):
        self.api_key = api_key
        self.sent = None
        self.messages = SimpleNamespace(create=self._create)
        FakeAnthropic.last = self

    def _create(self, **request):
        self.sent = request
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="text", text="Hello "),
                SimpleNamespace(type="thinking", thinking="ignored"),
                SimpleNamespace(type="text", text="team"),
            ]
        )


class FailingAnthropic(FakeAnthropic):
    def _create(self, **request):
        raise BrokenCall()


class BrokenCall(anthropic.APIError):
    def __init__(self):  # skip the library's own setup; we only need the error type
        pass


def claude_settings(make_settings, **changes):
    values = {
        "llm_provider": "claude",
        "anthropic_api_key": "test-key-not-real",
        "claude_generator_model": "test-generator-model",
        "claude_reviewer_model": "test-reviewer-model",
    }
    values.update(changes)
    return make_settings(**values)


# --- fake provider ---


def test_fake_reply_is_predictable(make_settings):
    client = get_llm_client("generator", make_settings())

    reply = client.complete("Explain this COBOL paragraph please, in plain words")

    # The first 40 characters of the prompt; the 40th is the space after "in".
    assert reply.text == "[fake reply] Explain this COBOL paragraph please, in "
    assert reply.provider == "fake"
    assert reply.model == "fake-generator"


def test_fake_reviewer_names_its_role(make_settings):
    reply = get_llm_client("reviewer", make_settings()).complete("hi", system="be brief")

    assert reply.model == "fake-reviewer"


def test_unknown_role_is_rejected(make_settings):
    with pytest.raises(ValueError, match="generator, reviewer"):
        get_llm_client("planner", make_settings())


# --- claude provider ---


def test_claude_without_api_key_gives_plain_message(make_settings):
    settings = claude_settings(make_settings, anthropic_api_key="")

    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY is missing"):
        get_llm_client("generator", settings)


def test_claude_without_generator_model_gives_plain_message(make_settings):
    settings = claude_settings(make_settings, claude_generator_model="")

    with pytest.raises(ConfigError, match="DA_CLAUDE_GENERATOR_MODEL is missing"):
        get_llm_client("generator", settings)


def test_claude_without_reviewer_model_gives_plain_message(make_settings):
    settings = claude_settings(make_settings, claude_reviewer_model="")

    with pytest.raises(ConfigError, match="DA_CLAUDE_REVIEWER_MODEL is missing"):
        get_llm_client("reviewer", settings)


def test_missing_reviewer_model_does_not_block_generator(make_settings, monkeypatch):
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    settings = claude_settings(make_settings, claude_reviewer_model="")

    assert get_llm_client("generator", settings).model == "test-generator-model"


def test_claude_reply_comes_from_mocked_library(make_settings, monkeypatch):
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)

    reply = get_llm_client("generator", claude_settings(make_settings)).complete("Say hello")

    assert reply.text == "Hello team"
    assert reply.provider == "claude"
    assert reply.model == "test-generator-model"
    sent = FakeAnthropic.last.sent
    assert sent["model"] == "test-generator-model"
    assert sent["messages"] == [{"role": "user", "content": "Say hello"}]
    assert "system" not in sent


def test_claude_uses_the_role_model_and_system_text(make_settings, monkeypatch):
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)

    get_llm_client("reviewer", claude_settings(make_settings)).complete("x", system="be brief")

    assert FakeAnthropic.last.sent["model"] == "test-reviewer-model"
    assert FakeAnthropic.last.sent["system"] == "be brief"


def test_claude_call_failure_gives_plain_message(make_settings, monkeypatch):
    monkeypatch.setattr(anthropic, "Anthropic", FailingAnthropic)
    client = get_llm_client("generator", claude_settings(make_settings))

    with pytest.raises(LLMClientError, match="The Claude call failed"):
        client.complete("Say hello")


def test_api_key_is_not_logged(make_settings, monkeypatch, caplog):
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)

    get_llm_client("generator", claude_settings(make_settings)).complete("Say hello")

    assert "test-key-not-real" not in caplog.text


# --- onprem provider ---


def test_onprem_says_not_configured_yet(make_settings):
    with pytest.raises(ConfigError, match="not configured yet"):
        get_llm_client("generator", make_settings(llm_provider="onprem"))


# --- without the anthropic library (as at work) ---

# Runs in a separate Python, so blocking the library cannot affect the other tests.
# sys.modules["anthropic"] = None makes "import anthropic" fail, as if it were not installed.
WITHOUT_ANTHROPIC_SCRIPT = """
import sys
sys.modules["anthropic"] = None
from agents.da_llm_client import get_llm_client
from configs.da_config import ConfigError, Settings

def settings(provider):
    return Settings(provider, "gen-model", "rev-model", "unused.db", anthropic_api_key="test-key")

print(get_llm_client("generator", settings("fake")).complete("hello").provider)
for provider in ("onprem", "claude"):
    try:
        get_llm_client("generator", settings(provider))
    except ConfigError as error:
        print(error)
"""


def test_module_loads_without_anthropic_installed():
    result = subprocess.run(
        [sys.executable, "-c", WITHOUT_ANTHROPIC_SCRIPT],
        cwd=PROJECT_ROOT / "src",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "fake"
    assert "not configured yet" in lines[1]
    assert "needs the anthropic library" in lines[2]
